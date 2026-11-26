"""
Scoring, exactly as defined in results/evaluation_protocol.md.

Everything is built from per-chip confusion COUNTS (tp, fp, fn, tn, domain). Counts can be
summed across chips (pooled score), cached, and resampled for the bootstrap.

Two modes:
  flood_only : domain = image-valid AND label-valid AND JRC==0   (headline)
  all_water  : domain = image-valid AND label-valid              (secondary)
Pixels outside the domain (NaN image, label -1, and JRC permanent water in flood_only mode)
are ignored: they are never a true/false positive/negative, and never "not flood".
"""

import numpy as np

MODE_FLOOD_ONLY = "flood_only"
MODE_ALL_WATER = "all_water"
MODES = (MODE_FLOOD_ONLY, MODE_ALL_WATER)


def evaluation_domain_and_truth(image_valid, label, jrc, mode):
    """Boolean (domain, truth) arrays for one chip. Truth is water, restricted to the domain."""
    domain = image_valid & (label != -1)
    if mode == MODE_FLOOD_ONLY:
        domain = domain & (jrc == 0)  # JRC applied to the domain, hence to prediction AND truth
    elif mode != MODE_ALL_WATER:
        raise ValueError(f"unknown mode {mode!r}")
    truth = (label == 1) & domain
    return domain, truth


def confusion_counts(pred, truth, domain):
    """tp, fp, fn, tn and domain size, counted only inside `domain`. Returns plain ints."""
    pred = np.asarray(pred, dtype=bool) & domain
    truth = np.asarray(truth, dtype=bool) & domain
    return {
        "tp": int((pred & truth).sum()),
        "fp": int((pred & ~truth).sum()),
        "fn": int((~pred & truth).sum()),
        "tn": int((domain & ~pred & ~truth).sum()),
        "domain": int(domain.sum()),
    }


def pool(counts_list):
    """Sum counts over chips (pooled statistics = metric of the summed counts)."""
    total = {k: 0 for k in ("tp", "fp", "fn", "tn", "domain")}
    for c in counts_list:
        for k in total:
            total[k] += c[k]
    return total


def _ratio(num, den):
    """Undefined (NaN), not 0 or 1, when the denominator is 0."""
    return num / den if den > 0 else float("nan")


def iou(c):
    return _ratio(c["tp"], c["tp"] + c["fp"] + c["fn"])


def precision(c):
    return _ratio(c["tp"], c["tp"] + c["fp"])


def recall(c):
    return _ratio(c["tp"], c["tp"] + c["fn"])


def f1(c):
    return _ratio(2 * c["tp"], 2 * c["tp"] + c["fp"] + c["fn"])


def false_positive_rate(c):
    """fp / (fp + tn): reported for flood-free chips, where IoU and recall are undefined."""
    return _ratio(c["fp"], c["fp"] + c["tn"])


def is_excluded(c):
    """A chip with no pixel in the domain is dropped from that metric."""
    return c["domain"] == 0


def has_truth_flood(c):
    """Per-chip IoU/F1/recall are averaged only over chips with at least one truth pixel."""
    return c["tp"] + c["fn"] > 0


def flood_fraction(c):
    return _ratio(c["tp"] + c["fn"], c["domain"])


def stratum(c, bins=(0.05, 0.30)):
    """'none', '<5%', '5-30%' or '>30%' by truth-flood fraction of the domain."""
    if not has_truth_flood(c):
        return "none"
    frac = flood_fraction(c)
    lo, hi = bins
    lo_pct, hi_pct = round(lo * 100), round(hi * 100)
    if frac < lo:
        return f"<{lo_pct}%"
    if frac <= hi:
        return f"{lo_pct}-{hi_pct}%"
    return f">{hi_pct}%"


def flood_free_summary(counts_list):
    """
    False-alarm summary over the FLOOD-FREE chips (non-empty domain, no truth flood pixel), reported
    for every method and variant:
      n_chips                : number of flood-free chips
      frac_chips_with_alarm  : fraction of them where the method predicts any flood pixel
      pooled_fpr             : sum(fp) / sum(fp + tn) over them
    """
    free = [c for c in counts_list if not is_excluded(c) and not has_truth_flood(c)]
    if not free:
        return {"n_chips": 0, "frac_chips_with_alarm": float("nan"), "pooled_fpr": float("nan")}
    pooled = pool(free)
    return {
        "n_chips": len(free),
        "frac_chips_with_alarm": sum(c["fp"] > 0 for c in free) / len(free),
        "pooled_fpr": _ratio(pooled["fp"], pooled["fp"] + pooled["tn"]),
    }
