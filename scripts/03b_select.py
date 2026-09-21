"""
Final selection after Stage 1 (protocol A9). Tuning-set metrics only; no held-out chip is scored.

  PYTHONPATH=. python scripts/03b_select.py stage2-rank      # M1, M2 Stage 2 with the grid-edge rule; prints the cost of any extension round
  PYTHONPATH=. python scripts/03b_select.py stage2-extend    # run the pending extension round (only after its cost has been accepted)
  PYTHONPATH=. python scripts/03b_select.py stage3-compute   # compute the six (features, k) combinations at every Stage 2 choice
  PYTHONPATH=. python scripts/03b_select.py freeze           # Stage 3 selection and the frozen configuration files
"""

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import yaml

from src.config import REPO_ROOT, load_config
from src.parallel import stream_map
from src.ranking import PRIMARY, SENSITIVITY, load_mv, load_units, tuning_sets
from src.selection import build_store, extension_kinds, select_m1, select_m2_stage2, select_m2_stage3, Store
from src.stage1 import ceiling_key, eligible_chips, load_or_build_chip_index, preprocessing_options, stage1_params
from src.stage2 import combo_key, config_key, stage2_params, stage2_path, stage2_unit, stage3_path, stage3_unit

CRITERIA = (PRIMARY, SENSITIVITY)
LABEL = {PRIMARY: "primary", SENSITIVITY: "sensitivity"}
STAGE1_DONE = ("b1", "b2_vv", "b2_vh", "b2g_vv", "b2g_vh")
OUT = REPO_ROOT / "results" / "tuning"


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()


def context():
    cfg = load_config()
    index = load_or_build_chip_index(cfg)
    chips = eligible_chips(index)
    events, splits = [index[c]["event"] for c in chips], [index[c]["split"] for c in chips]
    ctx = {"cfg": cfg, "chips": chips, "sets": tuning_sets(events, splits), "params": stage2_params(cfg)}
    ctx["stage1"] = json.loads((OUT / "stage1_rankings.json").read_text())["criteria"]
    ctx["plan"] = json.loads((OUT / "stage2_plan.json").read_text())["options"]
    ctx["preps"] = preprocessing_options(cfg, [9, 11])
    return ctx


def load_store(ctx):
    cfg, chips, p = ctx["cfg"], ctx["chips"], ctx["params"]
    names = [x["name"] for x in ctx["preps"]]
    counts, _ = load_units(p["unit_dir"], chips, names)
    mv = load_mv(p["unit_dir"], chips, names)
    m1_opts = sorted({o for c in CRITERIA for o in ctx["plan"][c]["m1"]})
    m2_opts = sorted({o for c in CRITERIA for o in ctx["plan"][c]["m2"]})
    ext = {}
    for kind in extension_kinds(p["stage2_dir"]):
        plan = json.loads((OUT / f"stage2_ext_{kind}_plan.json").read_text())
        ext[kind] = list(plan["needed"])
    return build_store(counts, mv, p["stage2_dir"], chips, m1_opts, m2_opts, ext)


def pack(entry, info=None, extra=None):
    out = {"key": list(entry["key"]), "ceiling": entry["ceiling"], "tuning_pooled_iou": entry["pooled"],
           "tuning_mean_per_chip_iou": entry["mean"], "ceiling_extensions": (info or {}).get("ceiling_extensions", [])}
    out.update(extra or {})
    return out


