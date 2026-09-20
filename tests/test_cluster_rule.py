"""The a-priori cluster-to-water rule (lowest mean VV) and the oracle diagnostic."""

import numpy as np

from src.cluster_rule import oracle_cluster, water_cluster_lowest_mean_vv
from src.methods import PixelKMeans


def test_rule_picks_the_darkest_cluster_whatever_the_ids_are(three_blob_image):
    vv, _, blob = three_blob_image  # blob 0 is the dark (-25 dB) region
    for perm in ([0, 1, 2], [2, 0, 1], [1, 2, 0]):  # k-means ids are arbitrary
        cmap = np.array(perm)[blob].astype(np.int32)
        water = water_cluster_lowest_mean_vv(cmap, vv)
        assert water == perm[0]


def test_rule_ties_go_to_the_lowest_id():
    vv = np.array([[-20.0, -20.0]])
    cmap = np.array([[1, 0]], dtype=np.int32)
    assert water_cluster_lowest_mean_vv(cmap, vv) == 0


def test_rule_ignores_invalid_pixels_and_nan():
    vv = np.array([[-99.0, -5.0, np.nan, -8.0]])
    cmap = np.array([[-1, 0, 1, 1]], dtype=np.int32)  # -99 is invalid, NaN is invalid
    # cluster 0 mean -5, cluster 1 mean -8 (its NaN pixel is ignored) -> cluster 1
    assert water_cluster_lowest_mean_vv(cmap, vv) == 1


def test_rule_returns_none_when_nothing_is_valid():
    assert water_cluster_lowest_mean_vv(np.full((2, 2), -1, np.int32), np.zeros((2, 2))) is None


def test_rule_on_real_kmeans_marks_only_the_darkest_blob(three_blob_image):
    vv, vh, blob = three_blob_image
    pred = PixelKMeans(k=3, seed=0).predict(vv, vh)
    assert np.array_equal(pred, blob == 0)


def test_oracle_can_disagree_with_the_rule(three_blob_image):
    vv, vh, blob = three_blob_image
    cmap = np.array([0, 1, 2])[blob].astype(np.int32)
    domain = np.ones(vv.shape, bool)
    truth = blob == 1  # suppose the true water is the middle blob
    rule = water_cluster_lowest_mean_vv(cmap, vv)
    oracle_id, oracle_iou = oracle_cluster(cmap, truth, domain)
    assert rule == 0 and oracle_id == 1 and oracle_iou == 1.0


def test_oracle_undefined_without_truth(three_blob_image):
    vv, _, blob = three_blob_image
    cmap = blob.astype(np.int32)
    assert oracle_cluster(cmap, np.zeros(vv.shape, bool), np.ones(vv.shape, bool))[0] is None
