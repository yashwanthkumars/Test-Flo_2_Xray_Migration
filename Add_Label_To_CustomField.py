import csv
import requests
import time
from datetime import datetime

# ---------------- CONFIG ----------------
JIRA_BASE_URL = "https://greyorange-work-sandbox-test.atlassian.net"
EMAIL = "yashwanth.k@padahsolutions.com"
#API_TOKEN = "YOUR_TOKEN"

CUSTOM_FIELD_ID = "customfield_10214"
LABEL_TO_ADD = "Xray_testPlan"

# Add your issue keys directly here
ISSUE_KEYS = [
    "GM-255416","GM-253450","GM-253267","GM-252505","GM-249823","GM-249456","GM-246080","GM-245039","GM-243611","GM-243447","GM-243446","GM-242740","GM-242671","GM-242344","GM-242339","GM-240876","GM-239810","GM-239246","GM-239198","GM-238106","GM-237983","GM-237905","GM-237842","GM-237263","GM-236318","GM-236213","GM-235886","GM-235438","GM-235173","GM-235015","GM-234532","GM-234078","GM-233252","GM-233137","GM-232991","GM-232958","GM-232806","GM-232757","GM-232446","GM-232429","GM-232350","GM-231502","GM-230233","GM-230232","GM-229861","GM-229029","GM-228664","GM-227064","GM-226893","GM-225768","GM-225745","GM-225724","GM-225691","GM-225668","GM-225541","GM-225240","GM-224477","GM-224461","GM-224049","GM-224022","GM-222955","GM-222223","GM-221026","GM-221025","GM-220544","GM-220461","GM-220460","GM-220458","GM-220305","GM-214503","GM-213695","GM-213582","GM-213373","GM-213173","GM-213169","GM-212870","GM-211876","GM-211736","GM-211735","GM-211716","GM-211715","GM-211714","GM-211355","GM-211243","GM-211034","GM-210543","GM-210463","GM-210349","GM-209853","GM-208320","GM-207942","GM-207527","GM-207493","GM-207492","GM-207491","GM-207429","GM-206747","GM-206154","GM-204089","GM-204080","GM-204038","GM-203806","GM-203595","GM-203593","GM-202855","GM-202785","GM-202632","GM-202631","GM-202575","GM-202545","GM-202436","GM-202296","GM-201914","GM-201888","GM-201874","GM-201873","GM-201659","GM-200002","GM-199599","GM-199530","GM-199524","GM-199352","GM-198628","GM-198535","GM-197951","GM-197849","GM-196913","GM-196906","GM-196185","GM-196010","GM-195936","GM-195340","GM-195308","GM-195307","GM-195213","GM-194246","GM-191197","GM-187550","GM-186413","GM-186182","GM-184399","GM-183349","GM-183074","GM-183014","GM-182452","GM-181591","GM-181437","GM-179433","GM-179186","GM-178703","GM-177349","GM-176912","GM-176626","GM-176562","GM-176269","GM-175996","GM-175865","GM-175561","GM-175278","GM-175210","GM-174927","GM-174774","GM-174661","GM-174641","GM-168793","GM-168461","GM-168169","GM-167995","GM-167731","GM-167699","GM-167698","GM-167309","GM-167078","GM-166703","GM-165916","GM-165721","GM-165492","GM-165453","GM-165451","GM-165100","GM-164587","GM-162010","GM-161885","GM-161572","GM-160880","GM-159771","GM-159521","GM-158757","GM-158481","GM-157791","GM-157195","GM-156945","GM-156476","GM-156214","GM-155764","GM-155679","GM-155414","GM-155252","GM-154297","GM-154296","GM-154290","GM-154262","GM-154259","GM-154144","GM-153755","GM-153685","GM-152848","GM-152660","GM-152014","GM-151043","GM-149617","GM-149415","GM-148751","GM-148630","GM-148629","GM-148322","GM-147857","GM-146685","GM-146424","GM-144093","GM-142831","GM-141832","GM-141720","GM-141362","GM-141169","GM-139730","GM-139573","GM-139178","GM-139177","GM-139146","GM-139145","GM-137850","GM-135642","GM-135213","GM-134523","GM-134522","GM-133568","GM-132665","GM-131504","GM-131228","GM-130921","GM-130848","GM-130847","GM-130839","GM-130784","GM-130732","GM-130704","GM-130697","GM-128943","GM-126305","GM-125776","GM-125624","GM-124074","GM-122956","GM-122515","GM-120961","GM-120423","GM-120239","GM-120238","GM-120237","GM-120095","GM-119659","GM-118209","GM-117136","GM-116182","GM-116181","GM-115597","GM-115591","GM-114330","GM-114307","GM-112856","GM-112809","GM-111333","GM-108510","GM-107838","GM-105232","GM-104780","GM-104676","GM-103967","GM-102739","GM-102738","GM-102587","GM-102492","GM-101871","GM-98468","GM-98123","GM-97322","GM-96137","GM-94670","GM-94446","GM-92881","GM-91419","GM-91412","GM-91408","GM-81218","GM-79268","GM-78844","GM-78488","GM-78279","GM-74895","GM-74581","GM-69269","GM-65328","GM-56077","GM-56074","GM-55995","GM-53646"
]

