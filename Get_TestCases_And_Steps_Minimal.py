import requests
import csv
import html
import re
import logging
from datetime import datetime
import time
import argparse

# ---------------- CONFIGURATION ----------------
JIRA_BASE_URL = "https://work-uat.greyorange.com"
JIRA_USERNAME = "yashwanth.k@padahsolutions.com"
JIRA_API_TOKEN = "YOUR_TOKEN"
JQL_QUERY = 'issuekey in ("GM-196970","GM-196969","GM-196968","GM-196967","GM-196965","GM-196961","GM-196962","GM-196960","GM-196958","GM-196959","GM-196841","GM-196034","GM-196015","GM-195973","GM-195970","GM-195968","GM-195964","GM-195966","GM-195962","GM-195960","GM-195958","GM-195955","GM-195954","GM-195951","GM-195949","GM-195946","GM-195943","GM-195945","GM-195941","GM-195942","GM-195940","GM-195938","GM-195860","GM-195700","GM-195585","GM-195576","GM-195338","GM-195335","GM-195334","GM-195333","GM-195329","GM-195327","GM-195328","GM-195326","GM-195324","GM-195323","GM-195322","GM-195321","GM-195319","GM-195317","GM-195316","GM-195315","GM-195314","GM-195312","GM-195313","GM-195311","GM-195310","GM-195309")'
# JQL_QUERY = 'key in ("GM-255416","GM-253450","GM-253267","GM-252505","GM-249823","GM-249456","GM-246080","GM-245039","GM-243611","GM-243447","GM-243446","GM-242740","GM-242671","GM-242344","GM-242339","GM-240876","GM-239810","GM-239246","GM-239198","GM-238106","GM-237983","GM-237905","GM-237842","GM-237263","GM-236318","GM-236213","GM-235886","GM-235438","GM-235173","GM-235015","GM-234532","GM-234078","GM-233252","GM-233137","GM-232991","GM-232958","GM-232806","GM-232757","GM-232446","GM-232429","GM-232350","GM-231502","GM-230233","GM-230232","GM-229861","GM-229029","GM-228664","GM-227064","GM-226893","GM-225768")'
# ------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.FileHandler('get_testcases_steps_minimal_uatv3.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def clean_html(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]*>", "", text)
    return text.strip()


def _get_with_retry(url, auth, params, max_retries=5, backoff_base=1.5):
    """GET with retry/backoff on transient errors (429/5xx/504)."""
    attempt = 0
    while True:
        try:
            resp = requests.get(url, auth=auth, params=params, timeout=60)
            if resp.status_code in (429, 500, 502, 503, 504):
                raise requests.exceptions.HTTPError(f"{resp.status_code} Error", response=resp)
            resp.raise_for_status()
            return resp
        except requests.exceptions.HTTPError as e:
            attempt += 1
            if attempt > max_retries:
                raise
            sleep_s = backoff_base ** attempt
            code = getattr(e, 'response', None).status_code if getattr(e, 'response', None) else 'HTTP'
            logger.warning(f"{code} - retry {attempt}/{max_retries} in {sleep_s:.1f}s")
            time.sleep(sleep_s)
        except requests.exceptions.RequestException as e:
            attempt += 1
            if attempt > max_retries:
                raise
            sleep_s = backoff_base ** attempt
            logger.warning(f"{e.__class__.__name__} - retry {attempt}/{max_retries} in {sleep_s:.1f}s")
            time.sleep(sleep_s)


