# Results

Written last, from outputs already on disk. Every number below is **measured** (produced by code
that was actually run, and is still on disk to re-check) unless marked **assumed/estimate**. Full
process detail, every declared choice, and every dated decision are in
`results/evaluation_protocol.md` (16 amendments) and `results/grid_extension_log.md`; this file is the
summary written for a reader who wants the results, not the process.

## 0. What this project is

Part A benchmarks an unsupervised method (SLIC superpixels + k-means, "M2", the Hack4Dev Tutorial 3
idea) against two baselines (B1: fixed VV threshold; B2: Otsu) and a pixel-level k-means ablation
(M1), on the labelled Sen1Floods11 benchmark, with an abstention guard (M2g/M1g/B2g) as an addition
this project introduces. Part B applies the frozen pipeline, unmodified, to a real flood in Accra,
Ghana, as a demonstration with **no ground truth**.

## 1. Benchmark (Sen1Floods11): data and method, briefly

- 446 hand-labelled chips (512x512, 10 m), 11 flood events, official splits train/valid/test/Bolivia =
  252/89/90/15. 440 chips are eligible (6 have zero valid pixels and are excluded from every metric).
  Bands VV/VH, dB, sourced from Google Earth Engine's `COPERNICUS/S1_GRD` (confirmed by reading the
  dataset's own README and Google's Sentinel-1 documentation directly, not assumed).
- Headline metric: **flood-only IoU** (domain = image-valid AND label-valid AND JRC permanent water
  == 0). Never overall accuracy. Pooled and mean-per-chip are both reported, always with a 95%
  bootstrap CI.
- **Cluster-to-water rule** (an assumption, stated up front): the cluster with the lowest mean VV is
  water. An abstention guard (a ceiling on that cluster's mean VV) can make a method abstain entirely
  on a chip rather than predict; this turns B2/M1/M2 into B2g/M1g/M2g.
- **Selection**: leave-one-event-out (11 folds) plus the official validation split = 12 tuning sets,
  each producing its own frozen configuration per method, selected on tuning chips only. Primary
  selection criterion: pooled flood-only IoU over all tuning chips (chosen so flood-free chips count
  through their false positives -- protocol Amendment 7). A declared sensitivity criterion (mean
  per-chip IoU) was run in parallel throughout. Grid edges were extended under a fixed, logged rule
  (`results/grid_extension_log.md`); two edges remain genuinely unresolved at the cap: the median
  window (stuck at 9-11 px for several variants) and, for 3 of 12 primary-M2 tuning sets, the lowest
  compactness value.
- **Held-out scoring ran exactly once**, from `scripts/04_evaluate.py`, locked by
  `results/tuning/heldout_lock.json` (a hash of all 24 frozen configuration files). Every fold's
  configuration is scored only on its own held-out event.

## 2. Benchmark results (primary criterion, LOEO, flood-only, measured)

Pooled over all 440 LOEO evaluation chips; 95% CI from 1000 chip-level bootstrap resamples.

| Method | Pooled IoU (95% CI) | Mean per-chip IoU (95% CI) | Flood-free alarm rate (of 47 chips) |
|---|---|---|---|
| B1 (fixed threshold) | 0.357 (0.305-0.408) | 0.219 (0.196-0.242) | 53% |
| B2 Otsu VV | 0.144 (0.119-0.171) | 0.223 (0.197-0.248) | 100% |
| B2 Otsu VH | 0.175 (0.149-0.205) | 0.238 (0.213-0.263) | 100% |
| M1 (pixel k-means) | 0.198 (0.167-0.230) | 0.247 (0.222-0.270) | 100% |
| M2 (SLIC + k-means) | 0.192 (0.161-0.224) | 0.201 (0.180-0.221) | 100% |
| B2g VV (guarded) | 0.390 (0.326-0.447) | 0.177 (0.149-0.202) | 2.1% |
| B2g VH (guarded) | 0.391 (0.329-0.450) | 0.159 (0.132-0.185) | 2.1% |
| M1g (guarded) | 0.394 (0.334-0.452) | 0.173 (0.146-0.199) | 2.1% |
| M2g (guarded) | 0.370 (0.309-0.424) | 0.151 (0.126-0.175) | 2.1% |

Macro-average over the 11 events (two-level bootstrap: resample events, then chips within each) gives
the same ordering; e.g. B1 0.345 (0.228-0.462), M2g 0.352 (0.215-0.483) -- see
`results/heldout_results.csv` for every method/criterion/split combination.

### 2.1 What this shows, stated plainly

- **Superpixel + k-means does not beat the simple threshold on this benchmark.** Unguarded, B1's
  pooled IoU (0.357) beats every clustering/Otsu variant, including M2 (0.192). This holds on
  held-out chips, not just tuning chips. This is a legitimate finding, not a bug, and CLAUDE.md
  anticipated exactly this possibility.
- **The guard trades recall for precision, and the two headline numbers disagree about the winner.**
  Unguarded B2/M1/M2 predict flood on 100% of the 47 flood-free held-out chips -- severe
  over-prediction. The guard cuts that to 2.1%, and pooled IoU rises accordingly (every guarded
  variant beats B1 on pooled IoU). But mean-per-chip IoU goes the other way: B1 (0.219) beats every
  guarded variant (0.151-0.177), because the guard also abstains on some real flood chips. **The two
  orderings are not statistically distinguishable at this sample size**: B1's pooled-IoU CI (0.305,
  0.408) overlaps every guarded variant's CI down to 0.309-0.334.
