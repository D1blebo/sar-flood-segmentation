"""
Stage 1 aggregation: rank preprocessing options per tuning set, and build the stage-2 union.
Implements protocol A3.1 (plain vs guarded selection), A5.3 (capped union) and section 6 (criterion).

A "tuning set" is a boolean mask over the eligible chips: the tuning chips only. Every number produced
here is an aggregate over the tuning chips of one tuning set, never a metric of a held-out chip.
"""

import json
import re
from collections import Counter
from pathlib import Path

import numpy as np

from src.metrics import MODES
from src.stage1 import ceiling_key, unit_path

FLOOD, ALL = MODES.index("flood_only"), MODES.index("all_water")
PLAIN_FAMILIES = ("b2_vv", "b2_vh", "m1", "m2")
VARIANTS = ("b1", "b2_vv", "b2_vh", "b2g_vv", "b2g_vh", "m1", "m1g", "m2", "m2g")


def load_units(unit_dir, chips, preps):
    """
    counts[(family, prep, cfg, ceiling)] = int array (n_chips, 2 modes, 5) [tp, fp, fn, tn, domain].
    family is 'b1' (cfg = threshold string, ceiling 'plain') or one of PLAIN_FAMILIES (cfg 'nominal').
    Also returns {component: [seconds per unit]}. Raises if any unit is missing.
    """
    counts, seconds, missing = {}, {}, []
    for ci, chip in enumerate(chips):
        for prep in preps:
            path = unit_path(unit_dir, chip, prep)
            if not path.exists():
                missing.append(f"{chip}|{prep}")
                continue
            unit = json.loads(path.read_text())
            for comp, s in unit["seconds"].items():
                seconds.setdefault(comp, []).append(s)
            for thr, enc in unit["b1"].items():
                counts.setdefault(("b1", prep, thr, "plain"), np.zeros((len(chips), 2, 5), np.int64))[ci] = enc
            for fam in PLAIN_FAMILIES:
                for ceil, enc in unit[fam].items():
                    counts.setdefault((fam, prep, "nominal", ceil), np.zeros((len(chips), 2, 5), np.int64))[ci] = enc
    if missing:
        raise FileNotFoundError(f"{len(missing)} units missing, e.g. {missing[:3]}")
    return counts, seconds


def check_consistency(counts):
    """Truth-flood pixels and domain size of a chip must not depend on the method or preprocessing."""
    ref = None
    for key, a in counts.items():
        sig = (a[:, :, 0] + a[:, :, 2], a[:, :, 4])
        if ref is None:
            ref = sig
        elif not (np.array_equal(sig[0], ref[0]) and np.array_equal(sig[1], ref[1])):
            raise AssertionError(f"truth/domain counts differ for candidate {key}")


def criterion(counts, mask, mode=FLOOD):
    """
    (mean per-chip IoU, pooled IoU, chips with flood) over the tuning chips in `mask`.
    Mean per-chip IoU averages only chips with at least one truth pixel (protocol section 6); pooled IoU
    sums TP, FP and FN over the mask. NaN if undefined.
    """
    c = counts[:, mode, :]
    tp, fp, fn = c[:, 0], c[:, 1], c[:, 2]
    has = mask & ((tp + fn) > 0)
    mean = float(np.mean(tp[has] / (tp[has] + fp[has] + fn[has]))) if has.any() else float("nan")
    m = mask & (c[:, 4] > 0)
    denom = tp[m].sum() + fp[m].sum() + fn[m].sum()
    pooled = float(tp[m].sum() / denom) if denom > 0 else float("nan")
    return mean, pooled, int(has.sum())


def _key(score):
    """Sort key, larger is better; NaN sorts last."""
    mean, pooled = score[0], score[1]
    return (-np.inf if np.isnan(mean) else mean, -np.inf if np.isnan(pooled) else pooled)


