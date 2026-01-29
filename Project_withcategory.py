import requests
import csv

# CONFIGURATION
JIRA_BASE_URL = "https://work.greyorange.com/jira"
API_ENDPOINT = "/rest/api/2/project"
BEARER_TOKEN = "YOUR_TOKEN"
OUTPUT_CSV = "jira_projects_with_typefinal.csv"

def fetch_projects():
    url = f"{JIRA_BASE_URL}{API_ENDPOINT}"
    headers = {
        "Authorization": f"Bearer {BEARER_TOKEN}",
        "Accept": "application/json"
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

def extract_project_data(projects_json):
    data = []
    for proj in projects_json:
        name = proj.get("name", "")
        key = proj.get("key", "")
        category = proj.get("projectCategory", {}).get("name", "No Category")
        project_type = proj.get("projectTypeKey", "Unknown")
        data.append({
            "Name": name,
            "Key": key,
            "Category": category,
            "Type": project_type
        })
    return data

def write_csv(project_data, output_file):
    with open(output_file, mode='w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=["Name", "Key", "Category", "Type"])
        writer.writeheader()
        for proj in project_data:
            writer.writerow(proj)
    print(f"Wrote {len(project_data)} projects to {output_file}")

def main():
    try:
        projects = fetch_projects()
        project_data = extract_project_data(projects)
        write_csv(project_data, OUTPUT_CSV)
    except requests.HTTPError as e:
        print(f"HTTP error occurred: {e} — Response content: {e.response.text}")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
