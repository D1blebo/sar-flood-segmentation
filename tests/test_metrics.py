"""Metrics checked against values worked out by hand on tiny arrays."""

import math

import numpy as np
import pytest

from src.io import image_valid_mask
from src.metrics import (confusion_counts, evaluation_domain_and_truth, f1, false_positive_rate,
                         flood_fraction, has_truth_flood, iou, is_excluded, pool, precision,
                         recall, stratum)


def test_scores_hand_computed():
    truth = np.array([1, 1, 0, 0, 1, 0], bool)
    pred = np.array([1, 0, 1, 0, 1, 0], bool)
    c = confusion_counts(pred, truth, np.ones(6, bool))
    # TP: pixels 0 and 4. FP: pixel 2. FN: pixel 1. TN: pixels 3 and 5.
    assert c == {"tp": 2, "fp": 1, "fn": 1, "tn": 2, "domain": 6}
    assert iou(c) == pytest.approx(2 / 4)
    assert precision(c) == pytest.approx(2 / 3)
    assert recall(c) == pytest.approx(2 / 3)
    assert f1(c) == pytest.approx(4 / 6)


def test_pixels_outside_the_domain_are_ignored_not_counted_as_not_flood():
    truth = np.array([1, 1, 0, 0, 1, 0], bool)
    pred = np.array([1, 0, 1, 0, 1, 0], bool)
    domain = np.array([1, 1, 0, 1, 1, 1], bool)  # the false positive (pixel 2) is ignored
    c = confusion_counts(pred, truth, domain)
    assert c == {"tp": 2, "fp": 0, "fn": 1, "tn": 2, "domain": 5}
    assert iou(c) == pytest.approx(2 / 3)


def test_undefined_metrics_are_nan_not_zero():
    zeros = np.zeros(10, bool)
    c = confusion_counts(zeros, zeros, np.ones(10, bool))  # no flood anywhere, none predicted
    for metric in (iou, precision, recall, f1):
        assert math.isnan(metric(c))
    assert not has_truth_flood(c)


def test_flood_free_chip_reported_as_false_positive_rate():
    truth = np.zeros(10, bool)
    pred = np.zeros(10, bool)
    pred[:2] = True
    c = confusion_counts(pred, truth, np.ones(10, bool))
    assert (c["fp"], c["tn"]) == (2, 8)
    assert false_positive_rate(c) == pytest.approx(0.2)
    assert not has_truth_flood(c)  # so per-chip IoU is not averaged for this chip


def test_chip_with_empty_domain_is_excluded():
    c = confusion_counts(np.ones(4, bool), np.ones(4, bool), np.zeros(4, bool))
    assert is_excluded(c)


def test_pool_sums_counts():
    a = {"tp": 1, "fp": 2, "fn": 3, "tn": 4, "domain": 10}
    b = {"tp": 10, "fp": 20, "fn": 30, "tn": 40, "domain": 100}
    assert pool([a, b]) == {"tp": 11, "fp": 22, "fn": 33, "tn": 44, "domain": 110}


def test_strata_boundaries():
    def chip(flood_px, domain=100):
        return {"tp": flood_px, "fp": 0, "fn": 0, "tn": domain - flood_px, "domain": domain}
    assert stratum(chip(0)) == "none"
    assert stratum(chip(2)) == "<5%"
    assert stratum(chip(5)) == "5-30%"    # 5% falls in the middle bin
    assert stratum(chip(30)) == "5-30%"   # so does 30%
    assert stratum(chip(31)) == ">30%"
    assert flood_fraction(chip(31)) == pytest.approx(0.31)


def test_domains_and_truth_for_both_modes_worked_out_by_hand():
    vv = np.array([[0, 0, np.nan], [0, 0, 0]], float)
    vh = vv.copy()
    label = np.array([[1, 1, 1], [-1, 1, 0]])
    jrc = np.array([[0, 1, 0], [0, 0, 0]])
    valid = image_valid_mask(vv, vh)

    # flood_only: pixel (0,1) is JRC, (0,2) is NaN, (1,0) is unlabelled -> all outside the domain
    domain, truth = evaluation_domain_and_truth(valid, label, jrc, "flood_only")
    assert domain.tolist() == [[True, False, False], [False, True, True]]
    assert truth.tolist() == [[True, False, False], [False, True, False]]

    # all_water: JRC pixel (0,1) is back in, NaN and unlabelled still out
    domain, truth = evaluation_domain_and_truth(valid, label, jrc, "all_water")
    assert domain.tolist() == [[True, True, False], [False, True, True]]
    assert truth.tolist() == [[True, True, False], [False, True, False]]


def test_prediction_on_jrc_permanent_water_is_not_a_false_positive_in_flood_only_mode():
    vv = np.zeros((1, 3))
    label = np.array([[0, 0, 0]])
    jrc = np.array([[1, 0, 0]])
    pred = np.array([[True, False, False]])  # predicts flood only on the permanent-water pixel
    valid = image_valid_mask(vv, vv)
    d, t = evaluation_domain_and_truth(valid, label, jrc, "flood_only")
    assert confusion_counts(pred, t, d)["fp"] == 0
    d, t = evaluation_domain_and_truth(valid, label, jrc, "all_water")
    assert confusion_counts(pred, t, d)["fp"] == 1


def test_unknown_mode_raises():
    with pytest.raises(ValueError):
        evaluation_domain_and_truth(np.ones((1, 1), bool), np.zeros((1, 1)), np.zeros((1, 1)), "x")
