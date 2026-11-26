"""
Bootstrap confidence intervals for held-out scoring (protocol section 3 and A2.2).

Two kinds, both percentile 95% CIs recomputing the statistic on every resample (never the bootstrap
mean as the point estimate -- the point estimate is always the statistic on the real, unresampled data):

  * chip-level  : resample chips with replacement from one flat list of per-chip counts. Used for the
                  headline pooled IoU and for per-event statistics ("for per-event results the
                  resampling is within the event", section 3).
  * event-level : two-level (A2.2) -- resample the 11 events with replacement, then resample chips with
                  replacement within each sampled event, and average the per-event statistic over the
                  resampled events. Used only for the 11-event macro-average.
"""

import numpy as np

from src.metrics import has_truth_flood, iou, pool


def pooled_iou_stat(counts_list):
    return iou(pool(counts_list)) if counts_list else float("nan")


def mean_per_chip_iou_stat(counts_list):
    vals = [iou(c) for c in counts_list if has_truth_flood(c)]
    return float(np.mean(vals)) if vals else float("nan")


def _percentile_ci(values, confidence):
    values = np.asarray([v for v in values if not np.isnan(v)], dtype=float)
    if values.size == 0:
        return float("nan"), float("nan")
    alpha = (1.0 - confidence) / 2.0
    lo, hi = np.percentile(values, [100 * alpha, 100 * (1 - alpha)])
    return float(lo), float(hi)


def bootstrap_chip_ci(counts_list, stat_fn, n_resamples=1000, seed=42, confidence=0.95):
    """Point estimate on the real data, plus a percentile CI from resampling chips with replacement."""
    point = stat_fn(counts_list)
    n = len(counts_list)
    if n == 0:
        return point, (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(n_resamples):
        idx = rng.integers(0, n, size=n)
        values.append(stat_fn([counts_list[i] for i in idx]))
    return point, _percentile_ci(values, confidence)


def bootstrap_macro_two_level(events_counts, per_event_stat_fn, n_resamples=1000, seed=42, confidence=0.95):
    """
    events_counts: {event_name: [chip_counts, ...]}. Point estimate: the unweighted mean of
    `per_event_stat_fn` over the real events (events with an undefined statistic are dropped, e.g. an
    event with no flood-truth chips for the mean-per-chip statistic). Each resample draws the events
    with replacement, then the chips of each drawn event with replacement, and averages the per-event
    statistic over the drawn events.
    """
    names = sorted(events_counts)
    real = [per_event_stat_fn(events_counts[e]) for e in names]
    real = [s for s in real if not np.isnan(s)]
    point = float(np.mean(real)) if real else float("nan")
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(n_resamples):
        drawn_events = [names[i] for i in rng.integers(0, len(names), size=len(names))]
        stats = []
        for e in drawn_events:
            chips = events_counts[e]
            if not chips:
                continue
            idx = rng.integers(0, len(chips), size=len(chips))
            stats.append(per_event_stat_fn([chips[i] for i in idx]))
        stats = [s for s in stats if not np.isnan(s)]
        values.append(float(np.mean(stats)) if stats else float("nan"))
    return point, _percentile_ci(values, confidence)
