"""
Amendment 2, item 4: two speed decisions, checked BEFORE any tuning.

(a) M1 subsample fit. Fit k-means on a random subsample of valid pixels, then assign all pixels.
    Compared with the full fit on 20 official TRAIN chips, for k = 2..5 and two preprocessing
    settings. No labels are used anywhere in the comparison.
    Two agreement measures per (chip, k, preprocessing):
      partition agreement : share of valid pixels given the same cluster, after matching the two
                            fits' arbitrary cluster ids optimally (Hungarian matching)
      water-mask IoU      : IoU of the two water masks chosen by the a-priori rule (what is scored)
    ADOPTION RULE, fixed before running: adopt only if over all 20 x 4 x 2 comparisons
      mean partition agreement >= 0.99 AND worst >= 0.95
      AND mean water-mask IoU >= 0.99 AND worst >= 0.95.
    Otherwise M1 keeps the full fit.
(b) Parallel across chips. Times the same 20 chips serially and with 4 and 8 worker processes and
    asserts the results are identical (timing only; no scores are printed).

Run with: PYTHONPATH=. python scripts/verify_speed_checks.py | tee results/speed_checks_output.txt
"""

import random
import time

import numpy as np
from scipy.optimize import linear_sum_assignment

from src.cluster_rule import water_cluster_lowest_mean_vv
from src.config import clip_range, load_config
from src.evaluate import evaluate_chip_id
from src.io import image_valid_mask, read_chip
from src.methods import PixelKMeans
from src.parallel import map_chips
from src.preprocess import preprocess
from src.splits import assert_only_from, load_official_splits

SUBSAMPLE = 50_000  # candidate size, fixed before running (about 19% of a 512 x 512 chip)
N_CHIPS = 20
PREPS = {"clip=none,median=0": (None, 0), "clip=medium,median=3": ("medium", 3)}


def matched_agreement(a, b, valid):
    """Share of valid pixels with the same cluster after optimally matching the cluster ids."""
    x, y = a[valid], b[valid]
    k = int(max(x.max(), y.max())) + 1
    table = np.zeros((k, k), dtype=np.int64)
    np.add.at(table, (x, y), 1)
    rows, cols = linear_sum_assignment(-table)  # maximise the matched pixel count
    return table[rows, cols].sum() / len(x)


def mask_iou(m1, m2):
    union = (m1 | m2).sum()
    return 1.0 if union == 0 else (m1 & m2).sum() / union


def rule_mask(cmap, vv):
    water = water_cluster_lowest_mean_vv(cmap, vv)
    return np.zeros(vv.shape, bool) if water is None else cmap == water


def main():
    cfg = load_config()
    seed = cfg["seed"]
    splits = load_official_splits()
    ids = sorted(splits["train"])
    random.Random(seed).shuffle(ids)
    chips = []
    for cid in ids:
        chip = read_chip(cid)
        if (image_valid_mask(chip["vv"], chip["vh"]) & (chip["label"] != -1)).any():
            chips.append(chip)  # skip chips that the protocol excludes (no valid pixel)
        if len(chips) == N_CHIPS:
            break
    chosen = [c["id"] for c in chips]
    assert_only_from(chosen, splits["train"], splits["valid"] + splits["test"] + splits["bolivia"],
                     "speed check")
    print(f"(a) M1 subsample fit: {SUBSAMPLE:,} pixels vs full fit, {N_CHIPS} official TRAIN chips")
    print(f"chips: {chosen}")

    part, iou_, t_full, t_sub = {}, {}, 0.0, 0.0
    for prep_name, (clip_name, window) in PREPS.items():
        clip = clip_range(cfg, clip_name) if clip_name else None
        for chip in chips:
            vv, vh = preprocess(chip["vv"], chip["vh"], clip, window)
            valid = image_valid_mask(vv, vh)
            for k in (2, 3, 4, 5):
                t0 = time.perf_counter()
                full = PixelKMeans(k, seed).cluster_map(vv, vh)
                t_full += time.perf_counter() - t0
                t0 = time.perf_counter()
                sub = PixelKMeans(k, seed, fit_subsample=SUBSAMPLE).cluster_map(vv, vh)
                t_sub += time.perf_counter() - t0
                part.setdefault((prep_name, k), []).append(matched_agreement(full, sub, valid))
                iou_.setdefault((prep_name, k), []).append(
                    mask_iou(rule_mask(full, vv), rule_mask(sub, vv)))

    print(f"\n{'preprocessing':22s} {'k':>2s} | partition agreement: mean   worst | "
          f"water-mask IoU: mean   worst")
    for (prep_name, k), p in part.items():
        q = iou_[(prep_name, k)]
        print(f"{prep_name:22s} {k:2d} | {np.mean(p):27.4f} {np.min(p):7.4f} | "
              f"{np.mean(q):24.4f} {np.min(q):7.4f}")
    all_p = np.concatenate([v for v in part.values()])
    all_q = np.concatenate([v for v in iou_.values()])
    print(f"\nOVERALL ({len(all_p)} comparisons): partition agreement mean {all_p.mean():.4f}, "
          f"worst {all_p.min():.4f}; water-mask IoU mean {all_q.mean():.4f}, worst {all_q.min():.4f}")
    print(f"fit time, one thread: full {t_full:.1f} s, subsample {t_sub:.1f} s "
          f"(x{t_full / t_sub:.1f} faster)")
    ok = all_p.mean() >= 0.99 and all_p.min() >= 0.95 and all_q.mean() >= 0.99 and all_q.min() >= 0.95
    print("DECISION by the pre-declared rule:", "ADOPT the subsample fit" if ok
          else "DO NOT ADOPT (M1 keeps the full fit)")

    print("\n(b) Parallel across chips (same 20 chips, M1 k=3 full fit, timing only)")
    kw = dict(method=PixelKMeans(3, seed), clip=None, median_window=0, prep_name="speed")
    results = {}
    for n_jobs in (1, 4, 8):
        t0 = time.perf_counter()
        results[n_jobs] = map_chips(evaluate_chip_id, chosen, n_jobs=n_jobs, **kw)
        print(f"  n_jobs={n_jobs}: {time.perf_counter() - t0:6.1f} s")
    print(f"  results identical across n_jobs: {results[1] == results[4] == results[8]}")


if __name__ == "__main__":
    main()
