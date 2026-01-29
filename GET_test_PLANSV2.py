import requests
import csv
import html
import re

# ---------------- CONFIGURATION ----------------
JIRA_BASE_URL = "https://work.greyorange.com"  # Replace with your Jira Server URL
JIRA_USERNAME = "yashwanth.k@padahsolutions.com"  # Your Jira username
JIRA_API_TOKEN = "YOUR_TOKEN"  # Your Jira API token (or password if using basic auth)
JQL_QUERY = 'issuetype = "Test Plan"'  # Modify if needed
# JQL_QUERY = 'issuetype = "Test Plan" AND project in (Intralogistics,GM)'
# ------------------------------------------------


def clean_html(text):
    """Remove HTML tags and decode HTML entities."""
    text = html.unescape(text)
    text = re.sub(r"<[^>]*>", "", text)
    return text.strip()


def get_issues_by_jql(jql):
    """Run JQL query with pagination and return all matching issues."""
    url = f"{JIRA_BASE_URL}/jira/rest/api/2/search"
    auth = (JIRA_USERNAME, JIRA_API_TOKEN)
    params = {"jql": jql, "fields": "summary,issuetype,subtasks", "maxResults": 50}  # Set max results per page
    all_issues = []
    start_at = 0

    while True:
        params["startAt"] = start_at  # Specify where to start the next page of results
        response = requests.get(url, auth=auth, params=params)
        response.raise_for_status()
        data = response.json()
        issues = data.get("issues", [])
        all_issues.extend(issues)

        # Check if there are more issues to fetch
        if len(issues) < 50:  # If less than 50 issues, it's the last page
            break
        start_at += 50  # Move to the next page

    return all_issues


def get_issue_details(issue_key):
    """Fetch full issue data by key with pagination support."""
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


def main():
    all_rows = []
    test_plans = get_issues_by_jql(JQL_QUERY)

    print(f"Found {len(test_plans)} Test Plans")

    for plan in test_plans:
        plan_key = plan["key"]
        plan_id = plan["id"]  # ✅ Parent issue ID
        plan_summary = plan["fields"].get("summary", "")
        subtasks = plan["fields"].get("subtasks", [])
        print(f"Processing {plan_key} ({plan_id}) with {len(subtasks)} subtasks")

        for sub in subtasks:
            sub_key = sub["key"]
            sub_id = sub["id"]  # ✅ Child issue ID
            sub_issue = get_issue_details(sub_key)
            key, issue_id, issue_type, summary, steps = extract_steps_data(sub_issue)

            # Add the main issue's key, id, and summary to each subtask row
            for step in steps:
                all_rows.append({
                    "Parent Key": plan_key,
                    "Parent ID": plan_id,
                    "Parent Summary": plan_summary,
                    "Child Key": key,
                    "Child ID": issue_id,
                    "Child Summary": summary,
                    "Issue Type": issue_type,
                    **step
                })

    # Write to CSV
    csv_file = "jira_test_plan_forlgandgmproject.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "Parent Key", "Parent ID", "Parent Summary",
            "Child Key", "Child ID", "Child Summary",
            "Issue Type", "#", "Action", "Input", "Expected result", "Status"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"✅ CSV exported successfully: {csv_file}")


if __name__ == "__main__":
    main()
