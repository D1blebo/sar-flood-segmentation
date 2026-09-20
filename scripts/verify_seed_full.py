"""
Amendment 5: full seed-sensitivity check, label-free, on the same 40 official TRAIN chips and 5 seeds.

  python scripts/verify_seed_full.py m1   # k = 2..5, n_init 3 and 10, four preprocessing conditions
  python scripts/verify_seed_full.py m2   # k = 2..5 x four feature sets, n_init 3 and 10, four conditions,
                                          # nominal SLIC (500 segments, compactness 0.05), cached segmentations

"Changed" = water-mask IoU with the reference seed (42) below 0.95. The decision rules (protocol A5.1 for M1,
A5.2 for M2) are applied and PRINTED at the end; this script changes nothing in the config.
Per-comparison rows are saved to data/seed_checks/ (git-ignored).

Run with: PYTHONPATH=. python scripts/verify_seed_full.py m1 > results/seed_m1_full_output.txt
"""

import csv
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from src.config import REPO_ROOT, load_config, prep_name
from src.io import image_valid_mask, read_chip
from src.parallel import map_chips
from src.seed_check import full_check_rows_for_chip
from src.splits import assert_only_from, load_official_splits


def cell(rs, thr):
    """Statistics of one group of comparisons."""
    ious = np.array([r["iou"] for r in rs])
    changed = ious < thr
    ch = [r for r, c in zip(rs, changed) if c]
    tiny_ok = [min(r["reference_water_px"], r["seed_water_px"]) / r["valid_px"] for r in ch]
    return {
        "n": len(rs), "changed": int(changed.sum()), "chips": len({r["chip"] for r in ch}),
        "worst": float(ious.min()),
        "ref_mean": float(np.mean([r["reference_mean_vv"] for r in ch])) if ch else float("nan"),
        "alt_mean": float(np.mean([r["seed_mean_vv"] for r in ch])) if ch else float("nan"),
        "tiny_frac": [t for t in tiny_ok],
    }


def rate(rows, thr, **where):
    rs = [r for r in rows if all(r[k] == v for k, v in where.items())]
    return sum(r["iou"] < thr for r in rs), len(rs)


def pooled(rows, thr, preps, **where):
    rs = [r for r in rows if r["prep"] in preps and all(r[k] == v for k, v in where.items())]
    return sum(r["iou"] < thr for r in rs), len(rs)


