import requests
import csv
import json
import time
import re
import threading
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
JIRA_URL = "https://work-uat.greyorange.com/jira"
TOKEN = "YOUR_TOKEN" 
INPUT_CSV = "fields_mapping.csv"
OUTPUT_LOG_CSV = "migration_detailed_logv1.csv"

# Tuning: Start small to verify it's not a network hang
MAX_WORKERS = 10      
FETCH_BATCH_SIZE = 500 

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "X-Atlassian-Token": "no-check"
}

# Queue for logging
log_queue = queue.Queue()

def logger_worker():
    """Background thread that only writes to the CSV."""
    with open(OUTPUT_LOG_CSV, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Issue Key", "Status", "Input Value", "Error Message"])
        while True:
            item = log_queue.get()
            if item is None: break  # Signal to stop
            writer.writerow([time.strftime("%H:%M:%S")] + item)
            f.flush() # Force write to disk so you can see it live
            log_queue.task_done()

def get_asset_id(display_value):
    if not display_value: return None
    if isinstance(display_value, list):
        return [get_asset_id(v) for v in display_value]
    match = re.search(r'\((.*?)\)', str(display_value))
    return {"key": match.group(1)} if match else display_value

def update_issue_worker(issue_key, field_id, raw_value):
    url = f"{JIRA_URL}/rest/api/2/issue/{issue_key}?notifyUsers=false"
    formatted_value = get_asset_id(raw_value)
    payload = {"fields": {field_id: formatted_value}}
    
    try:
        # Reduced timeout to prevent hanging forever
        res = requests.put(url, json=payload, headers=headers, timeout=10)
        if res.status_code == 204:
            log_queue.put([issue_key, "SUCCESS", raw_value, ""])
            return True
        else:
            log_queue.put([issue_key, "FAILED", raw_value, res.text])
            return False
    except Exception as e:
        log_queue.put([issue_key, "ERROR", raw_value, str(e)])
        return False

def run_fast_migration():
    # Start the background logger
    logger_thread = threading.Thread(target=logger_worker, daemon=True)
    logger_thread.start()

    print(f"--- STARTING FAST MIGRATION ---")
    
    with open(INPUT_CSV, mode='r', encoding='utf-8-sig') as f:
        mapping = list(csv.DictReader(f))[0]
    
    old_cf = f"customfield_{mapping['old_id'].strip()}"
    new_cf = f"customfield_{mapping['new_id'].strip()}"
    jql = f"cf[{mapping['old_id']}] is not EMPTY AND cf[{mapping['new_id']}] is EMPTY"

    total_success = 0
    start_at = 0
    
    try:
        while True:
            print(f"Fetching next {FETCH_BATCH_SIZE} issues (startAt={start_at})...")
            search_url = f"{JIRA_URL}/rest/api/2/search"
            params = {"jql": jql, "fields": f"key,{old_cf}", "maxResults": FETCH_BATCH_SIZE, "startAt": start_at}
            
            resp = requests.get(search_url, headers=headers, params=params, timeout=30)
            response_data = resp.json()
            issues = response_data.get('issues', [])
            total_results = response_data.get('total', 0)
            
            print(f"Found {len(issues)} issues in this batch (Total matching JQL: {total_results})")
            
            if not issues:
                print("No more issues found.")
                break

            print(f"Batch loaded. Updating {len(issues)} issues in parallel...")

            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = [
                    executor.submit(update_issue_worker, iss['key'], new_cf, iss['fields'].get(old_cf)) 
                    for iss in issues
                ]
                
                # Use a counter to show live dots so you know it's not stuck
                for i, future in enumerate(as_completed(futures)):
                    if future.result():
                        total_success += 1
                    if i % 10 == 0:
                        print(".", end="", flush=True)

            print(f"\nBatch Complete. Total successes: {total_success}")
            
            # Move to next batch
            start_at += len(issues)
            
            # Check if we've processed all available issues
            if start_at >= total_results:
                print(f"All {total_results} issues processed.")
                break

    except KeyboardInterrupt:
        print("\nStopping script...")
    finally:
        # Shut down logger
        log_queue.put(None)
        logger_thread.join()
        print(f"Final log saved to {OUTPUT_LOG_CSV}")

if __name__ == "__main__":
    run_fast_migration()