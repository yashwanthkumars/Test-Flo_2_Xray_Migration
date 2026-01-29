import requests
import csv
import logging

# ---------------- CONFIGURATION ----------------
JIRA_BASE_URL = "https://work.greyorange.com"  # Replace with your Jira Server URL
JIRA_USERNAME = "yashwanth.k@padahsolutions.com"  # Your Jira username
JIRA_API_TOKEN = "Pr0j#ct@JCM!2526"  # Your Jira API token (or password if using basic auth)

# Setup logging to print to the terminal
logging.basicConfig(
    level=logging.DEBUG,  # Log all levels DEBUG and above (for more detailed logs)
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]  # Output logs to the console (terminal)
)

def get_all_issues(start_at, max_results):
    """Fetch issues from Jira instance using pagination."""
    url = f"{JIRA_BASE_URL}/jira/rest/api/2/search"
    auth = (JIRA_USERNAME, JIRA_API_TOKEN)
    params = {
        "jql": "order by created",  # Modify this query if needed
        "fields": "key,issuetype,project",  # Retrieve only necessary fields
        "startAt": start_at,  # Starting point for this batch
        "maxResults": max_results  # Number of issues to fetch per request (1000 per request)
    }

    all_issues = []

    logging.info(f"Starting to fetch issues from Jira, starting at {start_at}.")

    try:
        response = requests.get(url, auth=auth, params=params)
        response.raise_for_status()  # Raise error for invalid responses
        data = response.json()

        # Log the raw response for debugging
        # logging.debug(f"Raw response from Jira: {data}")

        issues = data.get("issues", [])
        all_issues.extend(issues)
        logging.info(f"Fetched {len(issues)} issues starting from {start_at}.")

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching issues: {e}")

    return all_issues

def extract_issue_data(issue_json):
    """Extract necessary information from issue JSON."""
    key = issue_json.get("key", "")
    issuetype = issue_json.get("fields", {}).get("issuetype", {}).get("name", "")
    project_name = issue_json.get("fields", {}).get("project", {}).get("name", "")
    
    # Log the extracted data for verification
    logging.debug(f"Extracted data: Issue Key: {key}, Issue Type: {issuetype}, Project Name: {project_name}")

    return {
        "Issue Key": key,
        "Issue Type": issuetype,
        "Project Name": project_name
    }

def write_to_csv(issue_data, filename):
    """Write extracted data to CSV file."""
    try:
        with open(filename, "w", newline="", encoding="utf-8") as f:
            fieldnames = ["Issue Key", "Issue Type", "Project Name"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(issue_data)
        logging.info(f"CSV file exported successfully: {filename}")
    except Exception as e:
        logging.error(f"Error writing to CSV file: {e}")

def fetch_issues_in_batches(total_count, batch_size):
    """Fetch issues in batches and write to CSV file."""
    all_issues = []
    start_at = 500001  # Start at 500001 and fetch in batches
    while start_at < total_count:
        logging.info(f"Fetching batch starting from {start_at} to {start_at + batch_size - 1}")
        issues = get_all_issues(start_at, batch_size)
        
        if not issues:
            logging.info("No more issues found.")
            break
        
        # Extend the all_issues list with the fetched batch
        all_issues.extend(issues)
        
        # Move to the next batch (startAt + batch_size)
        start_at += batch_size

    return all_issues

def main():
    logging.info("Script started.")

    total_count = 1000000  # Total issues to fetch (10 lakh issues)
    batch_size = 1000     # Fetch 1000 issues per request (Jira's max limit per API call)

    # Fetch issues in batches and store in all_issues
    all_issues = fetch_issues_in_batches(total_count, batch_size)
    
    if not all_issues:
        logging.warning("No issues fetched.")
        return

    logging.info("Extracting issue data.")
    # Extract the relevant data for each issue
    issue_data = [extract_issue_data(issue) for issue in all_issues]

    logging.info("Writing data to CSV file.")
    # Write the data to CSV
    csv_file = "jira_issues_500001-1000000.csv"  # Modify filename if you fetch more issues
    write_to_csv(issue_data, csv_file)

    logging.info("Script completed.")

if __name__ == "__main__":
    main()
