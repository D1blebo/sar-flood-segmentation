"""
Held-out scoring (protocol A3.4, section 6, Amendment 8 A8.1). This is the ONLY script that reads a
metric on a held-out chip.

  PYTHONPATH=. python scripts/04_evaluate.py

Guarantees, each enforced in code (not just documented):
  * Runs once and only after every frozen per-tuning-set configuration exists (11 LOEO folds and the
    official split, both criteria: 24 files under results/frozen/). Refuses to start otherwise.
  * Every frozen configuration is scored on ITS OWN held-out chips only: a LOEO fold's config on that
    event's chips; the official-split ('official_valid') config on the official test split, and
    separately on the held-out Bolivia chips, both with the SAME config (protocol section 6,
    Secondary). No hyperparameter is re-tuned here. A leakage assertion (src/splits.assert_disjoint)
    runs before every evaluation set is scored.
  * Counts are recomputed from the frozen configuration by reading each chip and preprocessing +
    running the method fresh; the tuning cache (data/tuning_cache) is never read here.
  * Writes a lock file (results/tuning/heldout_lock.json, hash of every frozen file's bytes) and
    refuses a second run unless the lock is deleted by hand and the deletion is logged in
    results/evaluation_protocol.md (protocol A3.4).

Reports, for every (criterion, variant): the headline pooled flood-only IoU over all LOEO evaluation
chips with a chip-level bootstrap CI; the mean per-chip flood-only IoU over LOEO chips with flood
(same CI kind); the macro-average over the 11 events, two ways (per-event pooled IoU and per-event
mean-per-chip IoU), each with the two-level event bootstrap CI (A2.2); the flood-free false-positive
fraction; the same four numbers for the secondary all-water metric; a per-event breakdown with its own
within-event bootstrap CI; and the official test / Bolivia results of the 'official_valid' config,
reported separately (not part of the 11-event macro-average, per protocol section 6).

Out of scope for this script (left for a later reporting step): stratification by flood fraction, the
rule-vs-oracle diagnostic, and figures. Every LOEO/official-split number here is flagged as such.
"""

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import yaml

from src.bootstrap import (bootstrap_chip_ci, bootstrap_macro_two_level, mean_per_chip_iou_stat,
                           pooled_iou_stat)
from src.config import REPO_ROOT, load_config
from src.evaluate import evaluate_chip
from src.io import read_chip
from src.methods import AbstainingMethod, FixedThresholdVV, OtsuThreshold, PixelKMeans, SlicKMeans
from src.metrics import MODES, flood_free_summary, pool
from src.metrics import f1 as f1_metric
from src.metrics import iou as iou_metric
from src.metrics import precision as precision_metric
from src.metrics import recall as recall_metric
from src.slic_cache import SegmentationCache
from src.splits import assert_disjoint, chip_event, load_official_splits
from src.stage1 import eligible_chips, load_or_build_chip_index

VARIANTS = ("b1", "b2_vv", "b2_vh", "b2g_vv", "b2g_vh", "m1", "m1g", "m2", "m2g")
CRITERIA = ("primary", "sensitivity")
FROZEN_DIR = REPO_ROOT / "results" / "frozen"
LOCK_PATH = REPO_ROOT / "results" / "tuning" / "heldout_lock.json"
OUT_JSON = REPO_ROOT / "results" / "heldout_results.json"
OUT_CSV = REPO_ROOT / "results" / "heldout_results.csv"


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()


