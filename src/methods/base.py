"""
The one interface every method implements, so methods can be swapped and compared.

    method.predict(vv, vh, cache_key=None) -> bool array, same shape as vv

Contract:
  * vv, vh are already preprocessed dB arrays; NaN means "no measurement".
  * the output is False on every NaN pixel (NaN is never predicted as flood).
  * methods never see the label or the JRC mask.
  * cache_key identifies (chip + preprocessing) so expensive intermediate results (SLIC
    segmentations) can be cached; methods that do not cache simply ignore it.
"""

import numpy as np

from src.cluster_rule import water_cluster_lowest_mean_vv


class FloodMethod:
    name = "base"

    def predict(self, vv, vh, cache_key=None):
        raise NotImplementedError


class ClusteringMethod(FloodMethod):
    """
    A method that first labels every valid pixel with a cluster id, then picks the water cluster
    with the a-priori rule (lowest mean VV). Subclasses only implement `cluster_map`.
    Keeping the cluster map separate lets the oracle diagnostic reuse it without re-clustering.
    """

    def cluster_map(self, vv, vh, cache_key=None):
        """int32 array, cluster id >= 0 on valid pixels, -1 on NaN pixels."""
        raise NotImplementedError

    def predict(self, vv, vh, cache_key=None):
        cmap = self.cluster_map(vv, vh, cache_key)
        water = water_cluster_lowest_mean_vv(cmap, vv)
        if water is None:  # nothing valid in this chip
            return np.zeros(vv.shape, dtype=bool)
        return cmap == water  # invalid pixels have id -1, so they are never water
