"""
scripts/04_evaluate.py checked in isolation (protocol A3.4): method reconstruction from a frozen
record, the "all frozen configs exist" and lock refusals, and the summary statistics on tiny,
hand-computable counts. No real chip is read here.
"""

import importlib.util
import json

import pytest
import yaml

from src.config import REPO_ROOT
from src.methods import AbstainingMethod, FixedThresholdVV, OtsuThreshold, PixelKMeans, SlicKMeans


def _load_module():
    spec = importlib.util.spec_from_file_location("heldout_evaluate", REPO_ROOT / "scripts" / "04_evaluate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mod():
    return _load_module()


def c(tp, fp, fn, tn):
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "domain": tp + fp + fn + tn}


CLIP = {"vv": [-30.0, 0.0], "vh": [-35.0, 0.0]}


def _prep():
    return {"clip": "narrow", "clip_range_db": CLIP, "median_window": 5}


def test_build_method_b1(mod):
    method, clip, med = mod.build_method("b1", {"threshold_db": -16.0, "preprocessing": _prep()}, cache=None)
    assert isinstance(method, FixedThresholdVV) and method.threshold_db == -16.0
    assert clip == CLIP and med == 5


def test_build_method_b2_band_from_variant(mod):
    m_vv, _, _ = mod.build_method("b2_vv", {"preprocessing": _prep()}, cache=None)
    m_vh, _, _ = mod.build_method("b2_vh", {"preprocessing": _prep()}, cache=None)
    assert isinstance(m_vv, OtsuThreshold) and m_vv.band == "vv"
    assert isinstance(m_vh, OtsuThreshold) and m_vh.band == "vh"


def test_build_method_m1_and_its_guarded_variant(mod):
    rec = {"k": 3, "n_init": 10, "seed": 42, "max_iter": 300, "preprocessing": _prep()}
    plain, _, _ = mod.build_method("m1", rec, cache=None)
    assert isinstance(plain, PixelKMeans) and plain.k == 3 and plain.n_init == 10

    guarded_rec = dict(rec, abstention_guard={"ceiling_db": -15.0})
    guarded, _, _ = mod.build_method("m1g", guarded_rec, cache=None)
    assert isinstance(guarded, AbstainingMethod) and guarded.ceiling_db == -15.0
    assert isinstance(guarded.base, PixelKMeans)


def test_build_method_m2_and_its_guarded_variant(mod):
    rec = {"k": 4, "n_segments": 1000, "compactness": 0.2, "features": "vv_vh", "seed": 42,
          "n_init": 10, "max_iter": 300, "slic_max_num_iter": 10, "preprocessing": _prep()}
    plain, clip, med = mod.build_method("m2", rec, cache="CACHE")
    assert isinstance(plain, SlicKMeans)
    assert (plain.k, plain.n_segments, plain.compactness, plain.features) == (4, 1000, 0.2, "vv_vh")
    assert plain.cache == "CACHE" and clip == CLIP and med == 5

    guarded, _, _ = mod.build_method("m2g", dict(rec, abstention_guard={"ceiling_db": -12.0}), cache="CACHE")
    assert isinstance(guarded, AbstainingMethod) and isinstance(guarded.base, SlicKMeans)


def test_build_method_rejects_unknown_variant(mod):
    with pytest.raises(ValueError):
        mod.build_method("not_a_variant", {"preprocessing": _prep()}, cache=None)


def test_check_prerequisites_refuses_when_frozen_files_missing(mod, tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "FROZEN_DIR", tmp_path / "frozen")
    with pytest.raises(SystemExit, match="frozen configuration file"):
        mod.check_prerequisites(["OnlyEvent"])


def test_check_prerequisites_passes_when_every_file_exists(mod, tmp_path, monkeypatch):
    frozen = tmp_path / "frozen"
    monkeypatch.setattr(mod, "FROZEN_DIR", frozen)
    for crit in mod.CRITERIA:
        (frozen / crit).mkdir(parents=True)
        for name in mod.all_tuning_set_names(["E1", "E2"]):
            (frozen / crit / f"{name.replace(':', '_')}.yaml").write_text("selections: {}\n")
    mod.check_prerequisites(["E1", "E2"])  # must not raise


