import requests
import csv
import html
import re
 
# ---------------- CONFIGURATION ----------------
JIRA_BASE_URL = "https://work-uat.greyorange.com"  # Replace with your Jira Server URL
JIRA_USERNAME = "yashwanth.k@padahsolutions.com"  # Your Jira username
JIRA_API_TOKEN = "Pr0j#ct@JCM!2526"  # Your Jira API token (or password if using basic auth)
JQL_QUERY = 'key = GM-249456'  # Modify if needed
# JQL_QUERY = 'issuetype = "Test Plan" AND project in ("GM")'

# ------------------------------------------------
 

def clean_html(text):
    """Remove HTML tags and decode HTML entities."""
    text = html.unescape(text)
    text = re.sub(r"<[^>]*>", "", text)
    return text.strip()
 
 
def get_issues_by_jql(jql, max_results=100):
    """Run JQL query and return matching issues with pagination."""
    url = f"{JIRA_BASE_URL}/jira/rest/api/2/search"
    auth = (JIRA_USERNAME, JIRA_API_TOKEN)
    all_issues = []
    start_at = 0
    
    while True:
        params = {
            "jql": jql,
            "fields": "summary,issuetype,id,key",
            "startAt": start_at,
            "maxResults": max_results
        }
        response = requests.get(url, auth=auth, params=params)
        response.raise_for_status()
        data = response.json()
        issues = data.get("issues", [])
        all_issues.extend(issues)
        
        total = data.get("total", 0)
        if start_at + len(issues) >= total:
            break
        start_at += max_results
    
    return all_issues
 
 
def get_issue_details(issue_key):
    """Fetch full issue data by key."""
    url = f"{JIRA_BASE_URL}/jira/rest/api/2/issue/{issue_key}"
    auth = (JIRA_USERNAME, JIRA_API_TOKEN)
    params = {"expand": "renderedFields"}
    response = requests.get(url, auth=auth, params=params)
    response.raise_for_status()
    return response.json()
 
 
def extract_steps_data(issue_json):
    """Extract test steps from issue JSON (stepsRows and renderedCells)."""
    fields = issue_json.get("fields", {})
    key = issue_json.get("key", "")
    issue_id = issue_json.get("id", "")
    summary = fields.get("summary", "")
    issue_type = fields.get("issuetype", {}).get("name", "")
    
    # Extract additional fields
    description = clean_html(fields.get("description", "") or "")
    priority = fields.get("priority", {}).get("name", "") if fields.get("priority") else ""
    
    # Affects Version/s - can be multiple
    versions = fields.get("versions", [])
    affects_versions = ", ".join([v.get("name", "") for v in versions]) if versions else ""
    
    # Component/s - can be multiple
    components = fields.get("components", [])
    components_str = ", ".join([c.get("name", "") for c in components]) if components else ""
    
    # Labels - can be multiple
    labels = fields.get("labels", [])
    labels_str = ", ".join(labels) if labels else ""
    
    # Sprint
    sprint_field = fields.get("customfield_10020", [])  # Sprint is usually customfield_10020
    sprint = ""
    if sprint_field and isinstance(sprint_field, list) and len(sprint_field) > 0:
        # Extract sprint name from the sprint string format
        sprint_str = str(sprint_field[-1])  # Get last sprint
        match = re.search(r'name=([^,\]]+)', sprint_str)
        if match:
            sprint = match.group(1)
    
    # Story Points
    story_points = fields.get("customfield_10026", "") or ""  # Story Points is usually customfield_10026
    
    # Custom fields
    cf_15424 = fields.get("customfield_15424", "") or ""
    cf_15417 = fields.get("customfield_15417", "") or ""
    cf_15420 = fields.get("customfield_15420", "") or ""
    cf_15421 = fields.get("customfield_15421", "") or ""
    cf_15615 = fields.get("customfield_15615", "") or ""
    cf_16603 = fields.get("customfield_16603", "") or ""
    cf_15414 = fields.get("customfield_15414", "") or ""
    cf_11600 = fields.get("customfield_11600", "") or ""
    
    # Handle custom fields that might be objects
    if isinstance(cf_15424, dict):
        cf_15424 = cf_15424.get("value", "") or cf_15424.get("name", "")
    if isinstance(cf_15417, dict):
        cf_15417 = cf_15417.get("value", "") or cf_15417.get("name", "")
    if isinstance(cf_15420, dict):
        cf_15420 = cf_15420.get("value", "") or cf_15420.get("name", "")
    if isinstance(cf_15421, dict):
        cf_15421 = cf_15421.get("value", "") or cf_15421.get("name", "")
    if isinstance(cf_15615, dict):
        cf_15615 = cf_15615.get("value", "") or cf_15615.get("name", "")
    if isinstance(cf_16603, dict):
        cf_16603 = cf_16603.get("value", "") or cf_16603.get("name", "")
    if isinstance(cf_15414, dict):
        cf_15414 = cf_15414.get("value", "") or cf_15414.get("name", "")
    if isinstance(cf_11600, dict):
        cf_11600 = cf_11600.get("value", "") or cf_11600.get("name", "")
    
    # Assignee and Reporter
    assignee = fields.get("assignee", {})
    assignee_name = assignee.get("displayName", "") if assignee else ""
    
    reporter = fields.get("reporter", {})
    reporter_name = reporter.get("displayName", "") if reporter else ""
    
    # Status
    status = fields.get("status", {}).get("name", "") if fields.get("status") else ""
 
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
 
    return {
        "key": key,
        "issue_id": issue_id,
        "issue_type": issue_type,
        "summary": summary,
        "description": description,
        "priority": priority,
        "affects_versions": affects_versions,
        "components": components_str,
        "labels": labels_str,
        "sprint": sprint,
        "story_points": story_points,
        "cf_15424": cf_15424,
        "cf_15417": cf_15417,
        "cf_15420": cf_15420,
        "cf_15421": cf_15421,
        "cf_15615": cf_15615,
        "cf_16603": cf_16603,
        "cf_15414": cf_15414,
        "assignee": assignee_name,
        "reporter": reporter_name,
        "cf_11600": cf_11600,
        "status": status,
        "steps": steps
    }
 
 