def run_selection(ctx, store):
    cfg = ctx["cfg"]
    ceilings = [ceiling_key(c) for c in cfg["search_space"]["abstention_guard"]["ceilings_db"]]
    cstep = cfg["grid_extension"]["step"]["ceiling_db"]["value"]
    max_steps = cfg["grid_extension"]["max_extensions_per_parameter"]
    plan2 = cfg["search_plan"]["stage2"]["m2"]
    step_n, step_c = cfg["grid_extension"]["step"]["n_segments"]["value"], cfg["grid_extension"]["step"]["compactness"]["value"]
    selection, pending = {c: {} for c in CRITERIA}, {}
    triggers = {}
    for crit in CRITERIA:
        cext = {"step": cstep, "max": max_steps} if crit == PRIMARY else None
        for name, mask in ctx["sets"].items():
            sel = selection[crit].setdefault(name, {})
            for variant in STAGE1_DONE:
                top = ctx["stage1"][crit]["rankings"][name][variant][0]
                sel[variant] = {"key": [variant, top["prep"], top["cfg"]], "ceiling": top["ceiling"], "tuning_pooled_iou": top["pooled"],
                                "tuning_mean_per_chip_iou": top["mean"], "ceiling_extensions": []}
            for variant, guarded in (("m1", False), ("m1g", True)):
                assigned = ctx["stage1"][crit]["unions"][variant]["assigned"][name]
                winner = ctx["stage1"][crit]["rankings"][name][variant][0]["prep"]
                ranked, info = select_m1(store, winner, assigned, mask, guarded, ceilings, crit, cext)
                sel[variant] = pack(ranked[0], info)
            for variant, guarded in (("m2", False), ("m2g", True)):
                assigned = ctx["stage1"][crit]["unions"][variant]["assigned"][name]
                res = select_m2_stage2(store, assigned, mask, guarded, plan2["n_segments"], plan2["compactness"], ceilings, crit, cext,
                                       max_steps, step_n, step_c)
                sel[variant] = pack(res["ranked"][0], res, {"n_list": res["n_list"], "c_list": res["c_list"],
                                                            "steps_n": res["steps_n"], "steps_c": res["steps_c"]})
                if res["pending"]:
                    for prep, cf in res["pending"]["needed"].items():
                        pending.setdefault(prep, set()).update(map(tuple, cf))
                    triggers[(LABEL[crit], variant)] = triggers.get((LABEL[crit], variant), 0) + 1
    return selection, pending, triggers


