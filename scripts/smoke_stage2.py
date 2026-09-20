"""
Stage 2 SMOKE TEST. It checks that every method runs end to end on real chips and measures how
long each step takes, so the Stage 3 search can be sized to the laptop.

  * It touches OFFICIAL VALIDATION chips only; the leakage guard refuses anything else.
  * The numbers it prints are NOT results. Nothing is tuned, nothing is selected from them, and the
    nominal parameters below were fixed before running (midpoints of the config menus).

Run with: PYTHONPATH=. python scripts/smoke_stage2.py | tee results/stage2_smoke_output.txt
"""

import random
import tempfile
import time

import numpy as np

from src.config import b1_threshold_grid, clip_range, load_config
from src.evaluate import evaluate_chip
from src.io import read_chip
from src.methods import FixedThresholdVV, OtsuThreshold, PixelKMeans, SlicKMeans
from src.methods.slic_kmeans import slic_segments
from src.metrics import (f1, has_truth_flood, iou, is_excluded, pool, precision, recall,
                         stratum)
from src.preprocess import preprocess
from src.slic_cache import SegmentationCache
from src.splits import assert_only_from, chip_event, load_official_splits

N_CHIPS = 6

cfg = load_config()
seed = cfg["seed"]

# Nominal, untuned parameters (fixed before running):
NOMINAL_B1_DB = float(np.median(b1_threshold_grid(cfg)))  # midpoint of the -30..-8 dB menu
NOMINAL_K = 3
NOMINAL_N_SEGMENTS, NOMINAL_COMPACTNESS, NOMINAL_FEATURES = 500, 0.05, "vv_vh"
PREP_VARIANTS = {
    "clip=none,median=0": (None, 0),
    "clip=medium,median=3": (clip_range(cfg, "medium"), 3),  # exercises the clip + filter path
}


def nice(x):
    return "  n/a" if x != x else f"{x:5.3f}"


