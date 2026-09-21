"""Final selection (protocol A9): M1 pools, M2 stage 2 with the grid-edge rule, stage 3, and the new unit workers."""

import numpy as np
import pytest

from src.config import load_config
from src.evaluate import evaluate_chip
from src.methods import SlicKMeans
from src.ranking import PRIMARY, SENSITIVITY, derive_ceiling_counts
from src.selection import (Store, next_edge_values, rank_pairs, select_m1, select_m2_stage2, select_m2_stage3)
from src.stage1 import _enc, preprocessing_options
from src.stage2 import (combo_key, compute_stage2, compute_stage3, config_key, stage2_params, stage3_path, stage3_unit)

MASK = np.array([True])
CEILS = ["-18", "-15", "-12"]


def plain(tp, fp=0, fn=0, domain=100):
    """One chip; pooled IoU = tp / (tp + fp + fn)."""
    return np.array([[[tp, fp, fn, domain - tp - fp - fn, domain]] * 2], dtype=np.int64)


def store_with(entries):
    s = Store()
    for key, value in entries.items():
        tp, fp = value if isinstance(value, tuple) else (value, 100 - value)
        s.add(key, plain(tp, fp), np.array([-20.0]))
    return s


def test_store_returns_plain_counts_and_exact_derived_ceilings():
    s = Store()
    key = ("m1", "a", "k3")
    s.add(key, plain(8, 1, 1), np.array([-10.0]))                  # predicted region's mean VV is -10 dB
    assert s.counts(key, "plain") is s.plain[key]
    assert s.counts(key, "-5")[0, 0].tolist() == [8, 1, 1, 90, 100]        # -10 < -5: the guard keeps the prediction
    assert s.counts(key, "-12")[0, 0].tolist() == [0, 0, 9, 91, 100]       # -10 >= -12: abstain, FN = truth = 9
    assert np.array_equal(s.counts(key, "-15"), derive_ceiling_counts(s.plain[key], s.mv[key], -15.0))


def test_rank_pairs_plain_ignores_ceilings_and_guarded_picks_the_best_ceiling_jointly():
    s = Store()
    s.add(("m1", "a", "k3"), plain(50, 50), np.array([-20.0]))     # mean VV -20: kept at every ceiling
    s.add(("m1", "b", "k3"), plain(40, 10), np.array([-14.0]))     # -14: kept only at -12; abstains at -18 and -15
    cands = [("m1", "a", "k3"), ("m1", "b", "k3")]
    ranked, _ = rank_pairs(s, cands, MASK, False, CEILS, PRIMARY)
    assert [r["key"][1] for r in ranked] == ["b", "a"] and ranked[0]["ceiling"] == "plain"    # 40/50 beats 50/100
    ranked, _ = rank_pairs(s, cands, MASK, True, CEILS, PRIMARY)
    assert ranked[0]["key"][1] == "b" and ranked[0]["ceiling"] == "-12"                       # its only ceiling that keeps it


def test_rank_pairs_keeps_the_earlier_candidate_on_a_tie():
    s = store_with({("m1", "a", "k3"): 30, ("m1", "b", "k3"): 30})
    ranked, _ = rank_pairs(s, [("m1", "b", "k3"), ("m1", "a", "k3")], MASK, False, CEILS, PRIMARY)
    assert ranked[0]["key"][1] == "b"


def test_m1_pool_is_the_stage1_k3_winner_plus_k2_at_the_assigned_options():
    s = store_with({("m1", "w", "k3"): 30, ("m1", "x", "k2"): 45, ("m1", "y", "k2"): 20, ("m1", "z", "k3"): 99})
    ranked, _ = select_m1(s, "w", ["x", "y"], MASK, False, CEILS, PRIMARY)
    assert {r["key"] for r in ranked} == {("m1", "w", "k3"), ("m1", "x", "k2"), ("m1", "y", "k2")}   # z (k=3, not the winner) is not a candidate
    assert ranked[0]["key"] == ("m1", "x", "k2")
    ranked, _ = select_m1(s, "w", ["y"], MASK, False, CEILS, PRIMARY)
    assert ranked[0]["key"] == ("m1", "w", "k3")                                                   # k=3 can win too


def grid_store(score, extra=()):
    """M2 store for one option 'o' over the base grid (+ extra (n, c) pairs); score(n, c) is the pooled IoU x 100."""
    entries = {}
    for n in (200, 500, 1000, 2000):
        for c in (0.01, 0.05, 0.2, 1.0):
            entries[("m2", "o", config_key(n, c))] = score(n, c)
    for n, c in extra:
        entries[("m2", "o", config_key(n, c))] = score(n, c)
    return store_with(entries)


BASE_N, BASE_C = [200, 500, 1000, 2000], [0.01, 0.05, 0.2, 1.0]


def test_next_edge_values():
    assert next_edge_values([200, 500, 1000, 2000], kind="n") == (100, 4000)
    assert next_edge_values([0.01, 0.05, 0.2, 1.0], kind="c") == (0.002, 5.0)
    assert next_edge_values([100, 200, 4000], kind="n") == (50, 8000)


