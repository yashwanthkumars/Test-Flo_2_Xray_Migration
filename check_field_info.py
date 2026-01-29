import requests
import json

JIRA_URL = 'https://work-uat.greyorange.com/jira'
TOKEN = 'YOUR_TOKEN'

headers = {
    'Authorization': f'Bearer {TOKEN}',
    'Content-Type': 'application/json'
}

# Get field schema
resp = requests.get(f'{JIRA_URL}/rest/api/2/field', headers=headers)
fields = resp.json()

for field in fields:
    if field['id'] == 'customfield_11401':
        print('Field customfield_11401 Details:')
        print(f"Name: {field.get('name')}")
        print(f"Type: {field.get('type')}")
        print(f"Schema: {json.dumps(field.get('schema'), indent=2)}")
        print("\n--- Full Field Info ---")
        print(json.dumps(field, indent=2))
        break
