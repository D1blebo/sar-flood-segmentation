"""Baselines B1 (fixed threshold on VV) and B2 (Otsu threshold on VV or VH)."""

import numpy as np
from skimage.filters import threshold_otsu

from src.methods.base import FloodMethod


class FixedThresholdVV(FloodMethod):
    """B1. Water if VV < threshold_db. The threshold is tuned on the tuning chips, not here."""

    def __init__(self, threshold_db):
        self.threshold_db = float(threshold_db)
        self.name = f"B1_fixed_vv_{self.threshold_db:g}dB"

    def predict(self, vv, vh, cache_key=None):
        valid = np.isfinite(vv) & np.isfinite(vh)
        with np.errstate(invalid="ignore"):  # comparisons with NaN are False, which is what we want
            return valid & (vv < self.threshold_db)


class OtsuThreshold(FloodMethod):
    """
    B2. Otsu's method picks, per chip, the threshold that best splits a two-peak histogram of the
    valid pixels. Water is the darker side. Known weakness: when water covers only a small share of
    the chip the histogram has no second peak and the threshold drifts.
    """

    def __init__(self, band="vv"):
        if band not in ("vv", "vh"):
            raise ValueError("band must be 'vv' or 'vh'")
        self.band = band
        self.name = f"B2_otsu_{band}"

    def threshold(self, vv, vh):
        """Otsu threshold (dB) from valid pixels only, or None if the chip has no contrast."""
        valid = np.isfinite(vv) & np.isfinite(vh)
        x = (vv if self.band == "vv" else vh)[valid]
        if x.size < 2 or x.min() == x.max():
            return None
        return float(threshold_otsu(x))

    def predict(self, vv, vh, cache_key=None):
        thr = self.threshold(vv, vh)
        if thr is None:
            return np.zeros(vv.shape, dtype=bool)
        band = vv if self.band == "vv" else vh
        valid = np.isfinite(vv) & np.isfinite(vh)
        with np.errstate(invalid="ignore"):
            return valid & (band < thr)
