# Unsupervised SAR flood segmentation: benchmark and Accra case study

SLIC superpixels + k-means (and baselines) on Sentinel-1 VV/VH, evaluated on the labelled Sen1Floods11 benchmark and applied,
frozen, to the Odaw catchment in Accra. **Every Accra output is UNVALIDATED: no ground truth exists for the Accra event.**
Hard rules, stages and the full protocol are in `CLAUDE.md` and `results/evaluation_protocol.md` (amendments A1 to A22; A19 has revisions R2 to R5).
`CLAUDE.md` is the original brief: it names 29 June 2026 as the Accra event, but that date failed the timing rule and the case study uses 8-9 June 2020 (protocol Amendments 10 to 12).

## Setup

```bash
conda env create -f environment.yml        # environment name: sar_flood (versions also in requirements.txt)
conda activate sar_flood
export PYTHONPATH=.                         # every script is run from the repository root
```

- Benchmark data (Sen1Floods11 hand-labelled subset, public bucket, no credentials): `bash scripts/_download_sen1floods11_subset.sh`.
  Data live in `data/` (git-ignored).
- Accra scripts that pull imagery (`06`, `10a`, `11`, `12a`, `13`) use Google Earth Engine: run `earthengine authenticate` yourself and set your
  project ID in `ee_init()` in `scripts/06_accra_run.py`. All other Accra scripts read the GeoTIFFs already in `data/accra/`.

## Benchmark stages (commands as written in each script's own docstring)

```bash
python scripts/02_inspect.py                                   # data report
python scripts/03_tune.py compute > results/tuning/stage1_compute.log 2>&1
python scripts/03_tune.py rank > results/tuning/stage1_report.txt
python scripts/03b_select.py stage2-rank                       # then stage2-extend only after its cost is accepted
python scripts/03b_select.py stage3-compute
python scripts/03b_select.py freeze                            # writes results/frozen/**
python scripts/04_evaluate.py                                  # test evaluation, run once (refuses a second run: lock file)
python scripts/04b_POSTHOC_paired_event_bootstrap.py           # POST-HOC paired event-level intervals; reads heldout_results.json only
python scripts/05_accra_pooled_select.py                       # frozen `accra_pooled` configuration used for Accra
```

## Accra case study (frozen configuration, nothing retuned)

```bash
python scripts/06_accra_run.py              # downloads data/accra/*, runs B1/B2g/M1g/M2g -> results/accra/accra_tables.*
python scripts/07_accra_subaoi_run.py       # same methods per sub-AOI piece -> accra_subaoi_tables.*
python scripts/08_accra_m2g_tiled.py        # M2g per 512x512 tile and with density-matched n_segments -> accra_m2g_tiled_tables.*
python scripts/09_accra_delta_vv_3v15.py    # exploratory 15 Jun - 3 Jun dVV exceedances (+3/+6/+10 dB)
```

## Amendment 19 follow-up checks (change detection, coastal control, point checks)

Rules are fixed in `results/evaluation_protocol.md` (A19, A19-R2 to R5) and registered in `results/accra_followup_registration.txt`.

```bash
python scripts/10a_fetch_may_scenes.py                      # 22 and 28 May 2020 scenes (Earth Engine)
python scripts/10_accra_cd_baseline.py                      # -> results/accra_cd_baseline.csv
python scripts/10b_accra_cd_map_and_offsets.py              # -> event-pair map PNG, POST-HOC median dVV JSON
python scripts/11_accra_POSTHOC_rainfall.py                 # POST-HOC IMERG daily / 24 h-before-pass table (Earth Engine)
python scripts/12a_fetch_worldcover.py                      # ESA WorldCover v100 raster (Earth Engine)
python scripts/12_accra_coastal_control.py                  # -> accra_coastal_control.csv / .png
python scripts/13_accra_POSTHOC_rain_halfhourly_and_s1_list.py   # POST-HOC half-hourly rain chart + S1 acquisition list (Earth Engine)
python scripts/14_accra_point_checks.py                     # -> accra_point_checks.csv / histogram PNG
python scripts/15_accra_followup_summary.py                 # -> results/accra_followup_summary.md (reads the files above)
```

Order: `10a` before `10`; `12a` before `12` and `14`. Scripts 10, 10b, 14 and 15 import helpers from earlier scripts by path.
Summary of results and everything that did not go to plan: `results/accra_followup_summary.md`.

## Amendments 20 to 22 (lookups only: no imagery pulled, no method run)

```bash
python scripts/16_accra_candidate_2020_10_10_screening.py   # A20: 10 October 2020 candidate (Earth Engine catalogue) -> results/accra/candidate_2020_10_10_screening.*
python scripts/17_accra_POSTHOC_dfo_and_kotoka.py           # A21 POST-HOC: DFO records vs the 15 candidates; Kotoka GSOD daily rain
python scripts/18_accra_POSTHOC_kotoka_isd.py               # A22 POST-HOC: Kotoka ISD precipitation reports, 7-11 June 2020
python scripts/19_thesis_figures.py                      # thesis Figures 1 and 3 to 8 -> results/figures/thesis/ (reads stored results; re-scores nothing; Figure 2, the world map, is not scripted)
```

These three query outside services (Earth Engine, the DFO website, NOAA), so their outputs depend on those services still answering as they did on 2026-10-20.

## Tests and integrity checks

```bash
python -m pytest -q                                                       # 153 passed on 2026-11-16 (148 before the paired-bootstrap tests were added)
grep -E '^[0-9a-f]{64}  ' results/accra_followup_registration.txt | sha256sum -c -
```

The second command compares `configs/config.yaml`, `results/tuning/heldout_lock.json` and every `results/frozen/**/*.yaml` with the
hashes recorded before the Amendment 19 checks ran (27 files; all matched at hand-back).

## Reproducibility check, 2026-11-16

Scripts 07, 08, 09, 10, 10b, 12 and 14 (the ones that need only the files already in `data/accra/`) were re-run. Every tracked output they write,
CSV, JSON and PNG, came out byte-identical to the committed copy (`git status` showed no change). Script 15 was re-run after three corrections to
its text (a malformed table, a mislabelled rain column and a mislabelled hash line); no number in it changed. Scripts that query Earth Engine or
other services (06, 10a, 11, 12a, 13, 16, 17, 18) and the benchmark tuning scripts (02 to 05) were **not** re-run. `04_evaluate.py` was not re-run
and must not be: held-out scoring runs once.

Later on 2026-11-16, `scripts/19_thesis_figures.py` was added and run. It reproduced, from the frozen configurations, the stored
Accra M2g areas (8.86 ha and 1.88 ha) and the two example-chip figures quoted in the thesis. It has no unit tests of its own. The
remaining scripts (02, 02b, 03, 03b, 05, 13, 16, 17, 18 and the `verify_*` scripts) were read line by line on the same day; no
error was found in them. `scripts/smoke_stage2.py` and the test files were not read line by line.

## What was and was not re-run when this README was first written (2026-10-19)

Re-run in that session: scripts 08, 09, 10a, 10, 10b, 11, 12a, 12, 13, 14, 15 and the test suite. Scripts 02 to 07 are listed from their
docstrings and were not re-run then (06 and 07 were only imported). The new scripts 08 to 14 have no unit tests of their own.
