"""
Amendment 19 Step 5: write results/accra_followup_summary.md. Tables are read from the committed CSV/JSON outputs of
Steps 2-4 and the POST-HOC checks, so no table number is typed by hand. Narrative numbers are quoted from those same files.
Tags: [M] measured by code run in this session, [A] assumption or rule chosen by the owner/me, [E] estimate or reasoning.

  PYTHONPATH=. python scripts/15_accra_followup_summary.py
"""
import json

import numpy as np
import pandas as pd

from src.config import REPO_ROOT

R = REPO_ROOT / "results"
AREAS = ["full_Odaw_AOI", "core", "kaneshie", "darkuman_clipped", "pooled"]
RULES = ["cd", "cd_guarded", "brighten", "unspider_vh", "unspider_vv"]
RULE_NAME = {"cd": "CD (dVV < -3 dB) [A]", "cd_guarded": "guarded CD [A]", "brighten": "brightening (dVV > +3 dB) [A]",
             "unspider_vh": "UN-SPIDER ratio 1.25, VH [A]", "unspider_vv": "UN-SPIDER ratio 1.25, VV [A]"}


def md(df):
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        out.append("| " + " | ".join(str(v) for v in r.values) + " |")
    return "\n".join(out)


f2 = lambda v: f"{v:,.2f}"
cdb = pd.read_csv(R / "accra_cd_baseline.csv")


def step2_table(pair_set):
    rows = []
    for rule in RULES:
        for area in AREAS:
            s = cdb[(cdb.pair_set == pair_set) & (cdb.rule == rule) & (cdb.area == area)]
            ev, co, d = (s[s.role == k].iloc[0] for k in ("event", "control", "event_minus_control"))
            rows.append({"rule": RULE_NAME[rule], "area": area, "event minus control (ha)": f"{d.event_minus_control_ha:+,.2f}",
                         "event minus control (pp of valid domain)": f"{100 * d.event_minus_control_fraction:+.2f}",
                         "event (ha)": f2(ev.flagged_ha), "control (ha)": f2(co.flagged_ha)})
    return md(pd.DataFrame(rows))


hl = step2_table("headline")
ss = step2_table("same-satellite sensitivity")
rec = cdb[(cdb.role == "recession")]
rec_t = md(pd.DataFrame([{"rule": RULE_NAME[r], **{a: f2(rec[(rec.rule == r) & (rec.area == a)].flagged_ha.iloc[0]) for a in AREAS}} for r in RULES]))
pairs = cdb[(cdb.rule == "cd") & (cdb.area == "full_Odaw_AOI") & (cdb.role != "event_minus_control")][["pair_set", "role", "first_date", "second_date"]]
med = json.load(open(R / "accra" / "accra_cd_POSTHOC_median_dvv.json"))["full_AOI_domain"]
# Keys look like 'headline|event|2020-06-03->2020-06-09'. They are split into three columns because a '|' inside a
# markdown cell is read as a column break (corrected 2026-11-16: the earlier header had 5 cells over 3-cell rows).
med_t = md(pd.DataFrame([{"pair set": k.split("|")[0], "role": k.split("|")[1], "dates": k.split("|")[2],
                          "median dVV (dB)": f"{v['median_dVV_dB']:+.3f}",
                          "mean dVV (dB)": f"{v['mean_dVV_dB']:+.3f}"} for k, v in med.items()]))
rain = pd.read_csv(R / "accra_POSTHOC_rainfall.csv")
rb = rain[rain.table == "B_24h_before_pass"]
rain_b = md(pd.DataFrame([{"pass (UTC)": r.pass_date, "window (UTC)": f"{r.window_start_utc[:16]} to {r.window_end_utc[:16]}",
                           "slices": r.slices_found, "area-mean (mm)": f"{r.area_mean_mm:.2f}",
                           # CSV column 'max_pixel_mm' (name kept so the committed CSV is unchanged); see the note under the table
                           "pixel with centre in AOI (mm)": f"{r.max_pixel_mm:.2f}",
                           "rain / no rain (exactly 0.00 mm rule)": r.rain_or_no_rain} for r in rb.itertuples()]))
