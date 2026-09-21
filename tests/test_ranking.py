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


# ---- Amendment 7: pooled criterion, tie-breaks, median-window extensions ---------------------

from src.ranking import (PRIMARY, SENSITIVITY, available_extra_medians, extra_prep_names, median_of,
                         rank_with_extensions)
from src.stage1 import preprocessing_options as _prep_options


def _mk(rows):
    return counts_array([(tp, fp, fn, 100 - tp - fp - fn, 100) for tp, fp, fn in rows])


def test_pooled_criterion_lets_flood_free_chips_count_and_the_declared_criterion_does_not():
    # chip A has flood, chip B is flood-free. Ceiling X keeps A intact but B keeps 50 false-alarm pixels;
    # ceiling Y loses a little on A but abstains on B.
    counts = {("m1", "p", "nominal", "X"): _mk([(8, 1, 1), (0, 50, 0)]),
              ("m1", "p", "nominal", "Y"): _mk([(7, 1, 2), (0, 0, 0)])}
    mask = np.array([True, True])
    declared = rank_options(counts, "m1", mask, True, ["p"], ["X", "Y"], SENSITIVITY)[0]
    amended = rank_options(counts, "m1", mask, True, ["p"], ["X", "Y"], PRIMARY)[0]
    assert declared["ceiling"] == "X" and declared["mean"] == pytest.approx(0.8)      # B is invisible: X looks better
    assert amended["ceiling"] == "Y" and amended["pooled"] == pytest.approx(7 / 10)   # B's false alarms now count
    assert criterion(counts[("m1", "p", "nominal", "X")], mask)[1] == pytest.approx(8 / (8 + 51 + 1))


def test_primary_ties_fall_to_config_order_and_do_not_use_the_mean():
    same = _mk([(5, 5, 0), (0, 0, 0)])
    counts = {("m1", "a", "nominal", "plain"): same, ("m1", "b", "nominal", "plain"): same.copy()}
    ranked = rank_options(counts, "m1", np.array([True, True]), False, ["a", "b"], crit=PRIMARY)
    assert [r["prep"] for r in ranked] == ["a", "b"]
    ranked = rank_options(counts, "m1", np.array([True, True]), False, ["b", "a"], crit=PRIMARY)
    assert [r["prep"] for r in ranked] == ["b", "a"]                                  # order in the config decides


def test_names_and_extra_options():
    assert median_of("clip=medium,median=11") == 11 and median_of("clip=none,median=0") == 0
    assert extra_prep_names(["none", "wide"], [9, 11]) == ["clip=none,median=9", "clip=wide,median=9",
                                                            "clip=none,median=11", "clip=wide,median=11"]
    opts = _prep_options(load_config(), extra_medians=[9])
    assert len(opts) == 20 and opts[15]["name"] == "clip=narrow,median=7"                # the base 16 keep their order
    assert [o["name"] for o in opts[16:]] == ["clip=none,median=9", "clip=wide,median=9",
                                              "clip=medium,median=9", "clip=narrow,median=9"]
    assert len(_prep_options(load_config())) == 16


def _by_median(scores):
    """One chip; option 'clip=none,median=M' gets pooled IoU scores[M]/100."""
    return {("m1", f"clip=none,median={m}", "nominal", "plain"): _mk([(v, 100 - v - 0, 0)]) for m, v in scores.items()}


BASE = [f"clip=none,median={m}" for m in (0, 3, 5, 7)]


def _rank(scores, available):
    return rank_with_extensions(_by_median(scores), "m1", np.array([True]), False, BASE, ["none"], [], PRIMARY,
                                available)


def test_extension_rule_stops_at_each_declared_condition():
    up = {0: 10, 3: 20, 5: 30, 7: 40, 9: 50, 11: 60}
    ranked, info = _rank(up, available=[])                       # edge winner, no units for median 9: reported as pending
    assert info == {"extensions": [], "pending": 9} and median_of(ranked[0]["prep"]) == 7 and len(ranked) == 4
    ranked, info = _rank(up, available=[9])                      # 9 added; it wins at the new edge; 11 is pending
    assert info == {"extensions": [9], "pending": 11} and median_of(ranked[0]["prep"]) == 9
    ranked, info = _rank(up, available=[9, 11])                  # two extensions are the cap
    assert info == {"extensions": [9, 11], "pending": None} and median_of(ranked[0]["prep"]) == 11
    ranked, info = _rank({**up, 5: 90}, available=[9, 11])       # interior winner: the rule does not trigger
    assert info == {"extensions": [], "pending": None} and median_of(ranked[0]["prep"]) == 5
    ranked, info = _rank({**up, 9: 35, 11: 30}, available=[9, 11])   # 9 is added but 7 still wins: stop, nothing pending
    assert info == {"extensions": [9], "pending": None} and median_of(ranked[0]["prep"]) == 7


