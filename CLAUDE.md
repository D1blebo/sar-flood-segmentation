# Project brief for Claude Code: unsupervised SAR flood segmentation (benchmark + Accra case study)

## 0. Who I am and how to work with me

I am an undergraduate finishing a final-year project. I must be able to explain and defend every line of code in a viva, so:

- Prefer simple, readable code over clever code. Comment the *why*, not the *what*.
- Before each stage, explain in plain language what you are about to do and why. Define technical terms in a few words.
- Work in the stages below. At the end of each stage, run the tests, summarise what you found, and stop for my go-ahead.

### Hard rules (these override everything else)

1. **Never fabricate data or results.** Every number in any report must come from code you actually ran. If a download fails or a service is unavailable, stop and tell me. Do not switch to synthetic data unless I explicitly approve it.
2. **Never guess.** Do not guess URLs, file layouts, band order, units (dB vs linear), nodata values or split files. Inspect the real files first and print what you found (shape, dtype, value range, nodata, units) before writing processing code.
3. **No test-set leakage.** Tune every hyperparameter on the validation split only. Freeze the configuration. Evaluate on the test split once. Add an automated test that fails if any chip ID appears in both the tuning set and the test set.
4. **Label every claim** in reports as either **measured** (produced by code you ran) or **assumed/estimate** (reasoning, literature, or a rule I chose).
5. **Do not overclaim.** The Accra part has no ground truth. It is a demonstration, not a validated result, and every output about it must say so.
6. If you need something from me (Accra event date, Google Earth Engine project ID, disk location, credentials), **ask, do not invent**.

## 1. The problem

Accra floods repeatedly in the rainy seasons, especially low-lying catchments such as the Odaw basin. Optical satellite imagery is often unusable during heavy rain because of cloud. Sentinel-1 synthetic aperture radar (SAR) sees through cloud. Ground-truth flood maps for Ghanaian cities are scarce.

The project has two parts:

- **A. Benchmark validation.** Evaluate an unsupervised method (SLIC superpixels + k-means clustering) on an existing *labelled* Sentinel-1 flood dataset, with proper baselines and honest error bars.
- **B. Accra case study.** Apply the *frozen* pipeline to Sentinel-1 imagery over Accra during a recent rainy-season event, and present it as an unvalidated demonstration.

The method is based on the Hack4Dev `flood_detection` Tutorial 3 (SLIC superpixels + k-means on Sentinel-1). The tutorial has no accuracy check and only uses mean backscatter per segment. Adding a real evaluation and baselines is the main contribution of this project.

## 2. Stage 0: plan and environment (no code yet)

1. Reply with a short plan, your assumptions, and any questions.
2. Propose the repository layout. Suggested:
   ```
   sar_flood/
     configs/config.yaml        # all hyperparameters and paths
     src/                       # io, preprocessing, methods, metrics, plots
     scripts/                   # 01_download, 02_inspect, 03_tune, 04_evaluate, 05_accra
     tests/
     results/                   # csv tables, figures (generated)
     notebooks/                 # optional, figures/explanations only
     README.md
     RESULTS.md                 # written last, from real outputs
   ```
3. Use Python. Likely libraries: numpy, rasterio, scikit-image (`skimage.segmentation.slic`), scikit-learn (`KMeans`), scipy, pandas, matplotlib, pyyaml, pytest, earthengine-api (Accra part). Pin versions in `requirements.txt`.
4. Set a global random seed in the config and use it everywhere.

Ask me for anything you need before Stage 1.

## 3. Stage 1: benchmark data (inspect before you process)

Primary benchmark: **Sen1Floods11** (Sentinel-1 flood dataset with hand-labelled chips). Alternative: **ETCI 2021** if Sen1Floods11 cannot be obtained.

I am writing this from memory, so **verify everything below** and report what is actually true:

- Where and how the dataset can be downloaded legitimately (find the official source; do not guess URLs). If it needs credentials or a large download, tell me the size first.
- Which Sentinel-1 bands are present (expected VV and VH), their units (dB or linear), chip size, and nodata handling.
- What the hand-labelled masks contain (expected: water/flood = 1, non-water = 0, unlabelled = -1; verify), and whether the labels mean "flood" or "all water including permanent water". This matters for how we score.
- Whether official train / validation / test split files exist, and whether there is a held-out region.
- Which flood events/regions are in the dataset. **Check whether any Ghana event is included** and tell me. If yes, that is useful context for the Accra part.
- Whether a pre-event Sentinel-1 image exists for each chip (I believe not). If not, no change-detection method on the benchmark.
- What land-cover types the events cover. State honestly if the benchmark is mostly rural/open-water floods, because Accra is urban and that is a domain gap.

