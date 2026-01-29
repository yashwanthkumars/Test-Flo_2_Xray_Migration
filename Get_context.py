import requests
import csv

# --- CONFIGURATION ---
URL = "https://work-uat.greyorange.com/jira/rest/internal/2/field/customfield_12401/context"
TOKEN = "YOUR_TOKEN"
OUTPUT_FILE = "jira_context_export.csv"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

def export_context_to_csv():
    try:
        print("Fetching data from Jira...")
        response = requests.get(URL, headers=headers)
        response.raise_for_status()
        data = response.json()

        with open(OUTPUT_FILE, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            
            # Updated Headers to include Project ID and Single Issue Type ID
            writer.writerow([
                "Context_ID", 
                "Context_Name",
                "Project_ID",        # Added
                "Project_Key", 
                "Project_Name", 
                "Is_All_Issue_Types",
                "Single_Issue_Type_ID", # Added: Only populated if context has exactly 1 issue type
                "All_Specific_Issue_Types", 
                "Project_Lead"
            ])

            for context in data:
                c_id = context.get('id')
                c_name = context.get('name')
                is_all = context.get('allIssueTypes', False)
                
                # Logic for Issue Types
                it_list = context.get('issueTypes', [])
                
                # Column: Single_Issue_Type_ID
                # Populated only if allIssueTypes is False AND there is exactly one issue type
                single_it_id = ""
                if not is_all and len(it_list) == 1:
                    single_it_id = it_list[0].get('id')

                # Column: All_Specific_Issue_Types (Full list for reference)
                all_it_details = ""
                if not is_all:
                    all_it_details = ", ".join([f"{it.get('name')} ({it.get('id')})" for it in it_list])
                else:
                    all_it_details = "ALL"

                projects = context.get('projects', [])
                for project in projects:
                    writer.writerow([
                        c_id,
                        c_name,
                        project.get('id'),      # Project ID
                        project.get('key'),
                        project.get('name'),
                        "Yes" if is_all else "No",
                        single_it_id,           # Single ID column
                        all_it_details,
                        project.get('lead', {}).get('displayName', 'N/A')
                    ])

        print(f"Successfully exported data to {OUTPUT_FILE}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    export_context_to_csv()