def test_available_extra_medians_needs_every_chip_and_is_consecutive(tmp_path):
    def touch(chip, prep):
        f = unit_path(tmp_path, chip, prep)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("{}")
    for chip in ("A", "B"):
        for name in extra_prep_names(["none"], [9]):
            touch(chip, name)
    assert available_extra_medians(tmp_path, ["A", "B"], ["none"]) == [9]
    touch("A", "clip=none,median=11")                            # 11 exists for one chip only
    assert available_extra_medians(tmp_path, ["A", "B"], ["none"]) == [9]
    touch("B", "clip=none,median=11")
    assert available_extra_medians(tmp_path, ["A", "B"], ["none"]) == [9, 11]


def test_union_counts_an_absent_option_as_rank_length_plus_one():
    order = ["a", "b", "c"]
    rankings = {"s1": ["a", "b", "c"], "s2": ["a", "b"]}          # s2 has no option c
    out = stage2_union(rankings, order, top=1, cap=3)
    assert out["mean_rank"]["c"] == pytest.approx((3 + 3) / 2)    # rank 3 in s1; absent from s2, length 2 + 1 = 3
    assert out["mean_rank"]["a"] == 1.0


# ---- Amendment 8: mean VV stored per unit; counts at any ceiling derived exactly -------------------------------------------

from src.evaluate import evaluate_chip
from src.methods import PixelKMeans
from src.ranking import add_derived_ceilings, derive_ceiling_counts, load_mv, verify_derived_ceilings
from src.stage1 import mv_path, mv_unit


def test_derive_ceiling_counts_hand_computed_including_boundary_and_empty():
    plain = counts_array([(8, 1, 1, 90, 100), (0, 5, 4, 91, 100), (0, 0, 3, 97, 100)])
    mv = np.array([-20.0, -10.0, np.nan])                     # chip 2 predicted nothing
    out = derive_ceiling_counts(plain, mv, -15.0)
    assert out[0, FLOOD].tolist() == [8, 1, 1, 90, 100]       # -20 < -15: keep
    assert out[1, FLOOD].tolist() == [0, 0, 4, 96, 100]       # -10 >= -15: abstain, FN = truth (4), TN = 100 - 4
    assert out[2, FLOOD].tolist() == [0, 0, 3, 97, 100]       # empty prediction: unchanged
    assert derive_ceiling_counts(plain, np.array([-15.0, -15.0, np.nan]), -15.0)[0, FLOOD].tolist() == [0, 0, 9, 91, 100]  # equal abstains
    assert plain[0, FLOOD].tolist() == [8, 1, 1, 90, 100]     # the input is not modified


@pytest.mark.parametrize("water_shift", [0.0, 10.0])          # water at about -24 dB and at about -14 dB
def test_derived_counts_equal_the_direct_guard_for_every_ceiling(toy_chip, water_shift):
    chip = dict(toy_chip)
    vv = toy_chip["vv"].copy()
    vv[10:30, 10:35] += water_shift
    chip["vv"] = vv
    ceilings = [-30.0, -21.0, -18.0, -15.0, -12.0, -9.0, -6.0]
    direct = evaluate_chip(PixelKMeans(2, 0), chip, ceilings_db=ceilings)
    plain = np.array([[[direct[m][k] for k in ("tp", "fp", "fn", "tn", "domain")] for m in ("flood_only", "all_water")]])
    mv = np.array([np.nan if direct["water_mean_vv"] is None else direct["water_mean_vv"]])
    for c in ceilings:
        want = np.array([[[direct["guarded"][c][m][k] for k in ("tp", "fp", "fn", "tn", "domain")]
                          for m in ("flood_only", "all_water")]])
        assert np.array_equal(derive_ceiling_counts(plain, mv, c), want), c


