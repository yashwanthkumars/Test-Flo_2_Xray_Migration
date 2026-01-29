import requests
import csv
import json
import time

# --- CONFIGURATION ---
JIRA_URL = "https://work-uat.greyorange.com/jira"
TOKEN = "YOUR_TOKEN" 
INPUT_CSV = "fields_mapping.csv"   #Input file should  with this file name 
OUTPUT_LOG_CSV = "migration_logupdated_fieldv1.csv"

# Headers for Bearer Auth
headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "X-Atlassian-Token": "no-check"
}

def clean_id(field_id):
    """Ensures we only have the numeric part of the ID."""
    return str(field_id).replace("customfield_", "").strip()

def convert_value_to_object(value, field_key):
    """
    Convert string/list values to object format expected by JIRA fields.
    
    For object-type fields like user pickers, component fields, etc.,
    JIRA expects: {"id": "..."} or just the id string
    """
    if value is None:
        return None
    
    # If already a list, convert each item
    if isinstance(value, list):
        return [convert_value_to_object(item, field_key) for item in value]
    
    # If it's a dict, return as is
    if isinstance(value, dict):
        return value
    
    # If it's a string, try to convert to object format
    if isinstance(value, str):
        # Try to extract ID if it's in format "Name (ID-123)" or just an ID
        # For now, return as-is and let JIRA handle it
        return value
    
    return value

def get_field_info(field_key):
    """Fetch field configuration to understand its type."""
    try:
        url = f"{JIRA_URL}/rest/api/2/field/{field_key}"
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Warning: Could not fetch field info for {field_key}: {e}")
    return None

def get_editmeta_for_field(issue_key, field_key):
    """Fetch editmeta to see what format a field expects."""
    try:
        url = f"{JIRA_URL}/rest/api/2/issue/{issue_key}/editmeta"
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            fields = data.get('fields', {})
            field_meta = fields.get(field_key)
            return field_meta
    except Exception as e:
        print(f"  Warning: Could not fetch editmeta for {field_key}: {e}")
    return None

