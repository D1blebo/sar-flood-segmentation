"""
Amendment 3, A3.3: seed sensitivity of M1's lowest-VV cluster at k=4 and k=5.
TUNING chips only (official TRAIN chips), no labels used. Settings come from config.seed_sensitivity,
fixed before running. A seed "changes" the water cluster on a chip if its water mask has IoU below
`changed_if_water_mask_iou_below` with the reference seed's mask.

Run with: PYTHONPATH=. python scripts/verify_seed_sensitivity.py > results/seed_sensitivity_output.txt
"""

import random
import time
from collections import defaultdict

import numpy as np

from src.config import load_config
from src.io import image_valid_mask, read_chip
from src.parallel import map_chips
from src.seed_check import seed_rows_for_chip
from src.splits import assert_only_from, load_official_splits


def main():
    cfg = load_config()
    sc = cfg["seed_sensitivity"]
    threshold = sc["changed_if_water_mask_iou_below"]
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
                     "seed sensitivity")
    print(f"M1 seed sensitivity, {len(chips)} official TRAIN chips, k={sc['k']}, seeds={sc['seeds']} "
          f"(reference seed {sc['seeds'][0]}), n_init={cfg['kmeans']['n_init']}")
    print(f"'changed' = water-mask IoU with the reference seed < {threshold}. No labels used.\n")

    t0 = time.perf_counter()
    rows = [r for chip_rows in map_chips(seed_rows_for_chip, chips, cfg["compute"]["n_jobs"])
            for r in chip_rows]
    print(f"({len(rows)} comparisons in {time.perf_counter() - t0:.0f} s)\n")

    groups = defaultdict(list)
    for r in rows:
        groups[(r["prep"], r["k"])].append(r)
    print(f"{'preprocessing':22s} {'k':>2s} | comparisons  changed  rate | chips with any change | "
          f"IoU median  worst")
    for (prep, k), rs in sorted(groups.items()):
        ious = np.array([r["iou"] for r in rs])
        changed = ious < threshold
        by_chip = defaultdict(bool)
        for r in rs:
            by_chip[r["chip"]] |= r["iou"] < threshold
        print(f"{prep:22s} {k:2d} | {len(rs):11d} {changed.sum():8d} {changed.mean():5.1%} | "
              f"{sum(by_chip.values()):8d} of {len(by_chip):2d}        | "
              f"{np.median(ious):9.3f} {ious.min():6.3f}")
    print("\nper seed (all k and preprocessing pooled):")
    for seed in sc["seeds"][1:]:
        ious = np.array([r["iou"] for r in rows if r["seed"] == seed])
        print(f"  seed {seed}: changed on {(ious < threshold).mean():.1%} of {len(ious)} comparisons")


if __name__ == "__main__":
    main()
