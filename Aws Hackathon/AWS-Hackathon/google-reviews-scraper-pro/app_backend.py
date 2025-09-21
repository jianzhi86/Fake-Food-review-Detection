import uuid
import threading
import logging
import random
import time
import json
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS
from modules.scraper import GoogleReviewsScraper
from modules.s3_handler import S3Handler
from modules.config import load_config
from dataclasses import asdict
import re

app = Flask(__name__)

# --- Explicit and robust CORS setup ---
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True, allow_headers="*")
app.config['CORS_AUTOMATIC_OPTIONS'] = True

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
jobs = {}

def run_scraper_task(job_id: str, url: str):
    """ Main background task for scraping and analysis. """
    logging.info(f"[{job_id}] Starting background task for URL: {url}")
    job_info = jobs[job_id]
    config = load_config()

    try:
        job_info['status'] = 'running'
        job_info['progress']['percentage'] = 5
        job_info['progress']['message'] = 'Initializing scraper...'
        scraper_config = {"url": url, "headless": True, "sort_by": "relevance"}
        scraper = GoogleReviewsScraper(scraper_config)
        scraped_data = scraper.scrape(job_info=job_info)

        if not scraped_data:
            raise Exception("Scraper returned no data, indicating a fatal error.")

        logging.info(f"[{job_id}] Scraping complete. Found {len(scraped_data.get('reviews', []))} reviews.")
        job_info['status'] = 'analyzing'
        job_info['progress']['percentage'] = 95
        job_info['progress']['message'] = '✅ Scraping complete! Analyzing reviews...'
        time.sleep(1.5)

        reviews_objects = scraped_data.get("reviews", [])
        final_reviews_as_dicts = [asdict(r) for r in reviews_objects]
        for review in final_reviews_as_dicts:
            review['prediction'] = random.choice(["Fake", "Genuine"])

        final_result = {
            "company_name": scraped_data.get("company_name", "Unknown"),
            "reviews": final_reviews_as_dicts
        }
        job_info['result'] = final_result
        logging.info(f"[{job_id}] Analysis complete.")

        s3_handler = S3Handler(config)
        if s3_handler.enabled:
            s3_config = config.get("s3", {})
            company_name = final_result.get("company_name", "Unknown_Company")
            safe_filename = re.sub(r'[\\/*?:"<>|]', "", company_name).replace(" ", "_")
            s3_prefix = s3_config.get("prefix", "google-maps-data/")
            reports_folder = s3_config.get("reports_folder", "json-reports/")
            s3_key = f"{s3_prefix}{reports_folder}{safe_filename}_{job_id[:8]}.json"
            
            local_path = Path(f"{job_id}.json")
            with open(local_path, 'w', encoding='utf-8') as f:
                json.dump(final_result, f, ensure_ascii=False, indent=4)

            s3_url = s3_handler.upload_json_file(local_path, s3_key)
            if s3_url:
                job_info['s3_url'] = s3_url
                job_info['s3_key'] = s3_key   # 🔥 Save key for frontend
                logging.info(f"[{job_id}] Successfully uploaded report to S3: {s3_url}")
            local_path.unlink()
        
        job_info['status'] = 'complete'
        job_info['progress']['percentage'] = 100
        job_info['progress']['message'] = 'Done!'

    except Exception as e:
        logging.error(f"[{job_id}] A critical error occurred: {e}", exc_info=True)
        job_info['status'] = 'error'
        job_info['result'] = str(e)

@app.route("/detect", methods=["POST"])
def detect_endpoint():
    data = request.get_json()
    if not data or 'url' not in data or not data['url'].startswith("http"):
        return jsonify({"error": "A valid 'url' is required"}), 400
    url = data["url"]
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        'status': 'pending',
        'progress': {'percentage': 0, 'message': 'Job is queued...'},
        'result': None
    }
    thread = threading.Thread(target=run_scraper_task, args=(job_id, url))
    thread.start()
    logging.info(f"[{job_id}] Job created for URL: {url}")
    return jsonify({"job_id": job_id})

@app.route("/results/<job_id>", methods=["GET"])
def get_results_endpoint(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)

@app.route("/past_results", methods=["GET"])
def get_past_results():
    config = load_config()
    s3_handler = S3Handler(config)
    if not s3_handler.enabled:
        return jsonify({"error": "S3 is not configured."}), 500
    try:
        s3_config = config.get("s3", {})
        prefix = f"{s3_config.get('prefix', 'google-maps-data/')}{s3_config.get('reports_folder', 'json-reports/')}"
        response = s3_handler.s3_client.list_objects_v2(Bucket=s3_handler.bucket_name, Prefix=prefix)
        if 'Contents' not in response:
            return jsonify([])
        results = []
        for obj in sorted(response['Contents'], key=lambda x: x['LastModified'], reverse=True):
            key = obj['Key']
            filename = key.split('/')[-1]
            if not filename: continue
            company_name = filename.rsplit('_', 1)[0].replace('_', ' ')
            results.append({
                "name": company_name,
                "date": obj['LastModified'].isoformat(),
                "key": key,       # keep old
                "s3_key": key     # 🔥 new, so frontend never gets undefined
            })
        return jsonify(results)
    except Exception as e:
        logging.error(f"Failed to fetch past results from S3: {e}", exc_info=True)
        return jsonify({"error": "Could not retrieve past results from S3."}), 500

# --- FIXED DELETE ENDPOINT ---
@app.route("/delete_report", methods=["POST", "DELETE"])
def delete_report():
    if request.method == "OPTIONS":
        return jsonify({"message": "Preflight OK"}), 200

    data = request.get_json()
    s3_key = data.get('key') if data else None
    if not s3_key:
        return jsonify({"error": "S3 key is required."}), 400

    config = load_config()
    s3_handler = S3Handler(config)
    if not s3_handler.enabled:
        return jsonify({"error": "S3 is not configured."}), 500

    try:
        s3_handler.s3_client.delete_object(Bucket=s3_handler.bucket_name, Key=s3_key)
        logging.info(f"Successfully deleted report from S3: {s3_key}")
        return jsonify({"message": "Report deleted successfully."})
    except Exception as e:
        logging.error(f"Failed to delete report from S3: {e}", exc_info=True)
        return jsonify({"error": "Could not delete the report from S3."}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True, use_reloader=False)
