"""
Amendment 20: screening of the 10 October 2020 candidate. CATALOGUE QUERIES ONLY: no imagery pulled, no method run.
Rules are fixed in results/evaluation_protocol.md A20 (A10.2 unchanged). Tags in the output: [M] measured, [A] assumed, [E] estimate.

  PYTHONPATH=. python scripts/16_accra_candidate_2020_10_10_screening.py
"""
import csv
import datetime as dt
import importlib.util

import ee

from src.config import REPO_ROOT

_s = importlib.util.spec_from_file_location("m06", REPO_ROOT / "scripts" / "06_accra_run.py")
m06 = importlib.util.module_from_spec(_s)
_s.loader.exec_module(m06)
UTC = dt.timezone.utc
ts = lambda ms: dt.datetime.fromtimestamp(ms / 1000, UTC)
PEAK = dt.datetime(2020, 10, 10, 6, 0, tzinfo=UTC)      # ASSUMED (article gives no clock time)
W0, W1 = dt.datetime(2020, 10, 10, 0, 0, tzinfo=UTC), dt.datetime(2020, 10, 10, 12, 0, tzinfo=UTC)
hrs = lambda a, b: (a - b).total_seconds() / 3600

m06.ee_init()
aoi = m06.aoi_geometry()
aoi_area = aoi.area(1)

# ---- Step 2: Sentinel-1 IW GRD, all orbits, 2020-10-07 00:00 to 2020-10-15 23:59:59 UTC
s1 = (ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(aoi).filterDate("2020-10-07T00:00:00", "2020-10-16T00:00:00")
      .filter(ee.Filter.eq("instrumentMode", "IW")))
def meta(i):
    cov = ee.Number(i.geometry().intersection(aoi, 1).area(1)).divide(aoi_area)
    return ee.Feature(None, {"id": i.get("system:index"), "t": i.get("system:time_start"), "plat": i.get("platform_number"),
                             "pol": i.get("transmitterReceiverPolarisation"), "pass": i.get("orbitProperties_pass"),
                             "orbit": i.get("relativeOrbitNumber_start"), "cov": cov})
srows = sorted((f["properties"] for f in s1.map(meta).getInfo()["features"]), key=lambda p: p["t"])
rows = []
print(f"S1 IW GRD scenes intersecting the AOI, 2020-10-07 00:00 to 2020-10-15 23:59:59 UTC: {len(srows)}  [M]")
for p in srows:
    t = ts(p["t"])
    r = {"section": "S1_IW_GRD", "id": p["id"], "time_utc": t.isoformat(), "satellite": "S1" + p["plat"],
         "pass_or_instrument": p["pass"], "relative_orbit": p["orbit"], "polarisations": "+".join(p["pol"]),
         "aoi_fraction_in_footprint": round(p["cov"], 4), "hours_from_assumed_peak_0600": round(hrs(t, PEAK), 2),
         "hours_from_window_start_0000": round(hrs(t, W0), 2), "hours_from_window_end_1200": round(hrs(t, W1), 2),
         "within_24h_after_assumed_peak": 0 < hrs(t, PEAK) <= 24, "within_24h_after_0000": 0 < hrs(t, W0) <= 24,
         "within_24h_after_1200": 0 < hrs(t, W1) <= 24, "s2_aoi_cloud_fraction": "", "tag": "[M]"}
    rows.append(r)
    print(f"  {t:%Y-%m-%d %H:%M:%S} {r['satellite']} {p['pass']:10s} rel.orbit {p['orbit']:3d} {r['polarisations']:5s} AOI in footprint {p['cov']:.3f}  "
          f"{r['hours_from_assumed_peak_0600']:+8.2f} h from 06:00 | {r['hours_from_window_start_0000']:+8.2f} h from 00:00 | {r['hours_from_window_end_1200']:+8.2f} h from 12:00  {p['id']}")