def rank_options(counts, family, mask, guarded, prep_order, ceilings=()):
    """
    Rank the preprocessing options for one variant on one tuning set (best first).
    * B1 ('b1'): each option's best threshold.
    * plain B2/M1/M2: the UNGUARDED counts only (protocol A3.1).
    * guarded: each option's best (configuration, ceiling) pair, over `ceilings` (keys) only.
    Ties: pooled IoU, then earlier in config order (thresholds ascending, ceilings in list order).
    """
    ranked = []
    for order, prep in enumerate(prep_order):
        if family == "b1":
            cands = [(cfg, "plain") for (f, p, cfg, ce) in counts if f == "b1" and p == prep]
        elif guarded:
            cands = [("nominal", ce) for ce in ceilings]
        else:
            cands = [("nominal", "plain")]
        best = None
        for cfg, ce in cands:
            score = criterion(counts[(family, prep, cfg, ce)], mask)
            if best is None or _key(score) > _key(best[0]):
                best = (score, cfg, ce)
        ranked.append({"prep": prep, "mean": best[0][0], "pooled": best[0][1], "n_flood_chips": best[0][2],
                       "cfg": best[1], "ceiling": best[2], "_order": order})
    ranked.sort(key=lambda r: (tuple(-x for x in _key((r["mean"], r["pooled"]))), r["_order"]))
    for r in ranked:
        r.pop("_order")
    return ranked


def tuning_sets(events, splits):
    """{name: boolean mask over eligible chips}: 11 leave-one-event-out folds plus the official validation split."""
    events, splits = np.asarray(events), np.asarray(splits)
    sets = {f"loeo:{ev}": events != ev for ev in sorted(set(events))}
    sets["official_valid"] = splits == "valid"
    return sets


def stage2_union(rankings, prep_order, top=2, cap=6):
    """
    Protocol A5.3. rankings: {tuning set: [prep names, best first]} (the full stage-1 ranking).
    Take each set's top `top`; rank options by how many sets chose them (descending), ties by mean rank over
    ALL sets' full rankings (ascending, 1 = best), then config order; keep the first `cap`. A set whose own
    top options are outside the union falls back to its own best-ranked options that are inside it.
    """
    chosen = Counter(p for r in rankings.values() for p in r[:top])
    mean_rank = {p: float(np.mean([r.index(p) + 1 for r in rankings.values()])) for p in prep_order}
    order = sorted(chosen, key=lambda p: (-chosen[p], mean_rank[p], prep_order.index(p)))
    union = order[:cap]
    assigned = {s: [p for p in r if p in union][:top] for s, r in rankings.items()}
    return {"union": union, "chosen_by": dict(chosen), "mean_rank": mean_rank,
            "distinct_top2": len(chosen), "assigned": assigned}


def measured_speedup(log_path):
    """The parallel speedup the compute run printed, or None."""
    text = Path(log_path).read_text() if Path(log_path).exists() else ""
    m = re.search(r"parallel speedup ([0-9.]+)x", text)
    return float(m.group(1)) if m else None


def project_stage2_cost(unions, seconds, n_chips, speedup, m1_stage2_fraction=0.30, new_m2_configs=15):
    """
    Projected stage-2 time from the measured per-unit times. unions: {'m1','m1g','m2','m2g': [options]}.
    Options shared by plain and guarded variants are computed once. M2: 15 new (n_segments, compactness)
    configurations per option (nominal is done), each about a stage-1 M2 unit. M1: k = 2 at n_init 3 is
    ASSUMED to cost 30% of a stage-1 M1 unit (k=3, n_init 10; earlier timing: n_init 3 was about a third).
    """
    m2_opts = set(unions["m2"]) | set(unions["m2g"])
    m1_opts = set(unions["m1"]) | set(unions["m1g"])
    m2_s, m1_s = float(np.mean(seconds["m2"])), float(np.mean(seconds["m1"]))
    serial = n_chips * (len(m2_opts) * new_m2_configs * m2_s + len(m1_opts) * m1_s * m1_stage2_fraction)
    return {"m2_options": len(m2_opts), "m1_options": len(m1_opts), "m2_seconds_per_config_chip": m2_s,
            "m1_seconds_per_unit": m1_s, "serial_h": serial / 3600.0,
            "wall_h": serial / 3600.0 / speedup if speedup else None, "speedup_used": speedup}
