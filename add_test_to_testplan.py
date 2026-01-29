import csv
import requests
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from datetime import datetime
from time import time, sleep
import threading

# -----------------------------------------
# CONFIG
# -----------------------------------------

CLIENT_ID = "C3831C07670443818278986370084C75"
CLIENT_SECRET = "16990faa88467ac38e7f7fd989377e4f5ad1a0bbace6b0f5df50b3058b9a7bd9"

AUTH_URL = "https://xray.cloud.getxray.app/api/v2/authenticate"
GRAPHQL_URL = "https://xray.cloud.getxray.app/api/v2/graphql"

INPUT_CSV = "childtolink.csv"
OUTPUT_CSV = "testplan_add_resultsuatv.csv" #chaange V1 for evry run because we need logs for all runs

# Performance tuning (adjusted for rate limits)
BATCH_SIZE = 20  # Reduced batch size
MAX_WORKERS = 3  # Reduced workers to avoid rate limiting
REQUEST_DELAY = 0.5  # Delay between requests (seconds)
MAX_RETRIES = 3  # Retry failed requests
RETRY_DELAY = 5  # Initial retry delay (seconds)

# Token management
token_lock = threading.Lock()
current_token = None
token_timestamp = 0
TOKEN_REFRESH_INTERVAL = 3000  # Refresh token every 50 minutes


# -----------------------------------------
# CLEAN FUNCTION
# -----------------------------------------

def clean(value):
    if value is None:
        return ""
    value = str(value).strip()
    value = re.sub(r"[^\x20-\x7E]", "", value)
    value = re.sub(r"\s+", " ", value)
    return value


# -----------------------------------------
# GET TOKEN (WITH CACHING & REFRESH)
# -----------------------------------------

def get_token(force_refresh=False):
    global current_token, token_timestamp
    
    with token_lock:
        # Check if we need to refresh the token
        if force_refresh or current_token is None or (time() - token_timestamp) > TOKEN_REFRESH_INTERVAL:
            payload = {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET
            }
            try:
                response = requests.post(AUTH_URL, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
                if response.status_code != 200:
                    print("❌ Auth failed:", response.text)
                    return None
                current_token = response.json()
                token_timestamp = time()
                print("✔ Token refreshed")
            except Exception as e:
                print(f"❌ Token refresh error: {e}")
                return None
        
        return current_token


# -----------------------------------------
# ADD TESTS TO TEST PLAN (BATCH WITH RETRY)
# -----------------------------------------

def add_tests_to_testplan_batch(testplan_id, test_ids, attempt=1):
    """
    Add multiple tests to a test plan with retry logic and rate limit handling.
    """
    # Get fresh token
    token = get_token()
    if not token:
        return {"error": "Failed to get token"}
    
    # Format test IDs for GraphQL
    test_ids_str = ", ".join([f'"{tid}"' for tid in test_ids])
    
    query = f"""
    mutation {{
        addTestsToTestPlan(
            issueId: "{testplan_id}",
            testIssueIds: [{test_ids_str}]
        ) {{
            addedTests
            warning
        }}
    }}
    """

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        # Add delay between requests to respect rate limits
        sleep(REQUEST_DELAY)
        
        response = requests.post(GRAPHQL_URL, json={"query": query}, headers=headers, timeout=60)
        result = response.json()
        
        # Check for rate limit error
        if "errors" in result:
            error_msg = str(result.get("errors", []))
            if "Too many requests" in error_msg or "rate limit" in error_msg.lower():
                if attempt <= MAX_RETRIES:
                    wait_time = RETRY_DELAY * (2 ** (attempt - 1))  # Exponential backoff
                    print(f"⚠️ Rate limited. Retrying in {wait_time}s (attempt {attempt}/{MAX_RETRIES})...")
                    sleep(wait_time)
                    return add_tests_to_testplan_batch(testplan_id, test_ids, attempt + 1)
                else:
                    print(f"❌ Max retries exceeded for test plan {testplan_id}")
        
        return result
        
    except Exception as e:
        if attempt <= MAX_RETRIES:
            wait_time = RETRY_DELAY * (2 ** (attempt - 1))
            print(f"⚠️ Error: {e}. Retrying in {wait_time}s...")
            sleep(wait_time)
            return add_tests_to_testplan_batch(testplan_id, test_ids, attempt + 1)
        return {"error": str(e)}


# -----------------------------------------
# PROCESS CSV (OPTIMIZED)
# -----------------------------------------

def process_csv():
    start_time = time()
    token = get_token()
    if not token:
        return

    # Step 1: Read CSV and group by test plan
    print("📖 Reading CSV and grouping tests by test plan...")
    testplan_tests = defaultdict(list)
    
    with open(INPUT_CSV, "r") as f:
        reader = csv.DictReader(f)
        reader.fieldnames = [clean(h) for h in reader.fieldnames]

        for row in reader:
            testplan_id = clean(row["test_plan_id"])
            test_id = clean(row["test_issue_id"])
            testplan_tests[testplan_id].append(test_id)

    total_plans = len(testplan_tests)
    total_tests = sum(len(tests) for tests in testplan_tests.values())
    print(f"✔ Found {total_tests} tests across {total_plans} test plans")

    # Step 2: Create batches for each test plan
    print(f"📦 Creating batches (batch size: {BATCH_SIZE})...")
    batches = []
    
    for testplan_id, test_ids in testplan_tests.items():
        # Split tests into batches of BATCH_SIZE
        for i in range(0, len(test_ids), BATCH_SIZE):
            batch_tests = test_ids[i:i + BATCH_SIZE]
            batches.append((testplan_id, batch_tests))
    
    total_batches = len(batches)
    print(f"✔ Created {total_batches} batches")

    # Step 3: Process batches in parallel
    print(f"🚀 Processing batches with {MAX_WORKERS} workers...")
    results = []
    completed = 0

    def process_batch(batch_info):
        testplan_id, test_ids = batch_info
        response = add_tests_to_testplan_batch(testplan_id, test_ids)
        return testplan_id, test_ids, response

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_batch, batch): batch for batch in batches}
        
        for future in as_completed(futures):
            completed += 1
            testplan_id, test_ids, response = future.result()
            
            # Store result for each test in the batch
            for test_id in test_ids:
                results.append({
                    "test_plan_id": testplan_id,
                    "test_issue_id": test_id,
                    "response": json.dumps(response)
                })
            
            # Progress update
            if completed % 10 == 0 or completed == total_batches:
                elapsed = time() - start_time
                rate = completed / elapsed if elapsed > 0 else 0
                eta = (total_batches - completed) / rate if rate > 0 else 0
                print(f"⏳ Progress: {completed}/{total_batches} batches ({completed*100//total_batches}%) | "
                      f"Elapsed: {elapsed:.1f}s | ETA: {eta:.1f}s")

    # Step 4: Write output CSV
    print(f"💾 Writing results to {OUTPUT_CSV}...")
    with open(OUTPUT_CSV, "w", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=["test_plan_id", "test_issue_id", "response"])
        writer.writeheader()
        writer.writerows(results)

    elapsed_total = time() - start_time
    print(f"\n🎉 DONE! Processed {total_tests} tests in {elapsed_total:.1f} seconds ({total_tests/elapsed_total:.1f} tests/sec)")
    print(f"📄 Results saved to: {OUTPUT_CSV}")


# -----------------------------------------
# RUN SCRIPT
# -----------------------------------------

if __name__ == "__main__":
    process_csv()
