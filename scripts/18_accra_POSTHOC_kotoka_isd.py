"""
Amendment 22, POST-HOC, UNVALIDATED. No imagery, no method. Rules: results/evaluation_protocol.md A22.
Kotoka International Airport (ISD 654720-99999) precipitation groups, observation times 2020-06-07 00:00 to 2020-06-11 23:59:59 UTC,
given as they appear in the file; GSOD matching (A22.2); markers (A22.3); segment amounts only where A22.4 allows.
Tags: [M] measured, [A] rule/assumption, [E] estimate.

  PYTHONPATH=. python scripts/18_accra_POSTHOC_kotoka_isd.py
"""
import csv
import datetime as dt
import gzip
import re
import urllib.request

from src.config import REPO_ROOT

UA = {"User-Agent": "sar-flood-student-project/1.0"}
LABEL = "POST-HOC, UNVALIDATED"
UTC = dt.timezone.utc
T = lambda s: dt.datetime.fromisoformat(s).replace(tzinfo=UTC)
get = lambda url, t=180: urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=t).read()
fmt = lambda x: x.strftime("%d %b %H:%M")

# ---- A22.1: primary URL, then the pre-declared fallback
source_used, notes = None, []
try:
    raw = get("https://www.ncei.noaa.gov/data/global-hourly/access/2020/65472099999.csv")
    if raw[:6].lstrip().startswith(b'"STATI') or raw[:7] == b'"STATION':
        source_used = "global-hourly access CSV"
    else:
        notes.append("primary URL (global-hourly access CSV) did not return the data file (HTTP 301 to an S3 bucket index page); fallback used per A22.1")
except Exception as e:
    notes.append(f"primary URL failed ({type(e).__name__}: {e}); fallback used per A22.1")
if source_used is None:
    lines = gzip.decompress(get("https://www.ncei.noaa.gov/pub/data/noaa/2020/654720-99999-2020.gz")).decode("latin-1").splitlines()
    source_used = "pub/data/noaa/2020/654720-99999-2020.gz (ISD fixed-width)"
else:
    raise SystemExit("primary CSV parser not implemented: the primary URL is expected to fail; see notes")
print("source used:", source_used, "|", "; ".join(notes))

W0, W1 = T("2020-06-07T00:00:00"), T("2020-06-11T23:59:59")
recs = []
for l in lines:
    t = T(f"{l[15:19]}-{l[19:21]}-{l[21:23]}T{l[23:25]}:{l[25:27]}:00")
    if W0 <= t <= W1:
        recs.append((t, l[41:46], l[27], l))
print(f"ISD records in the window: {len(recs)} [M]; by type:",
      {k: sum(1 for r in recs if r[1] == k) for k in sorted({r[1] for r in recs})})
if not recs:
    raise SystemExit("STOP (A22.5): no ISD record in 7-11 June 2020: hourly or synoptic records are missing")

AA = re.compile(r"AA([1-4])(\d{2})(\d{4})([0-9A-Z])([0-9A-Z])")
OTHER = re.compile(r"A[OPHI][1-6]")
groups, other_seen, mw = [], [], 0
for t, rtype, src, l in recs:
    add = l[105:]
    i = add.find("ADD")
    if i < 0:
        continue
    add = add[i + 3:]
    for tag in ("REM", "EQD"):
        j = add.find(tag)
        if j >= 0:
            add = add[:j]
    for m in AA.finditer(add):
        hrs = int(m.group(2))
        depth = None if m.group(3) == "9999" else int(m.group(3)) / 10.0
        groups.append({"obs": t, "type": rtype, "src": src, "raw": m.group(0), "slot": m.group(1), "period_h": hrs, "depth_mm": depth,
                       "cond": m.group(4), "qual": m.group(5), "start": t - dt.timedelta(hours=hrs), "end": t})
    for m in OTHER.finditer(add):
        other_seen.append((t, m.group(0)))
    mw += add.count("MW1")
if not groups:
    raise SystemExit("STOP (A22.5): no AA precipitation group anywhere in 7-11 June 2020: hourly or synoptic precipitation records are missing")
print(f"AA groups in the window: {len(groups)}; AO/AP/AH/AI groups seen: {other_seen or 'none'} [M]")
print(f"records with a present-weather MW1 group (not an amount group, not reported): {mw}")