- **Reading depends on which protocol you use.** On the official test split, among the four methods
  carried into the Accra case study, **B1 has the highest pooled IoU (0.411)**, above all three
  guarded comparisons (0.377-0.384) -- the reverse of part of the LOEO picture. Domain-shift check on
  Bolivia (15 chips, held out from the official split too): pooled IoU 0.51-0.70 across methods, with
  very wide CIs given the small sample -- reported, not hidden.

### 2.2 What was tuned, in one line each

Frozen configurations differ across the 12 tuning sets; the dominant choice per method (primary
criterion): B1 clip=none, median=7, threshold -16 dB (7/12 sets); B2g VH clip=narrow, median=9, guard
-15 dB (10/12); M1g clip=narrow, median=9, k=2, guard -15 dB (6/12); M2g clip=none, median=3, SLIC
500/0.05, `vv_vh_std`, k=2, guard -15 dB (4/12, its largest group). Full per-fold detail:
`results/tuning/frozen_summary.txt`, `results/frozen/`.

### 2.3 Illustration figure (best case, not representative)

`results/figures/heldout_example_Mekong_16233_m2g.png`: M2g's frozen `loeo:Mekong` configuration on
chip `Mekong_16233` (a genuinely held-out event; independently re-verified that this chip's fold
excludes it from its own tuning data). IoU 0.9241, precision 0.9865, recall 0.9360 -- the single
highest-IoU chip among 543 held-out chips with at least 5% flood-only truth. Location confirmed from
the chip's own GeoTIFF bounds (not the "Mekong" event name): center 12.1653 N, 105.8086 E, reverse-
geocoded to Dambae district, Tbong Khmum province, **Cambodia**. Labelled on the figure as
a best-case illustration, not a representative result; the representative numbers are section 2 above.

### 2.4 Gaps against the original brief (measured is measured; these were not run)

Stated honestly rather than silently dropped: **stratification by flood fraction** (<5%/5-30%/>30%
bins) was not computed at the held-out stage -- `scripts/04_evaluate.py` explicitly scoped it out
(its own docstring says so) and it was never added afterward. The **rule-vs-oracle gap** (diagnostic
only, per CLAUDE.md section 5) was likewise never computed at the held-out stage (`with_oracle` was
never passed to `evaluate_chip` in `04_evaluate.py`). A full grid figure of example chips (good,
typical, failure cases per method) was not produced -- only the one illustration above. These remain
open items, not claimed results.

## 3. Accra case study (UNVALIDATED: no ground truth)

**Every number in this section is unvalidated.** No hand-labelled flood map exists for Accra in this
project. Agreement with Sentinel-2 below is agreement between two algorithms' outputs, not accuracy.

