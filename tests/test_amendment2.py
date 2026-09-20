"""Amendment 2: abstention guard, VV seen by the rule, B1 clip skip, M1 subsample, parallel."""

import numpy as np
import pytest

from src.cluster_rule import apply_abstention_ceiling
from src.config import b1_thresholds_for_clip, clip_range, load_config
from src.evaluate import evaluate_chip, evaluate_chip_id
from src.io import data_dir
from src.methods import AbstainingMethod, ClusteringMethod, FixedThresholdVV, OtsuThreshold, PixelKMeans
from src.metrics import flood_free_summary, iou
from src.parallel import map_chips
from src.splits import load_official_splits

needs_data = pytest.mark.skipif(not (data_dir() / "splits").exists(), reason="data not downloaded")


@pytest.fixture
def flood_free_chip():
    """Background only, VV around -10 dB: nothing here is water."""
    rng = np.random.default_rng(3)
    vv = rng.normal(-10, 0.7, (48, 48)).astype(np.float32)
    vh = rng.normal(-17, 0.7, (48, 48)).astype(np.float32)
    return {"id": "Free_1", "vv": vv, "vh": vh,
            "label": np.zeros((48, 48), np.int16), "jrc": np.zeros((48, 48), np.uint8)}


# ---- abstention guard ---------------------------------------------------------------------

def test_ceiling_function_edge_cases():
    vv = np.array([[-20.0, -10.0]])
    pred = np.array([[True, False]])
    assert apply_abstention_ceiling(pred, vv, None) is pred                 # no guard
    assert apply_abstention_ceiling(pred, vv, -15.0).tolist() == [[True, False]]   # -20 < -15: keep
    assert not apply_abstention_ceiling(pred, vv, -25.0).any()              # -20 >= -25: abstain
    assert not apply_abstention_ceiling(pred, vv, -20.0).any()              # equal counts as abstain
    empty = np.zeros((1, 2), bool)
    assert apply_abstention_ceiling(empty, vv, -25.0) is empty              # nothing to abstain from


@pytest.mark.parametrize("plain", [PixelKMeans(k=2, seed=0), OtsuThreshold("vv")],
                         ids=lambda m: m.name)
def test_guard_removes_false_alarms_on_a_flood_free_chip(plain, flood_free_chip):
    assert evaluate_chip(plain, flood_free_chip)["flood_only"]["fp"] > 0   # plain rule always fires
    guarded = evaluate_chip(AbstainingMethod(plain, -18.0), flood_free_chip)
    assert guarded["flood_only"]["fp"] == 0


def test_guard_keeps_real_water_when_the_ceiling_allows_it(toy_chip):
    plain = evaluate_chip(PixelKMeans(k=2, seed=0), toy_chip)
    kept = evaluate_chip(AbstainingMethod(PixelKMeans(k=2, seed=0), -18.0), toy_chip)
    assert kept == plain                                   # water is ~ -24 dB, below -18
    dropped = evaluate_chip(AbstainingMethod(PixelKMeans(k=2, seed=0), -30.0), toy_chip)
    assert dropped["flood_only"]["tp"] == 0 and dropped["flood_only"]["fn"] == 375


def test_multi_ceiling_evaluation_equals_the_wrapper_method(toy_chip):
    plain = PixelKMeans(k=2, seed=0)
    multi = evaluate_chip(plain, toy_chip, ceilings_db=[-30.0, -18.0])
    for c in (-30.0, -18.0):
        wrapped = evaluate_chip(AbstainingMethod(plain, c), toy_chip)
        assert multi["guarded"][c]["flood_only"] == wrapped["flood_only"]
        assert multi["guarded"][c]["all_water"] == wrapped["all_water"]
    assert multi["flood_only"] == evaluate_chip(plain, toy_chip)["flood_only"]  # plain unchanged