ra = rain[rain.table == "A_daily_UTC"].set_index(rain[rain.table == "A_daily_UTC"].window_start_utc.str[:10])
d8, d9, d10 = (ra.loc[f"2020-06-{d:02d}", "area_mean_mm"] for d in (8, 9, 10))
hh = pd.read_csv(R / "accra_POSTHOC_rainfall_halfhourly_7_12_june.csv")
top6 = hh.sort_values("area_mean_mm_per_30min", ascending=False).head(6)
top6_txt = ", ".join(f"{t[5:16].replace('T', ' ')}={m:.2f}" for t, m in zip(top6.slice_start_utc, top6.area_mean_mm_per_30min))
s1 = pd.read_csv(R / "accra_POSTHOC_s1_acquisitions_9_12_june.csv")
s1_t = md(s1[["scene_id", "start_utc", "platform", "mode", "polarisations", "pass", "relative_orbit", "hours_after_9jun_1818_pass",
              "aoi_fraction_in_footprint", "note"]])
cc = pd.read_csv(R / "accra_coastal_control.csv").iloc[:5]
cc_t = md(pd.DataFrame([{"category": r["item"], "pixels": r["pixels"], "share of accepted": (f"{100 * float(r['share_of_accepted']):.1f}%" if r["share_of_accepted"] != "not computed" else "not computed"),
                         "inside AOI": r["pixels_inside_AOI"], "outside AOI": r["pixels_outside_AOI"]} for _, r in cc.iterrows()]))

pc = pd.read_csv(R / "accra_point_checks.csv")
ctrl = pc[pc.kind == "control"]
site = pc[pc.kind == "site"]
cp_rows, cp = [], {}
for b in (50, 100):
    for col, nm in (("median_VV_9jun_dB", "9 June VV (dB)"), ("median_dVV_3to9_dB", "dVV 3 to 9 June (dB)")):
        v = ctrl[ctrl.buffer_m == b][col].astype(float).values
        p5, p50, p95 = np.percentile(v, [5, 50, 95])
        cp[(b, col)] = (p5, p50, p95)
        cp_rows.append({"buffer": f"{b} m", "quantity": nm, "n": len(v), "5th percentile": f"{p5:+.3f}", "median": f"{p50:+.3f}",
                        "95th percentile": f"{p95:+.3f}", "5th below median": f"{p5 - p50:+.3f}", "95th above median": f"{p95 - p50:+.3f}"})
cp_t = md(pd.DataFrame(cp_rows))


def site_table(buffer):
    s = site[site.buffer_m == buffer]
    return md(pd.DataFrame([{"site": r.site, "centroid": r.centroid_role, "OSM object": r.osm_object, "n valid px": r.n_valid_pixels,
                             "9 Jun VV (dB)": f"{r.median_VV_9jun_dB:.2f}", "VV pctile": f"{r.pctile_rank_VV9:.1f}",
                             "dVV 3-9 Jun (dB)": f"{r.median_dVV_3to9_dB:+.2f}", "dVV pctile": f"{r.pctile_rank_dVV:.1f}",
                             "VV 3 Jun": f"{r.median_VV_3jun_dB:.2f}", "VV 15 Jun (not 9 Jun evidence)": f"{r.median_VV_15jun_dB:.2f}",
                             "B1": f"{r.frac_B1:.2f}", "B2g VH": f"{r.frac_B2g_VH:.2f}", "M1g": f"{r.frac_M1g:.2f}", "M2g": f"{r.frac_M2g:.2f}",
                             "CD": f"{r.frac_CD:.2f}", "guarded CD": f"{r.frac_CD_guarded:.2f}",
                             "stands out (VV / dVV)": f"{r.stands_out_VV9} / {r.stands_out_dVV}"} for r in s.itertuples()]))


