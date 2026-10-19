"""
Amendment 19 A19-R4, POST-HOC, UNVALIDATED. Rules: results/evaluation_protocol.md A19-R4.
  R4.1 IMERG V07 half-hourly area-mean rain over the Odaw AOI, 7-12 June 2020 UTC (table + bar chart, 9 June 18:18 pass marked).
  R4.2 every Sentinel-1 GRD scene (any mode / orbit / pass) intersecting the AOI, 9 Jun 18:18:00 to 12 Jun 23:59:59 UTC.
No thresholds, no interpretation.

  PYTHONPATH=. python scripts/13_accra_POSTHOC_rain_halfhourly_and_s1_list.py
"""
import csv
import datetime as dt
import importlib.util

import ee
import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from src.config import REPO_ROOT

_s = importlib.util.spec_from_file_location("m06", REPO_ROOT / "scripts" / "06_accra_run.py")
m06 = importlib.util.module_from_spec(_s)
_s.loader.exec_module(m06)
UTC = dt.timezone.utc
LABEL = "POST-HOC, UNVALIDATED"
PASS = dt.datetime(2020, 6, 9, 18, 18, 5, tzinfo=UTC)
ts = lambda ms: dt.datetime.fromtimestamp(ms / 1000, UTC)

m06.ee_init()
aoi = m06.aoi_geometry()

# R4.1
col = (ee.ImageCollection("NASA/GPM_L3/IMERG_V07").filterDate("2020-06-07T00:00:00", "2020-06-13T00:00:00")
       .select("precipitation"))
red = ee.Reducer.mean().combine(ee.Reducer.max(), sharedInputs=True)
def per_slice(i):
    r = i.multiply(0.5).reduceRegion(reducer=red, geometry=aoi, scale=11132, crs="EPSG:4326", maxPixels=1e9)
    return ee.Feature(None, {"t": i.get("system:time_start"), "mean": r.get("precipitation_mean"), "max": r.get("precipitation_max")})
feats = col.map(per_slice).getInfo()["features"]
rows = sorted(({"t": ts(f["properties"]["t"]), "mean": f["properties"]["mean"], "max": f["properties"]["max"]} for f in feats),
              key=lambda r: r["t"])
print(f"half-hourly slices found: {len(rows)} (expected 288); missing values: {sum(r['mean'] is None for r in rows)}")
with open(REPO_ROOT / "results" / "accra_POSTHOC_rainfall_halfhourly_7_12_june.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["label", "slice_start_utc", "area_mean_mm_per_30min", "max_pixel_mm_per_30min"])
    for r in rows:
        w.writerow([LABEL, r["t"].isoformat(), r["mean"], r["max"]])
fig, ax = plt.subplots(figsize=(11, 4.2))
ax.bar([r["t"] for r in rows], [r["mean"] or 0 for r in rows], width=dt.timedelta(minutes=30), align="edge",
       color="#0072B2", linewidth=0)
ax.axvline(PASS, color="black", linestyle="--", linewidth=1)
ax.annotate("S1 pass, 9 Jun 18:18 UTC\n(orbit 147)", (PASS, ax.get_ylim()[1]), xytext=(-6, -6), textcoords="offset points", ha="right",
            va="top", fontsize=8)
ax.xaxis.set_major_locator(mdates.DayLocator()); ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
ax.set_xlim(dt.datetime(2020, 6, 7, tzinfo=UTC), dt.datetime(2020, 6, 13, tzinfo=UTC))
ax.set_ylabel("rain, mm per 30 min (area mean)"); ax.set_xlabel("UTC")
ax.spines[["top", "right"]].set_visible(False)
ax.set_title("POST-HOC, UNVALIDATED. IMERG V07 half-hourly rain over the Odaw AOI, 7-12 June 2020 (about 11 km pixels)", fontsize=9.5)
fig.savefig(REPO_ROOT / "results" / "accra_POSTHOC_rainfall_halfhourly_7_12_june.png", dpi=130, bbox_inches="tight")

# R4.2
s1 = (ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(aoi).filterDate("2020-06-09T18:18:00", "2020-06-13T00:00:00"))
aoi_area = aoi.area(1)
def meta(i):
    cov = ee.Number(i.geometry().intersection(aoi, 1).area(1)).divide(aoi_area)
    return ee.Feature(None, {"id": i.get("system:index"), "t": i.get("system:time_start"), "plat": i.get("platform_number"),
                             "mode": i.get("instrumentMode"), "pol": i.get("transmitterReceiverPolarisation"),
                             "pass": i.get("orbitProperties_pass"), "orbit": i.get("relativeOrbitNumber_start"), "cov": cov})
srows = sorted((f["properties"] for f in s1.map(meta).getInfo()["features"]), key=lambda p: p["t"])
with open(REPO_ROOT / "results" / "accra_POSTHOC_s1_acquisitions_9_12_june.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["label", "scene_id", "start_utc", "platform", "mode", "polarisations", "pass", "relative_orbit",
                "hours_after_9jun_1818_pass", "aoi_fraction_in_footprint", "note"])
    for p in srows:
        t = ts(p["t"])
        w.writerow([LABEL, p["id"], t.isoformat(), p["plat"], p["mode"], "+".join(p["pol"]), p["pass"], p["orbit"],
                    round((t - PASS).total_seconds() / 3600, 2), round(p["cov"], 4),
                    "the 9 June orbit-147 pass used in the study" if abs((t - PASS).total_seconds()) < 5 else ""])
print(f"\nS1 GRD scenes intersecting the AOI, 9 Jun 18:18:00 - 12 Jun 23:59:59 UTC: {len(srows)}")
for p in srows:
    t = ts(p["t"])
    print(f"  {t:%Y-%m-%d %H:%M:%S} S1{p['plat']} {p['mode']} {'+'.join(p['pol'])} {p['pass']:10s} rel.orbit {p['orbit']:3d} "
          f"+{(t - PASS).total_seconds() / 3600:6.2f} h  AOI in footprint {p['cov']:.3f}  {p['id']}")
print("\nhalf-hourly table, rows around the pass and the largest slices:")
for r in rows:
    if dt.datetime(2020, 6, 9, 16, 0, tzinfo=UTC) <= r["t"] <= dt.datetime(2020, 6, 9, 20, 0, tzinfo=UTC):
        print(f"  {r['t']:%d %b %H:%M} mean {r['mean']:.3f} mm  max {r['max']:.3f} mm")
top = sorted(rows, key=lambda r: -(r["mean"] or 0))[:6]
print("six largest slices:", "; ".join(f"{r['t']:%d %b %H:%M}={r['mean']:.2f}" for r in top))