def test_flood_free_summary_hand_computed():
    def chip(fp, tn, tp=0, fn=0, domain=None):
        return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "domain": domain or fp + tn + tp + fn}
    counts = [chip(5, 95),                 # flood-free, false alarm
              chip(0, 100),                # flood-free, quiet
              chip(3, 90, tp=5, fn=2),     # has flood: not part of the summary
              chip(0, 0, domain=0)]        # empty domain: excluded
    s = flood_free_summary(counts)
    assert s["n_chips"] == 2
    assert s["frac_chips_with_alarm"] == pytest.approx(0.5)
    assert s["pooled_fpr"] == pytest.approx(5 / 200)
    assert np.isnan(flood_free_summary([chip(1, 9, tp=1)])["pooled_fpr"])


# ---- which VV does the rule see? -----------------------------------------------------------

class FixedClusters(ClusteringMethod):
    """Stub that returns a preset cluster map, so only the rule under test decides the winner."""
    name = "stub"

    def __init__(self, cmap):
        self.cmap = cmap

    def cluster_map(self, vv, vh, cache_key=None):
        return self.cmap


def test_rule_uses_the_vv_after_clip_and_the_oracle_shares_the_cluster_map():
    # cluster 0: raw mean -26 (one -80 outlier); cluster 1: mean -20.
    vv = np.array([[-80, -8, -8, -8], [-20, -20, -20, -20]], np.float32)
    chip = {"id": "x", "vv": vv, "vh": vv - 7,
            "label": np.array([[0] * 4, [1] * 4], np.int16), "jrc": np.zeros((2, 4), np.uint8)}
    cmap = np.array([[0] * 4, [1] * 4], np.int32)
    raw = evaluate_chip(FixedClusters(cmap), chip)["all_water"]
    assert (raw["tp"], raw["fp"]) == (0, 4)            # no clip: cluster 0 looks darkest (wrong)
    clipped = evaluate_chip(FixedClusters(cmap), chip, clip={"vv": [-30, 5], "vh": [-40, 5]},
                            with_oracle=True)
    # after clipping the outlier to -30, cluster 0 has mean -13.5 and cluster 1 (-20) is darkest
    assert (clipped["all_water"]["tp"], clipped["all_water"]["fp"]) == (4, 0)
    assert clipped["all_water_oracle"] == clipped["all_water"]   # oracle picks from the same map


# ---- B1 thresholds under a clip -------------------------------------------------------------

def test_b1_thresholds_skip_values_that_predict_nothing_under_a_clip():
    cfg = load_config()
    assert len(b1_thresholds_for_clip(cfg, None)) == 23                       # -30 .. -8
    assert len(b1_thresholds_for_clip(cfg, clip_range(cfg, "wide"))) == 23    # floor -40: none skipped
    assert len(b1_thresholds_for_clip(cfg, clip_range(cfg, "medium"))) == 22  # -30 skipped
    narrow = clip_range(cfg, "narrow")                                        # floor -25
    kept = b1_thresholds_for_clip(cfg, narrow)
    assert len(kept) == 17 and min(kept) == -24.0
    vv = np.array([[-25.0, -10.0]], np.float32)                               # already clipped data
    assert not FixedThresholdVV(-25.0).predict(vv, vv).any()                  # t == floor: empty


# ---- M1 subsample fit -----------------------------------------------------------------------

def test_subsample_fit_assigns_every_valid_pixel_and_is_deterministic(toy_chip):
    vv, vh = toy_chip["vv"], toy_chip["vh"]
    a = PixelKMeans(k=2, seed=0, fit_subsample=500).cluster_map(vv, vh)
    b = PixelKMeans(k=2, seed=0, fit_subsample=500).cluster_map(vv, vh)
    assert np.array_equal(a, b)
    assert (a[np.isnan(vv)] == -1).all() and (a[np.isfinite(vv)] >= 0).all()


def test_subsample_equals_full_fit_on_well_separated_data(toy_chip):
    full = PixelKMeans(k=2, seed=0).predict(toy_chip["vv"], toy_chip["vh"])
    sub = PixelKMeans(k=2, seed=0, fit_subsample=500).predict(toy_chip["vv"], toy_chip["vh"])
    assert np.array_equal(full, sub)


