import pandas as pd
import requests
import json
from datetime import datetime
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# --- Configuration ---
JIRA_URL = "https://work-uat.greyorange.com/jira"
TOKEN = "YOUR_TOKEN"

# Input/Output files
INPUT_FILE = "issue_keysfield.csv"  # CSV file with issue keys (column: Issue_key or Key)
OUTPUT_FILE = f"Moredetail_field_values_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

# Field to export
CUSTOM_FIELD_ID = "customfield_15414"

# Performance settings
MAX_WORKERS = 10  # Number of parallel threads for faster processing

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(threadName)-10s] - %(message)s',
    handlers=[
        logging.FileHandler('export_field_values.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Thread-safe counter for progress tracking
class ProgressCounter:
    def __init__(self, total):
        self.lock = threading.Lock()
        self.processed = 0
        self.total = total
    
    def increment(self):
        with self.lock:
            self.processed += 1
            return self.processed

# --- Setup Authentication ---
headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "X-Atlassian-Token": "no-check"
}

def extract_text_from_adf(adf_content):
    """Extract plain text from Atlassian Document Format"""
    if not adf_content:
        return ""
    
    if isinstance(adf_content, str):
        return adf_content
    
    if isinstance(adf_content, dict):
        # Handle ADF format
        if adf_content.get('type') == 'doc':
            text_parts = []
            for content_item in adf_content.get('content', []):
                if content_item.get('type') == 'paragraph':
                    for text_item in content_item.get('content', []):
                        if text_item.get('type') == 'text':
                            text_parts.append(text_item.get('text', ''))
            return ' '.join(text_parts)
        # Handle other dict types (might be select/option fields)
        if 'value' in adf_content:
            return adf_content['value']
        if 'name' in adf_content:
            return adf_content['name']
    
    # If it's a list (multi-select or similar)
    if isinstance(adf_content, list):
        values = []
        for item in adf_content:
            if isinstance(item, dict):
                if 'value' in item:
                    values.append(item['value'])
                elif 'name' in item:
                    values.append(item['name'])
            else:
                values.append(str(item))
        return ', '.join(values)
    
    return str(adf_content)

def get_field_value(issue_key):
    """Fetch the custom field value for a given issue key"""
    url = f"{JIRA_URL}/rest/api/2/issue/{issue_key}"
    
    params = {
        "fields": CUSTOM_FIELD_ID
    }
    
    try:
        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            field_value = data.get('fields', {}).get(CUSTOM_FIELD_ID)
            
            # Extract text from ADF or other formats
            field_text = extract_text_from_adf(field_value)
            
            logger.info(f"✅ {issue_key}: Retrieved field value")
            return {
                'Issue_key': issue_key,
                'Field_Value': field_text,
                'Status': 'Success'
            }
        elif response.status_code == 404:
            logger.warning(f"❌ {issue_key}: Issue not found")
            return {
                'Issue_key': issue_key,
                'Field_Value': '',
                'Status': 'Issue Not Found'
            }
        else:
            logger.error(f"❌ {issue_key}: Error {response.status_code} - {response.text}")
            return {
                'Issue_key': issue_key,
                'Field_Value': '',
                'Status': f'Error: {response.status_code}'
            }
            
    except Exception as e:
        logger.error(f"❌ {issue_key}: Exception - {str(e)}")
        return {
            'Issue_key': issue_key,
            'Field_Value': '',
            'Status': f'Exception: {str(e)}'
        }

# --- Main Execution ---
def main():
    logger.info("=" * 60)
    logger.info("Starting Field Value Export")
    logger.info("=" * 60)
    logger.info(f"Input file: {INPUT_FILE}")
    logger.info(f"Output file: {OUTPUT_FILE}")
    logger.info(f"Field ID: {CUSTOM_FIELD_ID}")
    logger.info("")
    
    try:
        # Read input CSV with issue keys
        df = pd.read_csv(INPUT_FILE)
        
        # Try to find the issue key column (support multiple column names)
        key_column = None
        for col in ['Issue_key', 'Key', 'Issue Key', 'issue_key', 'key']:
            if col in df.columns:
                key_column = col
                break
        
        if key_column is None:
            logger.error(f"Could not find issue key column. Available columns: {list(df.columns)}")
            logger.error("Please ensure your CSV has a column named 'Issue_key', 'Key', or similar")
            return
        
        logger.info(f"Found issue key column: {key_column}")
        logger.info(f"Total issues to process: {len(df)}")
        logger.info(f"Parallel workers: {MAX_WORKERS}")
        logger.info("")
        
        # Prepare issue keys list
        issue_keys = []
        for index, row in df.iterrows():
            issue_key = str(row[key_column]).strip()
            if not issue_key or issue_key.lower() == 'nan':
                logger.warning(f"Skipping row {index + 1}: Empty issue key")
                continue
            issue_keys.append(issue_key)
        
        # Initialize progress counter
        counter = ProgressCounter(len(issue_keys))
        
        # Process issues in parallel
        results = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Submit all tasks
            future_to_key = {executor.submit(get_field_value, key): key for key in issue_keys}
            
            # Collect results as they complete
            for future in as_completed(future_to_key):
                try:
                    result = future.result()
                    results.append(result)
                    
                    # Log progress
                    progress = counter.increment()
                    if progress % 10 == 0 or progress == len(issue_keys):
                        logger.info(f"Progress: {progress}/{len(issue_keys)} issues processed")
                        
                except Exception as e:
                    issue_key = future_to_key[future]
                    logger.error(f"Exception processing {issue_key}: {e}")
                    results.append({
                        'Issue_key': issue_key,
                        'Field_Value': '',
                        'Status': f'Exception: {str(e)}'
                    })
        
        # Create output DataFrame
        output_df = pd.DataFrame(results)
        
        # Save to CSV
        output_df.to_csv(OUTPUT_FILE, index=False, encoding='utf-8')
        
        # Summary
        logger.info("")
        logger.info("=" * 60)
        logger.info("📈 SUMMARY")
        logger.info("=" * 60)
        
        success_count = len(output_df[output_df['Status'] == 'Success'])
        failed_count = len(output_df[output_df['Status'] != 'Success'])
        
        logger.info(f"✅ Success: {success_count}")
        logger.info(f"❌ Failed:  {failed_count}")
        logger.info(f"📄 Total:   {len(output_df)}")
        logger.info(f"💾 Output:  {OUTPUT_FILE}")
        logger.info("=" * 60)
        
    except FileNotFoundError:
        logger.error(f"Input file not found: {INPUT_FILE}")
        logger.error("Please create a CSV file with issue keys")
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)

if __name__ == "__main__":
    main()
