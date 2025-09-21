from flask import Flask, request, jsonify
from flask_cors import CORS
import uuid
import threading
import time

# A clean, simple dictionary for our test jobs
jobs = {}

def a_slow_background_task(job_id):
    """
    This function ONLY simulates a delay. It proves the threading concept.
    """
    print(f"BACKGROUND TASK: Starting 10-second wait for job {job_id}.")
    time.sleep(10)
    
    # When the wait is over, create some fake result data
    result_data = {
        "company_name": "Minimal Test Cafe",
        "reviews": [{"author_name": "Success!", "rating": 5, "text": "The background task worked!", "prediction": "Real"}]
    }
    
    # Update the job status
    jobs[job_id]['status'] = 'complete'
    jobs[job_id]['result'] = result_data
    print(f"BACKGROUND TASK: Job {job_id} is now complete.")

# --- Flask App Setup ---
app = Flask(__name__)
CORS(app)

@app.route('/detect', methods=['POST'])
def detect_start():
    job_id = str(uuid.uuid4())
    jobs[job_id] = {'status': 'running', 'result': None}

    # Start the slow task in the background
    thread = threading.Thread(target=a_slow_background_task, args=(job_id,))
    thread.start()

    # IMMEDIATELY return the job_id
    print(f"IMMEDIATE RESPONSE: Sent job_id {job_id} to the browser.")
    return jsonify({"job_id": job_id}), 202

@app.route('/results/<job_id>', methods=['GET'])
def get_results(job_id):
    job = jobs.get(job_id)
    print(f"POLLING CHECK: Browser is asking for status of job {job_id}.")
    return jsonify(job)

if __name__ == '__main__':
    # Make sure your main server is not running on port 5000
    # We will run this test on port 5001 to be safe
    app.run(port=5001, debug=True, threaded=True)