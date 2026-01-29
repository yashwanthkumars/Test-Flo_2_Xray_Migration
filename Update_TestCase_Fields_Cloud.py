import csv
import json
import requests
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from threading import Lock

# -----------------------------------------
# CONFIGURATION - JIRA CLOUD
# -----------------------------------------
# Jira Cloud credentials
JIRA_CLOUD_URL = "https://greyorange-work-uat-sandbox.atlassian.net"
JIRA_EMAIL = "yashwanth.k@padahsolutions.com"
JIRA_API_TOKEN = "YOUR_TOKEN"

# Custom Field IDs for Jira Cloud
CUSTOM_FIELDS = {
    'Requirement': 'customfield_10557',
    'Automation Test Key': 'customfield_10548',
    'Steps Progress': 'customfield_10563',
    'TC Status': 'customfield_10564',
    'TC Template': 'customfield_10565',
    'Team': 'customfield_10001',
    # 'Precondition': 'customfield_10463'
}

# TC Status mapping - map your CSV values to Jira IDs
TC_STATUS_MAPPING = {
    'Open': '11978',
    'In Progress': '11979',
    'Fail': '11980',
    'Pass': '11981',
    'Retest': '11982',
    'Blocked': '11983',
    # Color code mappings (case-insensitive for color codes)
    '8993a4': '11978',  # Open
    '8993A4': '11978',  # Open (uppercase)
    '226522': '11981',  # Pass (green color)
    '226522'.lower(): '11981',  # Pass (lowercase)
    'b70129': '11980',  # Fail (red color)
    'B70129': '11980',  # Fail (uppercase)
    'f5810b': '11982',  # Retest (orange color)
    'F5810B': '11982',  # Retest (uppercase)
    '1f0ae1': '11983',  # Blocked (blue color)
    '1F0AE1': '11983',  # Blocked (uppercase)
}

# Input CSV file with issue data
INPUT_CSV = "tesCase_custom_fields_20260120_174024.csv"

# Output CSV file for results
OUTPUT_CSV = f"testcase_update_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

# Thread Pool Configuration
MAX_WORKERS = 5  # Number of concurrent threads
RATE_LIMIT_BUFFER = 0.5  # Delay between requests (seconds) to avoid rate limit
RATE_LIMIT_THRESHOLD = 429  # HTTP status code for rate limit

# -----------------------------------------
# LOGGING CONFIGURATION
# -----------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[
        logging.FileHandler('update_testplan_fields.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Thread-safe locks and counters
result_lock = Lock()
rate_limit_lock = Lock()
progress_counter = {'completed': 0, 'total': 0, 'rate_limit_hits': 0}


# -----------------------------------------
# UPDATE ISSUE CUSTOM FIELDS
# -----------------------------------------
def update_issue_fields(issue_key, field_updates):
    """
    Update custom fields for a given issue in Jira Cloud.
    
    Args:
        issue_key: The Jira issue key (e.g., GM-25573)
        field_updates: Dictionary of field IDs and their values
    
    Returns:
        tuple: (success: bool, message: str)
    """
    url = f"{JIRA_CLOUD_URL}/rest/api/3/issue/{issue_key}"
    auth = (JIRA_EMAIL, JIRA_API_TOKEN)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    # Build the update payload
    payload = {
        "fields": field_updates
    }
    
    try:
        response = requests.put(url, json=payload, auth=auth, headers=headers)
        
        # Check for rate limiting
        if response.status_code == RATE_LIMIT_THRESHOLD:
            with rate_limit_lock:
                progress_counter['rate_limit_hits'] += 1
            logger.warning(f"[RATE LIMIT] {issue_key} - Backing off...")
            time.sleep(2)  # Wait before retrying
            return update_issue_fields(issue_key, field_updates)  # Retry
        
        if response.status_code == 204 or response.status_code == 200:
            with result_lock:
                progress_counter['completed'] += 1
            logger.info(f"[SUCCESS] {issue_key} - ({progress_counter['completed']}/{progress_counter['total']})")
            return True, "Success"
        else:
            error_msg = f"{response.status_code} - {response.text}"
            logger.error(f"[FAILED] {issue_key}: {error_msg}")
            return False, error_msg
        
        # Rate limit delay to avoid hitting Jira API limits
        time.sleep(RATE_LIMIT_BUFFER)
            
    except requests.exceptions.RequestException as e:
        error_msg = f"Request exception: {str(e)}"
        logger.error(f"[ERROR] {issue_key}: {error_msg}")
        return False, error_msg


# -----------------------------------------
# PARSE FIELD VALUE
# -----------------------------------------
def parse_field_value(field_name, value):
    """
    Parse and format field value based on field type.
    
    Args:
        field_name: Name of the field
        value: Raw value from CSV
    
    Returns:
        Formatted value for Jira API
    """
    # Handle empty values
    if value is None or str(value).strip() == '':
        return None
    
    value = str(value).strip()
    
    # Number fields - convert to number
    if field_name in ['Number of Steps', 'Number of Test Cases', 'Steps Progress']:
        try:
            return int(value)
        except ValueError:
            return 0
    
    # TP Progress - assuming it's a number (percentage)
    if field_name == 'TP Progress':
        try:
            value = value.replace('%', '').strip()
            return int(value)
        except ValueError:
            return 0
    
    # TP Status - it's a select field, use id instead of value
    if field_name == 'TC Status':
        # Map the CSV value to the correct Jira status ID
        status_id = TC_STATUS_MAPPING.get(value)
        if status_id:
            return {"id": status_id}
        else:
            # If no mapping found, try using the value directly (might be already an ID)
            logger.warning(f"No mapping found for TC Status value '{value}', using as-is")
            return {"id": value}
    
    # Automation Test Key - uses Atlassian Document Format
    if field_name == 'Automation Test Key':
        return {
            "version": 1,
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": value
                        }
                    ]
                }
            ]
        }
    
    # Requirement - assuming it's a text field
    if field_name == 'Requirement':
        return value
    
    # Default: return as string
    return value


