import csv
import json
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import re
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
import threading
import time
import os

# -----------------------------------------
# CONFIG
# -----------------------------------------
CLIENT_ID = "YOUR_TOKEN"
CLIENT_SECRET = "YOUR_TOKEN"

AUTH_URL = "https://xray.cloud.getxray.app/api/v2/authenticate"
GRAPHQL_URL = "https://xray.cloud.getxray.app/api/v2/graphql"

CSV_FILE = "import_steps3.csv"
OUTPUT_CSV = f"import_steps_results_optimizedv8_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
CHECKPOINT_FILE = "import_steps_checkpointv8.json"

# Performance settings
MAX_WORKERS = 3  # Number of parallel threads (reduced to avoid rate limits)
BATCH_SIZE = 20   # Steps to add per batch (optimal for Xray API)
REQUEST_TIMEOUT = 60  # Timeout for API requests in seconds

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(threadName)-10s] - %(message)s',
    handlers=[
        logging.FileHandler(f'import_steps_execution_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Thread-safe counters
class Counters:
    def __init__(self):
        self.lock = threading.Lock()
        self.success = 0
        self.failed = 0
        self.processed = 0
        self.total_steps_added = 0
    
    def increment_success(self, steps_count=0):
        with self.lock:
            self.success += 1
            self.processed += 1
            self.total_steps_added += steps_count
    
    def increment_failed(self):
        with self.lock:
            self.failed += 1
            self.processed += 1
    
    def get_stats(self):
        with self.lock:
            return {
                'success': self.success,
                'failed': self.failed,
                'processed': self.processed,
                'total_steps': self.total_steps_added
            }

counters = Counters()

# -----------------------------------------
# SESSION WITH CONNECTION POOLING & RETRY
# -----------------------------------------
def create_session():
    """Create a requests session with connection pooling and retry logic"""
    session = requests.Session()
    
    # Retry strategy
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST", "GET"]
    )
    
    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=MAX_WORKERS,
        pool_maxsize=MAX_WORKERS * 2
    )
    
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    return session

# Global session
session = create_session()

# -----------------------------------------
# CLEAN FUNCTION
# -----------------------------------------
def clean(value):
    if value is None:
        return ""
    value = str(value).strip()
    # Remove non-printable characters but keep common ones
    value = re.sub(r"[^\x20-\x7E\n\r\t]", "", value)
    value = re.sub(r"\s+", " ", value)
    return value

def escape_graphql_string(value):
    """Escape special characters for GraphQL strings"""
    if not value:
        return ""
    value = value.replace('\\', '\\\\')
    value = value.replace('"', '\\"')
    value = value.replace('\n', '\\n')
    value = value.replace('\r', '\\r')
    value = value.replace('\t', '\\t')
    return value

# -----------------------------------------
# AUTHENTICATION
# -----------------------------------------
def get_token():
    logger.info("Authenticating with Xray")
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
    
    headers = {"Content-Type": "application/json"}
    
    try:
        response = session.post(AUTH_URL, json=payload, headers=headers, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"Authentication failed: {response.text}")
            return None
        
        logger.info("Authentication successful")
        return response.json()
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        return None

# -----------------------------------------
# LOAD CSV WITH GROUPING
# -----------------------------------------
def load_steps_from_csv():
    tests = defaultdict(lambda: {"steps": []})
    
    logger.info(f"Reading steps from {CSV_FILE}")
    
    try:
        with open(CSV_FILE, "r", encoding="utf-8", newline='') as file:
            reader = csv.DictReader(file)
            reader.fieldnames = [clean(h) for h in reader.fieldnames]
            
            row_num = 0
            for row in reader:
                row_num += 1
                
                test_key = clean(row.get("Test Key", ""))
                step_no_str = clean(row.get("Step No", ""))
                
                if not test_key or not step_no_str:
                    continue
                
                try:
                    step_no = int(step_no_str)
                except ValueError:
                    continue
                
                action = clean(row.get("Action", "")).replace('\n', ' ').replace('\r', ' ')
                data = clean(row.get("Input", "")).replace('\n', ' ').replace('\r', ' ')
                result = clean(row.get("Expected Result", "")).replace('\n', ' ').replace('\r', ' ')
                
                step = {
                    "action": action,
                    "data": data,
                    "result": result,
                    "step_no": step_no
                }
                
                tests[test_key]["steps"].append(step)
        
        logger.info(f"Loaded steps for {len(tests)} tests from {row_num} rows")
        return tests
    except Exception as e:
        logger.error(f"Error loading CSV: {e}")
        return {}

