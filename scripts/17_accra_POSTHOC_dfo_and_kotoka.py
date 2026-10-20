"""
Amendment 21, POST-HOC, UNVALIDATED. No imagery, no method. Rules: results/evaluation_protocol.md A21.
  Lookup 1: DFO live FloodRecords table, Ghana rows whose dates overlap each candidate of the A20.8 ranking.
  Lookup 2: Kotoka International Airport (ISD 654720-99999) GSOD rainfall, 1-15 June 2020, with the A21.2 stop rule.
Tags in outputs: [M] measured, [A] assumed/rule, [E] estimate.

  PYTHONPATH=. python scripts/17_accra_POSTHOC_dfo_and_kotoka.py
"""
import csv
import datetime as dt
import html
import importlib.util
import re
import urllib.request

import numpy as np

from src.config import REPO_ROOT

UA = {"User-Agent": "sar-flood-student-project/1.0"}
LABEL = "POST-HOC, UNVALIDATED"
D = dt.date.fromisoformat
get = lambda url, t=120: urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=t).read()

# ---------------- Lookup 1: DFO ----------------
CANDIDATES = [  # (label, window start, window end) fixed in A21.1 from the A20.8 ranking
    ("2020-06-09 (selected; reported peak window 8-9 Jun)", "2020-06-08", "2020-06-09"), ("2025-05-18", "2025-05-18", "2025-05-18"),
    ("2018-06-18", "2018-06-18", "2018-06-18"), ("2019-04-14", "2019-04-14", "2019-04-14"),
    ("2023-10 UNOSAT FL20231018GHA (onset window 11-14 Oct)", "2023-10-11", "2023-10-14"), ("2019-04-07", "2019-04-07", "2019-04-07"),
    ("2019-10-28", "2019-10-28", "2019-10-28"), ("2019-10-10", "2019-10-10", "2019-10-10"), ("2020-10-10", "2020-10-10", "2020-10-10"),
    ("2018-06-28", "2018-06-28", "2018-06-28"), ("2019-05-30", "2019-05-30", "2019-05-30"), ("2026-06-29", "2026-06-29", "2026-06-29"),
    ("2023-03-07", "2023-03-07", "2023-03-07"), ("2016-06-09", "2016-06-09", "2016-06-09"), ("2015-06-03", "2015-06-03", "2015-06-03"),
]
page = get("https://floodobservatory.colorado.edu/wiki/FloodRecords").decode("utf-8", "ignore")
body = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
table = []
for r in re.findall(r"<tr[^>]*>(.*?)</tr>", body, flags=re.S):
    cells = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, flags=re.S)]
    if cells:
        table.append(cells)
header, recs = table[0], table[1:]
isdate = lambda c: re.fullmatch(r"\d{4}-\d{2}-\d{2}", c)
alld = [c for r in recs for c in r if isdate(c)]
t_min, t_max = min(alld), max(alld)
print(f"DFO FloodRecords: {len(recs)} rows, dates {t_min} to {t_max} [M]; header: {header}")
ghana = []
for r in recs:
    if any("Ghana" in c for c in r):
        ds = [c for c in r if isdate(c)]
        if len(ds) >= 2:
            ghana.append((D(ds[0]), D(ds[1]), r))
        else:
            print("  Ghana row without two parseable dates:", r)
print(f"Ghana rows: {len(ghana)} [M]")
rows1 = []
for label, a, b in CANDIDATES:
    a_, b_ = D(a), D(b)
    beyond = a_ > D(t_max)
    primary = [g for g in ghana if g[0] <= b_ and g[1] >= a_]
    sens = [g for g in ghana if g[0] <= b_ + dt.timedelta(days=3) and g[1] >= a_ - dt.timedelta(days=3)]
    status = ("beyond the table's range" if beyond else ("OVERLAP" if primary else "no overlapping Ghana row"))
    print(f"\n{label} [{a}..{b}]: {status}; +/-3 d sensitivity rows: {len(sens)}")
    for kind, lst in (("primary overlap", primary), ("sensitivity +/-3 d only", [g for g in sens if g not in primary])):
        for g in lst:
            print(f"    {kind}: {dict(zip(header, g[2]))}")
            rows1.append({"label": LABEL, "candidate": label, "window_start": a, "window_end": b, "match_kind": kind, "status": status, **{f"dfo_{h}": v for h, v in zip(header, g[2])}})
    if not primary and not [g for g in sens if g not in primary]:
        rows1.append({"label": LABEL, "candidate": label, "window_start": a, "window_end": b, "match_kind": "none", "status": status})
