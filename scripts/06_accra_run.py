"""
Accra Stage 4 (protocol A8.5, A11, A12): apply the frozen `accra_pooled` configuration (primary
criterion, headline M2g, comparisons M1g/B2g_VH/B1) to three Sentinel-1 images on relative orbit 147
around the selected 8-9 June 2020 event (A12.1). UNVALIDATED -- no ground truth exists for Accra; every
number here is a tuning-set-frozen prediction applied to unlabelled real imagery, not a held-out score.

Pipeline is the SAME as the benchmark (src/preprocess.py, src/methods/*, src/cluster_rule.py): dB units,
clip + median filter per the frozen config, no extra terrain correction or speckle filtering. Confirmed
before running (A13.1 in the protocol) that Sen1Floods11's own S1Hand chips come from the same source
(Google Earth Engine COPERNICUS/S1_GRD, dB, standard GEE GRD preprocessing: orbit file, thermal-noise
removal, radiometric calibration, terrain correction; no speckle filter applied by either).

  PYTHONPATH=. python scripts/06_accra_run.py
"""

import json
import tempfile
import time
import urllib.request
from pathlib import Path

import ee
import numpy as np
import rasterio
import yaml
from rasterio.merge import merge as rio_merge

from src.cluster_rule import apply_abstention_ceiling, water_cluster_lowest_mean_vv
from src.config import REPO_ROOT
from src.io import image_valid_mask
from src.methods import FixedThresholdVV, OtsuThreshold, PixelKMeans, SlicKMeans
from src.methods.base import ClusteringMethod
from src.preprocess import preprocess

DATA = REPO_ROOT / "data" / "accra"
OUT = REPO_ROOT / "results" / "accra"
CRS = "EPSG:32630"
SCALE = 10
PIXEL_HA = (SCALE * SCALE) / 10000.0  # 10 m pixel = 0.01 ha

HYBAS_IDS = [1120023430, 1122029290]
S1_IMAGES = {  # relative orbit 147, ascending (A11.3)
    "2020-06-03_pre": "COPERNICUS/S1_GRD/S1B_IW_GRDH_1SDV_20200603T181725_20200603T181750_021873_02983B_F419",
    "2020-06-09_event": "COPERNICUS/S1_GRD/S1A_IW_GRDH_1SDV_20200609T181805_20200609T181834_032944_03D0DF_47E9",
    "2020-06-15_next": "COPERNICUS/S1_GRD/S1B_IW_GRDH_1SDV_20200615T181725_20200615T181750_022048_029D7F_634F",
}
S2_IMAGE = "COPERNICUS/S2_SR_HARMONIZED/20200610T102031_20200610T103925_T30NYM"  # 16.63% AOI cloud (A11.2/A12.2)


def ee_init():
    ee.Initialize(project="striking-ensign-503117-i8")


def aoi_geometry():
    hybas = ee.FeatureCollection("WWF/HydroSHEDS/v1/Basins/hybas_12").filter(ee.Filter.inList("HYBAS_ID", HYBAS_IDS))
    return hybas.geometry().dissolve(maxError=1)


def tile_rectangles(bounds_coords, n_tiles):
    """Split the AOI bounding box into n_tiles horizontal strips (it's much taller than wide) so each
    getDownloadURL request stays under Earth Engine's 50 MB per-request limit."""
    xs = [c[0] for c in bounds_coords[0]]
    ys = [c[1] for c in bounds_coords[0]]
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    step = (ymax - ymin) / n_tiles
    return [ee.Geometry.Rectangle([xmin, ymin + i * step, xmax, ymin + (i + 1) * step], proj=CRS, geodesic=False)
           for i in range(n_tiles)]


def _fetch_with_retry(url, dest, tries=4, timeout=60):
    """urlretrieve hangs indefinitely on a stalled connection (observed); this bounds every attempt
    and retries a bounded number of times instead of blocking forever."""
    last_exc = None
    for attempt in range(1, tries + 1):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp, open(dest, "wb") as f:
                while chunk := resp.read(1 << 20):
                    f.write(chunk)
            return
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            print(f"    download attempt {attempt}/{tries} failed ({type(exc).__name__}: {exc}); retrying", flush=True)
    raise RuntimeError(f"download failed after {tries} attempts: {last_exc}")


