"""
Accra Stage 4 follow-up: fix a scale mismatch in `scripts/06_accra_run.py`'s M2g run.

M2g (`results/frozen/primary/accra_pooled.yaml`) was tuned with n_segments=500 on Sen1Floods11's
512x512 chips (confirmed by reading one chip's shape directly, not assumed) -- about 524 px/segment.
`scripts/06_accra_run.py` instead runs SLIC with n_segments=500 on the WHOLE 3462x1480 Accra raster
(5,123,760 px), about 10,247 px/segment: superpixels nearly 20x larger in area than anything SLIC
produced during tuning. This script does not retune anything; it tests two ways of giving M2g
inputs closer to the tuned condition, keeping every other frozen setting (clip, median window,
compactness, features, k, seed, abstention guard) exactly as selected:

  A) tiled_512   -- split each image into 512x512 tiles (the exact tuned chip size), run the frozen
                    M2g (n_segments=500) independently on each tile (own SLIC call, own k-means fit,
                    own cluster-to-water rule, own abstention check -- matching how it was tuned
                    per-chip), then stitch predictions back onto the full raster.
  B) whole_scaled -- keep the single whole-raster SLIC call as in 06, but scale n_segments so
                    px/segment matches the tuned density: n_segments = 500 * (3462*1480)/(512*512),
                    computed below, not hand-entered.

Both are reported per image for the full catchment (`data/accra/aoi_mask.tif`) and the three
sub-AOI pieces (core, kaneshie, darkuman_clipped -- same corridor as `scripts/07_accra_subaoi_run.py`),
in the same fields as `accra_tables.json`/`accra_subaoi_tables.json`: flagged area (ha), share of
flagged pixels inside JRC permanent water, and agreement with the Sentinel-2 NDWI comparison layer
(agreement with another algorithm's output, NOT accuracy -- no ground truth exists for Accra).
UNVALIDATED -- no ground truth exists for Accra.

No new Sentinel-1/Sentinel-2/JRC imagery is pulled; this reuses `data/accra/*.tif` already written
by `scripts/06_accra_run.py`. Outputs go to results/accra/accra_m2g_tiled_tables.{json,csv} --
the existing accra_tables.* and accra_subaoi_tables.* are not touched.

  PYTHONPATH=. python scripts/08_accra_m2g_tiled.py
"""

import importlib.util
import json
import time

import numpy as np

from src.config import REPO_ROOT
from src.io import image_valid_mask
from src.preprocess import preprocess

# Reuse 06's and 07's helpers (build_method, predict, load_frozen, read_bands, S1_IMAGES, PIXEL_HA,
# load_pieces, rasterize_pieces, score_piece) by path import, same pattern 07 already uses to reuse 06
# -- scripts/ is not a package, and these are small pure functions/constants, safe to re-exec.
_spec06 = importlib.util.spec_from_file_location("accra_run_06", REPO_ROOT / "scripts" / "06_accra_run.py")
m06 = importlib.util.module_from_spec(_spec06)
_spec06.loader.exec_module(m06)

_spec07 = importlib.util.spec_from_file_location("accra_subaoi_run_07", REPO_ROOT / "scripts" / "07_accra_subaoi_run.py")
m07 = importlib.util.module_from_spec(_spec07)
_spec07.loader.exec_module(m07)

DATA = m06.DATA
OUT = REPO_ROOT / "results" / "accra"
TILE = 512  # the Sen1Floods11 chip size M2g was tuned on (verified: data/sen1floods11/S1Hand/*.tif is 512x512)
MIN_REMAINDER = TILE // 4  # an edge remainder this short is merged into the previous tile, not padded alone


def tile_bounds(n, tile=TILE, min_remainder=MIN_REMAINDER):
    """Start index and length of each tile along one axis. A short final remainder (< min_remainder)
    is merged into the second-to-last tile instead of becoming its own mostly-padding sliver; a
    longer remainder stays its own tile and gets NaN-padded up to `tile` by the caller."""
    starts = list(range(0, n, tile))
    sizes = [min(tile, n - s) for s in starts]
    if len(sizes) > 1 and sizes[-1] < min_remainder:
        sizes[-2] += sizes[-1]
        starts.pop()
        sizes.pop()
    return list(zip(starts, sizes))


def run_tiled(method, clip, median, guard, vv_raw, vh_raw, aoi_mask):
    """Run one SlicKMeans method independently on every 512x512 tile of (vv_raw, vh_raw) and stitch
    the predictions onto a full-size boolean array. Tiles with no AOI pixel are skipped (left False,
    which is irrelevant since nothing there is ever scored)."""
    h, w = vv_raw.shape
    row_tiles, col_tiles = tile_bounds(h), tile_bounds(w)
    pred_full = np.zeros((h, w), dtype=bool)
    n_run = n_skipped = 0
    for r0, rh in row_tiles:
        for c0, cw in col_tiles:
            if not aoi_mask[r0:r0 + rh, c0:c0 + cw].any():
                n_skipped += 1
                continue
            vv_t = vv_raw[r0:r0 + rh, c0:c0 + cw]
            vh_t = vh_raw[r0:r0 + rh, c0:c0 + cw]
            if rh <= TILE and cw <= TILE and (rh < TILE or cw < TILE):
                vv_in = np.full((TILE, TILE), np.nan, dtype=np.float32)
                vh_in = np.full((TILE, TILE), np.nan, dtype=np.float32)
                vv_in[:rh, :cw], vh_in[:rh, :cw] = vv_t, vh_t
            else:
                vv_in, vh_in = vv_t, vh_t  # exactly TILE x TILE, or a merged remainder (bigger, rare)
            vv_p, vh_p = preprocess(vv_in, vh_in, clip, median)
            pred_tile = m06.predict(method, vv_p, vh_p, guard)
            pred_full[r0:r0 + rh, c0:c0 + cw] = pred_tile[:rh, :cw]
            n_run += 1
    print(f"    tiled: {n_run} tiles run ({len(row_tiles)}x{len(col_tiles)} grid), "
          f"{n_skipped} skipped (no AOI pixels)", flush=True)
    return pred_full


