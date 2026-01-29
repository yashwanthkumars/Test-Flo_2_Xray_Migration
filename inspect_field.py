import requests
import json

# --- CONFIGURATION ---
JIRA_URL = "https://work-uat.greyorange.com/jira"
TOKEN = "YOUR_TOKEN"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

# Check the old field
old_field = "customfield_11401"
new_field = "customfield_17210"

print(f"=== Inspecting Old Field: {old_field} ===")
url = f"{JIRA_URL}/rest/api/2/field/{old_field}"
resp = requests.get(url, headers=headers)
if resp.status_code == 200:
    field_info = resp.json()
    print(json.dumps(field_info, indent=2))
else:
    print(f"Error: {resp.status_code} - {resp.text}")

print(f"\n=== Inspecting New Field: {new_field} ===")
url = f"{JIRA_URL}/rest/api/2/field/{new_field}"
resp = requests.get(url, headers=headers)
if resp.status_code == 200:
    field_info = resp.json()
    print(json.dumps(field_info, indent=2))
else:
    print(f"Error: {resp.status_code} - {resp.text}")

# Get a sample issue to see the value in context
print(f"\n=== Sample Issue with Old Field ===")
search_url = f"{JIRA_URL}/rest/api/2/search"
params = {
    "jql": f"cf[11401] is not EMPTY",
    "fields": f"key,{old_field},{new_field}",
    "maxResults": 1
}
resp = requests.get(search_url, headers=headers, params=params)
if resp.status_code == 200:
    data = resp.json()
    if data['issues']:
        issue = data['issues'][0]
        print(f"Issue: {issue['key']}")
        print(f"Old Field Value ({old_field}):")
        print(f"  Type: {type(issue['fields'].get(old_field)).__name__}")
        print(f"  Value: {json.dumps(issue['fields'].get(old_field), indent=2)}")
        print(f"New Field Value ({new_field}):")
        print(f"  Type: {type(issue['fields'].get(new_field)).__name__}")
        print(f"  Value: {json.dumps(issue['fields'].get(new_field), indent=2)}")
else:
    print(f"Error: {resp.status_code} - {resp.text}")
