import requests
import json

BASE_URL = "https://work-uat.greyorange.com/jira"
TOKEN = "YOUR_TOKEN"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

# Get all fields to find asset field type
url = f"{BASE_URL}/rest/api/2/field"
response = requests.get(url, headers=headers)

if response.status_code == 200:
    fields = response.json()
    
    # Look for your existing asset fields
    print("=== Looking for Asset Fields ===\n")
    asset_fields = []
    
    for field in fields:
        field_id = field.get('id', '')
        # Check if it's one of your new asset fields
        if field_id in ['customfield_17210', 'customfield_17211', 'customfield_17221', 'customfield_17222']:
            schema = field.get('schema', {})
            print(f"Field: {field.get('name')}")
            print(f"  ID: {field_id}")
            print(f"  Type: {schema.get('type')}")
            print(f"  Custom Type: {schema.get('custom')}")
            print(f"  Custom ID: {schema.get('customId')}")
            print(f"  Full Schema: {json.dumps(schema, indent=2)}")
            print("-" * 60)
            asset_fields.append(schema.get('custom'))
    
    if asset_fields:
        print(f"\n✓ Found asset field type: {asset_fields[0]}")
    else:
        print("\n⚠ No asset fields found. Searching for 'asset' or 'object' in all custom fields...")
        for field in fields:
            if field.get('custom') and ('asset' in field.get('name', '').lower() or 
                                       'object' in str(field.get('schema', {})).lower()):
                schema = field.get('schema', {})
                print(f"\nField: {field.get('name')} ({field.get('id')})")
                print(f"  Custom Type: {schema.get('custom')}")
else:
    print(f"Error: {response.status_code} - {response.text}")
