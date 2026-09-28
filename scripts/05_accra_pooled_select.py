"""
Accra Stage 4 preparation (protocol A8.5, A12.1): select a frozen configuration for B1, B2g VH, M1g
and M2g on a NEW tuning set -- all 440 eligible benchmark chips pooled together, primary criterion
only. This is not one of the 12 LOEO/official-split tuning sets; it exists only because Accra has no
held-out benchmark fold of its own. Runs on BENCHMARK data only; nothing here touches Accra imagery.

Method: identical machinery to the 12-set selection (src/selection.py, src/ranking.py), applied to one
extra mask (all chips True). For M1/M2, "assigned options" are this set's own top-2 (from its full
Stage-1 ranking, extension rule included) filtered to the ALREADY-FIXED union of the 12 sets (protocol
A5.3's own fallback rule: a set outside the union falls back to its own best-ranked in-union options) --
the union itself is not re-opened. B1 and B2g VH are Stage-1-only and use every preprocessing option.

  PYTHONPATH=. python scripts/05_accra_pooled_select.py
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import yaml

from src.config import REPO_ROOT, load_config
from src.ranking import PRIMARY, add_derived_ceilings, load_mv, load_units, rank_options, rank_with_extensions
from src.selection import build_store, extension_kinds, select_m1, select_m2_stage2, select_m2_stage3
from src.stage1 import (ceiling_key, eligible_chips, load_or_build_chip_index,
                        preprocessing_options, stage1_params)
from src.stage2 import stage2_params

OUT = REPO_ROOT / "results" / "tuning"
SET_NAME = "accra_pooled"


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()


def main():
    cfg = load_config()
    index = load_or_build_chip_index(cfg)
    chips = eligible_chips(index)
    mask = np.ones(len(chips), dtype=bool)  # every eligible benchmark chip

    p1 = stage1_params(cfg)
    preps = preprocessing_options(cfg, [9, 11])
    names = [x["name"] for x in preps]
    counts, _ = load_units(p1["unit_dir"], chips, names)
    mv = load_mv(p1["unit_dir"], chips, names)
    add_derived_ceilings(counts, mv, [-21.0])  # so rank_with_extensions can look up the -21 ceiling if it triggers

    clips = list(cfg["preprocess"]["clip_options"])
    base_preps = [x["name"] for x in preprocessing_options(cfg)]  # the base 16, before extension
    ceilings = [ceiling_key(c) for c in cfg["search_space"]["abstention_guard"]["ceilings_db"]]
    cext = {"available": cfg["search_space"]["abstention_guard"]["ceilings_db"] + [-21.0],
           "step": cfg["grid_extension"]["step"]["ceiling_db"]["value"],
           "max": cfg["grid_extension"]["max_extensions_per_parameter"]}
    available_medians = json.loads((OUT / "stage1_rankings.json").read_text())["extension_medians_available"]

    print(f"STAGE 4 PREP: accra_pooled selection (benchmark data only), {len(chips)} chips, primary criterion")
    print(f"git HEAD {git('rev-parse', 'HEAD')[:12]}; tracked files modified: {git('diff', '--name-only', 'HEAD') or 'none'}")

    # ---- Stage 1: B1 and B2g VH (Stage-1-only variants) ----
    b1_ranked, b1_info = rank_with_extensions(counts, "b1", mask, False, base_preps, clips, (), PRIMARY, available_medians)
    b2gvh_ranked, b2gvh_info = rank_with_extensions(counts, "b2_vh", mask, True, base_preps, clips, ceilings, PRIMARY,
                                                     available_medians, ceiling_ext=cext)
    print(f"  B1 winner: {b1_ranked[0]['prep']} thr={b1_ranked[0]['cfg']}  pooled={b1_ranked[0]['pooled']:.4f}  extensions={b1_info['extensions']} pending={b1_info['pending']}")
    print(f"  B2g_VH winner: {b2gvh_ranked[0]['prep']} ceiling={b2gvh_ranked[0]['ceiling']}  pooled={b2gvh_ranked[0]['pooled']:.4f}  "
         f"med_ext={b2gvh_info['extensions']} med_pending={b2gvh_info['pending']} ceil_ext={b2gvh_info['ceiling_extensions']} ceil_pending={b2gvh_info['pending_ceiling']}")

    # ---- M1/M1g and M2/M2g: full Stage-1 ranking on all 24 options (extensions included), then
    #      intersect this set's own top-2 with the ALREADY-FIXED union (A5.3 fallback rule) ----
    stage1_all = json.loads((OUT / "stage1_rankings.json").read_text())["criteria"][PRIMARY]
    unions = {k: stage1_all["unions"][k]["union"] for k in ("m1", "m1g", "m2", "m2g")}

    m1_full, m1_full_info = rank_with_extensions(counts, "m1", mask, False, base_preps, clips, (), PRIMARY, available_medians)
    m1g_full, m1g_full_info = rank_with_extensions(counts, "m1", mask, True, base_preps, clips, ceilings, PRIMARY,
                                                     available_medians, ceiling_ext=cext)
    m2_full, m2_full_info = rank_with_extensions(counts, "m2", mask, False, base_preps, clips, (), PRIMARY, available_medians)
    m2g_full, m2g_full_info = rank_with_extensions(counts, "m2", mask, True, base_preps, clips, ceilings, PRIMARY,
                                                     available_medians, ceiling_ext=cext)

    def assign(full_ranked, union_key, top=2):
        order = [r["prep"] for r in full_ranked]
        return [p for p in order if p in unions[union_key]][:top]

    m1_assigned, m1g_assigned = assign(m1_full, "m1"), assign(m1g_full, "m1g")
    m2_assigned, m2g_assigned = assign(m2_full, "m2"), assign(m2g_full, "m2g")
    print(f"  M1  own top: {[r['prep'] for r in m1_full[:2]]}  -> assigned (in union): {m1_assigned}   union={unions['m1']}")
    print(f"  M1g own top: {[r['prep'] for r in m1g_full[:2]]}  -> assigned (in union): {m1g_assigned}   union={unions['m1g']}")
    print(f"  M2  own top: {[r['prep'] for r in m2_full[:2]]}  -> assigned (in union): {m2_assigned}   union={unions['m2']}")
    print(f"  M2g own top: {[r['prep'] for r in m2g_full[:2]]}  -> assigned (in union): {m2g_assigned}   union={unions['m2g']}")

    m1_opts = sorted({o for c in (PRIMARY, "mean_flood") for o in json.loads((OUT / "stage2_plan.json").read_text())["options"][c]["m1"]})
    m2_opts = sorted({o for c in (PRIMARY, "mean_flood") for o in json.loads((OUT / "stage2_plan.json").read_text())["options"][c]["m2"]})
    p2 = stage2_params(cfg)
    ext = {}
    for kind in extension_kinds(p2["stage2_dir"]):
        plan = json.loads((OUT / f"stage2_ext_{kind}_plan.json").read_text())
        ext[kind] = list(plan["needed"])
    store = build_store(counts, mv, p2["stage2_dir"], chips, m1_opts, m2_opts, ext)

    m1_ranked, m1_selinfo = select_m1(store, m1_full[0]["prep"], m1_assigned, mask, False, ceilings, PRIMARY, cext)
    m1g_ranked, m1g_selinfo = select_m1(store, m1g_full[0]["prep"], m1g_assigned, mask, True, ceilings, PRIMARY, cext)
    print(f"  M1  Stage2 winner: {m1_ranked[0]['key']}  pooled={m1_ranked[0]['pooled']:.4f}")
    print(f"  M1g Stage2 winner: {m1g_ranked[0]['key']} ceiling={m1g_ranked[0]['ceiling']}  pooled={m1g_ranked[0]['pooled']:.4f}")

    plan2 = cfg["search_plan"]["stage2"]["m2"]
    step_n, step_c = cfg["grid_extension"]["step"]["n_segments"]["value"], cfg["grid_extension"]["step"]["compactness"]["value"]
    m2_stage2 = select_m2_stage2(store, m2_assigned, mask, False, plan2["n_segments"], plan2["compactness"], ceilings, PRIMARY,
                                  cext, cfg["grid_extension"]["max_extensions_per_parameter"], step_n, step_c)
    m2g_stage2 = select_m2_stage2(store, m2g_assigned, mask, True, plan2["n_segments"], plan2["compactness"], ceilings, PRIMARY,
                                   cext, cfg["grid_extension"]["max_extensions_per_parameter"], step_n, step_c)
    print(f"  M2  Stage2 winner: {m2_stage2['ranked'][0]['key']}  pooled={m2_stage2['ranked'][0]['pooled']:.4f}  pending={m2_stage2['pending']}")
    print(f"  M2g Stage2 winner: {m2g_stage2['ranked'][0]['key']}  pooled={m2g_stage2['ranked'][0]['pooled']:.4f}  pending={m2g_stage2['pending']}")
    if m2_stage2["pending"] or m2g_stage2["pending"]:
        sys.exit("Stage2 needs a configuration not in the cache (pending) -- projecting cost and stopping, per the cost rule. "
                 f"m2 pending={m2_stage2['pending']}  m2g pending={m2g_stage2['pending']}")

    combos = cfg["search_space"]["m2_slic_kmeans"]["allowed_combinations"]
    p3 = dict(p2)
    stage3_store = build_stage3_store(p3, chips, [
        (m2_stage2["ranked"][0]["key"][1], *_nc(m2_stage2["ranked"][0]["key"][2])),
        (m2g_stage2["ranked"][0]["key"][1], *_nc(m2g_stage2["ranked"][0]["key"][2])),
    ])
    m2_stage3, _ = select_m2_stage3(stage3_store, m2_stage2["ranked"][0]["key"][1], *_nc(m2_stage2["ranked"][0]["key"][2]),
                                    combos, mask, False, ceilings, PRIMARY, cext)
    m2g_stage3, _ = select_m2_stage3(stage3_store, m2g_stage2["ranked"][0]["key"][1], *_nc(m2g_stage2["ranked"][0]["key"][2]),
                                     combos, mask, True, ceilings, PRIMARY, cext)
    print(f"  M2  Stage3 winner: {m2_stage3[0]['key']}  pooled={m2_stage3[0]['pooled']:.4f}")
    print(f"  M2g Stage3 winner: {m2g_stage3[0]['key']} ceiling={m2g_stage3[0]['ceiling']}  pooled={m2g_stage3[0]['pooled']:.4f}")

    write_frozen(cfg, chips, b1_ranked[0], b2gvh_ranked[0], m1_ranked[0], m1g_ranked[0],
                (m2_stage2["ranked"][0], m2_stage3[0]), (m2g_stage2["ranked"][0], m2g_stage3[0]))


def _nc(cfgkey):
    from src.stage2 import config_key  # noqa: F401  (just documents the inverse of config_key)
    n, c = cfgkey.split("_")
    return int(n[1:]), float(c[1:])


def build_stage3_store(p2, chips, prep_n_c_list):
    from src.selection import Store
    from src.stage2 import config_key, stage3_path
    store = Store()
    for prep, n, c in set(prep_n_c_list):
        arrays = {}
        for ci, chip in enumerate(chips):
            f = json.loads(stage3_path(p2["stage3_dir"], chip, prep, n, c).read_text())
            for combo, e in f["configs"].items():
                plain, mvv = arrays.setdefault(combo, (np.zeros((len(chips), 2, 5), np.int64), np.full(len(chips), np.nan)))
                plain[ci] = e["plain"]
                mvv[ci] = np.nan if e["mv"] is None else e["mv"]
        for combo, (plain, mvv) in arrays.items():
            store.add(("m2s3", prep, f"{config_key(n, c)}|{combo}"), plain, mvv)
    return store


def frozen_record_b1(cfg, r):
    clip, med = r["prep"].split(",")[0].split("=")[1], int(r["prep"].split(",")[1].split("=")[1])
    return {"method": "B1 fixed threshold on VV", "preprocessing": {"clip": clip, "clip_range_db": cfg["preprocess"]["clip_options"][clip], "median_window": med},
           "threshold_db": float(r["cfg"]), "tuning_set_pooled_flood_only_iou": r["pooled"], "tuning_set_mean_per_chip_flood_only_iou": r["mean"]}


def frozen_record_b2(cfg, r, band):
    clip, med = r["prep"].split(",")[0].split("=")[1], int(r["prep"].split(",")[1].split("=")[1])
    rec = {"method": f"B2 Otsu on {band.upper()}", "preprocessing": {"clip": clip, "clip_range_db": cfg["preprocess"]["clip_options"][clip], "median_window": med},
          "tuning_set_pooled_flood_only_iou": r["pooled"], "tuning_set_mean_per_chip_flood_only_iou": r["mean"]}
    if r["ceiling"] != "plain":
        rec["abstention_guard"] = {"ceiling_db": float(r["ceiling"])}
    return rec


def frozen_record_m1(cfg, entry, guarded):
    key = entry["key"]
    clip, med = key[1].split(",")[0].split("=")[1], int(key[1].split(",")[1].split("=")[1])
    k = int(key[2][1:])
    rec = {"method": "M1 pixel k-means", "preprocessing": {"clip": clip, "clip_range_db": cfg["preprocess"]["clip_options"][clip], "median_window": med},
          "k": k, "n_init": cfg["search_space"]["m1_pixel_kmeans"]["n_init_by_k"][k], "seed": cfg["seed"], "max_iter": cfg["kmeans"]["max_iter"],
          "tuning_set_pooled_flood_only_iou": entry["pooled"], "tuning_set_mean_per_chip_flood_only_iou": entry["mean"]}
    if guarded:
        rec["abstention_guard"] = {"ceiling_db": float(entry["ceiling"])}
    return rec


def frozen_record_m2(cfg, stage2_entry, stage3_entry, guarded):
    prep = stage2_entry["key"][1]
    clip, med = prep.split(",")[0].split("=")[1], int(prep.split(",")[1].split("=")[1])
    n_c, feat_k = stage3_entry["key"][2].split("|", 1)
    n, c = _nc(n_c)
    feat, k = feat_k.split("|")
    rec = {"method": "M2 SLIC + k-means", "preprocessing": {"clip": clip, "clip_range_db": cfg["preprocess"]["clip_options"][clip], "median_window": med},
          "n_segments": n, "compactness": c, "features": feat, "k": int(k), "n_init": cfg["search_space"]["m2_slic_kmeans"]["n_init"],
          "seed": cfg["seed"], "max_iter": cfg["kmeans"]["max_iter"], "slic_max_num_iter": cfg["slic"]["max_num_iter"],
          "tuning_set_pooled_flood_only_iou": stage3_entry["pooled"], "tuning_set_mean_per_chip_flood_only_iou": stage3_entry["mean"],
          "stage2_choice_tuning_set_pooled_iou": stage2_entry["pooled"]}
    if guarded:
        rec["abstention_guard"] = {"ceiling_db": float(stage3_entry["ceiling"])}
    return rec


def write_frozen(cfg, chips, b1, b2gvh, m1, m1g, m2_pair, m2g_pair):
    m2_stage2, m2_stage3 = m2_pair
    m2g_stage2, m2g_stage3 = m2g_pair
    sha = hashlib.sha256((REPO_ROOT / "configs" / "config.yaml").read_bytes()).hexdigest()
    head = git("rev-parse", "HEAD")
    selections = {
        "b1": frozen_record_b1(cfg, b1),
        "b2g_vh": frozen_record_b2(cfg, b2gvh, "vh"),
        "m1g": frozen_record_m1(cfg, m1g, True),
        "m2g": frozen_record_m2(cfg, m2g_stage2, m2g_stage3, True),
    }
    # (m1, m2 unguarded kept too, for completeness -- not used as Accra methods, but frozen for the record)
    selections["m1"] = frozen_record_m1(cfg, m1, False)
    selections["m2"] = frozen_record_m2(cfg, m2_stage2, m2_stage3, False)
    d = REPO_ROOT / "results" / "frozen" / "primary"
    d.mkdir(parents=True, exist_ok=True)
    header = (f"# Frozen configuration, primary criterion, tuning set {SET_NAME} ({len(chips)} chips: ALL eligible benchmark chips pooled).\n"
             f"# Not one of the 12 LOEO/official-split tuning sets -- exists only for Stage 4 (Accra), which has no benchmark fold of its own (A12.1).\n"
             f"# Tuning-set metrics only: benchmark data, no Accra chip involved. config sha256 {sha}; git HEAD at selection {head[:12]}.\n")
    (d / f"{SET_NAME}.yaml").write_text(header + yaml.safe_dump(
        {"criterion": "primary", "tuning_set": SET_NAME, "n_tuning_chips": len(chips), "selections": selections}, sort_keys=False))
    print(f"\nwritten: results/frozen/primary/{SET_NAME}.yaml")
    print(yaml.safe_dump({"selections": selections}, sort_keys=False))


if __name__ == "__main__":
    main()
