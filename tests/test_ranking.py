"""Stage 1 aggregation: the criterion, plain vs guarded ranking (A3.1), tuning sets, and the union (A5.3)."""

import numpy as np
import pytest

from src.ranking import (FLOOD, check_consistency, criterion, load_units, rank_options, stage2_union,
                         tuning_sets, project_stage2_cost)
from src.stage1 import compute_stage1_counts, preprocessing_options, stage1_unit, unit_path
from src.config import load_config


def counts_array(rows):
    """rows: [(tp, fp, fn, tn, domain), ...] per chip -> (n, 2, 5) with the same numbers in both modes."""
    a = np.array(rows, dtype=np.int64)
    return np.stack([a, a], axis=1)


def test_criterion_hand_computed():
    # chip A: tp5 fp5 fn0 -> IoU 0.5 | chip B: tp0 fp3 fn5 -> IoU 0 | chip C: no truth (tp0 fn0) -> not averaged
    c = counts_array([(5, 5, 0, 90, 100), (0, 3, 5, 92, 100), (0, 4, 0, 96, 100)])
    mean, pooled, n = criterion(c, np.array([True, True, True]))
    assert mean == pytest.approx(0.25) and n == 2
    assert pooled == pytest.approx(5 / (5 + 12 + 5))          # tp 5, fp 5+3+4, fn 5
    assert criterion(c, np.array([True, False, True]))[0] == pytest.approx(0.5)   # B removed from the tuning set
    assert np.isnan(criterion(c, np.array([False, False, True]))[0])              # only a flood-free chip: undefined


def test_held_out_chips_cannot_change_a_tuning_set_score():
    c = counts_array([(5, 5, 0, 90, 100), (0, 3, 5, 92, 100), (7, 1, 1, 91, 100)])
    mask = np.array([True, True, False])                      # chip 2 is held out
    before = criterion(c, mask)
    c2 = c.copy()
    c2[2] = [[99, 99, 99, 99, 400]] * 2                       # wreck the held-out chip's counts
    assert criterion(c2, mask) == before


def test_tuning_sets_are_eleven_folds_plus_official_valid():
    events = ["A", "A", "B", "C"]
    splits = ["train", "valid", "test", "valid"]
    sets = tuning_sets(events, splits)
    assert set(sets) == {"loeo:A", "loeo:B", "loeo:C", "official_valid"}
    assert sets["loeo:A"].tolist() == [False, False, True, True]        # held-out event's chips are out
    assert sets["official_valid"].tolist() == [False, True, False, True]


def _family_counts():
    """Two preprocessing options p1, p2 for family m1 on 2 chips with flood, plain and three ceilings."""
    def mk(iou_pairs):  # per chip (tp, fp, fn) -> IoU tp/(tp+fp+fn) with domain 100
        return counts_array([(tp, fp, fn, 100 - tp - fp - fn, 100) for tp, fp, fn in iou_pairs])
    return {
        ("m1", "p1", "nominal", "plain"): mk([(8, 1, 1), (8, 1, 1)]),   # IoU 0.8  best plain option
        ("m1", "p2", "nominal", "plain"): mk([(5, 3, 2), (5, 3, 2)]),   # IoU 0.5
        # guarded: p1 is never helped by a guard; p2 becomes excellent with ceiling -15 (guard removes its false alarms)
        ("m1", "p1", "nominal", "-18"): mk([(8, 1, 1), (8, 1, 1)]),
        ("m1", "p1", "nominal", "-15"): mk([(8, 1, 1), (8, 1, 1)]),
        ("m1", "p1", "nominal", "-12"): mk([(7, 1, 2), (7, 1, 2)]),
        ("m1", "p2", "nominal", "-18"): mk([(4, 3, 3), (4, 3, 3)]),
        ("m1", "p2", "nominal", "-15"): mk([(10, 0, 0), (10, 0, 0)]),   # IoU 1.0
        ("m1", "p2", "nominal", "-12"): mk([(5, 3, 2), (5, 3, 2)]),
    }


