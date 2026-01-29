import requests
import csv
import logging
from datetime import datetime

# ---------------- CONFIGURATION ----------------
JIRA_BASE_URL = "https://work-uat.greyorange.com"
JIRA_USERNAME = "yashwanth.k@padahsolutions.com"
JIRA_API_TOKEN = "YOUR_TOKEN"

# JQL Query
JQL_QUERY = 'issuetype = "Test Case"'

# Custom Field IDs
CUSTOM_FIELDS = {
    'Requirement': 'customfield_15424',
    'Automation Test Key': 'customfield_15429',
    'Steps Progress': 'customfield_15417',
    'TC Status': 'customfield_15420',
    'TC Template': 'customfield_15421',
    'Team': 'customfield_11600',
    'Precondition': 'customfield_15414',
}

# Output CSV file
OUTPUT_FILE = f"tesCase_custom_fields_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

# ------------------------------------------------

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.FileHandler('get_testplan_fields.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def get_issues_by_jql(jql, start_at=0, max_results=100):
    """
    Fetch issues from Jira using JQL query with pagination.
    Returns all issues matching the query.
    """
    url = f"{JIRA_BASE_URL}/jira/rest/api/2/search"
    auth = (JIRA_USERNAME, JIRA_API_TOKEN)
    
    all_issues = []
    
    while True:
        # Build field list for API request
        fields_list = list(CUSTOM_FIELDS.values()) + ['key', 'id']
        
        params = {
            "jql": jql,
            "startAt": start_at,
            "maxResults": max_results,
            "fields": ",".join(fields_list)
        }
        
        try:
            logger.info(f"Fetching issues: startAt={start_at}, maxResults={max_results}")
            response = requests.get(url, auth=auth, params=params)
            response.raise_for_status()
            
            data = response.json()
            issues = data.get("issues", [])
            total = data.get("total", 0)
            
            logger.info(f"Retrieved {len(issues)} issues out of {total} total")
            
            all_issues.extend(issues)
            
            # Check if we've retrieved all issues
            if start_at + len(issues) >= total:
                break
                
            start_at += max_results
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching issues: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise
    
    logger.info(f"Total issues retrieved: {len(all_issues)}")
    return all_issues


def extract_field_value(field_data):
    """
    Extract value from field data.
    Handles different field types (string, number, object, array).
    """
    if field_data is None:
        return ""
    
    # If it's a simple type (string, number, bool)
    if isinstance(field_data, (str, int, float, bool)):
        return str(field_data)
    
    # If it's a dict with 'value' key (common for custom fields)
    if isinstance(field_data, dict):
        if 'value' in field_data:
            return str(field_data['value'])
        if 'name' in field_data:
            return str(field_data['name'])
        if 'displayName' in field_data:
            return str(field_data['displayName'])
        # For user fields
        if 'emailAddress' in field_data:
            return str(field_data.get('displayName', field_data.get('emailAddress', '')))
        # Return string representation if no known key
        return str(field_data)
    
    # If it's a list, join values
    if isinstance(field_data, list):
        if len(field_data) == 0:
            return ""
        # Extract values from list items
        values = []
        for item in field_data:
            if isinstance(item, dict):
                if 'value' in item:
                    values.append(str(item['value']))
                elif 'name' in item:
                    values.append(str(item['name']))
                else:
                    values.append(str(item))
            else:
                values.append(str(item))
        return "; ".join(values)
    
    return str(field_data)


def export_to_csv(issues):
    """
    Export issues with custom fields to CSV.
    """
    if not issues:
        logger.warning("No issues to export")
        return
    
    csv_headers = [
        'Issue Key',
        'Issue ID',
        'Requirement',
        'Automation Test Key',
        'Steps Progress',
        'TC Status',
        'TC Template',
        'Team',
        'Precondition'
    ]
    
    try:
        with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(csv_headers)
            
            for issue in issues:
                issue_key = issue.get('key', '')
                issue_id = issue.get('id', '')
                fields = issue.get('fields', {})
                
                row = [
                    issue_key,
                    issue_id,
                    extract_field_value(fields.get(CUSTOM_FIELDS['Requirement'])),
                    extract_field_value(fields.get(CUSTOM_FIELDS['Automation Test Key'])),
                    extract_field_value(fields.get(CUSTOM_FIELDS['Steps Progress'])),
                    extract_field_value(fields.get(CUSTOM_FIELDS['TC Status'])),
                    extract_field_value(fields.get(CUSTOM_FIELDS['TC Template'])),
                    extract_field_value(fields.get(CUSTOM_FIELDS['Team'])),
                    extract_field_value(fields.get(CUSTOM_FIELDS['Precondition']))
                ]
                
                writer.writerow(row)
                logger.debug(f"Exported: {issue_key}")
        
        logger.info(f"✅ Successfully exported {len(issues)} issues to {OUTPUT_FILE}")
        
    except Exception as e:
        logger.error(f"Error writing to CSV: {e}")
        raise


def main():
    """
    Main execution function.
    """
    try:
        logger.info("=" * 60)
        logger.info("Starting Test Plan Custom Fields Export")
        logger.info(f"JQL Query: {JQL_QUERY}")
        logger.info("=" * 60)
        
        # Fetch issues
        issues = get_issues_by_jql(JQL_QUERY)
        
        if not issues:
            logger.warning("No issues found matching the JQL query")
            return
        
        # Export to CSV
        export_to_csv(issues)
        
        logger.info("=" * 60)
        logger.info("Export completed successfully")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Script execution failed: {e}")
        raise


if __name__ == "__main__":
    main()
