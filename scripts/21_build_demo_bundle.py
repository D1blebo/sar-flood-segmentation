"""
Build the live-demo bundle for Jupyter / Google Colab (added 2026-11-26).

  conda activate sar_flood
  PYTHONPATH=. python scripts/21_build_demo_bundle.py

Writes demo/sar_flood_demo/ and demo/sar_flood_demo.zip containing:
  live_demo.ipynb   the notebook: one cell per pipeline step
  src/              a copy of this repository's src/ (the SAME code the evaluation used)
  data/<chip>.npz   the two demo chips (VV, VH, hand label, JRC permanent water), read from the
                    Sen1Floods11 GeoTIFFs and saved as numpy arrays so Colab needs no rasterio
  frozen/           the two frozen leave-one-event-out configurations the chips need
  expected.json     what the notebook produced HERE, with the pinned library versions; the notebook
                    compares its own run against it, so a version difference on Colab is caught, not hidden
  requirements_demo.txt

Why: the notebook must run anywhere without the full dataset or the repository. It tunes nothing and
writes nothing back into the repository except under demo/. No registered or locked file is touched.
"""
import contextlib
import io
import json
import shutil
import warnings
import zipfile

import matplotlib
matplotlib.use("Agg")  # the build runs the notebook cells without a screen
import numpy as np

from src.config import REPO_ROOT
from src.io import read_chip

# Public GitHub repository holding this project. When set, Colab clones it instead of asking for the zip.
# A PUBLIC repo needs no token; never put a token in the notebook (anyone who sees the cell can use it).
REPO_URL = "https://github.com/D1blebo/sar-flood-segmentation"

CHIPS = ["Mekong_16233", "Paraguay_284928"]  # the two chips already shown in the thesis (slides 10 and 8)
DEFAULT_CHIP = CHIPS[0]
OUT = REPO_ROOT / "demo" / "sar_flood_demo"
REQUIREMENTS = ["numpy", "scipy", "scikit-image", "scikit-learn", "matplotlib", "pyyaml"]


# ---- the notebook cells ------------------------------------------------------------------------------

def md(text):
    return ("markdown", text.strip("\n"))


def code(text):
    return ("code", text.strip("\n"))