def test_lock_round_trip_refuses_a_second_run(mod, tmp_path, monkeypatch):
    frozen = tmp_path / "frozen"
    (frozen / "primary").mkdir(parents=True)
    (frozen / "primary" / "x.yaml").write_text("a: 1\n")
    lock = tmp_path / "lock.json"
    monkeypatch.setattr(mod, "FROZEN_DIR", frozen)
    monkeypatch.setattr(mod, "LOCK_PATH", lock)
    mod.check_lock()  # no lock yet: passes
    mod.write_lock("deadbeef")
    assert lock.exists()
    written = json.loads(lock.read_text())
    assert written["frozen_sha256"] == mod.frozen_hash() and written["git_head"] == "deadbeef"
    with pytest.raises(SystemExit, match="already ran"):
        mod.check_lock()


def test_summarize_flat_hand_computed(mod):
    counts = [c(2, 1, 0, 5), c(0, 0, 2, 6), c(0, 0, 0, 8)]  # third chip flood-free, no alarm
    out = mod.summarize_flat(counts, n_res=50, seed=0, confidence=0.95, label="x")
    assert out["n_chips"] == 3
    assert out["pooled"]["tp"] == 2 and out["pooled"]["fp"] == 1 and out["pooled"]["fn"] == 2
    assert out["pooled"]["iou"] == pytest.approx(2 / 5)
    # chip 1: IoU 2/3 (tp=2,fp=1,fn=0); chip 2: IoU 0 (tp=0,fp=0,fn=2); chip 3 excluded (no truth flood)
    assert out["mean_per_chip_iou_bootstrap"]["point"] == pytest.approx((2 / 3 + 0.0) / 2)
    assert out["flood_free"]["n_chips"] == 1 and out["flood_free"]["frac_chips_with_alarm"] == 0.0


def test_summarize_loeo_macro_average_is_unweighted_over_events(mod):
    # Event A: two chips pooling to IoU 1.0; event B: one chip with IoU 0.0. Macro average of per-event
    # pooled IoU is (1.0 + 0.0) / 2 = 0.5, unlike the flat pooled IoU which weights by pixel count.
    per_event = {"A": [c(2, 0, 0, 8), c(3, 0, 0, 7)], "B": [c(0, 5, 0, 5)]}
    out = mod.summarize_loeo(per_event, n_res=50, seed=0, confidence=0.95)
    assert out["macro_average_pooled_iou_two_level_bootstrap"]["point"] == pytest.approx(0.5)
    assert set(out["per_event"]) == {"A", "B"}
    assert out["per_event"]["A"]["n_chips"] == 2 and out["per_event"]["B"]["n_chips"] == 1


def test_write_csv_produces_one_header_and_expected_row_count(mod, tmp_path, monkeypatch):
    out_csv = tmp_path / "out.csv"
    monkeypatch.setattr(mod, "OUT_CSV", out_csv)
    flat = mod.summarize_flat([c(1, 0, 0, 9)], 20, 0, 0.95, "x")
    loeo = mod.summarize_loeo({"E1": [c(1, 0, 0, 9)]}, 20, 0, 0.95)
    results = {crit: {variant: {"loeo": {m: loeo for m in ("flood_only", "all_water")},
                                "official_valid_frozen_config": {"test": {m: flat for m in ("flood_only", "all_water")},
                                                                 "bolivia": {m: flat for m in ("flood_only", "all_water")}}}
                      for variant in mod.VARIANTS} for crit in mod.CRITERIA}
    mod.write_csv(results)
    lines = out_csv.read_text().strip().split("\n")
    assert lines[0].startswith("criterion,variant,evaluation_set,metric")
    # per (criterion, variant): 2 loeo_pooled rows (2 metrics) + 2 macro rows + 2 test rows + 2 bolivia rows = 8
    assert len(lines) - 1 == len(mod.CRITERIA) * len(mod.VARIANTS) * 8
