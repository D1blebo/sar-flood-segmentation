# POST-HOC: Kotoka ISD precipitation reports, 7 to 11 June 2020 (Amendment 22)

**POST-HOC, UNVALIDATED. No imagery, no method run. Nothing is merged, inferred or infilled.** Tags: **[M]** measured (2026-10-20); **[A]** rule or assumption; **[E]** estimate or reasoning.
Rules committed before the pull: `17ae32b` (A22), registered in `results/accra_followup_registration.txt`. Script `scripts/18_accra_POSTHOC_kotoka_isd.py`; full rows `results/accra_POSTHOC_kotoka_isd_7_11_june.csv`.

## What was pulled [M]

- NOAA ISD, station **654720-99999 (KOTOKA INTL)**, observation times 2020-06-07 00:00 to 2020-06-11 23:59:59 UTC. The pre-declared primary URL (global-hourly access CSV) no longer returns the data file (HTTP 301 to an S3 index page), so the **pre-declared fallback was used**:
  `pub/data/noaa/2020/654720-99999-2020.gz`, NOAA's ISD fixed-width file, same data.
- **143 records** in the window: 34 synoptic (FM-12) and 109 hourly METAR (FM-15). **Precipitation groups exist only in 8 of the synoptic reports** (all `AA1`; no `AA2`-`AA4`, `AO`, `AP`, `AH` or `AI` group anywhere). None of the 109 hourly reports carries a precipitation group.
  26 records carry a present-weather `MW1` group, which is not an amount group and is not reported (A22.1). The stop rule (A22.5) did **not** fire: records and precipitation groups exist; the gaps are reported below.
- Code meanings below are quoted from NOAA's own ISD format document (`isd-format-document.pdf`, section "LIQUID-PRECIPITATION occurrence identifier", text extracted locally): period in hours (`99` = missing); depth in mm with scaling factor 10 (`9999` = missing);
  condition code `2` = "Trace", `3` = "Begin accumulated period (precipitation amount missing until end of accumulated period)", `9` = "Missing"; quality code `1` = "Passed all quality control checks", `9` = "Passed gross limits check if element is present".

## The reports exactly as given, with the three markers (UTC)

| Obs. time (UTC) | Type | Group as given | Period | Depth | Cond. | Qual. | Accumulation window (UTC) | Marker overlaps |
|---|---|---|---|---|---|---|---|---|
| 7 Jun 00:00 | FM-12 | `AA106999999` | 6 h | missing (`9999`) | 9 | 9 | 6 Jun 18:00 to 7 Jun 00:00 | |
| 7 Jun 06:00 | FM-12 | `AA124000021` | 24 h | 0.0 mm | 2 (Trace) | 1 | 6 Jun 06:00 to 7 Jun 06:00 | |
| **MARKER 1** | | reported storm window (A12.1) | | | | | **8 Jun 22:00 to 9 Jun 06:00** | |
| 9 Jun 00:00 | FM-12 | `AA106000831` | 6 h | 0.8 mm | 3 | 1 | 8 Jun 18:00 to 9 Jun 00:00 | overlaps marker 1 |
| 9 Jun 06:00 | FM-12 | `AA124026031` | 24 h | 26.0 mm | 3 | 1 | 8 Jun 06:00 to 9 Jun 06:00 | overlaps marker 1 |
| 9 Jun 18:00 | FM-12 | `AA112001031` | 12 h | 1.0 mm | 3 | 1 | 9 Jun 06:00 to 9 Jun 18:00 | |
| **MARKER 2** | | Sentinel-1 pass | | | | | **9 Jun 18:18:05** | |
| 10 Jun 06:00 | FM-12 | `AA124001031` | 24 h | 1.0 mm | 3 | 1 | 9 Jun 06:00 to 10 Jun 06:00 | **contains the pass** |
| **MARKER 3** | | IMERG heaviest rain (A19-R4) | | | | | **10 Jun 15:30 to 18:00** | |
| 11 Jun 00:00 | FM-12 | `AA106000231` | 6 h | 0.2 mm | 3 | 1 | 10 Jun 18:00 to 11 Jun 00:00 | |
| 11 Jun 06:00 | FM-12 | `AA124016031` | 24 h | 16.0 mm | 3 | 1 | 10 Jun 06:00 to 11 Jun 06:00 | **overlaps marker 3** |