for name, ref in (("assumed peak 2020-10-10T06:00 [A]", PEAK), ("window start 2020-10-10T00:00", W0), ("window end 2020-10-10T12:00", W1)):
    after = [p for p in srows if hrs(ts(p["t"]), ref) > 0]
    first = min(after, key=lambda p: p["t"]) if after else None
    ok = bool(first and hrs(ts(first["t"]), ref) <= 24)
    print(f"RULE (a) at {name}: " + (f"first scene after = {ts(first['t']):%Y-%m-%d %H:%M:%S} (+{hrs(ts(first['t']), ref):.2f} h) -> {'PASS' if ok else 'FAIL'}" if first else "no scene after -> FAIL"))
    rows.append({"section": "RULE_A_VERDICT", "id": name, "time_utc": ts(first["t"]).isoformat() if first else "",
                 "hours_from_assumed_peak_0600": round(hrs(ts(first["t"]), ref), 2) if first else "", "within_24h_after_assumed_peak": "PASS" if ok else "FAIL", "tag": "[M]"})

# ---- Step 3: Sentinel-2 SR HARMONIZED within +/- 3 days of the assumed peak, AOI-clipped SCL cloud fraction (classes 3, 8, 9, 10)
t0, t1 = PEAK - dt.timedelta(days=3), PEAK + dt.timedelta(days=3)
s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(aoi).filterDate(t0.isoformat(), t1.isoformat()))
def s2meta(i):
    scl = i.select("SCL")
    cloud = scl.eq(3).Or(scl.eq(8)).Or(scl.eq(9)).Or(scl.eq(10)).rename("cloud")
    r = cloud.addBands(scl.mask().rename("valid")).reduceRegion(reducer=ee.Reducer.mean(), geometry=aoi, scale=20, maxPixels=1e9)
    return ee.Feature(None, {"id": i.get("system:index"), "t": i.get("system:time_start"), "tile_cloud": i.get("CLOUDY_PIXEL_PERCENTAGE"),
                             "cloud": r.get("cloud"), "valid": r.get("valid")})
s2rows = sorted((f["properties"] for f in s2.map(s2meta).getInfo()["features"]), key=lambda p: p["t"])
print(f"\nS2_SR_HARMONIZED scenes intersecting the AOI within +/-3 days of {PEAK:%Y-%m-%d %H:%M} UTC [A peak]: {len(s2rows)}  [M]")
best = None
for p in s2rows:
    t = ts(p["t"])
    cf = p["cloud"]
    rows.append({"section": "S2_SR_HARMONIZED", "id": p["id"], "time_utc": t.isoformat(), "satellite": "", "pass_or_instrument": "MSI",
                 "hours_from_assumed_peak_0600": round(hrs(t, PEAK), 2), "aoi_fraction_in_footprint": round(p["valid"], 4) if p["valid"] is not None else "",
                 "s2_aoi_cloud_fraction": round(cf, 4) if cf is not None else "", "tile_cloud_pct_metadata": p["tile_cloud"],
                 "s2_below_20pct": (cf is not None and cf < 0.20), "tag": "[M]"})
    print(f"  {t:%Y-%m-%d %H:%M:%S} {hrs(t, PEAK):+7.2f} h  AOI-clipped cloud {100 * cf:6.2f}%  (tile-wide metadata {p['tile_cloud']:.1f}%)  valid SCL over AOI {p['valid']:.3f}  {p['id']}" if cf is not None
          else f"  {t:%Y-%m-%d %H:%M:%S} no SCL value over AOI  {p['id']}")
    if cf is not None and (best is None or cf < best[0]):
        best = (cf, t, p["id"])
n_ok = sum(1 for p in s2rows if p["cloud"] is not None and p["cloud"] < 0.20)
print(f"scenes below 20% AOI-clipped cloud: {n_ok}; lowest = " + (f"{100 * best[0]:.2f}% at {best[1]:%Y-%m-%d %H:%M} UTC" if best else "n/a"))