### 3.1 Area of interest

Odaw catchment AOI derived from HydroBASINS (Lehner & Grill 2013), watershed traced upstream from the
Odaw's outlet at Korle Lagoon: **260.7 km2**, cross-checked two independent ways (local GDAL union vs.
Earth Engine's own copy of the same public dataset; 0.0085 km2 apart). `results/accra/odaw_aoi.geojson`.

A second, smaller **sub-AOI** was built later from named flood-affected neighbourhoods (Kwame Nkrumah
Circle, Kaneshie, Adabraka, Alajo, Odawna, Avenor, Darkuman), sourced from real OpenStreetMap
administrative-boundary polygons (5 of 7 places) or point proxies (2 of 7, where no OSM polygon
exists), buffered 300 m and left as **three explicit, disconnected pieces** (not smoothed into one
shape) by the project owner's decision: a connected 8.45 km2 core (Adabraka+Alajo+Avenor+Circle+
Odawna), isolated Kaneshie (2.22 km2), and Darkuman clipped to the main AOI (4.31 km2, since over a
third of its unclipped buffer fell outside the watershed). Total 14.98 km2.
`results/accra/subaoi_corridor.geojson`.

### 3.2 Event selection

CLAUDE.md's brief date (29 June 2026) was screened first and **rejected**: the nearest Sentinel-1 pass
after the assumed peak was +108.3 h (about 4.5 days), failing a fixed rule set before any candidate
was looked at (protocol Amendment 10: an S1 pass within 24 h of the peak, plus an independent
reference). Twelve historical candidates (2015-2025) were then screened against the same fixed rule;
**8-9 June 2020 was the only one to pass**, and only marginally -- the reported peak window (22:00 UTC
8 June to 06:00 UTC 9 June, from two named news sources, not a single confirmed instant) puts the
nearest S1 pass (2020-06-09T18:18:05 UTC) at +12.3 to +20.3 h after the peak. The project owner
accepted this range explicitly, recording that flood extent at pass time may already be lower than at
the peak. Rule (b) (independent reference) was met only marginally too: one Sentinel-2 scene at 16.63%
AOI-clipped cloud cover, 16.4 h after the pass. Copernicus EMS and the Dartmouth Flood Observatory were
both reached by API/mirror but neither's coverage window reaches back to 2020 -- reported as "checked,
out of range", not "no event". Full screening: protocol Amendments 10, 11, 12, 14.

### 3.3 Frozen configuration

Accra has no benchmark fold of its own, so a 13th tuning set ("`accra_pooled`", all 440 benchmark
chips pooled, primary criterion) was added and run through the identical selection machinery as the 12
real folds -- on benchmark data only, no Accra chip involved. Result (`results/frozen/primary/
accra_pooled.yaml`): B1 clip=none, median=7, threshold -16 dB; B2g VH clip=narrow, median=9, guard -15
dB; M1g clip=narrow, median=9, k=2, guard -15 dB; **M2g (headline)** clip=none, median=3, SLIC
500/0.05, `vv_vh_std`, k=2, guard -15 dB. All four match the dominant choice across the 12 real folds
for that variant -- a consistency check, not a validation.

### 3.4 Imagery

Confirmed before pulling anything (protocol A13.1) that Accra imagery uses the identical processing as
the benchmark: same `COPERNICUS/S1_GRD` source, dB units, no extra terrain correction or speckle
filtering beyond the frozen clip+median. Three relative-orbit-147 images: 3 June 2020 (pre-event
control, -131.7 to -123.7 h before the peak window), 9 June 2020 (the event pass, +12.3 to +20.3 h),
15 June 2020 (next pass, +156.3 to +164.3 h). Valid-pixel coverage of the AOI was 1.000 for every
image (no border-noise gaps).

### 3.5 Full-catchment results (measured, UNVALIDATED)