There is **no `AA` group dated 8 June, 10 June 12:00 or 10 June 18:00, and none at 12:00 or 18:00 on 7, 8, 10 or 11 June**; the nested 6-hour groups (9 Jun 00:00, 11 Jun 00:00) sit inside the 24-hour windows shown. The windows are the observation time minus the stated period.
**One thing I cannot explain [E]:** every group from 9 June onward carries condition code 3, which the format document defines as "Begin accumulated period (precipitation amount missing until end of accumulated period)", yet each has a numeric depth. I report the depths as given and do not resolve the apparent mismatch.

## Which observation each GSOD daily total corresponds to (A22.2)

| GSOD day (UTC) | GSOD PRCP, flag | Corresponding ISD report | Accumulation window (UTC) |
|---|---|---|---|
| 8 Jun | 0.00 in, flag `I` ("Station did not report any precipitation data for the day and did not report any occurrences of precipitation in its hourly observations. It's still possible that precipitation occurred but was not reported.") | **not determinable**: GSOD says no data was reported, and ISD has no `AA` group dated 8 June | none |
| 9 Jun | 1.02 in (25.91 mm), flag `G` (1 report of 24-hour amount) | exactly one match: `AA124026031` at 9 Jun 06:00, 24 h, 26.0 mm | **8 Jun 06:00 to 9 Jun 06:00** |
| 10 Jun | 0.04 in (1.02 mm), flag `G` | exactly one match: `AA124001031` at 10 Jun 06:00, 24 h, 1.0 mm | **9 Jun 06:00 to 10 Jun 06:00** |
| 11 Jun | 0.63 in (16.0 mm), flag `G` | exactly one match: `AA124016031` at 11 Jun 06:00, 24 h, 16.0 mm | **10 Jun 06:00 to 11 Jun 06:00** |

So each GSOD "day" total is a 24-hour window ending at 06:00 UTC, not a 00:00-24:00 calendar day [M]; the 9 June total covers the afternoon of 8 June as well as the reported storm window.

## Rain at the gauge before the pass, between the pass and 10 June 12:00, and after 10 June 12:00 (A22.4)

Under the rule I fixed (an amount is stated only from reports whose whole windows lie inside the segment and tile it, with no splitting) **all three are "not determinable from the reports as given" [M]**:

| Segment | Verdict | Reports wholly inside (as given) | Reports straddling a boundary (counted in no segment) | Uncovered by any report |
|---|---|---|---|---|
| (i) 7 Jun 00:00 to the pass (9 Jun 18:18:05) | not determinable | 24 h to 9 Jun 06:00 = 26.0 mm; 6 h to 9 Jun 00:00 = 0.8 mm (nested in it); 12 h to 9 Jun 18:00 = 1.0 mm | 24 h to 7 Jun 06:00 = 0.0 mm (starts before the segment); 24 h to 10 Jun 06:00 = 1.0 mm (contains the pass) | 7 Jun 00:00 to 8 Jun 06:00; 9 Jun 18:00 to 18:18 |
| (ii) pass to 10 Jun 12:00 | not determinable | none | 24 h to 10 Jun 06:00 = 1.0 mm; 24 h to 11 Jun 06:00 = 16.0 mm | the whole segment |
| (iii) 10 Jun 12:00 to 12 Jun 00:00 | not determinable | 6 h to 11 Jun 00:00 = 0.2 mm | 24 h to 11 Jun 06:00 = 16.0 mm (straddles 10 Jun 12:00) | 10 Jun 12:00 to 18:00; 11 Jun 00:00 to 12 Jun 00:00 |

What the reports do say, without adding anything: the only 24-hour report that contains the pass is 1.0 mm (9 Jun 06:00 to 10 Jun 06:00); the report that overlaps the IMERG peak window is a 24-hour 16.0 mm (10 Jun 06:00 to 11 Jun 06:00); the report that overlaps the reported storm window is a 24-hour 26.0 mm (8 Jun 06:00 to 9 Jun 06:00).
These windows are long relative to the markers, so none of them says **when** within its window the rain fell.

## Things that did not go to plan

- The primary ISD URL moved; the pre-declared fallback file was used.
- The segment rule I fixed yields "not determinable" for all three segments, because synoptic windows end at 00, 06, 12 and 18 UTC and none of them ends at the pass (18:18:05) or tiles across 7 to 8 June; nothing here was filled.
- ISD has no precipitation group at all in the hourly METAR reports and none on 8 June, consistent with GSOD's flag `I` for that day.

## Decision for you

I did not add the contiguous reports 8 Jun 06:00 to 9 Jun 06:00 (24 h) and 9 Jun 06:00 to 18:00 (12 h) together, because A22.4 forbids it. If you want a figure for "before the pass", the options are an amendment that defines a different segment (for example from the first report window that starts in the pulled period) and allows summing contiguous reported windows, or leaving it as above.
