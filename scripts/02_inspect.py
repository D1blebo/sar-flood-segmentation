"""
Stage 1 data inspection for Sen1Floods11 (hand-labeled subset).

What this script does, and why:
- Verifies the chip counts in each split file (train/valid/test/bolivia) actually
  match the files present on disk. Never trust a download silently.
- For every chip, checks that LabelHand and JRCWaterHand share the same pixel grid
  (CRS, affine transform, width, height). If they don't, subtracting one raster
  from the other (our flood-only rule) would silently misalign pixels, so we stop
  and report rather than guess.
- Reports band count/dtype/value range for S1Hand, and value counts for LabelHand,
  across the whole hand-labeled set (not just one chip), so we know these facts
  hold generally and not just for the one chip we spot-checked by hand.
- Computes flood-only (LabelHand==1 & JRCWaterHand==0) vs all-water (LabelHand==1)
  pixel counts, and how many water pixels the JRC permanent-water mask removes.
- Saves a handful of example chips (S1 image, label, JRC mask) as PNGs so a human
  can look at them directly.

Run with: python scripts/02_inspect.py
"""

import csv
import sys
from pathlib import Path

import numpy as np
import rasterio
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data" / "sen1floods11"
SPLITS_DIR = DATA_DIR / "splits"
FIG_DIR = REPO_ROOT / "results" / "figures"

SPLIT_FILES = {
    "train": "flood_train_data.csv",
    "valid": "flood_valid_data.csv",
    "test": "flood_test_data.csv",
    "bolivia": "flood_bolivia_data.csv",
}


def load_split_chip_ids(split_name):
    """Split CSVs have rows like 'Country_id_S1Hand.tif,Country_id_LabelHand.tif'."""
    path = SPLITS_DIR / SPLIT_FILES[split_name]
    chip_ids = []
    with open(path) as f:
        for row in csv.reader(f):
            s1_name = row[0]
            chip_id = s1_name.removesuffix("_S1Hand.tif")
            chip_ids.append(chip_id)
    return chip_ids


def verify_split_counts_on_disk(all_chip_ids):
    """Confirm every chip's 4 layer files actually exist on disk. Report, don't guess."""
    print("\n=== Split / file-count verification ===")
    missing = {}
    for split_name in SPLIT_FILES:
        ids = load_split_chip_ids(split_name)
        print(f"{split_name}: {len(ids)} chips listed in split file")
        for chip_id in ids:
            for layer in ["S1Hand", "LabelHand", "JRCWaterHand", "S1OtsuLabelHand"]:
                p = DATA_DIR / layer / f"{chip_id}_{layer}.tif"
                if not p.exists() or p.stat().st_size == 0:
                    missing.setdefault(split_name, []).append(str(p.relative_to(DATA_DIR)))

    total_listed = sum(len(load_split_chip_ids(s)) for s in SPLIT_FILES)
    print(f"Total chips across all splits: {total_listed} (dataset README states 446)")

    if missing:
        print("\nMISSING OR EMPTY FILES FOUND:")
        for split_name, files in missing.items():
            print(f"  {split_name}: {len(files)} missing files")
            for f in files[:10]:
                print(f"    {f}")
            if len(files) > 10:
                print(f"    ... and {len(files) - 10} more")
    else:
        print("No missing or empty files. All chips present for all 4 layers.")
    return missing