def download(image, bounds_coords, path, bands=None, n_tiles=4):
    """Download `image` over the AOI bounds as one GeoTIFF, tiling the request and mosaicking locally
    (a single request for the full AOI exceeds Earth Engine's 50 MB per-request limit)."""
    if path.exists():
        return
    img = image.select(bands) if bands else image
    tiles = tile_rectangles(bounds_coords, n_tiles)
    with tempfile.TemporaryDirectory() as td:
        tile_paths = []
        for i, tile in enumerate(tiles):
            url = img.getDownloadURL({"region": tile, "crs": CRS, "scale": SCALE, "format": "GEO_TIFF"})
            tp = Path(td) / f"tile_{i}.tif"
            _fetch_with_retry(url, tp)
            print(f"    tile {i + 1}/{n_tiles} ok", flush=True)
            tile_paths.append(tp)
        srcs = [rasterio.open(p) for p in tile_paths]
        mosaic, transform = rio_merge(srcs)
        profile = srcs[0].profile
        profile.update(height=mosaic.shape[1], width=mosaic.shape[2], transform=transform)
        for s in srcs:
            s.close()
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(mosaic)


def read_bands(path, band_names):
    with rasterio.open(path) as src:
        arrs = {name: src.read(i + 1).astype(np.float32) for i, name in enumerate(band_names)}
        nodata = src.nodata
        transform = src.transform
    return arrs, nodata, transform


def fetch_all():
    ee_init()
    aoi = aoi_geometry()
    bounds_coords = aoi.bounds(maxError=1, proj=CRS).getInfo()["coordinates"]
    DATA.mkdir(parents=True, exist_ok=True)

    for label, asset in S1_IMAGES.items():
        img = ee.Image(asset).select(["VV", "VH"])
        download(img, bounds_coords, DATA / f"s1_{label}.tif", ["VV", "VH"])
        print(f"  fetched s1_{label}.tif", flush=True)

    aoi_mask_img = ee.Image.constant(1).clip(aoi).unmask(0).rename("aoi")
    download(aoi_mask_img, bounds_coords, DATA / "aoi_mask.tif", ["aoi"], n_tiles=2)
    print("  fetched aoi_mask.tif", flush=True)

    jrc = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0).rename("occurrence")
    download(jrc, bounds_coords, DATA / "jrc_occurrence.tif", ["occurrence"], n_tiles=2)
    print("  fetched jrc_occurrence.tif", flush=True)

    s2 = ee.Image(S2_IMAGE).select(["B3", "B8", "SCL"])
    download(s2, bounds_coords, DATA / "s2_scene.tif", ["B3", "B8", "SCL"], n_tiles=4)
    print("  fetched s2_scene.tif", flush=True)


def load_frozen():
    d = yaml.safe_load((REPO_ROOT / "results" / "frozen" / "primary" / "accra_pooled.yaml").read_text())
    return d["selections"]


def build_method(rec, median_override=None):
    p = rec["preprocessing"]
    clip = p["clip_range_db"]
    median = median_override if median_override is not None else p["median_window"]
    if "threshold_db" in rec:
        base = FixedThresholdVV(rec["threshold_db"])
    elif "n_segments" in rec:
        base = SlicKMeans(rec["k"], rec["n_segments"], rec["compactness"], rec["features"], rec["seed"],
                          n_init=rec["n_init"], max_iter=rec["max_iter"], slic_max_iter=rec["slic_max_num_iter"])
    elif "k" in rec:
        base = PixelKMeans(rec["k"], rec["seed"], n_init=rec["n_init"], max_iter=rec["max_iter"])
    else:
        base = OtsuThreshold("vh")  # b2g_vh is the only plain-Otsu variant used for Accra
    return base, clip, median, rec.get("abstention_guard")


def predict(method, vv, vh, guard):
    if isinstance(method, ClusteringMethod):
        cmap = method.cluster_map(vv, vh)
        water = water_cluster_lowest_mean_vv(cmap, vv)
        pred = np.zeros(vv.shape, bool) if water is None else (cmap == water)
    else:
        pred = method.predict(vv, vh)
    if guard:
        pred = apply_abstention_ceiling(pred, vv, guard["ceiling_db"])
    return pred


