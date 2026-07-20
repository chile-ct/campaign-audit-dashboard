"""
Campaign Audit Dashboard — Auto Update Script
Queries BigQuery directly. No Claude/Anthropic API involved. $0 token cost.
Refreshes:
  1. The rolling 30-day funnel/campaign/spend snapshot (data/live-snapshot.json).
  2. The CURRENT CALENDAR MONTH's monthly breakdown (data/monthly-snapshot.json) —
     only the current month is re-queried each run (cheap, ~1 month of data); past
     months are already finalized and are carried forward untouched. When a new
     calendar month starts, its key is simply added on top — nothing is deleted.
The "save" metric (DAU w/ Save) is NOT re-queried daily (source query is ~28GB) —
it is carried forward from the previous snapshot.
"""
import json, os, datetime
from google.cloud import bigquery

PROJECT = "chotot-dwh"
DATA_JSON = os.path.join(os.path.dirname(__file__), '..', 'data', 'live-snapshot.json')
MONTHLY_JSON = os.path.join(os.path.dirname(__file__), '..', 'data', 'monthly-snapshot.json')
VERTICALS = ['pty', 'veh', 'gds', 'jobs']

client = bigquery.Client(project=PROJECT)


def run(sql):
    return [dict(r) for r in client.query(sql).result()]


print("Loading previous snapshot for save-metric carry-forward...")
old = {}
if os.path.exists(DATA_JSON):
    with open(DATA_JSON) as f:
        old = json.load(f)

old_summary = old.get('summary', {})
save_map = {}
for v in VERTICALS:
    for row in old.get('campaigns', {}).get(v, []):
        save_map[row[0]] = row[3]

print("Querying BigQuery (funnel summary)...")
funnel_rows = run("""
WITH base AS (
  SELECT v.clientId AS clientId, v.channelGrouping AS channelGrouping, cat.category_id AS category_id,
         cat.adview_count AS adview_count, cat.lead_count AS lead_count
  FROM `chotot-dwh.chotot_data.traffic_visit_detail` v, UNNEST(v.category) cat
  WHERE v.date BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY) AND CURRENT_DATE()
    AND v.channelGrouping IN ('Paid Search','Display')
    AND v.is_bot IS NOT TRUE
),
mapped AS (
  SELECT b.*, d.metric_layer_vertical AS vertical
  FROM base b LEFT JOIN `chotot-dwh.dim.d_category` d ON SAFE_CAST(b.category_id AS INT64) = d.category
)
SELECT vertical AS vertical, channelGrouping AS channelGrouping,
  COUNT(DISTINCT clientId) AS dau,
  COUNT(DISTINCT CASE WHEN adview_count > 0 THEN clientId END) AS dau_w_adview,
  COUNT(DISTINCT CASE WHEN lead_count > 0 THEN clientId END) AS dau_w_lead,
  SUM(lead_count) AS total_lead
FROM mapped WHERE vertical IS NOT NULL
GROUP BY vertical, channelGrouping
""")
print(f"  {len(funnel_rows)} rows (expect 8)")

print("Querying BigQuery (campaign detail)...")
campaign_rows = run("""
WITH base AS (
  SELECT v.clientId AS clientId, v.channelGrouping AS channelGrouping, v.campaign AS campaign,
         cat.category_id AS category_id, cat.adview_count AS adview_count, cat.lead_count AS lead_count
  FROM `chotot-dwh.chotot_data.traffic_visit_detail` v, UNNEST(v.category) cat
  WHERE v.date BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY) AND CURRENT_DATE()
    AND v.channelGrouping IN ('Paid Search','Display')
    AND v.is_bot IS NOT TRUE
),
mapped AS (
  SELECT b.*, d.metric_layer_vertical AS vertical
  FROM base b LEFT JOIN `chotot-dwh.dim.d_category` d ON SAFE_CAST(b.category_id AS INT64) = d.category
)
SELECT vertical AS vertical, channelGrouping AS channelGrouping, campaign AS campaign,
  COUNT(DISTINCT clientId) AS dau,
  COUNT(DISTINCT CASE WHEN adview_count > 0 THEN clientId END) AS dau_w_adview,
  COUNT(DISTINCT CASE WHEN lead_count > 0 THEN clientId END) AS dau_w_lead,
  SUM(lead_count) AS total_lead
FROM mapped WHERE vertical IS NOT NULL
GROUP BY vertical, channelGrouping, campaign
HAVING dau >= 100
ORDER BY vertical, channelGrouping, dau DESC
""")
print(f"  {len(campaign_rows)} rows")

print("Querying BigQuery (spend)...")
spend_rows = run("""
SELECT campaign AS campaign, SUM(lead_daily) AS total_lead, SUM(spend_vnd) AS spend_vnd
FROM `chotot-dwh.ct_digital.kiet_digital_campaign_daily`
WHERE date BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY) AND CURRENT_DATE()
GROUP BY campaign
HAVING spend_vnd > 0
""")
print(f"  {len(spend_rows)} rows")

