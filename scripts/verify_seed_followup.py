"""
Amendment 4, A4.1: follow-up to the M1 seed check with more k-means restarts (n_init).
Same 40 official TRAIN chips, same 5 seeds, same two preprocessing settings as the first check
(config.seed_sensitivity), runs and threshold from config.seed_sensitivity_followup. No labels used.

For every comparison where the water mask changed (IoU with the reference seed < 0.95) it also
reports the size of the chosen water cluster as a share of valid pixels, to test the guess that the
instability comes from tiny outlier clusters.

The pre-declared decision rule (protocol A4.1) is applied at the end and PRINTED; nothing is changed
in the config by this script.

Run with: PYTHONPATH=. python scripts/verify_seed_followup.py > results/seed_followup_output.txt
"""

import math
import random
import time
from collections import defaultdict

import numpy as np
from threadpoolctl import threadpool_limits

from src.config import clip_range, load_config
from src.io import image_valid_mask, read_chip
from src.methods import PixelKMeans
from src.parallel import map_chips
from src.preprocess import preprocess
from src.seed_check import seed_rows_for_chip
from src.splits import assert_only_from, load_official_splits


def wilson(k, n, z=1.96):
    """95% Wilson interval for a proportion k/n."""
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return centre - half, centre + half


def main():
    cfg = load_config()
    sc, fu = cfg["seed_sensitivity"], cfg["seed_sensitivity_followup"]
    thr, limit, tiny = sc["changed_if_water_mask_iou_below"], fu["changed_fraction_limit"], fu["tiny_cluster_fraction"]
    splits = load_official_splits()
    ids = sorted(splits["train"])
    random.Random(cfg["seed"]).shuffle(ids)
    chips = []
    for cid in ids:
        chip = read_chip(cid)
        if (image_valid_mask(chip["vv"], chip["vh"]) & (chip["label"] != -1)).any():
            chips.append(cid)
        if len(chips) == sc["n_chips"]:
            break
    assert_only_from(chips, splits["train"], splits["valid"] + splits["test"] + splits["bolivia"],
                     "seed follow-up")
    print(f"M1 seed follow-up, {len(chips)} official TRAIN chips (same as the first check), seeds="
          f"{sc['seeds']} (reference {sc['seeds'][0]}); 'changed' = water-mask IoU < {thr}; no labels.")
    print(f"tiny water cluster (descriptive) = below {tiny:.0%} of valid pixels\n")

    rows = []
    for run in fu["runs"]:
        t0 = time.perf_counter()
        part = [r for chip_rows in map_chips(seed_rows_for_chip, chips, cfg["compute"]["n_jobs"],
                                             ks=run["k"], n_init=run["n_init"]) for r in chip_rows]
        rows += part
        print(f"[{run['label']}, k={run['k']}: {len(part)} comparisons in {time.perf_counter() - t0:.0f} s]")

    groups = defaultdict(list)
    for r in rows:
        groups[(r["n_init"], r["prep"], r["k"])].append(r)

    print("\n=== A. How often does the water mask change? ===")
    print(f"{'n_init':>6s} {'preprocessing':22s} {'k':>2s} | changed / comparisons  rate   [95% CI]        | "
          f"chips with any change | IoU median  worst")
    rates = {}
    for key in sorted(groups):
        n_init, prep, k = key
        rs = groups[key]
        ious = np.array([r["iou"] for r in rs])
        changed = int((ious < thr).sum())
        lo, hi = wilson(changed, len(rs))
        by_chip = defaultdict(bool)
        for r in rs:
            by_chip[r["chip"]] |= r["iou"] < thr
        rates[key] = changed / len(rs)
        print(f"{n_init:6d} {prep:22s} {k:2d} | {changed:7d} / {len(rs):3d}        {rates[key]:6.1%} "
              f"[{lo:5.1%}, {hi:5.1%}] | {sum(by_chip.values()):8d} of {len(by_chip):2d}       | "
              f"{np.median(ious):9.3f} {ious.min():6.3f}")

    print("\n=== B. Size of the chosen water cluster (share of valid pixels), changed vs unchanged ===")
    print(f"{'n_init':>6s} {'preprocessing':22s} {'k':>2s} | changed: n  median ref  median alt  "
          f"share with a tiny cluster (<{tiny:.0%}) | unchanged: median")
    for key in sorted(groups):
        n_init, prep, k = key
        rs = groups[key]
        ch = [r for r in rs if r["iou"] < thr]
        un = [r for r in rs if r["iou"] >= thr]
        frac = lambda r, which: r[which] / r["valid_px"]
        if ch:
            ref = np.median([frac(r, "reference_water_px") for r in ch])
            alt = np.median([frac(r, "seed_water_px") for r in ch])
            n_tiny = sum(min(frac(r, "reference_water_px"), frac(r, "seed_water_px")) < tiny for r in ch)
            tail = f"{ref:9.3%}  {alt:9.3%}  {n_tiny:3d} of {len(ch):3d} ({n_tiny / len(ch):5.1%})"
        else:
            tail = "     -          -        -"
        un_med = np.median([frac(r, "reference_water_px") for r in un]) if un else float("nan")
        print(f"{n_init:6d} {prep:22s} {k:2d} | {len(ch):11d}  {tail} | {un_med:9.3%}")

    print("\n=== C. Test of the guess 'tiny outlier clusters, especially with no clip' (changed comparisons) ===")
    for n_init in sorted({r["n_init"] for r in rows}):
        for prep in sorted({r["prep"] for r in rows}):
            ch = [r for r in rows if r["n_init"] == n_init and r["prep"] == prep and r["iou"] < thr]
            if not ch:
                print(f"  n_init={n_init:2d} {prep:22s}: no changed comparisons")
                continue
            tinies = [r for r in ch if min(r["reference_water_px"], r["seed_water_px"]) / r["valid_px"] < tiny]
            mv = [min(r["reference_mean_vv"], r["seed_mean_vv"]) for r in tinies]
            extra = f"; median mean-VV of the darker cluster in those: {np.median(mv):.1f} dB" if mv else ""
            print(f"  n_init={n_init:2d} {prep:22s}: {len(tinies):3d} of {len(ch):3d} changed comparisons "
                  f"({len(tinies) / len(ch):5.1%}) involve a tiny water cluster{extra}")

    print("\n=== D. Timing, one thread, first %d chips, no clip / median 0 (seconds per k-means fit) ===" % fu["timing_chips"])
    times = {}
    with threadpool_limits(1):
        for k in (3, 4, 5):
            for n_init in (3, 10):
                ts = []
                for cid in chips[:fu["timing_chips"]]:
                    chip = read_chip(cid)
                    vv, vh = preprocess(chip["vv"], chip["vh"], None, 0)
                    t0 = time.perf_counter()
                    PixelKMeans(k, cfg["seed"], n_init=n_init, max_iter=cfg["kmeans"]["max_iter"]).cluster_map(vv, vh)
                    ts.append(time.perf_counter() - t0)
                times[(k, n_init)] = float(np.mean(ts))
                print(f"  k={k} n_init={n_init:2d}: {times[(k, n_init)]:.2f} s")

    print("\n=== E. PRE-DECLARED DECISION RULE (protocol A4.1), applied mechanically ===")
    preps = sorted({r["prep"] for r in rows})
    for k in (4, 5):
        rs = [rates[(10, p, k)] for p in preps]
        ok = all(x < limit for x in rs)
        border = any(abs(x - limit) <= 0.04 for x in rs)
        print(f"  k={k}: n_init=10 rates {[f'{x:.1%}' for x in rs]} -> "
              + ("USE n_init=10 for M1 at this k" if ok else "DROP this k from M1 (report as a finding)")
              + ("   [BORDERLINE: within 4 points of the limit]" if border else ""))
    r3 = [rates[(3, p, 3)] for p in preps]
    r3_10 = [rates[(10, p, 3)] for p in preps]
    unstable3 = any(x >= limit for x in r3)
    border3 = any(abs(x - limit) <= 0.04 for x in r3)
    print(f"  k=3 at n_init=3: rates {[f'{x:.1%}' for x in r3]} -> "
          + ("UNSTABLE: Stage 1's M1 uses n_init=10; new time estimate required" if unstable3
             else "stable: Stage 1's M1 keeps n_init=3")
          + ("   [BORDERLINE]" if border3 else ""))
    if unstable3:
        still = any(x >= limit for x in r3_10)
        print(f"  k=3 at n_init=10: rates {[f'{x:.1%}' for x in r3_10]} -> "
              + ("STILL >= limit: NOT COVERED by the rule; STOP AND ASK" if still else "below the limit"))
        per_fit3, per_fit10 = times[(3, 3)], times[(3, 10)]
        print(f"  M1 fit time at k=3: {per_fit3:.2f} s (n_init=3) -> {per_fit10:.2f} s (n_init=10), "
              f"x{per_fit10 / per_fit3:.1f}")


if __name__ == "__main__":
    main()
