import requests
import csv
import json
import time
import os

# --- CONFIGURATION ---
BASE_URL = "https://work-uat.greyorange.com/jira"
TOKEN = "YOUR_TOKEN"
INPUT_CSV = "fields_to_clone.csv"
MAPPING_LOG_CSV = "migration_logv2.csv"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "X-Atlassian-Token": "no-check"
}

def get_field_info(field_id):
    """Gets the underlying type and searcher of the old field."""
    url = f"{BASE_URL}/rest/api/2/field"
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return None, None
    fields = response.json()
    # Normalize ID to numeric for comparison
    clean_id = str(field_id).replace("customfield_", "")
    for f in fields:
        if f['id'] == f"customfield_{clean_id}":
            return f.get('schema', {}).get('custom'), f.get('schema', {}).get('customId')
    return None, None

def create_new_field(old_name, old_id):
    """Creates a new custom field with '- New' suffix as Asset Object type."""
    # Force asset object type instead of copying old field type
    # This is the Insight/Assets field type used in your Jira instance
    custom_type = "com.riadalabs.jira.plugins.insight:rlabs-customfield-default-object"

    new_name = f"{old_name} - New"
    payload = {
        "name": new_name,
        "description": f"Cloned from {old_id} - Asset Object Field",
        "type": custom_type,
        "searcherKey": "com.riadalabs.jira.plugins.insight:rlabs-customfield-object-searcher"
    }
    
    url = f"{BASE_URL}/rest/api/2/field"
    response = requests.post(url, headers=headers, json=payload)
    
    # Handle duplicate name conflict
    if response.status_code == 400 and "already exists" in response.text:
        print(f"   -> Name '{new_name}' exists, trying '- NEW2'")
        payload["name"] = f"{old_name} - NEW2"
        response = requests.post(url, headers=headers, json=payload)
    
    if response.status_code == 201:
        return response.json().get('id'), payload["name"]
    return None, f"Status {response.status_code}: {response.text}"

def migrate_contexts(old_field_id, new_field_id):
    """Fetches contexts from old field and creates ALL of them in the new field."""
    # Note: Using numeric ID for internal endpoint
    clean_old_id = str(old_field_id).replace("customfield_", "")
    get_url = f"{BASE_URL}/rest/internal/2/field/customfield_{clean_old_id}/context"
    res_get = requests.get(get_url, headers=headers)
    
    if res_get.status_code != 200:
        return f"Failed to get old context: {res_get.text}"

    contexts = res_get.json()
    if not contexts:
        return "No contexts found to migrate"

    # Delete the default context created for the new field first
    new_get_url = f"{BASE_URL}/rest/internal/2/field/{new_field_id}/context"
    res_new_get = requests.get(new_get_url, headers=headers)
    
    if res_new_get.status_code == 200 and res_new_get.json():
        default_context_id = res_new_get.json()[0]['id']
        delete_url = f"{BASE_URL}/rest/internal/2/field/{new_field_id}/context/{default_context_id}"
        requests.delete(delete_url, headers=headers)
        print(f"   -> Deleted default context {default_context_id}")

    errors = []
    created_count = 0
    
    # Create a NEW context for each old context
    for idx, ctx in enumerate(contexts, 1):
        payload = {
            "name": ctx.get('name'),
            "description": ctx.get('description'),
            "allProjects": ctx.get('allProjects'),
            "projects": [{"id": str(p['id'])} for p in ctx.get('projects', [])],
            "allIssueTypes": ctx.get('allIssueTypes'),
            "issueTypes": [{"id": str(it['id'])} for it in ctx.get('issueTypes', [])]
        }
        
        # POST to create a new context instead of PUT to update
        post_url = f"{BASE_URL}/rest/internal/2/field/{new_field_id}/context"
        res_post = requests.post(post_url, headers=headers, json=payload)
        
        if res_post.status_code in [200, 201]:
            created_count += 1
            print(f"   -> Created context {idx}/{len(contexts)}: {ctx.get('name')}")
        else:
            error_msg = f"Context '{ctx.get('name')}' POST Error {res_post.status_code}"
            errors.append(error_msg)
            print(f"   -> Failed: {error_msg}")
            
    result = f"Created {created_count}/{len(contexts)} contexts"
    return result if not errors else f"{result}. Errors: {'; '.join(errors)}"

def main():
    print("--- Jira Field Migration Tool ---")
    
    if not os.path.exists(INPUT_CSV):
        print(f"Error: {INPUT_CSV} not found in {os.getcwd()}")
        return

    with open(INPUT_CSV, mode='r', encoding='utf-8-sig') as fin:
        reader = list(csv.DictReader(fin))
        print(f"Found {len(reader)} rows in {INPUT_CSV}")

        with open(MAPPING_LOG_CSV, mode='w', newline='', encoding='utf-8') as fout:
            writer = csv.writer(fout)
            writer.writerow(["Original_Name", "Original_ID", "New_Name", "New_ID", "Status", "Errors"])

            for row in reader:
                fname = row.get('fieldname')
                fid = row.get('fieldid')
                
                if not fname or not fid:
                    print("Skipping empty or malformed row...")
                    continue
                
                print(f"Processing: {fname} (ID: {fid})")
                
                # 1. Create Field
                new_fid, result_msg = create_new_field(fname, fid)
                
                if not new_fid:
                    print(f"   [!] Failed to create field: {result_msg[:50]}...")
                    writer.writerow([fname, fid, "", "", "FAILED_TO_CREATE", result_msg])
                    continue
                
                print(f"   [+] Created New Field: {new_fid}")
                
                # 2. Migrate Context
                time.sleep(2) # Allow Jira indexing
                status = migrate_contexts(fid, new_fid)
                
                log_status = "COMPLETED" if status == "Success" else "CONTEXT_PARTIAL_FAIL"
                writer.writerow([fname, fid, result_msg, new_fid, log_status, status])
                print(f"   [+] Context Migration: {status}")

    print(f"\n--- Process Finished. View logs in {MAPPING_LOG_CSV} ---")

if __name__ == "__main__":
    main()