def test_subsample_larger_than_the_chip_is_the_full_fit(toy_chip):
    full = PixelKMeans(k=3, seed=0).cluster_map(toy_chip["vv"], toy_chip["vh"])
    big = PixelKMeans(k=3, seed=0, fit_subsample=10 ** 6).cluster_map(toy_chip["vv"], toy_chip["vh"])
    assert np.array_equal(full, big)


# ---- parallel == serial ---------------------------------------------------------------------

@needs_data
def test_parallel_results_equal_serial_results():
    ids = sorted(load_official_splits()["valid"])[:4]
    kw = dict(method=PixelKMeans(k=2, seed=0), clip=None, median_window=0, prep_name="p")
    serial = map_chips(evaluate_chip_id, ids, n_jobs=1, **kw)
    parallel = map_chips(evaluate_chip_id, ids, n_jobs=2, **kw)
    assert serial == parallel


# ---- Amendment 3: seed-sensitivity helper ---------------------------------------------------

def test_seed_rows_shape_and_identical_seeds_agree_on_separated_data(toy_chip):
    from src.seed_check import seed_rows
    rows = seed_rows(toy_chip["vv"], toy_chip["vh"], ks=[2], seeds=[42, 0, 1], n_init=3, max_iter=300)
    assert len(rows) == 2                                    # one row per non-reference seed
    assert all(r["iou"] == 1.0 for r in rows)                # two clean blobs: every seed agrees
    assert rows[0]["reference_water_px"] == 500            # the 20 x 25 dark block, nothing else
    assert rows[0]["seed_water_px"] == 500 and rows[0]["valid_px"] == 4060   # 64*64 minus 36 NaN px
    assert rows[0]["reference_mean_vv"] < -20                # the water cluster is the dark one


# ---- config hygiene -------------------------------------------------------------------------

def test_config_has_no_accidental_boolean_or_numeric_keys():
    """YAML reads a bare `on:` or `no:` as True/False; keys must be strings (n_init_by_k is the one int-keyed map)."""
    cfg = load_config()

    def walk(node, path=""):
        if isinstance(node, dict):
            for key, value in node.items():
                allowed_int_keys = path.endswith("n_init_by_k")
                assert isinstance(key, str) or (allowed_int_keys and isinstance(key, int)
                                                and not isinstance(key, bool)), f"bad key {key!r} at {path}"
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for item in node:
                walk(item, path)
    walk(cfg)


# ---- Amendment 5: seed-comparison helper ----------------------------------------------------

def test_compare_seeds_and_prep_name_hand_computed():
    from src.config import prep_name
    from src.seed_check import compare_seeds

    class Stub(ClusteringMethod):
        def __init__(self, cmap):
            self.cmap = np.array([cmap], np.int32)

        def cluster_map(self, vv, vh, cache_key=None):
            return self.cmap

    vv = np.array([[-25, -25, -10, -10, -5, -5]], np.float32)
    maps = {42: [0, 0, 1, 1, 2, 2], 0: [0, 0, 1, 1, 2, 2], 1: [0, 1, 1, 1, 2, 2]}
    rows = compare_seeds(lambda seed: Stub(maps[seed]), vv, vv - 7, [42, 0, 1])
    assert [r["seed"] for r in rows] == [0, 1]
    assert rows[0]["iou"] == 1.0                                    # same partition
    # seed 1: water is the cluster holding only pixel 0 (mean -25); reference water = pixels 0 and 1
    assert rows[1]["iou"] == 0.5 and rows[1]["reference_water_px"] == 2 and rows[1]["seed_water_px"] == 1
    assert rows[1]["valid_px"] == 6 and rows[1]["reference_mean_vv"] == -25.0
    assert prep_name("medium", 3) == "clip=medium,median=3"
