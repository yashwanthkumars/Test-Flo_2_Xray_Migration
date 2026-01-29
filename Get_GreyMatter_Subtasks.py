import requests
import csv
import html
import re

# ---------------- CONFIGURATION ----------------
JIRA_BASE_URL = "https://work-uat.greyorange.com"
JIRA_USERNAME = "yashwanth.k@padahsolutions.com"
JIRA_API_TOKEN = "Pr0j#ct@JCM!2526"
JQL_QUERY = 'project = GreyMatter AND issuetype = Sub-task'

# ------------------------------------------------


def clean_html(text):
    """Remove HTML tags and decode HTML entities."""
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]*>", "", text)
    return text.strip()


def get_issues_by_jql(jql, start_at=0, max_results=100):
    """Run JQL query and return matching issues with pagination."""
    url = f"{JIRA_BASE_URL}/jira/rest/api/2/search"
    auth = (JIRA_USERNAME, JIRA_API_TOKEN)
    params = {
        "jql": jql,
        "startAt": start_at,
        "maxResults": max_results,
        "fields": "summary,issuetype,status,assignee,priority,created,updated,description,parent"
    }
    response = requests.get(url, auth=auth, params=params)
    response.raise_for_status()
    return response.json()


def main():
    all_issues = []
    start_at = 0
    max_results = 100
    
    print(f"Fetching issues for JQL: {JQL_QUERY}")
    
    while True:
        result = get_issues_by_jql(JQL_QUERY, start_at, max_results)
        issues = result.get("issues", [])
        total = result.get("total", 0)
        
        print(f"Fetched {len(issues)} issues (Total: {total}, Current batch: {start_at + 1}-{start_at + len(issues)})")
        
        for issue in issues:
            key = issue.get("key", "")
            issue_id = issue.get("id", "")
            fields = issue.get("fields", {})
            
            # Extract fields
            summary = fields.get("summary", "")
            issue_type = fields.get("issuetype", {}).get("name", "")
            status = fields.get("status", {}).get("name", "")
            assignee = fields.get("assignee", {})
            assignee_name = assignee.get("displayName", "") if assignee else ""
            priority = fields.get("priority", {})
            priority_name = priority.get("name", "") if priority else ""
            created = fields.get("created", "")
            updated = fields.get("updated", "")
            description = clean_html(fields.get("description", ""))
            
            # Parent information
            parent = fields.get("parent", {})
            parent_key = parent.get("key", "") if parent else ""
            parent_summary = parent.get("fields", {}).get("summary", "") if parent else ""
            
            all_issues.append({
                "Issue Key": key,
                "Issue ID": issue_id,
                "Summary": summary,
                "Issue Type": issue_type,
                "Status": status,
                "Assignee": assignee_name,
                "Priority": priority_name,
                "Created": created,
                "Updated": updated,
                "Parent Key": parent_key,
                "Parent Summary": parent_summary,
                "Description": description
            })
        
        # Check if we need to fetch more
        if start_at + len(issues) >= total:
            break
        
        start_at += max_results
    
    # Write to CSV
    csv_file = "greymatter_subtasks.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "Issue Key", "Issue ID", "Summary", "Issue Type", "Status",
            "Assignee", "Priority", "Created", "Updated",
            "Parent Key", "Parent Summary", "Description"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_issues)
    
    print(f"\n✅ CSV exported successfully: {csv_file}")
    print(f"Total issues exported: {len(all_issues)}")


if __name__ == "__main__":
    main()
