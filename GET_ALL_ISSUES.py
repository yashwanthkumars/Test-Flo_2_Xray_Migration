import requests
import csv
import logging

# ---------------- CONFIGURATION ----------------
JIRA_BASE_URL = "https://work.greyorange.com"  # Replace with your Jira Server URL
JIRA_USERNAME = "yashwanth.k@padahsolutions.com"  # Your Jira username
JIRA_API_TOKEN = "Pr0j#ct@JCM!2526"  # Your Jira API token (or password if using basic auth)


# Setup logging to print to the terminal
logging.basicConfig(
    level=logging.INFO,  # Log all levels INFO and above
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler()  # Output logs to the console (terminal)
    ]
)

def get_all_issues():
    """Fetch all issues from Jira instance using pagination."""
    url = f"{JIRA_BASE_URL}/jira/rest/api/2/search"
    auth = (JIRA_USERNAME, JIRA_API_TOKEN)
    params = {
        "jql": "order by created",  # You can modify this query if needed
        "fields": "key,issuetype,project",  # Retrieve only necessary fields
        "maxResults": 50  # Maximum number of issues per request (you can adjust this number)
    }

    all_issues = []
    start_at = 0

    logging.info("Starting to fetch issues from Jira.")

    while True:
        params["startAt"] = start_at  # Specify where to start the next page of results
        try:
            response = requests.get(url, auth=auth, params=params)
            response.raise_for_status()  # Raise error for invalid responses
            data = response.json()
            issues = data.get("issues", [])
            all_issues.extend(issues)
            logging.info(f"Fetched {len(issues)} issues starting from {start_at}.")

            # If fewer than 50 issues are returned, we've reached the last page
            if len(issues) < 50:
                logging.info("No more issues to fetch. Reached last page.")
                break
            start_at += 50  # Move to the next page

        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching issues: {e}")
            break

    logging.info(f"Total issues fetched: {len(all_issues)}.")
    return all_issues

def extract_issue_data(issue_json):
    """Extract necessary information from issue JSON."""
    key = issue_json.get("key", "")
    issuetype = issue_json.get("fields", {}).get("issuetype", {}).get("name", "")
    project_name = issue_json.get("fields", {}).get("project", {}).get("name", "")
    
    return {
        "Issue Key": key,
        "Issue Type": issuetype,
        "Project Name": project_name
    }

def main():
    logging.info("Script started.")

    # Fetch all issues from Jira
    all_issues = get_all_issues()
    if not all_issues:
        logging.warning("No issues found in Jira.")
        return

    logging.info("Extracting issue data.")
    # Extract the relevant data for each issue
    issue_data = [extract_issue_data(issue) for issue in all_issues]

    logging.info("Writing data to CSV file.")
    # Write the data to CSV
    csv_file = "jira_all_issuesRun1.csv"
    try:
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            fieldnames = ["Issue Key", "Issue Type", "Project Name"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(issue_data)
        logging.info(f"CSV file exported successfully: {csv_file}")
    except Exception as e:
        logging.error(f"Error writing to CSV file: {e}")

    logging.info("Script completed.")

if __name__ == "__main__":
    main()