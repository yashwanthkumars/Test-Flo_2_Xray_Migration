import csv
import requests
import math
import time
import re
import random
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# ---------------- CONFIG ----------------
JIRA_BASE_URL = "https://greyorange-work-uat-sandbox.atlassian.net"
EMAIL = "yashwanth.k@padahsolutions.com"
API_TOKEN = "YOUR_TOKEN"

INPUT_FILE = "issue_keys.csv"
OUTPUT_FILE = "cloud_issue_mapping_fastLatest1.csv"
MAX_WORKERS = 5  # Parallel workers
MAX_RETRIES = 3
REQUESTS_PER_SECOND = 5.0

# Thread lock for safe dictionary updates
result_lock = threading.Lock()
rate_lock = threading.Lock()
_last_request_ts = 0.0

# ------------- LOG FUNCTION -------------
def log(msg):
    print(msg, flush=True)


def throttle():
    """Global throttle to keep overall request rate under REQUESTS_PER_SECOND.
    Safe across threads.
    """
    global _last_request_ts
    if REQUESTS_PER_SECOND <= 0:
        return
    interval = 1.0 / REQUESTS_PER_SECOND
    with rate_lock:
        now = time.monotonic()
        wait = (_last_request_ts + interval) - now
        if wait > 0:
            time.sleep(wait)
            now = time.monotonic()
        _last_request_ts = now

# ------------- READ ISSUE KEYS -------------
def read_issue_keys():
    keys = set()
    parent_child_pairs = []

    with open(INPUT_FILE, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)

        normalized = {h.lower().replace(" ", "").replace("_", ""): h for h in reader.fieldnames}
        parent_col = normalized.get("parentkey") or normalized.get("parent") or normalized.get("parent_key")
        child_col  = normalized.get("childkey") or normalized.get("child") or normalized.get("child_key")

        log(f"Detected Headers: {reader.fieldnames}")
        log(f"Using Parent column: {parent_col}, Child column: {child_col}")

        if not parent_col or not child_col:
            raise ValueError("❌ Could not detect Parent/Child columns in CSV.")

        for row in reader:
            parent = row[parent_col].strip() if parent_col and row.get(parent_col) else ""
            child  = row[child_col].strip() if child_col and row.get(child_col) else ""
            
            # Add all non-empty keys
            if parent:
                keys.add(parent)
            if child:
                keys.add(child)
            
            # Add pairs if both exist
            if parent and child:
                parent_child_pairs.append((parent, child))

    return list(keys), parent_child_pairs

# ------------- FETCH CLOUD ID FOR SINGLE ISSUE -------------
def fetch_issue_id(issue_key):
    """Fetch cloud ID for a single issue using direct API endpoint"""
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}"

    for attempt in range(MAX_RETRIES):
        try:
            throttle()
            response = requests.get(
                url,
                headers={"Accept": "application/json"},
                params={"fields": "id,key"},
                auth=(EMAIL, API_TOKEN),
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("id")
            elif response.status_code == 404:
                log(f"⚠️ Issue not found: {issue_key}")
                return None
            elif response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "5")
                try:
                    delay = float(retry_after)
                except:
                    delay = min(60, 2 ** (attempt + 1))
                log(f"❌ Rate limited on {issue_key}, sleeping {delay:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})")
                time.sleep(delay)
            else:
                log(f"❌ Error {response.status_code} for {issue_key}: {response.text[:100]}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
                else:
                    return None
                    
        except Exception as e:
            log(f"❌ Request error for {issue_key}: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
            else:
                return None

    return None

# ------------- MAIN FUNCTION (PARALLEL) -------------
def main():
    start_time = time.time()

    # CLI overrides
    parser = argparse.ArgumentParser(description="Fetch Jira Cloud issue IDs")
    parser.add_argument("--workers", type=int, default=None, help="Parallel workers (default 5)")
    parser.add_argument("--rps", type=float, default=None, help="Requests per second (default 5.0)")
    parser.add_argument("--output", type=str, default=None, help="Output CSV path")
    args, unknown = parser.parse_known_args()

    global MAX_WORKERS, REQUESTS_PER_SECOND, OUTPUT_FILE
    if args.workers and args.workers > 0:
        MAX_WORKERS = args.workers
    if args.rps and args.rps > 0:
        REQUESTS_PER_SECOND = args.rps
    if args.output:
        OUTPUT_FILE = args.output
    
    log("📥 Reading input CSV...")
    all_keys, parent_child_pairs = read_issue_keys()

    log(f"📊 Total unique keys: {len(all_keys)}")
    log(f"🚀 Processing with {MAX_WORKERS} workers (rps={REQUESTS_PER_SECOND})")

    issue_id_map = {}

    # Parallel processing - fetch each issue individually
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(fetch_issue_id, key): key for key in all_keys}
        
        completed = 0
        for future in as_completed(futures):
            key = futures[future]
            issue_id = future.result()
            
            with result_lock:
                if issue_id:
                    issue_id_map[key] = issue_id
                    
            completed += 1
            if completed % 50 == 0 or completed == len(all_keys):
                log(f"✅ Progress: {completed}/{len(all_keys)} - {len(issue_id_map)} IDs fetched")

    log(f"📤 Writing output to: {OUTPUT_FILE}")
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ParentKey", "ParentID_CLOUD", "ChildKey", "ChildID_CLOUD"])

        for parent, child in parent_child_pairs:
            writer.writerow([
                parent,
                issue_id_map.get(parent, ""),
                child,
                issue_id_map.get(child, "")
            ])

    elapsed = time.time() - start_time
    log(f"🎉 Complete! {len(all_keys)} keys in {elapsed:.2f}s | {len(issue_id_map)} IDs found")

# ------------- ENTRY POINT -------------
if __name__ == "__main__":
    main()
