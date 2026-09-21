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
from src.ranking import (add_derived_ceilings, load_mv, verify_derived_ceilings, FLOOD, PRIMARY, SENSITIVITY, VARIANTS, available_extra_medians, check_consistency, criterion,
                         extra_prep_names, load_units, measured_speedup, median_of, project_stage2_cost,
                         rank_options, rank_with_extensions, stage2_union, tuning_sets, _key)
from src.stage1 import (ceiling_key, eligible_chips, load_or_build_chip_index, mv_path, mv_unit, preprocessing_options,
                        stage1_params, stage1_unit, unit_path)

# variant name -> (family in the count cache, guarded?)
VARIANT_FAMILY = {"b1": ("b1", False), "b2_vv": ("b2_vv", False), "b2_vh": ("b2_vh", False),
                  "b2g_vv": ("b2_vv", True), "b2g_vh": ("b2_vh", True), "m1": ("m1", False),
                  "m1g": ("m1", True), "m2": ("m2", False), "m2g": ("m2", True)}


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()


def compute(extra_medians=(), kind="counts"):
    """kind='counts': the stage-1 count units; kind='mv': the mean-VV files (protocol A8.3)."""
    worker, path_of = (stage1_unit, unit_path) if kind == "counts" else (mv_unit, mv_path)
    cfg = load_config()
    params, preps = stage1_params(cfg), preprocessing_options(cfg, extra_medians)
    sha = hashlib.sha256((REPO_ROOT / "configs" / "config.yaml").read_bytes()).hexdigest()
    print(f"STAGE 1 compute ({kind})  {time.strftime('%Y-%m-%d %H:%M:%S')}"
          + (f"  (grid-edge extension: median windows {list(extra_medians)})" if extra_medians else ""), flush=True)
    print(f"config sha256 {sha}", flush=True)
    print(f"git HEAD {git('rev-parse', 'HEAD')[:12]}; tracked files modified since HEAD: "
          f"{git('diff', '--name-only', 'HEAD') or 'none'}", flush=True)
    index = load_or_build_chip_index(cfg)
    chips = eligible_chips(index)
    print(f"chips in the index: {len(index)}; eligible (>= 1 valid pixel): {len(chips)}; "
          f"preprocessing options: {len(preps)}", flush=True)
    units = [f"{c}|{p['name']}" for c in chips for p in preps]
    todo = [u for u in units if not path_of(params["unit_dir"], *u.split("|", 1)).exists()]
    print(f"units: {len(units)} total, {len(units) - len(todo)} already done, {len(todo)} to run; "
          f"{cfg['compute']['n_jobs']} workers", flush=True)

    t0, done, errors, busy = time.perf_counter(), 0, [], 0.0
    log_every = 100
    for unit, status, secs in stream_map(worker, todo, cfg["compute"]["n_jobs"], chunksize=2,
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


CRITERION_LABEL = {PRIMARY: "PRIMARY (A7): pooled flood-only IoU over ALL tuning chips",
                   SENSITIVITY: "SENSITIVITY (declared): mean per-chip flood-only IoU over tuning chips with flood"}


def value(r, crit):
    return r["pooled"] if crit == PRIMARY else r["mean"]


def verify_mv():
    """Exactness check (A8.3): counts derived from the stored mean VV must equal the stored counts at -18, -15, -12."""
    cfg = load_config()
    clips = list(cfg["preprocess"]["clip_options"])
    names = [p["name"] for p in preprocessing_options(cfg, [9, 11])]
    index = load_or_build_chip_index(cfg)
    chips = eligible_chips(index)
    params = stage1_params(cfg)
    counts, _ = load_units(params["unit_dir"], chips, names)
    mv = load_mv(params["unit_dir"], chips, names)
    checked, bad = verify_derived_ceilings(counts, mv, params["ceilings"])
    print(f"verify-mv: {len(chips)} chips x {len(names)} options x 4 families x {len(params['ceilings'])} ceilings: "
          f"{checked} (option, family, ceiling) arrays checked, {bad} mismatching")
    print("EXACT" if bad == 0 else "MISMATCH: do not use derived ceilings")
    sys.exit(0 if bad == 0 else 1)


def fmt(r, guarded, crit):
    extra = f" ceil {r['ceiling']}" if guarded else ""
    cfg = f" thr {r['cfg']}" if r["cfg"] != "nominal" else ""
    return f"{r['prep']}{cfg}{extra} ({value(r, crit):.3f})"


def old_stage1_rankings():
    """The Stage 1 rankings committed under the declared criterion (aa6ea93), for the reproduction check."""
    out = git("show", "aa6ea93:results/tuning/stage1_rankings.json")
    return json.loads(out)["rankings"] if out else None


def rank(dry=None):
    """dry=N: use only the first N chips whose units are all done, and write to a temp dir (for testing)."""
    cfg = load_config()
    base = [p["name"] for p in preprocessing_options(cfg)]
    clips = list(cfg["preprocess"]["clip_options"])
    ge = cfg["grid_extension"]
    step, max_ext = ge["step"]["median_window"]["value"], ge["max_extensions_per_parameter"]
    base_max = max(cfg["preprocess"]["median_window_options"])
    sha = hashlib.sha256((REPO_ROOT / "configs" / "config.yaml").read_bytes()).hexdigest()
    index = load_or_build_chip_index(cfg)
    chips = eligible_chips(index)
    params = stage1_params(cfg)
    if dry:
        chips = [c for c in chips if all(unit_path(params['unit_dir'], c, p).exists() for p in base)][:dry]
    events = [index[c]["event"] for c in chips]
    splits = [index[c]["split"] for c in chips]
    extras = [] if dry else available_extra_medians(params["unit_dir"], chips, clips)
    names = base + extra_prep_names(clips, extras)
    counts, seconds = load_units(params["unit_dir"], chips, names)
    check_consistency(counts)
    sets = tuning_sets(events, splits)
    ceilings = [ceiling_key(c) for c in params["ceilings"]]
    ref = next(iter(counts.values()))                       # truth counts do not depend on the candidate
    has_flood = (ref[:, FLOOD, 0] + ref[:, FLOOD, 2]) > 0

    print("STAGE 1 RANKING REPORT, re-ranked under the amended criterion (tuning-set aggregates only; no held-out chip is scored)")
    print(f"config sha256 {sha}; git HEAD {git('rev-parse', 'HEAD')[:12]}; tracked files modified: "
          f"{git('diff', '--name-only', 'HEAD') or 'none'}")
    print(f"units loaded: {len(chips)} chips x {len(names)} preprocessing options (base {len(base)} + extension medians {extras or 'none'}); "
          "truth/domain consistency check passed")
    print("tuning sets (chips in the tuning set / of which have flood-only truth):")
    print("  " + "; ".join(f"{n} {int(m.sum())}/{int((m & has_flood).sum())}" for n, m in sets.items()))

    # reproduction check: declared criterion on the base options must equal the committed Stage 1 numbers
    old = None if dry else old_stage1_rankings()
    if old:
        same = True
        for name, mask in sets.items():
            for variant in VARIANTS:
                family, guarded = VARIANT_FAMILY[variant]
                new = rank_options(counts, family, mask, guarded, base, ceilings, SENSITIVITY)
                same &= [(r["prep"], r["mean"], r["pooled"]) for r in new] == [(r["prep"], r["mean"], r["pooled"]) for r in old[name][variant]]
        print(f"reproduction check: the declared criterion on the 16 base options reproduces the committed Stage 1 rankings "
              f"(aa6ea93) exactly: {same}")

    results = {}
    for crit in (PRIMARY, SENSITIVITY):
        R, info = {n: {} for n in sets}, {n: {} for n in sets}
        for name, mask in sets.items():
            for variant in VARIANTS:
                family, guarded = VARIANT_FAMILY[variant]
                R[name][variant], info[name][variant] = rank_with_extensions(
                    counts, family, mask, guarded, base, clips, ceilings, crit, extras, base_max, step, max_ext)
        results[crit] = {"rankings": R, "extension_info": info}

    # -------- median-window extension status
    print("\n=== MEDIAN-WINDOW EXTENSION STATUS (grid-edge rule A2.5, per criterion / tuning set / variant) ===")
    pending_any = set()
    for crit in (PRIMARY, SENSITIVITY):
        print(f"\n{CRITERION_LABEL[crit]}")
        print(f"  {'variant':8s} {'winner at edge 7 (no extension needed yet)':>44s} {'extended to 9':>14s} {'to 11':>7s} {'needs units':>12s}")
        for variant in VARIANTS:
            infos = [results[crit]["extension_info"][n][variant] for n in sets]
            e9 = sum(9 in i["extensions"] for i in infos)
            e11 = sum(11 in i["extensions"] for i in infos)
            pend = sorted({i["pending"] for i in infos if i["pending"]})
            pending_any |= set(pend)
            at_edge_now = sum(median_of(results[crit]["rankings"][n][variant][0]["prep"]) == base_max and not results[crit]["extension_info"][n][variant]["extensions"] and not results[crit]["extension_info"][n][variant]["pending"] for n in sets)
            print(f"  {variant:8s} {at_edge_now:44d} {e9:14d} {e11:7d} {str(pend) if pend else '-':>12s}")
    if pending_any:
        print(f"\nPENDING: the rule triggers for median window(s) {sorted(pending_any)} whose units are not computed. Run: "
              f"python scripts/03_tune.py compute --medians {' '.join(str(m) for m in sorted(pending_any)[:1])}")

    # -------- table under both criteria
    print("\n=== STAGE 1 TABLE UNDER BOTH CRITERIA (top-1 over the 12 tuning sets; final option lists after any executed extension) ===")
    print(f"{'variant':8s} | {'PRIMARY pooled IoU: range':>25s}  most common winner | {'SENSITIVITY mean per-chip IoU: range':>36s}  most common winner")
    for variant in VARIANTS:
        parts = []
        for crit in (PRIMARY, SENSITIVITY):
            top = [results[crit]["rankings"][n][variant][0] for n in sets]
            vals = [value(t, crit) for t in top]
            key = lambda t: (t["prep"], t["cfg"] if t["cfg"] != "nominal" else "", t["ceiling"] if t["ceiling"] != "plain" else "")
            modal = max(set(map(key, top)), key=list(map(key, top)).count)
            parts.append((f"{min(vals):.3f} - {max(vals):.3f}", f"{'/'.join(x for x in modal if x)} ({list(map(key, top)).count(modal)}/12)"))
        print(f"{variant:8s} | {parts[0][0]:>25s}  {parts[0][1]:36s} | {parts[1][0]:>36s}  {parts[1][1]}")

    # -------- per-set top two under the primary criterion
    for variant in VARIANTS:
        _, guarded = VARIANT_FAMILY[variant]
        print(f"\n=== {variant}: best two options per tuning set, PRIMARY criterion (pooled flood-only IoU on that tuning set) ===")
        for name in sets:
            r = results[PRIMARY]["rankings"][name][variant]
            print(f"  {name:22s} 1. {fmt(r[0], guarded, PRIMARY):50s} 2. {fmt(r[1], guarded, PRIMARY)}")

    # -------- edges that are not executed automatically: ceiling and B1 threshold
    print("\n=== GRID EDGES NOT EXECUTED AUTOMATICALLY (A7.4): guard ceiling and B1 threshold ===")
    for crit in (PRIMARY, SENSITIVITY):
        print(f"\n{CRITERION_LABEL[crit]}")
        for variant in ("b2g_vv", "b2g_vh", "m1g", "m2g"):
            family, _ = VARIANT_FAMILY[variant]
            wins = {k: 0 for k in ceilings}
            ties = 0
            for name, mask in sets.items():
                w = results[crit]["rankings"][name][variant][0]
                wins[w["ceiling"]] += 1
                sc = {ce: criterion(counts[(family, w["prep"], "nominal", ce)], mask) for ce in ceilings}
                best = _key(sc[w["ceiling"]], crit)
                ties += sum(_key(sc[ce], crit) == best for ce in ceilings) > 1
            edge = wins[ceilings[0]] + wins[ceilings[-1]]
            print(f"  {variant:7s} winning ceiling by tuning set: " + ", ".join(f"{k} dB {v}/12" for k, v in wins.items())
                  + f"  -> at an edge in {edge}/12; exact ties among ceilings in {ties}/12")
        b1thr = [float(results[crit]["rankings"][n]["b1"][0]["cfg"]) for n in sets]
        print(f"  b1      winning thresholds {sorted(set(b1thr))} dB (grid edges -30 and -8)")

    # -------- unions under each criterion
    unions = {c: {} for c in (PRIMARY, SENSITIVITY)}
    print("\n=== STAGE-2 UNION (A5.3), per criterion: top 2 per tuning set, at most 6 options ===")
    for crit in (PRIMARY, SENSITIVITY):
        print(f"\n{CRITERION_LABEL[crit]}")
        for variant in ("m1", "m1g", "m2", "m2g"):
            u = stage2_union({n: [r["prep"] for r in results[crit]["rankings"][n][variant]] for n in sets}, names)
            unions[crit][variant] = u
            moved = [n for n in sets if set(u["assigned"][n]) != {r["prep"] for r in results[crit]["rankings"][n][variant][:2]}]
            listing = ", ".join(f"{p} ({u['chosen_by'][p]}/12)" for p in sorted(u["chosen_by"], key=lambda p: (-u["chosen_by"][p], u["mean_rank"][p])))
            print(f"  {variant:4s} {len(u['union'])} kept of {u['distinct_top2']} distinct: {listing}; fallback used by {len(moved)}/12 sets")
    speed = measured_speedup(REPO_ROOT / cfg["paths"]["tuning_results_dir"] / "stage1_compute.log")
    merged = {v: sorted(set(unions[PRIMARY][v]["union"]) | set(unions[SENSITIVITY][v]["union"])) for v in ("m1", "m1g", "m2", "m2g")}
    cost_primary = project_stage2_cost({v: unions[PRIMARY][v]["union"] for v in merged}, seconds, len(chips), speed or 2.0)
    cost_both = project_stage2_cost(merged, seconds, len(chips), speed or 2.0)
    print("\n=== STAGE-2 COST (measured per-unit times, contended: mean seconds " + ", ".join(f"{k} {np.mean(v):.2f}" for k, v in seconds.items()) + ") ===")
    for label, c in (("primary criterion only", cost_primary), ("primary + sensitivity (options computed once)", cost_both)):
        print(f"  {label:46s}: {c['m2_options']} distinct M2 options, {c['m1_options']} distinct M1 options; "
              f"{c['serial_h']:.1f} h of contended unit time = about {c['wall_h']:.1f} h wall on 4 workers")
    print("  (M1 stage 2 is ASSUMED to cost 30% of a stage-1 M1 unit; M2: 15 new (n_segments, compactness) configurations per option)")
    print("\nSTOP: stage 2 does not start until the project owner approves the union and cost.")

    out = {"config_sha256": sha, "extension_medians_available": extras, "tuning_sets": {n: int(m.sum()) for n, m in sets.items()},
           "criteria": {c: {"rankings": results[c]["rankings"], "extension_info": results[c]["extension_info"],
                            "unions": unions[c]} for c in results},
           "cost": {"primary_only": cost_primary, "primary_plus_sensitivity": cost_both}}
    out_dir = Path(tempfile.mkdtemp(prefix="rank_dry_")) if dry else REPO_ROOT / cfg["paths"]["tuning_results_dir"]
    (out_dir / "stage1_rankings.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "compute":
        med = [int(x) for x in sys.argv[3:]] if len(sys.argv) > 2 and sys.argv[2] == "--medians" else []
        compute(med)
    elif cmd == "mv":
        compute([9, 11], kind="mv")
    elif cmd == "verify-mv":
        verify_mv()
    elif cmd == "rank":
        rank(dry=int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[2] == "--dry" else None)
    else:
        sys.exit("usage: 03_tune.py compute|rank")
