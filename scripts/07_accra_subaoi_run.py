"""
Accra Stage 4 follow-up: the same frozen `accra_pooled` methods (M2g headline, M1g/B2g_VH/B1
comparisons), no retuning, applied to the ALREADY-DOWNLOADED 3/9/15 June 2020 imagery, clipped to the
three-piece Odaw sub-AOI (`results/accra/subaoi_corridor.geojson`: core, kaneshie, darkuman_clipped)
instead of the full Odaw catchment. No new Sentinel-1/Sentinel-2 imagery is pulled -- this reuses
`data/accra/s1_*.tif`, `jrc_occurrence.tif` and `s2_scene.tif` written by `scripts/06_accra_run.py`.

Reported PER PIECE (not only pooled), plus a pooled-across-the-three-pieces row for comparison with the
existing full-catchment result (`results/accra/accra_tables.*`), which this does not replace.
UNVALIDATED -- no ground truth exists for Accra.

  PYTHONPATH=. python scripts/07_accra_subaoi_run.py
"""

import importlib.util
import json
import time

import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.warp import transform_geom

from src.config import REPO_ROOT
from src.io import image_valid_mask
from src.preprocess import preprocess

# Reuse scripts/06_accra_run.py's helpers (build_method, predict, load_frozen, read_bands, constants)
# rather than duplicating them -- same file, imported by path since scripts/ is not a package.
_spec = importlib.util.spec_from_file_location("accra_run_06", REPO_ROOT / "scripts" / "06_accra_run.py")
m06 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m06)

DATA = m06.DATA
OUT = REPO_ROOT / "results" / "accra"


def load_pieces():
    fc = json.loads((OUT / "subaoi_corridor.geojson").read_text())
    return {f["properties"]["piece"]: f["geometry"] for f in fc["features"]}


def rasterize_pieces(pieces, shape, transform):
    """{'piece': bool array} on the same grid as the already-downloaded rasters (EPSG:4326 -> EPSG:32630)."""
    masks = {}
    for name, geom in pieces.items():
        geom_proj = transform_geom("EPSG:4326", m06.CRS, geom)
        arr = rasterize([(geom_proj, 1)], out_shape=shape, transform=transform, fill=0, dtype="uint8")
        masks[name] = arr.astype(bool)
    return masks


def score_piece(pred, valid0, piece_mask, jrc_mask, s2_water, s2_domain):
    n_piece = int(piece_mask.sum())
    valid_frac = float((valid0 & piece_mask).sum()) / n_piece if n_piece else float("nan")
    flagged = pred & piece_mask
    n_flagged = int(flagged.sum())
    area_ha = n_flagged * m06.PIXEL_HA
    jrc_share = float((flagged & jrc_mask).sum()) / n_flagged if n_flagged else float("nan")
    cmp_domain = s2_domain & piece_mask & valid0
    tp = int((flagged & s2_water & cmp_domain).sum())
    fp = int((flagged & ~s2_water & cmp_domain).sum())
    fn = int((~flagged & s2_water & cmp_domain).sum())
    denom = tp + fp + fn
    return {
        "n_piece_pixels": n_piece, "valid_fraction_of_piece": valid_frac,
        "flagged_pixels": n_flagged, "flagged_area_ha": area_ha,
        "jrc_permanent_water_share_of_flagged": jrc_share,
        "s2_agreement_domain_pixels": denom,
        "s2_agreement_iou": tp / denom if denom else float("nan"),
        "s2_agreement_precision": tp / (tp + fp) if (tp + fp) else float("nan"),
        "s2_agreement_recall": tp / (tp + fn) if (tp + fn) else float("nan"),
    }


def main():
    print(f"ACCRA SUB-AOI RUN {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)

    jrc_arr, _, transform = m06.read_bands(DATA / "jrc_occurrence.tif", ["occurrence"])
    jrc_mask = jrc_arr["occurrence"] >= 50.0
    shape = jrc_mask.shape

    s2_arr, _, _ = m06.read_bands(DATA / "s2_scene.tif", ["B3", "B8", "SCL"])
    scl = s2_arr["SCL"]
    s2_cloud = np.isin(scl, [3, 8, 9, 10]) | (scl == 0)
    b3, b8 = s2_arr["B3"], s2_arr["B8"]
    with np.errstate(divide="ignore", invalid="ignore"):
        ndwi = (b3 - b8) / (b3 + b8)
    s2_domain = ~s2_cloud & np.isfinite(ndwi)
    s2_water = (ndwi > 0) & s2_domain

    pieces = load_pieces()
    piece_masks = rasterize_pieces(pieces, shape, transform)
    piece_masks["pooled"] = piece_masks["core"] | piece_masks["kaneshie"] | piece_masks["darkuman_clipped"]
    for name, m in piece_masks.items():
        print(f"  piece {name}: {int(m.sum())} pixels ({int(m.sum()) * m06.PIXEL_HA:.2f} ha)", flush=True)

    selections = m06.load_frozen()
    all_rows = []
    for label, asset in m06.S1_IMAGES.items():
        arrs, nodata, _ = m06.read_bands(DATA / f"s1_{label}.tif", ["VV", "VH"])
        vv_raw, vh_raw = arrs["VV"], arrs["VH"]
        if nodata is not None:
            vv_raw[vv_raw == nodata] = np.nan
            vh_raw[vh_raw == nodata] = np.nan
        valid0 = image_valid_mask(vv_raw, vh_raw)

        for variant in ("b1", "b2g_vh", "m1g", "m2g"):
            rec = selections[variant]
            method, clip, median, guard = m06.build_method(rec)
            vv, vh = preprocess(vv_raw, vh_raw, clip, median)
            pred = m06.predict(method, vv, vh, guard)
            for piece_name, piece_mask in piece_masks.items():
                row = {"image": label, "variant": variant, "piece": piece_name}
                row.update(score_piece(pred, valid0, piece_mask, jrc_mask, s2_water, s2_domain))
                all_rows.append(row)
        print(f"  {label}: done", flush=True)

    (OUT / "accra_subaoi_tables.json").write_text(json.dumps(all_rows, indent=1))
    cols = list(all_rows[0].keys())
    lines = [",".join(cols)] + [",".join(str(r[c]) for c in cols) for r in all_rows]
    (OUT / "accra_subaoi_tables.csv").write_text("\n".join(lines) + "\n")
    print("\nwritten: results/accra/accra_subaoi_tables.json, results/accra/accra_subaoi_tables.csv", flush=True)
    for r in all_rows:
        print(f"  {r['image']:20s} {r['variant']:8s} {r['piece']:16s} valid_frac={r['valid_fraction_of_piece']:.3f} "
             f"flagged_ha={r['flagged_area_ha']:.3f} jrc_share={r['jrc_permanent_water_share_of_flagged']} "
             f"s2_iou={r['s2_agreement_iou']} s2_prec={r['s2_agreement_precision']} s2_rec={r['s2_agreement_recall']}", flush=True)


if __name__ == "__main__":
    main()