def get_insight_object_id_by_key(object_key):
    """
    Get Insight object ID and full details using the object key (e.g., BS-132475).
    Returns tuple: (object_key, object_id, workspace_id)
    """
    try:
        # Method 1: Direct object lookup by key
        url = f"{JIRA_URL}/rest/insight/1.0/object/{object_key}"
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            obj_data = response.json()
            obj_id = obj_data.get('id')
            workspace_id = obj_data.get('objectType', {}).get('workspaceId')
            if obj_id:
                print(f"  ✓ Found Insight object ID: {obj_id} (workspace: {workspace_id}) for key: {object_key}")
                return (object_key, str(obj_id), str(workspace_id) if workspace_id else None)
        
        # Method 2: Search using IQL (Insight Query Language)
        search_url = f"{JIRA_URL}/rest/insight/1.0/iql/objects"
        params = {
            "iql": f'Key = "{object_key}"',
            "resultPerPage": 1,
            "page": 1
        }
        response = requests.get(search_url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            objects = data.get('objectEntries', [])
            if objects and len(objects) > 0:
                obj = objects[0]
                obj_id = obj.get('id')
                workspace_id = obj.get('objectType', {}).get('workspaceId')
                print(f"  ✓ Found Insight object ID via IQL: {obj_id} (workspace: {workspace_id}) for key: {object_key}")
                return (object_key, str(obj_id), str(workspace_id) if workspace_id else None)
        
        # Method 3: Try the navlist AQL endpoint
        aql_url = f"{JIRA_URL}/rest/insight/1.0/object/navlist/aql"
        aql_params = {
            "objectKey": object_key,
            "resultsPerPage": 1
        }
        response = requests.get(aql_url, headers=headers, params=aql_params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            entries = data.get('objectEntries', [])
            if entries and len(entries) > 0:
                obj = entries[0]
                obj_id = obj.get('id')
                workspace_id = obj.get('objectType', {}).get('workspaceId')
                print(f"  ✓ Found Insight object ID via AQL: {obj_id} (workspace: {workspace_id}) for key: {object_key}")
                return (object_key, str(obj_id), str(workspace_id) if workspace_id else None)
                
    except Exception as e:
        print(f"  ⚠ Error searching for Insight object {object_key}: {e}")
    
    return (None, None, None)

def get_asset_object_info(display_value, field_key):
    """
    Extract object key from display value and fetch the object details.
    Returns tuple: (object_key, object_id)
    Display format: "Name (BS-12345)" -> Extract "BS-12345" -> Get numeric ID
    """
    if not display_value:
        return (None, None)
    
    # Extract the object key from format "Name (KEY-123)"
    object_key = None
    if isinstance(display_value, str) and '(' in display_value and ')' in display_value:
        # Extract "BS-132475" from "Sam's Club Atlanta (BS-132475)"
        object_key = display_value.split('(')[-1].strip(')')
    
    if not object_key:
        print(f"  ⚠ Could not extract object key from: {display_value}")
        return (None, None)
    
    # Get the object details
    obj_key, obj_id, workspace_id = get_insight_object_id_by_key(object_key)
    
    if not obj_id:
        print(f"  ⚠ Could not find object ID for key: {object_key} (from: {display_value})")
        return (None, None)
    
    return (obj_key, obj_id)

def convert_to_asset_field(value, field_key):
    """
    Convert value to asset field format.
    Insight fields expect objects. Try different object formats:
    1. {"key": "BS-132475"}
    2. {"objectKey": "BS-132475"} 
    3. {"id": 132475, "key": "BS-132475"}
    """
    if value is None:
        return None
    
    # If it's already a dict with id, extract and use only the id
    if isinstance(value, dict):
        if 'id' in value:
            # Try to convert to int if it's a string
            obj_id = value['id']
            try:
                return {"id": int(obj_id)}
            except (ValueError, TypeError):
                return {"id": obj_id}
        # If dict has other structure, try to preserve it
        return value
    
    # If it's a list, convert each item to object format
    if isinstance(value, list):
        converted = []
        for item in value:
            if isinstance(item, dict) and 'id' in item:
                # Extract the ID from the object and convert to int
                obj_id = item['id']
                try:
                    converted.append({"id": int(obj_id)})
                except (ValueError, TypeError):
                    converted.append({"id": obj_id})
            elif isinstance(item, dict):
                # Dict but no id field - use as is
                converted.append(item)
            elif isinstance(item, str):
                # String value - get the object KEY and ID, create object
                object_key, object_id = get_asset_object_info(item, field_key)
                if object_key and object_id:
                    # Try with both key and id
                    converted.append({"key": object_key, "id": int(object_id)})
                elif object_key:
                    # Just use the key
                    converted.append({"key": object_key})
                else:
                    print(f"  ⚠ Skipping item (no key found): {item}")
        return converted if converted else None
    
    # If it's a string, use the object KEY in an object
    if isinstance(value, str):
        object_key, object_id = get_asset_object_info(value, field_key)
        if object_key and object_id:
            # Return object with both key and id
            return {"key": object_key, "id": int(object_id)}
        elif object_key:
            # Just return the key in an object
            return {"key": object_key}
        else:
            print(f"  ⚠ Cannot convert to asset field (no key found): {value}")
            return None
    
    return value

def migrate_fields():
    log_data = []
    total_processed = 0
    total_success = 0
    total_failed = 0

    try:
        with open(INPUT_CSV, mode='r', encoding='utf-8-sig') as file:
            reader = csv.DictReader(file)
            rows = list(reader)
            
            if not rows:
                print("WARNING: No data rows found in the CSV file!")
                return
                
            print(f"Found {len(rows)} field mapping(s) to process\n")
            
            for row in rows:
                # Skip empty rows
                if not row or not row.get('old_id') or not row.get('new_id'):
                    print(f"Skipping empty or invalid row: {row}")
                    continue
                    
                # Clean IDs in case 'customfield_' was included in the CSV
                raw_old = clean_id(row['old_id'])
                raw_new = clean_id(row['new_id'])
                
                old_field_key = f"customfield_{raw_old}"
                new_field_key = f"customfield_{raw_new}"
                
                print(f"\n{'='*80}")
                print(f"Starting Migration: {old_field_key} -> {new_field_key}")
                print(f"{'='*80}")
                
                # Get field info for better understanding
                print(f"Fetching field information for {new_field_key}...")
                new_field_info = get_field_info(new_field_key)
                if new_field_info:
                    print(f"  Type: {new_field_info.get('type', 'unknown')}")
                    schema = new_field_info.get('schema', {})
                    print(f"  Schema Type: {schema.get('type', 'unknown')}")
                    if schema.get('custom'):
                        print(f"  Custom Type: {schema.get('custom', 'unknown')}")
                    
                    # Get editmeta to see what format the field expects
                    print(f"\n🔍 Fetching edit metadata for sample issue to understand expected format...")
                    # We'll get this from the first issue we find
                else:
                    print(f"  ⚠ Could not fetch field info for {new_field_key}")
                
                start_at = 0
                max_results = 50 # Smaller batches are safer for API stability
                field_issue_count = 0
                sample_shown = False

                while True:
                    # 1. Search for issues - use expand to get renderedFields which may contain object data
                    jql = f"cf[{raw_old}] is not EMPTY"
                    search_url = f"{JIRA_URL}/rest/api/2/search"
                    params = {
                        "jql": jql,
                        "fields": f"key,{old_field_key}",
                        "startAt": start_at,
                        "maxResults": max_results,
                        "expand": "names,schema"
                    }

                    print(f"\nSearching for issues with JQL: {jql} (batch: {start_at}-{start_at+max_results})")
                    response = requests.get(search_url, headers=headers, params=params)
                    
                    if response.status_code != 200:
                        print(f"❌ Search failed: {response.status_code} - {response.text}")
                        log_data.append(["N/A", old_field_key, new_field_key, "Search Failed", f"{response.status_code}: {response.text}"])
                        break

                    data = response.json()
                    issues = data.get('issues', [])
                    total_issues = data.get('total', 0)
                    
                    print(f"Found {len(issues)} issues in this batch (Total matching JQL: {total_issues})")
                    
                    if not issues:
                        if field_issue_count == 0:
                            print(f"⚠️  No issues found with data in {old_field_key}")
                        break

                    # Show sample value from first issue to understand data structure
                    if not sample_shown and issues:
                        sample_issue_key = issues[0]['key']
                        sample_value = issues[0]['fields'].get(old_field_key)
                        sample_type = type(sample_value).__name__
                        sample_json = json.dumps(sample_value, indent=2) if isinstance(sample_value, (dict, list)) else str(sample_value)
                        if len(sample_json) > 500:
                            sample_json = sample_json[:500] + "\n... (truncated)"
                        print(f"\n{'='*80}")
                        print(f"📋 SAMPLE DATA STRUCTURE from {sample_issue_key}")
                        print(f"{'='*80}")
                        print(f"Old Field Type: {sample_type}")
                        print(f"Old Field Value:\n{sample_json}")
                        
                        # Get the FULL issue details to see all field representations
                        print(f"\n🔍 Fetching FULL issue details to see complete field structure...")
                        full_issue_url = f"{JIRA_URL}/rest/api/2/issue/{sample_issue_key}"
                        full_params = {"expand": "renderedFields,names,schema,editmeta"}
                        full_response = requests.get(full_issue_url, headers=headers, params=full_params, timeout=10)
                        if full_response.status_code == 200:
                            full_data = full_response.json()
                            
                            # Check if there's rendered or raw object data
                            rendered_value = full_data.get('renderedFields', {}).get(old_field_key)
                            if rendered_value:
                                print(f"\nRendered Field Value:\n{json.dumps(rendered_value, indent=2)}")
                            
                            # Check schema information
                            if 'names' in full_data:
                                print(f"\nField Name: {full_data['names'].get(old_field_key, 'N/A')}")
                        
                        # Get editmeta for NEW field to see what it expects
                        print(f"\n🎯 Fetching editmeta for NEW field {new_field_key}...")
                        new_field_meta = get_editmeta_for_field(sample_issue_key, new_field_key)
                        if new_field_meta:
                            print(f"New Field Schema:")
                            print(json.dumps(new_field_meta.get('schema', {}), indent=2))
                            if 'allowedValues' in new_field_meta:
                                allowed = new_field_meta['allowedValues']
                                print(f"\nAllowed Values (first 3):")
                                for val in allowed[:3]:
                                    print(f"  {json.dumps(val, indent=4)}")
                        
                        # Search for an issue that ALREADY has the new field populated
                        print(f"\n🔍 Searching for an issue with {new_field_key} already populated...")
                        check_jql = f"cf[{raw_new}] is not EMPTY"
                        check_url = f"{JIRA_URL}/rest/api/2/search"
                        check_params = {
                            "jql": check_jql,
                            "fields": f"key,{new_field_key}",
                            "maxResults": 1,
                            "expand": "renderedFields"
                        }
                        check_res = requests.get(check_url, headers=headers, params=check_params, timeout=10)
                        if check_res.status_code == 200:
                            check_data = check_res.json()
                            if check_data.get('issues'):
                                populated_issue = check_data['issues'][0]
                                populated_key = populated_issue['key']
                                populated_value = populated_issue['fields'].get(new_field_key)
                                print(f"  Found issue {populated_key} with populated field!")
                                print(f"  Field Value (what JIRA returns):")
                                print(f"  {json.dumps(populated_value, indent=4)}")
                                
                                # Get the FULL issue with all expansions
                                full_populated_url = f"{JIRA_URL}/rest/api/2/issue/{populated_key}"
                                full_populated_params = {"expand": "names,schema,renderedFields"}
                                full_pop_res = requests.get(full_populated_url, headers=headers, params=full_populated_params, timeout=10)
                                if full_pop_res.status_code == 200:
                                    full_pop_data = full_pop_res.json()
                                    raw_field_value = full_pop_data.get('fields', {}).get(new_field_key)
                                    rendered_field_value = full_pop_data.get('renderedFields', {}).get(new_field_key)
                                    
                                    print(f"\n  RAW Field Value:")
                                    print(f"  {json.dumps(raw_field_value, indent=4)}")
                                    
                                    if rendered_field_value and rendered_field_value != raw_field_value:
                                        print(f"\n  RENDERED Field Value:")
                                        print(f"  {json.dumps(rendered_field_value, indent=4)}")
                                    
                                    # Try to get via Insight API to see object structure
                                    if isinstance(raw_field_value, list) and len(raw_field_value) > 0:
                                        first_val = raw_field_value[0]
                                        if isinstance(first_val, str) and '(' in first_val:
                                            test_key = first_val.split('(')[-1].strip(')')
                                            print(f"\n  Fetching Insight object {test_key} to see full structure...")
                                            insight_obj_url = f"{JIRA_URL}/rest/insight/1.0/object/{test_key}"
                                            insight_res = requests.get(insight_obj_url, headers=headers, timeout=10)
                                            if insight_res.status_code == 200:
                                                insight_obj = insight_res.json()
                                                print(f"  Insight Object ID: {insight_obj.get('id')}")
                                                print(f"  Insight Object Key: {insight_obj.get('objectKey')}")
                                                print(f"  Insight Object Label: {insight_obj.get('label')}")
                            else:
                                print(f"  No issues found with {new_field_key} populated yet")
                        
                        print(f"{'='*80}\n")
                        sample_shown = True

                    for issue in issues:
                        issue_key = issue['key']
                        value_to_copy = issue['fields'].get(old_field_key)
                        
                        # Format value for display
                        value_display = json.dumps(value_to_copy) if isinstance(value_to_copy, (dict, list)) else str(value_to_copy)
                        if len(value_display) > 100:
                            value_display = value_display[:100] + "..."

                        # Convert to asset field format
                        converted_value = convert_to_asset_field(value_to_copy, new_field_key)
                        
                        if converted_value is None:
                            print(f"⊘ [{issue_key}] Skipped: No value to convert")
                            log_data.append([issue_key, old_field_key, new_field_key, value_display, "Skipped", "No value"])
                            total_processed += 1
                            field_issue_count += 1
                            continue

                        # 2. Update the new field
                        update_url = f"{JIRA_URL}/rest/api/2/issue/{issue_key}?notifyUsers=false"
                        payload = {"fields": {new_field_key: converted_value}}
                        
                        # Debug: Print exact payload
                        print(f"  📤 Payload: {json.dumps(payload)}")

                        try:
                            update_res = requests.put(update_url, json=payload, headers=headers, timeout=30)

                            if update_res.status_code == 204:
                                # Verify the update by reading back the field
                                verify_url = f"{JIRA_URL}/rest/api/2/issue/{issue_key}?fields={new_field_key}"
                                verify_res = requests.get(verify_url, headers=headers, timeout=10)
                                
                                actual_value = None
                                if verify_res.status_code == 200:
                                    verify_data = verify_res.json()
                                    actual_value = verify_data.get('fields', {}).get(new_field_key)
                                
                                converted_display = json.dumps(converted_value) if isinstance(converted_value, (dict, list)) else str(converted_value)
                                if len(converted_display) > 100:
                                    converted_display = converted_display[:100] + "..."
                                
                                if actual_value:
                                    actual_display = json.dumps(actual_value) if isinstance(actual_value, (dict, list)) else str(actual_value)
                                    if len(actual_display) > 100:
                                        actual_display = actual_display[:100] + "..."
                                    print(f"✓ [{issue_key}] Updated successfully!")
                                    print(f"  Sent: {converted_display}")
                                    print(f"  Actual Value in Field: {actual_display}")
                                    log_data.append([issue_key, old_field_key, new_field_key, value_display, "Success", actual_display])
                                else:
                                    print(f"⚠ [{issue_key}] API returned 204 but field is EMPTY!")
                                    print(f"  Sent: {converted_display}")
                                    print(f"  Actual Value: NULL/EMPTY")
                                    log_data.append([issue_key, old_field_key, new_field_key, value_display, "Warning - Field Empty After Update", converted_display])
                                
                                total_success += 1
                            else:
                                error_text = update_res.text
                                print(f"✗ [{issue_key}] Failed: {error_text}")
                                log_data.append([issue_key, old_field_key, new_field_key, value_display, "Failed", error_text])
                                total_failed += 1
                        except requests.exceptions.RequestException as e:
                            error_msg = f"Request error: {str(e)}"
                            print(f"✗ [{issue_key}] {error_msg}")
                            log_data.append([issue_key, old_field_key, new_field_key, value_display, "Failed", error_msg])
                            total_failed += 1
                        except KeyboardInterrupt:
                            print("\n\n⚠️  Migration interrupted by user. Saving partial results...")
                            raise
                        
                        total_processed += 1
                        field_issue_count += 1
                        
                        # Small delay to avoid rate limiting
                        time.sleep(0.1)

                    # Handle Pagination
                    start_at += max_results
                    if start_at >= total_issues:
                        break
                
                print(f"\n✓ Completed migration for {old_field_key}: {field_issue_count} issues processed")

    except FileNotFoundError:
        print(f"Error: {INPUT_CSV} not found. Please ensure the file exists.")
        return
    except KeyboardInterrupt:
        print("\n\n⚠️  Migration interrupted by user!")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()

    # 3. Write results to CSV
    with open(OUTPUT_LOG_CSV, mode='w', newline='', encoding='utf-8') as log_file:
        writer = csv.writer(log_file)
        writer.writerow(["Issue Key", "Old Field", "New Field", "Value Copied", "Status", "Error Log"])
        writer.writerows(log_data)

    print(f"\n{'='*80}")
    print(f"MIGRATION SUMMARY")
    print(f"{'='*80}")
    print(f"Total Issues Processed: {total_processed}")
    print(f"  ✓ Successful: {total_success}")
    print(f"  ✗ Failed: {total_failed}")
    print(f"\nResults saved to: {OUTPUT_LOG_CSV}")
    print(f"{'='*80}\n")

if __name__ == "__main__":
    migrate_fields()