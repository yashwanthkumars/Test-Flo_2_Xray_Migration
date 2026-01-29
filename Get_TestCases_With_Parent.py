import requests
import csv
import time

# ---------------- CONFIGURATION ----------------
JIRA_BASE_URL = "https://work-uat.greyorange.com"
JIRA_USERNAME = "yashwanth.k@padahsolutions.com"
JIRA_API_TOKEN = "YOUR_TOKEN"
JQL_QUERY = 'project = "GM" AND issuetype = "Test Case"'

# ------------------------------------------------


def get_issues_by_jql(jql, max_results=25):
    """Run JQL query and return matching issues with pagination."""
    url = f"{JIRA_BASE_URL}/jira/rest/api/2/search"
    auth = (JIRA_USERNAME, JIRA_API_TOKEN)
    all_issues = []
    start_at = 0
    
    while True:
        params = {
            "jql": jql,
            "fields": "key,id,summary,parent",
            "startAt": start_at,
            "maxResults": max_results,
            "validateQuery": "false"
        }
        print(f"Fetching issues: startAt={start_at}, maxResults={max_results}")
        
        # Retry logic for server errors
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.get(url, auth=auth, params=params, timeout=120)
                response.raise_for_status()
                break
            except requests.exceptions.HTTPError as e:
                if response.status_code >= 500 and attempt < max_retries - 1:
                    wait_time = 10 * (attempt + 1)
                    print(f"  Server error, retrying in {wait_time} seconds... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    print(f"  Error: {e}")
                    print(f"  Response text: {response.text[:500]}")
                    raise
        
        data = response.json()
        issues = data.get("issues", [])
        all_issues.extend(issues)
        
        total = data.get("total", 0)
        print(f"  Retrieved {len(issues)} issues (Total: {len(all_issues)}/{total})")
        
        if start_at + len(issues) >= total:
            break
        start_at += max_results
    
    return all_issues


def get_total_count(jql):
    """Get total count of issues matching the JQL without fetching all data."""
    url = f"{JIRA_BASE_URL}/jira/rest/api/2/search"
    auth = (JIRA_USERNAME, JIRA_API_TOKEN)
    params = {
        "jql": jql,
        "maxResults": 0
    }
    try:
        response = requests.get(url, auth=auth, params=params, timeout=30)
        response.raise_for_status()
        return response.json().get("total", 0)
    except Exception as e:
        print(f"Warning: Could not get total count: {e}")
        return None


def main():
    print(f"Executing JQL: {JQL_QUERY}\n")
    
    # Try to get total count first
    total_count = get_total_count(JQL_QUERY)
    if total_count is not None:
        print(f"Total test cases to fetch: {total_count}\n")
    
    test_cases = get_issues_by_jql(JQL_QUERY)
    print(f"\nFound {len(test_cases)} Test Cases")
    
    # Process each test case
    all_rows = []
    for idx, tc in enumerate(test_cases, start=1):
        tc_key = tc.get("key", "")
        tc_summary = tc.get("fields", {}).get("summary", "")
        
        # Get parent information
        parent = tc.get("fields", {}).get("parent", {})
        parent_key = parent.get("key", "") if parent else ""
        parent_summary = parent.get("fields", {}).get("summary", "") if parent else ""
        
        all_rows.append({
            "Test Case Key": tc_key,
            "Test Case Summary": tc_summary,
            "Parent Key": parent_key,
            "Parent Summary": parent_summary
        })
        
        if idx % 50 == 0:
            print(f"Processed {idx}/{len(test_cases)} test cases...")
    
    # Write to CSV
    csv_file = "test_cases_with_parent.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "Test Case Key",
            "Test Case Summary",
            "Parent Key",
            "Parent Summary"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)
    
    print(f"\n✅ CSV exported successfully: {csv_file}")
    print(f"Total test cases written: {len(all_rows)}")


if __name__ == "__main__":
    main()