def test_mv_files_round_trip_and_reproduce_every_stored_ceiling(fake_dataset):
    params, preps = fake_dataset
    cfg_preps = preprocessing_options(load_config())
    names = [p["name"] for p in cfg_preps[:2]]
    for n in names:
        assert stage1_unit(f"Toy_1|{n}", params, cfg_preps)[1] == "done"
        assert mv_unit(f"Toy_1|{n}", params, cfg_preps)[1] == "done"
    assert mv_unit(f"Toy_1|{names[0]}", params, cfg_preps)[1] == "skipped"              # resumable
    assert not list(mv_path(params["unit_dir"], "Toy_1", names[0]).parent.glob("*.tmp"))
    counts, _ = load_units(params["unit_dir"], ["Toy_1"], names)
    mv = load_mv(params["unit_dir"], ["Toy_1"], names)
    checked, bad = verify_derived_ceilings(counts, mv, params["ceilings"])
    assert checked == 4 * 2 * 3 and bad == 0                                              # 4 families x 2 options x 3 ceilings
    add_derived_ceilings(counts, mv, [-21.0, -9.0])
    assert ("m1", names[0], "nominal", "-21") in counts and ("b2_vh", names[1], "nominal", "-9") in counts
    with pytest.raises(FileNotFoundError):
        load_mv(params["unit_dir"], ["Toy_1"], [cfg_preps[7]["name"]])


# ---- Amendment 8: guard-ceiling extension inside the ranking -----------------------------------------------------------------

from src.stage1 import ceiling_key


def _ceil_counts(by_ceiling):
    """One chip, one option 'p', guarded family m1: ceiling key -> pooled IoU / 100 (tp = v, fp = 100 - v)."""
    return {("m1", OPT, "nominal", ceiling_key(c)): _mk([(v, 100 - v, 0)]) for c, v in by_ceiling.items()}


OPT = "clip=none,median=0"
BASE_CEIL = ["-18", "-15", "-12"]
EXT = {"available": [-24.0, -21.0, -9.0, -6.0], "step": 3.0, "max": 2}


def _rank_ceil(scores, ext=EXT, guarded=True):
    return rank_with_extensions(_ceil_counts(scores), "m1", np.array([True]), guarded, [OPT], ["none"], BASE_CEIL, PRIMARY,
                                [], base_max_median=0, ceiling_ext=ext)


def test_ceiling_extension_follows_the_lower_edge_and_stops_at_the_cap():
    s = {-24: 10, -21: 20, -18: 30, -15: 25, -12: 20, -9: 5, -6: 5}
    ranked, info = _rank_ceil(s)                                # -18 wins at the low edge; -21 (20) is worse: stop
    assert ranked[0]["ceiling"] == "-18" and info["ceiling_extensions"] == [-21.0] and info["pending_ceiling"] is None
    up = {-24: 50, -21: 40, -18: 30, -15: 25, -12: 20, -9: 5, -6: 5}
    wide = {**EXT, "available": [-30.0, -27.0, -24.0, -21.0, -9.0, -6.0, -3.0]}   # steps beyond the cap exist and score better
    ranked, info = _rank_ceil({**up, -21: 60, -24: 70, -27: 80, -30: 90}, ext=wide)   # keeps improving: -21, -24, then the cap of 2
    assert ranked[0]["ceiling"] == "-24" and info["ceiling_extensions"] == [-21.0, -24.0]
    ranked, info = _rank_ceil({-18: 10, -15: 20, -12: 30, -9: 40, -6: 50, -3: 60, -21: 0, -24: 0}, ext=wide)   # upper edge, cap of 2
    assert ranked[0]["ceiling"] == "-6" and info["ceiling_extensions"] == [-9.0, -6.0]


def test_ceiling_extension_leaves_interior_winners_plain_variants_and_unavailable_steps_alone():
    ranked, info = _rank_ceil({-18: 10, -15: 30, -12: 20, -21: 5, -9: 5})
    assert ranked[0]["ceiling"] == "-15" and info["ceiling_extensions"] == []            # interior: no trigger
    ranked, info = _rank_ceil({-18: 30, -15: 20, -12: 10, -21: 40}, ext={**EXT, "available": []})
    assert info["ceiling_extensions"] == [] and info["pending_ceiling"] == -21.0          # triggered but not available
    plain = {("m1", OPT, "nominal", "plain"): _mk([(20, 80, 0)])}
    ranked, info = rank_with_extensions(plain, "m1", np.array([True]), False, [OPT], ["none"], BASE_CEIL, PRIMARY, [],
                                        base_max_median=0, ceiling_ext=EXT)
    assert info["ceiling_extensions"] == []                                               # a plain variant has no ceiling
    ranked, info = _rank_ceil({-18: 30, -15: 20, -12: 10}, ext=None)
    assert set(info) == {"extensions", "pending"}                                          # off by default (sensitivity criterion)
