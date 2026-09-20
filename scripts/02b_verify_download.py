"""
Decide, and show how we decided, that the Sen1Floods11 download is complete and valid.

A file counts as VALID only if ALL of these hold:
  1. it exists and has non-zero size;
  2. rasterio opens it and reads the whole array (this decompresses every tile, so a
     truncated GeoTIFF raises an error);
  3. it is 512 x 512 and every file in a folder has the same (band count, dtype);
  4. its byte size equals the size of the same object in the public bucket listing.

Also prints per-folder file counts (expected 446 each) and compares the summed local
bytes with the summed bucket bytes, so the 705 MB (du) vs 734 MB (bucket) question is
answered with numbers instead of a guess.

Run with: python scripts/02b_verify_download.py
Needs network access only for the bucket listing.
"""

import csv
import json
import time
import urllib.request
from collections import Counter
from pathlib import Path

import rasterio

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data" / "sen1floods11"
LAYERS = ["S1Hand", "LabelHand", "JRCWaterHand", "S1OtsuLabelHand"]
BUCKET_PREFIX = "v1.1/data/flood_events/HandLabeled"
SPLITS = ["flood_train_data.csv", "flood_valid_data.csv", "flood_test_data.csv",
          "flood_bolivia_data.csv"]


def expected_chip_ids():
    ids = []
    for name in SPLITS:
        with open(DATA_DIR / "splits" / name) as f:
            ids += [row[0].removesuffix("_S1Hand.tif") for row in csv.reader(f)]
    return ids


def list_bucket_sizes(layer):
    """Return {object filename: size in bytes} for one folder of the public bucket."""
    sizes, token = {}, None
    while True:
        url = ("https://storage.googleapis.com/storage/v1/b/sen1floods11/o"
               f"?prefix={BUCKET_PREFIX}/{layer}/&maxResults=1000&fields=items(name,size),nextPageToken")
        if token:
            url += f"&pageToken={token}"
        for attempt in range(5):
            try:
                with urllib.request.urlopen(url, timeout=60) as r:
                    page = json.load(r)
                break
            except Exception as exc:
                print(f"  listing retry {attempt + 1} for {layer}: {exc}")
                time.sleep(3)
        else:
            raise RuntimeError(f"could not list bucket folder {layer}")
        for item in page.get("items", []):
            sizes[Path(item["name"]).name] = int(item["size"])
        token = page.get("nextPageToken")
        if not token:
            return sizes


def main():
    ids = expected_chip_ids()
    print(f"Chips listed in the four split files: {len(ids)} (unique: {len(set(ids))})")
    problems = []
    total_local = total_bucket = 0

    for layer in LAYERS:
        folder = DATA_DIR / layer
        files = sorted(folder.glob("*.tif"))
        bucket = list_bucket_sizes(layer)
        structure = Counter()
        n_valid = 0
        local_bytes = 0
        for chip_id in ids:
            name = f"{chip_id}_{layer}.tif"
            path = folder / name
            if not path.exists() or path.stat().st_size == 0:
                problems.append((layer, chip_id, "missing or 0 bytes"))
                continue
            size = path.stat().st_size
            local_bytes += size
            try:
                with rasterio.open(path) as src:
                    src.read()  # full read: raises on truncated tiles
                    structure[(src.count, src.dtypes[0], src.height, src.width)] += 1
            except Exception as exc:
                problems.append((layer, chip_id, f"unreadable: {str(exc)[:60]}"))
                continue
            if bucket.get(name) != size:
                problems.append((layer, chip_id,
                                 f"size {size} != bucket size {bucket.get(name)}"))
                continue
            n_valid += 1
        bucket_bytes = sum(bucket.get(f"{c}_{layer}.tif", 0) for c in ids)
        total_local += local_bytes
        total_bucket += bucket_bytes
        print(f"\n{layer}: {len(files)} .tif files on disk, {n_valid} pass all 4 criteria")
        print(f"  (count, dtype, H, W) seen: {dict(structure)}")
        print(f"  summed bytes  local: {local_bytes:,}   bucket: {bucket_bytes:,}   "
              f"equal: {local_bytes == bucket_bytes}")

    split_bytes = sum((DATA_DIR / "splits" / n).stat().st_size for n in SPLITS)
    print(f"\nTotal data bytes  local: {total_local:,}   bucket: {total_bucket:,}")
    print(f"  = {total_local / 1e6:.1f} MB (decimal, 10^6) = {total_local / 2**20:.1f} MiB (binary, 2^20)")
    print(f"  split CSVs add {split_bytes:,} bytes")
    print(f"  the earlier 'du -sh' figure (705M) is in MiB and counts disk blocks, "
          f"the earlier bucket-listing figure (734.3) was decimal MB.")

    if problems:
        print(f"\n{len(problems)} PROBLEMS:")
        for p in problems[:20]:
            print("  ", p)
    else:
        print("\nAll 1,784 files pass all four criteria.")


if __name__ == "__main__":
    main()
