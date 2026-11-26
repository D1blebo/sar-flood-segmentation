# Accra follow-up checks: summary (Amendment 19)

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

| rule | area | event minus control (ha) | event minus control (pp of valid domain) | event (ha) | control (ha) |
|---|---|---|---|---|---|
| CD (dVV < -3 dB) [A] | full_Odaw_AOI | -5,343.74 | -20.52 | 994.11 | 6,337.85 |
| CD (dVV < -3 dB) [A] | core | -150.48 | -17.86 | 28.08 | 178.56 |
| CD (dVV < -3 dB) [A] | kaneshie | -47.88 | -21.69 | 6.11 | 53.99 |
| CD (dVV < -3 dB) [A] | darkuman_clipped | -69.21 | -16.10 | 9.32 | 78.53 |
| CD (dVV < -3 dB) [A] | pooled | -267.57 | -17.92 | 43.51 | 311.08 |
| guarded CD [A] | full_Odaw_AOI | -54.78 | -0.21 | 22.91 | 77.69 |
| guarded CD [A] | core | -0.96 | -0.11 | 0.42 | 1.38 |
| guarded CD [A] | kaneshie | -0.52 | -0.24 | 0.09 | 0.61 |
| guarded CD [A] | darkuman_clipped | -0.71 | -0.17 | 0.05 | 0.76 |
| guarded CD [A] | pooled | -2.19 | -0.15 | 0.56 | 2.75 |
| brightening (dVV > +3 dB) [A] | full_Odaw_AOI | +1,511.22 | +5.80 | 2,021.14 | 509.92 |
| brightening (dVV > +3 dB) [A] | core | +47.59 | +5.65 | 76.58 | 28.99 |
| brightening (dVV > +3 dB) [A] | kaneshie | +11.75 | +5.32 | 16.77 | 5.02 |
| brightening (dVV > +3 dB) [A] | darkuman_clipped | +25.10 | +5.84 | 36.35 | 11.25 |
| brightening (dVV > +3 dB) [A] | pooled | +84.44 | +5.66 | 129.70 | 45.26 |
| UN-SPIDER ratio 1.25, VH [A] | full_Odaw_AOI | -3,047.58 | -11.70 | 1,080.43 | 4,128.01 |
| UN-SPIDER ratio 1.25, VH [A] | core | -45.80 | -5.44 | 39.67 | 85.47 |
| UN-SPIDER ratio 1.25, VH [A] | kaneshie | -16.76 | -7.59 | 9.45 | 26.21 |
| UN-SPIDER ratio 1.25, VH [A] | darkuman_clipped | -24.91 | -5.80 | 15.43 | 40.34 |
| UN-SPIDER ratio 1.25, VH [A] | pooled | -87.47 | -5.86 | 64.55 | 152.02 |
| UN-SPIDER ratio 1.25, VV [A] | full_Odaw_AOI | -7,737.82 | -29.71 | 3,289.51 | 11,027.33 |
| UN-SPIDER ratio 1.25, VV [A] | core | -199.51 | -23.68 | 130.73 | 330.24 |
| UN-SPIDER ratio 1.25, VV [A] | kaneshie | -71.01 | -32.17 | 27.16 | 98.17 |
| UN-SPIDER ratio 1.25, VV [A] | darkuman_clipped | -116.84 | -27.19 | 50.96 | 167.80 |
| UN-SPIDER ratio 1.25, VV [A] | pooled | -387.36 | -25.94 | 208.85 | 596.21 |

**Event minus control, same-satellite sensitivity [M].**

