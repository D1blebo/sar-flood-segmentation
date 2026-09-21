"""
Final selection after Stage 1 (protocol A9): M1 (k = 3 vs k = 2), M2 Stage 2 (options x (n_segments, compactness) with the
grid-edge rule) and M2 Stage 3 ((features, k) combinations), each jointly with the guard ceiling for the guarded variants.

Every function scores a candidate on a tuning set's own chips only (a boolean mask). Nothing here reads a held-out chip's metric.
"""

import json
from pathlib import Path

import numpy as np

from src.ranking import PRIMARY, _key, criterion, derive_ceiling_counts
from src.stage1 import ceiling_key
from src.stage2 import config_key, stage2_path


class Store:
    """
    plain[(family, prep, cfg)] = counts (n_chips, 2, 5); mv[...] = predicted region's mean VV (n_chips,), NaN where empty.
    counts(key, ceiling) returns the plain counts or, for a ceiling key such as '-15', counts derived exactly from the mean VV.
    """

    def __init__(self):
        self.plain, self.mv, self._derived = {}, {}, {}

    def add(self, key, plain, mv):
        self.plain[key], self.mv[key] = plain, mv

    def has(self, key):
        return key in self.plain

    def counts(self, key, ceiling):
        if ceiling == "plain":
            return self.plain[key]
        ck = (key, ceiling)
        if ck not in self._derived:
            self._derived[ck] = derive_ceiling_counts(self.plain[key], self.mv[key], float(ceiling))
        return self._derived[ck]


def _load_kind_files(root, kind, chips, preps):
    """Read stage-2 style unit files (configs -> plain counts + mean VV) into {(prep, cfg): (plain, mv)}."""
    out = {}
    for prep in preps:
        for ci, chip in enumerate(chips):
            path = stage2_path(root, kind, chip, prep)
            if not path.exists():
                raise FileNotFoundError(f"{path} missing")
            for cfg, e in json.loads(path.read_text())["configs"].items():
                plain, mv = out.setdefault((prep, cfg), (np.zeros((len(chips), 2, 5), np.int64), np.full(len(chips), np.nan)))
                plain[ci] = e["plain"]
                mv[ci] = np.nan if e["mv"] is None else e["mv"]
    return out


def extension_kinds(stage2_dir):
    """Names of the M2 extension rounds present on disk, in order ('m2x1', 'm2x2', ...)."""
    return sorted(p.name for p in Path(stage2_dir).glob("m2x*") if p.is_dir())


def build_store(stage1_counts, stage1_mv, stage2_dir, chips, m1_options, m2_options, ext_prep_lists=None):
    """
    Assemble the store: stage-1 M1 (k = 3) and nominal M2 (500 / 0.05) for every option present in stage 1, stage-2 M1 (k = 2) and
    M2 configurations, and the M2 extension rounds. ext_prep_lists: {kind: [preps]} for the extension rounds that exist.
    """
    store = Store()
    for (fam, prep, cfg, ce), plain in stage1_counts.items():
        if ce == "plain" and fam == "m1":
            store.add(("m1", prep, "k3"), plain, stage1_mv[(fam, prep)])
        if ce == "plain" and fam == "m2":
            store.add(("m2", prep, config_key(500, 0.05)), plain, stage1_mv[(fam, prep)])
    for (prep, cfg), (plain, mv) in _load_kind_files(stage2_dir, "m1", chips, m1_options).items():
        store.add(("m1", prep, cfg), plain, mv)
    for (prep, cfg), (plain, mv) in _load_kind_files(stage2_dir, "m2", chips, m2_options).items():
        store.add(("m2", prep, cfg), plain, mv)
    for kind, preps in (ext_prep_lists or {}).items():
        for (prep, cfg), (plain, mv) in _load_kind_files(stage2_dir, kind, chips, preps).items():
            store.add(("m2", prep, cfg), plain, mv)
    return store


def rank_pairs(store, candidates, mask, guarded, ceilings, crit, ceiling_ext=None):
    """
    Rank candidate keys (in config order) on one tuning set (best first). Plain: unguarded counts. Guarded: each candidate's best ceiling
    from `ceilings` (keys, in list order), jointly with the configuration; if `ceiling_ext` = {'step': dB, 'max': n} is given, the winner's
    ceiling at either edge of the current list adds one step beyond it (at most n steps), and the ranking is repeated. Ties: strictly
    better wins, so the earlier candidate (or earlier ceiling) keeps a tie.
    Returns (ranked, info): ranked = [{'key', 'mean', 'pooled', 'n_flood_chips', 'ceiling'}, ...], info = {'ceiling_extensions': [dB]}.
    """
    added = []
    while True:
        current = list(ceilings) + [ceiling_key(c) for c in added]
        rows = []
        for order, key in enumerate(candidates):
            options = current if guarded else ["plain"]
            best = None
            for ce in options:
                score = criterion(store.counts(key, ce), mask)
                if best is None or _key(score, crit) > _key(best[0], crit):
                    best = (score, ce)
            rows.append({"key": key, "mean": best[0][0], "pooled": best[0][1], "n_flood_chips": best[0][2],
                         "ceiling": best[1], "_order": order})
        rows.sort(key=lambda r: (tuple(-x for x in _key((r["mean"], r["pooled"]), crit)), r["_order"]))
        changed = False
        if guarded and ceiling_ext and len(added) < ceiling_ext["max"]:
            vals = [float(k) for k in current]
            w = float(rows[0]["ceiling"])
            nxt = min(vals) - ceiling_ext["step"] if w == min(vals) else max(vals) + ceiling_ext["step"] if w == max(vals) else None
            if nxt is not None:
                added.append(nxt)
                changed = True
        if not changed:
            for r in rows:
                r.pop("_order")
            return rows, {"ceiling_extensions": added}