def test_plain_ranks_on_unguarded_scores_only_and_guarded_ranks_config_ceiling_pairs():
    counts, mask = _family_counts(), np.array([True, True])
    plain = rank_options(counts, "m1", mask, guarded=False, prep_order=["p1", "p2"], ceilings=["-18", "-15", "-12"])
    assert [r["prep"] for r in plain] == ["p1", "p2"]                   # the guard never enters the plain ranking
    assert plain[0]["mean"] == pytest.approx(0.8) and plain[0]["ceiling"] == "plain"
    guarded = rank_options(counts, "m1", mask, guarded=True, prep_order=["p1", "p2"], ceilings=["-18", "-15", "-12"])
    assert [r["prep"] for r in guarded] == ["p2", "p1"]                 # a different winner, chosen jointly with its ceiling
    assert guarded[0]["ceiling"] == "-15" and guarded[0]["mean"] == pytest.approx(1.0)
    assert all(r["ceiling"] != "plain" for r in guarded)                # guarded candidates are ceilings only


def test_b1_ranking_uses_each_options_best_threshold_and_ties_go_to_config_order():
    def mk(tp): return counts_array([(tp, 2, 2, 90 - tp, 100)])
    counts = {("b1", "p1", "-20", "plain"): mk(5), ("b1", "p1", "-15", "plain"): mk(9),
              ("b1", "p2", "-20", "plain"): mk(9), ("b1", "p2", "-15", "plain"): mk(1)}
    ranked = rank_options(counts, "b1", np.array([True]), guarded=False, prep_order=["p1", "p2"])
    assert [(r["prep"], r["cfg"]) for r in ranked] == [("p1", "-15"), ("p2", "-20")]   # tie in score: p1 comes first


def test_union_rule_hand_computed_with_tiebreak_cap_and_fallback():
    order = list("abcde")
    rankings = {"s1": list("abcde"), "s2": list("acbed"), "s3": list("bacde"), "s4": list("cadbe")}
    # top-2 choices: s1 a,b | s2 a,c | s3 b,a | s4 c,a  ->  a:4, b:2, c:2
    # mean rank: b (2+3+1+4)/4 = 2.5, c (3+2+3+1)/4 = 2.25  ->  c beats b on the tie
    out = stage2_union(rankings, order, top=2, cap=3)
    assert out["chosen_by"] == {"a": 4, "b": 2, "c": 2} and out["union"] == ["a", "c", "b"]
    assert out["mean_rank"]["b"] == pytest.approx(2.5) and out["mean_rank"]["c"] == pytest.approx(2.25)
    capped = stage2_union(rankings, order, top=2, cap=2)
    assert capped["union"] == ["a", "c"]
    assert capped["assigned"]["s3"] == ["a", "c"]        # s3's top-2 was b, a; b left the union, so it falls back to its next in-union option
    assert capped["assigned"]["s1"] == ["a", "c"]        # likewise s1 (a, b) -> a, then c
    assert capped["assigned"]["s2"] == ["a", "c"]


def test_cost_projection_counts_shared_options_once():
    seconds = {"m2": [1.0, 1.0], "m1": [2.0, 2.0]}
    unions = {"m1": ["a", "b"], "m1g": ["b", "c"], "m2": ["x", "y"], "m2g": ["y"]}
    out = project_stage2_cost(unions, seconds, n_chips=100, speedup=2.0)
    assert out["m2_options"] == 2 and out["m1_options"] == 3                     # shared options are computed once
    serial = 100 * (2 * 15 * 1.0 + 3 * 2.0 * 0.30)
    assert out["serial_h"] == pytest.approx(serial / 3600) and out["wall_h"] == pytest.approx(serial / 3600 / 2)


def test_load_units_round_trip_and_consistency(fake_dataset):
    params, preps = fake_dataset
    cfg_preps = preprocessing_options(load_config())
    for p in cfg_preps[:2]:
        assert stage1_unit(f"Toy_1|{p['name']}", params, cfg_preps)[1] == "done"
    names = [p["name"] for p in cfg_preps[:2]]
    counts, seconds = load_units(params["unit_dir"], ["Toy_1"], names)
    check_consistency(counts)
    a = counts[("b1", names[0], "-17", "plain")]
    assert a.shape == (1, 2, 5) and a[0, FLOOD].tolist() == [375, 0, 0, 3304, 3679]
    assert ("m2", names[1], "nominal", "-18") in counts and set(seconds) == {"preprocess", "b1", "b2", "m1", "m2"}
    with pytest.raises(FileNotFoundError):
        load_units(params["unit_dir"], ["Toy_1"], [cfg_preps[5]["name"]])           # a unit that was never computed
    bad = dict(counts)
    key = ("b1", names[0], "-17", "plain")
    bad[key] = counts[key].copy(); bad[key][0, FLOOD, 2] += 1                         # a candidate disagreeing on truth
    with pytest.raises(AssertionError):
        check_consistency(bad)
