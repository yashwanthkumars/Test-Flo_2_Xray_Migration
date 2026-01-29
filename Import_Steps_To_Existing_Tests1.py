import csv
import json
import requests
import re
import logging
from datetime import datetime

# -----------------------------------------
# CONFIG
# -----------------------------------------
CLIENT_ID = "YOUR_TOKEN"
CLIENT_SECRET = "YOUR_TOKEN"

AUTH_URL = "https://xray.cloud.getxray.app/api/v2/authenticate"
GRAPHQL_URL = "https://xray.cloud.getxray.app/api/v2/graphql"

CSV_FILE = "import_steps1.csv"  # CSV with Test Key, Step No, Action, Input, Expected Result
OUTPUT_CSV = "import_steps_resultsv4.csv"   #chaange V1 for evry run because we need logs for all runs

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.FileHandler('import_steps_execution.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# Set UTF-8 encoding for console output
import sys
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

logger = logging.getLogger(__name__)


# -----------------------------------------
# CLEAN FUNCTION (TRIM TEXT, REMOVE JUNK)
# -----------------------------------------
def clean(value):
    if value is None:
        return ""
    value = str(value).strip()
    value = re.sub(r"[^\x20-\x7E]", "", value)
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
# AUTHENTICATION → RETURNS TOKEN
# -----------------------------------------
def get_token():
    logger.info("Authenticating with Xray")
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }

    headers = {"Content-Type": "application/json"}
    response = requests.post(AUTH_URL, json=payload, headers=headers)

    if response.status_code != 200:
        logger.error(f"Authentication failed: {response.text}")
        return None

    logger.info("Authentication successful")
    return response.json()


# -----------------------------------------
# READ CSV & GROUP STEPS BY TEST KEY
# -----------------------------------------
def load_steps_from_csv():
    from collections import defaultdict
    tests = defaultdict(lambda: {"steps": []})

    logger.info(f"Reading steps from {CSV_FILE}")
    
    # Use newline='' to properly handle multi-line fields in CSV
    with open(CSV_FILE, "r", encoding="utf-8", newline='') as file:
        reader = csv.DictReader(file)
        reader.fieldnames = [clean(h) for h in reader.fieldnames]

        row_num = 0
        for row in reader:
            row_num += 1
            
            # Get and validate required fields
            test_key = clean(row.get("Test Key", ""))
            step_no_str = clean(row.get("Step No", ""))
            
            if not test_key:
                logger.warning(f"Row {row_num}: Skipping - empty Test Key")
                continue
                
            if not step_no_str:
                logger.warning(f"Row {row_num}: Test {test_key} - empty Step No, skipping")
                continue
            
            try:
                step_no = int(step_no_str)
            except ValueError:
                logger.warning(f"Row {row_num}: Test {test_key} - invalid Step No '{step_no_str}', skipping")
                continue
            
            # Clean multi-line fields (replace newlines with spaces)
            action = clean(row.get("Action", "")).replace('\n', ' ').replace('\r', ' ')
            data = clean(row.get("Input", "")).replace('\n', ' ').replace('\r', ' ')
            result = clean(row.get("Expected Result", "")).replace('\n', ' ').replace('\r', ' ')
            
            step = {
                "action": action,
                "data": data,
                "result": result,
                "status": clean(row.get("status", "")),
                "step_no": step_no
            }

            tests[test_key]["steps"].append(step)

    logger.info(f"Loaded steps for {len(tests)} test issues from {row_num} rows")
    return tests


# -----------------------------------------
# GET EXISTING TEST TO ADD STEPS
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
        response = requests.post(GRAPHQL_URL, json={"query": query}, headers=headers)
        result = response.json()
        tests = result.get("data", {}).get("getTests", {}).get("results", [])
        if tests:
            return tests[0].get("issueId")
        return None
    except Exception as e:
        logger.error(f"Error getting test {test_key}: {e}")
        return None


# -----------------------------------------
# UPDATE TEST STEPS IN XRAY USING addTestStep MUTATION
# -----------------------------------------
def update_test_steps(token, test_key, steps):
    """
    Uses GraphQL addTestStep mutation to add steps to existing test.
    """
    
    # Get the issue ID first
    issue_id = get_test_issue_id(token, test_key)
    if not issue_id:
        return {"error": f"Test not found"}
    
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    try:
        # Add each step using addTestStep mutation
        steps_added = 0
        for s in steps:
            action = escape_graphql_string(s['action'])
            data = escape_graphql_string(s['data'])
            result = escape_graphql_string(s['result'])
            
            # Note: Removing 'status' field as it's not supported in CreateStepInput
            query = f"""
            mutation {{
                addTestStep(
                    issueId: "{issue_id}",
                    step: {{
                        action: "{action}",
                        data: "{data}",
                        result: "{result}"
                    }}
                ) {{
                    id
                    action
                    data
                    result
                }}
            }}
            """
            
            response = requests.post(GRAPHQL_URL, json={"query": query}, headers=headers)
            result_json = response.json()
            
            if "errors" in result_json:
                error_msg = result_json['errors'][0].get('message', str(result_json['errors']))
                return {"error": error_msg}
            
            steps_added += 1
        
        return {"success": True, "steps_added": steps_added}
        
    except Exception as e:
        return {"error": str(e)}


# -----------------------------------------
# MAIN PROCESS
# -----------------------------------------
def process_imports():
    start_time = datetime.now()
    logger.info("=" * 60)
    logger.info("Starting test steps import")
    logger.info("=" * 60)
    
    token = get_token()
    if not token:
        logger.error("Failed to authenticate")
        return

    tests = load_steps_from_csv()
    output_rows = []

    total_tests = len(tests)
    success_count = 0
    failed_count = 0
    
    logger.info(f"\n📊 Processing {total_tests} tests...\n")
    
    for idx, (test_key, test_data) in enumerate(tests.items(), 1):
        steps = sorted(test_data["steps"], key=lambda x: x["step_no"])
        
        print(f"[{idx}/{total_tests}] {test_key} ({len(steps)} steps)... ", end="", flush=True)

        update_response = update_test_steps(token, test_key, steps)

        if "error" in update_response:
            status = "Failed"
            message = update_response["error"]
            print(f"❌ FAILED - {message}")
            failed_count += 1
        elif "success" in update_response:
            status = "Success"
            steps_added = update_response.get("steps_added", len(steps))
            message = f"Added {steps_added} steps"
            print(f"✅ SUCCESS")
            success_count += 1
        else:
            status = "Unknown"
            message = "Unknown response format"
            print(f"⚠️ UNKNOWN")

        output_rows.append([test_key, len(steps), status, message])

    # -----------------------------------------
    # WRITE OUTPUT CSV
    # -----------------------------------------
    logger.info(f"\nWriting results to {OUTPUT_CSV}")
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Test Key", "Steps Count", "Status", "Message"])
        writer.writerows(output_rows)

    elapsed_time = datetime.now() - start_time
    
    logger.info("\n" + "=" * 60)
    logger.info("📈 SUMMARY")
    logger.info("=" * 60)
    logger.info(f"✅ Success: {success_count}/{total_tests}")
    logger.info(f"❌ Failed:  {failed_count}/{total_tests}")
    logger.info(f"⏱️  Time:    {elapsed_time.total_seconds():.1f} seconds")
    logger.info(f"📄 Results: {OUTPUT_CSV}")
    logger.info("=" * 60)


# RUN
if __name__ == "__main__":
    process_imports()
