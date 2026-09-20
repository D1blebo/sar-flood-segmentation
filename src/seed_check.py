"""
Does M1's lowest-VV ("water") cluster depend on the k-means seed? (protocol Amendment 3, A3.3)

For each chip, preprocessing and k, cluster with several seeds and compare each seed's water mask
(the a-priori rule's pick) with the reference seed's. No labels are used anywhere in this check.
"""

import numpy as np

from src.cluster_rule import water_cluster_lowest_mean_vv
from src.config import clip_range, load_config
from src.io import read_chip
from src.methods import PixelKMeans
from src.preprocess import preprocess


def _water_mask(vv, vh, k, seed, n_init, max_iter):
    cmap = PixelKMeans(k, seed, n_init=n_init, max_iter=max_iter).cluster_map(vv, vh)
    water = water_cluster_lowest_mean_vv(cmap, vv)
    return np.zeros(vv.shape, bool) if water is None else cmap == water


def _iou(a, b):
    union = (a | b).sum()
    return 1.0 if union == 0 else float((a & b).sum() / union)


def seed_rows(vv, vh, ks, seeds, n_init, max_iter):
    """
    One row per (k, seed other than seeds[0]): the IoU between that seed's water mask and the
    reference seed's (seeds[0]). vv and vh must already be preprocessed.
    """
    rows = []
    for k in ks:
        reference = _water_mask(vv, vh, k, seeds[0], n_init, max_iter)
        for seed in seeds[1:]:
            mask = _water_mask(vv, vh, k, seed, n_init, max_iter)
            rows.append({"k": k, "seed": seed, "iou": _iou(reference, mask),
                         "reference_water_px": int(reference.sum())})
    return rows


def seed_rows_for_chip(chip_id):
    """Top-level (picklable) worker: all preprocessing settings for one chip, from the config."""
    cfg = load_config()
    sc = cfg["seed_sensitivity"]
    chip = read_chip(chip_id)
    rows = []
    for prep in sc["preprocessing"]:
        clip = clip_range(cfg, prep["clip"])
        vv, vh = preprocess(chip["vv"], chip["vh"], clip, prep["median"])
        for row in seed_rows(vv, vh, sc["k"], sc["seeds"], cfg["kmeans"]["n_init"],
                             cfg["kmeans"]["max_iter"]):
            rows.append({"chip": chip_id, "prep": f"clip={prep['clip']},median={prep['median']}",
                         **row})
    return rows