Deliverables: `scripts/02_inspect.py` that prints a data report, plus a written summary of what you found. Save a few example chips (image, label) as PNGs so I can look at them.

## 4. Stage 2: methods to implement

All methods take a VV/VH chip and output a binary flood mask. Keep them behind one common interface so they can be swapped and compared.

**Baselines**

- **B1. Fixed threshold on VV.** Threshold tuned on the validation split only.
- **B2. Otsu threshold on VV** (and separately on VH). Otsu picks the threshold that best separates a two-peak histogram. Note in the README that it is known to degrade when water covers a small fraction of the image.

**Main method**

- **M1. Pixel-level k-means.** Cluster individual pixels on the VV/VH features. Test k in {2, 3, 4, 5}.
- **M2. SLIC superpixels + k-means (the Tutorial 3 method).** SLIC groups neighbouring pixels of similar value into small patches. Compute features per patch, cluster the patches with k-means, then map cluster labels back to pixels.
  - Per-patch features to compare: mean VV only; mean VV + mean VH; plus standard deviation of each; plus VV-VH difference.
  - Tune `n_segments` and `compactness` on validation only.

**Cluster-to-water rule (important)**

k-means cluster IDs are arbitrary. Use this a-priori rule, fixed before looking at any test results: **the cluster with the lowest mean VV backscatter is water** (calm water is dark to radar).

- Also compute an **oracle diagnostic**: choose the cluster that best matches the ground truth. This is for diagnosis only and must never be used for reported headline results. The gap between the rule and the oracle tells us how much error comes from the rule and how much from the clustering itself.

**Preprocessing options to ablate**

- Speckle filtering: none vs a simple filter (median or Lee, window size tuned on validation). Speckle is the grainy noise inherent to radar images.
- Handle NaN/nodata explicitly. Never let nodata pixels silently enter a cluster or a metric.
- Check units: if the data are linear power, convert to dB before clustering, and say where and why.

**Optional stretch (only after everything else is done and I approve):** a small supervised reference model (for example a random forest on the same per-pixel features, trained on the train split) as a "how much do we lose by not using labels" ceiling. Label it as a reference, not part of the proposed method.

## 5. Stage 3: evaluation protocol

- **Primary metric:** flood-class **IoU** (intersection over union of predicted and true flood pixels). Also report **F1, precision, recall**. Do **not** use overall accuracy as a headline number, because flood is a minority class and accuracy is misleading.
- Ignore unlabelled pixels (-1) in all metrics.
- Report both **pooled** (all test pixels together) and **per-chip** statistics. Chips with no flood pixels make per-chip IoU undefined. Report those separately as a false-positive rate on flood-free chips.
- **Uncertainty:** bootstrap over chips (for example 1000 resamples), and report 95% confidence intervals for every headline number.
- **Stratify by flood fraction** (for example bins: <5%, 5-30%, >30% of labelled pixels). I suspect thresholding and k-means both degrade when water is a small share of the image. Test this and report what you actually find.
- **Held-out generalisation:** report results on the held-out region/event split if the dataset provides one, separately from the standard test split. Because tuning happens on validation only, this doubles as a domain-shift check.
- Tuning workflow: search on validation, select by mean flood IoU, write the chosen config to `results/frozen_config.yaml`, then run the test evaluation once.

**Outputs**