def main(which):
    cfg = load_config()
    sc, full = cfg["seed_sensitivity"], cfg["seed_sensitivity_full"]
    thr, limit = sc["changed_if_water_mask_iou_below"], full["changed_fraction_limit"]
    tie_pp = full["n_init_tie_within_pp"]
    conds = [prep_name(c["clip"], c["median"]) for c in full["conditions"]]
    original = [prep_name(c["clip"], c["median"]) for c in full["original_conditions"]]

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
    assert_only_from(chips, splits["train"], splits["valid"] + splits["test"] + splits["bolivia"], "seed full")
    print(f"{which.upper()} seed check, {len(chips)} official TRAIN chips (same as before), seeds={sc['seeds']} "
          f"(reference {sc['seeds'][0]}), 'changed' = water-mask IoU < {thr}, no labels used.")
    for i, c in enumerate(conds, 1):
        print(f"  C{i} = {c}" + ("   (one of the two original conditions)" if c in original else ""))

    t0 = time.perf_counter()
    rows = [r for chip_rows in map_chips(full_check_rows_for_chip, chips, cfg["compute"]["n_jobs"], which=which)
            for r in chip_rows]
    print(f"\n{len(rows)} comparisons in {time.perf_counter() - t0:.0f} s\n")
    out_dir = REPO_ROOT / full["rows_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / f"seed_{which}_rows.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    variants = sorted({(r["features"], r["k"]) for r in rows}, key=lambda x: (x[0], x[1]))
    n_inits = sorted({r["n_init"] for r in rows})
    n_chips = len(chips)

    print("=== TABLE 1. changed comparisons / comparisons made | chips with any change / %d | worst IoU ===" % n_chips)
    print("(each cell: 'changed/made  chips/%d  worstIoU')" % n_chips)
    head = f"{'features':11s} {'k':>2s} {'n_init':>6s} | " + " | ".join(f"{'C%d' % (i + 1):^26s}" for i in range(len(conds)))
    print(head)
    stats = {}
    for feats, k in variants:
        for n_init in n_inits:
            parts = []
            for c in conds:
                rs = [r for r in rows if r["features"] == feats and r["k"] == k and r["n_init"] == n_init and r["prep"] == c]
                st = cell(rs, thr)
                stats[(feats, k, n_init, c)] = st
                parts.append(f"{st['changed']:3d}/{st['n']:3d}  {st['chips']:2d}/{n_chips}  {st['worst']:6.3f}")
            print(f"{feats or '-':11s} {k:2d} {n_init:6d} | " + " | ".join(f"{p:^26s}" for p in parts))

    print("\n=== TABLE 2. mean VV (dB) of the chosen water cluster in CHANGED comparisons: reference seed / other seed (n changed) ===")
    print(head)
    for feats, k in variants:
        for n_init in n_inits:
            parts = []
            for c in conds:
                st = stats[(feats, k, n_init, c)]
                parts.append("-" if st["changed"] == 0 else f"{st['ref_mean']:6.1f}/{st['alt_mean']:6.1f} (n={st['changed']})")
            print(f"{feats or '-':11s} {k:2d} {n_init:6d} | " + " | ".join(f"{p:^26s}" for p in parts))
    unch = [r["reference_mean_vv"] for r in rows if r["iou"] >= thr]
    ch_all = [r["reference_mean_vv"] for r in rows if r["iou"] < thr]
    mean_or_nan = lambda xs: float(np.mean(xs)) if len(xs) else float("nan")
    print(f"context, all settings pooled: mean VV of the reference water cluster = {mean_or_nan(unch):.1f} dB in unchanged "
          f"comparisons ({len(unch)}), {mean_or_nan(ch_all):.1f} dB in changed ones ({len(ch_all)})")

    print("\n=== TABLE 3. Reconciling the earlier counts (the two ORIGINAL conditions only, C-labels above) ===")
    if which == "m1":
        for label, ks, n_init in [("first check (k=4,5; n_init 3)", (4, 5), 3),
                                  ("follow-up, n_init 10 (k=3,4,5)", (3, 4, 5), 10),
                                  ("follow-up, n_init 3 (k=3 only)", (3,), 3),
                                  ("matched to the first check: k=4,5 at n_init 10", (4, 5), 10),
                                  ("matched: k=3 at n_init 10", (3,), 10)]:
            c = sum(pooled(rows, thr, original, k=k, n_init=n_init)[0] for k in ks)
            n = sum(pooled(rows, thr, original, k=k, n_init=n_init)[1] for k in ks)
            print(f"  {label:50s}: {c:4d} changed of {n:4d} comparisons")
        print("  (earlier reports: 183 of 640, 154 of 960 and 32 of 320)")
    else:
        print("  (not applicable to M2: no earlier M2 check)")

    print("\n=== TABLE 4. Pooled changed fraction ===")
    for feats, k in variants:
        for n_init in n_inits:
            c4, n4 = pooled(rows, thr, conds, features=feats, k=k, n_init=n_init)
            c2, n2 = pooled(rows, thr, original, features=feats, k=k, n_init=n_init)
            print(f"  {feats or '-':11s} k={k} n_init={n_init:2d}: four conditions {c4:3d}/{n4:3d} = {c4 / n4:6.1%}; "
                  f"original two {c2:3d}/{n2:3d} = {c2 / n2:6.1%}")

    print("\n=== TABLE 5. Tiny water clusters (descriptive; tiny = below %.0f%% of valid pixels) ===" % (100 * full["tiny_cluster_fraction"]))
    ch_rows = [r for r in rows if r["iou"] < thr]
    n_tiny = sum(min(r["reference_water_px"], r["seed_water_px"]) / r["valid_px"] < full["tiny_cluster_fraction"] for r in ch_rows)
    print(f"  {n_tiny} of {len(ch_rows)} changed comparisons involve a tiny water cluster")

    print("\n=== PRE-DECLARED RULES (protocol %s), applied mechanically ===" % ("A5.1" if which == "m1" else "A5.2"))
    if which == "m1":
        for k in (2, 3):
            c3, n3 = pooled(rows, thr, conds, k=k, n_init=3)
            c10, n10 = pooled(rows, thr, conds, k=k, n_init=10)
            p3, p10 = c3 / n3, c10 / n10
            chosen = 3 if abs(p3 - p10) * 100 <= tie_pp else (10 if p10 < p3 else 3)
            why = "within %g points -> 3" % tie_pp if abs(p3 - p10) * 100 <= tie_pp else "lower changed fraction"
            worst_cond = max(rate(rows, thr, k=k, n_init=chosen, prep=c)[0] / rate(rows, thr, k=k, n_init=chosen, prep=c)[1] for c in conds)
            print(f"  k={k}: pooled changed fraction n_init 3 = {p3:.1%}, n_init 10 = {p10:.1%} (difference "
                  f"{abs(p3 - p10) * 100:.1f} points) -> n_init = {chosen} ({why}). Instability caveat: "
                  f"pooled {(p3 if chosen == 3 else p10):.1%}, worst single condition {worst_cond:.1%}"
                  f"{' (>= limit)' if worst_cond >= limit else ''}.")
        info = []
        for k in (4, 5):
            c_, n_ = pooled(rows, thr, conds, k=k, n_init=10)
            info.append(f"k={k} {c_ / n_:.1%}" if n_ else f"k={k} (not run)")
        print("  k=4 and k=5: stay dropped from M1 (project owner's decision). For information, pooled at n_init 10: "
              + ", ".join(info))
    else:
        c3, n3 = pooled(rows, thr, conds, n_init=3)
        c10, n10 = pooled(rows, thr, conds, n_init=10)
        p3, p10 = c3 / n3, c10 / n10
        in_force = 3 if (p10 - p3) * 100 > tie_pp else 10
        print(f"  n_init: pooled changed fraction n_init 3 = {p3:.1%} ({c3}/{n3}), n_init 10 = {p10:.1%} ({c10}/{n10}) "
              f"-> n_init {in_force} in force" + (" (REASON NOT TO use 10: it is worse by more than %g points)" % tie_pp if in_force == 3 else " (10 is the default; no reason found against it)"))
        kept, dropped = [], []
        for feats, k in variants:
            per = [rate(rows, thr, features=feats, k=k, n_init=in_force, prep=c) for c in conds]
            rates_ = [a / b for a, b in per]
            (kept if all(x < limit for x in rates_) else dropped).append((feats, k, rates_))
        print("  per (feature set, k) at the n_init in force; KEEP only if the changed fraction is below %.0f%% in EVERY condition:" % (100 * limit))
        for feats, k, rates_ in kept:
            print(f"    KEEP  {feats:11s} k={k}: " + ", ".join(f"{x:.1%}" for x in rates_))
        for feats, k, rates_ in dropped:
            print(f"    DROP  {feats:11s} k={k}: " + ", ".join(f"{x:.1%}" for x in rates_))
        nominal_dropped = any(f == "vv_vh" and k == 3 for f, k, _ in dropped)
        if nominal_dropped:
            print("  NOMINAL (vv_vh, k=3) WOULD BE DROPPED: Stage 1's M2 depends on it -> NOT COVERED, STOP AND ASK")
        if not kept:
            print("  NO (feature set, k) combination would remain -> NOT COVERED, STOP AND ASK")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("m1", "m2"):
        sys.exit("usage: verify_seed_full.py m1|m2")
    main(sys.argv[1])
