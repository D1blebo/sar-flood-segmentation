"""
Stage 3 tuning driver (Stage 1 of the search plan, protocol A6.4).

  PYTHONPATH=. python scripts/03_tune.py compute > results/tuning/stage1_compute.log 2>&1
      Fill the per-(chip, preprocessing) count cache. Resumable: re-running skips finished units.
      The log contains progress and timing only, no scores.

  PYTHONPATH=. python scripts/03_tune.py rank > results/tuning/stage1_report.txt
      Rank preprocessing options per tuning set and preview the stage-2 union and cost. Prints tuning-set
      aggregates only (never a metric for a held-out chip), then stops for approval before stage 2.
"""

import hashlib
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

from src.config import REPO_ROOT, load_config
from src.parallel import stream_map
from src.ranking import (FLOOD, VARIANTS, check_consistency, criterion, load_units, measured_speedup,
                         project_stage2_cost, rank_options, stage2_union, tuning_sets)
from src.stage1 import (ceiling_key, eligible_chips, load_or_build_chip_index, preprocessing_options,
                        stage1_params, stage1_unit, unit_path)

# variant name -> (family in the count cache, guarded?)
VARIANT_FAMILY = {"b1": ("b1", False), "b2_vv": ("b2_vv", False), "b2_vh": ("b2_vh", False),
                  "b2g_vv": ("b2_vv", True), "b2g_vh": ("b2_vh", True), "m1": ("m1", False),
                  "m1g": ("m1", True), "m2": ("m2", False), "m2g": ("m2", True)}


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()


