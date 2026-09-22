"""Bootstrap CIs checked on tiny, hand-computable data (protocol section 3, A2.2)."""

import numpy as np

from src.bootstrap import (bootstrap_chip_ci, bootstrap_macro_two_level, mean_per_chip_iou_stat,
                           pooled_iou_stat)


def c(tp, fp, fn, tn):
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "domain": tp + fp + fn + tn}


def test_pooled_iou_stat_hand_computed():
    counts = [c(2, 1, 0, 5), c(0, 0, 2, 6)]  # pooled: tp=2, fp=1, fn=2 -> 2/5
    assert pooled_iou_stat(counts) == 2 / 5


def test_pooled_iou_stat_empty_list_is_nan():
    assert np.isnan(pooled_iou_stat([]))


def test_mean_per_chip_iou_stat_excludes_flood_free_chips():
    counts = [c(1, 1, 0, 8), c(0, 0, 0, 10)]  # second chip has no truth flood (tp+fn=0): excluded
    assert mean_per_chip_iou_stat(counts) == 0.5


def test_mean_per_chip_iou_stat_all_flood_free_is_nan():
    assert np.isnan(mean_per_chip_iou_stat([c(0, 0, 0, 10), c(0, 1, 0, 9)]))


def test_bootstrap_chip_ci_point_estimate_matches_the_real_statistic():
    counts = [c(3, 1, 0, 6), c(2, 0, 1, 7), c(0, 2, 0, 8)]
    point, (lo, hi) = bootstrap_chip_ci(counts, pooled_iou_stat, n_resamples=200, seed=0)
    assert point == pooled_iou_stat(counts)
    assert 0.0 <= lo <= point <= hi <= 1.0 or lo <= point <= hi  # a CI bracket around the point


def test_bootstrap_chip_ci_is_deterministic():
    counts = [c(3, 1, 0, 6), c(2, 0, 1, 7), c(0, 2, 0, 8), c(1, 1, 1, 7)]
    r1 = bootstrap_chip_ci(counts, mean_per_chip_iou_stat, n_resamples=300, seed=7)
    r2 = bootstrap_chip_ci(counts, mean_per_chip_iou_stat, n_resamples=300, seed=7)
    assert r1 == r2


def test_bootstrap_chip_ci_empty_is_nan():
    point, (lo, hi) = bootstrap_chip_ci([], pooled_iou_stat, n_resamples=50, seed=0)
    assert np.isnan(point) and np.isnan(lo) and np.isnan(hi)


def test_bootstrap_macro_two_level_perfect_agreement_is_degenerate():
    # Every event has one chip with a perfect prediction: every resample gives IoU = 1 exactly.
    events = {"A": [c(5, 0, 0, 5)], "B": [c(3, 0, 0, 7)], "C": [c(1, 0, 0, 9)]}
    point, (lo, hi) = bootstrap_macro_two_level(events, pooled_iou_stat, n_resamples=200, seed=1)
    assert point == 1.0 and lo == 1.0 and hi == 1.0


def test_bootstrap_macro_two_level_point_is_unweighted_mean_over_events():
    # Event A pools to IoU 1.0 (from two chips), event B to IoU 0.0: unweighted mean of per-event
    # stats is 0.5, NOT the pooled-over-all-chips figure (which would be different).
    events = {"A": [c(2, 0, 0, 8), c(3, 0, 0, 7)], "B": [c(0, 5, 0, 5)]}
    point, _ = bootstrap_macro_two_level(events, pooled_iou_stat, n_resamples=10, seed=0)
    assert point == 0.5


def test_bootstrap_macro_two_level_drops_events_with_an_undefined_statistic():
    # Event B has no flood-truth chip, so mean_per_chip_iou_stat(B) is NaN and B is excluded from
    # the point estimate (unweighted mean over the events where the statistic is defined).
    events = {"A": [c(2, 0, 0, 8)], "B": [c(0, 0, 0, 10)]}
    point, _ = bootstrap_macro_two_level(events, mean_per_chip_iou_stat, n_resamples=10, seed=0)
    assert point == 1.0


def test_bootstrap_macro_two_level_is_deterministic():
    events = {"A": [c(2, 1, 0, 7), c(1, 0, 1, 8)], "B": [c(0, 3, 0, 7)], "C": [c(4, 0, 1, 5)]}
    r1 = bootstrap_macro_two_level(events, pooled_iou_stat, n_resamples=150, seed=3)
    r2 = bootstrap_macro_two_level(events, pooled_iou_stat, n_resamples=150, seed=3)
    assert r1 == r2