| rule | area | event minus control (ha) | event minus control (pp of valid domain) | event (ha) | control (ha) |
|---|---|---|---|---|---|
| CD (dVV < -3 dB) [A] | full_Odaw_AOI | +4,246.07 | +16.30 | 5,004.20 | 758.13 |
| CD (dVV < -3 dB) [A] | core | +93.13 | +11.05 | 125.66 | 32.53 |
| CD (dVV < -3 dB) [A] | kaneshie | +30.28 | +13.72 | 38.23 | 7.95 |
| CD (dVV < -3 dB) [A] | darkuman_clipped | +33.75 | +7.85 | 45.72 | 11.97 |
| CD (dVV < -3 dB) [A] | pooled | +157.16 | +10.53 | 209.61 | 52.45 |
| guarded CD [A] | full_Odaw_AOI | +27.83 | +0.11 | 52.17 | 24.34 |
| guarded CD [A] | core | +0.21 | +0.02 | 0.61 | 0.40 |
| guarded CD [A] | kaneshie | +0.03 | +0.01 | 0.21 | 0.18 |
| guarded CD [A] | darkuman_clipped | -0.11 | -0.03 | 0.11 | 0.22 |
| guarded CD [A] | pooled | +0.13 | +0.01 | 0.93 | 0.80 |
| brightening (dVV > +3 dB) [A] | full_Odaw_AOI | -2,518.68 | -9.67 | 662.21 | 3,180.89 |
| brightening (dVV > +3 dB) [A] | core | -46.48 | -5.52 | 38.59 | 85.07 |
| brightening (dVV > +3 dB) [A] | kaneshie | -15.62 | -7.08 | 5.47 | 21.09 |
| brightening (dVV > +3 dB) [A] | darkuman_clipped | -21.59 | -5.02 | 15.50 | 37.09 |
| brightening (dVV > +3 dB) [A] | pooled | -83.69 | -5.61 | 59.56 | 143.25 |
| UN-SPIDER ratio 1.25, VH [A] | full_Odaw_AOI | +2,982.96 | +11.45 | 3,758.79 | 775.83 |
| UN-SPIDER ratio 1.25, VH [A] | core | +38.38 | +4.56 | 72.40 | 34.02 |
| UN-SPIDER ratio 1.25, VH [A] | kaneshie | +15.04 | +6.81 | 24.35 | 9.31 |
| UN-SPIDER ratio 1.25, VH [A] | darkuman_clipped | +21.57 | +5.02 | 34.31 | 12.74 |
| UN-SPIDER ratio 1.25, VH [A] | pooled | +74.99 | +5.02 | 131.06 | 56.07 |
| UN-SPIDER ratio 1.25, VV [A] | full_Odaw_AOI | +7,142.63 | +27.42 | 9,613.56 | 2,470.93 |
| UN-SPIDER ratio 1.25, VV [A] | core | +150.10 | +17.81 | 276.19 | 126.09 |
| UN-SPIDER ratio 1.25, VV [A] | kaneshie | +55.26 | +25.04 | 82.26 | 27.00 |
| UN-SPIDER ratio 1.25, VV [A] | darkuman_clipped | +79.66 | +18.53 | 130.25 | 50.59 |
| UN-SPIDER ratio 1.25, VV [A] | pooled | +285.02 | +19.09 | 488.70 | 203.68 |

**Recession, 9 to 15 June, hectares, no control pair [M].**

| rule | full_Odaw_AOI | core | kaneshie | darkuman_clipped | pooled |
|---|---|---|---|---|---|
| CD (dVV < -3 dB) [A] | 1,997.14 | 80.03 | 16.33 | 37.15 | 133.51 |
| guarded CD [A] | 34.07 | 0.98 | 0.18 | 1.10 | 2.26 |
| brightening (dVV > +3 dB) [A] | 970.78 | 27.34 | 5.89 | 9.20 | 42.43 |
| UN-SPIDER ratio 1.25, VH [A] | 1,494.25 | 54.82 | 11.61 | 25.25 | 91.68 |
| UN-SPIDER ratio 1.25, VV [A] | 5,591.39 | 237.43 | 51.48 | 111.44 | 400.35 |

**POST-HOC median dVV per pair, full-AOI domain (not pre-declared) [M].**