def build_m2g_scaled(rec, n_segments):
    """Same frozen M2g settings as `m06.build_method`, with only n_segments replaced."""
    p = rec["preprocessing"]
    method = m06.SlicKMeans(rec["k"], n_segments, rec["compactness"], rec["features"], rec["seed"],
                             n_init=rec["n_init"], max_iter=rec["max_iter"], slic_max_iter=rec["slic_max_num_iter"])
    return method, p["clip_range_db"], p["median_window"], rec.get("abstention_guard")


def score_rows(image_label, run, n_segments_used, pred, valid0, piece_masks, jrc_mask, s2_water, s2_domain):
    rows = []
    for piece_name, piece_mask in piece_masks.items():
        row = {"image": image_label, "variant": "m2g", "run": run, "n_segments_used": n_segments_used,
               "piece": piece_name}
        row.update(m07.score_piece(pred, valid0, piece_mask, jrc_mask, s2_water, s2_domain))
        rows.append(row)
    return rows


def run_one_image(label, vv_raw, vh_raw, aoi_mask, jrc_mask, s2_water, s2_domain, piece_masks, rec, scaled_n_segments):
    valid0 = image_valid_mask(vv_raw, vh_raw)
    rows = []

    method_t, clip_t, median_t, guard_t = m06.build_method(rec)
    pred_tiled = run_tiled(method_t, clip_t, median_t, guard_t, vv_raw, vh_raw, aoi_mask)
    rows += score_rows(label, "tiled_512", rec["n_segments"], pred_tiled, valid0, piece_masks, jrc_mask, s2_water, s2_domain)

    method_s, clip_s, median_s, guard_s = build_m2g_scaled(rec, scaled_n_segments)
    vv_p, vh_p = preprocess(vv_raw, vh_raw, clip_s, median_s)
    pred_scaled = m06.predict(method_s, vv_p, vh_p, guard_s)
    rows += score_rows(label, "whole_scaled", scaled_n_segments, pred_scaled, valid0, piece_masks, jrc_mask, s2_water, s2_domain)

    return rows


def main():
    print(f"ACCRA M2G TILED RUN {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)

    aoi_arr, _, transform = m06.read_bands(DATA / "aoi_mask.tif", ["aoi"])
    aoi_mask = aoi_arr["aoi"] > 0.5

    jrc_arr, _, _ = m06.read_bands(DATA / "jrc_occurrence.tif", ["occurrence"])
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

    sub_masks = m07.rasterize_pieces(m07.load_pieces(), shape, transform)
    piece_masks = {"catchment": aoi_mask, **sub_masks}
    for name, mask in piece_masks.items():
        print(f"  piece {name}: {int(mask.sum())} pixels ({int(mask.sum()) * m06.PIXEL_HA:.2f} ha)", flush=True)

    selections = m06.load_frozen()
    rec = selections["m2g"]
    h, w = shape
    scaled_n_segments = round(rec["n_segments"] * (h * w) / (TILE * TILE))
    print(f"  frozen n_segments={rec['n_segments']} tuned for {TILE}x{TILE}={TILE * TILE} px chips "
          f"({rec['n_segments'] / (TILE * TILE):.6f} segments/px)", flush=True)
    print(f"  scene {h}x{w}={h * w} px -> density-matched n_segments={scaled_n_segments}", flush=True)

    all_rows = []
    for label, asset in m06.S1_IMAGES.items():
        arrs, nodata, _ = m06.read_bands(DATA / f"s1_{label}.tif", ["VV", "VH"])
        vv_raw, vh_raw = arrs["VV"], arrs["VH"]
        if nodata is not None:
            vv_raw[vv_raw == nodata] = np.nan
            vh_raw[vh_raw == nodata] = np.nan
        print(f"  {label}: shape {vv_raw.shape}", flush=True)
        all_rows += run_one_image(label, vv_raw, vh_raw, aoi_mask, jrc_mask, s2_water, s2_domain,
                                   piece_masks, rec, scaled_n_segments)
        print(f"  {label}: done", flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    out_json = OUT / "accra_m2g_tiled_tables.json"
    out_csv = OUT / "accra_m2g_tiled_tables.csv"
    out_json.write_text(json.dumps(all_rows, indent=1))
    cols = list(all_rows[0].keys())
    lines = [",".join(cols)] + [",".join(str(r[c]) for c in cols) for r in all_rows]
    out_csv.write_text("\n".join(lines) + "\n")
    print(f"\nwritten: results/accra/accra_m2g_tiled_tables.json, results/accra/accra_m2g_tiled_tables.csv", flush=True)
    for r in all_rows:
        print(f"  {r['image']:20s} {r['run']:13s} n_seg={r['n_segments_used']:5d} {r['piece']:16s} "
              f"valid_frac={r['valid_fraction_of_piece']:.3f} flagged_ha={r['flagged_area_ha']:.3f} "
              f"jrc_share={r['jrc_permanent_water_share_of_flagged']} s2_iou={r['s2_agreement_iou']} "
              f"s2_prec={r['s2_agreement_precision']} s2_rec={r['s2_agreement_recall']}", flush=True)


if __name__ == "__main__":
    main()
