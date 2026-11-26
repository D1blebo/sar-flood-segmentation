"""
Does a k-means method's lowest-VV ("water") cluster depend on the k-means seed?
(protocol Amendments 3, 4 and 5). No labels are used anywhere in these checks.

For each chip, preprocessing condition and setting, cluster with several seeds and compare each seed's
water mask (the a-priori rule's pick) with the reference seed's. Also records the size of the chosen
water cluster (share of valid pixels) and its mean VV, to see what kind of cluster is involved.
"""

import numpy as np

from src.cluster_rule import water_cluster_lowest_mean_vv
from src.config import REPO_ROOT, clip_range, load_config, prep_name
from src.io import read_chip
from src.methods import PixelKMeans, SlicKMeans
from src.preprocess import preprocess
from src.slic_cache import SegmentationCache


def _water_from_method(method, vv, vh, cache_key=None):
    """(water mask chosen by the a-priori rule, its mean VV in dB). Empty mask -> mean NaN."""
    cmap = method.cluster_map(vv, vh, cache_key)
    water = water_cluster_lowest_mean_vv(cmap, vv)
    if water is None:
        return np.zeros(vv.shape, bool), float("nan")
    mask = cmap == water
    return mask, float(vv[mask].mean())


def _iou(a, b):
    union = (a | b).sum()
    return 1.0 if union == 0 else float((a & b).sum() / union)


def compare_seeds(make_method, vv, vh, seeds, cache_key=None):
    """
    One row per seed other than seeds[0]: IoU between that seed's water mask and the reference seed's
    (seeds[0]), plus size (pixels) and mean VV of both water clusters. `make_method(seed)` builds the
    method. vv and vh must already be preprocessed.
    """
    valid_px = int(np.isfinite(vv).sum())
    reference, ref_mean = _water_from_method(make_method(seeds[0]), vv, vh, cache_key)
    rows = []
    for seed in seeds[1:]:
        mask, mean = _water_from_method(make_method(seed), vv, vh, cache_key)
        rows.append({"seed": seed, "iou": _iou(reference, mask),
                     "reference_water_px": int(reference.sum()), "seed_water_px": int(mask.sum()),
                     "valid_px": valid_px, "reference_mean_vv": ref_mean, "seed_mean_vv": mean})
    return rows


def seed_rows(vv, vh, ks, seeds, n_init, max_iter):
    """M1 rows (used by the first check and the follow-up): one per (k, non-reference seed)."""
    rows = []
    for k in ks:
        make = lambda seed, k=k: PixelKMeans(k, seed, n_init=n_init, max_iter=max_iter)
        rows += [{"k": k, **r} for r in compare_seeds(make, vv, vh, seeds)]
    return rows


def seed_rows_for_chip(chip_id, ks=None, n_init=None):
    """Top-level (picklable) worker for the first check / follow-up (config.seed_sensitivity)."""
    cfg = load_config()
    sc = cfg["seed_sensitivity"]
    ks = sc["k"] if ks is None else ks
    n_init = cfg["kmeans"]["n_init"] if n_init is None else n_init
    chip = read_chip(chip_id)
    rows = []
    for prep in sc["preprocessing"]:
        vv, vh = preprocess(chip["vv"], chip["vh"], clip_range(cfg, prep["clip"]), prep["median"])
        for row in seed_rows(vv, vh, ks, sc["seeds"], n_init, cfg["kmeans"]["max_iter"]):
            rows.append({"chip": chip_id, "prep": prep_name(prep["clip"], prep["median"]),
                         "n_init": n_init, **row})
    return rows


def full_check_rows_for_chip(chip_id, which):
    """
    Top-level (picklable) worker for the Amendment 5 full check (config.seed_sensitivity_full).
    which = 'm1': k in the M1 list, both n_init, four conditions.
    which = 'm2': k in the M2 list x feature sets, both n_init, four conditions, at the nominal SLIC
                  setting, reading/writing the on-disk segmentation cache (label-free, so safe to share).
    """
    cfg = load_config()
    seeds, max_iter = cfg["seed_sensitivity"]["seeds"], cfg["kmeans"]["max_iter"]
    full = cfg["seed_sensitivity_full"]
    chip = read_chip(chip_id)
    cache = SegmentationCache(REPO_ROOT / cfg["paths"]["cache_dir"] / "slic") if which == "m2" else None
    rows = []
    for cond in full["conditions"]:
        pname = prep_name(cond["clip"], cond["median"])
        vv, vh = preprocess(chip["vv"], chip["vh"], clip_range(cfg, cond["clip"]), cond["median"])
        for n_init in full["n_init_list"]:
            if which == "m1":
                variants = [(k, "") for k in full["m1"]["k"]]
            else:
                variants = [(k, f) for f in full["m2"]["features"] for k in full["m2"]["k"]]
            for k, feats in variants:
                if which == "m1":
                    make = lambda seed, k=k, n_init=n_init: PixelKMeans(
                        k, seed, n_init=n_init, max_iter=max_iter)
                    cache_key = None
                else:
                    m2 = full["m2"]
                    make = lambda seed, k=k, n_init=n_init, feats=feats: SlicKMeans(
                        k, m2["n_segments"], m2["compactness"], feats, seed, n_init=n_init,
                        max_iter=max_iter, slic_max_iter=cfg["slic"]["max_num_iter"], cache=cache)
                    cache_key = f"{chip_id}|{pname}"
                for r in compare_seeds(make, vv, vh, seeds, cache_key):
                    rows.append({"chip": chip_id, "method": which.upper(), "prep": pname,
                                 "n_init": n_init, "k": k, "features": feats, **r})
    return rows