def measured_m2_unit_seconds(ctx, sample=300):
    """Mean seconds of a stage-2 M2 unit (15 configurations plus preprocessing), measured while 4 workers ran at once."""
    files = sorted((Path(ctx["params"]["stage2_dir"]) / "m2").rglob("*.json"))
    files = files[::max(1, len(files) // sample)]
    return float(np.mean([json.loads(f.read_text())["seconds"] for f in files]))


def stage2_rank():
    ctx = context()
    cfg = ctx["cfg"]
    sha = hashlib.sha256((REPO_ROOT / "configs" / "config.yaml").read_bytes()).hexdigest()
    print("STAGE 2 RANKING (tuning-set aggregates only; protocol A9)")
    print(f"config sha256 {sha}; git HEAD {git('rev-parse', 'HEAD')[:12]}; tracked files modified: {git('diff', '--name-only', 'HEAD') or 'none'}")
    store = load_store(ctx)
    kinds = extension_kinds(ctx["params"]["stage2_dir"])
    print(f"store: {len(store.plain)} configurations; extension rounds present: {kinds or 'none'}")
    selection, pending, triggers = run_selection(ctx, store)
    if pending:
        r = len(kinds) + 1
        s_unit = measured_m2_unit_seconds(ctx)
        pre = 0.53
        per_cfg = (s_unit - pre) / len(ctx["params"]["s2_m2"]["grid"])
        n_chips = len(ctx["chips"])
        hours = sum(n_chips * (pre + len(cf) * per_cfg) for cf in pending.values()) / 3600.0 / cfg["compute"]["n_jobs"]
        limit = cfg["search_plan"]["stage2_run"]["ask_before_extension_compute_above_hours"]
        needed = {p: sorted([list(x) for x in cf]) for p, cf in pending.items()}
        (OUT / f"stage2_ext_m2x{r}_plan.json").write_text(json.dumps({"round": r, "kind": f"m2x{r}", "needed": needed, "cost_hours": hours}, indent=1))
        print(f"\nGRID-EDGE RULE (A9.2) TRIGGERED: extension round {r} is needed. Winners at an edge of n_segments or compactness "
              f"(number of (tuning set, variant) pairs by criterion and variant): {dict(sorted(triggers.items()))}")
        print(f"  options needing new configurations: {len(needed)}; new configurations in total: {sum(len(v) for v in needed.values())}; "
              f"e.g. {next(iter(needed.items()))}")
        print(f"  measured M2 stage-2 unit time {s_unit:.1f} s (15 configs + preprocessing, contended) -> {per_cfg:.2f} s per configuration")
        print(f"  projected extension time: {hours:.2f} h on {cfg['compute']['n_jobs']} workers; rule: run if <= {limit} h -> "
              + ("RUN AS DECLARED" if hours <= limit else "ASK FIRST"))
        sys.exit(0)
    (OUT / "stage2_selection.json").write_text(json.dumps(selection, indent=1))
    print("\nno further extension triggers: Stage 2 selection is final; written to results/tuning/stage2_selection.json")
    for crit in CRITERIA:
        print(f"\n{LABEL[crit].upper()}: M2 grid at the winners (n_segments, compactness), by variant")
        for variant in ("m2", "m2g"):
            cnt = {}
            for name in ctx["sets"]:
                k = selection[crit][name][variant]["key"][2]
                cnt[k] = cnt.get(k, 0) + 1
            print(f"  {variant:4s} " + ", ".join(f"{k} x{v}" for k, v in sorted(cnt.items(), key=lambda kv: -kv[1])))
        for variant in ("m1", "m1g"):
            cnt = {}
            for name in ctx["sets"]:
                k = selection[crit][name][variant]["key"]
                cnt[f"{k[2]} at {k[1]}"] = cnt.get(f"{k[2]} at {k[1]}", 0) + 1
            print(f"  {variant:4s} " + ", ".join(f"{k} x{v}" for k, v in sorted(cnt.items(), key=lambda kv: -kv[1])))


def stage2_extend():
    ctx = context()
    cfg, p = ctx["cfg"], ctx["params"]
    kinds = extension_kinds(p["stage2_dir"])
    plans = sorted(OUT.glob("stage2_ext_m2x*_plan.json"))
    todo_plans = [f for f in plans if f.name.split("_")[2] not in kinds]
    if not todo_plans:
        sys.exit("no pending extension plan")
    plan = json.loads(todo_plans[-1].read_text())
    kind = plan["kind"]
    p["ext_grid"] = plan["needed"]
    sha = hashlib.sha256((REPO_ROOT / "configs" / "config.yaml").read_bytes()).hexdigest()
    print(f"STAGE 2 EXTENSION {kind}  {time.strftime('%Y-%m-%d %H:%M:%S')}\nconfig sha256 {sha}; git HEAD {git('rev-parse', 'HEAD')[:12]}; "
          f"tracked files modified: {git('diff', '--name-only', 'HEAD') or 'none'}", flush=True)
    units = [f"{kind}|{c}|{o}" for o in plan["needed"] for c in ctx["chips"]]
    todo = [u for u in units if not stage2_path(p["stage2_dir"], *u.split("|", 2)).exists()]
    print(f"{len(units)} units, {len(units) - len(todo)} already done, {len(todo)} to run; projected {plan['cost_hours']:.2f} h", flush=True)
    t0, done, errors = time.perf_counter(), 0, []
    for unit, status, secs in stream_map(stage2_unit, todo, cfg["compute"]["n_jobs"], chunksize=1, params=p, preps=ctx["preps"]):
        done += 1
        if status.startswith("error"):
            errors.append(unit)
            print(f"  ERROR {unit}: {status}", flush=True)
        if done % 100 == 0 or done == len(todo):
            wall = time.perf_counter() - t0
            print(f"  {done}/{len(todo)} units, {wall / 60:.1f} min elapsed, eta {(len(todo) - done) * wall / done / 60:.1f} min", flush=True)
    print(f"finished: {done - len(errors)} done, {len(errors)} errors, wall {(time.perf_counter() - t0) / 60:.1f} min", flush=True)
    sys.exit(1 if errors else 0)


def stage3_triples(ctx):
    sel = json.loads((OUT / "stage2_selection.json").read_text())
    triples = set()
    for crit in CRITERIA:
        for name in ctx["sets"]:
            for variant in ("m2", "m2g"):
                _, prep, cfgkey = sel[crit][name][variant]["key"]
                n, c = int(cfgkey.split("_")[0][1:]), float(cfgkey.split("_")[1][1:])
                triples.add((prep, n, c))
    return sel, sorted(triples)


def stage3_compute():
    ctx = context()
    cfg, p = ctx["cfg"], ctx["params"]
    sel, triples = stage3_triples(ctx)
    print(f"STAGE 3 compute {time.strftime('%Y-%m-%d %H:%M:%S')}; git HEAD {git('rev-parse', 'HEAD')[:12]}; "
          f"tracked files modified: {git('diff', '--name-only', 'HEAD') or 'none'}", flush=True)
    print(f"{len(triples)} distinct (option, n_segments, compactness) Stage 2 choices: {triples}", flush=True)
    units = [f"{c}|{prep}|{n}|{comp:g}" for prep, n, comp in triples for c in ctx["chips"]]
    todo = [u for u in units if not stage3_path(p["stage3_dir"], u.split("|")[0], u.split("|")[1], int(u.split("|")[2]), float(u.split("|")[3])).exists()]
    print(f"{len(units)} units, {len(units) - len(todo)} already done, {len(todo)} to run", flush=True)
    t0, done, errors = time.perf_counter(), 0, []
    for unit, status, secs in stream_map(stage3_unit, todo, cfg["compute"]["n_jobs"], chunksize=1, params=p, preps=ctx["preps"]):
        done += 1
        if status.startswith("error"):
            errors.append(unit)
            print(f"  ERROR {unit}: {status}", flush=True)
        if done % 100 == 0 or done == len(todo):
            wall = time.perf_counter() - t0
            print(f"  {done}/{len(todo)} units, {wall / 60:.1f} min elapsed", flush=True)
    print(f"finished: {done - len(errors)} done, {len(errors)} errors, wall {(time.perf_counter() - t0) / 60:.1f} min", flush=True)
    sys.exit(1 if errors else 0)


def load_stage3_store(ctx, triples):
    p, chips = ctx["params"], ctx["chips"]
    store = Store()
    for prep, n, c in triples:
        arrays = {}
        for ci, chip in enumerate(chips):
            f = json.loads(stage3_path(p["stage3_dir"], chip, prep, n, c).read_text())
            for combo, e in f["configs"].items():
                plain, mv = arrays.setdefault(combo, (np.zeros((len(chips), 2, 5), np.int64), np.full(len(chips), np.nan)))
                plain[ci] = e["plain"]
                mv[ci] = np.nan if e["mv"] is None else e["mv"]
        for combo, (plain, mv) in arrays.items():
            store.add(("m2s3", prep, f"{config_key(n, c)}|{combo}"), plain, mv)
    return store


def frozen_record(cfg, variant, entry, final_m2=None):
    """The complete, self-contained hyperparameter record of one selection (tuning-set metrics only)."""
    key = entry["key"]
    guard = {"ceiling_db": float(entry["ceiling"])} if entry["ceiling"] != "plain" else None

    def prep_of(name):
        clip, med = name.split(",")[0].split("=")[1], int(name.split(",")[1].split("=")[1])
        return {"clip": clip, "clip_range_db": cfg["preprocess"]["clip_options"][clip], "median_window": med}

    rec = {"tuning_set_pooled_flood_only_iou": entry["tuning_pooled_iou"], "tuning_set_mean_per_chip_flood_only_iou": entry["tuning_mean_per_chip_iou"]}
    if variant == "b1":
        rec.update(method="B1 fixed threshold on VV", preprocessing=prep_of(key[1]), threshold_db=float(key[2]))
    elif variant.startswith("b2"):
        rec.update(method="B2 Otsu on " + ("VV" if variant.endswith("vv") else "VH"), preprocessing=prep_of(key[1]))
    elif variant.startswith("m1"):
        k = int(key[2][1:])
        rec.update(method="M1 pixel k-means", preprocessing=prep_of(key[1]), k=k, n_init=cfg["search_space"]["m1_pixel_kmeans"]["n_init_by_k"][k],
                   seed=cfg["seed"], max_iter=cfg["kmeans"]["max_iter"])
    else:
        n_cfg, feat_k = final_m2["n_c"], final_m2["combo"]
        feat, k = feat_k.split("|")
        rec.update(method="M2 SLIC + k-means", preprocessing=prep_of(key[1]), n_segments=int(n_cfg.split("_")[0][1:]),
                   compactness=float(n_cfg.split("_")[1][1:]), features=feat, k=int(k), n_init=cfg["search_space"]["m2_slic_kmeans"]["n_init"],
                   seed=cfg["seed"], max_iter=cfg["kmeans"]["max_iter"], slic_max_num_iter=cfg["slic"]["max_num_iter"])
    if variant.endswith("g") or variant.startswith("b2g"):
        rec["abstention_guard"] = guard
    return rec


def freeze():
    ctx = context()
    cfg = ctx["cfg"]
    sel, triples = stage3_triples(ctx)
    store3 = load_stage3_store(ctx, triples)
    store2 = load_store(ctx)
    for prep, n, c in triples:      # determinism check: (vv_vh, k=2) in Stage 3 must equal the Stage 2 counts exactly
        k2, k3 = ("m2", prep, config_key(n, c)), ("m2s3", prep, f"{config_key(n, c)}|vv_vh|2")
        if not (np.array_equal(store2.plain[k2], store3.plain[k3]) and np.array_equal(np.nan_to_num(store2.mv[k2], nan=1e9), np.nan_to_num(store3.mv[k3], nan=1e9))):
            sys.exit(f"Stage 3 (vv_vh, 2) differs from Stage 2 for {prep} {config_key(n, c)}: refusing to freeze")
    checks = len(triples)
    combos = cfg["search_space"]["m2_slic_kmeans"]["allowed_combinations"]
    ceilings = [ceiling_key(c) for c in cfg["search_space"]["abstention_guard"]["ceilings_db"]]
    cstep, max_steps = cfg["grid_extension"]["step"]["ceiling_db"]["value"], cfg["grid_extension"]["max_extensions_per_parameter"]
    sha = hashlib.sha256((REPO_ROOT / "configs" / "config.yaml").read_bytes()).hexdigest()
    head = git("rev-parse", "HEAD")
    frozen = {c: {} for c in CRITERIA}
    for crit in CRITERIA:
        cext = {"step": cstep, "max": max_steps} if crit == PRIMARY else None
        for name, mask in ctx["sets"].items():
            rec_all = {}
            for variant in ("b1", "b2_vv", "b2_vh", "b2g_vv", "b2g_vh", "m1", "m1g"):
                rec_all[variant] = frozen_record(cfg, variant, sel[crit][name][variant])
            for variant, guarded in (("m2", False), ("m2g", True)):
                _, prep, cfgkey = sel[crit][name][variant]["key"]
                n, c = int(cfgkey.split("_")[0][1:]), float(cfgkey.split("_")[1][1:])
                ranked, info = select_m2_stage3(store3, prep, n, c, combos, mask, guarded, ceilings, crit, cext)
                best = ranked[0]
                entry = {"key": ["m2", prep, cfgkey], "ceiling": best["ceiling"], "tuning_pooled_iou": best["pooled"],
                         "tuning_mean_per_chip_iou": best["mean"]}
                rec_all[variant] = frozen_record(cfg, variant, entry, {"n_c": cfgkey, "combo": best["key"][2].split("|", 1)[1]})
                rec_all[variant]["stage2_choice_tuning_set_pooled_iou"] = sel[crit][name][variant]["tuning_pooled_iou"]
                rec_all[variant]["stage3_ceiling_extensions_db"] = info["ceiling_extensions"]
            frozen[crit][name] = rec_all
            d = REPO_ROOT / "results" / "frozen" / LABEL[crit]
            d.mkdir(parents=True, exist_ok=True)
            header = (f"# Frozen configurations, {LABEL[crit]} criterion, tuning set {name} ({int(mask.sum())} tuning chips).\n"
                      f"# Tuning-set metrics only: no held-out chip was scored. config sha256 {sha}; git HEAD at selection {head[:12]}.\n")
            (d / f"{name.replace(':', '_')}.yaml").write_text(header + yaml.safe_dump(
                {"criterion": LABEL[crit], "tuning_set": name, "n_tuning_chips": int(mask.sum()), "selections": rec_all}, sort_keys=False))
    (OUT / "frozen_all.json").write_text(json.dumps(frozen, indent=1))
    write_summary(frozen, ctx, sha, head, checks)


def describe(rec):
    p = rec["preprocessing"]
    base = f"clip {p['clip']}, median {p['median_window']}"
    if "threshold_db" in rec:
        base += f", thr {rec['threshold_db']:g} dB"
    if "k" in rec and "features" not in rec:
        base += f", k={rec['k']} (n_init {rec['n_init']})"
    if "features" in rec:
        base += f", SLIC {rec['n_segments']}/{rec['compactness']:g}, {rec['features']}, k={rec['k']}"
    g = rec.get("abstention_guard")
    return base + (f", guard {g['ceiling_db']:g} dB" if g else "")


def write_summary(frozen, ctx, sha, head, checks):
    lines = ["FROZEN CONFIGURATIONS BY TUNING SET AND CRITERION (tuning-set aggregates only; no held-out score exists)",
             f"config sha256 {sha}; git HEAD at selection {head[:12]}; Stage 3 determinism check: (vv_vh, k=2) equals the Stage 2 counts exactly for all {checks} distinct Stage 2 choices", ""]
    variants = ("b1", "b2_vv", "b2_vh", "b2g_vv", "b2g_vh", "m1", "m1g", "m2", "m2g")
    for crit in CRITERIA:
        lines.append(f"===== {LABEL[crit].upper()} criterion ({'pooled flood-only IoU over all tuning chips' if crit == PRIMARY else 'mean per-chip flood-only IoU over tuning chips with flood'}) =====")
        for v in variants:
            groups = {}
            for name in ctx["sets"]:
                groups.setdefault(describe(frozen[crit][name][v]), []).append(name)
            vals = [frozen[crit][n][v]["tuning_set_pooled_flood_only_iou" if crit == PRIMARY else "tuning_set_mean_per_chip_flood_only_iou"] for n in ctx["sets"]]
            lines.append(f"\n{v}  (tuning-set criterion {min(vals):.3f} to {max(vals):.3f}; {len(groups)} distinct configuration(s) over 12 tuning sets)")
            for desc, names in sorted(groups.items(), key=lambda kv: -len(kv[1])):
                lines.append(f"   {len(names):2d}/12  {desc}" + ("" if len(names) > 3 else "   [" + ", ".join(n.replace('loeo:', '') for n in names) + "]"))
        lines.append("")
    (OUT / "frozen_summary.txt").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"stage2-rank": stage2_rank, "stage2-extend": stage2_extend, "stage3-compute": stage3_compute, "freeze": freeze}.get(
        cmd, lambda: sys.exit("usage: 03b_select.py stage2-rank|stage2-extend|stage3-compute|freeze"))()