# ---- sanity checks: never push obviously broken data ----
if len(funnel_rows) < 4 or len(campaign_rows) < 50 or len(spend_rows) < 20:
    raise SystemExit(
        f"Sanity check failed (funnel={len(funnel_rows)}, campaigns={len(campaign_rows)}, "
        f"spend={len(spend_rows)}) — refusing to overwrite live-snapshot.json"
    )

# ---- assemble summary ----
summary = {v: {
    "Display": {"dau": 0, "save": 0, "adview": 0, "lead": 0, "totalLead": 0},
    "Paid Search": {"dau": 0, "save": 0, "adview": 0, "lead": 0, "totalLead": 0},
} for v in VERTICALS}
for r in funnel_rows:
    v, ch = r['vertical'], r['channelGrouping']
    if v not in summary:
        continue
    old_save = old_summary.get(v, {}).get(ch, {}).get('save', 0)
    summary[v][ch] = {
        "dau": int(r['dau']), "save": old_save,
        "adview": int(r['dau_w_adview']), "lead": int(r['dau_w_lead']),
        "totalLead": int(r['total_lead'] or 0),
    }

# ---- assemble campaigns ----
campaigns = {v: [] for v in VERTICALS}
for r in campaign_rows:
    v = r['vertical']
    if v not in campaigns:
        continue
    save = save_map.get(r['campaign'], 0)
    campaigns[v].append([
        r['campaign'], r['channelGrouping'], int(r['dau']), save,
        int(r['dau_w_adview']), int(r['dau_w_lead']), int(r['total_lead'] or 0),
    ])
for v in VERTICALS:
    campaigns[v].sort(key=lambda row: row[2], reverse=True)

# ---- assemble spend ----
spend_last30 = {}
for r in spend_rows:
    if r['spend_vnd'] is None:
        continue
    spend_last30[r['campaign']] = {
        "lead": int(r['total_lead']) if r['total_lead'] is not None else 0,
        "spend": round(r['spend_vnd']),
    }

out = {
    "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "window_days": 30,
    "summary": summary,
    "campaigns": campaigns,
    "spend_last30": spend_last30,
}

os.makedirs(os.path.dirname(DATA_JSON), exist_ok=True)
with open(DATA_JSON, 'w') as f:
    json.dump(out, f)

total_dau = sum(summary[v][ch]['dau'] for v in VERTICALS for ch in ("Display", "Paid Search"))
print(f"OK data/live-snapshot.json updated — total DAU across verticals: {total_dau:,}")

# ==========================================================================
# MONTHLY SNAPSHOT — refresh only the current calendar month (cheap, ~1 month
# of data). Past months don't change once finalized, so they're carried
# forward untouched from the existing file instead of being re-queried.
# ==========================================================================
today = datetime.datetime.now(datetime.timezone.utc).date()
current_ym = today.strftime('%Y-%m')

print(f"Loading previous monthly snapshot ({MONTHLY_JSON})...")
monthly = {}
if os.path.exists(MONTHLY_JSON):
    with open(MONTHLY_JSON) as f:
        monthly = json.load(f)
monthly.setdefault('monthly_summary', {})
monthly.setdefault('monthly_campaigns', {})
monthly.setdefault('spend_by_month', {})

print(f"Querying BigQuery (monthly funnel summary, {current_ym} MTD)...")
month_funnel_rows = run("""
WITH base AS (
  SELECT v.clientId AS clientId, v.channelGrouping AS channelGrouping, cat.category_id AS category_id,
         cat.adview_count AS adview_count, cat.lead_count AS lead_count
  FROM `chotot-dwh.chotot_data.traffic_visit_detail` v, UNNEST(v.category) cat
  WHERE v.date BETWEEN DATE_TRUNC(CURRENT_DATE(), MONTH) AND CURRENT_DATE()
    AND v.channelGrouping IN ('Paid Search','Display')
    AND v.is_bot IS NOT TRUE
),
mapped AS (
  SELECT b.*, d.metric_layer_vertical AS vertical
  FROM base b LEFT JOIN `chotot-dwh.dim.d_category` d ON SAFE_CAST(b.category_id AS INT64) = d.category
)
SELECT vertical AS vertical, channelGrouping AS channelGrouping,
  COUNT(DISTINCT clientId) AS dau,
  COUNT(DISTINCT CASE WHEN adview_count > 0 THEN clientId END) AS dau_w_adview,
  COUNT(DISTINCT CASE WHEN lead_count > 0 THEN clientId END) AS dau_w_lead,
  SUM(lead_count) AS total_lead
FROM mapped WHERE vertical IS NOT NULL
GROUP BY vertical, channelGrouping
""")
print(f"  {len(month_funnel_rows)} rows")

