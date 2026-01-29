import requests
import csv
import json
import time
import os

# --- CONFIGURATION ---
BASE_URL = "https://work-uat.greyorange.com/jira"
TOKEN = "YOUR_TOKEN"
INPUT_CSV = "fields_mapping.csv"  # Ensure columns: old_id, new_id
OUTPUT_LOG_CSV = "screen_migration_log.csv"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "X-Atlassian-Token": "no-check"
}

def clean_id(field_id):
    return str(field_id).replace("customfield_", "").strip()

def migrate_screens(old_id, new_id):
    """Finds screens containing the old field and adds the new field to them."""
    old_cf = f"customfield_{old_id}"
    new_cf = f"customfield_{new_id}"
    
    # 1. Get all screens in Jira
    screen_url = f"{BASE_URL}/rest/api/2/screens"
    res = requests.get(screen_url, headers=headers)
    
    if res.status_code != 200:
        return f"Error fetching screens: {res.text}"

    screens = res.json()
    affected_screens = 0
    errors = []

    for screen in screens:
        screen_id = screen['id']
        
        # 2. Get tabs for this screen
        tabs_url = f"{BASE_URL}/rest/api/2/screens/{screen_id}/tabs"
        tabs_res = requests.get(tabs_url, headers=headers)
        
        if tabs_res.status_code != 200:
            continue

        for tab in tabs_res.json():
            tab_id = tab['id']
            
            # 3. Get fields in this tab
            fields_url = f"{BASE_URL}/rest/api/2/screens/{screen_id}/tabs/{tab_id}/fields"
            fields_res = requests.get(fields_url, headers=headers)
            
            if fields_res.status_code != 200:
                continue

            # Check if old field is in this tab
            tab_fields = [f['id'] for f in fields_res.json()]
            
            if old_cf in tab_fields:
                if new_cf in tab_fields:
                    print(f"   -> New field already on Screen {screen_id}, Tab {tab_id}")
                    continue

                # 4. Add the new field to this specific tab
                add_url = f"{BASE_URL}/rest/api/2/screens/{screen_id}/tabs/{tab_id}/fields"
                payload = {"fieldId": new_cf}
                add_res = requests.post(add_url, headers=headers, json=payload)

                if add_res.status_code in [200, 201]:
                    print(f"   [+] Added to Screen: {screen['name']} (ID: {screen_id})")
                    affected_screens += 1
                else:
                    errors.append(f"Screen {screen_id} Fail: {add_res.text}")

    if not errors:
        return f"Success: Added to {affected_screens} screens"
    else:
        return f"Partial Success ({affected_screens}). Errors: {'; '.join(errors)}"

def main():
    print("--- Jira Screen Association Migrator ---")
    
    if not os.path.exists(INPUT_CSV):
        print(f"Error: {INPUT_CSV} not found.")
        return

    log_data = []

    with open(INPUT_CSV, mode='r', encoding='utf-8-sig') as file:
        reader = csv.DictReader(file)
        for row in reader:
            old_raw = clean_id(row['old_id'])
            new_raw = clean_id(row['new_id'])
            
            print(f"\nProcessing: customfield_{old_raw} -> customfield_{new_raw}")
            
            status = migrate_screens(old_raw, new_raw)
            log_data.append([old_raw, new_raw, status])
            print(f"Result: {status}")

    # Write logs
    with open(OUTPUT_LOG_CSV, mode='w', newline='', encoding='utf-8') as log_file:
        writer = csv.writer(log_file)
        writer.writerow(["Old ID", "New ID", "Migration Status"])
        writer.writerows(log_data)

    print(f"\nDone. Log saved to {OUTPUT_LOG_CSV}")

if __name__ == "__main__":
    main()