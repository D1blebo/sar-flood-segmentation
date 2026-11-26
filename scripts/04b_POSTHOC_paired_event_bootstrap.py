"""
POST-HOC (not in the pre-declared protocol): paired, event-level bootstrap of the held-out pooled flood-only IoU.

Why this exists. The chip-level intervals written by scripts/04_evaluate.py treat chips as independent, but chips
cut from one flood image are not. This script resamples whole EVENTS instead, and because every method is scored
on the same events it also reports PAIRED differences (method A minus method B on the same resampled events).

What it reads. Only results/heldout_results.json: the per-event pooled confusion counts (tp, fp, fn) that the
single locked held-out run already stored. It does NOT read any chip, does NOT re-score anything, and does NOT
touch the held-out lock. So it cannot leak and cannot change a held-out number.

Label. This analysis was chosen AFTER the held-out results were seen, so it is POST-HOC and every output says so.

Method. 10,000 resamples, seed 42. Each resample draws the 11 events with replacement, sums tp/fp/fn over the
drawn events, and computes pooled IoU = tp / (tp + fp + fn). The same draws are used for every method, which is
what makes the differences paired. Intervals are 2.5th to 97.5th percentiles. The point estimate is always the
statistic on the real, un-resampled events.

  PYTHONPATH=. python scripts/04b_POSTHOC_paired_event_bootstrap.py
"""

import csv
import json

import numpy as np

from src.config import REPO_ROOT

LABEL = "POST-HOC (not pre-declared); LOEO, primary criterion, flood-only"
N_RESAMPLES, SEED, CONFIDENCE = 10_000, 42, 0.95
VARIANTS = ("b1", "b2_vv", "b2_vh", "m1", "m2", "b2g_vv", "b2g_vh", "m1g", "m2g")
# (first, second): the reported difference is first minus second
PAIRS = (("m2g", "b1"), ("m1g", "b1"), ("m2g", "m1g"), ("m2g", "m2"), ("m1g", "m1"), ("b1", "m2"))
IN_JSON = REPO_ROOT / "results" / "heldout_results.json"
OUT_CSV = REPO_ROOT / "results" / "heldout_POSTHOC_paired_event_bootstrap.csv"


def pooled_iou(counts):
    """counts: array (n_events, 3) of [tp, fp, fn]. Pooled IoU of the summed counts; NaN if the denominator is 0."""
    total = counts.sum(axis=0)
    denom = total.sum()
    return float(total[0] / denom) if denom > 0 else float("nan")


def event_draws(n_events, n_resamples, seed):
    """Indices (n_resamples, n_events) of events drawn with replacement. One shared set of draws for all methods."""
    return np.random.default_rng(seed).integers(0, n_events, size=(n_resamples, n_events))


def bootstrap_values(counts, draws):
    """Pooled IoU of every resample, for one method."""
    return np.array([pooled_iou(counts[idx]) for idx in draws])


def percentile_interval(values, confidence=CONFIDENCE):
    alpha = (1.0 - confidence) / 2.0
    lo, hi = np.nanpercentile(values, [100 * alpha, 100 * (1 - alpha)])
    return float(lo), float(hi)


def load_event_counts(path=IN_JSON, criterion="primary", mode="flood_only"):
    """({variant: array (n_events, 3)}, event names). Events are sorted by name so every method uses the same order."""
    results = json.loads(path.read_text())[criterion]
    events = sorted(results[VARIANTS[0]]["loeo"][mode]["per_event"])
    counts = {}
    for v in VARIANTS:
        per_event = results[v]["loeo"][mode]["per_event"]
        assert sorted(per_event) == events, f"{v}: event list differs"
        counts[v] = np.array([[per_event[e]["pooled"][k] for k in ("tp", "fp", "fn")] for e in events], dtype=float)
    return counts, events


def main():
    counts, events = load_event_counts()
    draws = event_draws(len(events), N_RESAMPLES, SEED)
    boot = {v: bootstrap_values(counts[v], draws) for v in VARIANTS}

    rows = []
    print(f"{LABEL}\n{len(events)} events, {N_RESAMPLES} resamples, seed {SEED}\n")
    print("Event-level interval for pooled IoU, per method:")
    for v in VARIANTS:
        lo, hi = percentile_interval(boot[v])
        point = pooled_iou(counts[v])
        rows.append({"label": LABEL, "kind": "method", "first": v, "second": "", "point": point, "ci95_lo": lo, "ci95_hi": hi})
        print(f"  {v:7s} {point:.3f} ({lo:.3f} to {hi:.3f})")
    print("\nPaired difference in pooled IoU (first minus second), same resampled events:")
    for a, b in PAIRS:
        lo, hi = percentile_interval(boot[a] - boot[b])
        point = pooled_iou(counts[a]) - pooled_iou(counts[b])
        rows.append({"label": LABEL, "kind": "paired_difference", "first": a, "second": b, "point": point, "ci95_lo": lo, "ci95_hi": hi})
        print(f"  {a:4s} minus {b:4s} {point:+.3f} ({lo:+.3f} to {hi:+.3f})")

    with open(OUT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nwritten: {OUT_CSV.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
