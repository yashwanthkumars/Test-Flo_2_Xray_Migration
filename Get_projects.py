import requests
import csv

# CONFIGURATION — set your values here
JIRA_BASE_URL = "https://work.greyorange.com/jira"
API_ENDPOINT = "/rest/api/2/project"
BEARER_TOKEN = "YOUR_TOKEN"  # Replace with your actual Bearer token
OUTPUT_CSV = "jira_projects.csv"

def fetch_projects():
    url = f"{JIRA_BASE_URL}{API_ENDPOINT}"
    headers = {
        "Authorization": f"Bearer {BEARER_TOKEN}",
        "Accept": "application/json"
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()  # will raise an exception for HTTP errors

    return response.json()

def extract_project_names(projects_json):
    # The API should return a list of project objects; each has e.g. "name"
    names = []
    for proj in projects_json:
        # adjust key if different name field
        name = proj.get("name")
        if name:
            names.append(name)
        else:
            # fallback if name field is different
            names.append(proj.get("key", ""))
    return names

def write_csv(names, output_file):
    with open(output_file, mode='w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        # header
        writer.writerow(["ProjectName"])
        # each row
        for nm in names:
            writer.writerow([nm])
    print(f"Wrote {len(names)} projects to {output_file}")

def main():
    try:
        projects = fetch_projects()
        project_names = extract_project_names(projects)
        write_csv(project_names, OUTPUT_CSV)
    except requests.HTTPError as e:
        print(f"HTTP error occurred: {e} — Response content: {e.response.text}")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
