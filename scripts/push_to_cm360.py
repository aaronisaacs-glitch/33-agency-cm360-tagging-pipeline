"""
push_to_cm360.py
----------------
Reads validated request JSON files, creates placements in CM360,
uploads creatives where needed, generates tags, and writes results
to outputs/results.json for the dashboard and tag distribution.

Auth: Workload Identity Federation via GOOGLE_APPLICATION_CREDENTIALS
"""

import json
import os
import sys
import mimetypes
from datetime import datetime
from pathlib import Path

from google.oauth2 import credentials as oauth2_credentials
import google.auth
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ROOT = Path(__file__).parent.parent
REQUESTS_DIR = ROOT / "requests"
ASSETS_DIR = REQUESTS_DIR / "assets"
OUTPUTS_DIR = ROOT / "outputs"
TAGS_DIR = ROOT / "tags"
OUTPUTS_DIR.mkdir(exist_ok=True)
TAGS_DIR.mkdir(exist_ok=True)

SCOPES = ["https://www.googleapis.com/auth/dfatrafficking"]

def get_service():
    creds, _ = google.auth.default(scopes=SCOPES)
    return build("dfareporting", "v3.5", credentials=creds)

def get_profile_id(service):
    profiles = service.userProfiles().list().execute()
    return profiles["items"][0]["profileId"]

def format_date(date_str):
    """DD/MM/YYYY → MM/DD/YYYY for CM360"""
    try:
        d, m, y = date_str.split("/")
        return f"{m}/{d}/{y}"
    except:
        return date_str

def format_datetime(date_str, time="08:00 AM"):
    return f"{format_date(date_str)} {time}"

def get_or_create_tracking_creative(service, profile_id, advertiser_id, creative_id, creative_name, width, height):
    """Return existing creative ID or create a new tracking creative."""
    if creative_id:
        return creative_id

    body = {
        "advertiserId": advertiser_id,
        "name": creative_name,
        "type": "TRACKING_TEXT",
        "size": {"width": int(width), "height": int(height)},
    }
    created = service.creatives().insert(profileId=profile_id, body=body).execute()
    print(f"  ✓ Created tracking creative: {creative_name} (ID: {created['id']})")
    return created["id"]

def upload_standard_creative(service, profile_id, advertiser_id, name, asset_path, width, height, click_url):
    """Upload a display image or HTML5 creative."""
    ext = Path(asset_path).suffix.lower()
    mime = "application/zip" if ext == ".zip" else (mimetypes.guess_type(str(asset_path))[0] or "image/jpeg")
    asset_type = "HTML" if ext == ".zip" else "HTML_IMAGE"

    media = MediaFileUpload(str(asset_path), mimetype=mime)
    asset_meta = {"assetIdentifier": {"name": Path(asset_path).name, "type": asset_type}}
    uploaded = service.creativeAssets().insert(
        advertiserId=advertiser_id,
        profileId=profile_id,
        body=asset_meta,
        media_body=media
    ).execute()

    body = {
        "advertiserId": advertiser_id,
        "name": name,
        "type": "DISPLAY",
        "size": {"width": int(width), "height": int(height)},
        "creativeAssets": [{"assetIdentifier": uploaded["assetIdentifier"], "role": "PRIMARY"}],
        "clickTags": [{"name": "clickTag", "eventName": "exit",
                       "clickThroughUrl": {"customClickThroughUrl": click_url}}]
    }
    created = service.creatives().insert(profileId=profile_id, body=body).execute()
    print(f"  ✓ Uploaded standard creative: {name} (ID: {created['id']})")
    return created["id"]