# -----------------------------------------
# LOAD CHECKPOINT
# -----------------------------------------
def load_checkpoint():
    """Load processed test keys from checkpoint file"""
    if not os.path.exists(CHECKPOINT_FILE):
        return set()
    
    try:
        with open(CHECKPOINT_FILE, 'r') as f:
            data = json.load(f)
            return set(data.get('processed', []))
    except Exception as e:
        logger.warning(f"Could not load checkpoint: {e}")
        return set()

def save_checkpoint(test_key):
    """Save processed test key to checkpoint file"""
    try:
        processed = load_checkpoint()
        processed.add(test_key)
        
        with open(CHECKPOINT_FILE, 'w') as f:
            json.dump({'processed': list(processed)}, f)
    except Exception as e:
        logger.warning(f"Could not save checkpoint: {e}")

# -----------------------------------------
# GET TEST ISSUE ID
# -----------------------------------------
def get_test_issue_id(token, test_key):
    """Get the test issueId from test key"""
    query = f"""
    {{
        getTests(jql: "key = {test_key}", limit: 1) {{
            results {{
                issueId
                testType {{ name }}
            }}
        }}
    }}
    """
    
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    try:
        response = session.post(
            GRAPHQL_URL, 
            json={"query": query}, 
            headers=headers,
            timeout=REQUEST_TIMEOUT
        )
        result = response.json()
        
        if "errors" in result:
            return None
            
        tests = result.get("data", {}).get("getTests", {}).get("results", [])
        if tests:
            return tests[0].get("issueId")
        return None
    except Exception as e:
        logger.error(f"Error getting test {test_key}: {e}")
        return None

# -----------------------------------------
# ADD STEPS IN BATCHES
# -----------------------------------------
def add_steps_batch(token, issue_id, steps_batch):
    """Add multiple steps in a single operation using mutation"""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    # Build mutations for all steps in batch
    mutations = []
    for idx, step in enumerate(steps_batch):
        action = escape_graphql_string(step['action'])
        data = escape_graphql_string(step['data'])
        result = escape_graphql_string(step['result'])
        
        mutation = f"""
        step{idx}: addTestStep(
            issueId: "{issue_id}",
            step: {{
                action: "{action}",
                data: "{data}",
                result: "{result}"
            }}
        ) {{
            id
        }}
        """
        mutations.append(mutation)
    
    # Combine all mutations into one query
    query = f"""
    mutation {{
        {' '.join(mutations)}
    }}
    """
    
    try:
        response = session.post(
            GRAPHQL_URL, 
            json={"query": query}, 
            headers=headers,
            timeout=REQUEST_TIMEOUT
        )
        result_json = response.json()
        
        if "errors" in result_json:
            error_msg = result_json['errors'][0].get('message', str(result_json['errors']))
            return {"error": error_msg}
        
        return {"success": True, "steps_added": len(steps_batch)}
        
    except Exception as e:
        return {"error": str(e)}

# -----------------------------------------
# UPDATE TEST STEPS WITH BATCHING
# -----------------------------------------
def update_test_steps(token, test_key, steps):
    """Add steps to test using batching for better performance"""
    
    # Get the issue ID first
    issue_id = get_test_issue_id(token, test_key)
    if not issue_id:
        return {"error": "Test not found"}
    
    total_steps = len(steps)
    steps_added = 0
    
    # Process steps in batches
    for i in range(0, total_steps, BATCH_SIZE):
        batch = steps[i:i + BATCH_SIZE]
        result = add_steps_batch(token, issue_id, batch)
        
        if "error" in result:
            return {"error": f"Batch {i//BATCH_SIZE + 1} failed: {result['error']}"}
        
        steps_added += result.get("steps_added", 0)
        
        # Small delay to avoid rate limiting
        if i + BATCH_SIZE < total_steps:
            time.sleep(0.5)
    
    return {"success": True, "steps_added": steps_added}

# -----------------------------------------
# PROCESS SINGLE TEST (WORKER FUNCTION)
# -----------------------------------------
def process_test(token, test_key, test_data, total_tests):
    """Process a single test - used by worker threads"""
    
    steps = sorted(test_data["steps"], key=lambda x: x["step_no"])
    
    try:
        update_response = update_test_steps(token, test_key, steps)
        
        if "error" in update_response:
            status = "Failed"
            message = update_response["error"]
            counters.increment_failed()
            logger.warning(f"❌ {test_key} ({len(steps)} steps) - FAILED: {message}")
        elif "success" in update_response:
            status = "Success"
            steps_added = update_response.get("steps_added", len(steps))
            message = f"Added {steps_added} steps"
            counters.increment_success(steps_added)
            save_checkpoint(test_key)
            
            stats = counters.get_stats()
            logger.info(f"✅ {test_key} ({steps_added} steps) - Progress: {stats['processed']}/{total_tests}")
        else:
            status = "Unknown"
            message = "Unknown response format"
            counters.increment_failed()
        
        return [test_key, len(steps), status, message]
        
    except Exception as e:
        counters.increment_failed()
        logger.error(f"❌ {test_key} - Exception: {e}")
        return [test_key, len(steps), "Failed", str(e)]

