"""
Verify every Sen1Floods11 chip file needed for this project (all 4 layers for
every chip listed in the split CSVs) and (re-)download anything missing or
corrupt. The network on this machine has been flaky during download: several
files were truncated (some 0 bytes) while curl still reported success, so file
*existence* and non-zero size are not enough — each file must be opened and
read with rasterio to be trusted.
"""

import csv
import subprocess
from pathlib import Path

import rasterio

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data" / "sen1floods11"
SPLITS_DIR = DATA_DIR / "splits"
BASE = "https://storage.googleapis.com/sen1floods11/v1.1/data/flood_events/HandLabeled"

LAYERS = ["S1Hand", "LabelHand", "JRCWaterHand", "S1OtsuLabelHand"]
SPLIT_FILES = [
    "flood_train_data.csv",
    "flood_valid_data.csv",
    "flood_test_data.csv",
    "flood_bolivia_data.csv",
]


def all_chip_ids():
    ids = []
    for fname in SPLIT_FILES:
        with open(SPLITS_DIR / fname) as f:
            for row in csv.reader(f):
                ids.append(row[0].removesuffix("_S1Hand.tif"))
    return ids


def is_valid_tif(path):
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        with rasterio.open(path) as src:
            src.read()
        return True
    except Exception:
        return False


def fetch(layer, chip_id, out_path):
    """
    Resume (-C -) rather than restart: the network here repeatedly stalls
    mid-transfer, so a fresh restart on every retry throws away partial
    progress. -C - picks up from the existing file's current byte offset
    (GCS objects support byte-range requests), so repeated attempts
    accumulate instead of repeating from zero.
    """
    url = f"{BASE}/{layer}/{chip_id}_{layer}.tif"
    result = subprocess.run(
        ["curl", "-sL", "-C", "-", "--retry", "3", "--max-time", "120", url, "-o", str(out_path)],
        check=False,
    )
    if result.returncode not in (0, 33):  # 33 = server doesn't support resume; fall back to fresh
        return
    if result.returncode == 33:
        out_path.unlink(missing_ok=True)
        subprocess.run(
            ["curl", "-sL", "--retry", "3", "--max-time", "120", url, "-o", str(out_path)],
            check=False,
        )


def main(max_rounds=6):
    ids = all_chip_ids()
    print(f"Total chips expected: {len(ids)}")

    for round_num in range(1, max_rounds + 1):
        bad = []
        for chip_id in ids:
            for layer in LAYERS:
                out_path = DATA_DIR / layer / f"{chip_id}_{layer}.tif"
                if not is_valid_tif(out_path):
                    bad.append((layer, chip_id, out_path))

        print(f"Round {round_num}: {len(bad)} missing/corrupt files.")
        if not bad:
            print("All files present and valid.")
            return True

        for i, (layer, chip_id, out_path) in enumerate(bad, 1):
            out_path.parent.mkdir(parents=True, exist_ok=True)
            fetch(layer, chip_id, out_path)
            if i % 50 == 0:
                print(f"  ...{i}/{len(bad)} re-fetched this round")

    print(f"Gave up after {max_rounds} rounds; some files may still be missing/corrupt.")
    return False


if __name__ == "__main__":
    main()