OUTPUT_CSV = f"label_add_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

# -----------------------------------------
# FUNCTIONS
# -----------------------------------------

def get_current_labels(issue_key):
    """Fetch current labels from the custom field for an issue."""
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}"
    
    try:
        response = requests.get(
            url,
            headers={"Accept": "application/json"},
            params={"fields": CUSTOM_FIELD_ID},
            auth=(EMAIL, API_TOKEN),
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            current_value = data.get("fields", {}).get(CUSTOM_FIELD_ID)
            
            # Custom field might be a string, list, or dict depending on field type
            if isinstance(current_value, list):
                return [item.get("value", item) if isinstance(item, dict) else item for item in current_value]
            elif isinstance(current_value, str):
                return [current_value] if current_value else []
            elif current_value is None:
                return []
            else:
                return [str(current_value)]
        else:
            print(f"❌ Failed to get current labels for {issue_key}: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Error fetching labels for {issue_key}: {e}")
        return None


def add_label_to_issue(issue_key):
    """Add the label to custom field 10214 for the given issue."""
    
    # First, get current labels
    current_labels = get_current_labels(issue_key)
    
    if current_labels is None:
        return {
            "issue_key": issue_key,
            "status": "FAILED",
            "message": "Could not retrieve current labels",
            "status_code": None
        }
    
    # Check if label already exists
    if LABEL_TO_ADD in current_labels:
        return {
            "issue_key": issue_key,
            "status": "SKIPPED",
            "message": "Label already exists",
            "status_code": 200
        }
    
    # Add the new label
    updated_labels = current_labels + [LABEL_TO_ADD]
    
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/{issue_key}"
    
    payload = {
        "fields": {
            CUSTOM_FIELD_ID: updated_labels
        }
    }
    
    try:
        response = requests.put(
            url,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json"
            },
            json=payload,
            auth=(EMAIL, API_TOKEN),
            timeout=30
        )
        
        if response.status_code == 204:
            return {
                "issue_key": issue_key,
                "status": "SUCCESS",
                "message": f"Label added successfully. Previous labels: {current_labels}",
                "status_code": 204
            }
        else:
            return {
                "issue_key": issue_key,
                "status": "FAILED",
                "message": f"Error: {response.text[:200]}",
                "status_code": response.status_code
            }
    except Exception as e:
        return {
            "issue_key": issue_key,
            "status": "ERROR",
            "message": str(e),
            "status_code": None
        }


def process_issue_keys():
    """Process issue keys from the ISSUE_KEYS list and add label to each."""
    
    results = []
    
    if not ISSUE_KEYS:
        print("❌ No issue keys found in ISSUE_KEYS list")
        print("   Please add issue keys to the ISSUE_KEYS list in the script")
        return
    
    print(f"✅ Processing {len(ISSUE_KEYS)} issue keys\n")
    
    for idx, issue_key in enumerate(ISSUE_KEYS, start=1):
        issue_key = issue_key.strip()
        
        if not issue_key:
            print(f"⚠️ Item {idx}: Skipping empty issue key")
            continue
        
        print(f"\n➡ [{idx}/{len(ISSUE_KEYS)}] Processing {issue_key}")
        
        result = add_label_to_issue(issue_key)
        results.append(result)
        
        status_emoji = "✅" if result["status"] == "SUCCESS" else "⚠️" if result["status"] == "SKIPPED" else "❌"
        print(f"{status_emoji} {result['status']}: {result['message']}")
        
        # Rate limiting
        time.sleep(0.5)
    
    # Write results to output CSV
    if results:
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["issue_key", "status", "message", "status_code"])
            writer.writeheader()
            writer.writerows(results)
        
        print(f"\n✅ Results saved to: {OUTPUT_CSV}")
        
        # Summary
        success_count = sum(1 for r in results if r["status"] == "SUCCESS")
        skipped_count = sum(1 for r in results if r["status"] == "SKIPPED")
        failed_count = sum(1 for r in results if r["status"] in ["FAILED", "ERROR"])
        
        print(f"\n📊 Summary:")
        print(f"   ✅ Success: {success_count}")
        print(f"   ⚠️ Skipped: {skipped_count}")
        print(f"   ❌ Failed: {failed_count}")
        print(f"   📝 Total: {len(results)}")


# -----------------------------------------
# MAIN
# -----------------------------------------

if __name__ == "__main__":
    print(f"🏷️  Adding label '{LABEL_TO_ADD}' to custom field {CUSTOM_FIELD_ID}")
    print(f"🔗 Jira Instance: {JIRA_BASE_URL}\n")
    
    process_issue_keys()