def create_placement(service, profile_id, data, creative_id):
    """Create a placement in CM360 and return placement ID + tags."""
    dims = data["dimensions"].split("x")
    width, height = (dims[0], dims[1]) if len(dims) == 2 else ("1", "1")
    tag_type = data["tagType"]

    ad_type_map = {
        "TrackingAd": "TRACKING",
        "Standard": "STANDARD",
        "StaticClickTracker": "CLICK_TRACKER",
        "DynamicClickTracker": "CLICK_TRACKER",
    }

    placement_body = {
        "advertiserId": data["advertiserId"],
        "campaignId": data["campaignId"],
        "siteId": data["siteId"],
        "name": data["placementName"],
        "startDate": format_date(data["startDate"]),
        "endDate": format_date(data["endDate"]),
        "size": {"width": int(width), "height": int(height)},
        "compatibility": "DISPLAY",
        "paymentSource": "PLACEMENT_AGENCY_PAID",
        "pricingSchedule": {
            "pricingType": data.get("pricingType", "PRICING_TYPE_CPM"),
            "startDate": format_date(data["startDate"]),
            "endDate": format_date(data["endDate"]),
        },
        "tagFormats": ["PLACEMENT_TAG_STANDARD", "PLACEMENT_TAG_JAVASCRIPT",
                       "PLACEMENT_TAG_IFRAME_JAVASCRIPT", "PLACEMENT_TAG_CLICK_COMMANDS"]
    }

    placement = service.placements().insert(
        profileId=profile_id, body=placement_body
    ).execute()
    placement_id = placement["id"]
    print(f"  ✓ Created placement: {data['placementName']} (ID: {placement_id})")

    # Associate creative with campaign
    service.campaignCreativeAssociations().insert(
        profileId=profile_id,
        campaignId=data["campaignId"],
        body={"creativeId": creative_id}
    ).execute()

    # Create ad
    start_dt = format_datetime(data["startDate"], "08:00 AM")
    end_dt = format_datetime(data["endDate"], "11:59 PM")
    ad_body = {
        "advertiserId": data["advertiserId"],
        "campaignId": data["campaignId"],
        "name": data["adName"],
        "type": ad_type_map.get(tag_type, "TRACKING"),
        "active": True,
        "startTime": start_dt,
        "endTime": end_dt,
        "placementAssignments": [{"placementId": placement_id, "active": True}],
        "creativeRotation": {
            "creativeAssignments": [{"creativeId": creative_id, "active": True,
                                     "clickThroughUrl": {"customClickThroughUrl": data.get("destinationUrl", "")}}],
            "type": "CREATIVE_ROTATION_TYPE_RANDOM",
            "weightCalculationStrategy": "WEIGHT_STRATEGY_EQUAL"
        },
        "deliverySchedule": {"hardCutoff": False, "priority": "AD_PRIORITY_15"},
        "clickThroughUrl": {"customClickThroughUrl": data.get("destinationUrl", "")},
    }

    ad = service.ads().insert(profileId=profile_id, body=ad_body).execute()
    print(f"  ✓ Created ad: {data['adName']} (ID: {ad['id']})")

    # Generate tags
    tag_response = service.placements().generatetags(
        profileId=profile_id,
        campaignId=data["campaignId"],
        placementIds=[placement_id],
        tagFormats=["PLACEMENT_TAG_STANDARD", "PLACEMENT_TAG_JAVASCRIPT",
                    "PLACEMENT_TAG_IFRAME_JAVASCRIPT", "PLACEMENT_TAG_CLICK_COMMANDS"]
    ).execute()

    tag_data = tag_response.get("placementTags", [{}])[0].get("tagDatas", [{}])[0]

    return {
        "placementId": placement_id,
        "adId": ad["id"],
        "creativeId": creative_id,
        "impressionTagImage": tag_data.get("impressionTag", ""),
        "impressionTagJs": tag_data.get("impressionTag", ""),
        "clickTag": tag_data.get("clickTag", ""),
    }

def push():
    service = get_service()
    profile_id = get_profile_id(service)

    request_files = sorted(REQUESTS_DIR.glob("*.json"))
    if not request_files:
        print("No request files found.")
        sys.exit(1)

    results = []
    campaign_tags = {}  # group tags by campaign for distribution

    for req_file in request_files:
        data = json.loads(req_file.read_text())
        req_id = str(data.get("rowId", req_file.stem))
        tag_type = data["tagType"]
        advertiser_id = data["advertiserId"]
        campaign_id = data["campaignId"]
        dims = data["dimensions"].split("x")
        width, height = (dims[0], dims[1]) if len(dims) == 2 else ("1", "1")

        print(f"\n→ Processing row {req_id}: {data['placementName']}")

        try:
            # Resolve creative
            if tag_type == "TrackingAd":
                creative_id = get_or_create_tracking_creative(
                    service, profile_id, advertiser_id,
                    data.get("trackingCreativeId", ""),
                    data.get("trackingCreativeName", f"{data['jobNumber']}_tracking_ad"),
                    width, height
                )
            elif tag_type == "Standard":
                asset_path = ASSETS_DIR / req_id / data["assetFilename"]
                creative_id = upload_standard_creative(
                    service, profile_id, advertiser_id,
                    data["creativeName"], asset_path, width, height,
                    data.get("destinationUrl", "")
                )
            else:
                # Click trackers — no creative needed, use placeholder
                creative_id = None

            # Create placement + ad + generate tags
            tag_result = create_placement(service, profile_id, data, creative_id)

            result = {
                **data,
                **tag_result,
                "status": "live",
                "processedAt": datetime.utcnow().isoformat(),
                "error": ""
            }
            results.append(result)

            # Group by campaign for tag sheet
            camp_key = f"{data['client']}_{campaign_id}"
            if camp_key not in campaign_tags:
                campaign_tags[camp_key] = {
                    "client": data["client"],
                    "campaignName": data["campaignId"],
                    "campaignId": campaign_id,
                    "requesterEmail": data.get("requesterEmail", ""),
                    "placements": []
                }
            campaign_tags[camp_key]["placements"].append({
                "placementName": data["placementName"],
                "adName": data["adName"],
                "site": data["site"],
                "dimensions": data["dimensions"],
                "startDate": data["startDate"],
                "endDate": data["endDate"],
                "impressionTagImage": tag_result["impressionTagImage"],
                "impressionTagJs": tag_result["impressionTagJs"],
                "clickTag": tag_result["clickTag"],
                "placementId": tag_result["placementId"],
            })

        except Exception as e:
            print(f"  ✗ Failed: {e}")
            results.append({**data, "status": "failed", "error": str(e), "processedAt": datetime.utcnow().isoformat()})

    # Write results for dashboard
    results_path = OUTPUTS_DIR / "results.json"
    existing = []
    if results_path.exists():
        existing = json.loads(results_path.read_text())
    existing.extend(results)
    results_path.write_text(json.dumps(existing, indent=2, default=str))
    print(f"\n✓ Results written to outputs/results.json")

    # Write tag files per campaign
    for camp_key, camp_data in campaign_tags.items():
        tag_path = TAGS_DIR / f"tags_{camp_key}.json"
        tag_path.write_text(json.dumps(camp_data, indent=2))
    print(f"✓ Tag files written to tags/")

    failures = sum(1 for r in results if r.get("status") == "failed")
    if failures:
        print(f"\n{failures} placement(s) failed — check logs above.")
        sys.exit(1)

if __name__ == "__main__":
    push()