def check_grid_alignment(all_chip_ids, origin_tol_deg=1e-6):
    """
    LabelHand and JRCWaterHand must be on the same pixel grid (CRS, resolution,
    width, height, and origin) before we can subtract one from the other for the
    flood-only metric. If any chip fails this, stop and report rather than
    silently reprojecting or skipping.

    Origin is compared with a tolerance rather than exact float equality: the two
    layers are written by separate export pipelines and their affine transforms
    can differ by ~1e-11 degrees (sub-micrometre) purely from floating-point
    representation. origin_tol_deg=1e-6 degrees is ~0.11 m at the equator, still
    ~800x smaller than the 10 m pixel size, so it cannot mask a real misalignment.
    """
    print("\n=== Grid alignment check: LabelHand vs JRCWaterHand ===")
    mismatches = []
    checked = 0
    for chip_id in all_chip_ids:
        label_path = DATA_DIR / "LabelHand" / f"{chip_id}_LabelHand.tif"
        jrc_path = DATA_DIR / "JRCWaterHand" / f"{chip_id}_JRCWaterHand.tif"
        if not (label_path.exists() and jrc_path.exists()):
            continue
        with rasterio.open(label_path) as lb, rasterio.open(jrc_path) as jrc:
            lt, jt = lb.transform, jrc.transform
            same = (
                lb.crs == jrc.crs
                and lb.width == jrc.width
                and lb.height == jrc.height
                and np.isclose(lt.a, jt.a, atol=1e-12)  # pixel width
                and np.isclose(lt.e, jt.e, atol=1e-12)  # pixel height
                and lt.b == jt.b == 0  # no rotation
                and lt.d == jt.d == 0
                and np.isclose(lt.c, jt.c, atol=origin_tol_deg)  # origin x
                and np.isclose(lt.f, jt.f, atol=origin_tol_deg)  # origin y
            )
            if not same:
                mismatches.append(
                    {
                        "chip": chip_id,
                        "label_crs": lb.crs,
                        "jrc_crs": jrc.crs,
                        "label_transform": lb.transform,
                        "jrc_transform": jrc.transform,
                        "label_shape": (lb.height, lb.width),
                        "jrc_shape": (jrc.height, jrc.width),
                    }
                )
        checked += 1

    print(f"Checked {checked} chips.")
    if mismatches:
        print(f"GRID MISMATCH FOUND on {len(mismatches)} chips. Stopping — do not compute")
        print("flood-only metric until this is resolved. Details:")
        for m in mismatches[:5]:
            print(f"  {m}")
        return mismatches
    else:
        print("All checked chips: LabelHand and JRCWaterHand share the same CRS, "
              "transform, and dimensions.")
        return []


def inspect_bands_and_labels(all_chip_ids, sample_limit=None):
    """
    Report S1 band count/dtype/value range, NaN presence, and LabelHand value
    counts across the (available) hand-labeled chips. This is measured on
    whatever chips are present on disk, not assumed from the README.
    """
    print("\n=== Band / label statistics (measured across available chips) ===")
    ids = all_chip_ids if sample_limit is None else all_chip_ids[:sample_limit]

    vv_min, vv_max = np.inf, -np.inf
    vh_min, vh_max = np.inf, -np.inf
    n_nan_vv = 0
    n_nan_vh = 0
    n_chips_checked = 0

    label_value_counts = {-1: 0, 0: 0, 1: 0}
    flood_only_px = 0  # LabelHand==1 & JRCWaterHand==0
    all_water_px = 0  # LabelHand==1
    jrc_removed_px = 0  # LabelHand==1 & JRCWaterHand==1 (water removed by the flood-only rule)
    corrupt_chips = []  # files that exist but fail to read (e.g. truncated download)

    for chip_id in ids:
        s1_path = DATA_DIR / "S1Hand" / f"{chip_id}_S1Hand.tif"
        label_path = DATA_DIR / "LabelHand" / f"{chip_id}_LabelHand.tif"
        jrc_path = DATA_DIR / "JRCWaterHand" / f"{chip_id}_JRCWaterHand.tif"
        if not (s1_path.exists() and label_path.exists() and jrc_path.exists()):
            continue

        try:
            with rasterio.open(s1_path) as src:
                s1 = src.read()  # (bands, H, W)
                if src.count != 2:
                    print(f"  WARNING: {chip_id} has {src.count} bands, expected 2 (VV, VH)")
                    continue
                vv, vh = s1[0], s1[1]
            with rasterio.open(label_path) as src:
                label = src.read(1)
            with rasterio.open(jrc_path) as src:
                jrc = src.read(1)
        except Exception as exc:
            corrupt_chips.append((chip_id, str(exc)))
            continue

        n_nan_vv += int(np.isnan(vv).sum())
        n_nan_vh += int(np.isnan(vh).sum())
        if np.isfinite(vv).any():
            vv_min = min(vv_min, float(np.nanmin(vv)))
            vv_max = max(vv_max, float(np.nanmax(vv)))
        if np.isfinite(vh).any():
            vh_min = min(vh_min, float(np.nanmin(vh)))
            vh_max = max(vh_max, float(np.nanmax(vh)))

        for v in (-1, 0, 1):
            label_value_counts[v] += int((label == v).sum())

        water = label == 1
        jrc_water = jrc == 1
        all_water_px += int(water.sum())
        flood_only_px += int((water & ~jrc_water).sum())
        jrc_removed_px += int((water & jrc_water).sum())

        n_chips_checked += 1

    print(f"Chips checked: {n_chips_checked}")
    if corrupt_chips:
        print(f"\nCORRUPT/UNREADABLE FILES: {len(corrupt_chips)} chips failed to read "
              f"(likely truncated downloads). These need re-downloading:")
        for chip_id, err in corrupt_chips[:10]:
            print(f"  {chip_id}: {err[:100]}")
        if len(corrupt_chips) > 10:
            print(f"  ... and {len(corrupt_chips) - 10} more")
    print(f"S1 VV range: [{vv_min:.2f}, {vv_max:.2f}] dB")
    print(f"S1 VH range: [{vh_min:.2f}, {vh_max:.2f}] dB")
    print(f"S1 NaN count: VV={n_nan_vv}, VH={n_nan_vh}")
    total_px = sum(label_value_counts.values())
    print(f"LabelHand value counts (pooled): {label_value_counts} "
          f"(nodata frac={label_value_counts[-1]/total_px:.4f}, "
          f"water frac={label_value_counts[1]/total_px:.4f})")
    print(f"\nAll-water pixels (LabelHand==1): {all_water_px}")
    print(f"Flood-only pixels (LabelHand==1 & JRCWaterHand==0): {flood_only_px}")
    print(f"Pixels removed by JRC permanent-water mask (LabelHand==1 & JRCWaterHand==1): "
          f"{jrc_removed_px}")
    if all_water_px > 0:
        print(f"  -> JRC mask removes {100 * jrc_removed_px / all_water_px:.2f}% "
              f"of all-water-labeled pixels")

    return {
        "n_chips_checked": n_chips_checked,
        "vv_range": (vv_min, vv_max),
        "vh_range": (vh_min, vh_max),
        "label_value_counts": label_value_counts,
        "all_water_px": all_water_px,
        "flood_only_px": flood_only_px,
        "jrc_removed_px": jrc_removed_px,
        "corrupt_chips": corrupt_chips,
    }


