"""
On-disk cache for SLIC segmentations.

A segmentation depends only on (chip, preprocessing, n_segments, compactness), NOT on k or on
which per-segment features are used, so one cached segmentation serves many k-means variants.
Stored as compressed uint16 (0 = invalid pixel, otherwise segment id + 1): segment maps compress
very well, which keeps thousands of cached configurations small.
"""

import hashlib
import os
import tempfile
from pathlib import Path

import numpy as np

CACHE_VERSION = "1"  # bump if the segmentation code changes in a way that alters its output


class SegmentationCache:
    def __init__(self, cache_dir):
        self.dir = Path(cache_dir)
        self.hits = 0
        self.misses = 0

    def _path(self, key):
        h = hashlib.sha1(key.encode()).hexdigest()
        return self.dir / h[:2] / f"{h}.npz"

    def get_or_compute(self, key, compute_fn):
        """Return the int32 segment map (-1 = invalid) for `key`, computing and storing it once."""
        path = self._path(key)
        if path.exists():
            self.hits += 1
            return np.load(path)["seg"].astype(np.int32) - 1
        self.misses += 1
        seg = compute_fn()
        if seg.max() >= 65535:
            raise ValueError("segment ids do not fit in uint16")
        path.parent.mkdir(parents=True, exist_ok=True)
        # write to a temp file then rename, so an interrupted run never leaves a half-written file
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".npz")
        os.close(fd)
        np.savez_compressed(tmp, seg=(seg + 1).astype(np.uint16))
        os.replace(tmp, path)
        return seg