def select_m1(store, stage1_winner_prep, assigned_options, mask, guarded, ceilings, crit, ceiling_ext=None):
    """M1 / M1g (A6.3, A9.1): k = 3 at the stage-1 winning option versus k = 2 at each assigned option; best by the criterion."""
    candidates = [("m1", stage1_winner_prep, "k3")] + [("m1", o, "k2") for o in assigned_options]
    return rank_pairs(store, candidates, mask, guarded, ceilings, crit, ceiling_ext)


def next_edge_values(values, step_n=2.0, step_c=5.0, kind="n"):
    """Beyond-the-edge values of a grid: (below, above). n_segments are integers."""
    lo, hi = min(values), max(values)
    f = step_n if kind == "n" else step_c
    conv = (lambda x: int(round(x))) if kind == "n" else (lambda x: float(f"{x:.6g}"))
    return conv(lo / f), conv(hi * f)


def select_m2_stage2(store, assigned_options, mask, guarded, base_n, base_c, ceilings, crit, ceiling_ext=None,
                     max_steps=2, step_n=2.0, step_c=5.0):
    """
    M2 / M2g Stage 2 (A9.1, A9.2): candidates = each assigned option x each (n_segments, compactness) of the current grid, ordered by option,
    then n ascending, then c ascending. If the winner sits at an edge of n or c, the grid is extended by one step (cap `max_steps` per
    parameter) provided the extension configurations are in the store; otherwise the needed configurations are returned in `pending`.
    Returns a dict: ranked, ceiling_extensions, n_list, c_list, steps_n, steps_c, pending (None or {'n':[..], 'c':[..], 'needed': {option: [[n, c], ...]}}).
    """
    n_list, c_list, steps_n, steps_c = sorted(base_n), sorted(base_c), 0, 0
    while True:
        cands = [("m2", o, config_key(n, c)) for o in assigned_options for n in n_list for c in c_list]
        ranked, cinfo = rank_pairs(store, cands, mask, guarded, ceilings, crit, ceiling_ext)
        w = ranked[0]["key"][2]                              # 'n{n}_c{c}'
        wn = int(w.split("_")[0][1:])
        wc = float(w.split("_")[1][1:])
        new_n = new_c = None
        if wn in (n_list[0], n_list[-1]) and steps_n < max_steps:
            lo, hi = next_edge_values(n_list, step_n, step_c, "n")
            new_n = lo if wn == n_list[0] else hi
        if wc in (c_list[0], c_list[-1]) and steps_c < max_steps:
            lo, hi = next_edge_values(c_list, step_n, step_c, "c")
            new_c = lo if wc == c_list[0] else hi
        if new_n is None and new_c is None:
            return {"ranked": ranked, "ceiling_extensions": cinfo["ceiling_extensions"], "n_list": n_list, "c_list": c_list,
                    "steps_n": steps_n, "steps_c": steps_c, "pending": None}
        n2 = sorted(set(n_list) | ({new_n} if new_n else set()))
        c2 = sorted(set(c_list) | ({new_c} if new_c else set()))
        needed = {o: [[n, c] for n in n2 for c in c2 if (n, c) not in {(a, b) for a in n_list for b in c_list}] for o in assigned_options}
        if any(not store.has(("m2", o, config_key(n, c))) for o in assigned_options for n, c in needed[o]):
            return {"ranked": ranked, "ceiling_extensions": cinfo["ceiling_extensions"], "n_list": n_list, "c_list": c_list,
                    "steps_n": steps_n, "steps_c": steps_c,
                    "pending": {"n": new_n, "c": new_c, "needed": needed}}
        n_list, c_list = n2, c2
        steps_n += new_n is not None
        steps_c += new_c is not None


def select_m2_stage3(store3, option, n, c, combos, mask, guarded, ceilings, crit, ceiling_ext=None):
    """M2 / M2g Stage 3 (A9.1): the allowed (features, k) combinations at the Stage 2 choice; the store holds key ('m2s3', option, 'n_c|feat|k')."""
    cands = [("m2s3", option, f"{config_key(n, c)}|{feat}|{k}") for feat, k in combos]
    return rank_pairs(store3, cands, mask, guarded, ceilings, crit, ceiling_ext)
