"""Stage 2 units: correct counts, nominal excluded, resumable, and the stored mean VV reproduces guarded counts."""

import json

import numpy as np

from src.config import clip_range, load_config
from src.evaluate import evaluate_chip
from src.methods import PixelKMeans, SlicKMeans
from src.ranking import derive_ceiling_counts
from src.stage1 import _enc, preprocessing_options
from src.stage2 import compute_stage2, config_key, stage2_params, stage2_path, stage2_unit


def _params(fake_dataset, tmp_path_factory=None):
    params, _ = fake_dataset
    p = dict(stage2_params(load_config()))
    p.update(data_dir=params["data_dir"], unit_dir=params["unit_dir"], slic_cache_dir=params["slic_cache_dir"],
             stage2_dir=params["unit_dir"] + "_stage2")
    return p


def test_grid_is_fifteen_configs_without_the_nominal_setting():
    p = stage2_params(load_config())
    keys = [config_key(n, c) for n, c in p["s2_m2"]["grid"]]
    assert len(keys) == 15 and len(set(keys)) == 15 and "n500_c0.05" not in keys and "n200_c0.01" in keys
    assert p["s2_m1"] == {"k": 2, "n_init": 3} and p["s2_m2"]["k"] == 2 and p["s2_m2"]["features"] == "vv_vh"
    assert p["s2_m2"]["n_init"] == 10


def test_m1_and_m2_units_match_direct_evaluation_and_reproduce_guarded_counts(fake_dataset, toy_chip):
    p = _params(fake_dataset)
    prep = {"name": "clip=medium,median=3", "clip": "medium", "median": 3}
    clip = clip_range(load_config(), "medium")
    m1 = compute_stage2(toy_chip, prep, p, "m1")["configs"]["k2"]
    direct = evaluate_chip(PixelKMeans(2, p["seed"], n_init=3), toy_chip, clip, 3, ceilings_db=[-18.0, -12.0])
    assert m1["plain"] == _enc(direct)
    plain = np.array([m1["plain"]])
    mv = np.array([np.nan if m1["mv"] is None else m1["mv"]])
    for c in (-18.0, -12.0):                                           # mean VV stored -> guarded counts derived exactly
        assert derive_ceiling_counts(plain, mv, c)[0].tolist() == _enc(direct["guarded"][c])
    m2 = compute_stage2(toy_chip, prep, p, "m2")["configs"]
    assert len(m2) == 15 and "n500_c0.05" not in m2
    d2 = evaluate_chip(SlicKMeans(2, 1000, 0.2, "vv_vh", p["seed"], n_init=10), toy_chip, clip, 3)
    assert m2["n1000_c0.2"]["plain"] == _enc(d2)


def test_stage2_worker_is_resumable_atomic_and_reports_errors(fake_dataset):
    p = _params(fake_dataset)
    preps = preprocessing_options(load_config())
    unit = "m1|Toy_1|clip=none,median=0"
    assert stage2_unit(unit, p, preps)[1] == "done"
    path = stage2_path(p["stage2_dir"], "m1", "Toy_1", "clip=none,median=0")
    assert path.exists() and json.loads(path.read_text())["kind"] == "m1" and not list(path.parent.glob("*.tmp"))
    assert stage2_unit(unit, p, preps)[1] == "skipped"
    assert stage2_unit("m1|Missing_9|clip=none,median=0", p, preps)[1].startswith("error")
    assert stage2_unit("bogus|Toy_1|clip=none,median=0", p, preps)[1].startswith("error")