def report_nan_pixels():
    """
    NaN in the S1 image means the radar has no measurement there, so no method can
    classify it. Report where NaNs are, whether VV/VH agree, how they overlap the
    labels, and which chips are fully NaN, so the metrics code can mask them.
    """
    print("\n=== NaN pixels in S1 imagery (pooled over all splits) ===")
    chip_split = {}
    for split_name in SPLIT_FILES:
        for chip_id in load_split_chip_ids(split_name):
            chip_split[chip_id] = split_name

    n_with_nan, nan_total = 0, 0
    overlap = {-1: 0, 0: 0, 1: 0}
    masks_agree = True
    fully_nan = []
    per_split_chips = {s: 0 for s in SPLIT_FILES}
    vv_pcts = []  # per chip: VV 0.01th, 50th, 99.99th percentile over non-NaN pixels
    for chip_id, split_name in chip_split.items():
        with rasterio.open(DATA_DIR / "S1Hand" / f"{chip_id}_S1Hand.tif") as src:
            s1 = src.read()
        with rasterio.open(DATA_DIR / "LabelHand" / f"{chip_id}_LabelHand.tif") as src:
            label = src.read(1)
        nan_vv, nan_vh = np.isnan(s1[0]), np.isnan(s1[1])
        masks_agree &= bool(np.array_equal(nan_vv, nan_vh))
        n = int(nan_vv.sum())
        if n < nan_vv.size:
            vv_pcts.append(np.percentile(s1[0][~nan_vv], [0.01, 50, 99.99]))
        if n == 0:
            continue
        n_with_nan += 1
        per_split_chips[split_name] += 1
        nan_total += n
        for v in (-1, 0, 1):
            overlap[v] += int((nan_vv & (label == v)).sum())
        if n == nan_vv.size:
            fully_nan.append((chip_id, split_name))

    print(f"Chips with any NaN: {n_with_nan} of {len(chip_split)} "
          f"(per split: {per_split_chips})")
    print(f"VV and VH NaN masks identical on every chip: {masks_agree}")
    print(f"NaN pixels total: {nan_total}")
    print(f"  under LabelHand -1: {overlap[-1]}, under 0: {overlap[0]}, under 1 (water): {overlap[1]}")
    print(f"Fully-NaN chips: {fully_nan}")
    p = np.array(vv_pcts)
    print(f"Per-chip VV percentiles over {len(p)} chips with any valid pixel "
          f"(min..max across chips): 0.01th {p[:, 0].min():.1f}..{p[:, 0].max():.1f}, "
          f"median {p[:, 1].min():.1f}..{p[:, 1].max():.1f}, "
          f"99.99th {p[:, 2].min():.1f}..{p[:, 2].max():.1f} dB")


