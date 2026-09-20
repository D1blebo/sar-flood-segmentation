"""Shared interface, shapes, hand-computed SLIC features, and end-to-end counts on the toy chip."""

import numpy as np
import pytest

from src.evaluate import evaluate_chip
from src.methods import (FEATURE_SETS, ClusteringMethod, FixedThresholdVV, OtsuThreshold,
                         PixelKMeans, SlicKMeans)
from src.methods.slic_kmeans import segment_features, slic_segments
from src.metrics import iou


def make_methods():
    return [
        FixedThresholdVV(-17.0),
        OtsuThreshold("vv"),
        OtsuThreshold("vh"),
        PixelKMeans(k=2, seed=0),
        SlicKMeans(k=2, n_segments=60, compactness=0.2, features="vv_vh", seed=0),
    ]


@pytest.mark.parametrize("method", make_methods(), ids=lambda m: m.name)
def test_common_interface(method, toy_chip):
    pred = method.predict(toy_chip["vv"], toy_chip["vh"])
    assert pred.dtype == bool and pred.shape == (64, 64)


def test_clustering_methods_expose_cluster_map(toy_chip):
    for m in make_methods():
        if isinstance(m, ClusteringMethod):
            cmap = m.cluster_map(toy_chip["vv"], toy_chip["vh"])
            assert cmap.dtype == np.int32 and cmap.shape == (64, 64)
            assert (cmap[np.isnan(toy_chip["vv"])] == -1).all()
            assert (cmap[np.isfinite(toy_chip["vv"])] >= 0).all()


def test_slic_segment_map_shape_range_and_count(toy_chip):
    seg = slic_segments(toy_chip["vv"], toy_chip["vh"], n_segments=60, compactness=0.2)
    assert seg.shape == (64, 64) and seg.dtype == np.int32
    n = len(np.unique(seg[seg >= 0]))
    assert 20 <= n <= 180  # SLIC returns roughly n_segments patches, not exactly


def test_segment_features_hand_computed():
    vv = np.array([[1.0, 3.0], [5.0, 9.0]], np.float32)
    vh = np.array([[0.0, 0.0], [2.0, 4.0]], np.float32)
    seg = np.array([[0, 0], [1, 1]], np.int32)
    # segment 0: VV {1,3} mean 2 std 1; VH {0,0} mean 0 std 0
    # segment 1: VV {5,9} mean 7 std 2; VH {2,4} mean 3 std 1
    f, inverse = segment_features(vv, vh, seg, "vv")
    assert f.tolist() == [[2.0], [7.0]] and inverse.tolist() == [0, 0, 1, 1]
    f, _ = segment_features(vv, vh, seg, "vv_vh")
    assert f.tolist() == [[2.0, 0.0], [7.0, 3.0]]
    f, _ = segment_features(vv, vh, seg, "vv_vh_std")
    assert np.allclose(f, [[2, 0, 1, 0], [7, 3, 2, 1]])
    f, _ = segment_features(vv, vh, seg, "vv_vh_diff")
    assert np.allclose(f, [[2, 0, 2], [7, 3, 4]])  # third column: mean(VV - VH)


def test_segment_features_skip_segments_with_no_valid_pixel():
    vv = np.array([[1.0, 3.0], [5.0, 9.0]], np.float32)
    seg = np.array([[0, 0], [-1, -1]], np.int32)  # segment 1 lies entirely in NaN territory
    f, inverse = segment_features(vv, vv, seg, "vv")
    assert f.shape == (1, 1) and inverse.tolist() == [0, 0]


def test_unknown_feature_set_raises():
    with pytest.raises(ValueError):
        segment_features(np.zeros((2, 2)), np.zeros((2, 2)), np.zeros((2, 2), np.int32), "nope")


def test_feature_sets_listed_in_config_exist():
    from src.config import load_config
    assert set(load_config()["search_space"]["m2_slic_kmeans"]["features"]) == set(FEATURE_SETS)


def test_evaluate_chip_counts_worked_out_by_hand(toy_chip):
    # B1 at -17 dB separates the toy water (~ -24) from background (~ -10) perfectly.
    out = evaluate_chip(FixedThresholdVV(-17.0), toy_chip)
    assert out["flood_only"] == {"tp": 375, "fp": 0, "fn": 0, "tn": 3304, "domain": 3679}
    assert out["all_water"] == {"tp": 500, "fp": 0, "fn": 0, "tn": 3304, "domain": 3804}


@pytest.mark.parametrize("method", [OtsuThreshold("vv"), OtsuThreshold("vh"), PixelKMeans(k=2, seed=0)],
                         ids=lambda m: m.name)
def test_simple_methods_are_perfect_on_the_toy_chip(method, toy_chip):
    out = evaluate_chip(method, toy_chip)
    assert iou(out["flood_only"]) == 1.0 and iou(out["all_water"]) == 1.0


def test_slic_kmeans_is_nearly_perfect_on_the_toy_chip(toy_chip):
    m = SlicKMeans(k=2, n_segments=60, compactness=0.2, features="vv_vh", seed=0)
    out = evaluate_chip(m, toy_chip)
    assert iou(out["all_water"]) > 0.9  # patches straddling the boundary cost a little


def test_evaluate_chip_rule_prediction_matches_method_predict(toy_chip):
    from src.preprocess import preprocess
    m = PixelKMeans(k=2, seed=0)
    vv, vh = preprocess(toy_chip["vv"], toy_chip["vh"])
    out = evaluate_chip(m, toy_chip)
    # rebuild the flood_only counts by hand from method.predict and compare
    from src.io import image_valid_mask
    from src.metrics import confusion_counts, evaluation_domain_and_truth
    d, t = evaluation_domain_and_truth(image_valid_mask(toy_chip["vv"], toy_chip["vh"]),
                                       toy_chip["label"], toy_chip["jrc"], "flood_only")
    assert out["flood_only"] == confusion_counts(m.predict(vv, vh), t, d)


def test_oracle_entries_only_for_clustering_methods_when_requested(toy_chip):
    with_oracle = evaluate_chip(PixelKMeans(k=2, seed=0), toy_chip, with_oracle=True)
    assert {"flood_only_oracle", "all_water_oracle"} <= set(with_oracle)
    assert "flood_only_oracle" not in evaluate_chip(PixelKMeans(k=2, seed=0), toy_chip)
    assert "flood_only_oracle" not in evaluate_chip(FixedThresholdVV(-17.0), toy_chip, with_oracle=True)


def test_methods_never_receive_label_or_jrc():
    import inspect
    for cls in (FixedThresholdVV, OtsuThreshold, PixelKMeans, SlicKMeans):
        params = inspect.signature(cls.predict).parameters
        assert set(params) <= {"self", "vv", "vh", "cache_key"}
