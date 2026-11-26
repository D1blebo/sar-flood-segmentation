"""Load configs/config.yaml and expand the few compact entries in it."""

from pathlib import Path

import numpy as np
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_config(path=None):
    path = Path(path) if path else REPO_ROOT / "configs" / "config.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def b1_threshold_grid(cfg):
    """Candidate VV thresholds (dB) for the fixed-threshold baseline."""
    s = cfg["search_space"]["b1_fixed_threshold"]["threshold_db"]
    # stop is inclusive; the half-step avoids float round-off dropping the last value
    return [float(x) for x in np.arange(s["start"], s["stop"] + s["step"] / 2, s["step"])]


def clip_range(cfg, name):
    """Return {'vv': [lo, hi], 'vh': [lo, hi]} or None for the option called `name`."""
    return cfg["preprocess"]["clip_options"][name]


def b1_thresholds_for_clip(cfg, clip):
    """
    B1 thresholds worth trying under a clip. Clipping puts a floor `lo` under VV, so VV < t is
    empty for every t <= lo; those thresholds predict nothing and are skipped (Amendment 2).
    """
    return b1_thresholds_above_floor(b1_threshold_grid(cfg), clip)


def b1_thresholds_above_floor(grid, clip):
    """The thresholds in `grid` that can predict anything once VV is clipped to clip['vv'] (None = no clip)."""
    if clip is None:
        return list(grid)
    return [t for t in grid if t > clip["vv"][0]]


def prep_name(clip_name, median_window):
    """Canonical name of a preprocessing option, also used as part of the SLIC cache key."""
    return f"clip={clip_name},median={median_window}"
