"""NaN must never shape a cluster, a threshold or a prediction."""

import numpy as np
import pytest

from src.methods import FixedThresholdVV, OtsuThreshold, PixelKMeans, SlicKMeans
from src.methods.slic_kmeans import segment_features, slic_segments
from src.preprocess import clip_db, median_filter_nan, preprocess


def all_methods():
    return [
        FixedThresholdVV(-17.0),
        OtsuThreshold("vv"),
        OtsuThreshold("vh"),
        PixelKMeans(k=2, seed=0),
        SlicKMeans(k=2, n_segments=40, compactness=0.2, features="vv_vh", seed=0),
    ]


@pytest.mark.parametrize("method", all_methods(), ids=lambda m: m.name)
def test_prediction_is_false_on_nan_pixels(method, toy_chip):
    pred = method.predict(toy_chip["vv"], toy_chip["vh"])
    nan = np.isnan(toy_chip["vv"])
    assert nan.sum() == 36
    assert not pred[nan].any()
    assert pred.dtype == bool and pred.shape == toy_chip["vv"].shape


@pytest.mark.parametrize("method", all_methods(), ids=lambda m: m.name)
def test_all_nan_chip_is_safe_and_predicts_nothing(method):
    vv = np.full((16, 16), np.nan, np.float32)
    assert not method.predict(vv, vv.copy()).any()


def test_pixel_kmeans_is_fitted_on_valid_pixels_only(toy_chip):
    vv, vh = toy_chip["vv"], toy_chip["vh"]
    valid = np.isfinite(vv)
    # the same valid pixels, in the same order, laid out as a 1-row image with no NaN at all
    flat_pred = PixelKMeans(k=2, seed=0).predict(vv[valid][None, :], vh[valid][None, :])[0]
    full_pred = PixelKMeans(k=2, seed=0).predict(vv, vh)
    assert np.array_equal(full_pred[valid], flat_pred)  # NaN pixels had no influence on the fit


def test_otsu_threshold_ignores_nan(toy_chip):
    vv, vh = toy_chip["vv"], toy_chip["vh"]
    valid = np.isfinite(vv)
    m = OtsuThreshold("vv")
    assert m.threshold(vv, vh) == m.threshold(vv[valid][None, :], vh[valid][None, :])


def test_slic_segments_masked_where_nan_and_features_are_finite(toy_chip):
    vv, vh = toy_chip["vv"], toy_chip["vh"]
    seg = slic_segments(vv, vh, n_segments=40, compactness=0.2)
    nan = np.isnan(vv)
    assert (seg[nan] == -1).all() and (seg[~nan] >= 0).all()
    for feature_set in ("vv", "vv_vh", "vv_vh_std", "vv_vh_diff"):
        feats, inverse = segment_features(vv, vh, seg, feature_set)
        assert np.isfinite(feats).all()          # no NaN reached k-means
        assert len(inverse) == (~nan).sum()      # one entry per valid pixel


def test_median_filter_keeps_nan_and_does_not_leak_it():
    band = np.arange(25, dtype=np.float32).reshape(5, 5)
    band[2, 2] = np.nan
    out = median_filter_nan(band, 3)
    assert np.isnan(out[2, 2])
    assert np.isfinite(np.delete(out.ravel(), 12)).all()  # NaN did not spread to neighbours


def test_median_window_zero_is_identity():
    band = np.random.default_rng(0).normal(size=(6, 6)).astype(np.float32)
    assert np.array_equal(median_filter_nan(band, 0), band)


def test_clip_preserves_nan_and_limits_range():
    vv = np.array([-50.0, -20.0, np.nan, 10.0], np.float32)
    vh = np.array([-50.0, -20.0, -10.0, 10.0], np.float32)
    cvv, cvh = clip_db(vv, vh, {"vv": [-30.0, 5.0], "vh": [-35.0, -5.0]})
    assert cvv[[0, 1, 3]].tolist() == [-30.0, -20.0, 5.0] and np.isnan(cvv[2])
    assert cvh.tolist() == [-35.0, -20.0, -10.0, -5.0]
    same_vv, same_vh = clip_db(vv, vh, None)
    assert same_vv is vv and same_vh is vh


def test_nan_in_one_band_invalidates_both_bands():
    vv = np.array([[1.0, 2.0]], np.float32)
    vh = np.array([[np.nan, 3.0]], np.float32)
    pvv, pvh = preprocess(vv, vh)
    assert np.isnan(pvv[0, 0]) and np.isnan(pvh[0, 0])
    assert pvv[0, 1] == 2.0 and pvh[0, 1] == 3.0
