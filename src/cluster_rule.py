"""
Turning k-means clusters into a water mask.

Cluster ids from k-means are arbitrary, so we need a rule. The rule is fixed a priori (before any
score was seen): the cluster whose pixels have the LOWEST MEAN VV is water, because calm water is
dark to radar.

`oracle_cluster` is a DIAGNOSTIC that looks at the ground truth. It must never be used for a
reported headline result. The gap between the rule and the oracle tells us how much error comes
from the rule and how much from the clustering itself.
"""

import numpy as np


def water_cluster_lowest_mean_vv(cluster_map, vv):
    """
    cluster_map: int array, -1 where invalid. Returns the id of the cluster with the lowest mean
    VV over its valid pixels, or None if there are none. Ties go to the lowest id (argmin returns
    the first minimum), so the result never depends on array ordering tricks.
    """
    ok = (cluster_map >= 0) & np.isfinite(vv)
    if not ok.any():
        return None
    ids = cluster_map[ok]
    n = int(ids.max()) + 1
    sums = np.bincount(ids, weights=vv[ok].astype(np.float64), minlength=n)
    counts = np.bincount(ids, minlength=n)
    means = np.full(n, np.inf)  # clusters with no pixels can never win
    present = counts > 0
    means[present] = sums[present] / counts[present]
    return int(np.argmin(means))


def oracle_cluster(cluster_map, truth, domain):
    """
    DIAGNOSTIC ONLY (uses ground truth). The single cluster whose pixels best match the truth,
    by IoU inside `domain`. Returns (cluster_id, iou), or (None, nan) if the truth has no water.
    """
    truth = truth & domain
    if not truth.any():
        return None, float("nan")
    best_id, best_iou = None, -1.0
    for cid in np.unique(cluster_map[cluster_map >= 0]):
        pred = (cluster_map == cid) & domain
        union = (pred | truth).sum()
        score = (pred & truth).sum() / union if union else 0.0
        if score > best_iou:  # strict '>' keeps the lowest id on ties
            best_id, best_iou = int(cid), float(score)
    return best_id, best_iou


def apply_abstention_ceiling(pred, vv, ceiling_db):
    """
    Abstention guard (candidate variants M1g / M2g / B2g, Amendment 2).

    A predicted water region counts as water only if its mean VV is BELOW `ceiling_db`; otherwise
    the chip gets no predicted flood at all. This targets chips where the darkest cluster is not
    actually dark, for example a flood-free chip that k-means splits into "less bright" and
    "more bright" land. `vv` is the same preprocessed VV the method received (after clip and
    median), and for a cluster method `pred` is exactly the chosen cluster's pixels, so this is the
    cluster's mean VV. ceiling_db=None means no guard (the plain a-priori rule).
    """
    if ceiling_db is None or not pred.any():
        return pred
    if float(vv[pred].mean()) < ceiling_db:
        return pred
    return np.zeros_like(pred, dtype=bool)
