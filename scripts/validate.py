"""
validate.py — validates all request JSON files before pushing to CM360.
Exits 1 on any error, blocking the pipeline.
"""
import json, sys, zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
REQUESTS_DIR = ROOT / "requests"
ASSETS_DIR = REQUESTS_DIR / "assets"
SITES = {s["name"]: s["id"] for s in json.loads((ROOT / "config/sites.json").read_text())["sites"]}
ADVERTISERS = {a["name"]: a["id"] for a in json.loads((ROOT / "config/advertisers.json").read_text())["advertisers"]}
CAMPAIGNS = {c["id"]: c for c in json.loads((ROOT / "config/campaigns.json").read_text())["campaigns"]}
PICKLIST = json.loads((ROOT / "config/picklist.json").read_text())
VALID_DIMS = set(PICKLIST["dimensions"])
VALID_FUNNEL = set(PICKLIST["funnelStages"])
VALID_TAGS = {"TrackingAd", "Standard", "StaticClickTracker", "DynamicClickTracker"}
DATE_FMT = "%d/%m/%Y"
errors = []

def err(rid, field, msg): errors.append(f"  [Row {rid}] {field}: {msg}")

def validate(path):
    try: data = json.loads(path.read_text())
    except Exception as e: errors.append(f"  [{path.name}] JSON parse error: {e}"); return

    rid = data.get("rowId", path.stem)

    for f in ["client","campaignId","advertiserId","siteId","medium","format",
              "tagType","dimensions","startDate","endDate","funnelStage",
              "country","landingPage","destinationUrl","placementName","adName",
              "requesterEmail"]:
        if not str(data.get(f, "")).strip():
            err(rid, f, "Required field missing")

    if data.get("site") and data["site"] not in SITES:
        err(rid, "site", f"'{data['site']}' not in sites.json")

    if data.get("tagType") and data["tagType"] not in VALID_TAGS:
        err(rid, "tagType", f"'{data['tagType']}' is not valid")

    if data.get("dimensions") and data["dimensions"] not in VALID_DIMS:
        err(rid, "dimensions", f"'{data['dimensions']}' not recognised")

    try:
        s = datetime.strptime(data.get("startDate",""), DATE_FMT)
        e = datetime.strptime(data.get("endDate",""), DATE_FMT)
        if e <= s: err(rid, "endDate", "End date must be after start date")
    except ValueError:
        err(rid, "dates", "Dates must be DD/MM/YYYY")

    for u in ["landingPage","destinationUrl"]:
        v = data.get(u,"")
        if v and not v.startswith(("http://","https://")):
            err(rid, u, "Must start with http:// or https://")

    tag_type = data.get("tagType","")
    if tag_type == "Standard":
        asset = data.get("assetFilename","").strip()
        if not asset:
            err(rid, "assetFilename", "Standard ads require a creative file")
        else:
            ap = ASSETS_DIR / str(rid) / asset
            if not ap.exists():
                err(rid, "assetFilename", f"File '{asset}' not found in requests/assets/{rid}/")
            else:
                ext = Path(asset).suffix.lower()
                kb = ap.stat().st_size / 1024
                if ext == ".zip":
                    if kb > 500: err(rid, "assetFilename", f"{kb:.0f}KB exceeds 500KB HTML5 limit")
                    try:
                        with zipfile.ZipFile(ap) as z:
                            if "index.html" not in z.namelist():
                                err(rid, "assetFilename", "HTML5 zip must contain index.html at root")
                    except: err(rid, "assetFilename", "Not a valid zip file")
                elif ext in (".jpg",".jpeg",".png",".gif"):
                    if kb > 200: err(rid, "assetFilename", f"{kb:.0f}KB exceeds 200KB display limit")
                else:
                    err(rid, "assetFilename", f"Unsupported file type '{ext}'")

    if tag_type == "TrackingAd":
        if not data.get("trackingCreativeId") and not data.get("trackingCreativeName"):
            err(rid, "trackingCreative", "Must provide either an existing creative ID or a new creative name")

def main():
    files = sorted(REQUESTS_DIR.glob("*.json"))
    if not files: print("No request files found."); sys.exit(1)
    print(f"\nValidating {len(files)} request(s)...\n")
    for f in files: validate(f)
    print("=" * 60)
    if errors:
        print(f"FAILED — {len(errors)} error(s):\n")
        for e in errors: print(e)
        print(); sys.exit(1)
    else:
        print(f"All {len(files)} request(s) valid ✓\n"); sys.exit(0)

if __name__ == "__main__": main()