CELLS = [
    md("""
# Live demo: unsupervised SAR flood mapping (SLIC + k-means + abstention guard)

Runs the **frozen M2g pipeline** on one Sentinel-1 chip from Sen1Floods11, one step per cell.

* The settings come from the leave-one-event-out fold that **held this chip's whole event out**, so the
  method never saw this chip during tuning. Nothing is tuned here.
* The pipeline code in `src/` is a copy of the code used for the thesis evaluation.
* **No labels are used** until the last step, where the result is compared with the hand label.
* Both chips were hand-picked for the thesis (a best case and a dry scene). They illustrate how the
  method works; they are **not** typical results. The headline numbers are on the slides.

**How to run.** Jupyter: open this file from inside the unzipped `sar_flood_demo` folder, then *Run All*.
Colab: *File > Upload notebook* (this file), then *Runtime > Run all*. The first cell clones the public
GitHub repository if `REPO_URL` is set; otherwise it asks you to choose `sar_flood_demo.zip`.
"""),
    code(f"""
# Setup: find the demo bundle (local Jupyter), or fetch it (Google Colab)
import os, subprocess, sys, zipfile
from pathlib import Path

REPO_URL = "{REPO_URL}"   # public repository: no token needed (never put a token here)

def find_bundle():
    for p in (Path.cwd(), Path.cwd() / "sar_flood_demo", Path("/content/sar_flood_demo"),
              Path("/content/repo/demo/sar_flood_demo")):
        if (p / "src").is_dir() and (p / "data").is_dir():
            return p
    return None

BUNDLE = find_bundle()
if BUNDLE is None:
    try:
        from google.colab import files   # this module only exists inside Colab
    except ImportError:
        raise RuntimeError("Open this notebook from inside the unzipped sar_flood_demo folder.")
    if REPO_URL:
        subprocess.run(["git", "clone", "--depth", "1", REPO_URL, "/content/repo"], check=True)
    else:
        print("Choose sar_flood_demo.zip:")
        uploaded = files.upload()
        zipfile.ZipFile(next(iter(uploaded))).extractall(".")
    BUNDLE = find_bundle()
os.chdir(BUNDLE)
sys.path.insert(0, str(BUNDLE))
print("Bundle:", BUNDLE)
"""),
    code("""
# Imports: the pipeline functions come from src/, the same code as the thesis evaluation
import json, time
import numpy as np, yaml, scipy, skimage, sklearn
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from skimage.segmentation import mark_boundaries

from src.preprocess import preprocess
from src.methods import SlicKMeans
from src.cluster_rule import water_cluster_lowest_mean_vv, apply_abstention_ceiling
from src.metrics import (MODE_FLOOD_ONLY, confusion_counts, evaluation_domain_and_truth,
                         iou, precision, recall)

print(f"numpy {np.__version__}, scipy {scipy.__version__}, scikit-image {skimage.__version__}, "
      f"scikit-learn {sklearn.__version__}")

BLUE, RED, GREEN = (0.16, 0.47, 0.84), (0.85, 0.15, 0.15), (0.15, 0.65, 0.15)

def grey(vv, lo_hi):
    # VV in dB stretched to a grey image, for display only (NaN drawn black)
    lo, hi = lo_hi
    g = np.clip((np.nan_to_num(vv, nan=lo) - lo) / (hi - lo), 0, 1)
    return np.dstack([g, g, g])

def overlay(rgb, mask, colour, alpha=0.75):
    # paint `mask` part-transparently so the radar image still shows through
    out = rgb.copy()
    out[mask] = (1 - alpha) * out[mask] + alpha * np.array(colour)
    return out

def show(*panels, legend=None):
    fig, axes = plt.subplots(1, len(panels), figsize=(5.5 * len(panels), 5.5), squeeze=False)
    for ax, (title, img) in zip(axes[0], panels):
        ax.imshow(img); ax.set_title(title); ax.axis("off")
    if legend:
        axes[0][-1].legend(handles=legend, loc="lower right", fontsize=9)
    plt.show()
"""),
    md("""
## Step 1: load one chip and its frozen settings
`Mekong_16233` is a flooded chip (slide 10). To show the dry chip (slide 8), change it to
`Paraguay_284928` and run all cells again.
"""),
    code(f"""
CHIP = "{DEFAULT_CHIP}"      # or "Paraguay_284928"
EVENT = CHIP.rsplit("_", 1)[0]   # chip ids are <event>_<number>

arrays = np.load(f"data/{{CHIP}}.npz")
vv_raw, vh_raw, label, jrc = arrays["vv"], arrays["vh"], arrays["label"], arrays["jrc"]
valid = np.isfinite(vv_raw) & np.isfinite(vh_raw)   # pixels with a radar value in both bands
fold = yaml.safe_load(open(f"frozen/loeo_{{EVENT}}.yaml"))["selections"]   # this fold never saw EVENT
rec = fold["m2g"]
RUN = {{"chip": CHIP}}
t0 = time.perf_counter()

print(f"Chip {{CHIP}}: {{vv_raw.shape[0]}} x {{vv_raw.shape[1]}} pixels (10 m), "
      f"VV {{np.nanmin(vv_raw):.1f}} to {{np.nanmax(vv_raw):.1f}} dB")
print(f"Frozen M2g settings (fold that held out {{EVENT}}): median window {{rec['preprocessing']['median_window']}}, "
      f"{{rec['n_segments']}} superpixels, compactness {{rec['compactness']}}, features {{rec['features']}}, "
      f"k = {{rec['k']}}, guard ceiling {{rec['abstention_guard']['ceiling_db']}} dB")

LO_HI = tuple(np.nanpercentile(vv_raw, [2, 98]))   # one grey stretch for every panel
show(("Sentinel-1 VV (dB): dark = smooth surface, e.g. calm water", grey(vv_raw, LO_HI)))
"""),
    md("## Step 2: median filter (reduce speckle, the grainy noise in every radar image)"),
    code("""
p = rec["preprocessing"]
vv, vh = preprocess(vv_raw, vh_raw, p["clip_range_db"], p["median_window"])
w = p["median_window"]
show(("Raw VV", grey(vv_raw, LO_HI)), (f"After {w} x {w} median filter", grey(vv, LO_HI)))
"""),
    md("## Step 3: SLIC superpixels (group neighbouring pixels of similar brightness)"),
    code("""
method = SlicKMeans(rec["k"], rec["n_segments"], rec["compactness"], rec["features"], rec["seed"],
                    n_init=rec["n_init"], max_iter=rec["max_iter"], slic_max_iter=rec["slic_max_num_iter"])
seg = method.segments(vv, vh)
RUN["n_superpixels"] = int(len(np.unique(seg[seg >= 0])))
print(f"{RUN['n_superpixels']} superpixels")
show((f"SLIC: {RUN['n_superpixels']} superpixels",
      mark_boundaries(grey(vv, LO_HI), np.where(seg < 0, 0, seg), color=(1, 0.85, 0))))
"""),
    md("## Step 4: k-means on the superpixels (mean and spread of VV and VH per superpixel)"),
    code("""
cmap = method.cluster_map(vv, vh)   # same SLIC again (deterministic), then k-means, seed fixed
means = {int(c): float(np.nanmean(vv[cmap == c])) for c in np.unique(cmap[cmap >= 0])}
for c, m in sorted(means.items(), key=lambda kv: kv[1]):
    print(f"cluster {c}: mean VV {m:6.2f} dB, {100 * (cmap == c).sum() / valid.sum():5.1f}% of the chip")
img = grey(vv, LO_HI)
for i, c in enumerate(sorted(means, key=means.get)):   # colours in order dark -> bright
    img = overlay(img, cmap == c, plt.get_cmap("tab10")(i)[:3], alpha=0.6)
show((f"k-means, k = {rec['k']} (blue = darker cluster)", img))
"""),
    md("""
## Step 5: the rule fixed in advance, and the abstention guard
* **Rule:** the cluster with the lowest mean VV is water (calm water is dark to radar).
* **Guard:** accept it only if its mean VV is below the ceiling; otherwise return an empty map.
  Without the guard, the rule *always* finds "water", even on dry ground.
"""),
    code("""
water = water_cluster_lowest_mean_vv(cmap, vv)
before_guard = cmap == water
ceiling = rec["abstention_guard"]["ceiling_db"]
pred = apply_abstention_ceiling(before_guard, vv, ceiling)
RUN["before_guard_pixels"] = int((before_guard & valid).sum())
RUN["flagged_pixels"] = int((pred & valid).sum())

darkest = means[water]
print(f"Darkest cluster: {darkest:.2f} dB. Guard ceiling: {ceiling} dB.")
print("-> below the ceiling: ACCEPT as water" if pred.any() else "-> NOT below the ceiling: ABSTAIN (empty map)")
print(f"Without the guard, {100 * RUN['before_guard_pixels'] / valid.sum():.1f}% of the chip would be called flood.")

if not pred.any():
    # Slide 8 quotes the separately tuned UNGUARDED M2 configuration (not M2g minus its guard)
    m2 = fold["m2"]
    vv2, vh2 = preprocess(vv_raw, vh_raw, m2["preprocessing"]["clip_range_db"], m2["preprocessing"]["median_window"])
    c2 = SlicKMeans(m2["k"], m2["n_segments"], m2["compactness"], m2["features"], m2["seed"], n_init=m2["n_init"],
                    max_iter=m2["max_iter"], slic_max_iter=m2["slic_max_num_iter"]).cluster_map(vv2, vh2)
    RUN["unguarded_m2_pixels"] = int(((c2 == water_cluster_lowest_mean_vv(c2, vv2)) & valid).sum())
    print(f"(The separately tuned unguarded M2 flags {100 * RUN['unguarded_m2_pixels'] / valid.sum():.1f}% here.)")
    show(("Darkest cluster, REJECTED by the guard", overlay(grey(vv, LO_HI), before_guard, RED, alpha=0.4)),
         ("Final map: no flood", grey(vv, LO_HI)))
else:
    show(("Final map: predicted flood (blue)", overlay(grey(vv, LO_HI), pred, BLUE)))
"""),
    md("## Step 6: only now, compare with the hand label (flood-only; unlabelled pixels ignored)"),
    code("""
domain, truth = evaluation_domain_and_truth(valid, label, jrc, MODE_FLOOD_ONLY)
c = confusion_counts(pred, truth, domain)
RUN.update(tp=int(c["tp"]), fp=int(c["fp"]), fn=int(c["fn"]))
base = grey(vv, LO_HI)
if truth.any():
    score = f"IoU {iou(c):.3f}, precision {precision(c):.3f}, recall {recall(c):.3f}"
    err = overlay(overlay(overlay(base, pred & truth, GREEN), pred & domain & ~truth, RED), ~pred & truth, BLUE)
    legend = [Patch(color=GREEN, label="correct flood"), Patch(color=RED, label="false alarm"),
              Patch(color=BLUE, label="missed flood")]
else:
    score = f"no flood in the label; {100 * RUN['flagged_pixels'] / valid.sum():.1f}% flagged (want 0%)"
    err, legend = overlay(base, pred & domain, RED), None
print(score)
print(f"Pipeline time {time.perf_counter() - t0:.1f} s. One hand-picked chip is an illustration, not a result.")
show(("Hand label (flood)", overlay(base, truth, (0.80, 0.62, 0.05))), (score, err), legend=legend)
"""),
    md("## Check: is this the same result as the stored run?"),
    code("""
# expected.json was written when the bundle was built, with the pinned library versions.
# Different scikit-image / scikit-learn versions can change SLIC or k-means slightly; this says so.
expected = json.load(open("expected.json"))
ref = expected["chips"].get(CHIP)
if ref is None:
    print("No stored result for this chip.")
else:
    diffs = {k: (RUN.get(k), v) for k, v in ref.items() if RUN.get(k) != v}
    if not diffs:
        print("Identical to the stored run (every pixel count matches).")
    else:
        print("DIFFERENT from the stored run (this run, stored):", diffs)
        print("Stored run used:", expected["versions"])
"""),
]


