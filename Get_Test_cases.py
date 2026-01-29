# import requests

# GRAPHQL_URL = "https://xray.cloud.getxray.app/api/v2/graphql"
# TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0ZW5hbnQiOiIxMWZjNmFiYS0xMmYwLTNmZjEtYTM2Ni0yYzU0N2QzYWY1NTgiLCJhY2NvdW50SWQiOiI3MTIwMjA6MjRiMmYwMGEtMzZhOC00Njk4LThkODgtMDc5Y2QzZjVmYjg2IiwiaXNYZWEiOmZhbHNlLCJpYXQiOjE3NjYxMzcwNjAsImV4cCI6MTc2NjIyMzQ2MCwiYXVkIjoiQjUzNTdEOTAyRTMwNEU1NUIwNThGRjQ4NTJGMUYxQjIiLCJpc3MiOiJjb20ueHBhbmRpdC5wbHVnaW5zLnhyYXkiLCJzdWIiOiJCNTM1N0Q5MDJFMzA0RTU1QjA1OEZGNDg1MkYxRjFCMiJ9._Lx84rA-4266iHSE51YfZOo5rNYM6Fgt5jiCFX47Pjk"

# query = """
# {
#   getTests(jql: "project = GreyMatter", limit: 100) {
#     total
#     results {
#       issueId
#       jira(fields: ["key", "summary", "issuetype"])
#     }
#   }
# }
# """

# response = requests.post(
#     GRAPHQL_URL,
#     json={"query": query},
#     headers={
#         "Authorization": f"Bearer {TOKEN}",
#         "Content-Type": "application/json"
#     }
# )

# # print(response.json())

# if "data" in response.json():
#     print(f"issues keys: {[issue['jira']['key'] for issue in response.json()['data']['getTests']['results']]}")



# ====================================================================



import requests
import csv
from datetime import datetime
from time import sleep
import json

GRAPHQL_URL = "https://xray.cloud.getxray.app/api/v2/graphql"
TOKEN = "YOUR_TOKEN"

JQL = "project = GreyMatter"
PAGE_SIZE = 100

# Rate limit settings
REQUEST_DELAY = 0.5  # Delay between requests (seconds)
MAX_RETRIES = 3  # Maximum retry attempts
RETRY_DELAY = 5  # Initial retry delay (seconds)


def fetch_page_with_retry(query, attempt=1):
    """Fetch a single page with retry logic for rate limits."""
    try:
        # Add delay between requests
        sleep(REQUEST_DELAY)
        
        response = requests.post(
            GRAPHQL_URL,
            json={"query": query},
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json"
            },
            timeout=60
        )
        
        # Log response details
        print(f"🔍 Response Status Code: {response.status_code}")
        
        data = response.json()
        
        # Log the full response for debugging
        print(f"🔍 Response Data: {json.dumps(data, indent=2)[:500]}...")  # First 500 chars
        
        # Check for rate limit errors
        if "errors" in data:
            error_msg = str(data.get("errors", []))
            print(f"🔍 Error detected: {error_msg}")
            if "Too many requests" in error_msg or "rate limit" in error_msg.lower():
                if attempt <= MAX_RETRIES:
                    wait_time = RETRY_DELAY * (2 ** (attempt - 1))  # Exponential backoff
                    print(f"⚠️ Rate limited. Retrying in {wait_time}s (attempt {attempt}/{MAX_RETRIES})...")
                    sleep(wait_time)
                    return fetch_page_with_retry(query, attempt + 1)
                else:
                    print(f"❌ Max retries exceeded")
                    return None
            else:
                print(f"❌ Error: {data['errors']}")
                return None
        
        return data
        
    except Exception as e:
        print(f"🔍 Exception caught: {type(e).__name__}: {e}")
        if attempt <= MAX_RETRIES:
            wait_time = RETRY_DELAY * (2 ** (attempt - 1))
            print(f"⚠️ Exception: {e}. Retrying in {wait_time}s...")
            sleep(wait_time)
            return fetch_page_with_retry(query, attempt + 1)
        print(f"❌ Failed after {MAX_RETRIES} retries: {e}")
        return None


def get_tests_paginated(jql, page_size=100):
    """Fetch all test cases with pagination and rate limit handling."""
    all_tests = []
    start = 0
    total = None
    page = 1
    consecutive_failures = 0
    max_consecutive_failures = 3

    while True:
        query = f"""
        {{
          getTests(jql: "{jql}", limit: {page_size}, start: {start}) {{
            total
            results {{
              issueId
              jira(fields: ["key", "summary", "issuetype"])
            }}
          }}
        }}
        """
        data = fetch_page_with_retry(query)
        
        if not data:
            consecutive_failures += 1
            print(f"⚠️ Failed to fetch page {page} (data is None). Consecutive failures: {consecutive_failures}/{max_consecutive_failures}")
            if consecutive_failures >= max_consecutive_failures:
                print("❌ Too many consecutive failures. Stopping.")
                break
            # Skip this page and try the next one
            start += page_size
            page += 1
            continue

        # Log data structure for debugging
        print(f"🔍 Data keys: {list(data.keys())}")
        if "data" in data:
            print(f"🔍 data.data keys: {list(data['data'].keys()) if data['data'] else 'data is None'}")
        
        if "data" not in data or "getTests" not in data["data"]:
            consecutive_failures += 1
            print(f"⚠️ Invalid response structure on page {page}.")
            print(f"🔍 Expected 'data.getTests' but got: {data}")
            print(f"⚠️ Consecutive failures: {consecutive_failures}/{max_consecutive_failures}")
            if consecutive_failures >= max_consecutive_failures:
                print("❌ Too many consecutive failures. Stopping.")
                break
            # Skip this page and try the next one
            start += page_size
            page += 1
            continue1
            continue

        # Reset consecutive failures on success
        consecutive_failures = 0
        
        tests = data["data"]["getTests"]["results"]
        total = data["data"]["getTests"]["total"]

        if not tests:
            print(f"⚠️ No tests returned on page {page}, but continuing...")
            start += page_size
            page += 1
            # Continue if we haven't reached the total yet
            if total and len(all_tests) >= total:
                break
            continue

        all_tests.extend(tests)
        print(f"✔ Page {page}: Retrieved {len(tests)} tests (Total: {len(all_tests)}/{total})")

        start += page_size
        page += 1

        if total and len(all_tests) >= total:
            print(f"✅ Reached total count. Stopping.")
            break

    return all_tests


def export_to_csv(tests):
    """Export test cases to CSV."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_file = f"xray_test_cases_{ts}.csv"

    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["Issue ID", "Issue Key", "Summary", "Issue Type"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for test in tests:
            writer.writerow({
                "Issue ID": test.get("issueId", ""),
                "Issue Key": test["jira"].get("key", ""),
                "Summary": test["jira"].get("summary", ""),
                "Issue Type": test["jira"].get("issuetype", "")
            })

    print(f"\n✔ CSV exported: {csv_file}")
    return csv_file


if __name__ == "__main__":
    print(f"Fetching test cases for: {JQL}")
    tests = get_tests_paginated(JQL, PAGE_SIZE)
    print(f"\n📊 Total tests retrieved: {len(tests)}")
    
    if tests:
        export_to_csv(tests)
    else:
        print("❌ No tests found")