| Image | Method | Flagged area (ha) | Share inside JRC permanent water |
|---|---|---|---|
| 3 Jun (pre, false-alarm baseline) | B1 | 38.92 | 0.0216 |
| | B2g VH | 95.72 | 0.0178 |
| | M1g | 81.33 | 0.0209 |
| | **M2g (headline)** | 8.86 | 0.1919 |
| 9 Jun (event) | B1 | 35.08 | 0.0388 |
| | B2g VH | 112.13 | 0.0152 |
| | M1g | 50.13 | 0.0337 |
| | **M2g (headline)** | 1.88 | 0.3723 |
| 15 Jun (next) | B1 | 36.06 | 0.0150 |
| | B2g VH | 101.12 | 0.0168 |
| | M1g | 59.83 | 0.0236 |
| | **M2g (headline)** | 0.00 | undefined |

**The 3 June (pre-event) flagged area is a false-alarm baseline, not a detection** -- every method
flags a broadly similar or larger area on 3 June than on 9 June, which on its own is a reason for
caution about reading the 9 June numbers as flood detections. Full table incl. Sentinel-2 agreement
(weak reference) and the median-3 sensitivity run: `results/accra/accra_tables.json/csv`.

### 3.6 Sub-AOI (named-corridor) follow-up (measured, UNVALIDATED)

Same frozen methods, same imagery, clipped to the three sub-AOI pieces instead. Reported per piece,
per CLAUDE.md's instinct that a signal could be diluted when pooled across a much larger catchment.

| Image | Method | core | kaneshie | darkuman_clipped | pooled (14.98 km2) |
|---|---|---|---|---|---|
| 9 Jun (event) | B1 | 0.00 ha | 0.00 ha | 0.00 ha | 0.00 ha |
| | B2g VH | 0.52 ha | 0.14 ha | 2.21 ha | 2.87 ha |
| | M1g | 0.12 ha | 0.00 ha | 0.32 ha | 0.44 ha |
| | **M2g (headline)** | 0.00 ha | 0.00 ha | 0.00 ha | 0.00 ha |

**M2g flags exactly zero in every piece, every image.** A follow-up diagnostic (recomputing the
clustering step alone, before the guard) found why: M2g's darkest cluster sits at the AOI's
southernmost edge (roughly 5.53-5.56 N, at the coast/Korle Lagoon mouth), not in the inland corridor
at all -- so it is not the guard suppressing a signal that formed; the clustering step itself never
places a "water" cluster near these neighbourhoods at catchment scale. Full detail:
`results/accra/accra_subaoi_tables.json/csv`, protocol A9 (diagnostic) turn in this session.

### 3.7 Exploratory diagnostic: double-bounce brightening (EXPLORATORY DIAGNOSTIC, UNVALIDATED, separate label)

