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
    p["stage3_dir"] = str(REPO_ROOT / cfg["paths"]["tuning_cache_dir"] / "stage3")
    p["s3"] = {"combos": cfg["search_space"]["m2_slic_kmeans"]["allowed_combinations"],
               "n_init": cfg["search_space"]["m2_slic_kmeans"]["n_init"]}
    p["ext_grid"] = {}   # filled by the extension driver: {preprocessing option: [[n_segments, compactness], ...]}
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
    elif kind == "m2" or kind.startswith("m2x"):
        # 'm2' = the base grid (nominal excluded); 'm2xR' = extension round R, whose configurations are given per option
        p, cache, configs = params["s2_m2"], SegmentationCache(params["slic_cache_dir"]), {}
        grid = p["grid"] if kind == "m2" else params["ext_grid"][prep["name"]]
        for n, c in grid:
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


# ---- Stage 3 (protocol A9.1): the allowed (features, k) combinations at a Stage 2 choice -------------------------------------

def stage3_path(stage3_dir, chip_id, prep_name_, n_segments, compactness):
    return Path(stage3_dir) / chip_id / f"{prep_name_}__{config_key(n_segments, compactness)}.json"


def combo_key(features, k):
    return f"{features}|{k}"


def compute_stage3(chip, prep, n_segments, compactness, params):
    """Counts and mean VV of every allowed (features, k) combination for one chip at one (option, n_segments, compactness)."""
    clip = params["clip_options"][prep["clip"]]
    t0 = time.perf_counter()
    vv, vh = preprocess(chip["vv"], chip["vh"], clip, prep["median"])
    image_valid = image_valid_mask(chip["vv"], chip["vh"])
    key = f"{chip['id']}|{prep['name']}"
    cache = SegmentationCache(params["slic_cache_dir"])
    combos = {}
    for features, k in params["s3"]["combos"]:
        m2 = SlicKMeans(k, n_segments, compactness, features, params["seed"], n_init=params["s3"]["n_init"],
                        max_iter=params["max_iter"], slic_max_iter=params["slic_max_iter"], cache=cache)
        combos[combo_key(features, k)] = _entry(evaluate_prepared(m2, vv, vh, image_valid, chip["label"], chip["jrc"], key))
    return {"version": UNIT_VERSION, "chip": chip["id"], "prep": prep["name"], "n_segments": n_segments,
            "compactness": compactness, "configs": combos, "seconds": time.perf_counter() - t0}


def stage3_unit(unit, params, preps):
    """Worker: unit is 'CHIP|PREPNAME|N|C'. Same contract as stage2_unit."""
    t0 = time.perf_counter()
    try:
        chip_id, pname, n, c = unit.split("|")
        n, c = int(n), float(c)
        path = stage3_path(params["stage3_dir"], chip_id, pname, n, c)
        if path.exists():
            return unit, "skipped", 0.0
        prep = next(p for p in preps if p["name"] == pname)
        content = compute_stage3(read_chip(chip_id, params["data_dir"]), prep, n, c, params)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(content, f)
        os.replace(tmp, path)
        return unit, "done", time.perf_counter() - t0
    except Exception as exc:  # noqa: BLE001
        return unit, f"error: {type(exc).__name__}: {exc}", time.perf_counter() - t0