CODE = {"2": "Trace", "3": "Begin accumulated period (precipitation amount missing until end of accumulated period)", "4": "End accumulated period",
        "9": "Missing", "1": "Measurement impossible or inaccurate"}
QUAL = {"0": "Passed gross limits check", "1": "Passed all quality control checks", "9": "Passed gross limits check if element is present",
        "2": "Suspect", "3": "Erroneous", "4": "Passed gross limits check, data originate from an NCEI data source", "5": "Passed all quality control checks, data originate from an NCEI data source"}

# ---- markers (A22.3)
STORM = (T("2020-06-08T22:00:00"), T("2020-06-09T06:00:00"))
PASS = T("2020-06-09T18:18:05")
IMERG = (T("2020-06-10T15:30:00"), T("2020-06-10T18:00:00"))
ov = lambda a, b, c, d: a < d and c < b
rows = []
for g in sorted(groups, key=lambda g: g["obs"]):
    tags = []
    if ov(g["start"], g["end"], *STORM): tags.append("overlaps reported storm window 8 Jun 22:00-9 Jun 06:00")
    if g["start"] <= PASS <= g["end"]: tags.append("window contains the 9 Jun 18:18:05 pass")
    if ov(g["start"], g["end"], *IMERG): tags.append("overlaps IMERG peak 10 Jun 15:30-18:00")
    rows.append({"label": LABEL, "row_type": "ISD AA group (as given)", "time_utc": g["obs"].isoformat(), "report_type": g["type"], "source_flag": g["src"],
                 "raw_group": g["raw"], "period_h": g["period_h"], "depth_mm": "missing" if g["depth_mm"] is None else g["depth_mm"],
                 "condition_code": g["cond"], "condition_meaning_per_isd_format_doc": CODE.get(g["cond"], "see ISD format document"),
                 "quality_code": g["qual"], "quality_meaning_per_isd_format_doc": QUAL.get(g["qual"], "see ISD format document"),
                 "accumulation_window_utc": f"{g['start'].isoformat()} to {g['end'].isoformat()}", "markers": "; ".join(tags), "tag": "[M]"})
for lab, a, b in (("MARKER: reported storm window (A12.1)", *STORM), ("MARKER: Sentinel-1 pass", PASS, PASS), ("MARKER: IMERG heaviest rain (A19-R4)", *IMERG)):
    rows.append({"label": LABEL, "row_type": lab, "time_utc": a.isoformat(), "accumulation_window_utc": f"{a.isoformat()} to {b.isoformat()}", "tag": "[A]"})
rows.sort(key=lambda r: r["time_utc"])

print("\n=== table, time order (marker rows inserted) ===")
for r in rows:
    if r["row_type"].startswith("MARKER"):
        print(f"  ---- {r['row_type']}: {r['accumulation_window_utc']}")
    else:
        print(f"  {r['time_utc'][:16]} {r['report_type']} src {r['source_flag']}  {r['raw_group']}  period {r['period_h']} h  depth {r['depth_mm']} mm  cond {r['condition_code']}  qual {r['quality_code']}"
              f"  window {r['accumulation_window_utc'][:16]}..{r['accumulation_window_utc'][-25:-9]}  {r['markers']}")

# ---- A22.2: GSOD daily totals for 8-11 June and the ISD report they correspond to
gsod = list(csv.DictReader(get("https://www.ncei.noaa.gov/data/global-summary-of-the-day/access/2020/65472099999.csv").decode("utf-8", "ignore").splitlines()))
FLAG = {"G": "1 report of 24-hour precipitation amount", "E": "1 report of 12-hour precipitation amount",
        "I": "Station did not report any precipitation data for the day and did not report any occurrences of precipitation in its hourly observations. It's still possible that precipitation occurred but was not reported."}
