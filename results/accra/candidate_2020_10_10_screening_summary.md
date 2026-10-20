# Candidate screening: 10 October 2020 (Amendment 20)

**Screening only: no imagery pulled, no method run, nothing selected. UNVALIDATED: no ground truth.**
Tags: **[M]** measured by a query or code run (2026-10-20); **[A]** assumed or a rule chosen by the owner or me; **[E]** estimate or reasoning.
Rules: A10.2 unchanged and not relaxed (A20.2). Rules, peak assumption and decision rule were committed before any query (`2c2f431`, registered in `results/accra_followup_registration.txt`).
Script: `scripts/16_accra_candidate_2020_10_10_screening.py`; rows: `results/accra/candidate_2020_10_10_screening.csv`.

## Verdict

**Rule (a): FAIL [M]. Rule (b): not met by any route [M].** By A20.6 (rule (a) fails): **recorded as the 15th candidate, and I stopped.** The frozen pipeline was not run on it, no imagery was pulled,
and the 9 June 2020 event is not replaced.

## Step 1: peak time

- **FloodList, read directly [M]:** "Ghana – Flash Floods Cause Traffic Chaos in Accra", FloodList News, **published 10 October 2020** (the article's own date; this confirms the 2020 year A14.1 found).
  Sentences giving date or time: "Media reported a heavy downpour lasting several hours, early on 10 October, causing floods in areas of Accra and neighbouring Kasoa in Central Region." and
  "Just over 78 mm of rain was recorded at Kotoka International Airport in Accra in 24 hours to 10 October." **The article gives no clock time.**
- **Second named source, found by search and read directly [M]:** Citi Newsroom (Jonas Nyabor), "Saturday morning downpour wreaks havoc in parts of Accra [Photos]", 10 October 2020: "rains from Friday night and
  Saturday morning had left Shalom Estate at Adenta for instance, completely submerged." **No clock time** either, so there is no second clock time to report. I do not choose between the two sources.
- **Assumed peak: 2020-10-10T06:00 UTC [A]** (same convention as A14 for 2019-10-10; Ghana is UTC+0). Bounding window 2020-10-10T00:00 to 12:00 UTC [A].
- Not used: a search-engine synthesis said the rain began Friday night and recorded "about 150mm" over ten hours; I did not read the underlying page, so it is unverified. A Disasters Charter "Flood in Ghana" page is a **2011** activation and is irrelevant.

## Step 2: Sentinel-1 IW GRD over the Odaw AOI, 2020-10-07 00:00 to 2020-10-15 23:59 UTC, all relative orbits, both pass directions [M, Earth Engine catalogue only]

| Scene ID | UTC | Sat | Pass | Rel. orbit | AOI in footprint | h from assumed peak (06:00) | h from window start (00:00) | h from window end (12:00) |
|---|---|---|---|---|---|---|---|---|
| `S1A_IW_GRDH_1SDV_20201007T181811_20201007T181840_034694_040A84_FCDA` | 2020-10-07 18:18:11 | S1A | ascending | 147 | 1.000 | -59.70 | -53.70 | -65.70 |
| `S1B_IW_GRDH_1SDV_20201013T181731_20201013T181756_023798_02D391_111E` | 2020-10-13 18:17:31 | S1B | ascending | 147 | 1.000 | **+84.29** | +90.29 | +78.29 |

Only two IW scenes exist in the window, both on orbit 147 ascending; **no descending scene and no other orbit**. **Rule (a) is FAIL at the assumed peak (+84.29 h), at the window start (+90.29 h) and at the window end
(+78.29 h)** [M]: the first scene after any peak between 00:00 and 12:00 on 10 October is 13 October 18:17:31, far beyond 24 h. The headline verdict is the one at the assumed peak (A20.3); the other two agree.
(This lists Earth Engine's catalogue only; a scene missing there is not shown to be missing from the archive.)

## Step 3: rule (b), only as far as A11.2, A12.2 and A14.3 went

**Sentinel-2 `S2_SR_HARMONIZED`, scenes within +/-3 days of the assumed peak, AOI-clipped SCL cloud fraction (classes 3, 8, 9, 10; 20 m; below 20% needed) [M]:**

| Scene | UTC | h from assumed peak | AOI-clipped cloud | Tile-wide metadata | SCL valid over AOI |
|---|---|---|---|---|---|
| `20201008T102031_20201008T103158_T30NZM` | 2020-10-08 10:39:27 | -43.34 | 64.93% | 74.2% | 0.997 |
| `20201008T102031_20201008T103158_T30NYM` | 2020-10-08 10:39:31 | -43.34 | 59.91% | 61.9% | 0.588 |
| `20201010T101029_20201010T102201_T30NZM` | 2020-10-10 10:29:31 | +4.49 | 100.00% | 95.0% | 1.000 |
| `20201010T101029_20201010T102201_T30NYM` | 2020-10-10 10:29:36 | +4.49 | 100.00% | 99.8% | 0.588 |

**0 of 4 below 20%** (lowest 59.91%, on a tile that covers only 58.8% of the AOI). **Rule (b) via Sentinel-2: fails.** The cloud criterion is only a necessary condition; no imagery was pulled, so no visual water check was made.

| Reference | Label | What was found [M] |
|---|---|---|
| Copernicus EMS Rapid Mapping | **checked, out of range** | API answered (268 records); earliest activation 2023-03-24T12:39, after the candidate; no record with an October 2020 event time; no Ghana record. Not evidence of no event. |
| EMS Risk and Recovery Mapping | **not checked** | no working endpoint (A12.2); not retried |
| DFO, live site | **checked, in range** | **New: reachable this time** (earlier amendments: connection failed). Its `FloodRecords` table has 5,513 records, 1985-01-01 to 2024-03-07, 29 rows naming Ghana; **none starts in September to November 2020** (nearest in time: 2019-10-25). DFO lists large events, so this is not evidence of no flooding [E]. |
| DFO, HDX mirror | **checked, out of range** | its own metadata: 1985-2010 |
| UNOSAT | **not re-queried** | prior result only (A17.6, A18): no usable Ghana product for Accra other than the rejected 2023 one |

No archive that does not reach 2020 is reported as "no event".

## Updated ranking (A14.4 style), all 15 candidates

Offsets for the older rows are copied from A10, A14, A17 and A10.1 (measured then, not re-measured here). The 2020-10-10 row is measured now with the assumed peak [A].

| # | Candidate | Rule (a) | Best rule (b) evidence found |
|---|---|---|---|
| 1 | **2020-06-09 (selected, A12.1)** | **PASS** (+12.3 to +20.3 h) | S2 cloud-free at 16.63% (A12.2) |
| 2 | 2025-05-18 | FAIL (+49.3 h) | S2 cloud-free at 11.4% (A10) |
| 3 | 2018-06-18 | FAIL (+54.3 h) | S2 80-100% cloudy over the AOI (A14.3) -- fails |
| 4 | 2019-04-14 | FAIL (+54.3 h) | S2 23.3% cloud, borderline (A10) |
| 5 | 2023-10 UNOSAT FL20231018GHA (A17; onset window 11-14 Oct) | FAIL (+66.3 h to +138.3 h) | product exists but its geometry has zero overlap with the Odaw AOI (A17.3) |
| 6 | 2019-04-07 | FAIL (+70.3 h) | S2 cloud-free at 18.7% (A10) |
| 7 | 2019-10-28 | FAIL (+75.3 h) | S2 cloud-free at 5.2% (A10) |
| 8 | 2019-10-10 | FAIL (+84.3 h) | S2 75.8% cloud, fails (A14.3) |
| 9 | **2020-10-10 (this screening, assumed peak 06:00 UTC [A])** | **FAIL (+84.3 h; +78.3 to +90.3 h across the window)** | **S2 0 of 4 below 20% (lowest 59.9%); EMS Rapid Mapping out of range; DFO live table: no Ghana record starting Sep-Nov 2020** |
| 10 | 2018-06-28 (Kumasi, per A14.1) | FAIL (+102.3 h) | S2 80-100% cloudy over the AOI (A14.3) -- fails |
| 11 | 2019-05-30 | FAIL (+102.3 h) | S2 all >80% cloud -- fails (A10) |
| 12 | 2026-06-29 | FAIL (+108.3 h) | not assessed (rule (a) fails, A10.1) |
| 13 | 2023-03-07 | FAIL, badly (no pass in window) | S2 23-29% cloud, borderline (A10) |
| 14 | 2016-06-09 | FAIL, badly (24-day S1 gap) | S2 all >97% cloud -- fails (A10) |
| 15 | 2015-06-03 | FAIL, badly (no pass in window) | S2 did not exist yet (A10) |

Numbering is by rule (a) offset, not by screening order. By my count 2020-10-10 is the 15th distinct date screened [M, A20.7]; A14.4's own table omitted 2026-06-29 and the 2023 UNOSAT product, which are included here.
**No candidate beats 2020-06-09 on rule (a), and 2020-06-09 remains the selected event.**

## Notes and things that did not go to plan

- **Both S1 scenes in the window are on orbit 147**, as for the selected event; the 13 October offset (+84.3 h) is the same as 2019-10-10's by coincidence of the repeat cycle [E].
- **DFO is now reachable and reaches 2020.** Earlier amendments labelled the DFO live site "not checked" for earlier candidates; I did **not** re-run those, because that is outside this step. Say if you want it done.
- **Decision rule note:** A20.6 also covers "passes (a) but not (b)" because A10.2 requires both; it was not needed, since (a) failed.
- Two sources, neither with a clock time; the 06:00 UTC peak therefore remains an assumption, but the rule (a) verdict is the same for any peak between 00:00 and 12:00 [M].
- The A14.4 header ("12 candidates plus the selected event") matches its table only if 2026-06-29 is counted as the unlisted 12th; I added it and the A17 product to the table.