def chip_event(chip_id):
    """'Sri-Lanka_233609' -> 'Sri-Lanka' (chip ids are EVENT_NUMBER)."""
    return chip_id.rsplit("_", 1)[0]


def report_valid_pixel_rules():
    """
    Effect of the evaluation masking rules in results/evaluation_protocol.md, measured on
    all 446 chips (descriptive: no method is scored here).
      valid_all   = S1 not NaN  AND  LabelHand != -1
      valid_flood = valid_all   AND  JRCWaterHand == 0
    """
    print("\n=== Masking rules: NaN by event, water removed, chip exclusions ===")
    per_event = {}
    water_all = water_all_kept = water_flood = water_flood_kept = 0
    excluded = {"all_water": [], "flood_only": []}
    strata = {}
    for split_name in SPLIT_FILES:
        strata[split_name] = {"no flood": 0, "<5%": 0, "5-30%": 0, ">30%": 0}
        for chip_id in load_split_chip_ids(split_name):
            with rasterio.open(DATA_DIR / "S1Hand" / f"{chip_id}_S1Hand.tif") as src:
                s1 = src.read()
            with rasterio.open(DATA_DIR / "LabelHand" / f"{chip_id}_LabelHand.tif") as src:
                label = src.read(1)
            with rasterio.open(DATA_DIR / "JRCWaterHand" / f"{chip_id}_JRCWaterHand.tif") as src:
                jrc = src.read(1)

            nan = np.isnan(s1[0]) | np.isnan(s1[1])
            valid_all = ~nan & (label != -1)
            valid_flood = valid_all & (jrc == 0)

            ev = per_event.setdefault(chip_event(chip_id), {"chips": 0, "nan_chips": 0, "nan_px": 0})
            ev["chips"] += 1
            ev["nan_chips"] += int(nan.any())
            ev["nan_px"] += int(nan.sum())

            water = label == 1
            water_all += int(water.sum())
            water_all_kept += int((water & valid_all).sum())
            flood_truth = water & (jrc == 0)
            water_flood += int(flood_truth.sum())
            water_flood_kept += int((flood_truth & valid_flood).sum())

            if valid_all.sum() == 0:
                excluded["all_water"].append((chip_id, split_name))
            if valid_flood.sum() == 0:
                excluded["flood_only"].append((chip_id, split_name))
            else:
                n_flood = int((flood_truth & valid_flood).sum())
                frac = n_flood / int(valid_flood.sum())
                key = "no flood" if n_flood == 0 else "<5%" if frac < 0.05 else \
                    "5-30%" if frac <= 0.30 else ">30%"
                strata[split_name][key] += 1

    print("NaN by event (chips with any NaN / chips, NaN pixels):")
    for ev, d in sorted(per_event.items()):
        print(f"  {ev:10s} {d['nan_chips']:3d} / {d['chips']:3d}   {d['nan_px']:>9,d} px")
    print(f"All-water pixels (label==1): {water_all:,}; kept after NaN + label masking: "
          f"{water_all_kept:,}; removed by NaN masking: {water_all - water_all_kept:,}")
    print(f"Flood-only truth pixels (label==1 & JRC==0): {water_flood:,}; kept after masking: "
          f"{water_flood_kept:,}; removed by NaN masking: {water_flood - water_flood_kept:,}")
    print(f"Chips with ZERO valid pixels (excluded from that metric): {excluded}")
    print("Flood-fraction strata (flood-only truth / valid pixels), chips per official split:")
    for split_name, d in strata.items():
        print(f"  {split_name:8s} {d}")