def _rel(path):
    """Path relative to the repo root for display, or the path itself if it lives elsewhere (tests use tmp_path)."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


# ---- prerequisites and the lock (protocol A3.4) --------------------------------------------------

def frozen_path(criterion, tuning_set):
    return FROZEN_DIR / criterion / f"{tuning_set.replace(':', '_')}.yaml"


def all_tuning_set_names(events):
    return [f"loeo:{ev}" for ev in events] + ["official_valid"]


def check_prerequisites(events):
    missing = [_rel(p) for c in CRITERIA for name in all_tuning_set_names(events)
              if not (p := frozen_path(c, name)).exists()]
    if missing:
        sys.exit(f"refusing to start: {len(missing)} frozen configuration file(s) missing (need 24; "
                 f"11 LOEO folds + official_valid, x 2 criteria), e.g. {missing[:3]}")


def frozen_files_sorted():
    return sorted(FROZEN_DIR.rglob("*.yaml"))


def frozen_hash():
    h = hashlib.sha256()
    for f in frozen_files_sorted():
        h.update(f.read_bytes())
    return h.hexdigest()


def check_lock():
    if LOCK_PATH.exists():
        sys.exit(f"refusing to run: held-out scoring already ran (lock at {_rel(LOCK_PATH)}, "
                 f"written {json.loads(LOCK_PATH.read_text()).get('written_at', '?')}). Protocol A3.4: delete the "
                 f"lock by hand and log the deletion (date, reason) in results/evaluation_protocol.md before "
                 f"re-running.")


def write_lock(head):
    LOCK_PATH.write_text(json.dumps({
        "frozen_sha256": frozen_hash(),
        "written_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "git_head": head,
        "frozen_files": [_rel(f) for f in frozen_files_sorted()],
    }, indent=1))


# ---- reconstructing a method from a frozen record -------------------------------------------------

def load_frozen(criterion, tuning_set):
    return yaml.safe_load(frozen_path(criterion, tuning_set).read_text())["selections"]


def build_method(variant, rec, cache):
    """(method, clip_range_db, median_window) from one frozen selection record."""
    if variant == "b1":
        base = FixedThresholdVV(rec["threshold_db"])
    elif variant in ("b2_vv", "b2g_vv"):
        base = OtsuThreshold("vv")
    elif variant in ("b2_vh", "b2g_vh"):
        base = OtsuThreshold("vh")
    elif variant in ("m1", "m1g"):
        base = PixelKMeans(rec["k"], rec["seed"], n_init=rec["n_init"], max_iter=rec["max_iter"])
    elif variant in ("m2", "m2g"):
        base = SlicKMeans(rec["k"], rec["n_segments"], rec["compactness"], rec["features"], rec["seed"],
                          n_init=rec["n_init"], max_iter=rec["max_iter"], slic_max_iter=rec["slic_max_num_iter"],
                          cache=cache)
    else:
        raise ValueError(f"unknown variant {variant!r}")
    guard = rec.get("abstention_guard")
    if guard:
        base = AbstainingMethod(base, guard["ceiling_db"])
    p = rec["preprocessing"]
    return base, p["clip_range_db"], p["median_window"]


# ---- scoring one evaluation set -------------------------------------------------------------------

def score_chips(chip_ids, method, clip, median, ddir):
    """{'flood_only': [counts...], 'all_water': [counts...]} for these chips, method fresh on every chip."""
    out = {m: [] for m in MODES}
    for cid in chip_ids:
        chip = read_chip(cid, ddir)
        res = evaluate_chip(method, chip, clip, median)
        for m in MODES:
            out[m].append(res[m])
    return out


def pooled_metrics(counts_list):
    c = pool(counts_list)
    return {"tp": c["tp"], "fp": c["fp"], "fn": c["fn"], "tn": c["tn"], "domain": c["domain"],
            "iou": iou_metric(c), "f1": f1_metric(c), "precision": precision_metric(c), "recall": recall_metric(c)}


def with_ci(point, ci):
    return {"point": point, "ci95_lo": ci[0], "ci95_hi": ci[1]}


def summarize_flat(counts_list, n_res, seed, confidence, label):
    """Headline + secondary numbers for one flat evaluation set (protocol A8.1 items i and iii; no macro-average -- that needs events)."""
    pooled_pt, pooled_ci = bootstrap_chip_ci(counts_list, pooled_iou_stat, n_res, seed, confidence)
    mean_pt, mean_ci = bootstrap_chip_ci(counts_list, mean_per_chip_iou_stat, n_res, seed, confidence)
    return {
        "label": label, "n_chips": len(counts_list),
        "pooled": pooled_metrics(counts_list),
        "pooled_iou_bootstrap": with_ci(pooled_pt, pooled_ci),
        "mean_per_chip_iou_bootstrap": with_ci(mean_pt, mean_ci),
        "flood_free": flood_free_summary(counts_list),
    }


def summarize_loeo(per_event_counts, n_res, seed, confidence):
    """protocol A8.1: headline pooled IoU + CI, mean-per-chip IoU + CI, both macro-averages + two-level CI, flood-free."""
    flat = [c for cs in per_event_counts.values() for c in cs]
    pooled_pt, pooled_ci = bootstrap_chip_ci(flat, pooled_iou_stat, n_res, seed, confidence)
    mean_pt, mean_ci = bootstrap_chip_ci(flat, mean_per_chip_iou_stat, n_res, seed, confidence)
    macro_pooled_pt, macro_pooled_ci = bootstrap_macro_two_level(per_event_counts, pooled_iou_stat, n_res, seed, confidence)
    macro_mean_pt, macro_mean_ci = bootstrap_macro_two_level(per_event_counts, mean_per_chip_iou_stat, n_res, seed, confidence)
    per_event = {}
    for event, counts in per_event_counts.items():
        e_pooled_pt, e_pooled_ci = bootstrap_chip_ci(counts, pooled_iou_stat, n_res, seed, confidence)
        e_mean_pt, e_mean_ci = bootstrap_chip_ci(counts, mean_per_chip_iou_stat, n_res, seed, confidence)
        per_event[event] = {
            "n_chips": len(counts), "pooled": pooled_metrics(counts),
            "pooled_iou_bootstrap": with_ci(e_pooled_pt, e_pooled_ci),
            "mean_per_chip_iou_bootstrap": with_ci(e_mean_pt, e_mean_ci),
            "flood_free": flood_free_summary(counts),
        }
    return {
        "n_chips": len(flat),
        "pooled": pooled_metrics(flat),
        "headline_pooled_iou_bootstrap": with_ci(pooled_pt, pooled_ci),
        "mean_per_chip_iou_bootstrap": with_ci(mean_pt, mean_ci),
        "macro_average_pooled_iou_two_level_bootstrap": with_ci(macro_pooled_pt, macro_pooled_ci),
        "macro_average_mean_per_chip_iou_two_level_bootstrap": with_ci(macro_mean_pt, macro_mean_ci),
        "flood_free": flood_free_summary(flat),
        "per_event": per_event,
    }


# ---- main -------------------------------------------------------------------------------------

def main():
    cfg = load_config()
    ddir = REPO_ROOT / cfg["paths"]["data_dir"]
    index = load_or_build_chip_index(cfg)
    elig = set(eligible_chips(index))
    events = sorted({v["event"] for v in index.values()})

    check_prerequisites(events)
    check_lock()

    official = load_official_splits(ddir)
    cache = SegmentationCache(str(REPO_ROOT / cfg["paths"]["cache_dir"] / "slic"))
    bcfg = cfg["evaluation"]["bootstrap"]
    n_res, seed, confidence = bcfg["n_resamples"], bcfg["seed"], bcfg["confidence"]
    head = git("rev-parse", "HEAD")

    print(f"HELD-OUT SCORING {time.strftime('%Y-%m-%d %H:%M:%S')}; git HEAD {head[:12]}; "
         f"tracked files modified: {git('diff', '--name-only', 'HEAD') or 'none'}", flush=True)
    print(f"{len(events)} LOEO events, {len(elig)} eligible chips; bootstrap n_resamples={n_res} seed={seed} "
         f"confidence={confidence}", flush=True)

    results = {}
    for crit in CRITERIA:
        results[crit] = {}
        for variant in VARIANTS:
            print(f"  {crit}/{variant}", flush=True)
            per_event_flood, per_event_all = {}, {}
            for event in events:
                rec = load_frozen(crit, f"loeo:{event}")[variant]
                method, clip, med = build_method(variant, rec, cache)
                eval_ids = sorted(c for c in elig if index[c]["event"] == event)
                tuning_ids = sorted(elig - set(eval_ids))
                assert_disjoint(tuning_ids, eval_ids, f"held-out LOEO {event}")
                assert all(chip_event(c) == event for c in eval_ids)
                scored = score_chips(eval_ids, method, clip, med, ddir)
                per_event_flood[event] = scored["flood_only"]
                per_event_all[event] = scored["all_water"]

            rec = load_frozen(crit, "official_valid")[variant]
            method, clip, med = build_method(variant, rec, cache)
            valid_ids = sorted(set(official["valid"]) & elig)
            official_out = {}
            for split_name in ("test", "bolivia"):
                split_ids = sorted(set(official[split_name]) & elig)
                assert_disjoint(valid_ids, split_ids, f"official_valid vs {split_name}")
                scored = score_chips(split_ids, method, clip, med, ddir)
                official_out[split_name] = {
                    "flood_only": summarize_flat(scored["flood_only"], n_res, seed, confidence, f"official_{split_name}"),
                    "all_water": summarize_flat(scored["all_water"], n_res, seed, confidence, f"official_{split_name}"),
                }

            results[crit][variant] = {
                "loeo": {"flood_only": summarize_loeo(per_event_flood, n_res, seed, confidence),
                        "all_water": summarize_loeo(per_event_all, n_res, seed, confidence)},
                "official_valid_frozen_config": official_out,
            }

    OUT_JSON.write_text(json.dumps(results, indent=1))
    write_csv(results)
    write_lock(head)
    print(f"\nwritten: {_rel(OUT_JSON)}, {_rel(OUT_CSV)}, "
         f"{_rel(LOCK_PATH)} (protocol A3.4: a second run is refused until this lock "
         f"is deleted by hand and the deletion is logged)", flush=True)


def write_csv(results):
    rows = ["criterion,variant,evaluation_set,metric,n_chips,pooled_iou,ci95_lo,ci95_hi,mean_per_chip_iou,mean_ci95_lo,mean_ci95_hi"]
    for crit in CRITERIA:
        for variant in VARIANTS:
            r = results[crit][variant]
            for mode in MODES:
                loeo = r["loeo"][mode]
                pb, mb = loeo["headline_pooled_iou_bootstrap"], loeo["mean_per_chip_iou_bootstrap"]
                rows.append(f"{crit},{variant},loeo_pooled_all_chips,{mode},{loeo['n_chips']},"
                           f"{pb['point']:.6g},{pb['ci95_lo']:.6g},{pb['ci95_hi']:.6g},"
                           f"{mb['point']:.6g},{mb['ci95_lo']:.6g},{mb['ci95_hi']:.6g}")
                mp = loeo["macro_average_pooled_iou_two_level_bootstrap"]
                mm = loeo["macro_average_mean_per_chip_iou_two_level_bootstrap"]
                rows.append(f"{crit},{variant},loeo_macro_average_11_events,{mode},11,"
                           f"{mp['point']:.6g},{mp['ci95_lo']:.6g},{mp['ci95_hi']:.6g},"
                           f"{mm['point']:.6g},{mm['ci95_lo']:.6g},{mm['ci95_hi']:.6g}")
            for split_name in ("test", "bolivia"):
                for mode in MODES:
                    s = r["official_valid_frozen_config"][split_name][mode]
                    pb, mb = s["pooled_iou_bootstrap"], s["mean_per_chip_iou_bootstrap"]
                    rows.append(f"{crit},{variant},official_{split_name},{mode},{s['n_chips']},"
                               f"{pb['point']:.6g},{pb['ci95_lo']:.6g},{pb['ci95_hi']:.6g},"
                               f"{mb['point']:.6g},{mb['ci95_lo']:.6g},{mb['ci95_hi']:.6g}")
    OUT_CSV.write_text("\n".join(rows) + "\n")


if __name__ == "__main__":
    main()
