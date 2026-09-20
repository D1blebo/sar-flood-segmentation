"""
M2: SLIC superpixels, then k-means on per-superpixel features (the Hack4Dev Tutorial 3 idea).

SLIC groups neighbouring pixels of similar value into small patches ("superpixels"). We compute a
few features per patch, cluster the PATCHES with k-means, and give every pixel its patch's cluster.

NaN handling (SLIC cannot take NaN): fill NaN with the chip's valid median, run SLIC, then mark the
NaN pixels invalid again (-1). Patch features use valid pixels only, and k-means never sees a patch
that has no valid pixel. We do not use SLIC's `mask=` argument because its seeding step took 0.7 to
8.4 s per chip (200 to 2000 segments) against about 0.35 s without it (measured on one chip).
"""

import numpy as np
from skimage import __version__ as SKIMAGE_VERSION
from skimage.segmentation import slic
from sklearn.cluster import KMeans

from src.methods.base import ClusteringMethod
from src.slic_cache import CACHE_VERSION

FEATURE_SETS = ("vv", "vv_vh", "vv_vh_std", "vv_vh_diff")


def slic_segments(vv, vh, n_segments, compactness, max_num_iter=10):
    """int32 segment map for one chip: ids >= 0 on valid pixels, -1 on NaN pixels."""
    valid = np.isfinite(vv) & np.isfinite(vh)
    seg = np.full(vv.shape, -1, dtype=np.int32)
    if not valid.any():
        return seg
    img = np.stack([vv, vh], axis=-1).astype(np.float64)
    for b in range(2):
        img[~valid, b] = np.median(img[valid, b])  # neutral fill, so the image has no NaN
    raw = slic(
        img,
        n_segments=n_segments,
        compactness=compactness,
        max_num_iter=max_num_iter,
        convert2lab=False,  # Lab conversion is only meaningful for 3-channel RGB
        enforce_connectivity=True,
        start_label=0,
        channel_axis=-1,
    )
    seg[valid] = raw[valid]  # re-mask: NaN pixels go back to -1
    return seg


def segment_features(vv, vh, seg, feature_set):
    """
    One row of features per segment that has at least one valid pixel, plus `inverse`, which maps
    each valid pixel (in raster order) to its row. Features are in dB and are NOT rescaled.
      vv         : mean VV
      vv_vh      : mean VV, mean VH
      vv_vh_std  : mean VV, mean VH, std VV, std VH
      vv_vh_diff : mean VV, mean VH, mean(VV - VH)   (equals mean VV - mean VH exactly)
    """
    if feature_set not in FEATURE_SETS:
        raise ValueError(f"feature_set must be one of {FEATURE_SETS}")
    valid = seg >= 0
    _, inverse = np.unique(seg[valid], return_inverse=True)
    counts = np.bincount(inverse).astype(np.float64)

    def mean_std(band):
        x = band[valid].astype(np.float64)
        mean = np.bincount(inverse, weights=x) / counts
        var = np.bincount(inverse, weights=x * x) / counts - mean * mean
        return mean, np.sqrt(np.maximum(var, 0.0))  # max() guards tiny negative round-off

    m_vv, s_vv = mean_std(vv)
    m_vh, s_vh = mean_std(vh)
    columns = {
        "vv": [m_vv],
        "vv_vh": [m_vv, m_vh],
        "vv_vh_std": [m_vv, m_vh, s_vv, s_vh],
        "vv_vh_diff": [m_vv, m_vh, m_vv - m_vh],
    }[feature_set]
    return np.column_stack(columns), inverse


class SlicKMeans(ClusteringMethod):
    def __init__(self, k, n_segments, compactness, features, seed,
                 n_init=3, max_iter=300, slic_max_iter=10, cache=None):
        self.k, self.n_segments, self.compactness = k, n_segments, compactness
        self.features, self.seed = features, seed
        self.n_init, self.max_iter, self.slic_max_iter = n_init, max_iter, slic_max_iter
        self.cache = cache
        self.name = f"M2_slic_kmeans_k{k}_n{n_segments}_c{compactness:g}_{features}"

    def segments(self, vv, vh, cache_key=None):
        def compute():
            return slic_segments(vv, vh, self.n_segments, self.compactness, self.slic_max_iter)

        if self.cache is None or cache_key is None:
            return compute()
        key = (f"{cache_key}|slic|n={self.n_segments}|c={self.compactness:g}"
               f"|it={self.slic_max_iter}|skimage={SKIMAGE_VERSION}|v={CACHE_VERSION}")
        return self.cache.get_or_compute(key, compute)

    def cluster_map(self, vv, vh, cache_key=None):
        cmap = np.full(vv.shape, -1, dtype=np.int32)
        seg = self.segments(vv, vh, cache_key)
        if (seg >= 0).sum() == 0:
            return cmap
        feats, inverse = segment_features(vv, vh, seg, self.features)
        # k-means on the patches (one row per patch, unweighted), fitted on valid patches only
        km = KMeans(
            n_clusters=min(self.k, len(feats)),
            n_init=self.n_init,
            max_iter=self.max_iter,
            random_state=self.seed,
        ).fit(feats)
        cmap[seg >= 0] = km.labels_[inverse]  # every pixel takes its patch's cluster
        return cmap
