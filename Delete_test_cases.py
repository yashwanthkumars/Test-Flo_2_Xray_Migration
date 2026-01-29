import requests
from requests.auth import HTTPBasicAuth
import json
 
# Jira Cloud URL
JIRA_URL = 'https://greyorange-work-sandbox-test.atlassian.net'  # Replace with your Jira domain
API_TOKEN = 'YOUR_TOKEN'  # Replace with your API token
USER_EMAIL = 'yashwanth.k@padahsolutions.com'  # Replace with your email address
HEADERS = {
    'Content-Type': 'application/json',
}
 
# List of issue keys to delete
ISSUE_KEYS = ['GM-249457','GM-249458','GM-249458','GM-249458','GM-249458','GM-249458','GM-249458','GM-249459','GM-249459','GM-249459','GM-249459','GM-249460','GM-249460','GM-249460','GM-249460','GM-249460','GM-249460','GM-249461','GM-249461','GM-249462','GM-249462','GM-249462','GM-249463','GM-249463','GM-249463','GM-249464','GM-249464','GM-249465','GM-249465','GM-249465','GM-249465','GM-249465','GM-249466','GM-249467','GM-249467','GM-249468','GM-249469','GM-249469','GM-249469','GM-249470','GM-249471','GM-249471','GM-249471','GM-249472','GM-249472','GM-249473','GM-249473','GM-249473','GM-249473','GM-249474','GM-249474','GM-249475','GM-249475','GM-249475','GM-249475','GM-249476','GM-249476','GM-249476','GM-249476','GM-249477','GM-249477','GM-249478','GM-249478','GM-249478','GM-249478','GM-249478','GM-249478','GM-249478','GM-249479','GM-249479','GM-249479','GM-249479','GM-249479','GM-249479','GM-249479','GM-249480','GM-249481','GM-249481','GM-249481','GM-249481','GM-249481','GM-249481','GM-249482','GM-249482','GM-249482','GM-249482','GM-249482','GM-249482','GM-249482','GM-249483','GM-249483','GM-249483','GM-249484','GM-249484','GM-249484','GM-249485','GM-249485','GM-249485','GM-249485','GM-249485','GM-249485','GM-249485','GM-249486','GM-249486','GM-249487','GM-249487','GM-249487','GM-249487','GM-249487','GM-249487','GM-249487','GM-249488','GM-249488','GM-249488','GM-249488','GM-249488','GM-249488','GM-249488','GM-249489','GM-249489','GM-249489','GM-249489','GM-249489','GM-249490','GM-249491','GM-249491','GM-249492','GM-249492','GM-249492','GM-249492','GM-249493','GM-249493','GM-249494','GM-249494','GM-249494','GM-249495','GM-249495','GM-249495','GM-249496','GM-249496','GM-249496','GM-249497','GM-249497','GM-249497','GM-249497','GM-249498','GM-249498','GM-249498','GM-249499','GM-249499','GM-249500','GM-249500','GM-249500','GM-249500','GM-249501','GM-249501','GM-249501','GM-249501','GM-249502','GM-249502','GM-249503','GM-249503','GM-249504','GM-249505','GM-249505','GM-249505','GM-249505','GM-249506','GM-249506','GM-249506','GM-249507','GM-249507','GM-249507','GM-249507','GM-249507','GM-249507','GM-249507']  # Replace with your issue keys
 
def delete_issue(issue_key):
    url = f'{JIRA_URL}/rest/api/3/issue/{issue_key}'
   
    # Send DELETE request to Jira Cloud REST API
    response = requests.delete(
        url,
        headers=HEADERS,
        auth=HTTPBasicAuth(USER_EMAIL, API_TOKEN)
    )
 
    # Check the response
    if response.status_code == 204:
        print(f"Issue {issue_key} deleted successfully.")
    else:
        print(f"Failed to delete issue {issue_key}: {response.status_code}, {response.text}")
 
def main():
    for issue_key in ISSUE_KEYS:
        delete_issue(issue_key)
 
if __name__ == "__main__":
    main()
 
 