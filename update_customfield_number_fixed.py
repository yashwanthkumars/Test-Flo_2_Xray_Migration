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
CSV_FILE_PATH = "Fail_count_field_values_export_20260120_131716.csv"

# Field configuration
CUSTOM_FIELD_ID = "customfield_10220"
FIELD_TYPE = "number"  # FORCE number type for this field

# Performance settings
MAX_WORKERS = 10

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

# Thread-safe counter
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
    
    def increment_failed(self):
        with self.lock:
            self.failed += 1
    
    def increment_skipped(self):
        with self.lock:
            self.skipped += 1
    
    def get_stats(self):
        with self.lock:
            return {
                'success': self.success,
                'failed': self.failed,
                'skipped': self.skipped,
                'processed': self.success + self.failed + self.skipped
            }

# Setup Auth
auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
headers = {
    "Accept": "application/json",
    "Content-Type": "application/json"
}

def convert_to_number(value):
    """Convert value to pure number for number fields"""
    if pd.isna(value) or value == "" or value == "None" or value is None:
        return None
    
    try:
        value_str = str(value).strip()
        # Remove any commas
        value_str = value_str.replace(',', '')
        
        # Convert to float
        num = float(value_str)
        
        # Validate range (< 100 trillion)
        if abs(num) >= 100_000_000_000_000:
            logger.warning(f"Number too large: {num}")
            return None
        
        # Return as int if whole number
        return int(num) if num.is_integer() else num
        
    except (ValueError, AttributeError, TypeError) as e:
        logger.warning(f"Could not convert '{value}' to number: {e}")
        return None

def update_jira_issue(issue_key, new_value):
    """Update a single Jira issue's custom field with a number"""
    url = f"{JIRA_CLOUD_URL}/rest/api/3/issue/{issue_key}"
    
    # Convert to number
    field_value = convert_to_number(new_value)
    
    if field_value is None:
        logger.warning(f"⚠️  {issue_key}: Skipping - empty or invalid value ('{new_value}')")
        return {'issue_key': issue_key, 'status': 'Skipped', 'message': 'Empty or invalid value'}
    
    # Important: For number fields, send as plain number in JSON, not as object
    # This is the KEY fix - numbers must be sent as numbers, not wrapped in objects
    payload = json.dumps({
        "fields": {
            CUSTOM_FIELD_ID: field_value  # Plain number, not {"value": field_value}
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
            logger.info(f"✅ {issue_key}")
            return {'issue_key': issue_key, 'status': 'Success', 'message': f'Updated'}
        else:
            logger.error(f"❌ {issue_key}: Failed - {response.status_code} - {response.text[:200]}")
            return {'issue_key': issue_key, 'status': 'Failed', 'message': f"{response.status_code}"}
    
    except Exception as e:
        logger.error(f"❌ {issue_key}: Exception - {str(e)}")
        return {'issue_key': issue_key, 'status': 'Failed', 'message': f'Exception: {str(e)}'}

# Main function
def main():
    start_time = datetime.now()
    logger.info("="*70)
    logger.info("🚀 Starting Custom Field Update - NUMBER FIELD")
    logger.info("="*70)
    logger.info(f"Input file: {CSV_FILE_PATH}")
    logger.info(f"Field ID: {CUSTOM_FIELD_ID} (NUMBER FIELD)")
    logger.info(f"Parallel workers: {MAX_WORKERS}")
    logger.info("")
    
    try:
        df = pd.read_csv(CSV_FILE_PATH)
        total_rows = len(df)
        
        logger.info(f"Total issues to update: {total_rows}")
        logger.info("")
        
        # Show sample values
        logger.info("Sample values from CSV:")
        for idx, val in enumerate(df['Custom_fi'].head(5)):
            converted = convert_to_number(val)
            logger.info(f"  Row {idx+1}: '{val}' -> {converted} (type: {type(converted).__name__ if converted else 'None'})")
        logger.info("")
        
        counter = ProgressCounter(total_rows)
        
        # Prepare tasks
        tasks = []
        for index, row in df.iterrows():
            issue_key = row['Issue_key']
            field_value = row['Custom_fi']
            tasks.append((issue_key, field_value))
        
        # Process in parallel
        results = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_issue = {
                executor.submit(update_jira_issue, issue_key, field_value): issue_key 
                for issue_key, field_value in tasks
            }
            
            for future in as_completed(future_to_issue):
                try:
                    result = future.result()
                    results.append(result)
                    
                    if result['status'] == 'Success':
                        counter.increment_success()
                    elif result['status'] == 'Skipped':
                        counter.increment_skipped()
                    else:
                        counter.increment_failed()
                    
                    stats = counter.get_stats()
                    if stats['processed'] % 10 == 0 or stats['processed'] == total_rows:
                        logger.info(f"Progress: {stats['processed']}/{total_rows} ✅{stats['success']} ⚠️ {stats['skipped']} ❌{stats['failed']}")
                        
                except Exception as e:
                    logger.error(f"Exception: {e}")
                    counter.increment_failed()
        
        # Save results
        output_file = f"update_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        results_df = pd.DataFrame(results)
        results_df.to_csv(output_file, index=False, encoding='utf-8')
        
        elapsed_time = datetime.now() - start_time
        stats = counter.get_stats()
        
        logger.info("")
        logger.info("="*70)
        logger.info("📈 FINAL SUMMARY")
        logger.info("="*70)
        logger.info(f"✅ Success:  {stats['success']}/{total_rows}")
        logger.info(f"⚠️  Skipped:  {stats['skipped']}/{total_rows}")
        logger.info(f"❌ Failed:   {stats['failed']}/{total_rows}")
        logger.info(f"⏱️  Time:     {elapsed_time.total_seconds():.1f} seconds")
        logger.info(f"💾 Results:  {output_file}")
        logger.info("="*70)

    except FileNotFoundError:
        logger.error(f"Input file not found: {CSV_FILE_PATH}")
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)

if __name__ == "__main__":
    main()