def test_m2_edge_rule_pending_then_extended_then_capped():
    peak = lambda n, c: 30 + (10 if n == 2000 else 0)                     # best at n = 2000 (an edge), interior c? make c interior:
    score = lambda n, c: peak(n, c) + (5 if c == 0.05 else 0)
    out = select_m2_stage2(grid_store(score), ["o"], MASK, False, BASE_N, BASE_C, CEILS, PRIMARY)
    assert out["pending"]["n"] == 4000 and out["pending"]["c"] is None and out["steps_n"] == 0       # 4000 not computed yet
    assert out["pending"]["needed"]["o"] == [[4000, c] for c in BASE_C]                                  # new n crossed with the current c values
    grow = lambda n, c: score(n, c) + (20 if n == 4000 else 0) + (30 if n == 8000 else 0)   # each new edge value beats the last
    extra = [(4000, c) for c in BASE_C]
    out = select_m2_stage2(grid_store(grow, extra), ["o"], MASK, False, BASE_N, BASE_C, CEILS, PRIMARY)
    assert out["steps_n"] == 1 and out["n_list"][-1] == 4000 and out["pending"]["n"] == 8000       # 4000 wins, again at an edge
    extra2 = extra + [(8000, c) for c in BASE_C]
    out = select_m2_stage2(grid_store(grow, extra2), ["o"], MASK, False, BASE_N, BASE_C, CEILS, PRIMARY)
    assert out["steps_n"] == 2 and out["pending"] is None and out["ranked"][0]["key"][2].startswith("n8000")   # cap of 2 steps reached


def test_m2_edge_rule_extends_both_parameters_and_crosses_the_new_value_with_the_other_grid():
    score = lambda n, c: 50 if (n, c) == (200, 0.01) else 10             # best in the corner
    out = select_m2_stage2(grid_store(score), ["o"], MASK, False, BASE_N, BASE_C, CEILS, PRIMARY)
    assert out["pending"]["n"] == 100 and out["pending"]["c"] == 0.002
    need = {tuple(x) for x in out["pending"]["needed"]["o"]}
    assert need == {(100, c) for c in [0.002] + BASE_C} | {(n, 0.002) for n in BASE_N}          # new row and new column, corner included


def test_m2_interior_winner_does_not_trigger_and_guarded_uses_the_ceiling():
    score = lambda n, c: 60 if (n, c) == (500, 0.05) else 20
    out = select_m2_stage2(grid_store(score), ["o"], MASK, False, BASE_N, BASE_C, CEILS, PRIMARY)
    assert out["pending"] is None and out["ranked"][0]["key"][2] == "n500_c0.05" and out["steps_n"] == out["steps_c"] == 0
    out = select_m2_stage2(grid_store(score), ["o"], MASK, True, BASE_N, BASE_C, CEILS, PRIMARY)
    assert out["ranked"][0]["ceiling"] in CEILS                          # a ceiling was chosen jointly


def test_stage3_selects_among_the_allowed_combinations():
    combos = [["vv", 2], ["vv_vh", 2], ["vv_vh_std", 3]]
    s = Store()
    for (feat, k), v in zip(combos, (20, 40, 35)):
        s.add(("m2s3", "o", f"n500_c0.05|{feat}|{k}"), plain(v, 100 - v), np.array([-20.0]))
    ranked, _ = select_m2_stage3(s, "o", 500, 0.05, combos, MASK, False, CEILS, PRIMARY)
    assert ranked[0]["key"][2] == "n500_c0.05|vv_vh|2"


# ---- the new unit workers -----------------------------------------------------------------------------------------------------

def _params(fake_dataset):
    params, _ = fake_dataset
    p = dict(stage2_params(load_config()))
    p.update(data_dir=params["data_dir"], unit_dir=params["unit_dir"], slic_cache_dir=params["slic_cache_dir"],
             stage2_dir=params["unit_dir"] + "_s2", stage3_dir=params["unit_dir"] + "_s3")
    return p


def test_extension_round_unit_computes_only_the_requested_configurations(fake_dataset, toy_chip):
    p = _params(fake_dataset)
    p["ext_grid"] = {"clip=none,median=0": [[4000, 0.05], [4000, 0.2]]}
    prep = {"name": "clip=none,median=0", "clip": "none", "median": 0}
    out = compute_stage2(toy_chip, prep, p, "m2x1")["configs"]
    assert set(out) == {"n4000_c0.05", "n4000_c0.2"}
    direct = evaluate_chip(SlicKMeans(2, 4000, 0.2, "vv_vh", p["seed"], n_init=10), toy_chip, None, 0)
    assert out["n4000_c0.2"]["plain"] == _enc(direct)


def test_stage3_unit_has_every_combination_and_reproduces_the_stage2_configuration(fake_dataset, toy_chip):
    p = _params(fake_dataset)
    prep = {"name": "clip=none,median=0", "clip": "none", "median": 0}
    out = compute_stage3(toy_chip, prep, 1000, 0.2, p)["configs"]
    assert set(out) == {combo_key(f, k) for f, k in p["s3"]["combos"]} and len(out) == 6
    stage2 = compute_stage2(toy_chip, prep, p, "m2")["configs"]["n1000_c0.2"]
    assert out[combo_key("vv_vh", 2)] == stage2                           # (vv_vh, 2) is the stage-2 configuration itself
    preps = preprocessing_options(load_config())
    assert stage3_unit("Toy_1|clip=none,median=0|1000|0.2", p, preps)[1] == "done"
    assert stage3_path(p["stage3_dir"], "Toy_1", "clip=none,median=0", 1000, 0.2).exists()
    assert stage3_unit("Toy_1|clip=none,median=0|1000|0.2", p, preps)[1] == "skipped"
    assert stage3_unit("Missing_9|clip=none,median=0|1000|0.2", p, preps)[1].startswith("error")
