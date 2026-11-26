"""
Live demo (added 2026-11-26): run the frozen M2g pipeline on ONE held-out chip, step by step.

  PYTHONPATH=. python scripts/20_live_demo.py                      # flood chip, Mekong_16233 (slide 10)
  PYTHONPATH=. python scripts/20_live_demo.py Paraguay_284928      # dry chip, shows the guard (slide 8)
  PYTHONPATH=. python scripts/20_live_demo.py Mekong_16233 --no-pause --save

Why this script exists: to show an audience that the method really runs, in a few seconds, on a chip it
was never tuned on. It is a presentation aid, not an evaluation:
  * It reads frozen configurations only (results/frozen/primary/loeo_<event>.yaml). It tunes nothing,
    writes no result table and does not touch any registered or locked file.
  * The configuration is the one from the leave-one-event-out fold that held the chip's whole event out,
    so the chip was never seen during tuning.
  * The steps are the same as src/evaluate.py and scripts/19_thesis_figures.py: preprocess, SLIC, k-means
    on superpixel features, darkest cluster = water, abstention guard.
  * One chip is an illustration. The two suggested chips were hand-picked for the thesis (best case and a
    dry scene), so they are not typical results. Say so if you show them.
"""
import argparse
import time

import matplotlib.pyplot as plt
import numpy as np
import yaml
from matplotlib.patches import Patch
from skimage.segmentation import mark_boundaries

from src.cluster_rule import apply_abstention_ceiling, water_cluster_lowest_mean_vv
from src.config import REPO_ROOT
from src.io import image_valid_mask, read_chip
from src.methods import SlicKMeans
from src.metrics import (MODE_FLOOD_ONLY, confusion_counts, evaluation_domain_and_truth, iou, precision,
                         recall)
from src.preprocess import preprocess

OUT = REPO_ROOT / "results" / "figures" / "demo"
BLUE, RED, GREEN, GOLD = (0.16, 0.47, 0.84), (0.85, 0.15, 0.15), (0.15, 0.65, 0.15), (0.80, 0.62, 0.05)


def frozen_record(event, variant):
    """Frozen settings of `variant` from the fold that held `event` out, so it never saw this chip."""
    path = REPO_ROOT / "results" / "frozen" / "primary" / f"loeo_{event}.yaml"
    return yaml.safe_load(path.read_text())["selections"][variant], path


def grey(vv, lo_hi=None):
    """VV in dB stretched to 0..1 grey RGB, for display only. NaN shown at the low end."""
    lo, hi = lo_hi or np.nanpercentile(vv, [2, 98])
    g = np.clip((np.nan_to_num(vv, nan=lo) - lo) / (hi - lo), 0, 1)
    return np.dstack([g, g, g])


def overlay(rgb, mask, colour, alpha=0.75):
    out = rgb.copy()
    out[mask] = (1 - alpha) * out[mask] + alpha * np.array(colour)
    return out