- `results/benchmark_results.csv`: one row per method/variant with IoU, F1, precision, recall and 95% CIs.
- Figures: bar chart with error bars; IoU vs flood fraction; a grid of example chips (SAR image, ground truth, each method's prediction, error map), including good, typical and failure cases.
- A short written analysis: which method wins, whether superpixels help (M1 vs M2), whether k-means beats Otsu/thresholding, how large the rule-vs-oracle gap is, and where each method fails.

If superpixel + k-means does **not** beat a simple threshold, say so plainly. That is a legitimate finding.

## 6. Stage 4: Accra case study (demonstration only)

**Event (chosen by me): Monday 29 June 2026.** Local news and Copernicus flood-news pages report that heavy rain began late on Sunday 28 June and continued into the morning of Monday 29 June, with flooding in many parts of Accra, Tema and surrounding areas. Treat 29 June as the *rain/flood day*, **not** as a satellite acquisition date. Verify these details yourself from the sources you find; do not just trust this paragraph.

I will still provide (ask me if missing): the **area of interest** (Odaw catchment or a Greater Accra bounding box) and my **Google Earth Engine project ID**. I will run `earthengine authenticate` myself.

**Acquisition selection (do this first, before any flood mapping):**

- List every Sentinel-1 IW GRD acquisition covering the AOI from 15 June to 13 July 2026. For each, print: date and time (UTC), satellite (A/C/D), orbit direction, relative orbit, and the **offset in hours from the morning of 29 June**.
- Check which satellites' data actually exist in Google Earth Engine for this period and how delayed the ingestion is. One source I found says Sentinel-1A was planned to end its mission on 29 June 2026 (and did on 30 June) after Sentinel-1D launched. I have not verified how that affects data availability over Accra. If Earth Engine lacks the acquisitions we need, tell me and suggest an alternative (for example the Copernicus Data Space Ecosystem) and ask me before switching.
- The post-event image should be the **earliest acquisition after the rain peak**. Also process the following acquisitions as a series, to show whether the water recedes. If the nearest image is more than about 48 hours after the peak, flag that floodwater may already have drained (my estimate, untested), and say so in every Accra figure.
- Baselines: use the same relative orbit for all. Build two baselines and compare them: (a) a **pre-event wet-season image** from earlier in June, and (b) a **dry-season median** (for example December 2025 to February 2026). June 2026 was reported as unusually wet, so a June baseline may itself be wet. Report how much the choice of baseline changes the result.
- Print the acquisition list and the chosen images in the report before showing any flood map.

1. Use Google Earth Engine to pull Sentinel-1 GRD (IW mode, VV+VH) for the images selected above. Use the **same orbit direction and relative orbit** for event and baseline images. Report the **time gap between the rain peak and the image acquisition**, because revisit time is a real limitation.
2. Match the benchmark preprocessing exactly (units, filtering) so the frozen pipeline sees comparable inputs. Report any mismatch.
3. Apply the **frozen** pipeline from Stage 3. Do **not** retune anything on Accra.
4. Apply masks and report each one: permanent water (for example JRC Global Surface Water occurrence, so the sea and lagoons are not counted as floods), and steep terrain (radar shadow) using a DEM slope mask. Show a figure of what each mask removes.
5. Outputs: flood-extent map over a basemap-free background, flagged area in hectares, and the same result from the baseline methods for comparison.
6. **Validation hook:** if I supply `data/accra/validation_polygons.geojson` (hand-drawn flooded / non-flooded polygons), compute IoU/F1 on it and report with a very clear note about how small the sample is. If it is absent, every Accra figure and table must carry the label **UNVALIDATED: no ground truth**.
   - This event is well documented (news reports, NADMO photos, named flooded areas). Suggest how I could build a small validation set from those sources, and be honest about the limits: photos and reports are point-like and road-scale, which Sentinel-1 at ~10 m may not resolve.
   - Check whether the Copernicus Emergency Management Service activated Rapid Mapping for this event, and whether the Copernicus Global Flood Monitoring (GFM) product covers Accra on the relevant dates. I did not find evidence of an activation, and I have not verified GFM coverage. If GFM exists, use it only as a **comparison layer**: it is another algorithm's output, so agreement with it is **not** accuracy.
7. Agreement between methods is **not** accuracy. If you compute agreement (IoU between methods), label it that way.

## 7. Tests (required)

- Metrics are checked against hand-computed values on tiny arrays (IoU, F1, handling of -1 pixels, empty-flood chips).
- Cluster-to-water rule test on a synthetic toy image where the answer is known.
- The leakage guard from the hard rules.
- SLIC/k-means shape and NaN-handling tests.
- Determinism test: same seed, same output.

## 8. Final deliverables

- Runnable code with one command per stage and a `README.md` (setup, how to reproduce every table and figure).
- `RESULTS.md` written last, only from real outputs, with a **Limitations** section that honestly covers:
  - urban double-bounce and layover in dense areas like Accra (may hide or falsely flag flooded areas),
  - Sentinel-1 ~10 m resolution vs narrow drains and streets,
  - revisit time vs how fast urban floods rise and recede,
  - domain gap between the benchmark and Accra,
  - the cluster-to-water rule being an assumption,
  - no ground truth for Accra.
- A one-page "how to explain this in a viva" note: the pipeline in plain language, the main result, and the three weakest points.

## 9. First reply

Do not write code yet. Reply with: (1) your plan and repository layout, (2) your assumptions, (3) the exact questions you need me to answer (event date, AOI, GEE project ID, where to store data, whether I have a GPU, which dataset access route you found), and (4) any risks you see in this brief.