print("\n=== GSOD daily totals and the ISD report they correspond to (A22.2: exactly one AA group on that UTC date with equal depth in inches) ===")
for d in ("2020-06-08", "2020-06-09", "2020-06-10", "2020-06-11"):
    r = [x for x in gsod if x["DATE"] == d][0]
    p, flag = float(r["PRCP"]), r["PRCP_ATTRIBUTES"].strip()
    same_day = [g for g in groups if g["obs"].date().isoformat() == d]
    match = [g for g in same_day if g["depth_mm"] is not None and round(g["depth_mm"] / 25.4, 2) == round(p, 2)] if p != 99.99 and flag != "I" else []
    if flag == "I":
        verdict = f"not determinable: GSOD flag I ({FLAG['I']}); AA groups dated {d}: {[g['raw'] for g in same_day] or 'none'}"
    elif len(match) == 1:
        g = match[0]
        verdict = (f"matches exactly one AA group: {g['raw']} at {g['obs'].isoformat()} (period {g['period_h']} h, {g['depth_mm']} mm) -> accumulation window "
                   f"{g['start'].isoformat()} to {g['end'].isoformat()} UTC")
    else:
        verdict = f"not determinable ({len(match)} matching AA groups); AA groups dated {d}: {[g['raw'] for g in same_day] or 'none'}"
    print(f"  {d}: GSOD PRCP {r['PRCP'].strip()} in = {round(p * 25.4, 2)} mm, flag {flag} ({FLAG.get(flag, 'see NOAA readme')[:60]}...) -> {verdict}")
    rows.append({"label": LABEL, "row_type": "GSOD daily total (A22.2)", "time_utc": d, "raw_group": f"PRCP {r['PRCP'].strip()} in; flag {flag}", "depth_mm": round(p * 25.4, 2),
                 "markers": verdict, "tag": "[M]"})

# ---- A22.4: segments
SEG = [("(i) before the pass", T("2020-06-07T00:00:00"), PASS), ("(ii) pass to 10 Jun 12:00", PASS, T("2020-06-10T12:00:00")),
       ("(iii) after 10 Jun 12:00", T("2020-06-10T12:00:00"), T("2020-06-12T00:00:00"))]
print("\n=== A22.4 segment amounts (only if reports tile the whole segment; no splitting, no infill) ===")
amount = [g for g in groups if g["depth_mm"] is not None]
for name, S, E in SEG:
    inside = sorted([g for g in amount if g["start"] >= S and g["end"] <= E], key=lambda g: g["start"])
    strad = [g for g in amount if ov(g["start"], g["end"], S, E) and g not in inside]
    cov, gaps, cur = [], [], S
    for g in inside:
        if g["start"] > cur: gaps.append((cur, g["start"]))
        cur = max(cur, g["end"])
    if cur < E: gaps.append((cur, E))
    tiles = not gaps and all(inside[i]["end"] == inside[i + 1]["start"] for i in range(len(inside) - 1)) if inside else False
    if tiles:
        verdict = f"determinable: sum of reported values as given = {sum(g['depth_mm'] for g in inside):.1f} mm from {len(inside)} windows"
    else:
        verdict = "NOT DETERMINABLE from the reports as given"
    print(f"  {name} [{fmt(S)} - {fmt(E)} UTC]: {verdict}")
    print(f"      windows wholly inside: {[(g['raw'], g['depth_mm'], fmt(g['start']) + '-' + fmt(g['end'])) for g in inside] or 'none'}")
    print(f"      straddling a boundary (counted in no segment): {[(g['raw'], g['depth_mm'], fmt(g['start']) + '-' + fmt(g['end'])) for g in strad] or 'none'}")
    print(f"      uncovered intervals of the segment: {[fmt(a) + ' - ' + fmt(b) for a, b in gaps] or 'none'}")
    rows.append({"label": LABEL, "row_type": f"SEGMENT {name} (A22.4)", "time_utc": S.isoformat(), "accumulation_window_utc": f"{S.isoformat()} to {E.isoformat()}",
                 "markers": f"{verdict}; inside: {[(g['raw'], g['depth_mm']) for g in inside]}; straddling: {[(g['raw'], g['depth_mm'], fmt(g['start']) + '-' + fmt(g['end'])) for g in strad]}; "
                            f"uncovered: {[fmt(a) + ' - ' + fmt(b) for a, b in gaps]}", "tag": "[M]"})

cols = ["label", "row_type", "time_utc", "report_type", "source_flag", "raw_group", "period_h", "depth_mm", "condition_code", "condition_meaning_per_isd_format_doc",
        "quality_code", "quality_meaning_per_isd_format_doc", "accumulation_window_utc", "markers", "tag"]
with open(REPO_ROOT / "results" / "accra_POSTHOC_kotoka_isd_7_11_june.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
print("\nwritten results/accra_POSTHOC_kotoka_isd_7_11_june.csv")
