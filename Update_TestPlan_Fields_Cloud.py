import csv
import json
import requests
import logging
from datetime import datetime

# -----------------------------------------
# CONFIGURATION - JIRA CLOUD
# -----------------------------------------
# Jira Cloud credentials
JIRA_CLOUD_URL = "https://greyorange-work-uat-sandbox.atlassian.net"
JIRA_EMAIL = "yashwanth.k@padahsolutions.com"
JIRA_API_TOKEN = "YOUR_TOKEN"

# Custom Field IDs for Jira Cloud
CUSTOM_FIELDS = {
    'Requirement': 'customfield_10519',
    'TP Progress': 'customfield_10520',
    'TP Status': 'customfield_10521',
    'Number of Steps': 'customfield_10522',
    'Number of Test Cases': 'customfield_10523',
}

# TP Status mapping - map your CSV values to Jira IDs
TP_STATUS_MAPPING = {
    'Open': '11901',
    'In Progress': '11902',
    'Acceptance': '11903',
    'Closed': '11904',
    'To Do': '11905',
    '8993A4': '11901',  # Open
    '0052CC': '11902',  # In Progress
    '6554C0': '11903',  # Acceptance
    '226522': '11904',  # Closed
    'C1C7D0': '11905',  # To Do
}

# Input CSV file with issue data
INPUT_CSV = "testplan_fields_input.csv"

# Output CSV file for results
OUTPUT_CSV = f"testplan_update_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

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
        
        if response.status_code == 204 or response.status_code == 200:
            logger.info(f"[SUCCESS] {issue_key}")
            return True, "Success"
        else:
            error_msg = f"{response.status_code} - {response.text}"
            logger.error(f"[FAILED] {issue_key}: {error_msg}")
            return False, error_msg
            
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
    if field_name in ['Number of Steps', 'Number of Test Cases']:
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
    if field_name == 'TP Status':
        # Map the CSV value to the correct Jira status ID
        status_id = TP_STATUS_MAPPING.get(value)
        if status_id:
            return {"id": status_id}
        else:
            # If no mapping found, try using the value directly (might be already an ID)
            logger.warning(f"No mapping found for TP Status value '{value}', using as-is")
            return {"id": value}
    
    # Requirement - assuming it's a text field
    if field_name == 'Requirement':
        return value
    
    # Default: return as string
    return value


# -----------------------------------------
# READ CSV AND UPDATE ISSUES
# -----------------------------------------
def process_csv():
    """
    Read CSV file and update each issue with custom field values.
    """
    try:
        with open(INPUT_CSV, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            
            # Validate CSV headers
            required_headers = ['Issue Key', 'Issue ID', 'Requirement', 'TP Progress', 'TP Status', 
                              'Number of Steps', 'Number of Test Cases']
            
            if not all(header in reader.fieldnames for header in required_headers):
                logger.error(f"CSV missing required headers. Expected: {required_headers}")
                logger.error(f"Found headers: {reader.fieldnames}")
                return
            
            results = []
            
            for row_num, row in enumerate(reader, start=2):
                issue_key = row.get('Issue Key', '').strip()
                
                if not issue_key:
                    continue
                
                # Build field updates dictionary
                field_updates = {}
                
                # Requirement
                requirement = parse_field_value('Requirement', row.get('Requirement'))
                if requirement is not None:
                    field_updates[CUSTOM_FIELDS['Requirement']] = requirement
                
                # TP Progress
                tp_progress = parse_field_value('TP Progress', row.get('TP Progress'))
                if tp_progress is not None:
                    field_updates[CUSTOM_FIELDS['TP Progress']] = tp_progress
                
                # TP Status
                tp_status = parse_field_value('TP Status', row.get('TP Status'))
                if tp_status is not None:
                    field_updates[CUSTOM_FIELDS['TP Status']] = tp_status
                
                # Number of Steps
                num_steps = parse_field_value('Number of Steps', row.get('Number of Steps'))
                if num_steps is not None:
                    field_updates[CUSTOM_FIELDS['Number of Steps']] = num_steps
                
                # Number of Test Cases
                num_tests = parse_field_value('Number of Test Cases', row.get('Number of Test Cases'))
                if num_tests is not None:
                    field_updates[CUSTOM_FIELDS['Number of Test Cases']] = num_tests
                
                # Skip if no fields to update
                if not field_updates:
                    results.append({
                        'Issue Key': issue_key,
                        'Status': 'Skipped',
                        'Message': 'No field values provided'
                    })
                    continue
                
                # Update the issue
                success, message = update_issue_fields(issue_key, field_updates)
                
                results.append({
                    'Issue Key': issue_key,
                    'Status': 'Success' if success else 'Failed',
                    'Message': message,
                    'Fields Updated': ', '.join(field_updates.keys())
                })
            
            # Write results to CSV
            write_results_csv(results)
            
            # Summary
            success_count = sum(1 for r in results if r['Status'] == 'Success')
            failed_count = sum(1 for r in results if r['Status'] == 'Failed')
            
            logger.info(f"\n{'='*60}")
            logger.info(f"SUMMARY: Total={len(results)}, Success={success_count}, Failed={failed_count}")
            logger.info(f"Results: {OUTPUT_CSV}")
            logger.info(f"{'='*60}")
            
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
    logger.info("JIRA CLOUD - UPDATE TEST PLAN FIELDS")
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
