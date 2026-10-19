"""
Amendment 19 (A19.3-A19.5, A19-R2.5), Step 2: change-detection (CD) baseline. UNVALIDATED: no ground truth.

Rules (all fixed in results/evaluation_protocol.md before this was run):
  inputs     median-3 filtered dB (frozen M2g preprocessing, no clip), each scene filtered then differenced
  dVV        VV_filtered(second date) - VV_filtered(first date)
  cd         dVV < -3 dB                         (-3 dB is an ASSUMPTION: no source confirmed)
  cd_guarded cd AND VV_filtered(second) < -15 dB (frozen guard ceiling, applied per pixel)
  brighten   dVV > +3 dB
  unspider_vh / unspider_vv   V_dB(second) / V_dB(first) > 1.25, V = filtered dB (UN-SPIDER ratio rule only)
  domain     finite VV and VH in both scenes, NOT JRC permanent water (>=50), inside the area

  PYTHONPATH=. python scripts/10_accra_cd_baseline.py
"""

import csv
import importlib.util
import json

import numpy as np

from src.config import REPO_ROOT
from src.io import image_valid_mask
from src.preprocess import preprocess

_s6 = importlib.util.spec_from_file_location("m06", REPO_ROOT / "scripts" / "06_accra_run.py")
m06 = importlib.util.module_from_spec(_s6)
_s6.loader.exec_module(m06)
_s7 = importlib.util.spec_from_file_location("m07", REPO_ROOT / "scripts" / "07_accra_subaoi_run.py")
m07 = importlib.util.module_from_spec(_s7)
_s7.loader.exec_module(m07)

DATA = m06.DATA
LABEL = "UNVALIDATED: no ground truth"
SCENE_FILE = {"2020-05-22": "2020-05-22_ref", "2020-05-28": "2020-05-28_ref", "2020-06-03": "2020-06-03_pre",
              "2020-06-09": "2020-06-09_event", "2020-06-15": "2020-06-15_next"}
CD_DB, GUARD_DB, BRIGHT_DB, RATIO = -3.0, -15.0, 3.0, 1.25
RULES = ["cd", "cd_guarded", "brighten", "unspider_vh", "unspider_vv"]
RULE_LABEL = {"cd": "CD: dVV < -3 dB (assumed threshold)", "cd_guarded": "guarded CD: dVV < -3 dB and VV_event < -15 dB",
              "brighten": "brightening: dVV > +3 dB",
              "unspider_vh": "UN-SPIDER ratio 1.25 sensitivity, VH (ratio rule only)",
              "unspider_vv": "UN-SPIDER ratio 1.25 sensitivity, VV (ratio rule only)"}
# (pair_set, role, first date, second date)
PAIRS = [
    ("headline", "event", "2020-06-03", "2020-06-09"),
    ("headline", "control", "2020-05-28", "2020-06-03"),
    ("headline", "recession", "2020-06-09", "2020-06-15"),
    ("same-satellite sensitivity", "event", "2020-05-28", "2020-06-09"),
    ("same-satellite sensitivity", "control", "2020-05-22", "2020-06-03"),
]
_cache = {}


def load_scene(date):
    """Filtered dB VV/VH (frozen M2g preprocessing) and the raw valid mask, loaded once per date."""
    if date not in _cache:
        arrs, nodata, _ = m06.read_bands(DATA / f"s1_{SCENE_FILE[date]}.tif", ["VV", "VH"])
        vv, vh = arrs["VV"], arrs["VH"]
        if nodata is not None:
            vv[vv == nodata] = np.nan
            vh[vh == nodata] = np.nan
        rec = m06.load_frozen()["m2g"]["preprocessing"]
        fvv, fvh = preprocess(vv, vh, rec["clip_range_db"], rec["median_window"])
        _cache[date] = (fvv, fvh, image_valid_mask(vv, vh))
    return _cache[date]


def pair_masks(first, second):
    """Flag masks (bool arrays) for each rule, plus the pair's valid mask (before JRC / area)."""
    v1, h1, ok1 = load_scene(first)
    v2, h2, ok2 = load_scene(second)
    d = v2 - v1
    with np.errstate(divide="ignore", invalid="ignore"):
        masks = {"cd": d < CD_DB, "cd_guarded": (d < CD_DB) & (v2 < GUARD_DB), "brighten": d > BRIGHT_DB,
                 "unspider_vh": (h2 / h1) > RATIO, "unspider_vv": (v2 / v1) > RATIO}
    return masks, ok1 & ok2, d


def main():
    guard = m06.load_frozen()["m2g"]["abstention_guard"]["ceiling_db"]
    assert guard == GUARD_DB, f"frozen guard ceiling changed: {guard}"
    aoi_arr, _, transform = m06.read_bands(DATA / "aoi_mask.tif", ["aoi"])
    aoi = aoi_arr["aoi"] > 0.5
    jrc = m06.read_bands(DATA / "jrc_occurrence.tif", ["occurrence"])[0]["occurrence"] >= 50.0
    sub = m07.rasterize_pieces(m07.load_pieces(), aoi.shape, transform)
    areas = {"full_Odaw_AOI": aoi, **sub, "pooled": sub["core"] | sub["kaneshie"] | sub["darkuman_clipped"]}

    rows, ha = [], {}
    for pair_set, role, first, second in PAIRS:
        masks, ok, _ = pair_masks(first, second)
        for rule in RULES:
            for area, amask in areas.items():
                dom = ok & ~jrc & amask
                n_dom, n_fl = int(dom.sum()), int((masks[rule] & dom).sum())
                h = n_fl * m06.PIXEL_HA
                ha[(pair_set, role, rule, area)] = (h, n_fl / n_dom if n_dom else float("nan"))
                rows.append({"label": LABEL, "pair_set": pair_set, "role": role, "first_date": first,
                             "second_date": second, "rule": rule, "rule_description": RULE_LABEL[rule],
                             "area": area, "domain_pixels": n_dom, "flagged_pixels": n_fl, "flagged_ha": h,
                             "flagged_fraction_of_domain": n_fl / n_dom if n_dom else float("nan"),
                             "event_minus_control_ha": "", "event_minus_control_fraction": ""})
    for pair_set in ("headline", "same-satellite sensitivity"):
        ev = [p for p in PAIRS if p[0] == pair_set and p[1] == "event"][0]
        co = [p for p in PAIRS if p[0] == pair_set and p[1] == "control"][0]
        for rule in RULES:
            for area in areas:
                he, fe = ha[(pair_set, "event", rule, area)]
                hc, fc = ha[(pair_set, "control", rule, area)]
                rows.append({"label": LABEL, "pair_set": pair_set, "role": "event_minus_control",
                             "first_date": f"{ev[2]} -> {ev[3]} minus {co[2]} -> {co[3]}", "second_date": "", "rule": rule,
                             "rule_description": RULE_LABEL[rule], "area": area, "domain_pixels": "", "flagged_pixels": "",
                             "flagged_ha": "", "flagged_fraction_of_domain": "",
                             "event_minus_control_ha": he - hc, "event_minus_control_fraction": fe - fc})

    out = REPO_ROOT / "results" / "accra_cd_baseline.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"written {out.relative_to(REPO_ROOT)} ({len(rows)} rows)")
    json.dump({f"{k[0]}|{k[1]}|{k[2]}|{k[3]}": v for k, v in ha.items()},
              open(REPO_ROOT / "results" / "accra" / "accra_cd_baseline_raw.json", "w"), indent=1)


if __name__ == "__main__":
    main()