n_out = int(site.stands_out_VV9.sum() + site.stands_out_dVV.sum())
n_ranks = 2 * len(site)
head50 = site[(site.buffer_m == 50) & (site.centroid_role == "headline")]
circ = site[(site.buffer_m == 50) & (site.site == "Kwame Nkrumah Circle")].pctile_rank_VV9
odaw = site[(site.buffer_m == 50) & (site.site == "Odawna")].pctile_rank_VV9
taifa = site[(site.buffer_m == 50) & (site.site == "Taifa")].pctile_rank_VV9
v50, d50, v100, d100 = (cp[(50, "median_VV_9jun_dB")], cp[(50, "median_dVV_3to9_dB")], cp[(100, "median_VV_9jun_dB")], cp[(100, "median_dVV_3to9_dB")])
d_hl = {k: v for k, v in zip(RULES, [0] * 5)}
g = lambda ps, rule, area, role: cdb[(cdb.pair_set == ps) & (cdb.rule == rule) & (cdb.area == area) & (cdb.role == role)].iloc[0]

import hashlib, re, subprocess
reg = (R / "accra_followup_registration.txt").read_text()
recorded = re.findall(r"sha256 at that commit: ([0-9a-f]{64})", reg)
cur = hashlib.sha256((R / "evaluation_protocol.md").read_bytes()).hexdigest()
# Corrected 2026-11-16. The earlier text compared the CURRENT protocol hash with the last recorded hash and called
# that line "(R5)". Once Amendments 20 to 22 were registered, the last line was no longer R5, so the label was wrong.
# Now the R5 hash (the state at the Amendment 19 hand-back) is quoted from the record itself, and the current file
# is compared with the latest hash recorded, whichever amendment that is.
r5 = re.search(r"r5_commit: [0-9a-f]+\s+evaluation_protocol\.md sha256 at that commit: ([0-9a-f]{64})", reg).group(1)
latest = re.findall(r"sha256 (?:at that commit|now): ([0-9a-f]{64})", reg)[-1]
hash_chain = ("at the Amendment 19 hand-back the `results/evaluation_protocol.md` sha256 was " + r5[:16] +
              "... (the R5 line of the registration record) [M]. Later amendments are registered after it; the "
              "current file's sha256 " + cur[:16] + "... " +
              ("equals the latest hash in the registration record [M]." if cur == latest else
               "DOES NOT equal the latest hash in the registration record: the protocol changed without being registered [M]."))

