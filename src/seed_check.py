"""
Does M1's lowest-VV ("water") cluster depend on the k-means seed? (protocol Amendments 3 and 4)

For each chip, preprocessing and k, cluster with several seeds and compare each seed's water mask
(the a-priori rule's pick) with the reference seed's. No labels are used anywhere in this check.
Also records how big the chosen water cluster is (as a share of valid pixels) and its mean VV, to test
whether the instability comes from tiny outlier clusters.
"""

import numpy as np

from src.cluster_rule import water_cluster_lowest_mean_vv
from src.config import clip_range, load_config
from src.io import read_chip
from src.methods import PixelKMeans
from src.preprocess import preprocess


def _water(vv, vh, k, seed, n_init, max_iter):
    """(water mask chosen by the a-priori rule, its mean VV in dB). Empty mask -> mean NaN."""
    cmap = PixelKMeans(k, seed, n_init=n_init, max_iter=max_iter).cluster_map(vv, vh)
    water = water_cluster_lowest_mean_vv(cmap, vv)
    if water is None:
        return np.zeros(vv.shape, bool), float("nan")
    mask = cmap == water
    return mask, float(vv[mask].mean())


def _iou(a, b):
    union = (a | b).sum()
    return 1.0 if union == 0 else float((a & b).sum() / union)


def seed_rows(vv, vh, ks, seeds, n_init, max_iter):
    """
    One row per (k, seed other than seeds[0]): the IoU between that seed's water mask and the
    reference seed's (seeds[0]), plus the size (pixels) and mean VV of both water clusters.
    vv and vh must already be preprocessed. valid_px is the number of non-NaN pixels.
    """
    valid_px = int(np.isfinite(vv).sum())
    rows = []
    for k in ks:
        reference, ref_mean = _water(vv, vh, k, seeds[0], n_init, max_iter)
        for seed in seeds[1:]:
            mask, mean = _water(vv, vh, k, seed, n_init, max_iter)
            rows.append({"k": k, "seed": seed, "iou": _iou(reference, mask),
                         "reference_water_px": int(reference.sum()), "seed_water_px": int(mask.sum()),
                         "valid_px": valid_px, "reference_mean_vv": ref_mean, "seed_mean_vv": mean})
    return rows


def seed_rows_for_chip(chip_id, ks=None, n_init=None):
    """
    Top-level (picklable) worker: all preprocessing settings for one chip.
    ks and n_init default to config.seed_sensitivity and config.kmeans.
    """
    cfg = load_config()
    sc = cfg["seed_sensitivity"]
    ks = sc["k"] if ks is None else ks
    n_init = cfg["kmeans"]["n_init"] if n_init is None else n_init
    chip = read_chip(chip_id)
    rows = []
    for prep in sc["preprocessing"]:
        clip = clip_range(cfg, prep["clip"])
        vv, vh = preprocess(chip["vv"], chip["vh"], clip, prep["median"])
        for row in seed_rows(vv, vh, ks, sc["seeds"], n_init, cfg["kmeans"]["max_iter"]):
            rows.append({"chip": chip_id, "prep": f"clip={prep['clip']},median={prep['median']}",
                         "n_init": n_init, **row})
    return rows
