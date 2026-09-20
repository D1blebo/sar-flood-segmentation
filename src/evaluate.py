"""
Glue: preprocess a chip, run one method, and return per-chip confusion counts for both metrics.

The returned counts are the unit that Stage 3 will cache per (method, configuration, chip); the
leave-one-event-out folds and the official split then only sum different subsets of them.

Which VV does the cluster rule (and the abstention ceiling) see? The VV AFTER clip and median
filter, the same array the method clusters. The oracle uses the same cluster map.
"""

import numpy as np

from src.cluster_rule import (apply_abstention_ceiling, oracle_cluster,
                              water_cluster_lowest_mean_vv)
from src.io import image_valid_mask, read_chip
from src.methods.base import ClusteringMethod
from src.metrics import MODES, confusion_counts, evaluation_domain_and_truth
from src.preprocess import preprocess


def evaluate_chip(method, chip, clip=None, median_window=0, cache_key=None, with_oracle=False,
                  ceilings_db=()):
    """
    Returns {'flood_only': counts, 'all_water': counts} for the plain method, and in addition:
      * with_oracle=True (clustering methods only): '<mode>_oracle' counts. DIAGNOSTIC ONLY, uses
        the ground truth.
      * ceilings_db=[c1, c2, ...]: out['guarded'][c] = {'flood_only': counts, 'all_water': counts}
        for the abstention-guard variant at each ceiling, from the SAME prediction (so all variants
        cost one clustering).
    `cache_key` should identify the chip and the preprocessing, e.g. 'Ghana_5079|clip=none|med=0'.
    """
    vv, vh = preprocess(chip["vv"], chip["vh"], clip, median_window)
    image_valid = image_valid_mask(chip["vv"], chip["vh"])  # same NaN mask as after preprocessing

    cmap = None
    if isinstance(method, ClusteringMethod):
        cmap = method.cluster_map(vv, vh, cache_key)
        water = water_cluster_lowest_mean_vv(cmap, vv)  # the a-priori rule, on the preprocessed VV
        pred = np.zeros(vv.shape, bool) if water is None else (cmap == water)
    else:
        pred = method.predict(vv, vh, cache_key)

    out = {}
    for mode in MODES:
        domain, truth = evaluation_domain_and_truth(image_valid, chip["label"], chip["jrc"], mode)
        out[mode] = confusion_counts(pred, truth, domain)
        if with_oracle and cmap is not None:
            best, _ = oracle_cluster(cmap, truth, domain)
            oracle_pred = np.zeros(vv.shape, bool) if best is None else (cmap == best)
            out[f"{mode}_oracle"] = confusion_counts(oracle_pred, truth, domain)
        for ceiling in ceilings_db:
            guarded = apply_abstention_ceiling(pred, vv, ceiling)
            out.setdefault("guarded", {}).setdefault(ceiling, {})[mode] = confusion_counts(
                guarded, truth, domain)
    return out


def evaluate_chip_id(chip_id, method, clip=None, median_window=0, prep_name="", ceilings_db=(),
                     with_oracle=False):
    """
    Read one chip and evaluate it. Top-level and picklable, so it can run in worker processes.
    The SLIC cache key is built here from the chip id and the preprocessing name.
    """
    chip = read_chip(chip_id)
    return chip_id, evaluate_chip(method, chip, clip, median_window,
                                  cache_key=f"{chip_id}|{prep_name}", with_oracle=with_oracle,
                                  ceilings_db=ceilings_db)
