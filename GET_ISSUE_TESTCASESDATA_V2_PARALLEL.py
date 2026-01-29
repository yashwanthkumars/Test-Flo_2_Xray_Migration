import requests
import csv
import html
import re
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# ---------------- CONFIGURATION ----------------
JIRA_BASE_URL = "https://work-uat.greyorange.com"
JIRA_USERNAME = "yashwanth.k@padahsolutions.com"
JIRA_API_TOKEN = "Pr0j#ct@JCM!2526"
JQL_QUERY = 'key  in ("GM-167199","GM-167200")'

# ------------------------------------------------

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.FileHandler('script_execution442-443_dup.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Thread lock for thread-safe list operations
results_lock = threading.Lock()


def clean_html(text):
    """Remove HTML tags and decode HTML entities."""
    text = html.unescape(text)
    text = re.sub(r"<[^>]*>", "", text)
    return text.strip()


def get_issues_by_jql(jql):
    """Run JQL query and return matching issues with pagination."""
    url = f"{JIRA_BASE_URL}/jira/rest/api/2/search"
    auth = (JIRA_USERNAME, JIRA_API_TOKEN)
    
    all_issues = []
    start_at = 0
    max_results = 100
    
    while True:
        params = {
            "jql": jql, 
            "fields": "summary,issuetype,subtasks",
            "startAt": start_at,
            "maxResults": max_results
        }
        try:
            logger.info(f"Fetching issues: startAt={start_at}")
            response = requests.get(url, auth=auth, params=params)
            response.raise_for_status()
            data = response.json()
            issues = data.get("issues", [])
            total = data.get("total", 0)
            
            all_issues.extend(issues)
            logger.info(f"Retrieved {len(issues)} issues (Total: {len(all_issues)}/{total})")
            
            # Check if we've retrieved all issues
            if start_at + len(issues) >= total:
                break
                
            start_at += max_results
            
        except requests.exceptions.RequestException as e:
            logger.error(f"JQL query error: {e}")
            raise
    
    logger.info(f"JQL query completed: {len(all_issues)} total issues")
    return all_issues


def get_issue_details(issue_key):
    """Fetch full issue data by key."""
    url = f"{JIRA_BASE_URL}/jira/rest/api/2/issue/{issue_key}"
    auth = (JIRA_USERNAME, JIRA_API_TOKEN)
    params = {"expand": "renderedFields"}
    try:
        response = requests.get(url, auth=auth, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {issue_key}: {e}")
        raise


def extract_steps_data(issue_json):
    """Extract test steps from issue JSON (stepsRows and renderedCells)."""
    fields = issue_json.get("fields", {})
    key = issue_json.get("key", "")
    issue_id = issue_json.get("id", "")
    summary = fields.get("summary", "")
    issue_type = fields.get("issuetype", {}).get("name", "")

    # Extract the test steps from customfield_15416 -> stepsRows -> renderedCells
    steps = []
    customfield_15416 = fields.get("customfield_15416", {})

    if customfield_15416 and isinstance(customfield_15416, dict):
        test_steps = customfield_15416.get("stepsRows", [])

        for i, step in enumerate(test_steps, start=1):
            status_name = step.get("status", {}).get("name", "")
            cells = step.get("cells", [])
            rendered_cells = step.get("renderedCells", [])
 
            # Clean HTML
            clean_cells = [clean_html(c) for c in rendered_cells or cells]
 
            # Check if we have at least 3 columns
            if len(clean_cells) >= 3:
                steps.append({
                    "#": i,
                    "Action": clean_cells[0],
                    "Input": clean_cells[1],
                    "Expected result": clean_cells[2],
                    "Status": status_name
                })
 
    return key, issue_id, issue_type, summary, steps


def process_subtask(sub, plan_key, plan_id, plan_summary):
    """Process a single subtask (parallel worker function)."""
    sub_key = sub["key"]
    sub_id = sub["id"]
    
    try:
        sub_issue = get_issue_details(sub_key)
        key, issue_id, issue_type, summary, steps = extract_steps_data(sub_issue)
        
        rows = []
        for step in steps:
            rows.append({
                "Parent Key": plan_key,
                "Parent ID": plan_id,
                "Parent Summary": plan_summary,
                "Child Key": key,
                "Child ID": issue_id,
                "Child Summary": summary,
                "Issue Type": issue_type,
                **step
            })
        
        return rows
    except Exception as e:
        logger.error(f"Error processing subtask {sub_key}: {e}")
        return []


def main():
    start_time = datetime.now()
    logger.info("Starting Test Plan Data Extraction (Parallel)")
    
    all_rows = []
    test_plans = get_issues_by_jql(JQL_QUERY)
    logger.info(f"Found {len(test_plans)} Test Plans")
 
    # Use ThreadPoolExecutor for parallel processing
    max_workers = 10  # Adjust based on system resources
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        
        for plan_idx, plan in enumerate(test_plans, 1):
            plan_key = plan["key"]
            plan_id = plan["id"]
            plan_summary = plan["fields"].get("summary", "")
            subtasks = plan["fields"].get("subtasks", [])
            
            logger.info(f"[{plan_idx}/{len(test_plans)}] Processing {plan_key} with {len(subtasks)} subtasks")
            
            # Submit each subtask as a parallel job
            for sub in subtasks:
                future = executor.submit(process_subtask, sub, plan_key, plan_id, plan_summary)
                futures.append(future)
        
        # Collect results as they complete
        completed = 0
        for future in as_completed(futures):
            try:
                rows = future.result()
                with results_lock:
                    all_rows.extend(rows)
                completed += 1
                if completed % 50 == 0:
                    logger.info(f"Completed {completed}/{len(futures)} parallel tasks")
            except Exception as e:
                logger.error(f"Error in parallel processing: {e}")
    
    logger.info(f"Extracted {len(all_rows)} total test steps")
 
    # Write to CSV
    csv_file = "jira_test_Plan_with_442-443_dup.csv"
    logger.info(f"Writing data to {csv_file}")
    try:
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            fieldnames = [
                "Parent Key", "Parent ID", "Parent Summary",
                "Child Key", "Child ID", "Child Summary",
                "Issue Type", "#", "Action", "Input", "Expected result", "Status"
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_rows)
        logger.info(f"CSV export completed: {csv_file}")
    except Exception as e:
        logger.error(f"CSV write error: {e}")
        raise
    
    elapsed_time = datetime.now() - start_time
    logger.info(f"Completed in {elapsed_time.total_seconds():.2f} seconds")


if __name__ == "__main__":
    main()
