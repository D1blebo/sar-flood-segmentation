"""
Stage 2 of the search plan (protocol A8.4): on the preprocessing options of the union,
  * M1 at k = 2 (n_init 3), and
  * M2 at (`vv_vh`, k = 2, n_init 10) over the (n_segments, compactness) grid except the nominal setting, which stage 1 did.
Each configuration is stored with its plain counts and the predicted region's mean VV, so the guarded variants at any ceiling
are derived later (protocol A8.3). One file per (kind, chip, preprocessing option); resumable, atomic, frozen parameters.
"""

import json
import os
import tempfile
import time
from pathlib import Path

from src.config import REPO_ROOT
from src.evaluate import evaluate_prepared
from src.io import image_valid_mask, read_chip
from src.methods import PixelKMeans, SlicKMeans
from src.preprocess import preprocess
from src.slic_cache import SegmentationCache
from src.stage1 import UNIT_VERSION, _enc, stage1_params

KINDS = ("m1", "m2")


def config_key(n_segments, compactness):
    return f"n{n_segments}_c{compactness:g}"


def stage2_params(cfg):
    """Frozen parameters for the stage-2 workers (plain, picklable)."""
    p = dict(stage1_params(cfg))
    plan = cfg["search_plan"]["stage2"]
    nominal = cfg["search_plan"]["stage1"]["m2"]
    p["stage2_dir"] = str(REPO_ROOT / cfg["paths"]["tuning_cache_dir"] / "stage2")
    k1 = plan["m1"]["k"][0]
    p["s2_m1"] = {"k": k1, "n_init": cfg["search_space"]["m1_pixel_kmeans"]["n_init_by_k"][k1]}
    p["s2_m2"] = {"k": plan["m2"]["k"], "features": plan["m2"]["features"],
                  "n_init": cfg["search_space"]["m2_slic_kmeans"]["n_init"],
                  "grid": [[n, c] for n in plan["m2"]["n_segments"] for c in plan["m2"]["compactness"]
                           if (n, c) != (nominal["n_segments"], nominal["compactness"])]}
    return p


def stage2_path(stage2_dir, kind, chip_id, prep_name_):
    return Path(stage2_dir) / kind / chip_id / f"{prep_name_}.json"


def _entry(res):
    return {"plain": _enc(res), "mv": res["water_mean_vv"]}


def compute_stage2(chip, prep, params, kind):
    """The content of one stage-2 unit for an already-loaded chip."""
    clip = params["clip_options"][prep["clip"]]
    t0 = time.perf_counter()
    vv, vh = preprocess(chip["vv"], chip["vh"], clip, prep["median"])
    image_valid = image_valid_mask(chip["vv"], chip["vh"])
    label, jrc, key = chip["label"], chip["jrc"], f"{chip['id']}|{prep['name']}"
    out = {"version": UNIT_VERSION, "kind": kind, "chip": chip["id"], "prep": prep["name"]}
    if kind == "m1":
        p = params["s2_m1"]
        m1 = PixelKMeans(p["k"], params["seed"], n_init=p["n_init"], max_iter=params["max_iter"])
        out["configs"] = {f"k{p['k']}": _entry(evaluate_prepared(m1, vv, vh, image_valid, label, jrc, key))}
    elif kind == "m2":
        p, cache, configs = params["s2_m2"], SegmentationCache(params["slic_cache_dir"]), {}
        for n, c in p["grid"]:
            m2 = SlicKMeans(p["k"], n, c, p["features"], params["seed"], n_init=p["n_init"], max_iter=params["max_iter"],
                            slic_max_iter=params["slic_max_iter"], cache=cache)
            configs[config_key(n, c)] = _entry(evaluate_prepared(m2, vv, vh, image_valid, label, jrc, key))
        out["configs"] = configs
    else:
        raise ValueError(kind)
    out["seconds"] = time.perf_counter() - t0
    return out


def stage2_unit(unit, params, preps):
    """
    Worker: unit is 'KIND|CHIP|PREPNAME'. Returns (unit, status, seconds) with status 'done', 'skipped' or 'error: ...'.
    Never raises (a bad unit is reported and retried by re-running); writes atomically; skips finished units.
    """
    t0 = time.perf_counter()
    try:
        kind, chip_id, pname = unit.split("|", 2)
        path = stage2_path(params["stage2_dir"], kind, chip_id, pname)
        if path.exists():
            return unit, "skipped", 0.0
        prep = next(p for p in preps if p["name"] == pname)
        content = compute_stage2(read_chip(chip_id, params["data_dir"]), prep, params, kind)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(content, f)
        os.replace(tmp, path)
        return unit, "done", time.perf_counter() - t0
    except Exception as exc:  # noqa: BLE001
        return unit, f"error: {type(exc).__name__}: {exc}", time.perf_counter() - t0