Checked whether flooded urban pixels brighten (double-bounce scattering against building walls --
Mason, Dance & Cloke 2021; Chini et al.; Zhao, Li, Li, Matgen & Chini 2024) rather than darken, as a
candidate explanation for M2g's null result. Simple pixel difference, `delta_VV = VV(9 Jun) - VV(3
Jun)`, raw dB, no clip/median filtering, permanent water masked out. Median/mean delta_VV is mildly
positive everywhere checked (full AOI +0.34/+0.36 dB; the three sub-AOI pieces +0.40 to +0.60 dB) --
not unique to the corridor. Area above declared thresholds (+3/+6/+10 dB, chosen from general SAR
change-detection convention, not a literature-quoted figure): full AOI 3553/405/24 ha; corridor pieces
30-122 ha at +3 dB down to 0.2-1.4 ha at +10 dB. **Overlap with M2g's flagged pixels is essentially
zero everywhere** -- but M2g flags almost nothing in the AOI to begin with (section 3.6), so this is a
weak result either way. **A brightness increase here is consistent with, but not proof of, flooding**;
ordinary radar variation or other surface change could produce the same signature, and there is no
ground truth to check against either reading. `results/accra/exploratory_delta_vv_diagnostic.json`.

### 3.8 Alternative dataset explored, not pursued

UrbanSARFloods (Zhao, Xiong & Zhu, CVPRW 2024) was investigated as a possible urban-flood benchmark
with real ground truth. Confirmed real, CC-BY-4.0, hosted on Hugging Face; core chip archive 38 GB (not
414 GB as the top-level page implies -- that bundles raw SLC archives too). A single sample file was
inspected via remote windowed reads (no download): ground truth is clean binary; the "SAR" file has
**8 bands**, not 2 -- most likely 4 interferometric-coherence bands (range [0,1]) plus 4 dB-scale
intensity bands, not a simple VV/VH pair, and band identities are not confirmed. Decided not worth
pursuing given time remaining; not integrated into this project.

## 4. Limitations

- **Urban double-bounce and layover** (Mason, Dance & Cloke 2021; Chini et al.; Zhao et al. 2024): the
  cluster-to-water rule assumes floodwater is dark; in dense urban areas flooded pixels can instead
  brighten from double-bounce scattering off building walls, which would make this pipeline miss them,
  not just under- or over-estimate their extent. Section 3.7's diagnostic looked for this signature in
  Accra and found nothing conclusive either way -- absence of a strong result here is not evidence of
  absence of the mechanism.
- **Sentinel-1's ~10 m pixel size** is coarse relative to Accra's drains and narrow streets; the
  frozen median window (as small as 90-110 m at its 9-11 px setting for several variants, per the
  unresolved grid-edge cap in section 1) plausibly blurs exactly the narrow channels most relevant to
  urban flash flooding.
- **Revisit time vs. how fast urban floods rise and recede**: the best available Accra pass was 12.3
  to 20.3 h after the reported peak (section 3.2); by CLAUDE.md's own estimate, floodwater in a fast
  urban event may already be receding well before that, and every Accra number here should be read
  with that in mind.
- **Domain gap between the benchmark and Accra**: Sen1Floods11's 11 events are mostly rural/open-water
  floods; Accra is a dense low-lying urban catchment. The frozen configuration was never tuned on
  anything resembling Accra, by design (no retuning is the point of "frozen"), but that also means its
  hyperparameters (clip range, median window, SLIC scale) were chosen for a different kind of scene.
- **The cluster-to-water rule is an assumption**, stated in CLAUDE.md and never independently verified
  in this project: "the cluster with the lowest mean VV is water." No rule-vs-oracle check was run at
  the held-out or Accra stage (section 2.4) to quantify how much of the benchmark's error this rule
  itself contributes versus the clustering step.
- **No ground truth for Accra**, at all. Every Accra number in section 3 is a frozen-pipeline
  prediction on unlabelled real imagery; agreement with Sentinel-2 (where computed) is agreement
  between two algorithms, not accuracy. Section 3.5-3.7's honest, striking finding -- M2g predicts
  almost nothing in the flood-affected corridor either way, on any of the three dates -- should be read
  as a limitation of this specific frozen pipeline at this spatial scale, not as evidence about whether
  Accra actually flooded on 8-9 June 2020, which this project draws no conclusion about.
- **Statistical power**: several held-out comparisons (section 2.1) are not statistically
  distinguishable given 440 chips' worth of data; Bolivia's domain-shift check (15 chips) carries very
  wide intervals, reported rather than hidden.
- **Gaps against the original brief** (section 2.4): no flood-fraction stratification, no held-out
  rule-vs-oracle gap, no full example-chip grid figure.

## 5. Where everything is

- Benchmark protocol, every dated amendment: `results/evaluation_protocol.md`.
- Frozen configurations: `results/frozen/`, summary `results/tuning/frozen_summary.txt`.
- Held-out results: `results/heldout_results.json` / `.csv`, lock `results/tuning/heldout_lock.json`.
- Proof-of-concept figure: `results/figures/heldout_example_Mekong_16233_m2g.png`.
- Accra: AOI and sub-AOI (`results/accra/*.geojson`, `*_provenance.md`), full-catchment and sub-AOI
  tables (`results/accra/accra_tables.*`, `accra_subaoi_tables.*`), exploratory diagnostic
  (`results/accra/exploratory_delta_vv_diagnostic.json`), run logs (`results/accra/*.log`).
- Tests: `tests/` (148 passing at last run), including the leakage guard, determinism, and metric
  hand-computation checks required by CLAUDE.md section 7.