def run_one(image_label, vv_raw, vh_raw, aoi_mask, jrc_mask, s2_water, s2_domain, selections, median_override, tag):
    rows = []
    valid0 = image_valid_mask(vv_raw, vh_raw)
    n_aoi = int(aoi_mask.sum())
    valid_frac = float((valid0 & aoi_mask).sum()) / n_aoi if n_aoi else float("nan")
    for variant in ("b1", "b2g_vh", "m1g", "m2g"):
        rec = selections[variant]
        method, clip, median, guard = build_method(rec, median_override)
        vv, vh = preprocess(vv_raw, vh_raw, clip, median)
        pred = predict(method, vv, vh, guard)
        flagged = pred & aoi_mask
        n_flagged = int(flagged.sum())
        area_ha = n_flagged * PIXEL_HA
        jrc_share = float((flagged & jrc_mask).sum()) / n_flagged if n_flagged else float("nan")
        # S2 comparison domain: cloud-free S2, inside the AOI, AND S1-valid (an S1 border-noise pixel is
        # never a real disagreement -- excluding it keeps it out of the denominator, not a false negative).
        cmp_domain = s2_domain & aoi_mask & valid0
        tp = int((flagged & s2_water & cmp_domain).sum())
        fp = int((flagged & ~s2_water & cmp_domain).sum())
        fn = int((~flagged & s2_water & cmp_domain).sum())
        denom = tp + fp + fn
        iou = tp / denom if denom else float("nan")
        precision = tp / (tp + fp) if (tp + fp) else float("nan")
        recall = tp / (tp + fn) if (tp + fn) else float("nan")
        rows.append({
            "image": image_label, "sensitivity": tag, "variant": variant,
            "n_aoi_pixels": n_aoi, "valid_fraction_of_aoi": valid_frac,
            "flagged_pixels": n_flagged, "flagged_area_ha": area_ha,
            "jrc_permanent_water_share_of_flagged": jrc_share,
            "s2_agreement_domain_pixels": denom, "s2_agreement_iou": iou,
            "s2_agreement_precision": precision, "s2_agreement_recall": recall,
        })
    return rows


def main():
    print(f"ACCRA RUN {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    fetch_all()

    aoi_arr, _, _ = read_bands(DATA / "aoi_mask.tif", ["aoi"])
    aoi_mask = aoi_arr["aoi"] > 0.5

    jrc_arr, _, _ = read_bands(DATA / "jrc_occurrence.tif", ["occurrence"])
    jrc_mask = jrc_arr["occurrence"] >= 50.0

    s2_arr, s2_nodata, _ = read_bands(DATA / "s2_scene.tif", ["B3", "B8", "SCL"])
    scl = s2_arr["SCL"]
    s2_cloud = np.isin(scl, [3, 8, 9, 10]) | (scl == 0)
    b3, b8 = s2_arr["B3"], s2_arr["B8"]
    with np.errstate(divide="ignore", invalid="ignore"):
        ndwi = (b3 - b8) / (b3 + b8)
    s2_domain = ~s2_cloud & np.isfinite(ndwi)
    s2_water = (ndwi > 0) & s2_domain

    selections = load_frozen()
    all_rows = []
    for label, asset in S1_IMAGES.items():
        arrs, nodata, _ = read_bands(DATA / f"s1_{label}.tif", ["VV", "VH"])
        vv_raw, vh_raw = arrs["VV"], arrs["VH"]
        # GEE's GEO_TIFF export declares nodata (confirmed 0.0 by reading the file's own metadata, not
        # assumed) for masked S1 border-noise pixels; rasterio does not auto-mask, so it's done here.
        if nodata is not None:
            vv_raw[vv_raw == nodata] = np.nan
            vh_raw[vh_raw == nodata] = np.nan
        print(f"  {label}: shape {vv_raw.shape}, AOI pixels {int(aoi_mask.sum())}", flush=True)
        all_rows += run_one(label, vv_raw, vh_raw, aoi_mask, jrc_mask, s2_water, s2_domain, selections, None, "frozen")
        all_rows += run_one(label, vv_raw, vh_raw, aoi_mask, jrc_mask, s2_water, s2_domain, selections, 3, "median3")
        print(f"  {label}: done", flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "accra_tables.json").write_text(json.dumps(all_rows, indent=1))
    cols = list(all_rows[0].keys())
    lines = [",".join(cols)] + [",".join(str(r[c]) for c in cols) for r in all_rows]
    (OUT / "accra_tables.csv").write_text("\n".join(lines) + "\n")
    print("\nwritten: results/accra/accra_tables.json, results/accra/accra_tables.csv", flush=True)
    for r in all_rows:
        print(f"  {r['image']:20s} {r['sensitivity']:8s} {r['variant']:8s} valid_frac={r['valid_fraction_of_aoi']:.3f} "
             f"flagged_ha={r['flagged_area_ha']:.2f} jrc_share={r['jrc_permanent_water_share_of_flagged']} "
             f"s2_iou={r['s2_agreement_iou']} s2_prec={r['s2_agreement_precision']} s2_rec={r['s2_agreement_recall']}", flush=True)


if __name__ == "__main__":
    main()