# ---- Step 3 (cont.): external references, one attempt each, no URL guessing (endpoints from A11.4; the DFO link is the site's own)
import html, json, re, urllib.request
UA = {"User-Agent": "sar-flood-student-project/1.0"}
def get(url, timeout=90):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()
def ext(name, status, detail):
    rows.append({"section": "RULE_B_EXTERNAL", "id": name, "pass_or_instrument": status, "polarisations": detail, "tag": "[M]"})
    print(f"{name}: {status} | {detail}")
try:
    items = json.loads(get("https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations-info/?limit=300"))
    items = items.get("results", items) if isinstance(items, dict) else items
    first_act = min(i["activationTime"] for i in items if i.get("activationTime"))
    oct20 = [i["code"] for i in items if (i.get("eventTime") or "").startswith("2020-10")]
    ghana = [i["code"] for i in items if "ghana" in json.dumps(i).lower()]
    ext("Copernicus EMS Rapid Mapping (public-activations-info API)", "checked, out of range",
        f"{len(items)} records; earliest activationTime {first_act}, after 2020-10-10; records with eventTime in Oct 2020: {oct20 or 'none'}; Ghana records: {ghana or 'none'} (not evidence of no event: the API does not reach 2020 activations)")
except Exception as e:
    ext("Copernicus EMS Rapid Mapping (public-activations-info API)", "not checked", f"{type(e).__name__}: {e}")
ext("Copernicus EMS Risk and Recovery Mapping", "not checked", "no working endpoint found in A12.2; not retried")
try:
    page = get("https://floodobservatory.colorado.edu/wiki/FloodRecords", 120).decode("utf-8", "ignore")
    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    recs = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", body, flags=re.S):
        cells = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, flags=re.S)]
        if cells:
            recs.append(cells)
    dates = [c for r in recs for c in r if re.fullmatch(r"\d{4}-\d{2}-\d{2}", c)]
    gh = [r for r in recs if any("Ghana" in c for c in r)]  # substring: also catches multi-country rows
    gh_near = [r[:6] for r in gh if any(re.fullmatch(r"2020-(09|10|11)-\d\d", c) for c in r[:4])]
    gh_dates = sorted(c for r in gh for c in r[:4] if re.fullmatch(r"\d{4}-\d{2}-\d{2}", c))
    ext("Dartmouth Flood Observatory, live site /wiki/FloodRecords", "checked, in range",
        f"{len(recs) - 1} table rows, start/end dates {min(dates)} to {max(dates)}; {len(gh)} Ghana rows (dates {gh_dates[:1]}..{gh_dates[-1:]}); Ghana rows starting Sep-Nov 2020: {gh_near or 'none'}. "
        "A DFO table with no Ghana record for this date is not evidence of no flooding (DFO lists large events)")
except Exception as e:
    ext("Dartmouth Flood Observatory, live site", "not checked", f"{type(e).__name__}: {e}")
try:
    pk = json.loads(get("https://data.humdata.org/api/3/action/package_show?id=global-active-archive-of-large-flood-events-dfo"))["result"]
    ext("Dartmouth Flood Observatory, HDX mirror", "checked, out of range", f"its own metadata: {pk['notes'][:140]}...; dataset_date {pk['dataset_date']}")
except Exception as e:
    ext("Dartmouth Flood Observatory, HDX mirror", "not checked", f"{type(e).__name__}: {e}")
ext("UNOSAT", "not re-queried in this step", "A17.6 and A18: no usable Ghana flood-extent product on HDX/UNOSAT for Accra other than the rejected 2023 product (prior result, not re-run)")

cols = ["section", "id", "time_utc", "satellite", "pass_or_instrument", "relative_orbit", "polarisations", "aoi_fraction_in_footprint",
        "hours_from_assumed_peak_0600", "hours_from_window_start_0000", "hours_from_window_end_1200", "within_24h_after_assumed_peak",
        "within_24h_after_0000", "within_24h_after_1200", "s2_aoi_cloud_fraction", "tile_cloud_pct_metadata", "s2_below_20pct", "tag"]
out = REPO_ROOT / "results" / "accra" / "candidate_2020_10_10_screening.csv"
with open(out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
print("written", out.relative_to(REPO_ROOT), len(rows), "rows")
