"""Reading chips from disk. Nothing here modifies the data."""

from pathlib import Path

import numpy as np
import rasterio

from src.config import REPO_ROOT, load_config


def data_dir(cfg=None):
    cfg = cfg or load_config()
    return REPO_ROOT / cfg["paths"]["data_dir"]


def _read(path, band=None):
    with rasterio.open(path) as src:
        return src.read() if band is None else src.read(band)


def read_chip(chip_id, ddir=None):
    """
    Return a dict with the four arrays a method or metric may need:
      vv, vh : float32 dB, NaN where the radar has no measurement
      label  : int16, -1 unlabelled / 0 not water / 1 water
      jrc    : uint8, 1 = JRC permanent water
    Methods only ever receive vv and vh; label and jrc are used by the metrics.
    """
    ddir = Path(ddir) if ddir else data_dir()
    s1 = _read(ddir / "S1Hand" / f"{chip_id}_S1Hand.tif")  # (2, H, W): band 0 VV, band 1 VH
    return {
        "id": chip_id,
        "vv": s1[0],
        "vh": s1[1],
        "label": _read(ddir / "LabelHand" / f"{chip_id}_LabelHand.tif", 1),
        "jrc": _read(ddir / "JRCWaterHand" / f"{chip_id}_JRCWaterHand.tif", 1),
    }


def image_valid_mask(vv, vh):
    """True where both bands are finite. A pixel with no radar measurement cannot be classified."""
    return np.isfinite(vv) & np.isfinite(vh)
