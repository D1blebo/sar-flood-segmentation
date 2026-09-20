"""
Stage 1 of the search plan (protocol A6.4): per-chip confusion counts for every method at every
preprocessing option, cached on disk so that every tuning set can rank options by summing a subset.

One UNIT is one (chip, preprocessing option). Computing a unit runs, on that chip after that preprocessing:
  B1 at every threshold valid under the clip; B2 on VV and on VH; M1 (nominal); M2 (nominal),
with B2, M1 and M2 each stored plain and at every abstention ceiling. Counts are stored for both metrics.

Resumable: a unit is written atomically (temp file, then rename) and skipped if its file exists.
Reproducible: workers receive all parameters frozen at launch (`stage1_params`), never re-read the config.
"""

import json
import os
import tempfile
import time
from pathlib import Path

import numpy as np

from src.config import REPO_ROOT, b1_threshold_grid, b1_thresholds_above_floor, prep_name
from src.evaluate import evaluate_prepared
from src.io import image_valid_mask, read_chip
from src.methods import FixedThresholdVV, OtsuThreshold, PixelKMeans, SlicKMeans
from src.metrics import MODES
from src.preprocess import preprocess
from src.slic_cache import SegmentationCache

UNIT_VERSION = 1
COUNT_KEYS = ("tp", "fp", "fn", "tn", "domain")


def preprocessing_options(cfg, extra_medians=()):
    """
    The 16 (clip, median) options in config order, as dicts with their canonical name, followed by the
    grid-edge extension options (protocol A7.4): every clip at each median window in `extra_medians`.
    """
    clips = cfg["preprocess"]["clip_options"]
    base = [{"name": prep_name(clip, med), "clip": clip, "median": med}
            for clip in clips for med in cfg["preprocess"]["median_window_options"]]
    extra = [{"name": prep_name(clip, med), "clip": clip, "median": med} for med in extra_medians for clip in clips]
    return base + extra


def stage1_params(cfg):
    """Everything a worker needs, frozen at launch (plain, picklable)."""
    plan = cfg["search_plan"]["stage1"]
    m1k = plan["m1"]["k"]
    return {
        "data_dir": str(REPO_ROOT / cfg["paths"]["data_dir"]),
        "slic_cache_dir": str(REPO_ROOT / cfg["paths"]["cache_dir"] / "slic"),
        "unit_dir": str(REPO_ROOT / cfg["paths"]["tuning_cache_dir"] / "stage1"),
        "seed": cfg["seed"],
        "max_iter": cfg["kmeans"]["max_iter"],
        "slic_max_iter": cfg["slic"]["max_num_iter"],
        "clip_options": cfg["preprocess"]["clip_options"],
        "b1_grid": b1_threshold_grid(cfg),
        "ceilings": cfg["search_space"]["abstention_guard"]["ceilings_db"],
        "m1": {"k": m1k, "n_init": cfg["search_space"]["m1_pixel_kmeans"]["n_init_by_k"][m1k]},
        "m2": {"k": plan["m2"]["k"], "n_segments": plan["m2"]["n_segments"],
               "compactness": plan["m2"]["compactness"], "features": plan["m2"]["features"],
               "n_init": cfg["search_space"]["m2_slic_kmeans"]["n_init"]},
    }


def ceiling_key(ceiling):
    return f"{ceiling:g}"


def _enc(by_mode):
    """{'flood_only': counts, 'all_water': counts} -> [[tp, fp, fn, tn, domain], [...]] in MODES order."""
    return [[by_mode[m][k] for k in COUNT_KEYS] for m in MODES]


def _enc_with_ceilings(res, ceilings):
    """Plain counts plus one entry per ceiling, from an evaluate_prepared result."""
    out = {"plain": _enc(res)}
    for c in ceilings:
        out[ceiling_key(c)] = _enc(res["guarded"][c])
    return out