cols1 = ["label", "candidate", "window_start", "window_end", "match_kind", "status"] + [f"dfo_{h}" for h in header]
with open(REPO_ROOT / "results" / "accra_POSTHOC_dfo_candidate_overlap.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols1)
    w.writeheader()
    w.writerows(rows1)

# ---------------- Lookup 2: Kotoka GSOD ----------------
print("\n=== Kotoka International Airport ===")
isd = list(csv.DictReader(get("https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv").decode("utf-8", "ignore").splitlines()))
st = [r for r in isd if "KOTOKA" in r["STATION NAME"].upper()]
print("ISD station-list matches for KOTOKA:", [(r["USAF"], r["WBAN"], r["STATION NAME"], r["LAT"], r["LON"], r["BEGIN"], r["END"]) for r in st], "[M]")
assert len(st) == 1, "more than one Kotoka station: ask the owner (A21.2)"
usaf, wban = st[0]["USAF"], st[0]["WBAN"]
gsod = list(csv.DictReader(get(f"https://www.ncei.noaa.gov/data/global-summary-of-the-day/access/2020/{usaf}{wban}.csv").decode("utf-8", "ignore").splitlines()))
doc_flags = {"G": "1 report of 24-hour precipitation amount", "E": "1 report of 12-hour precipitation amount",
             "I": "station did not report any precipitation data for the day and did not report any occurrences of precipitation in its hourly observations; still possible that precipitation occurred but was not reported (NOAA GSOD readme)",
             "H": "station reported 0 for the day but also at least one occurrence of precipitation in hourly observations; incomplete data for the day (NOAA GSOD readme)"}
july = [r for r in gsod if "2020-06-01" <= r["DATE"] <= "2020-06-15"]
rows2 = []
stop_reasons = []
for r in july:
    p = float(r["PRCP"])
    mm = None if p == 99.99 else round(p * 25.4, 2)
    flag = r["PRCP_ATTRIBUTES"].strip()
    rows2.append({"label": LABEL, "date_gmt_day": r["DATE"], "gsod_prcp_inches": r["PRCP"].strip(), "gsod_prcp_mm": mm, "gsod_flag": flag,
                  "flag_meaning_per_noaa_readme": doc_flags.get(flag, "see NOAA readme"), "frshtt": r["FRSHTT"], "tag": "[M]"})
    if r["DATE"] in ("2020-06-08", "2020-06-09", "2020-06-10") and (mm is None or flag == "I"):
        stop_reasons.append(f"{r['DATE']}: PRCP {r['PRCP'].strip()} flag {flag or '(none)'}")
    print(f"  {r['DATE']}  PRCP {r['PRCP'].strip():>5} in = {mm if mm is not None else 'missing':>6} mm  flag {flag}  FRSHTT {r['FRSHTT']}")
print(f"GSOD June 2020 rows for 1-15 June: {len(july)} of 15 [M]")

# station location vs the AOI (metadata)
_s = importlib.util.spec_from_file_location("m06", REPO_ROOT / "scripts" / "06_accra_run.py")
m06 = importlib.util.module_from_spec(_s)
_s.loader.exec_module(m06)
from rasterio.warp import transform as rtransform
aoi_arr, _, tr = m06.read_bands(m06.DATA / "aoi_mask.tif", ["aoi"])
lat, lon = float(gsod[0]["LATITUDE"]), float(gsod[0]["LONGITUDE"])
x, y = rtransform("EPSG:4326", m06.CRS, [lon], [lat])
col, row = int((x[0] - tr.c) // tr.a), int((y[0] - tr.f) // tr.e)
inside = bool(0 <= row < aoi_arr["aoi"].shape[0] and 0 <= col < aoi_arr["aoi"].shape[1] and aoi_arr["aoi"][row, col] > 0.5)
print(f"station {usaf}-{wban} at ({lat:.4f}, {lon:.4f}) from the GSOD file; inside the Odaw AOI mask: {inside} [M]")

if stop_reasons:
    print("\nSTOP (A21.2): " + "; ".join(stop_reasons) + ". ISD pull and IMERG comparison NOT run.")
status = "STOPPED per A21.2: " + "; ".join(stop_reasons) if stop_reasons else "stop rule not triggered"
for r in rows2:
    r["status"] = status
with open(REPO_ROOT / "results" / "accra_POSTHOC_kotoka_rainfall.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows2[0].keys()))
    w.writeheader()
    w.writerows(rows2)
print("written results/accra_POSTHOC_dfo_candidate_overlap.csv and results/accra_POSTHOC_kotoka_rainfall.csv")
