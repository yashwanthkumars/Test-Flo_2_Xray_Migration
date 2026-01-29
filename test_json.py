import json
import pandas as pd

# Test what json.dumps does with numbers
test_values = [0, 1, 11909, 50]

for val in test_values:
    payload = json.dumps({
        "fields": {
            "customfield_10356": val
        }
    })
    print(f"Value: {val}")
    print(f"Payload: {payload}")
    print(f"Type in payload: {type(json.loads(payload)['fields']['customfield_10356'])}")
    print()