def main():
    splits = load_official_splits()
    rng = random.Random(seed)
    candidates = sorted(splits["valid"])
    rng.shuffle(candidates)

    chips, skipped = [], []
    for cid in candidates:
        chip = read_chip(cid)
        probe = evaluate_chip(FixedThresholdVV(-20.0), chip)
        if is_excluded(probe["flood_only"]):
            skipped.append(cid)  # zero valid pixels: dropped by the protocol's exclusion rule
            continue
        chips.append(chip)
        if len(chips) == N_CHIPS:
            break

    chosen = [c["id"] for c in chips]
    assert_only_from(
        chosen + skipped,
        allowed_ids=splits["valid"],
        forbidden_ids=splits["test"] + splits["bolivia"] + splits["train"],
        what="smoke test",
    )
    print("SMOKE TEST: official VALIDATION chips only. Not results; nothing tuned or selected.")
    print(f"Chips: {chosen}")
    print(f"Skipped (zero valid pixels): {skipped}")
    print(f"Nominal B1 threshold {NOMINAL_B1_DB:g} dB; k={NOMINAL_K}; SLIC n_segments="
          f"{NOMINAL_N_SEGMENTS}, compactness={NOMINAL_COMPACTNESS}, features={NOMINAL_FEATURES}")

    cache = SegmentationCache(tempfile.mkdtemp(prefix="slic_smoke_"))
    methods = [
        FixedThresholdVV(NOMINAL_B1_DB),
        OtsuThreshold("vv"),
        OtsuThreshold("vh"),
        PixelKMeans(k=NOMINAL_K, seed=seed),
        SlicKMeans(k=NOMINAL_K, n_segments=NOMINAL_N_SEGMENTS, compactness=NOMINAL_COMPACTNESS,
                   features=NOMINAL_FEATURES, seed=seed, cache=cache),
    ]

    for prep_name, (clip, window) in PREP_VARIANTS.items():
        print(f"\n=== Preprocessing: {prep_name} ===")
        print("per-chip flood-only IoU (n/a = chip has no flood-only truth pixel)")
        print(f"{'chip':18s} {'stratum':8s} " + " ".join(f"{m.name[:14]:>14s}" for m in methods))
        counts = {m.name: {"flood_only": [], "all_water": [], "fo_oracle": [], "aw_oracle": []}
                  for m in methods}
        seconds = {m.name: [] for m in methods}
        for chip in chips:
            row = []
            for m in methods:
                key = f"{chip['id']}|{prep_name}"
                t0 = time.perf_counter()
                out = evaluate_chip(m, chip, clip, window, cache_key=key, with_oracle=True)
                seconds[m.name].append(time.perf_counter() - t0)
                for mode in ("flood_only", "all_water"):
                    counts[m.name][mode].append(out[mode])
                if "flood_only_oracle" in out:
                    counts[m.name]["fo_oracle"].append(out["flood_only_oracle"])
                    counts[m.name]["aw_oracle"].append(out["all_water_oracle"])
                row.append(nice(iou(out["flood_only"]) if has_truth_flood(out["flood_only"])
                                else float("nan")))
            st = stratum(counts[methods[0].name]["flood_only"][-1])
            print(f"{chip['id']:18s} {st:8s} " + " ".join(f"{r:>14s}" for r in row))

        print(f"\npooled over these {len(chips)} chips (smoke test only):")
        print(f"{'method':44s} {'FO-IoU':>6s} {'FO-F1':>6s} {'FO-P':>6s} {'FO-R':>6s} "
              f"{'AW-IoU':>6s} {'FO-oracle':>9s} {'s/chip':>7s}")
        for m in methods:
            fo, aw = pool(counts[m.name]["flood_only"]), pool(counts[m.name]["all_water"])
            oracle = (nice(iou(pool(counts[m.name]["fo_oracle"])))
                      if counts[m.name]["fo_oracle"] else "      n/a")
            print(f"{m.name:44s} {nice(iou(fo))} {nice(f1(fo))} {nice(precision(fo))} "
                  f"{nice(recall(fo))} {nice(iou(aw))} {oracle:>9s} "
                  f"{np.mean(seconds[m.name]):7.2f}")

    print(f"\nSLIC cache: {cache.misses} misses, {cache.hits} hits "
          "(each chip x preprocessing is segmented once, then reused)")

    # ---- timing, to size the Stage 3 search -----------------------------------------------
    print("\n=== Timing on one chip (seconds), to size the tuning search ===")
    chip = chips[0]
    vv, vh = preprocess(chip["vv"], chip["vh"], None, 0)
    for n in cfg["search_space"]["m2_slic_kmeans"]["n_segments"]:
        t0 = time.perf_counter()
        slic_segments(vv, vh, n, NOMINAL_COMPACTNESS)
        print(f"  SLIC segmentation, n_segments={n:5d}: {time.perf_counter() - t0:5.2f} s")
    for k in cfg["search_space"]["m1_pixel_kmeans"]["k"]:
        t0 = time.perf_counter()
        PixelKMeans(k=k, seed=seed).cluster_map(vv, vh)
        print(f"  pixel k-means, k={k}: {time.perf_counter() - t0:5.2f} s")
    tmp_cache = SegmentationCache(tempfile.mkdtemp(prefix="slic_time_"))
    m2 = SlicKMeans(k=NOMINAL_K, n_segments=NOMINAL_N_SEGMENTS, compactness=NOMINAL_COMPACTNESS,
                    features=NOMINAL_FEATURES, seed=seed, cache=tmp_cache)
    t0 = time.perf_counter()
    m2.cluster_map(vv, vh, cache_key="timing")
    cold = time.perf_counter() - t0
    t0 = time.perf_counter()
    m2.cluster_map(vv, vh, cache_key="timing")
    warm = time.perf_counter() - t0
    print(f"  M2 end to end, cache miss: {cold:5.2f} s;  cache hit (k-means only): {warm:5.2f} s")
    n_all = 446
    print(f"  => one M2 configuration over all {n_all} chips: about {cold * n_all / 60:.1f} min "
          f"uncached, {warm * n_all / 60:.1f} min once its segmentation is cached")
    print(f"  => one B1/B2 configuration is negligible next to that; M1 at k=3: about "
          f"{n_all * np.mean(seconds['M1_pixel_kmeans_k3']) / 60:.1f} min per pass")


if __name__ == "__main__":
    main()
