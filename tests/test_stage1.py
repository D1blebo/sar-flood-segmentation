"""Stage 1 unit worker: correct counts, resumable, atomic, and errors do not kill a run."""

import json

from src.config import load_config
from src.stage1 import compute_stage1_counts, preprocessing_options, stage1_unit, unit_path


def prep_by_name(preps, name):
    return next(p for p in preps if p["name"] == name)


def test_there_are_sixteen_preprocessing_options_with_canonical_names():
    preps = preprocessing_options(load_config())
    assert len(preps) == 16 and preps[0]["name"] == "clip=none,median=0" and preps[-1]["name"] == "clip=narrow,median=7"
    assert len({p["name"] for p in preps}) == 16


def test_unit_counts_match_the_hand_computed_toy_values(fake_dataset, toy_chip):
    params, preps = fake_dataset
    out = compute_stage1_counts(toy_chip, prep_by_name(preps, "clip=none,median=0"), params)
    # B1 at -17 dB separates the toy water (~ -24) from background (~ -10) perfectly (see test_methods)
    assert out["b1"]["-17"] == [[375, 0, 0, 3304, 3679], [500, 0, 0, 3304, 3804]]  # flood_only, all_water
    for key in ("b2_vv", "b2_vh", "m1", "m2"):
        assert set(out[key]) == {"plain", "-18", "-15", "-12"}                     # plain + every ceiling
    assert out["b2_vv"]["plain"][0][:3] == [375, 0, 0]                              # Otsu is perfect here too
    assert out["m1"]["-18"] == out["m1"]["plain"]                                   # water is ~ -24 dB: guard keeps it
    assert set(out["seconds"]) == {"preprocess", "b1", "b2", "m1", "m2"}


def test_b1_thresholds_at_or_below_the_clip_floor_are_not_computed(fake_dataset, toy_chip):
    params, preps = fake_dataset
    narrow = compute_stage1_counts(toy_chip, prep_by_name(preps, "clip=narrow,median=0"), params)["b1"]
    assert "-25" not in narrow and "-24" in narrow and len(narrow) == 17           # clip floor is -25 dB
    assert len(compute_stage1_counts(toy_chip, prep_by_name(preps, "clip=none,median=0"), params)["b1"]) == 23


def test_unit_is_deterministic(fake_dataset, toy_chip):
    params, preps = fake_dataset
    prep = prep_by_name(preps, "clip=medium,median=3")
    a = compute_stage1_counts(toy_chip, prep, params)
    b = compute_stage1_counts(toy_chip, prep, params)
    a.pop("seconds"), b.pop("seconds")
    assert a == b


def test_worker_writes_atomically_and_resumes(fake_dataset):
    params, preps = fake_dataset
    unit = "Toy_1|clip=none,median=0"
    assert stage1_unit(unit, params, preps)[1] == "done"
    path = unit_path(params["unit_dir"], "Toy_1", "clip=none,median=0")
    assert path.exists() and json.loads(path.read_text())["chip"] == "Toy_1"
    assert not list(path.parent.glob("*.tmp"))                                     # no half-written leftovers
    before = path.stat().st_mtime_ns
    assert stage1_unit(unit, params, preps)[1] == "skipped"                        # resumable
    assert path.stat().st_mtime_ns == before                                       # and not recomputed


def test_a_bad_unit_returns_an_error_instead_of_raising(fake_dataset):
    params, preps = fake_dataset
    unit, status, _ = stage1_unit("Missing_9|clip=none,median=0", params, preps)
    assert status.startswith("error") and unit == "Missing_9|clip=none,median=0"
    assert not unit_path(params["unit_dir"], "Missing_9", "clip=none,median=0").exists()


def test_each_ceiling_is_stored_under_its_own_key(fake_dataset, toy_chip):
    """Water at about -14 dB: -14 is above the ceilings -18 and -15 (abstain) and below -12 (keep)."""
    params, preps = fake_dataset
    chip = dict(toy_chip)
    vv = toy_chip["vv"].copy()
    vv[10:30, 10:35] += 10.0                                # dark block now about -14 dB, background still -10
    chip["vv"] = vv
    out = compute_stage1_counts(chip, prep_by_name(preps, "clip=none,median=0"), params)
    plain_tp = out["m1"]["plain"][0][0]
    assert plain_tp > 0                                     # the plain rule finds the block
    assert out["m1"]["-18"][0][0] == 0 and out["m1"]["-15"][0][0] == 0   # -14 is not below -18 or -15: abstain
    assert out["m1"]["-12"][0][0] == plain_tp               # -14 is below -12: keep