def report_clip_effects():
    """
    How many valid pixels does each fixed dB clip range change? Label-free, and computed on
    the official train + valid chips only (no test imagery is touched for this).
    """
    import yaml

    with open(REPO_ROOT / "configs" / "config.yaml") as f:
        clip_options = yaml.safe_load(f)["preprocess"]["clip_options"]
    print("\n=== Pixels changed by each clip range (official train + valid chips) ===")
    ids = load_split_chip_ids("train") + load_split_chip_ids("valid")
    vv_all, vh_all = [], []
    for chip_id in ids:
        with rasterio.open(DATA_DIR / "S1Hand" / f"{chip_id}_S1Hand.tif") as src:
            s1 = src.read()
        ok = ~(np.isnan(s1[0]) | np.isnan(s1[1]))
        vv_all.append(s1[0][ok])
        vh_all.append(s1[1][ok])
    vv, vh = np.concatenate(vv_all), np.concatenate(vh_all)
    print(f"Chips: {len(ids)}; valid (non-NaN) pixels: {vv.size:,}")
    for name, rng in clip_options.items():
        if rng is None:
            print(f"  {name:7s}: no clipping (0 pixels changed)")
            continue
        for band, arr in (("vv", vv), ("vh", vh)):
            lo, hi = rng[band]
            below, above = int((arr < lo).sum()), int((arr > hi).sum())
            print(f"  {name:7s} {band}: [{lo:6.1f}, {hi:5.1f}] dB -> below {below:>10,} "
                  f"({100 * below / arr.size:6.3f}%), above {above:>10,} "
                  f"({100 * above / arr.size:6.3f}%)")


def save_example_chips(chip_ids, n_examples=4):
    """Save S1 (VV as grayscale), LabelHand, and JRCWaterHand as PNGs for visual inspection."""
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\n=== Saving {min(n_examples, len(chip_ids))} example chips to {FIG_DIR} ===")

    saved = 0
    for chip_id in chip_ids:
        s1_path = DATA_DIR / "S1Hand" / f"{chip_id}_S1Hand.tif"
        label_path = DATA_DIR / "LabelHand" / f"{chip_id}_LabelHand.tif"
        jrc_path = DATA_DIR / "JRCWaterHand" / f"{chip_id}_JRCWaterHand.tif"
        if not (s1_path.exists() and label_path.exists() and jrc_path.exists()):
            continue

        with rasterio.open(s1_path) as src:
            vv = src.read(1)
        with rasterio.open(label_path) as src:
            label = src.read(1)
        with rasterio.open(jrc_path) as src:
            jrc = src.read(1)

        fig, axes = plt.subplots(1, 3, figsize=(12, 4))
        axes[0].imshow(vv, cmap="gray", vmin=-25, vmax=0)
        axes[0].set_title(f"{chip_id}\nS1 VV (dB)")
        axes[1].imshow(label, cmap="viridis", vmin=-1, vmax=1)
        axes[1].set_title("LabelHand\n(-1 nodata, 0 dry, 1 water)")
        axes[2].imshow(jrc, cmap="Blues", vmin=0, vmax=1)
        axes[2].set_title("JRCWaterHand\n(permanent water)")
        for ax in axes:
            ax.axis("off")
        fig.tight_layout()
        out_path = FIG_DIR / f"example_{chip_id}.png"
        fig.savefig(out_path, dpi=100)
        plt.close(fig)
        print(f"  saved {out_path.relative_to(REPO_ROOT)}")
        saved += 1
        if saved >= n_examples:
            break


def main():
    if not SPLITS_DIR.exists():
        print(f"ERROR: {SPLITS_DIR} does not exist. Run the download script first.")
        sys.exit(1)

    missing = verify_split_counts_on_disk(None)

    all_chip_ids = []
    for split_name in SPLIT_FILES:
        all_chip_ids.extend(load_split_chip_ids(split_name))

    mismatches = check_grid_alignment(all_chip_ids)
    if mismatches:
        print("\nSTOPPING: grid mismatch between LabelHand and JRCWaterHand. "
              "Fix before computing flood-only metrics.")
        sys.exit(1)

    inspect_bands_and_labels(all_chip_ids)
    report_nan_pixels()
    report_valid_pixel_rules()
    report_clip_effects()

    # A varied sample: different countries and flood fractions, not just the first N chips.
    example_ids = []
    seen_countries = set()
    for chip_id in all_chip_ids:
        country = chip_id.split("_")[0]
        if country not in seen_countries:
            example_ids.append(chip_id)
            seen_countries.add(country)
    save_example_chips(example_ids, n_examples=6)

    print("\nDone.")


if __name__ == "__main__":
    main()