def main():
    all_rows = []
    test_plans = get_issues_by_jql(JQL_QUERY)
 
    print(f"Found {len(test_plans)} Test Plans")
 
    for plan in test_plans:
        plan_key = plan["key"]
        plan_id = plan["id"]  # ✅ Parent issue ID
        plan_summary = plan["fields"].get("summary", "")
        
        # Fetch all subtasks using JQL query
        subtasks_jql = f'parent = {plan_key}'
        subtasks = get_issues_by_jql(subtasks_jql)
        print(f"Processing {plan_key} ({plan_id}) with {len(subtasks)} subtasks")
 
        for sub in subtasks:
            sub_key = sub["key"]
            sub_id = sub["id"]  # ✅ Child issue ID
            sub_issue = get_issue_details(sub_key)
            issue_data = extract_steps_data(sub_issue)
 
            # Always write at least one row per subtask
            steps = issue_data["steps"]
            if steps:
                for step in steps:
                    all_rows.append({
                        "Parent Key": plan_key,
                        "Parent ID": plan_id,
                        "Parent Summary": plan_summary,
                        "Child Key": issue_data["key"],
                        "Child ID": issue_data["issue_id"],
                        "Child Summary": issue_data["summary"],
                        "Issue Type": issue_data["issue_type"],
                        "Description": issue_data["description"],
                        "Priority": issue_data["priority"],
                        "Affects Version/s": issue_data["affects_versions"],
                        "Component/s": issue_data["components"],
                        "Labels": issue_data["labels"],
                        "Sprint": issue_data["sprint"],
                        "Story Points": issue_data["story_points"],
                        "15424": issue_data["cf_15424"],
                        "15417": issue_data["cf_15417"],
                        "15420": issue_data["cf_15420"],
                        "15421": issue_data["cf_15421"],
                        "15615": issue_data["cf_15615"],
                        "16603": issue_data["cf_16603"],
                        "15414": issue_data["cf_15414"],
                        "Assignee": issue_data["assignee"],
                        "Reporter": issue_data["reporter"],
                        "Team": issue_data["cf_11600"],
                        "Status": issue_data["status"],
                        "Step No": step["#"],
                        "Action": step["Action"],
                        "Input": step["Input"],
                        "Expected Result": step["Expected result"],
                        "Step Status": step["Status"]
                    })
            else:
                all_rows.append({
                    "Parent Key": plan_key,
                    "Parent ID": plan_id,
                    "Parent Summary": plan_summary,
                    "Child Key": issue_data["key"],
                    "Child ID": issue_data["issue_id"],
                    "Child Summary": issue_data["summary"],
                    "Issue Type": issue_data["issue_type"],
                    "Description": issue_data["description"],
                    "Priority": issue_data["priority"],
                    "Affects Version/s": issue_data["affects_versions"],
                    "Component/s": issue_data["components"],
                    "Labels": issue_data["labels"],
                    "Sprint": issue_data["sprint"],
                    "Story Points": issue_data["story_points"],
                    "15424": issue_data["cf_15424"],
                    "15417": issue_data["cf_15417"],
                    "15420": issue_data["cf_15420"],
                    "15421": issue_data["cf_15421"],
                    "15615": issue_data["cf_15615"],
                    "16603": issue_data["cf_16603"],
                    "15414": issue_data["cf_15414"],
                    "Assignee": issue_data["assignee"],
                    "Reporter": issue_data["reporter"],
                    "Team": issue_data["cf_11600"],
                    "Status": issue_data["status"],
                    "Step No": "",
                    "Action": "",
                    "Input": "",
                    "Expected Result": "",
                    "Step Status": ""
                })
 
    # Write to CSV
    csv_file = "jira_test_steps_with_ids.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "Parent Key", "Parent ID", "Parent Summary",
            "Child Key", "Child ID", "Child Summary",
            "Issue Type", "Description", "Priority", "Affects Version/s", "Component/s",
            "Labels", "Sprint", "Story Points", "15424", "15417", "15420", "15421",
            "15615", "16603", "15414", "Assignee", "Reporter", "Team", "Status",
            "Step No", "Action", "Input", "Expected Result", "Step Status"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)
 
    print(f"✅ CSV exported successfully: {csv_file}")
 
 
if __name__ == "__main__":
    main()