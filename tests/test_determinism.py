"""Same seed, same output. Also: the segmentation cache must not change any result."""

import numpy as np

from src.methods import OtsuThreshold, PixelKMeans, SlicKMeans
from src.preprocess import preprocess
from src.slic_cache import SegmentationCache


def _m2(cache=None, seed=0, n_segments=40):
    return SlicKMeans(k=3, n_segments=n_segments, compactness=0.2, features="vv_vh_std",
                      seed=seed, cache=cache)


def test_pixel_kmeans_is_deterministic(toy_chip):
    a = PixelKMeans(k=3, seed=7).cluster_map(toy_chip["vv"], toy_chip["vh"])
    b = PixelKMeans(k=3, seed=7).cluster_map(toy_chip["vv"], toy_chip["vh"])
    assert np.array_equal(a, b)


def test_slic_kmeans_is_deterministic(toy_chip):
    a = _m2(seed=7).cluster_map(toy_chip["vv"], toy_chip["vh"])
    b = _m2(seed=7).cluster_map(toy_chip["vv"], toy_chip["vh"])
    assert np.array_equal(a, b)


def test_otsu_is_deterministic(toy_chip):
    m = OtsuThreshold("vv")
    assert np.array_equal(m.predict(toy_chip["vv"], toy_chip["vh"]),
                          m.predict(toy_chip["vv"], toy_chip["vh"]))


def test_preprocess_is_deterministic(toy_chip):
    clip = {"vv": [-30.0, 5.0], "vh": [-35.0, -5.0]}
    a = preprocess(toy_chip["vv"], toy_chip["vh"], clip, 3)
    b = preprocess(toy_chip["vv"], toy_chip["vh"], clip, 3)
    assert np.array_equal(a[0], b[0], equal_nan=True) and np.array_equal(a[1], b[1], equal_nan=True)


def test_cache_returns_the_same_result_as_no_cache(toy_chip, tmp_path):
    vv, vh = toy_chip["vv"], toy_chip["vh"]
    plain = _m2().cluster_map(vv, vh)
    cache = SegmentationCache(tmp_path)
    first = _m2(cache).cluster_map(vv, vh, cache_key="Toy_1|clip=none|med=0")   # miss: computes
    second = _m2(cache).cluster_map(vv, vh, cache_key="Toy_1|clip=none|med=0")  # hit: reads disk
    assert (cache.misses, cache.hits) == (1, 1)
    assert np.array_equal(plain, first) and np.array_equal(plain, second)


def test_cache_key_separates_segmentation_parameters(toy_chip, tmp_path):
    vv, vh = toy_chip["vv"], toy_chip["vh"]
    cache = SegmentationCache(tmp_path)
    _m2(cache, n_segments=40).cluster_map(vv, vh, cache_key="Toy_1|clip=none|med=0")
    _m2(cache, n_segments=80).cluster_map(vv, vh, cache_key="Toy_1|clip=none|med=0")
    assert (cache.misses, cache.hits) == (2, 0)  # different n_segments -> different entry


def test_one_segmentation_serves_several_k_and_feature_settings(toy_chip, tmp_path):
    vv, vh = toy_chip["vv"], toy_chip["vh"]
    cache = SegmentationCache(tmp_path)
    for k, feats in ((2, "vv"), (3, "vv_vh"), (4, "vv_vh_diff")):
        SlicKMeans(k=k, n_segments=40, compactness=0.2, features=feats, seed=0,
                   cache=cache).cluster_map(vv, vh, cache_key="Toy_1|clip=none|med=0")
    assert (cache.misses, cache.hits) == (1, 2)  # segmented once, reused twice