def notebook_json():
    def cell(i, kind, src):
        lines = src.splitlines(keepends=True)
        # nbformat 4.5 requires a unique id per cell; newer Jupyter versions will refuse notebooks without one
        c = {"id": f"cell-{i:02d}", "cell_type": kind, "metadata": {}, "source": lines}
        if kind == "code":
            c.update(execution_count=None, outputs=[])
        return c

    return {"cells": [cell(i, k, s) for i, (k, s) in enumerate(CELLS)], "nbformat": 4, "nbformat_minor": 5,
            "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                         "language_info": {"name": "python"}}}


def run_cells(chip):
    """Run the notebook's code cells here, for one chip, and return its RUN record (the expected values)."""
    import os
    ns = {}
    old = os.getcwd()
    os.chdir(OUT)  # so the setup cell finds the bundle, not the repository (which also has src/ and data/)
    try:
        with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()) as out:
            warnings.simplefilter("ignore")  # "cannot show figure" under the Agg backend
            for kind, src in CELLS[:-1]:  # the last cell is the check against expected.json, written after this
                if kind == "code":
                    exec(src.replace(f'CHIP = "{DEFAULT_CHIP}"', f'CHIP = "{chip}"'), ns)
    finally:
        os.chdir(old)
        matplotlib.pyplot.close("all")
    print(out.getvalue())
    return ns["RUN"]