def get_testcases_with_steps(jql: str, start_index: int | None = None, end_index: int | None = None, page_size: int = 100):
    """Run JQL and return issues in the requested index range (0-based, inclusive).
    Only fetch the fields we need: 'issuetype' and 'customfield_15416'.
    """
    url = f"{JIRA_BASE_URL}/jira/rest/api/2/search"
    auth = (JIRA_USERNAME, JIRA_API_TOKEN)
    all_issues = []
    cursor = start_index if (start_index is not None and start_index >= 0) else 0
    end_limit = end_index if (end_index is not None and end_index >= 0) else None
    total = None

    while True:
        if end_limit is not None:
            remaining = end_limit - cursor + 1
            if remaining <= 0:
                break
            max_results = max(1, min(page_size, remaining))
        else:
            max_results = page_size

        params = {
            "jql": jql,
            "fields": "issuetype,customfield_15416",
            "expand": "renderedFields",
            "startAt": cursor,
            "maxResults": max_results,
        }
        logger.info(f"Fetching issues: startAt={cursor}, maxResults={max_results}")
        resp = _get_with_retry(url, auth, params)
        data = resp.json()

        issues = data.get("issues", [])
        if total is None:
            total = data.get("total", 0)

        if not issues:
            break

        all_issues.extend(issues)
        logger.info(f"Retrieved {len(issues)} issues (Accumulated {len(all_issues)}/{total})")

        cursor += len(issues)
        if cursor >= total:
            break

    logger.info(f"Range fetch completed: {len(all_issues)} issues returned (total={total})")
    return all_issues


def extract_steps(issue: dict):
    fields = issue.get("fields", {})
    cf = fields.get("customfield_15416", {})
    steps_rows = []

    if isinstance(cf, dict):
        steps_rows = cf.get("stepsRows", []) or []

    steps = []
    for i, step in enumerate(steps_rows, start=1):
        status_name = (step.get("status", {}) or {}).get("name", "")
        cells = step.get("cells", []) or []
        rendered_cells = step.get("renderedCells", []) or []
        raw_cells = rendered_cells or cells

        clean_cells = [clean_html(c) for c in raw_cells]
        if len(clean_cells) >= 3:
            steps.append({
                "#": i,
                "Action": clean_cells[0],
                "Input": clean_cells[1],
                "Expected result": clean_cells[2],
                "Status": status_name,
            })
    return steps


essential_headers = [
    "IssueKey", "Issue Type", "#", "Action", "Input", "Expected result", "Status"
]


def export_testcases_and_steps(jql: str, start_index: int | None = None, end_index: int | None = None):
    issues = get_testcases_with_steps(jql, start_index=start_index, end_index=end_index)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = (
        f"_{start_index}_{end_index}" if (start_index is not None and end_index is not None) else ""
    )
    csv_file = f"testcases_steps_minimal_uatv1{suffix}_{ts}.csv"
    rows_written = 0

    logger.info(f"Writing CSV: {csv_file}")
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=essential_headers)
        writer.writeheader()

        for issue in issues:
            key = issue.get("key", "")
            issue_type = (issue.get("fields", {})
                          .get("issuetype", {})
                          .get("name", ""))

            steps = extract_steps(issue)

            if steps:
                for step in steps:
                    writer.writerow({
                        "IssueKey": key,
                        "Issue Type": issue_type,
                        **step,
                    })
                    rows_written += 1
            else:
                # No steps: still output a row for this Test Case
                writer.writerow({
                    "IssueKey": key,
                    "Issue Type": issue_type,
                    "#": "",
                    "Action": "",
                    "Input": "",
                    "Expected result": "",
                    "Status": "No Steps",
                })
                rows_written += 1

    logger.info(f"CSV export completed: {csv_file} (rows: {rows_written})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export GreyMatter Test Case steps in ranges")
    parser.add_argument("--start", type=int, default=None, help="0-based start index of issues to export")
    parser.add_argument("--end", type=int, default=None, help="0-based end index of issues to export (inclusive)")
    args = parser.parse_args()

    start_idx = args.start
    end_idx = args.end

    if (start_idx is not None) ^ (end_idx is not None):
        raise SystemExit("Provide both --start and --end, or neither.")

    export_testcases_and_steps(JQL_QUERY, start_index=start_idx, end_index=end_idx)