# -----------------------------------------
# MAIN PROCESS WITH PARALLEL EXECUTION
# -----------------------------------------
def process_imports():
    start_time = datetime.now()
    logger.info("=" * 80)
    logger.info("🚀 Starting OPTIMIZED test steps import")
    logger.info("=" * 80)
    
    # Get token
    token = get_token()
    if not token:
        logger.error("Failed to authenticate")
        return
    
    # Load steps from CSV
    tests = load_steps_from_csv()
    if not tests:
        logger.error("No tests loaded from CSV")
        return
    
    # Load checkpoint to skip already processed tests
    processed_tests = load_checkpoint()
    remaining_tests = {k: v for k, v in tests.items() if k not in processed_tests}
    
    total_tests = len(tests)
    total_remaining = len(remaining_tests)
    total_steps = sum(len(t["steps"]) for t in tests.values())
    remaining_steps = sum(len(t["steps"]) for t in remaining_tests.values())
    
    logger.info(f"\n📊 Statistics:")
    logger.info(f"   Total tests: {total_tests}")
    logger.info(f"   Already processed: {len(processed_tests)}")
    logger.info(f"   Remaining: {total_remaining}")
    logger.info(f"   Total steps: {total_steps}")
    logger.info(f"   Remaining steps: {remaining_steps}")
    logger.info(f"   Batch size: {BATCH_SIZE}")
    logger.info(f"   Parallel workers: {MAX_WORKERS}")
    logger.info(f"\n⚡ Processing with {MAX_WORKERS} parallel workers...\n")
    
    output_rows = []
    
    # Process tests in parallel
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all tasks
        future_to_test = {
            executor.submit(process_test, token, test_key, test_data, total_tests): test_key
            for test_key, test_data in remaining_tests.items()
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_test):
            try:
                result = future.result()
                output_rows.append(result)
            except Exception as e:
                test_key = future_to_test[future]
                logger.error(f"Exception processing {test_key}: {e}")
                output_rows.append([test_key, 0, "Failed", str(e)])
    
    # Write output CSV
    logger.info(f"\n📝 Writing results to {OUTPUT_CSV}")
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Test Key", "Steps Count", "Status", "Message"])
        writer.writerows(output_rows)
    
    elapsed_time = datetime.now() - start_time
    stats = counters.get_stats()
    
    # Calculate performance metrics
    steps_per_second = stats['total_steps'] / elapsed_time.total_seconds() if elapsed_time.total_seconds() > 0 else 0
    
    logger.info("\n" + "=" * 80)
    logger.info("📈 FINAL SUMMARY")
    logger.info("=" * 80)
    logger.info(f"✅ Success:      {stats['success']}/{total_remaining}")
    logger.info(f"❌ Failed:       {stats['failed']}/{total_remaining}")
    logger.info(f"📊 Total Steps:  {stats['total_steps']}")
    logger.info(f"⏱️  Time:         {elapsed_time.total_seconds():.1f} seconds ({elapsed_time})")
    logger.info(f"🚀 Speed:        {steps_per_second:.1f} steps/second")
    logger.info(f"📄 Results:      {OUTPUT_CSV}")
    logger.info(f"💾 Checkpoint:   {CHECKPOINT_FILE}")
    logger.info("=" * 80)
    
    # Cleanup checkpoint if all done
    if stats['success'] == total_remaining and os.path.exists(CHECKPOINT_FILE):
        logger.info("✨ All tests processed successfully! Cleaning up checkpoint file.")
        try:
            os.remove(CHECKPOINT_FILE)
        except:
            pass

# -----------------------------------------
# RUN
# -----------------------------------------
if __name__ == "__main__":
    try:
        process_imports()
    except KeyboardInterrupt:
        logger.info("\n⚠️  Process interrupted by user. Progress saved in checkpoint file.")
        stats = counters.get_stats()
        logger.info(f"Processed: {stats['processed']} tests, {stats['total_steps']} steps")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
