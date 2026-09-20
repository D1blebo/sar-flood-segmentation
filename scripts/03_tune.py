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
import subprocess
import sys
import time
from collections import Counter

from src.config import REPO_ROOT, load_config
from src.parallel import stream_map
from src.stage1 import (eligible_chips, load_or_build_chip_index, preprocessing_options, stage1_params,
                        stage1_unit, unit_path)


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


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "compute":
        compute()
    else:
        sys.exit("usage: 03_tune.py compute|rank")
