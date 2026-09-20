"""M1: k-means on individual pixels, using the (VV, VH) values in dB."""

import numpy as np
from sklearn.cluster import KMeans

from src.methods.base import ClusteringMethod


class PixelKMeans(ClusteringMethod):
    def __init__(self, k, seed, n_init=3, max_iter=300, fit_subsample=None):
        """
        fit_subsample: if set, k-means is fitted on that many randomly chosen valid pixels
        (seeded), and then EVERY valid pixel is assigned to the nearest fitted centre. This only
        speeds up the fit; whether it changes the result is checked before it is adopted
        (results/speed_checks_output.txt). None = fit on all valid pixels.
        """
        self.k, self.seed, self.n_init, self.max_iter = k, seed, n_init, max_iter
        self.fit_subsample = fit_subsample
        self.name = f"M1_pixel_kmeans_k{k}" + (f"_sub{fit_subsample}" if fit_subsample else "")

    def cluster_map(self, vv, vh, cache_key=None):
        valid = np.isfinite(vv) & np.isfinite(vh)
        cmap = np.full(vv.shape, -1, dtype=np.int32)
        if not valid.any():
            return cmap
        # Fit on valid pixels ONLY. sklearn would raise on NaN, and NaN must not shape clusters.
        x = np.column_stack([vv[valid], vh[valid]]).astype(np.float64)
        fit_x = x
        if self.fit_subsample and len(x) > self.fit_subsample:
            rows = np.random.default_rng(self.seed).choice(len(x), self.fit_subsample, replace=False)
            fit_x = x[np.sort(rows)]
        km = KMeans(
            n_clusters=min(self.k, len(fit_x)),
            n_init=self.n_init,
            max_iter=self.max_iter,
            random_state=self.seed,
        ).fit(fit_x)
        cmap[valid] = km.labels_ if fit_x is x else km.predict(x)
        return cmap