print(f"Querying BigQuery (monthly campaign detail, {current_ym} MTD)...")
month_campaign_rows = run("""
WITH base AS (
  SELECT v.clientId AS clientId, v.channelGrouping AS channelGrouping, v.campaign AS campaign,
         cat.category_id AS category_id, cat.adview_count AS adview_count, cat.lead_count AS lead_count
  FROM `chotot-dwh.chotot_data.traffic_visit_detail` v, UNNEST(v.category) cat
  WHERE v.date BETWEEN DATE_TRUNC(CURRENT_DATE(), MONTH) AND CURRENT_DATE()
    AND v.channelGrouping IN ('Paid Search','Display')
    AND v.is_bot IS NOT TRUE
),
mapped AS (
  SELECT b.*, d.metric_layer_vertical AS vertical
  FROM base b LEFT JOIN `chotot-dwh.dim.d_category` d ON SAFE_CAST(b.category_id AS INT64) = d.category
)
SELECT vertical AS vertical, channelGrouping AS channelGrouping, campaign AS campaign,
  COUNT(DISTINCT clientId) AS dau,
  COUNT(DISTINCT CASE WHEN adview_count > 0 THEN clientId END) AS dau_w_adview,
  COUNT(DISTINCT CASE WHEN lead_count > 0 THEN clientId END) AS dau_w_lead,
  SUM(lead_count) AS total_lead
FROM mapped WHERE vertical IS NOT NULL
GROUP BY vertical, channelGrouping, campaign
HAVING dau >= 100
ORDER BY vertical, channelGrouping, dau DESC
""")
print(f"  {len(month_campaign_rows)} rows")

print(f"Querying BigQuery (monthly spend, {current_ym} MTD)...")
month_spend_rows = run("""
SELECT campaign AS campaign, SUM(lead_daily) AS total_lead, SUM(spend_vnd) AS spend_vnd
FROM `chotot-dwh.ct_digital.kiet_digital_campaign_daily`
WHERE date BETWEEN DATE_TRUNC(CURRENT_DATE(), MONTH) AND CURRENT_DATE()
GROUP BY campaign
HAVING spend_vnd > 0
""")
print(f"  {len(month_spend_rows)} rows")

# ---- sanity check: never let a broken/partial query corrupt monthly history ----
if len(month_funnel_rows) < 4 or len(month_campaign_rows) < 10:
    raise SystemExit(
        f"Monthly sanity check failed (funnel={len(month_funnel_rows)}, "
        f"campaigns={len(month_campaign_rows)}) — refusing to overwrite monthly-snapshot.json"
    )

# ---- assemble current-month summary (Save not available per-month, same as before) ----
month_summary_entry = {v: {
    "Display": {"dau": 0, "save": 0, "adview": 0, "lead": 0, "totalLead": 0},
    "Paid Search": {"dau": 0, "save": 0, "adview": 0, "lead": 0, "totalLead": 0},
} for v in VERTICALS}
for r in month_funnel_rows:
    v, ch = r['vertical'], r['channelGrouping']
    if v not in month_summary_entry:
        continue
    month_summary_entry[v][ch] = {
        "dau": int(r['dau']), "save": 0,
        "adview": int(r['dau_w_adview']), "lead": int(r['dau_w_lead']),
        "totalLead": int(r['total_lead'] or 0),
    }
monthly['monthly_summary'][current_ym] = month_summary_entry

# ---- assemble current-month campaigns (format matches existing MONTH_CAMPAIGNS rows) ----
month_campaigns_entry = {v: [] for v in VERTICALS}
for r in month_campaign_rows:
    v = r['vertical']
    if v not in month_campaigns_entry:
        continue
    month_campaigns_entry[v].append([
        r['campaign'], r['channelGrouping'], int(r['dau']),
        int(r['dau_w_adview']), int(r['dau_w_lead']), int(r['total_lead'] or 0),
    ])
for v in VERTICALS:
    month_campaigns_entry[v].sort(key=lambda row: row[2], reverse=True)
monthly['monthly_campaigns'][current_ym] = month_campaigns_entry

# ---- assemble current-month spend ----
month_spend_entry = {}
for r in month_spend_rows:
    if r['spend_vnd'] is None:
        continue
    month_spend_entry[r['campaign']] = {
        "lead": int(r['total_lead']) if r['total_lead'] is not None else 0,
        "spend": round(r['spend_vnd']),
    }
monthly['spend_by_month'][current_ym] = month_spend_entry

monthly['current_month'] = current_ym
monthly['current_month_through'] = today.isoformat()
monthly['generated_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()

os.makedirs(os.path.dirname(MONTHLY_JSON), exist_ok=True)
with open(MONTHLY_JSON, 'w') as f:
    json.dump(monthly, f)

month_dau = sum(month_summary_entry[v][ch]['dau'] for v in VERTICALS for ch in ("Display", "Paid Search"))
print(f"OK data/monthly-snapshot.json updated — {current_ym} MTD DAU across verticals: {month_dau:,} "
      f"(months on file: {sorted(monthly['monthly_summary'].keys())})")
