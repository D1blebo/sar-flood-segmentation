"""
Tests for scripts/04b_POSTHOC_paired_event_bootstrap.py (the POST-HOC paired, event-level bootstrap).
Toy counts only, so the expected answers can be worked out by hand.
"""

import importlib.util

import numpy as np

from src.config import REPO_ROOT

_spec = importlib.util.spec_from_file_location(
    "paired04b", REPO_ROOT / "scripts" / "04b_POSTHOC_paired_event_bootstrap.py")
pb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pb)


def test_pooled_iou_sums_counts_before_dividing():
    # two events: [tp, fp, fn] = [1, 1, 0] and [3, 0, 3] -> tp 4, fp 1, fn 3 -> 4 / 8
    counts = np.array([[1, 1, 0], [3, 0, 3]], dtype=float)
    assert pb.pooled_iou(counts) == 0.5


def test_pooled_iou_is_nan_when_nothing_to_score():
    assert np.isnan(pb.pooled_iou(np.zeros((2, 3))))


def test_same_seed_gives_same_draws_and_other_seed_differs():
    a, b = pb.event_draws(11, 50, 42), pb.event_draws(11, 50, 42)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, pb.event_draws(11, 50, 43))
    assert a.shape == (50, 11) and a.min() >= 0 and a.max() <= 10


def test_identical_methods_have_zero_paired_difference():
    # Paired means both methods see the SAME resampled events, so a method minus itself is exactly 0 every time.
    counts = np.array([[5, 1, 2], [0, 3, 4], [7, 0, 1]], dtype=float)
    draws = pb.event_draws(3, 200, 42)
    diff = pb.bootstrap_values(counts, draws) - pb.bootstrap_values(counts, draws)
    assert np.all(diff == 0)
    assert pb.percentile_interval(diff) == (0.0, 0.0)


def test_uniformly_better_method_has_a_positive_interval():
    # Method A has more true positives than B in every event, so A minus B is positive in every resample.
    b = np.array([[2, 2, 6], [1, 1, 8], [3, 0, 7]], dtype=float)
    a = b + np.array([2, 0, -2])          # move 2 pixels from FN to TP in every event
    draws = pb.event_draws(3, 500, 42)
    lo, hi = pb.percentile_interval(pb.bootstrap_values(a, draws) - pb.bootstrap_values(b, draws))
    assert 0 < lo <= hi
