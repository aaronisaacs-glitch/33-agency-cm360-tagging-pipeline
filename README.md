# CM360 Tagging Pipeline

Fully automated end-to-end tagging pipeline. Biddable team submits requests via the form → you review and approve → pipeline creates placements in CM360, generates tags, and emails them to the biddable team.

---

## How it works

```
Form submission → JSON downloaded → Added to requests/ → PR opened
→ GitHub Actions validates → You review and merge
→ Pipeline authenticates to GCP → Creates placements in CM360
→ Uploads creatives (Standard ads) → Generates tags
→ Emails clean tag sheet to biddable team → Dashboard updates
```

---

## Repo structure

```
├── public/
│   ├── index.html          ← Tag request form (GitHub Pages)
│   └── dashboard.html      ← Trafficking log (GitHub Pages)
├── requests/
│   ├── *.json              ← One file per placement request
│   └── assets/{rowId}/     ← Creative files for Standard ads
├── outputs/
│   ├── results.json        ← All processed results (feeds dashboard)
│   └── Tags_*.xlsx         ← Generated tag sheets
├── tags/
│   └── tags_*.json         ← Interim tag files (auto-archived after send)
├── scripts/
│   ├── validate.py
│   ├── push_to_cm360.py
│   └── distribute_tags.py
├── config/
│   ├── advertisers.json    ← client name → CM360 advertiser ID
│   ├── campaigns.json      ← campaign name → CM360 campaign ID
│   ├── sites.json          ← site name → CM360 site ID
│   └── picklist.json       ← all dropdown values
└── .github/workflows/
    └── pipeline.yml
```

---

## GitHub Secrets required

| Secret | Value |
|--------|-------|
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | `projects/841934241994/locations/global/workloadIdentityPools/github-actions/providers/github` |
| `GCP_SERVICE_ACCOUNT` | `cm360-tagging-pipeline@phrasal-datum-499508-j9.iam.gserviceaccount.com` |
| `SENDGRID_API_KEY` | Your SendGrid API key |
| `FROM_EMAIL` | The sending email address (e.g. `tagging@youragency.com`) |
| `BIDDABLE_TEAM_EMAIL` | Biddable team email or distribution list |

---

## Enabling email (SendGrid)

1. Sign up at sendgrid.com (free tier: 100 emails/day)
2. Go to Settings → API Keys → Create API Key (Full Access)
3. Add the key as `SENDGRID_API_KEY` in GitHub Secrets
4. Add `FROM_EMAIL` and `BIDDABLE_TEAM_EMAIL` secrets

---

## Adding new clients / campaigns / sites

**New advertiser:**
Edit `config/advertisers.json` and add:
```json
{ "name": "NewClient", "id": "CM360_ADVERTISER_ID" }
```
Then add to the client dropdown in `public/index.html`.

**New campaign:**
Edit `config/campaigns.json` and add:
```json
{
  "name": "2026_NEWCLIENT_CAMPAIGN",
  "id": "CM360_CAMPAIGN_ID",
  "advertiserName": "NewClient",
  "label": "NewClient — Campaign Name 2026"
}
```

**New site:**
Edit `config/sites.json` and add:
```json
{ "name": "NewSite.com", "id": "CM360_SITE_ID", "label": "New Site", "utmSource": "NewSite" }
```
Then add to the site dropdown in `public/index.html`.

---

## Hosting the form (GitHub Pages)

1. Go to repo Settings → Pages
2. Source: Deploy from branch → `main` → `/public`
3. Share the URL with the biddable team

---

## The review flow

1. Biddable team fills in the form and submits — JSON files are downloaded
2. They add the JSON files (and any creative assets) to a PR
3. GitHub Actions validates everything automatically
4. You review the PR — check the placement names in the preview
5. Merge → pipeline runs → tags sent to biddable team automatically
6. Dashboard updates with live/ended status based on dates
