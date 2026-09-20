"""
Preprocessing shared by EVERY method (including the threshold baselines).

Order: keep the NaN mask -> clip (dB) -> median filter -> method.
NaN is never silently turned into a number that a method could mistake for data: it stays NaN
in the output, and the methods/metrics mask it.
"""

import numpy as np
from scipy.ndimage import median_filter


def clip_db(vv, vh, clip):
    """
    Clip each band to a fixed dB range. `clip` is {'vv': [lo, hi], 'vh': [lo, hi]} or None.
    np.clip leaves NaN as NaN. Outliers matter because k-means is outlier-sensitive and SLIC
    rescales the image to [0, 1] using its min and max.
    """
    if clip is None:
        return vv, vh
    return np.clip(vv, *clip["vv"]), np.clip(vh, *clip["vh"])


def median_filter_nan(band, window):
    """
    Median filter that ignores NaN. NaN pixels are first filled with the chip's median so the
    filter never sees NaN, then restored to NaN afterwards, so NaN pixels stay NaN and valid
    pixels near a NaN edge are only mildly pulled toward the chip median. window 0 = no filter.
    The median depends only on ranks, so filtering dB or linear power gives the same result.
    """
    if not window:
        return band
    valid = np.isfinite(band)
    if not valid.any():
        return band.copy()
    filled = np.where(valid, band, np.median(band[valid]))
    out = median_filter(filled, size=window, mode="reflect")
    out[~valid] = np.nan
    return out


def preprocess(vv, vh, clip=None, median_window=0):
    """Return preprocessed (vv, vh) with one shared NaN mask (NaN in either band -> NaN in both)."""
    invalid = ~(np.isfinite(vv) & np.isfinite(vh))
    vv, vh = vv.astype(np.float32, copy=True), vh.astype(np.float32, copy=True)
    vv[invalid] = np.nan
    vh[invalid] = np.nan
    vv, vh = clip_db(vv, vh, clip)
    vv, vh = median_filter_nan(vv, median_window), median_filter_nan(vh, median_window)
    return vv, vh