# -----------------------------------------
# READ CSV AND UPDATE ISSUES WITH THREAD POOL
# -----------------------------------------
def process_csv():
    """
    Read CSV file and update each issue with custom field values using thread pool.
    """
    try:
        with open(INPUT_CSV, 'r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            
            # Normalize header names (remove BOM and whitespace)
            normalized_fieldnames = [name.strip() for name in reader.fieldnames]
            reader.fieldnames = normalized_fieldnames
            
            # Validate CSV headers
            required_headers = ['Issue Key', 'Issue ID', 'Requirement', 'Automation Test Key', 'Steps Progress', 
                              'TC Status', 'TC Template', 'Team']
            
            if not all(header in reader.fieldnames for header in required_headers):
                logger.error(f"CSV missing required headers. Expected: {required_headers}")
                logger.error(f"Found headers: {reader.fieldnames}")
                return
            
            # Collect all rows to process
            rows_to_process = []
            for row_num, row in enumerate(reader, start=2):
                issue_key = row.get('Issue Key', '').strip()
                if issue_key:
                    rows_to_process.append(row)
            
            # Initialize progress counter
            progress_counter['total'] = len(rows_to_process)
            progress_counter['completed'] = 0
            
            logger.info(f"Total issues to process: {progress_counter['total']}")
            logger.info(f"Starting thread pool with {MAX_WORKERS} workers...")
            
            results = []
            
            # Use ThreadPoolExecutor for parallel processing
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                # Submit all tasks
                future_to_row = {}
                for row in rows_to_process:
                    issue_key = row.get('Issue Key', '').strip()
                    
                    # Build field updates dictionary
                    field_updates = {}
                    
                    # Requirement
                    requirement = parse_field_value('Requirement', row.get('Requirement'))
                    if requirement is not None:
                        field_updates[CUSTOM_FIELDS['Requirement']] = requirement
                    
                    # Automation Test Key
                    auto_test_key = parse_field_value('Automation Test Key', row.get('Automation Test Key'))
                    if auto_test_key is not None:
                        field_updates[CUSTOM_FIELDS['Automation Test Key']] = auto_test_key
                    
                    # Steps Progress
                    steps_progress = parse_field_value('Steps Progress', row.get('Steps Progress'))
                    if steps_progress is not None:
                        field_updates[CUSTOM_FIELDS['Steps Progress']] = steps_progress
                    
                    # TC Status
                    tc_status = parse_field_value('TC Status', row.get('TC Status'))
                    if tc_status is not None:
                        field_updates[CUSTOM_FIELDS['TC Status']] = tc_status
                    
                    # TC Template
                    tc_template = parse_field_value('TC Template', row.get('TC Template'))
                    if tc_template is not None:
                        field_updates[CUSTOM_FIELDS['TC Template']] = tc_template
                    
                    # Team
                    team = parse_field_value('Team', row.get('Team'))
                    if team is not None:
                        field_updates[CUSTOM_FIELDS['Team']] = team
                    
                    # Skip if no fields to update
                    if not field_updates:
                        results.append({
                            'Issue Key': issue_key,
                            'Status': 'Skipped',
                            'Message': 'No field values provided'
                        })
                        with result_lock:
                            progress_counter['completed'] += 1
                        continue
                    
                    # Submit task to executor
                    future = executor.submit(update_issue_fields, issue_key, field_updates)
                    future_to_row[future] = (issue_key, field_updates)
                
                # Process completed futures as they finish
                for future in as_completed(future_to_row):
                    issue_key, field_updates = future_to_row[future]
                    try:
                        success, message = future.result()
                        results.append({
                            'Issue Key': issue_key,
                            'Status': 'Success' if success else 'Failed',
                            'Message': message,
                            'Fields Updated': ', '.join(field_updates.keys())
                        })
                    except Exception as e:
                        logger.error(f"[ERROR] {issue_key}: {str(e)}")
                        results.append({
                            'Issue Key': issue_key,
                            'Status': 'Failed',
                            'Message': str(e),
                            'Fields Updated': ', '.join(field_updates.keys())
                        })
            
            # Write results to CSV
            write_results_csv(results)
            
            # Summary
            success_count = sum(1 for r in results if r['Status'] == 'Success')
            failed_count = sum(1 for r in results if r['Status'] == 'Failed')
            skipped_count = sum(1 for r in results if r['Status'] == 'Skipped')
            
            logger.info(f"\n{'='*70}")
            logger.info(f"FINAL SUMMARY")
            logger.info(f"{'='*70}")
            logger.info(f"Total Issues:        {len(results)}")
            logger.info(f"Completed:           {progress_counter['completed']}/{progress_counter['total']}")
            logger.info(f"Success:             {success_count}")
            logger.info(f"Failed:              {failed_count}")
            logger.info(f"Skipped:             {skipped_count}")
            logger.info(f"Rate Limit Hits:     {progress_counter['rate_limit_hits']}")
            logger.info(f"Results File:        {OUTPUT_CSV}")
            logger.info(f"{'='*70}\n")
            
    except FileNotFoundError:
        logger.error(f"CSV file not found: {INPUT_CSV}")
        logger.error("Please ensure the CSV file exists in the same directory")
    except Exception as e:
        logger.error(f"Error processing CSV: {str(e)}", exc_info=True)


# -----------------------------------------
# WRITE RESULTS TO CSV
# -----------------------------------------
def write_results_csv(results):
    """
    Write update results to a CSV file.
    """
    try:
        with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['Issue Key', 'Status', 'Message', 'Fields Updated']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            writer.writerows(results)
            
        logger.info(f"Results written to {OUTPUT_CSV}")
    except Exception as e:
        logger.error(f"Error writing results CSV: {str(e)}")


# -----------------------------------------
# MAIN FUNCTION
# -----------------------------------------
def main():
    """
    Main execution function.
    """
    logger.info("="*60)
    logger.info("JIRA CLOUD - UPDATE TEST CASE FIELDS")
    logger.info("="*60)
    
    # Validate configuration
    if JIRA_CLOUD_URL == "https://your-domain.atlassian.net":
        logger.error("ERROR: Please update JIRA_CLOUD_URL")
        return
    
    if JIRA_EMAIL == "your-email@example.com":
        logger.error("ERROR: Please update JIRA_EMAIL")
        return
    
    if JIRA_API_TOKEN == "your-api-token":
        logger.error("ERROR: Please update JIRA_API_TOKEN")
        return
    
    # Process the CSV file
    process_csv()


if __name__ == "__main__":
    main()