txt = f"""# Accra follow-up checks: summary (Amendment 19)

**UNVALIDATED: no ground truth exists for this event. Nothing here is validation.** Tags: **[M]** measured by code run in this
session from the files named; **[A]** assumption or rule chosen by the owner or me; **[E]** estimate or reasoning.

- **Amendment:** Amendment 19, 2026-10-19, first committed in **`d2b2985`** (protocol sha256 at that commit
  `2851ffc7be28cfc2b0a36148ff38747e16c8f1c9b3a35f54b7dac7a7fe75ad1e`). Revisions R2-R5 below. Registration record:
  `results/accra_followup_registration.txt`.
- Interpretation limit (A19-R5.4, owner's): the point checks are read **only as a test of the 8-9 June overnight storm**; the heaviest
  IMERG rain is **10 June 15:30-18:00 UTC, after the 9 June pass**; 15 June values are **not** evidence about 9 June.

## 1. Scene IDs [M, Earth Engine catalogue query 2026-10-19; IW, VV+VH, relative orbit 147, ascending]

| Date (UTC) | Sat | Scene ID |
|---|---|---|
| 2020-05-22 18:17:24 | S1B | `S1B_IW_GRDH_1SDV_20200522T181724_20200522T181749_021698_0292FB_9ACA` |
| 2020-05-28 18:18:04 | S1A | `S1A_IW_GRDH_1SDV_20200528T181804_20200528T181833_032769_03CBB7_64D8` |
| 2020-06-03 18:17:25 | S1B | `S1B_IW_GRDH_1SDV_20200603T181725_20200603T181750_021873_02983B_F419` |
| 2020-06-09 18:18:05 | S1A | `S1A_IW_GRDH_1SDV_20200609T181805_20200609T181834_032944_03D0DF_47E9` |
| 2020-06-15 18:17:25 | S1B | `S1B_IW_GRDH_1SDV_20200615T181725_20200615T181750_022048_029D7F_634F` |

## 2. Every amendment and POST-HOC / exploratory label from this session, in order, with commits

1. **A19** (`d2b2985`, registration record `fb9f2d3`), pre-declared before any check was run: A19.1 disclosure of exploratory runs already seen
   (tiled M2g, `scripts/08`; 3 v 15 June brightening, `scripts/09`; A15's 9 v 3 June diagnostic); A19.2 scenes; **A19.3-A19.5** Step 2 rules
   (CD, guarded CD, brightening, same-satellite sensitivity pairs, event-minus-control reporting); A19.6 Step 3 rules; **A19.7** Step 4 rules
   (sites, 50 m headline and 100 m sensitivity buffers, 200 controls, seed 20200609, percentile rule); A19.8 reporting; A19.9 registration.
   This commit also first committed the previously uncommitted Amendments 17 and 18 (written 2026-10-03).
2. **A19-R2** (`806fcf1`, registration `fa0a5a4`), pre-declared, before any check was run: R2.1 frozen M2g preprocessing and guard quoted with line numbers;
   R2.2 what the A15 9 v 3 June file already contained (part of the event-pair result was already seen); R2.3 dates and provenance of A17/A18;
   R2.4 WorldCover class 80 as the only sea-mask fallback; R2.5 the **UN-SPIDER ratio 1.25 sensitivity** variant.
3. **Step 2 run and outputs** (`5b9acdc`). Includes the **POST-HOC** file `results/accra/accra_cd_POSTHOC_median_dvv.json`. That median-dVV diagnostic was
   run before it was written into the protocol (it was logged afterwards, in A19-R3's text), so it is post-hoc and was not pre-declared.
4. **A19-R3** (`ee49938`, registration `269e6f5`), **POST-HOC**, rules committed before the rainfall was computed: IMERG daily and 24 h-before-pass table.
   Outputs committed in `226ab51`.
5. **A19-R4** (`933c832`), **POST-HOC**, rules committed before running: R4.0 record of Step 3 category (c); R4.1 half-hourly IMERG 7-12 June; R4.2 Sentinel-1
   acquisition list after the 9 June pass. Step 3 outputs and scripts 11/12a/12 committed in `226ab51`; R4 outputs and script 13 in `de15712`.
6. **A19-R5** (`65d511d`, registration `967f935`), pre-run: Step 4 geocoding rule, site list, control spacing, interpretation limit. Step 4 outputs: `b807426`.

Exploratory labels (A15 and earlier, disclosed in A19.1): `exploratory_delta_vv_diagnostic.json` (9 v 3 June, earlier session),
`exploratory_delta_vv_3v15_diagnostic.json` and the tiled M2g tables `accra_m2g_tiled_tables.*` (committed in `d2b2985`).

## 3. Step 2: change-detection baseline (`results/accra_cd_baseline.csv`, map `results/accra_cd_event_pair_map.png`)

Rules [A]: median-3 filter, no clip (frozen M2g preprocessing, `accra_pooled.yaml` lines 50-52); dVV = VV(second) - VV(first); CD if dVV < -3 dB (**-3 dB is an
assumption: no published source confirmed**); guarded CD also needs VV(second) < -15 dB (frozen guard, lines 64-65; applied per pixel here, per cluster in the frozen
pipeline); brightening if dVV > +3 dB; JRC water (occurrence >= 50) removed; domain = valid in both scenes. Headline pairs: event 3 to 9 June, control 28 May to 3 June,
recession 9 to 15 June. Sensitivity (label "same-satellite sensitivity"): event 28 May to 9 June (S1A to S1A), control 22 May to 3 June (S1B to S1B).

**Event minus control, headline pairs [M].**

{hl}

**Event minus control, same-satellite sensitivity [M].**

{ss}

**Recession, 9 to 15 June, hectares, no control pair [M].**

{rec_t}

**POST-HOC median dVV per pair, full-AOI domain (not pre-declared) [M].**

{med_t}

**What this says.** In the headline pairs the event pair does **not** stand out from the control pair for decrease: CD event minus control is
{g('headline','cd','full_Odaw_AOI','event_minus_control').event_minus_control_ha:+,.0f} ha in the full AOI (event {g('headline','cd','full_Odaw_AOI','event').flagged_ha:,.0f} ha,
control {g('headline','cd','full_Odaw_AOI','control').flagged_ha:,.0f} ha) and negative in every sub-area [M]. The same-satellite sensitivity reverses the sign
({g('same-satellite sensitivity','cd','full_Odaw_AOI','event_minus_control').event_minus_control_ha:+,.0f} ha in the full AOI) [M]. Brightening also reverses. The median-dVV
table points to a scene-wide level shift, not a satellite offset: 28 May is about 1.5 dB brighter than 3 June and, by subtraction, about 2.2 dB brighter than 22 May, so any pair
with 28 May as reference flags a lot of decrease [E, additive from medians]. Neither pair set is therefore a clean control, and the fixed -3 dB rule has no offset correction.
**No offset-corrected CD was run (owner's decision).** Already seen before this step (raw, unfiltered, A15 file; see A19-R2.2): the +3 dB brightening hectares for the event pair
(3,553 ha full AOI) and a lower bound of about 1,300 ha on the raw event-pair decrease. Every number in the tables above is first seen now (filtered inputs; new pairs).
Guarded CD flags almost nothing in any pair (event, full AOI {g('headline','cd_guarded','full_Odaw_AOI','event').flagged_ha:.1f} ha) [M].

## 4. Step 3: coastal positive control (`results/accra_coastal_control.csv`, `results/accra_coastal_control_map.png`)

The frozen M2g on 9 June, recomputed with `scripts/06`'s whole-raster procedure with no AOI restriction, accepts **144,927** pixels, equal to the declared count [M]; 188 of them lie inside the
AOI (1.88 ha, equal to the original `accra_tables.json`) [M].

{cc_t}

Category (c) Korle Lagoon: **not computed (Nominatim/Overpass unavailable); bounded above by category (d) = 2.8%.** Nominatim had no object named "Korle Lagoon" (0 matches over four phrasings);
Overpass returned HTTP 502 twice. I make no statement about where the lagoon lies relative to JRC water. Category (b) is the **fallback** (WorldCover v100 class 80, not in (a)) because the OSM
coastline query failed [A, A19-R2.4]; WorldCover class 80 also covers lagoons and reservoirs, so it is not a pure sea mask. (d) was below 50%, so the land-cover breakdown was not triggered.
99.9% of the accepted pixels (144,739) are outside the AOI. [M]

## 5. POST-HOC checks: rainfall and Sentinel-1 acquisitions (A19-R3, A19-R4)

IMERG V07, area mean over the Odaw AOI, about 11 km pixels. **24 h before each pass [M]:**

{rain_b}

All five windows are labelled "rain" because the declared rule (exactly 0.00 mm) is met by none; the label does not separate the dates, and I did not change the rule.

Note on the two rain columns (corrected 2026-11-16; the CSV is unchanged). The column called `max_pixel_mm` in `results/accra_POSTHOC_rainfall.csv` is **not** the wettest pixel
touching the basin. Earth Engine's `mean` reducer weights every IMERG pixel by the fraction of it that lies inside the AOI, but its `max` and `count` reducers use only pixels whose
centre lies inside the AOI [A: Earth Engine's documented reducer behaviour, not re-tested here]. `imerg_pixels_in_aoi` reads 1 on every row [M], so exactly one pixel centre is inside the
AOI and the "max" is simply that one pixel's value. That is why it is smaller than the area mean in three of the five rows above, which a true maximum could never be. Read the column
as "the one IMERG pixel centred in the AOI"; the area mean is the number used everywhere else.

Daily area-mean (UTC day) is {d8:.2f} mm on 8 June, {d9:.2f} mm on 9 June and {d10:.2f} mm on 10 June [M]. The six largest half-hour slices (mm per 30 min, 7-12 June) are {top6_txt} [M], all on 10 June, 15:30-18:00 UTC,
about 21 h after the 9 June 18:18 pass. **IMERG neither confirms nor contradicts the 8 to 9 June reports:** an area mean over about 11 km pixels, smeared over a basin about 10 km wide, cannot settle
whether a short local storm fell on the night of 8 to 9 June; what it does show is that the heaviest rain in 7-12 June came after the 9 June pass [M, E]. Table and bar chart:
`results/accra_POSTHOC_rainfall_halfhourly_7_12_june.csv/.png`.

**Sentinel-1 GRD scenes intersecting the AOI, 9 Jun 18:18:00 to 12 Jun 23:59:59 UTC (all orbits, both pass directions) [M, Earth Engine catalogue only]:**

{s1_t}

Only the 9 June pass itself is listed; nothing else is in Earth Engine for that window. A scene absent from Earth Engine is not shown to be absent from the Sentinel-1 archive, and I did not switch to the Copernicus Data Space Ecosystem.

## 6. Step 4: point checks (`results/accra_point_checks.csv`, `results/accra_point_checks_dvv_hist.png`)

Sites and centroids follow the owner's rule in A19-R5 (headline = the OSM object matching the named landmark, else the `place=*` node; every other candidate is an "alternative centroid" row). Buffers: 50 m
(headline) and 100 m (pre-declared sensitivity). Flags are the frozen B1, B2g (VH), M1g, M2g on the 9 June image and the CD / guarded CD rules of the event pair. **15 June columns are shown only because A19.7 asks
for them; they are not evidence about 9 June.** Percentile = mid-rank among the 200 controls (seed 20200609, WorldCover built-up, whole 100 m buffer inside the AOI, at least 100 m from every site centroid and from each other).

**How large a change a site needed in order to stand out (5th and 95th percentiles of the 200 controls) [M].**

{cp_t}

At 50 m a site's 9 June VV had to be below {v50[0]:.2f} dB or above {v50[2]:.2f} dB, and its dVV (3 to 9 June) below {d50[0]:+.2f} dB or above {d50[2]:+.2f} dB, to count as standing out (percentile below 5
or above 95); at 100 m the limits are VV below {v100[0]:.2f} or above {v100[2]:.2f} dB and dVV below {d100[0]:+.2f} or above {d100[2]:+.2f} dB. Relative to the control medians that is a change of roughly
{d50[1] - d50[0]:.1f} dB lower or {d50[2] - d50[1]:.1f} dB higher in dVV at 50 m ({d100[1] - d100[0]:.1f} dB lower or {d100[2] - d100[1]:.1f} dB higher at 100 m) [M, arithmetic on the table].

**Headline sites, 50 m [M].**

{site_table(50)}

**All centroids, 100 m sensitivity [M].**

{site_table(100)}

**Result.** None of the four headline sites (50 m) stands out from the controls on 9 June VV or on dVV: percentiles {', '.join(f'{r.site} {r.pctile_rank_VV9:.1f}/{r.pctile_rank_dVV:.1f}' for r in head50.itertuples())} (VV / dVV) [M].
None of B1, B2g, M1g or M2g flags any pixel at a headline site, and CD flags 0-3% [M]. Across all 14 centroids and both buffers, {n_out} of {n_ranks} percentile ranks fall outside 5-95;
about {0.10 * n_ranks:.1f} would be expected by chance alone if they were independent, which they are not [E]. Read only as a test of the 8-9 June overnight storm: not standing out is **not** evidence of no flooding, because the
pass is later than the reported storm, IMERG shows little rain on 8 to 9 June at its resolution (above), and a 50 m buffer holds about 80 ten-metre pixels with speckle. It is not validation either way.

**Centroid choice moves the site percentiles widely, so a single 50 m buffer is dominated by location noise.** At 50 m, the Kwame Nkrumah Circle 9 June VV percentile runs from {circ.min():.1f} to {circ.max():.1f} across its candidate
centroids, which are only 51-81 m apart; Odawna runs from {odaw.min():.1f} to {odaw.max():.1f} and Taifa from {taifa.min():.1f} to {taifa.max():.1f} [M]. Candidate centroids only tens of metres apart gave percentiles spanning most of the 0-100 range, so
no single-buffer result should be read as a property of the named place.

## 7. What did not go to plan

- **-3 dB has no confirmed source [A].** ALTIS (arXiv 2603.13803) quotes "3-8 dB" second-hand and itself uses mean - 2 sd; UN-SPIDER's 1.25 ratio is trial and error with no source. Two other candidates were unreadable.
- **UN-SPIDER dB-versus-linear reading unverified [A].** The page does not say; its script returned HTTP 403. I used the literal reading (dB values divided) and ran no alternative.
- **Neither pair set gives a clean control** (28 May level shift, section 3), and no offset-corrected CD was run, by the owner's decision.
- **Sea mask is the WorldCover fallback** because Overpass returned 502; **Korle Lagoon (c) was not computed.**
- **The rain/no-rain label is uninformative** (all five windows "rain" under the exact-zero rule); the CSV's `max_pixel_mm` column is the single IMERG pixel centred in the AOI, not a maximum (section 5 note).
- **The post-hoc median-dVV diagnostic was run before it was logged** in the protocol (logged in A19-R3). It is labelled POST-HOC in file name and header.
- **Palette validator could not run** (Node 12 too old); the Okabe-Ito orange/blue pair used on the Step 2 map was not checked with the script. The Step 2 map legend overlaps the southern tip of the AOI, and the Step 3 figure has unused white space.
- **Amendment naming:** revisions are called A19-R2 to R5, not "A19.2", because A19.2 already names the scene table. The protocol file also carried uncommitted Amendments 17 and 18, which were committed with A19.
- **Geocoding:** several OSM matches per site; the owner chose the rule, and the Taifa choice was changed once. Controls are kept 100 m from every centroid used, not only the four headline points (change recorded in A19-R5.2).
- **No unit tests were written for the new scripts 08-14** (tile bounds, buffer geometry, percentile rank). The existing suite does not cover them.
- **The 9 June pass precedes the heaviest rain** (10 June, 15:30-18:00 UTC), which weakens every 9 June check as a test of anything on 10-12 June; and the 8-9 June premise itself is only weakly visible in IMERG.
- A README did not exist; one was created (see `README.md`).

## 8. Verification at hand-back [M]

- Test suite: `PYTHONPATH=. python -m pytest -q` gave **148 passed** (11 s).
- Frozen files unchanged: `sha256sum -c` of the 27 pre-run hashes in `results/accra_followup_registration.txt` (`configs/config.yaml`, `results/tuning/heldout_lock.json` and the 25 `results/frozen/**/*.yaml`)
  gave **27 OK, 0 failed**; `git status` shows nothing modified under `results/frozen`, `results/tuning` or `configs`.
- Protocol hash chain: {hash_chain}
- `data/` is git-ignored, so the WorldCover raster is not in git; its SHA-256 is in `results/accra_followup_data_hashes.txt`.

## 9. Output index

Step 2: `scripts/10a_fetch_may_scenes.py`, `10_accra_cd_baseline.py`, `10b_accra_cd_map_and_offsets.py`; `results/accra_cd_baseline.csv`, `results/accra_cd_event_pair_map.png`, `results/accra/accra_cd_baseline_raw.json`,
`results/accra/accra_cd_POSTHOC_median_dvv.json`. Step 3: `scripts/12a_fetch_worldcover.py`, `12_accra_coastal_control.py`; `results/accra_coastal_control.csv`, `.png`. POST-HOC: `scripts/11_accra_POSTHOC_rainfall.py`,
`13_accra_POSTHOC_rain_halfhourly_and_s1_list.py`; `results/accra_POSTHOC_*`. Step 4: `scripts/14_accra_point_checks.py`; `results/accra_point_checks.csv`, `results/accra_point_checks_dvv_hist.png`. Summary generator: `scripts/15_accra_followup_summary.py`.
Reproduction commands: `README.md`.
"""
(R / "accra_followup_summary.md").write_text(txt)
print("written results/accra_followup_summary.md", len(txt), "chars")