def compute_stage1_counts(chip, prep, params):
    """The content of one unit for an already-loaded chip. `prep` is one preprocessing_options entry."""
    clip = params["clip_options"][prep["clip"]]
    seconds = {}
    t0 = time.perf_counter()
    vv, vh = preprocess(chip["vv"], chip["vh"], clip, prep["median"])
    image_valid = image_valid_mask(chip["vv"], chip["vh"])
    seconds["preprocess"] = time.perf_counter() - t0
    label, jrc, key = chip["label"], chip["jrc"], f"{chip['id']}|{prep['name']}"
    ceilings = params["ceilings"]

    t0 = time.perf_counter()
    b1 = {}
    for thr in b1_thresholds_above_floor(params["b1_grid"], clip):
        b1[f"{thr:g}"] = _enc(evaluate_prepared(FixedThresholdVV(thr), vv, vh, image_valid, label, jrc))
    seconds["b1"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    out = {"b1": b1}
    for band in ("vv", "vh"):
        res = evaluate_prepared(OtsuThreshold(band), vv, vh, image_valid, label, jrc, ceilings_db=ceilings)
        out[f"b2_{band}"] = _enc_with_ceilings(res, ceilings)
    seconds["b2"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    m1 = PixelKMeans(params["m1"]["k"], params["seed"], n_init=params["m1"]["n_init"], max_iter=params["max_iter"])
    out["m1"] = _enc_with_ceilings(
        evaluate_prepared(m1, vv, vh, image_valid, label, jrc, key, ceilings_db=ceilings), ceilings)
    seconds["m1"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    p2 = params["m2"]
    m2 = SlicKMeans(p2["k"], p2["n_segments"], p2["compactness"], p2["features"], params["seed"],
                    n_init=p2["n_init"], max_iter=params["max_iter"], slic_max_iter=params["slic_max_iter"],
                    cache=SegmentationCache(params["slic_cache_dir"]))
    out["m2"] = _enc_with_ceilings(
        evaluate_prepared(m2, vv, vh, image_valid, label, jrc, key, ceilings_db=ceilings), ceilings)
    seconds["m2"] = time.perf_counter() - t0

    return {"version": UNIT_VERSION, "chip": chip["id"], "prep": prep["name"], "seconds": seconds, **out}


def unit_path(unit_dir, chip_id, prep_name_):
    return Path(unit_dir) / chip_id / f"{prep_name_}.json"


def stage1_unit(unit, params, preps):
    """
    Worker: unit is 'CHIP|PREPNAME'. Returns (unit, status, seconds) where status is 'done', 'skipped'
    or 'error: ...'. Never raises, so one bad unit cannot kill a long run; re-running retries it.
    """
    t0 = time.perf_counter()
    try:
        chip_id, pname = unit.split("|", 1)
        path = unit_path(params["unit_dir"], chip_id, pname)
        if path.exists():
            return unit, "skipped", 0.0
        prep = next(p for p in preps if p["name"] == pname)
        content = compute_stage1_counts(read_chip(chip_id, params["data_dir"]), prep, params)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(content, f)
        os.replace(tmp, path)  # atomic: an interrupted run never leaves a half-written unit
        return unit, "done", time.perf_counter() - t0
    except Exception as exc:  # noqa: BLE001 - reported, not hidden
        return unit, f"error: {type(exc).__name__}: {exc}", time.perf_counter() - t0


def build_chip_index(cfg):
    """
    {chip_id: {event, split, domain_all, domain_flood}} for all 446 chips: which official split and
    event a chip is in, and how many pixels are both image-valid and label-valid (all-water domain) or
    also not permanent water (flood-only domain). Label FACTS only; no method is scored here.
    """
    from src.metrics import MODES as _modes, evaluation_domain_and_truth
    from src.splits import chip_event, load_official_splits

    ddir = REPO_ROOT / cfg["paths"]["data_dir"]
    index = {}
    for split, ids in load_official_splits(ddir).items():
        for chip_id in ids:
            chip = read_chip(chip_id, ddir)
            valid = image_valid_mask(chip["vv"], chip["vh"])
            dom = {m: int(evaluation_domain_and_truth(valid, chip["label"], chip["jrc"], m)[0].sum())
                   for m in _modes}
            index[chip_id] = {"event": chip_event(chip_id), "split": split,
                              "domain_all": dom["all_water"], "domain_flood": dom["flood_only"]}
    return index


def load_or_build_chip_index(cfg):
    path = REPO_ROOT / cfg["paths"]["tuning_cache_dir"] / "chip_index.json"
    if path.exists():
        return json.loads(path.read_text())
    index = build_chip_index(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index))
    return index


def eligible_chips(index):
    """Chips with at least one valid pixel; the rest are excluded from every metric (protocol section 2)."""
    return sorted(c for c, v in index.items() if v["domain_all"] > 0)