| pair set | role | dates | median dVV (dB) | mean dVV (dB) |
|---|---|---|---|---|
| headline | event | 2020-06-03->2020-06-09 | +0.346 | +0.355 |
| headline | control | 2020-05-28->2020-06-03 | -1.464 | -1.562 |
| headline | recession | 2020-06-09->2020-06-15 | -0.338 | -0.353 |
| same-satellite sensitivity | event | 2020-05-28->2020-06-09 | -1.096 | -1.207 |
| same-satellite sensitivity | control | 2020-05-22->2020-06-03 | +0.691 | +0.729 |

**What this says.** In the headline pairs the event pair does **not** stand out from the control pair for decrease: CD event minus control is
-5,344 ha in the full AOI (event 994 ha,
control 6,338 ha) and negative in every sub-area [M]. The same-satellite sensitivity reverses the sign
(+4,246 ha in the full AOI) [M]. Brightening also reverses. The median-dVV
table points to a scene-wide level shift, not a satellite offset: 28 May is about 1.5 dB brighter than 3 June and, by subtraction, about 2.2 dB brighter than 22 May, so any pair
with 28 May as reference flags a lot of decrease [E, additive from medians]. Neither pair set is therefore a clean control, and the fixed -3 dB rule has no offset correction.
**No offset-corrected CD was run (owner's decision).** Already seen before this step (raw, unfiltered, A15 file; see A19-R2.2): the +3 dB brightening hectares for the event pair
(3,553 ha full AOI) and a lower bound of about 1,300 ha on the raw event-pair decrease. Every number in the tables above is first seen now (filtered inputs; new pairs).
Guarded CD flags almost nothing in any pair (event, full AOI 22.9 ha) [M].

## 4. Step 3: coastal positive control (`results/accra_coastal_control.csv`, `results/accra_coastal_control_map.png`)

The frozen M2g on 9 June, recomputed with `scripts/06`'s whole-raster procedure with no AOI restriction, accepts **144,927** pixels, equal to the declared count [M]; 188 of them lie inside the
AOI (1.88 ha, equal to the original `accra_tables.json`) [M].

| category | pixels | share of accepted | inside AOI | outside AOI |
|---|---|---|---|---|
| (a) JRC permanent water | 139449 | 96.2% | 70 | 139379 |
| (b) sea = WorldCover v100 class 80, not in (a) [FALLBACK per A19-R2.4] | 1412 | 1.0% | 69 | 1343 |
| (c) Korle Lagoon: not computed (Nominatim/Overpass unavailable); bounded above by category (d) = 2.8% | not computed | not computed | not computed | not computed |
| (d) none of the above | 4066 | 2.8% | 49 | 4017 |
| total accepted | 144927 | 100.0% | 188 | 144739 |

Category (c) Korle Lagoon: **not computed (Nominatim/Overpass unavailable); bounded above by category (d) = 2.8%.** Nominatim had no object named "Korle Lagoon" (0 matches over four phrasings);
Overpass returned HTTP 502 twice. I make no statement about where the lagoon lies relative to JRC water. Category (b) is the **fallback** (WorldCover v100 class 80, not in (a)) because the OSM
coastline query failed [A, A19-R2.4]; WorldCover class 80 also covers lagoons and reservoirs, so it is not a pure sea mask. (d) was below 50%, so the land-cover breakdown was not triggered.
99.9% of the accepted pixels (144,739) are outside the AOI. [M]

## 5. POST-HOC checks: rainfall and Sentinel-1 acquisitions (A19-R3, A19-R4)

IMERG V07, area mean over the Odaw AOI, about 11 km pixels. **24 h before each pass [M]:**

| pass (UTC) | window (UTC) | slices | area-mean (mm) | pixel with centre in AOI (mm) | rain / no rain (exactly 0.00 mm rule) |
|---|---|---|---|---|---|
| 2020-05-22 18:17:24 UTC | 2020-05-21T18:00 to 2020-05-22T18:00 | 48 | 0.16 | 0.14 | rain |
| 2020-05-28 18:18:04 UTC | 2020-05-27T18:00 to 2020-05-28T18:00 | 48 | 20.76 | 24.34 | rain |
| 2020-06-03 18:17:25 UTC | 2020-06-02T18:00 to 2020-06-03T18:00 | 48 | 1.28 | 1.37 | rain |
| 2020-06-09 18:18:05 UTC | 2020-06-08T18:00 to 2020-06-09T18:00 | 48 | 4.13 | 3.39 | rain |
| 2020-06-15 18:17:25 UTC | 2020-06-14T18:00 to 2020-06-15T18:00 | 48 | 0.88 | 0.35 | rain |

All five windows are labelled "rain" because the declared rule (exactly 0.00 mm) is met by none; the label does not separate the dates, and I did not change the rule.

Note on the two rain columns (corrected 2026-11-16; the CSV is unchanged). The column called `max_pixel_mm` in `results/accra_POSTHOC_rainfall.csv` is **not** the wettest pixel
touching the basin. Earth Engine's `mean` reducer weights every IMERG pixel by the fraction of it that lies inside the AOI, but its `max` and `count` reducers use only pixels whose
centre lies inside the AOI [A: Earth Engine's documented reducer behaviour, not re-tested here]. `imerg_pixels_in_aoi` reads 1 on every row [M], so exactly one pixel centre is inside the
AOI and the "max" is simply that one pixel's value. That is why it is smaller than the area mean in three of the five rows above, which a true maximum could never be. Read the column
as "the one IMERG pixel centred in the AOI"; the area mean is the number used everywhere else.

Daily area-mean (UTC day) is 0.11 mm on 8 June, 4.47 mm on 9 June and 76.84 mm on 10 June [M]. The six largest half-hour slices (mm per 30 min, 7-12 June) are 06-10 16:30=9.33, 06-10 15:30=9.22, 06-10 16:00=8.80, 06-10 17:00=6.97, 06-10 17:30=6.59, 06-10 18:00=6.42 [M], all on 10 June, 15:30-18:00 UTC,
about 21 h after the 9 June 18:18 pass. **IMERG neither confirms nor contradicts the 8 to 9 June reports:** an area mean over about 11 km pixels, smeared over a basin about 10 km wide, cannot settle
whether a short local storm fell on the night of 8 to 9 June; what it does show is that the heaviest rain in 7-12 June came after the 9 June pass [M, E]. Table and bar chart:
`results/accra_POSTHOC_rainfall_halfhourly_7_12_june.csv/.png`.

**Sentinel-1 GRD scenes intersecting the AOI, 9 Jun 18:18:00 to 12 Jun 23:59:59 UTC (all orbits, both pass directions) [M, Earth Engine catalogue only]:**

| scene_id | start_utc | platform | mode | polarisations | pass | relative_orbit | hours_after_9jun_1818_pass | aoi_fraction_in_footprint | note |
|---|---|---|---|---|---|---|---|---|---|
| S1A_IW_GRDH_1SDV_20200609T181805_20200609T181834_032944_03D0DF_47E9 | 2020-06-09T18:18:05+00:00 | A | IW | VV+VH | ASCENDING | 147 | 0.0 | 1 | the 9 June orbit-147 pass used in the study |

Only the 9 June pass itself is listed; nothing else is in Earth Engine for that window. A scene absent from Earth Engine is not shown to be absent from the Sentinel-1 archive, and I did not switch to the Copernicus Data Space Ecosystem.

## 6. Step 4: point checks (`results/accra_point_checks.csv`, `results/accra_point_checks_dvv_hist.png`)

Sites and centroids follow the owner's rule in A19-R5 (headline = the OSM object matching the named landmark, else the `place=*` node; every other candidate is an "alternative centroid" row). Buffers: 50 m
(headline) and 100 m (pre-declared sensitivity). Flags are the frozen B1, B2g (VH), M1g, M2g on the 9 June image and the CD / guarded CD rules of the event pair. **15 June columns are shown only because A19.7 asks
for them; they are not evidence about 9 June.** Percentile = mid-rank among the 200 controls (seed 20200609, WorldCover built-up, whole 100 m buffer inside the AOI, at least 100 m from every site centroid and from each other).

**How large a change a site needed in order to stand out (5th and 95th percentiles of the 200 controls) [M].**

| buffer | quantity | n | 5th percentile | median | 95th percentile | 5th below median | 95th above median |
|---|---|---|---|---|---|---|---|
| 50 m | 9 June VV (dB) | 200 | -10.189 | -7.392 | -2.613 | -2.797 | +4.779 |
| 50 m | dVV 3 to 9 June (dB) | 200 | -1.000 | +0.431 | +1.552 | -1.431 | +1.121 |
| 100 m | 9 June VV (dB) | 200 | -9.421 | -7.326 | -3.473 | -2.095 | +3.853 |
| 100 m | dVV 3 to 9 June (dB) | 200 | -0.566 | +0.490 | +1.140 | -1.055 | +0.650 |

At 50 m a site's 9 June VV had to be below -10.19 dB or above -2.61 dB, and its dVV (3 to 9 June) below -1.00 dB or above +1.55 dB, to count as standing out (percentile below 5
or above 95); at 100 m the limits are VV below -9.42 or above -3.47 dB and dVV below -0.57 or above +1.14 dB. Relative to the control medians that is a change of roughly
1.4 dB lower or 1.1 dB higher in dVV at 50 m (1.1 dB lower or 0.7 dB higher at 100 m) [M, arithmetic on the table].

**Headline sites, 50 m [M].**

| site | centroid | OSM object | n valid px | 9 Jun VV (dB) | VV pctile | dVV 3-9 Jun (dB) | dVV pctile | VV 3 Jun | VV 15 Jun (not 9 Jun evidence) | B1 | B2g VH | M1g | M2g | CD | guarded CD | stands out (VV / dVV) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Odawna | headline | way 664056985 Odawna Market | 80 | -6.78 | 62.5 | +0.64 | 59.5 | -7.60 | -8.08 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | False / False |
| Odawna | alternative centroid | way 126879329 Odawna Close (residential) | 80 | -2.41 | 95.5 | +1.10 | 83.0 | -3.52 | -4.44 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | True / False |
| Odawna | alternative centroid | way 1488444430 Odawna Close (service) | 79 | -5.80 | 77.5 | -0.33 | 16.5 | -6.59 | -5.95 | 0.00 | 0.00 | 0.00 | 0.00 | 0.04 | 0.00 | False / False |
| Kwame Nkrumah Circle | headline | node 1133566054 Kwame Nkrumah Interchange | 79 | -9.38 | 10.0 | -0.12 | 26.5 | -8.99 | -9.39 | 0.00 | 0.00 | 0.00 | 0.00 | 0.03 | 0.00 | False / False |
| Kwame Nkrumah Circle | alternative centroid | way 11664610 | 78 | -9.82 | 7.0 | +0.77 | 67.0 | -10.59 | -10.19 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | False / False |
| Kwame Nkrumah Circle | alternative centroid | way 510252753 | 79 | -9.16 | 13.0 | +0.80 | 68.0 | -8.92 | -9.03 | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 | 0.00 | False / False |
| Kwame Nkrumah Circle | alternative centroid | way 510252751 | 80 | -4.87 | 84.5 | -0.25 | 21.0 | -5.03 | -4.30 | 0.00 | 0.00 | 0.00 | 0.00 | 0.05 | 0.00 | False / False |
| Kwame Nkrumah Circle | alternative centroid | way 510252749 | 78 | -9.38 | 10.0 | -0.00 | 29.0 | -8.87 | -8.82 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | False / False |
| Kwame Nkrumah Circle | alternative centroid | mean of the four segment points (computed) | 77 | -9.38 | 10.0 | -0.25 | 21.0 | -8.95 | -9.24 | 0.00 | 0.00 | 0.00 | 0.00 | 0.04 | 0.00 | False / False |
| Taifa | headline | node 9703337660 Taifa (place=suburb) | 81 | -9.07 | 15.5 | +0.21 | 42.0 | -8.81 | -9.66 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | False / False |
| Taifa | alternative centroid | node 5008220723 Taifa bus stop | 78 | -7.88 | 38.5 | +0.51 | 54.0 | -8.18 | -9.21 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | False / False |
| Taifa | alternative centroid | way 628294317 Accra Nsawam Highway | 78 | -12.15 | 0.5 | +1.75 | 98.0 | -13.41 | -12.99 | 0.00 | 0.05 | 0.00 | 0.00 | 0.00 | 0.00 | True / True |
| Taifa | alternative centroid | way 1517822465 Charismatic Baptist Church | 78 | -8.63 | 22.5 | +0.46 | 52.5 | -9.15 | -9.19 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | False / False |
| Lapaz | headline | node 5566513301 Lapaz (place=suburb) | 79 | -4.79 | 86.5 | -0.16 | 25.5 | -5.63 | -5.52 | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 | 0.00 | False / False |

**All centroids, 100 m sensitivity [M].**

| site | centroid | OSM object | n valid px | 9 Jun VV (dB) | VV pctile | dVV 3-9 Jun (dB) | dVV pctile | VV 3 Jun | VV 15 Jun (not 9 Jun evidence) | B1 | B2g VH | M1g | M2g | CD | guarded CD | stands out (VV / dVV) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Odawna | headline | way 664056985 Odawna Market | 316 | -6.90 | 61.5 | +1.17 | 95.5 | -7.60 | -8.04 | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 | 0.00 | False / True |
| Odawna | alternative centroid | way 126879329 Odawna Close (residential) | 315 | -2.78 | 97.5 | +1.08 | 91.0 | -3.95 | -4.46 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | True / False |
| Odawna | alternative centroid | way 1488444430 Odawna Close (service) | 317 | -5.25 | 86.5 | +0.86 | 82.0 | -6.51 | -5.42 | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 | 0.00 | False / False |
| Kwame Nkrumah Circle | headline | node 1133566054 Kwame Nkrumah Interchange | 313 | -8.36 | 26.0 | +0.61 | 62.0 | -8.88 | -8.12 | 0.00 | 0.00 | 0.00 | 0.00 | 0.03 | 0.00 | False / False |
| Kwame Nkrumah Circle | alternative centroid | way 11664610 | 312 | -8.36 | 26.0 | +0.50 | 52.0 | -8.94 | -8.24 | 0.00 | 0.00 | 0.00 | 0.00 | 0.02 | 0.00 | False / False |
| Kwame Nkrumah Circle | alternative centroid | way 510252753 | 316 | -8.49 | 22.0 | +0.38 | 41.5 | -8.86 | -8.17 | 0.00 | 0.00 | 0.00 | 0.00 | 0.06 | 0.00 | False / False |
| Kwame Nkrumah Circle | alternative centroid | way 510252751 | 316 | -4.58 | 91.5 | +0.54 | 55.5 | -5.06 | -4.58 | 0.00 | 0.00 | 0.00 | 0.00 | 0.02 | 0.00 | False / False |
| Kwame Nkrumah Circle | alternative centroid | way 510252749 | 313 | -6.42 | 74.0 | +0.39 | 41.5 | -6.45 | -7.62 | 0.00 | 0.00 | 0.00 | 0.00 | 0.02 | 0.00 | False / False |
| Kwame Nkrumah Circle | alternative centroid | mean of the four segment points (computed) | 311 | -8.31 | 27.0 | +0.59 | 59.5 | -8.86 | -8.10 | 0.00 | 0.00 | 0.00 | 0.00 | 0.02 | 0.00 | False / False |
| Taifa | headline | node 9703337660 Taifa (place=suburb) | 318 | -8.77 | 13.0 | +0.45 | 46.5 | -9.14 | -9.24 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | False / False |
| Taifa | alternative centroid | node 5008220723 Taifa bus stop | 311 | -8.17 | 28.5 | +0.13 | 26.0 | -8.12 | -8.41 | 0.00 | 0.00 | 0.00 | 0.00 | 0.04 | 0.00 | False / False |
| Taifa | alternative centroid | way 628294317 Accra Nsawam Highway | 314 | -10.07 | 2.5 | +0.59 | 59.0 | -10.83 | -11.16 | 0.00 | 0.06 | 0.00 | 0.00 | 0.01 | 0.00 | True / False |
| Taifa | alternative centroid | way 1517822465 Charismatic Baptist Church | 313 | -7.63 | 39.5 | +0.78 | 77.5 | -8.50 | -8.42 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | False / False |
| Lapaz | headline | node 5566513301 Lapaz (place=suburb) | 318 | -6.51 | 73.5 | -0.01 | 19.0 | -6.61 | -6.77 | 0.00 | 0.00 | 0.00 | 0.00 | 0.04 | 0.00 | False / False |

**Result.** None of the four headline sites (50 m) stands out from the controls on 9 June VV or on dVV: percentiles Odawna 62.5/59.5, Kwame Nkrumah Circle 10.0/26.5, Taifa 15.5/42.0, Lapaz 86.5/25.5 (VV / dVV) [M].
None of B1, B2g, M1g or M2g flags any pixel at a headline site, and CD flags 0-3% [M]. Across all 14 centroids and both buffers, 6 of 56 percentile ranks fall outside 5-95;
about 5.6 would be expected by chance alone if they were independent, which they are not [E]. Read only as a test of the 8-9 June overnight storm: not standing out is **not** evidence of no flooding, because the
pass is later than the reported storm, IMERG shows little rain on 8 to 9 June at its resolution (above), and a 50 m buffer holds about 80 ten-metre pixels with speckle. It is not validation either way.

**Centroid choice moves the site percentiles widely, so a single 50 m buffer is dominated by location noise.** At 50 m, the Kwame Nkrumah Circle 9 June VV percentile runs from 7.0 to 84.5 across its candidate
centroids, which are only 51-81 m apart; Odawna runs from 62.5 to 95.5 and Taifa from 0.5 to 38.5 [M]. Candidate centroids only tens of metres apart gave percentiles spanning most of the 0-100 range, so
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
- Protocol hash chain: at the Amendment 19 hand-back the `results/evaluation_protocol.md` sha256 was 0e5de3e8534868dc... (the R5 line of the registration record) [M]. Later amendments are registered after it; the current file's sha256 459861b528f5f731... equals the latest hash in the registration record [M].
- `data/` is git-ignored, so the WorldCover raster is not in git; its SHA-256 is in `results/accra_followup_data_hashes.txt`.

## 9. Output index

Step 2: `scripts/10a_fetch_may_scenes.py`, `10_accra_cd_baseline.py`, `10b_accra_cd_map_and_offsets.py`; `results/accra_cd_baseline.csv`, `results/accra_cd_event_pair_map.png`, `results/accra/accra_cd_baseline_raw.json`,
`results/accra/accra_cd_POSTHOC_median_dvv.json`. Step 3: `scripts/12a_fetch_worldcover.py`, `12_accra_coastal_control.py`; `results/accra_coastal_control.csv`, `.png`. POST-HOC: `scripts/11_accra_POSTHOC_rainfall.py`,
`13_accra_POSTHOC_rain_halfhourly_and_s1_list.py`; `results/accra_POSTHOC_*`. Step 4: `scripts/14_accra_point_checks.py`; `results/accra_point_checks.csv`, `results/accra_point_checks_dvv_hist.png`. Summary generator: `scripts/15_accra_followup_summary.py`.
Reproduction commands: `README.md`.
