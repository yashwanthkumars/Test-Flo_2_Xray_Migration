import requests
import csv
import json
import time
import re
from datetime import datetime

# --- CONFIGURATION ---
JIRA_URL = "https://work-uat.greyorange.com/jira"
TOKEN = "YOUR_TOKEN"
INPUT_CSV = "fields_mapping.csv"
OUTPUT_CSV = f"field_values_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
FETCH_BATCH_SIZE = 100

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "X-Atlassian-Token": "no-check"
}

def get_field_value_details(field_value):
    """
    Extract both ID and display value from field data.
    Supports objects, arrays, and simple values.
    For asset fields with display values like "Name (ASSET-123)", extracts the ID.
    """
    if not field_value:
        return None, None
    
    # Handle list/array fields
    if isinstance(field_value, list):
        ids = []
        values = []
        for item in field_value:
            item_id, item_value = get_field_value_details(item)
            if item_id:
                ids.append(item_id)
            if item_value:
                values.append(item_value)
        return json.dumps(ids) if ids else None, json.dumps(values) if values else None
    
    # Handle object fields (like assets, select lists, etc.)
    if isinstance(field_value, dict):
        # Asset objects
        if 'workspaceId' in field_value and 'objectId' in field_value:
            return field_value.get('objectId'), field_value.get('label', '')
        
        # Objects with key (like assets)
        if 'key' in field_value:
            return field_value.get('key'), field_value.get('label', field_value.get('key'))
        
        # Objects with id (like custom field options, users)
        if 'id' in field_value:
            return field_value.get('id'), field_value.get('value', field_value.get('name', field_value.get('displayName', '')))
        
        # Objects with value
        if 'value' in field_value:
            return field_value.get('value'), field_value.get('value')
        
        # Return entire object as JSON if no specific pattern matches
        return None, json.dumps(field_value)
    
    # Handle simple string values (may contain asset IDs in parentheses)
    value_str = str(field_value)
    
    # Try to extract ID from parentheses format: "Display Name (ID)"
    match = re.search(r'\(([^)]+)\)$', value_str)
    if match:
        extracted_id = match.group(1)
        return extracted_id, value_str
    
    # If no parentheses, return as both ID and display value
    return value_str, value_str

def export_field_values():
    """Export old field values from Jira issues to CSV."""
    
    print(f"--- STARTING FIELD VALUES EXPORT ---")
    print(f"Output file: {OUTPUT_CSV}")
    
    # Read mapping configuration
    with open(INPUT_CSV, mode='r', encoding='utf-8-sig') as f:
        mapping = list(csv.DictReader(f))[0]
    
    old_field_id = mapping['old_id'].strip()
    new_field_id = mapping['new_id'].strip()
    old_cf = f"customfield_{old_field_id}"
    
    # JQL to fetch issues with old field populated
    jql = f"cf[{old_field_id}] is not EMPTY"
    
    print(f"Searching for issues with JQL: {jql}")
    
    # Prepare output CSV
    with open(OUTPUT_CSV, mode='w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([
            "Issue Key",
            "Issue ID",
            "Old Field ID",
            "New Field ID",
            "Value ID",
            "Value Display",
            "Raw JSON"
        ])
        
        start_at = 0
        total_exported = 0
        
        while True:
            print(f"\nFetching batch starting at {start_at}...")
            
            search_url = f"{JIRA_URL}/rest/api/2/search"
            params = {
                "jql": jql,
                "fields": f"key,{old_cf}",
                "maxResults": FETCH_BATCH_SIZE,
                "startAt": start_at
            }
            
            try:
                resp = requests.get(search_url, headers=headers, params=params, timeout=30)
                resp.raise_for_status()
                response_data = resp.json()
                
                issues = response_data.get('issues', [])
                total_results = response_data.get('total', 0)
                
                print(f"Found {len(issues)} issues in this batch (Total: {total_results})")
                
                if not issues:
                    print("No more issues found.")
                    break
                
                # Process each issue
                for issue in issues:
                    issue_key = issue['key']
                    issue_id = issue['id']
                    field_value = issue['fields'].get(old_cf)
                    
                    if field_value is not None:
                        value_id, value_display = get_field_value_details(field_value)
                        raw_json = json.dumps(field_value, ensure_ascii=False)
                        
                        writer.writerow([
                            issue_key,
                            issue_id,
                            old_field_id,
                            new_field_id,
                            value_id or '',
                            value_display or '',
                            raw_json
                        ])
                        total_exported += 1
                        
                        if total_exported % 10 == 0:
                            print(".", end="", flush=True)
                
                csvfile.flush()  # Write to disk after each batch
                
                print(f"\nBatch complete. Total exported: {total_exported}")
                
                # Move to next batch
                start_at += len(issues)
                
                # Check if we've processed all available issues
                if start_at >= total_results:
                    print(f"\nAll {total_results} issues processed.")
                    break
                    
            except requests.exceptions.RequestException as e:
                print(f"\nError fetching issues: {e}")
                break
            except Exception as e:
                print(f"\nUnexpected error: {e}")
                break
    
    print(f"\n--- EXPORT COMPLETE ---")
    print(f"Total issues exported: {total_exported}")
    print(f"Output saved to: {OUTPUT_CSV}")

if __name__ == "__main__":
    export_field_values()
