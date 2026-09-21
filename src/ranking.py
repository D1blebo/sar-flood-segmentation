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
from src.stage1 import ceiling_key, mv_path, unit_path

FLOOD, ALL = MODES.index("flood_only"), MODES.index("all_water")
PLAIN_FAMILIES = ("b2_vv", "b2_vh", "m1", "m2")
PRIMARY, SENSITIVITY = "pooled_all", "mean_flood"   # amended criterion (A7.2) and the declared one (A7.3)
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


def _key(score, crit=SENSITIVITY):
    """
    Sort key, larger is better; NaN sorts last.
    PRIMARY   : pooled flood-only IoU over all tuning chips (ties then fall to config order).
    SENSITIVITY: mean per-chip IoU over chips with flood, then pooled IoU (the declared criterion).
    """
    mean, pooled = score[0], score[1]
    m = -np.inf if np.isnan(mean) else mean
    q = -np.inf if np.isnan(pooled) else pooled
    if crit == PRIMARY:
        return (q,)
    if crit == SENSITIVITY:
        return (m, q)
    raise ValueError(f"unknown criterion {crit!r}")


def rank_options(counts, family, mask, guarded, prep_order, ceilings=(), crit=SENSITIVITY):
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
            if best is None or _key(score, crit) > _key(best[0], crit):
                best = (score, cfg, ce)
        ranked.append({"prep": prep, "mean": best[0][0], "pooled": best[0][1], "n_flood_chips": best[0][2],
                       "cfg": best[1], "ceiling": best[2], "_order": order})
    ranked.sort(key=lambda r: (tuple(-x for x in _key((r["mean"], r["pooled"]), crit)), r["_order"]))
    for r in ranked:
        r.pop("_order")
    return ranked


_MEDIAN = re.compile(r"median=(\d+)")


def median_of(prep):
    """The median window of a preprocessing option name such as 'clip=none,median=7'."""
    return int(_MEDIAN.search(prep).group(1))


def extra_prep_names(clips, medians):
    """Names of the extension options: every clip at each extra median window."""
    return [f"clip={c},median={m}" for m in medians for c in clips]


def available_extra_medians(unit_dir, chips, clips, candidates=(9, 11)):
    """The extra median windows whose units exist for ALL chips and all clips (consecutive from the first)."""
    have = []
    for m in candidates:
        if all(unit_path(unit_dir, chip, name).exists() for chip in chips for name in extra_prep_names(clips, [m])):
            have.append(m)
        else:
            break
    return have


def rank_with_extensions(counts, family, mask, guarded, base_preps, clips, ceilings, crit,
                         available, base_max_median=7, step=2, max_extensions=2, ceiling_ext=None):
    """
    Rank one (variant, tuning set) and apply the grid-edge rule (A2.5, A7.4, A8.3), repeating until nothing triggers:
    * median window: if the winner's median is the current upper edge, add the next median (edge + step) for all clips,
      at most `max_extensions` times; only medians in `available` (units computed) can be added, otherwise `pending`
      reports the median that is needed.
    * guard ceiling (guarded variants, only if `ceiling_ext` is given = {'available': [floats], 'step': dB, 'max': n}):
      if the winner's ceiling is the lowest or highest in the current list, add one step beyond it, at most `max` steps in
      total; ceilings not in `available` are reported in `pending_ceiling`.
    Returns (ranked, info): info = {'extensions': [medians], 'pending': median or None}, plus 'ceiling_extensions' and
    'pending_ceiling' when ceiling_ext is given.
    """
    added_m, added_c, pending_m, pending_c = [], [], None, None
    while True:
        preps = list(base_preps) + extra_prep_names(clips, added_m)
        current = list(ceilings) + [ceiling_key(c) for c in added_c]
        ranked = rank_options(counts, family, mask, guarded, preps, current, crit)
        winner, changed, pending_m, pending_c = ranked[0], False, None, None
        edge = base_max_median + step * len(added_m)
        if median_of(winner["prep"]) == edge and len(added_m) < max_extensions:
            if edge + step in available:
                added_m.append(edge + step)
                changed = True
            else:
                pending_m = edge + step
        if guarded and ceiling_ext and len(added_c) < ceiling_ext["max"]:
            values = [float(k) for k in current]
            lo, hi, w = min(values), max(values), float(winner["ceiling"])
            nxt = lo - ceiling_ext["step"] if w == lo else hi + ceiling_ext["step"] if w == hi else None
            if nxt is not None:
                if nxt in ceiling_ext["available"]:
                    added_c.append(nxt)
                    changed = True
                else:
                    pending_c = nxt
        if not changed:
            break
    info = {"extensions": added_m, "pending": pending_m}
    if ceiling_ext:
        info.update({"ceiling_extensions": added_c, "pending_ceiling": pending_c})
    return ranked, info


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
    mean_rank = {p: float(np.mean([r.index(p) + 1 if p in r else len(r) + 1 for r in rankings.values()]))
                 for p in prep_order}
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


# ---- counts at any ceiling, derived from the stored mean VV (protocol A8.3) ----------------------------------------------

def derive_ceiling_counts(plain, mv, ceiling):
    """
    Counts of the guarded variant at `ceiling`, from the plain counts (n, 2, 5) and the predicted region's mean VV per chip
    (n,), NaN where nothing was predicted. The guard keeps the prediction iff mean VV < ceiling; on abstention TP = FP = 0,
    FN = TP + FN, TN = domain - FN. Exactly what apply_abstention_ceiling would give.
    """
    out = plain.copy()
    a = np.asarray(mv, dtype=float) >= ceiling          # NaN compares False: an empty prediction is left as it is
    truth = plain[:, :, 0] + plain[:, :, 2]
    out[a, :, 0] = 0
    out[a, :, 1] = 0
    out[a, :, 2] = truth[a]
    out[a, :, 3] = plain[a, :, 4] - truth[a]
    return out


def load_mv(unit_dir, chips, preps):
    """{(family, prep): float array (n_chips,)} of the predicted region's mean VV, NaN where empty. Raises if a file is missing."""
    mv, missing = {}, []
    for ci, chip in enumerate(chips):
        for prep in preps:
            path = mv_path(unit_dir, chip, prep)
            if not path.exists():
                missing.append(f"{chip}|{prep}")
                continue
            unit = json.loads(path.read_text())
            for fam in PLAIN_FAMILIES:
                a = mv.setdefault((fam, prep), np.full(len(chips), np.nan))
                a[ci] = np.nan if unit[fam] is None else unit[fam]
    if missing:
        raise FileNotFoundError(f"{len(missing)} mean-VV files missing, e.g. {missing[:3]}")
    return mv


def add_derived_ceilings(counts, mv, ceilings):
    """Add counts[(family, prep, 'nominal', key)] for every ceiling in `ceilings` (floats) that is not already there."""
    for (fam, prep), a in mv.items():
        plain = counts[(fam, prep, "nominal", "plain")]
        for c in ceilings:
            counts.setdefault((fam, prep, "nominal", ceiling_key(c)), derive_ceiling_counts(plain, a, c))


def verify_derived_ceilings(counts, mv, ceilings):
    """(checked, mismatched): derived counts against the stored ones for ceilings that were computed directly."""
    checked = bad = 0
    for (fam, prep), a in mv.items():
        plain = counts[(fam, prep, "nominal", "plain")]
        for c in ceilings:
            stored = counts[(fam, prep, "nominal", ceiling_key(c))]
            checked += 1
            bad += not np.array_equal(stored, derive_ceiling_counts(plain, a, c))
    return checked, bad
