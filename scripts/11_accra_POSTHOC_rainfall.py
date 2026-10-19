"""
Amendment 19 A19-R3, POST-HOC (not pre-declared as part of the original checks). UNVALIDATED.
IMERG V07 rain over the Odaw AOI: daily totals 20 May-15 Jun 2020 and the 24 h before each Sentinel-1 pass.
Rules are in results/evaluation_protocol.md A19-R3. Table only, no thresholds.

  PYTHONPATH=. python scripts/11_accra_POSTHOC_rainfall.py
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
LABEL = "POST-HOC, UNVALIDATED"
PASSES = {"2020-05-22": "18:17:24", "2020-05-28": "18:18:04", "2020-06-03": "18:17:25",
          "2020-06-09": "18:18:05", "2020-06-15": "18:17:25"}


def accumulate(aoi, start, end):
    """Area-mean and max-pixel accumulation (mm) over [start, end), plus slices found and IMERG pixels touched."""
    col = (ee.ImageCollection("NASA/GPM_L3/IMERG_V07").filterDate(start.isoformat(), end.isoformat())
           .select("precipitation"))
    total = col.map(lambda i: i.multiply(0.5)).sum()  # mm/hr x 0.5 h per slice
    kw = dict(geometry=aoi, scale=11132, crs="EPSG:4326", maxPixels=1e9)
    mean = total.reduceRegion(reducer=ee.Reducer.mean(), **kw).get("precipitation")
    mx = total.reduceRegion(reducer=ee.Reducer.max(), **kw).get("precipitation")
    npx = total.reduceRegion(reducer=ee.Reducer.count(), **kw).get("precipitation")
    r = ee.Dictionary({"mean": mean, "max": mx, "npx": npx, "slices": col.size()}).getInfo()
    return r


def main():
    m06.ee_init()
    aoi = m06.aoi_geometry()
    rows = []
    d = dt.datetime(2020, 5, 20, tzinfo=UTC)
    while d <= dt.datetime(2020, 6, 15, tzinfo=UTC):
        r = accumulate(aoi, d, d + dt.timedelta(days=1))
        rows.append({"label": LABEL, "table": "A_daily_UTC", "pass_date": "", "window_start_utc": d.isoformat(),
                     "window_end_utc": (d + dt.timedelta(days=1)).isoformat(), "slices_found": r["slices"],
                     "imerg_pixels_in_aoi": r["npx"], "area_mean_mm": r["mean"], "max_pixel_mm": r["max"],
                     "rain_or_no_rain": "no rain" if (r["mean"] == 0 and r["max"] == 0) else "rain"})
        d += dt.timedelta(days=1)
    for date, hms in PASSES.items():
        t = dt.datetime.fromisoformat(f"{date}T{hms}").replace(tzinfo=UTC)
        end = t.replace(minute=0 if t.minute < 30 else 30, second=0)  # pass time floored to the half hour
        start = end - dt.timedelta(hours=24)
        r = accumulate(aoi, start, end)
        rows.append({"label": LABEL, "table": "B_24h_before_pass", "pass_date": f"{date} {hms} UTC",
                     "window_start_utc": start.isoformat(), "window_end_utc": end.isoformat(),
                     "slices_found": r["slices"], "imerg_pixels_in_aoi": r["npx"], "area_mean_mm": r["mean"],
                     "max_pixel_mm": r["max"],
                     "rain_or_no_rain": "no rain" if (r["mean"] == 0 and r["max"] == 0) else "rain"})
    out = REPO_ROOT / "results" / "accra_POSTHOC_rainfall.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(f"{r['table']:18s} {r['pass_date'] or r['window_start_utc'][:10]:24s} slices={r['slices_found']:3d} "
              f"px={r['imerg_pixels_in_aoi']} mean={r['area_mean_mm']:.2f} mm max={r['max_pixel_mm']:.2f} mm {r['rain_or_no_rain']}")


if __name__ == "__main__":
    main()
