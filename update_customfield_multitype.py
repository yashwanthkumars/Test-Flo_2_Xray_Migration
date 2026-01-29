import pandas as pd
import requests
from requests.auth import HTTPBasicAuth
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import threading
from datetime import datetime
import re

# --- Configuration ---
JIRA_CLOUD_URL = "https://greyorange-work-uat-sandbox.atlassian.net"
JIRA_EMAIL = "yashwanth.k@padahsolutions.com"
JIRA_API_TOKEN = "YOUR_TOKEN"
CSV_FILE_PATH = "Pass_count_field_values_export_20260120_131716.csv"

# IMPORTANT: Replace with your actual Jira Custom Field ID
CUSTOM_FIELD_ID = "customfield_10356"

# Field type - AUTO will detect from CSV, or specify: "number", "text", "adf", "select", "multiselect", "date"
FIELD_TYPE = "AUTO"  # Options: AUTO, number, text, adf, select, multiselect, date

# Performance settings
MAX_WORKERS = 10  # Number of parallel threads

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

# --- Field Type Converters ---

def convert_to_adf(text_value):
    """Convert plain text to Atlassian Document Format (for paragraph/rich text fields)"""
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

def convert_to_number(value):
    """Convert value to number (for number fields)"""
    if pd.isna(value) or value == "" or value == "None":
        return None
    
    try:
        # Try to convert to float first to handle decimals
        num = float(str(value))
        # Return as int if it's a whole number, otherwise as float
        return int(num) if num.is_integer() else num
    except (ValueError, AttributeError):
        logger.warning(f"Could not convert '{value}' to number")
        return None

def convert_to_text(value):
    """Simple text value (for text fields)"""
    if pd.isna(value) or value == "":
        return None
    return str(value)

def convert_to_select(value):
    """Convert to select list option (for single select fields)"""
    if pd.isna(value) or value == "":
        return None
    
    # If it's already a dict with 'value' key, use it as is
    if isinstance(value, dict) and 'value' in value:
        return value
    
    # Otherwise, treat as a string option name
    return {"value": str(value).strip()}

def convert_to_multiselect(value):
    """Convert to multi-select options (for multi-select fields)"""
    if pd.isna(value) or value == "":
        return None
    
    # If it's a list, convert each to dict with 'value'
    if isinstance(value, list):
        return [{"value": str(v).strip()} for v in value if v]
    
    # If it's a string, split by comma
    if isinstance(value, str):
        values = [v.strip() for v in str(value).split(',') if v.strip()]
        if values:
            return [{"value": v} for v in values]
    
    return None

def convert_to_date(value):
    """Convert to date format YYYY-MM-DD (for date fields)"""
    if pd.isna(value) or value == "":
        return None
    
    try:
        # Try pandas to_datetime for flexible parsing
        parsed_date = pd.to_datetime(value)
        return parsed_date.strftime('%Y-%m-%d')
    except:
        logger.warning(f"Could not parse date: '{value}'")
        return None

def detect_field_type(sample_values):
    """Auto-detect field type from sample values"""
    # Remove None and empty values
    valid_values = [v for v in sample_values if pd.notna(v) and v != "" and v != "None"]
    
    if not valid_values:
        return "text"  # Default to text if no valid values
    
    # Check if all are numbers
    all_numbers = all(is_number(v) for v in valid_values)
    if all_numbers:
        return "number"
    
    # Check if all are dates
    all_dates = all(is_date(v) for v in valid_values)
    if all_dates:
        return "date"
    
    # Default to text (ADF will be used for paragraph fields)
    return "text"

def is_number(value):
    """Check if value is a number"""
    try:
        float(str(value))
        return True
    except (ValueError, TypeError):
        return False

def is_date(value):
    """Check if value is a date"""
    try:
        pd.to_datetime(value)
        return True
    except:
        return False

def get_converter(field_type):
    """Get the appropriate converter function for field type"""
    converters = {
        "number": convert_to_number,
        "text": convert_to_text,
        "adf": convert_to_adf,
        "select": convert_to_select,
        "multiselect": convert_to_multiselect,
        "date": convert_to_date,
    }
    return converters.get(field_type, convert_to_text)

# --- Update Function ---

def update_jira_issue(issue_key, new_value, converter_func):
    """Update a single Jira issue's custom field"""
    url = f"{JIRA_CLOUD_URL}/rest/api/3/issue/{issue_key}"
    
    # Convert value using appropriate converter
    field_value = converter_func(new_value)
    
    if field_value is None:
        logger.warning(f"⚠️  {issue_key}: Skipping - empty or invalid value")
        return {'issue_key': issue_key, 'status': 'Skipped', 'message': 'Empty or invalid value'}
    
    # Construct the payload
    payload = json.dumps({
        "fields": {
            CUSTOM_FIELD_ID: field_value
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
            return {'issue_key': issue_key, 'status': 'Failed', 'message': f"{response.status_code}"}
    
    except Exception as e:
        logger.error(f"❌ {issue_key}: Exception - {str(e)}")
        return {'issue_key': issue_key, 'status': 'Failed', 'message': f'Exception: {str(e)}'}

# --- Main Execution ---
def main():
    start_time = datetime.now()
    logger.info("="*60)
    logger.info("🚀 Starting Custom Field Update (Multi-Type Support)")
    logger.info("="*60)
    logger.info(f"Input file: {CSV_FILE_PATH}")
    logger.info(f"Field ID: {CUSTOM_FIELD_ID}")
    logger.info(f"Parallel workers: {MAX_WORKERS}")
    logger.info("")
    
    try:
        df = pd.read_csv(CSV_FILE_PATH)
        total_rows = len(df)
        
        logger.info(f"Total issues to update: {total_rows}")
        
        # Determine field type
        detected_field_type = FIELD_TYPE
        if FIELD_TYPE == "AUTO":
            # Get sample values - try different column names
            sample_col = None
            for col in ['Custom_fi', 'Field_Value', 'field_value']:
                if col in df.columns:
                    sample_col = col
                    break
            if sample_col is None:
                sample_col = df.columns[1]  # Use second column as fallback
            
            sample_values = df[sample_col].head(20).tolist()
            detected_field_type = detect_field_type(sample_values)
            logger.info(f"Auto-detected field type: {detected_field_type} (from column: {sample_col})")
        else:
            logger.info(f"Using specified field type: {detected_field_type}")
        
        logger.info(f"Parallel workers: {MAX_WORKERS}")
        logger.info("")
        
        # Get converter function
        converter = get_converter(detected_field_type)
        
        # Initialize counter
        counter = ProgressCounter(total_rows)
        
        # Prepare tasks
        tasks = []
        for index, row in df.iterrows():
            issue_key = row.get('Issue_key', row.get('issue_key', None))
            # Try different column names for the value (Custom_fi, Field_Value, field_value, or second column)
            field_value = row.get('Custom_fi', row.get('Field_Value', row.get('field_value', row.iloc[1])))
            
            if not issue_key:
                logger.warning(f"Skipping row {index + 1}: No issue key found")
                continue
            
            tasks.append((issue_key, field_value))
        
        # Process updates in parallel
        results = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Submit all tasks
            future_to_issue = {
                executor.submit(update_jira_issue, issue_key, field_value, converter): issue_key 
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
        logger.info(f"Field Type Used: {detected_field_type}")
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
