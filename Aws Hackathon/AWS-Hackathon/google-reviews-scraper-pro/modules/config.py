"""
Configuration management for the Google Maps Reviews Scraper.
This file can be overridden by a local config.yaml file.
"""

import logging
from pathlib import Path
from typing import Dict, Any
import os
import yaml

# --- Logging Configuration ---
# Set logging level from environment variable or default to INFO
log_level = getattr(logging, os.environ.get('LOG_LEVEL', 'INFO').upper(), logging.INFO)
logging.basicConfig(level=log_level, format="[%(asctime)s] %(levelname)s: %(message)s")
log = logging.getLogger("scraper")

# --- Default Configuration Path ---
# This is a new line to define the path for the config file.
DEFAULT_CONFIG_PATH = Path("config.yaml")

# --- Default Configuration ---
# These are the default settings. They will be merged with any user-provided
# config.yaml file, with the user's settings taking precedence.
DEFAULT_CONFIG = {
    # The URL to the Google Maps location to scrape
    "url": "https://maps.app.goo.gl/6tkNMDjcj3SS6LJe9",
    
    # Browser settings
    "headless": True, # Run browser in headless mode (no UI)
    "sort_by": "relevance", # Sort reviews by 'relevance' or 'newest'
    
    # Scraping control
    "stop_on_match": False, # Stop scraping when a review ID is already found
    "overwrite_existing": False, # Overwrite existing reviews in the database
    
    # MongoDB settings
    "use_mongodb": True,
    "mongodb": {
        "uri": "mongodb://localhost:27017",
        "database": "reviews",
        "collection": "google_reviews"
    },
    
    # JSON backup settings
    "backup_to_json": True,
    "json_path": "google_reviews.json",
    
    # Data management settings
    "seen_ids_path": "google_reviews.ids",
    "convert_dates": True, # Convert review dates to datetime objects
    
    # Image downloading settings
    "download_images": True,
    "image_dir": "review_images",
    "download_threads": 4, # Number of concurrent threads for downloading images
    "store_local_paths": True, # Store the local path to the downloaded image
    
    # URL replacement settings (for custom content delivery networks)
    "replace_urls": False,
    "custom_url_base": "https://mycustomurl.com",
    "custom_url_profiles": "/profiles/",
    "custom_url_reviews": "/reviews/",
    "preserve_original_urls": True, # Keep the original URLs in the data
    
    # Custom parameters to add to each document.
    # The "company" value is now handled dynamically by scraper.py.
    "custom_params": {
        "source": "Google Maps"
    }
}

# --- Configuration Loading Function ---
def load_config(config_path: Path = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    """
    Load configuration from a YAML file or use defaults.
    Includes a helper function for deep merging dictionaries.
    """
    config = DEFAULT_CONFIG.copy()

    # Helper function to recursively merge dictionaries
    def deep_update(d, u):
        for k, v in u.items():
            if isinstance(v, dict) and k in d and isinstance(d[k], dict):
                deep_update(d[k], v)
            else:
                d[k] = v

    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                user_config = yaml.safe_load(f)
                if user_config:
                    deep_update(config, user_config)
                    log.info(f"Loaded configuration from {config_path}")
        except Exception as e:
            log.error(f"Error loading config from {config_path}: {e}")
            log.info("Using default configuration")
    else:
        log.info(f"Config file {config_path} not found, using default configuration")
        # Create a default config file for future use
        try:
            with open(config_path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False)
                log.info(f"Created default configuration file at {config_path}")
        except Exception as e:
            log.error(f"Could not create default config file at {config_path}: {e}")

    return config
