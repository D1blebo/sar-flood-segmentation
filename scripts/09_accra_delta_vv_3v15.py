"""
EXPLORATORY DIAGNOSTIC, UNVALIDATED. Same delta_VV exceedance diagnostic as Amendment 15 (A15.3), but
comparing 15 June 2020 against 3 June 2020 instead of 9 June against 3 June.

  delta_VV = VV(2020-06-15) - VV(2020-06-03), raw dB, no clip/median filter.
  Domain: finite VV and VH in BOTH images, AND NOT JRC permanent water (occurrence >= 50).
  Reported for the full Odaw AOI and core / kaneshie / darkuman_clipped: distribution and area (ha)
  above +3 / +6 / +10 dB. Thresholds are the ones fixed in A15.2, not re-chosen. M2g overlap is not computed.

  PYTHONPATH=. python scripts/09_accra_delta_vv_3v15.py
"""

import importlib.util
import json

import numpy as np

from src.config import REPO_ROOT
from src.io import image_valid_mask

_spec06 = importlib.util.spec_from_file_location("accra_run_06", REPO_ROOT / "scripts" / "06_accra_run.py")
m06 = importlib.util.module_from_spec(_spec06)
_spec06.loader.exec_module(m06)
_spec07 = importlib.util.spec_from_file_location("accra_subaoi_run_07", REPO_ROOT / "scripts" / "07_accra_subaoi_run.py")
m07 = importlib.util.module_from_spec(_spec07)
_spec07.loader.exec_module(m07)

DATA, OUT = m06.DATA, REPO_ROOT / "results" / "accra"
THRESHOLDS = (3, 6, 10)


def load_vv_valid(label):
    arrs, nodata, _ = m06.read_bands(DATA / f"s1_{label}.tif", ["VV", "VH"])
    vv, vh = arrs["VV"], arrs["VH"]
    if nodata is not None:
        vv[vv == nodata] = np.nan
        vh[vh == nodata] = np.nan
    return vv, image_valid_mask(vv, vh)


def main():
    aoi_arr, _, transform = m06.read_bands(DATA / "aoi_mask.tif", ["aoi"])
    aoi = aoi_arr["aoi"] > 0.5
    jrc = m06.read_bands(DATA / "jrc_occurrence.tif", ["occurrence"])[0]["occurrence"] >= 50.0
    pieces = {"full_Odaw_AOI": aoi, **m07.rasterize_pieces(m07.load_pieces(), aoi.shape, transform)}

    vv_a, ok_a = load_vv_valid("2020-06-03_pre")
    vv_b, ok_b = load_vv_valid("2020-06-15_next")
    delta = vv_b - vv_a
    domain = ok_a & ok_b & ~jrc

    results = {}
    for name, mask in pieces.items():
        d = delta[mask & domain]
        res = {"n_domain_pixels": int(d.size),
               "distribution_dB": {"min": float(d.min()), "p05": float(np.percentile(d, 5)),
                                   "p25": float(np.percentile(d, 25)), "median": float(np.median(d)),
                                   "mean": float(d.mean()), "p75": float(np.percentile(d, 75)),
                                   "p95": float(np.percentile(d, 95)), "max": float(d.max())},
               "thresholds": {}}
        for t in THRESHOLDS:
            n = int((d > t).sum())
            res["thresholds"][f">{t}dB"] = {"n_pixels": n, "area_ha": n * m06.PIXEL_HA}
        results[name] = res
        th = res["thresholds"]
        print(f"{name:18s} n={d.size:8d} median={res['distribution_dB']['median']:+.2f} "
              f"mean={res['distribution_dB']['mean']:+.2f} | " +
              " ".join(f"{k}: {v['area_ha']:.2f} ha" for k, v in th.items()), flush=True)

    out = {"label": "EXPLORATORY DIAGNOSTIC, UNVALIDATED",
           "definition": "delta_VV = VV(2020-06-15) - VV(2020-06-03), raw dB, no filtering; domain = valid in both "
                         "images and not JRC permanent water (occurrence >= 50)",
           "results": results}
    (OUT / "exploratory_delta_vv_3v15_diagnostic.json").write_text(json.dumps(out, indent=1))
    print("written: results/accra/exploratory_delta_vv_3v15_diagnostic.json")


if __name__ == "__main__":
    main()