def step(n, text, pause):
    """Print one narrated step; optionally wait for Enter so the presenter can talk over it."""
    print(f"\n[{n}] {text}")
    if pause:
        input("    (press Enter) ")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("chip", nargs="?", default="Mekong_16233", help="chip id, e.g. Mekong_16233")
    ap.add_argument("--no-pause", action="store_true", help="run straight through without waiting for Enter")
    ap.add_argument("--save", action="store_true", help="also save the figure to results/figures/demo/")
    args = ap.parse_args()
    pause = not args.no_pause
    event = args.chip.rsplit("_", 1)[0]   # chip ids are <event>_<number>, e.g. Sri-Lanka_101973
    t0 = time.perf_counter()

    rec, path = frozen_record(event, "m2g")
    step(1, f"Load chip {args.chip} (event {event}). Frozen M2g settings from {path.relative_to(REPO_ROOT)}:\n"
            f"    median window {rec['preprocessing']['median_window']}, {rec['n_segments']} superpixels, "
            f"compactness {rec['compactness']}, features {rec['features']}, k = {rec['k']}, "
            f"guard ceiling {rec['abstention_guard']['ceiling_db']} dB. No labels are used to fit anything.", pause)
    chip = read_chip(args.chip)
    valid = image_valid_mask(chip["vv"], chip["vh"])
    print(f"    {chip['vv'].shape[0]} x {chip['vv'].shape[1]} pixels, {100 * valid.mean():.1f}% have a radar value; "
          f"VV range {np.nanmin(chip['vv']):.1f} to {np.nanmax(chip['vv']):.1f} dB")

    step(2, "Median filter: reduce speckle, the grainy noise in every radar image.", pause)
    p = rec["preprocessing"]
    vv, vh = preprocess(chip["vv"], chip["vh"], p["clip_range_db"], p["median_window"])

    step(3, "SLIC: group neighbouring pixels of similar brightness into superpixels.", pause)
    method = SlicKMeans(rec["k"], rec["n_segments"], rec["compactness"], rec["features"], rec["seed"],
                        n_init=rec["n_init"], max_iter=rec["max_iter"], slic_max_iter=rec["slic_max_num_iter"])
    seg = method.segments(vv, vh)
    print(f"    {len(np.unique(seg[seg >= 0]))} superpixels")

    step(4, f"k-means: sort the superpixels into {rec['k']} groups by their features (seed {rec['seed']}).", pause)
    cmap = method.cluster_map(vv, vh)   # recomputes the same SLIC (deterministic), then clusters
    means = {c: float(np.nanmean(vv[cmap == c])) for c in np.unique(cmap[cmap >= 0])}
    for c, m in sorted(means.items(), key=lambda kv: kv[1]):
        print(f"    cluster {c}: mean VV {m:6.2f} dB, {100 * (cmap == c).sum() / valid.sum():5.1f}% of valid pixels")

    water = water_cluster_lowest_mean_vv(cmap, vv)
    before_guard = np.zeros(vv.shape, bool) if water is None else (cmap == water)
    ceiling = rec["abstention_guard"]["ceiling_db"]
    pred = apply_abstention_ceiling(before_guard, vv, ceiling)
    darkest = means.get(water, float("nan"))
    verdict = "below the ceiling, so ACCEPT it as water" if pred.any() else "NOT below the ceiling, so ABSTAIN (empty map)"
    step(5, f"Rule fixed in advance: the darkest cluster is water (cluster {water}, mean VV {darkest:.2f} dB).\n"
            f"    Guard: {darkest:.2f} dB vs ceiling {ceiling} dB -> {verdict}.", pause)
    print(f"    Without the guard this cluster would be called flood: "
          f"{100 * (before_guard & valid).sum() / valid.sum():.1f}% of valid pixels.")
    if not pred.any():
        # Slide 8 quotes the separately tuned UNGUARDED M2 configuration, not M2g minus its guard; show both
        # so the two numbers are not confused.
        m2, _ = frozen_record(event, "m2")
        p2 = m2["preprocessing"]
        vv2, vh2 = preprocess(chip["vv"], chip["vh"], p2["clip_range_db"], p2["median_window"])
        c2 = SlicKMeans(m2["k"], m2["n_segments"], m2["compactness"], m2["features"], m2["seed"], n_init=m2["n_init"],
                        max_iter=m2["max_iter"], slic_max_iter=m2["slic_max_num_iter"]).cluster_map(vv2, vh2)
        w2 = water_cluster_lowest_mean_vv(c2, vv2)
        share2 = 0.0 if w2 is None else 100 * ((c2 == w2) & valid).sum() / valid.sum()
        print(f"    (The separately tuned unguarded M2 configuration flags {share2:.1f}% of valid pixels here.)")

    domain, truth = evaluation_domain_and_truth(valid, chip["label"], chip["jrc"], MODE_FLOOD_ONLY)
    step(6, "Only now compare with the hand label (flood-only, unlabelled pixels ignored).", pause)
    flagged = 100 * (pred & valid).sum() / valid.sum()
    if truth.any():
        c = confusion_counts(pred, truth, domain)
        score = f"IoU {iou(c):.3f}, precision {precision(c):.3f}, recall {recall(c):.3f}"
    else:
        score = f"no flood in the label; {flagged:.1f}% flagged (want 0%)"
    print(f"    {score}")
    print(f"\nTotal time {time.perf_counter() - t0:.1f} s. One chip is an illustration, not a result.")

    # ---- the figure: one panel per step --------------------------------------------------------------
    lo_hi = tuple(np.nanpercentile(chip["vv"], [2, 98]))   # same stretch for raw and filtered, so they compare
    raw, filt = grey(chip["vv"], lo_hi), grey(vv, lo_hi)
    palette = plt.get_cmap("tab10")
    clusters = filt.copy()
    for i, cid in enumerate(sorted(means, key=means.get)):  # colour order = dark to bright
        clusters = overlay(clusters, cmap == cid, palette(i)[:3], alpha=0.6)
    err = overlay(overlay(overlay(filt, pred & truth, GREEN), pred & domain & ~truth, RED), ~pred & truth, BLUE)
    if not truth.any():
        err = overlay(filt, pred & domain, RED)

    fig, axes = plt.subplots(2, 3, figsize=(14, 9.5))
    panels = [
        ("1  Sentinel-1 VV (dB), raw", raw),
        (f"2  Median filter ({p['median_window']}x{p['median_window']})", filt),
        (f"3  SLIC: {len(np.unique(seg[seg >= 0]))} superpixels", mark_boundaries(filt, np.where(seg < 0, 0, seg),
                                                                                    color=(1, 0.85, 0))),
        (f"4  k-means, k = {rec['k']} (dark to bright)", clusters),
        (f"5  Darkest cluster {darkest:.1f} dB vs guard {ceiling} dB\n-> {'water' if pred.any() else 'abstain: empty map'}",
         overlay(filt, pred, BLUE) if pred.any() else overlay(filt, before_guard, RED, alpha=0.35)),
        (f"6  vs hand label\n{score}", err),
    ]
    for ax, (title, img) in zip(axes.flat, panels):
        ax.imshow(img)
        ax.set_title(title, fontsize=11)
        ax.axis("off")
    if truth.any():
        axes.flat[5].legend(handles=[Patch(color=GREEN, label="correct flood"), Patch(color=RED, label="false alarm"),
                                     Patch(color=BLUE, label="missed flood")], loc="lower right", fontsize=8)
    if not pred.any():
        axes.flat[4].legend(handles=[Patch(color=RED, alpha=0.5, label="darkest cluster (rejected)")],
                            loc="lower right", fontsize=8)
    fig.suptitle(f"Chip {args.chip}: frozen M2g from the fold that held out {event}. "
                 f"A single hand-picked illustration, not a typical result.", fontsize=11)
    fig.tight_layout()
    if args.save:
        OUT.mkdir(parents=True, exist_ok=True)
        fig.savefig(OUT / f"demo_{args.chip}.png", dpi=150, bbox_inches="tight", facecolor="white")
        print(f"saved results/figures/demo/demo_{args.chip}.png")
    plt.show()


if __name__ == "__main__":
    main()
