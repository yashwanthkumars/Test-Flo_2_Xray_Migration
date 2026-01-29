# Jira DC to Xray Cloud Migration Guide

This README provides a step-by-step guide for migrating Test Plans and Test Cases from Jira Data Center (DC) to Xray Cloud, including batching, field mapping, workflow/screen changes, and validation.

---

## Table of Contents
1. Prerequisites
2. Export Test Plan Keys from Jira DC
3. Prepare Issue Keys for Batch Processing
4. Update and Run Migration Scripts
5. Manual Field and Workflow Changes
6. Validation and Post-Migration Steps
7. Troubleshooting & Tips

---

## 1. Prerequisites
- Access to Jira DC with required permissions
- Python 3.x installed
- Required Python packages installed (see requirements.txt if available)
- Access to Xray Cloud and API credentials
- Migration scripts present in this directory

---

## 2. Export Test Plan Keys from Jira DC
1. In Jira, go to **Issues > Search for Issues**.
2. Use JQL to filter Test Plans:
   ```
   issuetype = "Test Plan"
   ```
3. Export the results (Issue Key column) to Excel/CSV.

---

## 3. Prepare Issue Keys for Batch Processing
1. Copy the Issue Key column from Excel.
2. Paste into a new sheet, select the first 50 or 100 keys (as needed for batching).
3. Paste into Notepad.
4. Use Ctrl+H (Find/Replace):
   - Find: `\r\n` (or just line break)
   - Replace with: `,`
5. This converts the column to a comma-separated row.
6. Copy the result for use in the migration script.

---

## 4. Update and Run Migration Scripts
1. Open the relevant migration script (e.g., `GET_test_PLANSV2.py`).
2. Locate the line where issue keys are defined (usually a list or string variable).
3. Replace the old keys with your new comma-separated list.
4. Update log and result file names for each batch (e.g., `output_v1.json`, `output_v2.json`).
5. Save the file.
6. Ensure correct Jira URL and credentials are set.
7. Run the script in your terminal:
   ```
   python GET_test_PLANSV2.py
   ```
8. Repeat for each batch.

---

## 5. Manual Field and Workflow Changes
- Add dummy custom fields and labels to Test Plans manually (API/bulk edit may not be recognized by Xray).
- Adjust workflows and screens for each project as needed:
  - Move Test Cases to Test issue type.
  - Update screens to include all required fields.
  - Assign workflows to Test issue type and map statuses.

---

## 6. Validation and Post-Migration Steps
- After migration, use JQL to validate counts in both UI and script output.
- Generate Xray token and validate Test Plans in Xray Cloud.
- For field updates, use the provided scripts and ensure headers are correct (`Issue_key, Custom_fi`).
- Export and update field values as needed.

---

## 7. Troubleshooting & Tips
- Always check log files for errors.
- If you encounter gateway errors, reduce batch size.
- Double-check field mappings and workflow assignments.
- For any missing fields, export their values and update as required.

---

For further automation or help, refer to the scripts in this directory or contact the migration team.
