import numpy as np
import pytest


@pytest.fixture
def toy_chip():
    """
    64 x 64 synthetic chip where every answer can be worked out by hand.
      water block   : rows 10-29, cols 10-34  (20 x 25 = 500 px), dark: VV ~ -24 dB
      background    : VV ~ -10 dB
      permanent JRC : rows 10-14 of the water block (5 x 25 = 125 px)
      unlabelled    : cols 60-63 (label -1, 64 x 4 = 256 px)
      NaN block     : rows 50-55, cols 0-5 (36 px), in dry background (label 0)
    Expected pixel counts:
      flood_only: domain 4096-256-36-125 = 3679, truth 500-125 = 375
      all_water : domain 4096-256-36     = 3804, truth 500
    """
    rng = np.random.default_rng(0)
    h = w = 64
    vv = rng.normal(-10, 0.7, (h, w))
    vh = rng.normal(-17, 0.7, (h, w))
    water = np.zeros((h, w), bool)
    water[10:30, 10:35] = True
    vv[water] = rng.normal(-24, 0.7, water.sum())
    vh[water] = rng.normal(-31, 0.7, water.sum())

    label = np.zeros((h, w), np.int16)
    label[water] = 1
    label[:, 60:] = -1
    jrc = np.zeros((h, w), np.uint8)
    jrc[10:15, 10:35] = 1

    vv[50:56, 0:6] = np.nan
    vh[50:56, 0:6] = np.nan
    return {"id": "Toy_1", "vv": vv.astype(np.float32), "vh": vh.astype(np.float32),
            "label": label, "jrc": jrc}


@pytest.fixture
def three_blob_image():
    """
    Three flat regions with well separated VV: -25 dB (left), -12 dB (middle), -5 dB (right).
    Returns (vv, vh, blob_index) where blob_index is 0, 1, 2 for left, middle, right.
    """
    blob = np.zeros((30, 30), int)
    blob[:, 10:20] = 1
    blob[:, 20:] = 2
    vv = np.choose(blob, [-25.0, -12.0, -5.0]).astype(np.float32)
    vh = (vv - 7.0).astype(np.float32)
    rng = np.random.default_rng(1)
    vv = vv + rng.normal(0, 0.1, vv.shape).astype(np.float32)
    vh = vh + rng.normal(0, 0.1, vh.shape).astype(np.float32)
    return vv, vh, blob