def compute():
    cfg = load_config()
    params, preps = stage1_params(cfg), preprocessing_options(cfg)
    sha = hashlib.sha256((REPO_ROOT / "configs" / "config.yaml").read_bytes()).hexdigest()
    print(f"STAGE 1 compute  {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    print(f"config sha256 {sha}", flush=True)
    print(f"git HEAD {git('rev-parse', 'HEAD')[:12]}; tracked files modified since HEAD: "
          f"{git('diff', '--name-only', 'HEAD') or 'none'}", flush=True)
    index = load_or_build_chip_index(cfg)
    chips = eligible_chips(index)
    print(f"chips in the index: {len(index)}; eligible (>= 1 valid pixel): {len(chips)}; "
          f"preprocessing options: {len(preps)}", flush=True)
    units = [f"{c}|{p['name']}" for c in chips for p in preps]
    todo = [u for u in units if not unit_path(params["unit_dir"], *u.split("|", 1)).exists()]
    print(f"units: {len(units)} total, {len(units) - len(todo)} already done, {len(todo)} to run; "
          f"{cfg['compute']['n_jobs']} workers", flush=True)

    t0, done, errors, busy = time.perf_counter(), 0, [], 0.0
    log_every = 100
    for unit, status, secs in stream_map(stage1_unit, todo, cfg["compute"]["n_jobs"], chunksize=2,
                                         params=params, preps=preps):
        done += 1
        busy += secs
        if status.startswith("error"):
            errors.append((unit, status))
            print(f"  ERROR {unit}: {status}", flush=True)
        if done % log_every == 0 or done == len(todo):
            wall = time.perf_counter() - t0
            rate = done / wall
            print(f"  {done}/{len(todo)} units, {wall / 60:.1f} min elapsed, {rate:.2f} units/s, "
                  f"eta {(len(todo) - done) / rate / 60:.1f} min", flush=True)
    wall = time.perf_counter() - t0
    print(f"\nfinished: {done - len(errors)} done, {len(errors)} errors; wall {wall / 60:.1f} min; "
          f"sum of unit times {busy / 60:.1f} min -> parallel speedup {busy / wall:.2f}x "
          f"(measured on {done} units)", flush=True)
    if errors:
        print("re-run this command to retry the failed units", flush=True)
        sys.exit(1)


def fmt(r, guarded):
    extra = f" ceil {r['ceiling']}" if guarded else ""
    cfg = f" thr {r['cfg']}" if r["cfg"] != "nominal" else ""
    return f"{r['prep']}{cfg}{extra} ({r['mean']:.3f})"


def rank(dry=None):
    """dry=N: use only the first N chips whose units are all done, and write to a temp dir (for testing)."""
    cfg = load_config()
    preps = [p["name"] for p in preprocessing_options(cfg)]
    sha = hashlib.sha256((REPO_ROOT / "configs" / "config.yaml").read_bytes()).hexdigest()
    index = load_or_build_chip_index(cfg)
    chips = eligible_chips(index)
    params = stage1_params(cfg)
    if dry:
        chips = [c for c in chips if all(unit_path(params['unit_dir'], c, p).exists() for p in preps)][:dry]
    events = [index[c]["event"] for c in chips]
    splits = [index[c]["split"] for c in chips]
    counts, seconds = load_units(params["unit_dir"], chips, preps)
    check_consistency(counts)
    sets = tuning_sets(events, splits)
    ceilings = [ceiling_key(c) for c in params["ceilings"]]
    print("STAGE 1 RANKING REPORT (tuning-set aggregates only; no held-out chip is scored here)")
    print(f"config sha256 {sha}; git HEAD {git('rev-parse', 'HEAD')[:12]}; tracked files modified: "
          f"{git('diff', '--name-only', 'HEAD') or 'none'}")
    print(f"units loaded: {len(chips)} chips x {len(preps)} preprocessing options; truth/domain consistency check passed")
    print("criterion = mean per-chip flood-only IoU over the tuning set's chips with flood; guarded variants are "
          "ranked by their best (configuration, ceiling); plain variants by unguarded scores only (A3.1)\n")
    ref = next(iter(counts.values()))                       # truth counts do not depend on the candidate
    has_flood = (ref[:, FLOOD, 0] + ref[:, FLOOD, 2]) > 0
    print("tuning sets (chips in the tuning set / of which have flood-only truth):")
    for name, mask in sets.items():
        print(f"  {name:22s} {int(mask.sum()):3d} / {int((mask & has_flood).sum()):3d}")

    rankings = {name: {} for name in sets}
    for name, mask in sets.items():
        for variant in VARIANTS:
            family, guarded = VARIANT_FAMILY[variant]
            rankings[name][variant] = rank_options(counts, family, mask, guarded, preps, ceilings)

    for variant in VARIANTS:
        _, guarded = VARIANT_FAMILY[variant]
        print(f"\n=== {variant}: best two preprocessing options per tuning set (criterion on that tuning set) ===")
        for name in sets:
            r = rankings[name][variant]
            print(f"  {name:22s} 1. {fmt(r[0], guarded):48s} 2. {fmt(r[1], guarded)}")

    unions = {}
    print("\n=== STAGE-2 UNION (A5.3): top 2 per tuning set, at most 6 options, ranked by number of tuning sets choosing them ===")
    for variant in ("m1", "m1g", "m2", "m2g"):
        u = stage2_union({n: [r["prep"] for r in rankings[n][variant]] for n in sets}, preps)
        unions[variant] = u
        print(f"\n{variant}: {u['distinct_top2']} distinct options appear in some tuning set's top two; union keeps {len(u['union'])}")
        for p in sorted(u["chosen_by"], key=lambda p: (-u["chosen_by"][p], u["mean_rank"][p])):
            print(f"   {p:24s} chosen by {u['chosen_by'][p]:2d} of {len(sets)} sets, mean rank {u['mean_rank'][p]:5.2f}"
                  f"{'   KEPT' if p in u['union'] else '   dropped (cap)'}")
        moved = [n for n in sets if set(u["assigned"][n]) != {r["prep"] for r in rankings[n][variant][:2]}]
        print(f"   tuning sets that use the fallback (own top two not both in the union): {len(moved)} of {len(sets)}"
              + (f" ({', '.join(moved)})" if moved else ""))

    speed = measured_speedup(REPO_ROOT / cfg["paths"]["tuning_results_dir"] / "stage1_compute.log")
    cost = project_stage2_cost({v: unions[v]["union"] for v in unions}, seconds, len(chips), speed or 2.0)
    print("\n=== MEASURED STAGE-1 TIMING AND PROJECTED STAGE-2 COST ===")
    print("mean seconds per unit (serial): " + ", ".join(f"{k} {np.mean(v):.2f}" for k, v in seconds.items())
          + f"; total {sum(np.mean(v) for v in seconds.values()):.2f}")
    print(f"parallel speedup measured on the stage-1 run: {speed if speed else 'not found in the log; 2.0 assumed'}")
    print(f"stage 2 needs {cost['m2_options']} distinct M2 options and {cost['m1_options']} distinct M1 options "
          f"(plain and guarded share an option when they coincide)")
    print(f"projected stage-2 time: {cost['serial_h']:.1f} h serial, "
          f"{cost['wall_h']:.1f} h at the speedup above (M1 stage 2 is ASSUMED to cost 30% of a stage-1 M1 unit; "
          f"M2: 15 new (n_segments, compactness) configurations per option)")
    print("\nSTOP: stage 2 does not start until the project owner approves this union and cost.")

    out = {"config_sha256": sha, "tuning_sets": {n: int(m.sum()) for n, m in sets.items()},
           "rankings": rankings, "unions": unions, "cost": cost}
    out_dir = Path(tempfile.mkdtemp(prefix="rank_dry_")) if dry else REPO_ROOT / cfg["paths"]["tuning_results_dir"]
    (out_dir / "stage1_rankings.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "compute":
        compute()
    elif cmd == "rank":
        rank(dry=int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[2] == "--dry" else None)
    else:
        sys.exit("usage: 03_tune.py compute|rank")
