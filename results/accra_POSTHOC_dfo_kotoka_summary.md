# POST-HOC lookups (Amendment 21): DFO overlap with the ranked candidates, and Kotoka gauge rainfall

**POST-HOC, UNVALIDATED. No imagery, no method run. No rule changed; no rule (a) verdict changed.** Tags: **[M]** measured by a query or code run (2026-10-20); **[A]** rule or assumption; **[E]** estimate or reasoning.
Rules were committed before running: `7641847`, registered in `results/accra_followup_registration.txt`. Script: `scripts/17_accra_POSTHOC_dfo_and_kotoka.py`.

## 1. DFO live FloodRecords table vs every candidate in the A20.8 ranking

Source: `floodobservatory.colorado.edu/wiki/FloodRecords` (the site's own link). The table has 5,514 rows, **1985-01-01 to 2024-03-07**, **29 Ghana rows** (Country cell contains "Ghana") [M].
Overlap = the Ghana row's [Start, End] intersects the candidate's window (A21.1). Full rows are in `results/accra_POSTHOC_dfo_candidate_overlap.csv`.

| Candidate (window) | Result [M] | Matching DFO row (full row for every match) |
|---|---|---|
| 2020-06-09, selected (8-9 Jun 2020) | **no overlapping Ghana row**; none within +/-3 d | none |
| 2025-05-18 | **beyond the table's range** (table ends 2024-03-07) | not assessable |
| 2018-06-18 | **OVERLAP** | #4631, Glide none, 2018-06-18 to 2018-06-19, Ghana + Côte d'Ivoire, 58,480 km2, Source FloodList, Torrential rain, 21 fatalities, 115 displaced, severity 1.0, impact index 5.1 |
| 2019-04-14 | no overlapping Ghana row | none |
| 2023-10 UNOSAT FL20231018GHA (11-14 Oct) | **OVERLAP** | #5476, FL-2023-000215-GHA, 2023-09-15 to 2023-10-24, Ghana, 5,412 km2, Source News, Dam/Levy break or release, 0 fatalities, 26,000 displaced, severity 1.0, impact index 5.3 |
| 2019-04-07 | no overlapping Ghana row | none |
| 2019-10-28 | **OVERLAP** | #4819, Glide none, 2019-10-25 to 2019-10-30, Ghana, 7,286 km2, Source FloodList, Heavy rain, 0 fatalities, 0 displaced, severity 1.0, impact index 4.6 |
| 2019-10-10 | no overlapping Ghana row | none |
| **2020-10-10** | **no overlapping Ghana row**; none within +/-3 d | none |
| 2018-06-28 | **OVERLAP** | #4638, Glide none, 2018-06-28 to 2018-07-02, Ghana, 23,281 km2, Source FloodList, Heavy rain, 5 fatalities, 500 displaced, severity 1.5, impact index 5.2 |
| 2019-05-30 | no overlapping Ghana row | none |
| 2026-06-29 | **beyond the table's range** | not assessable |
| 2023-03-07 | **OVERLAP** | #5380, Glide none, 2023-03-07 to 2023-03-07, Ghana, 4,067 km2, Source FloodList, Heavy rain, 3 fatalities, 0 displaced, severity 1.0, impact index 3.6 |
| 2016-06-09 | no overlapping Ghana row (**sensitivity only**, +/-3 d: #4361, 2016-06-12 to 2016-06-21, Ghana, 74,506 km2, Source News, Heavy rain, 5 fatalities, 0 displaced, 1.0, 5.9) | none in the primary window |
| 2015-06-03 | **OVERLAP** | #4260, FL-2015-000065-GHA, 2015-06-02 to 2015-06-15, Ghana + Togo, 266,950 km2, Source News, Torrential rain, 150 fatalities, 5,300 displaced, severity 1.5, impact index 6.7 |

What this does and does not say:
- Six candidates overlap a DFO Ghana row (2018-06-18, 2018-06-28, 2019-10-28, 2023-03-07, 2023-10 UNOSAT, 2015-06-03). The **selected 2020-06-09 event and the 2020-10-10 candidate have no DFO Ghana row**, and 2019-04-07, 2019-04-14, 2019-05-30, 2019-10-10 have none either [M].
- DFO rows give a country, not a city: the 2018-06-28 row says Ghana, which does not settle the A14.1 doubt about Accra versus Kumasi [E]. DFO lists large events from news sources, so a missing row is **not** evidence of no flooding, and a match is **not** an independent flood map [E].
- **No rule (a) verdict changed, and the ranking is unchanged.** Every overlapping candidate still fails rule (a); for those, a DFO row is one more route that could count towards rule (b) (A10.2 names a DFO record), but a candidate qualifies only with both [E, from A10.2]. I did not rewrite any earlier rule (b) label.
- 2025-05-18 and 2026-06-29 are beyond the table's last date, so they are reported as out of range, not as "no record".

## 2. Kotoka International Airport gauge, 1 to 15 June 2020: STOPPED by the A21.2 stop rule

- **Station [M]:** NOAA ISD/GSOD **654720-99999, KOTOKA INTL**, 5.605 N, 0.167 W (GSOD file: 5.6052, -0.1668), record 1942-07-01 to 2025-08-24. It is the only Kotoka match in NOAA's station list (the other Accra entry, 654490, ended in 1952). The station is **outside** the Odaw AOI mask [M].
- **Data [M]:** the GSOD 2020 file has all 15 rows for 1-15 June. GSOD days are 0000Z-2359Z (NOAA readme); PRCP is in inches (x 25.4 = mm) and "may include latter part of previous day".
- **Stop [M]:** **8 June 2020 has PRCP 0.00 with flag `I`**, which NOAA defines as "Station did not report any precipitation data for the day and did not report any occurrences of precipitation in its hourly observations. It's still possible that precipitation occurred but was not reported." My pre-declared rule (A21.2) says to stop if the value for 8, 9 or 10 June is missing or carries that flag. **So I stopped: I did not pull ISD (hourly or 6-hourly amounts) and did not build the comparison table with the IMERG daily means.**
- Raw GSOD rows as retrieved, for the record (`results/accra_POSTHOC_kotoka_rainfall.csv`; PRCP mm, flag): 1 Jun 0.0 G; 2 Jun 14.99 E; 3-6 Jun 0.0 I; 7 Jun 0.0 G; **8 Jun 0.0 I**; 9 Jun 25.91 G; 10 Jun 1.02 G; 11 Jun 16.0 G; 12 Jun 0.0 G; 13 Jun 32.0 G; 14 Jun 20.07 G; 15 Jun 0.0 G. Flag G is "1 report of 24-hour precipitation amount", E is "1 report of 12-hour precipitation amount" (NOAA readme). Days flagged `I` (3, 4, 5, 6, 8 June) are "no data reported", not confirmed dry days [M].
- Among the days with a reported amount the largest daily total is **13 June (32.0 mm)**; the 8 June gauge value cannot be read as a dry day. No further interpretation, and no comparison with IMERG, per the stop rule.

## Decision for you

The stop rule fired on one flagged day (8 June), while 9 and 10 June are unflagged 24-hour reports. Options, each needing your say-so and a logged amendment: (a) relax the stop rule to 9 and 10 June and build the IMERG comparison table; (b) pull ISD hourly reports for 8 to 10 June to see whether Kotoka reported anything on 8 June; (c) leave it stopped.