def main():
    if OUT.exists():
        shutil.rmtree(OUT)  # rebuilt from scratch every time; contains nothing hand-made
    (OUT / "data").mkdir(parents=True)
    (OUT / "frozen").mkdir()
    shutil.copytree(REPO_ROOT / "src", OUT / "src", ignore=shutil.ignore_patterns("__pycache__"))
    for chip in CHIPS:
        a = read_chip(chip)
        np.savez_compressed(OUT / "data" / f"{chip}.npz", vv=a["vv"], vh=a["vh"], label=a["label"], jrc=a["jrc"])
        event = chip.rsplit("_", 1)[0]
        shutil.copy(REPO_ROOT / "results" / "frozen" / "primary" / f"loeo_{event}.yaml", OUT / "frozen")
    (OUT / "live_demo.ipynb").write_text(json.dumps(notebook_json(), indent=1))

    import importlib.metadata as md_
    versions = {r: md_.version(r) for r in REQUIREMENTS}
    (OUT / "requirements_demo.txt").write_text("".join(f"{r}=={v}\n" for r, v in versions.items()))
    expected = {"versions": versions, "chips": {}}
    for chip in CHIPS:
        print(f"==== {chip}")
        run = run_cells(chip)
        expected["chips"][chip] = {k: v for k, v in run.items() if k != "chip"}
    (OUT / "expected.json").write_text(json.dumps(expected, indent=1))

    zpath = OUT.parent / "sar_flood_demo.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(OUT.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(OUT.parent))
    print(f"written demo/sar_flood_demo/ and demo/sar_flood_demo.zip ({zpath.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
