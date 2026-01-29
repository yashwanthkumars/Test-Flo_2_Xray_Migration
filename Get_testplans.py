import requests
import csv
from datetime import datetime
from time import sleep
import json

GRAPHQL_URL = "https://xray.cloud.getxray.app/api/v2/graphql"
TOKEN = "YOUR_TOKEN"

JQL = 'issuetype = "Test Plan"'
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


def get_testplans_paginated(jql, page_size=100):
    """Fetch all test plans with pagination and rate limit handling."""
    all_plans = []
    start = 0
    total = None
    page = 1
    consecutive_failures = 0
    max_consecutive_failures = 3

    while True:
        # Escape quotes in JQL for GraphQL
        escaped_jql = jql.replace('"', '\\"')
        
        query = f"""
        {{
          getTestPlans(jql: "{escaped_jql}", limit: {page_size}, start: {start}) {{
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
        
        if "data" not in data or "getTestPlans" not in data["data"]:
            consecutive_failures += 1
            print(f"⚠️ Invalid response structure on page {page}.")
            print(f"🔍 Expected 'data.getTestPlans' but got: {data}")
            print(f"⚠️ Consecutive failures: {consecutive_failures}/{max_consecutive_failures}")
            if consecutive_failures >= max_consecutive_failures:
                print("❌ Too many consecutive failures. Stopping.")
                break
            # Skip this page and try the next one
            start += page_size
            page += 1
            continue

        # Reset consecutive failures on success
        consecutive_failures = 0
        
        plans = data["data"]["getTestPlans"]["results"]
        total = data["data"]["getTestPlans"]["total"]

        if not plans:
            print(f"⚠️ No test plans returned on page {page}.")
            # If we have a total and already retrieved all, stop
            if total is not None and len(all_plans) >= total:
                print(f"✅ All {len(all_plans)} test plans retrieved. Stopping.")
                break
            # If no total or haven't reached it, but got empty results, stop pagination
            if total == 0 or (total is not None and start >= total):
                print(f"✅ Pagination complete. Stopping.")
                break
            # Otherwise, might be a temporary issue, try next page
            start += page_size
            page += 1
            continue

        all_plans.extend(plans)
        print(f"✔ Page {page}: Retrieved {len(plans)} test plans (Total: {len(all_plans)}/{total})")

        start += page_size
        page += 1

        if total is not None and len(all_plans) >= total:
            print(f"✅ Reached total count ({total}). Stopping.")
            break

    return all_plans


def export_to_csv(plans):
    """Export test plans to CSV."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_file = f"xray_test_plans_{ts}.csv"

    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["Issue ID", "Issue Key", "Summary", "Issue Type"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for plan in plans:
            writer.writerow({
                "Issue ID": plan.get("issueId", ""),
                "Issue Key": plan["jira"].get("key", ""),
                "Summary": plan["jira"].get("summary", ""),
                "Issue Type": plan["jira"].get("issuetype", "")
            })

    print(f"\n✔ CSV exported: {csv_file}")
    return csv_file


if __name__ == "__main__":
    print(f"Fetching test plans for: {JQL}")
    plans = get_testplans_paginated(JQL, PAGE_SIZE)
    print(f"\n📊 Total test plans retrieved: {len(plans)}")
    
    if plans:
        export_to_csv(plans)
    else:
        print("❌ No test plans found")

