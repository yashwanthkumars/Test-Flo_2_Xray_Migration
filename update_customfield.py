import pandas as pd
import requests
from requests.auth import HTTPBasicAuth
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import threading
from datetime import datetime

# --- Configuration ---
JIRA_CLOUD_URL = "https://greyorange-work-uat-sandbox.atlassian.net"
JIRA_EMAIL = "yashwanth.k@padahsolutions.com"
JIRA_API_TOKEN = "YOUR_TOKEN"
CSV_FILE_PATH = "Moredetail_field_values_export_20260127_112342.csv"  # Replace with your actual file name

# IMPORTANT: Replace 'customfield_10001' with your actual Jira Custom Field ID
CUSTOM_FIELD_ID = "customfield_10568" 

# Performance settings
MAX_WORKERS = 10 # Number of parallel threads

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(threadName)-10s] - %(message)s',
    handlers=[
        logging.FileHandler(f'update_customfield_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Thread-safe counter for progress tracking
class ProgressCounter:
    def __init__(self, total):
        self.lock = threading.Lock()
        self.success = 0
        self.failed = 0
        self.skipped = 0
        self.total = total
    
    def increment_success(self):
        with self.lock:
            self.success += 1
            return self.success
    
    def increment_failed(self):
        with self.lock:
            self.failed += 1
            return self.failed
    
    def increment_skipped(self):
        with self.lock:
            self.skipped += 1
            return self.skipped
    
    def get_stats(self):
        with self.lock:
            return {
                'success': self.success,
                'failed': self.failed,
                'skipped': self.skipped,
                'processed': self.success + self.failed + self.skipped
            }

# --- Setup Authentication ---
auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
headers = {
    "Accept": "application/json",
    "Content-Type": "application/json"
}

def convert_to_adf(text_value):
    """Convert plain text to Atlassian Document Format for paragraph fields"""
    if pd.isna(text_value) or text_value == "":
        return None
    
    return {
        "version": 1,
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": str(text_value)
                    }
                ]
            }
        ]
    }

def update_jira_issue(issue_key, new_value):
    """Update a single Jira issue's custom field"""
    url = f"{JIRA_CLOUD_URL}/rest/api/3/issue/{issue_key}"
    
    # Convert to ADF format for paragraph field
    adf_value = convert_to_adf(new_value)
    
    if adf_value is None:
        logger.warning(f"⚠️  {issue_key}: Skipping - empty value")
        return {'issue_key': issue_key, 'status': 'Skipped', 'message': 'Empty value'}
    
    # Construct the payload
    payload = json.dumps({
        "fields": {
            CUSTOM_FIELD_ID: adf_value
        }
    })

    try:
        response = requests.request(
            "PUT",
            url,
            data=payload,
            headers=headers,
            auth=auth,
            timeout=30
        )

        if response.status_code == 204:
            logger.info(f"✅ {issue_key}: Successfully updated")
            return {'issue_key': issue_key, 'status': 'Success', 'message': 'Updated successfully'}
        else:
            logger.error(f"❌ {issue_key}: Failed - {response.status_code} - {response.text}")
            return {'issue_key': issue_key, 'status': 'Failed', 'message': f"{response.status_code} - {response.text}"}
    
    except Exception as e:
        logger.error(f"❌ {issue_key}: Exception - {str(e)}")
        return {'issue_key': issue_key, 'status': 'Failed', 'message': f'Exception: {str(e)}'}

# --- Main Execution ---
def main():
    start_time = datetime.now()
    logger.info("="*60)
    logger.info("🚀 Starting Custom Field Update")
    logger.info("="*60)
    logger.info(f"Input file: {CSV_FILE_PATH}")
    logger.info(f"Field ID: {CUSTOM_FIELD_ID}")
    logger.info(f"Parallel workers: {MAX_WORKERS}")
    logger.info("")
    
    try:
        df = pd.read_csv(CSV_FILE_PATH)
        total_rows = len(df)
        
        logger.info(f"Total issues to update: {total_rows}")
        logger.info("")
        
        # Initialize counter
        counter = ProgressCounter(total_rows)
        
        # Prepare tasks
        tasks = []
        for index, row in df.iterrows():
            issue_key = row['Issue_key']
            field_value = row['Custom_fi']
            tasks.append((issue_key, field_value))
        
        # Process updates in parallel
        results = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Submit all tasks
            future_to_issue = {
                executor.submit(update_jira_issue, issue_key, field_value): issue_key 
                for issue_key, field_value in tasks
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_issue):
                try:
                    result = future.result()
                    results.append(result)
                    
                    # Update counter
                    if result['status'] == 'Success':
                        counter.increment_success()
                    elif result['status'] == 'Skipped':
                        counter.increment_skipped()
                    else:
                        counter.increment_failed()
                    
                    # Log progress
                    stats = counter.get_stats()
                    if stats['processed'] % 10 == 0 or stats['processed'] == total_rows:
                        logger.info(f"Progress: {stats['processed']}/{total_rows} issues processed")
                        
                except Exception as e:
                    issue_key = future_to_issue[future]
                    logger.error(f"Exception processing {issue_key}: {e}")
                    results.append({'issue_key': issue_key, 'status': 'Failed', 'message': str(e)})
                    counter.increment_failed()
        
        # Save results to CSV
        output_file = f"update_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        results_df = pd.DataFrame(results)
        results_df.to_csv(output_file, index=False, encoding='utf-8')
        
        elapsed_time = datetime.now() - start_time
        stats = counter.get_stats()
        
        logger.info("")
        logger.info("="*60)
        logger.info("📈 FINAL SUMMARY")
        logger.info("="*60)
        logger.info(f"✅ Success:  {stats['success']}/{total_rows}")
        logger.info(f"⚠️  Skipped:  {stats['skipped']}/{total_rows}")
        logger.info(f"❌ Failed:   {stats['failed']}/{total_rows}")
        logger.info(f"⏱️  Time:     {elapsed_time.total_seconds():.1f} seconds")
        logger.info(f"💾 Results:  {output_file}")
        logger.info("="*60)

    except FileNotFoundError:
        logger.error(f"Input file not found: {CSV_FILE_PATH}")
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)

if __name__ == "__main__":
    main()