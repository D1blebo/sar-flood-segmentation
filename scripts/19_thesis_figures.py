"""
Thesis figures 1 and 3 to 8, regenerated from stored results and local data (added 2026-11-16).

  PYTHONPATH=. python scripts/19_thesis_figures.py

Why this script exists: the figures in the thesis had no plotting code in the repository, so nobody could
show how they were made. This script draws them again and writes them to results/figures/thesis/.

What it does NOT do:
  * It does not tune anything and does not change any configuration or any result file.
  * Figures 3, 4 and 6 only READ results/heldout_results.json (written once by scripts/04_evaluate.py).
  * Figures 5 and 7 each run frozen methods on ONE held-out chip, to draw the picture. The two chip IDs are
    fixed below: they are the chips already shown in the thesis. The code that originally CHOSE them (by
    screening held-out chips) is not in the repository, so that choice cannot be reproduced here and the
    chips must be described as hand-picked illustrations, not as typical results.
  * Figure 8 re-runs the frozen Accra M2g configuration on the two downloaded scenes and checks that the
    flagged area equals the stored table (results/accra/accra_tables.json) before drawing.
  * Figure 2 (the world map) is not made here: it needs country outlines, which are not in this repository.

Every Accra panel is labelled UNVALIDATED: there is no ground truth for Accra.
"""
import importlib.util
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch, Patch

from src.cluster_rule import apply_abstention_ceiling, water_cluster_lowest_mean_vv
from src.config import REPO_ROOT
from src.io import image_valid_mask, read_chip
from src.methods import SlicKMeans
from src.metrics import (MODE_FLOOD_ONLY, confusion_counts, evaluation_domain_and_truth, iou, precision,
                         recall)
from src.preprocess import preprocess

OUT = REPO_ROOT / "results" / "figures" / "thesis"
HELDOUT = json.loads((REPO_ROOT / "results" / "heldout_results.json").read_text())["primary"]

# One colour per GROUP of methods, plus a different marker shape, so the groups can be told apart
# without relying on colour alone (colour-blind readers, black-and-white printing).
GREY, ORANGE, BLUE = "#6f6e69", "#eb6834", "#2a78d6"
VARIANTS = [  # (key in heldout_results.json, label, colour, marker)
    ("b1", "B1  fixed threshold", GREY, "s"),
    ("b2_vv", "B2  Otsu (VV)", ORANGE, "^"),
    ("b2_vh", "B2  Otsu (VH)", ORANGE, "^"),
    ("m1", "M1  pixel k-means", ORANGE, "^"),
    ("m2", "M2  SLIC + k-means", ORANGE, "^"),
    ("b2g_vv", "B2g Otsu (VV), guarded", BLUE, "o"),
    ("b2g_vh", "B2g Otsu (VH), guarded", BLUE, "o"),
    ("m1g", "M1g pixel k-means, guarded", BLUE, "o"),
    ("m2g", "M2g SLIC + k-means, guarded", BLUE, "o"),
]
GUARD_CHIP = "Paraguay_284928"   # Figure 5: a flood-free held-out chip (already in the thesis)
BEST_CHIP = "Mekong_16233"       # Figure 7: a high-IoU held-out chip (already in the thesis)

plt.rcParams.update({"font.family": "serif", "font.size": 11, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.spines.left": False})


def flood_only(variant):
    """The leave-one-event-out, flood-only block of the stored held-out results for one variant."""
    return HELDOUT[variant]["loeo"]["flood_only"]


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / name, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"written results/figures/thesis/{name}")


def light_grid(ax):
    ax.grid(axis="x", color="#deddd6", linewidth=1)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0)


# ---- Figure 1: the processing chain (a drawing, no data) ---------------------------------------------

def figure_1():
    steps = [("Sentinel-1\nVV, VH (dB)", GREY), ("NaN mask,\nclip, median\nfilter", GREY), ("SLIC\nsuperpixels", BLUE),
             ("k-means on\nsegment\nfeatures", BLUE), ("Darkest\ncluster\n= water", BLUE), ("Guard:\nmean VV\n< ceiling?", ORANGE)]
    fig, ax = plt.subplots(figsize=(11, 4))
    for i, (text, colour) in enumerate(steps):
        x = i * 1.8
        ax.add_patch(FancyBboxPatch((x, 1.6), 1.4, 1.6, boxstyle="round,pad=0.04", linewidth=2,
                                    edgecolor=colour, facecolor=colour + "1f"))  # "1f" = 12% opacity
        ax.text(x + 0.7, 2.4, text, ha="center", va="center")
        if i < len(steps) - 1:
            ax.annotate("", xy=(x + 1.78, 2.4), xytext=(x + 1.46, 2.4), arrowprops={"arrowstyle": "-|>", "color": "#444"})
    last = (len(steps) - 1) * 1.8
    # One arrow to each side of the guard box; each label is anchored away from the other so they cannot overlap.
    for dx, text, align in ((-0.6, "yes: flood mask", "right"), (0.6, "no: empty mask", "left")):
        ax.annotate("", xy=(last + 0.7 + dx, 0.6), xytext=(last + 0.7 + dx * 0.4, 1.5),
                    arrowprops={"arrowstyle": "-|>", "color": "#444"})
        ax.text(last + 0.7 + dx * 0.6, 0.3, text, ha=align)
    ax.text(0, 3.5, "No labels are used at any step. Baselines B1/B2 replace the three blue steps with a threshold.",
            color="#52514e")
    ax.set_xlim(-0.1, last + 2.6)
    ax.set_ylim(0, 3.8)
    ax.axis("off")
    save(fig, "fig1_processing_chain.png")


# ---- Figures 3, 4, 6: charts of the stored held-out results ------------------------------------------

def group_legend(ax, **kw):
    handles = [Line2D([], [], color=c, marker=m, linewidth=2.5, markersize=8, label=l)
               for l, c, m in (("Baseline threshold", GREY, "s"), ("Unguarded", ORANGE, "^"), ("Guarded", BLUE, "o"))]
    ax.legend(handles=handles, frameon=False, ncol=3, **kw)


def figure_3():
    fig, ax = plt.subplots(figsize=(8, 4.6))
    for row, (key, label, colour, marker) in enumerate(VARIANTS):
        b = flood_only(key)["headline_pooled_iou_bootstrap"]
        ax.plot([b["ci95_lo"], b["ci95_hi"]], [row, row], color=colour, linewidth=2.5, solid_capstyle="round")
        ax.plot(b["point"], row, marker=marker, color=colour, markersize=9, markeredgecolor="white", markeredgewidth=1.5)
        ax.text(b["ci95_hi"] + 0.008, row, f"{b['point']:.3f}", va="center", color="#52514e", fontsize=10)
    ax.set_yticks(range(len(VARIANTS)), [v[1] for v in VARIANTS])
    ax.invert_yaxis()
    ax.set_xlim(0, 0.55)
    n = flood_only("b1")["n_chips"]
    ax.set_xlabel(f"Pooled flood-only IoU (95% bootstrap CI), leave-one-event-out, {n} chips")
    light_grid(ax)
    group_legend(ax, loc="lower center", bbox_to_anchor=(0.4, 1.0))
    save(fig, "fig3_heldout_pooled_iou.png")


def figure_4():
    fig, ax = plt.subplots(figsize=(8, 4.4))
    for row, (key, label, colour, marker) in enumerate(VARIANTS):
        ff = flood_only(key)["flood_free"]
        pct = 100 * ff["pooled_fpr"]
        chips_with_alarm = round(ff["frac_chips_with_alarm"] * ff["n_chips"])
        ax.barh(row, pct, height=0.55, color=colour)
        ax.text(pct + 0.6, row, f"{pct:.2f}%  ({chips_with_alarm}/{ff['n_chips']} chips)", va="center",
                color="#52514e", fontsize=10)
    ax.set_yticks(range(len(VARIANTS)), [v[1] for v in VARIANTS])
    ax.invert_yaxis()
    ax.set_xlim(0, 60)
    ax.set_xlabel(f"Pixels wrongly flagged as flood on the {flood_only('b1')['flood_free']['n_chips']} "
                  f"flood-free held-out chips (%)")
    light_grid(ax)
    handles = [Patch(color=c, label=l) for l, c in (("Baseline threshold", GREY), ("Unguarded", ORANGE), ("Guarded", BLUE))]
    ax.legend(handles=handles, frameon=False, loc="lower right")
    save(fig, "fig4_floodfree_false_positive_rate.png")


def figure_6():
    b1, m2g = flood_only("b1")["per_event"], flood_only("m2g")["per_event"]
    events = sorted(m2g, key=lambda e: m2g[e]["pooled"]["iou"], reverse=True)  # best M2g event at the top
    fig, ax = plt.subplots(figsize=(8, 4.8))
    for row, ev in enumerate(events):
        a, b = b1[ev]["pooled"]["iou"], m2g[ev]["pooled"]["iou"]
        ax.plot([a, b], [row, row], color="#deddd6", linewidth=3, zorder=1)
        ax.plot(a, row, marker="s", color=GREY, markersize=9, markeredgecolor="white", markeredgewidth=1.5, zorder=2)
        ax.plot(b, row, marker="o", color=BLUE, markersize=9, markeredgecolor="white", markeredgewidth=1.5, zorder=3)
    ax.set_yticks(range(len(events)), [f"{ev.replace('-', ' ')} ({m2g[ev]['n_chips']})" for ev in events])
    ax.invert_yaxis()
    ax.set_xlim(0, 0.8)
    ax.set_xlabel("Pooled flood-only IoU on the held-out event (number of chips in brackets)")
    light_grid(ax)
    ax.legend(handles=[Line2D([], [], color=GREY, marker="s", linestyle="", markersize=9, label="B1 fixed threshold"),
                       Line2D([], [], color=BLUE, marker="o", linestyle="", markersize=9, label="M2g SLIC + k-means, guarded")],
              frameon=False, loc="lower right")
    save(fig, "fig6_per_event_iou.png")


# ---- Figures 5 and 7: one held-out chip each, frozen configuration of that chip's own fold -----------

def frozen_fold(event):
    """Frozen selections of the leave-one-event-out fold that held `event` out (so it never saw this chip)."""
    path = REPO_ROOT / "results" / "frozen" / "primary" / f"loeo_{event}.yaml"
    return yaml.safe_load(path.read_text())["selections"]


def slic_kmeans_prediction(rec, vv_raw, vh_raw):
    """
    Flood mask of M2 or M2g from one frozen record, on raw VV/VH in dB. Same steps as src/evaluate.py:
    preprocess, cluster, call the cluster with the lowest mean VV water, then apply the guard if there is one.
    """
    p = rec["preprocessing"]
    vv, vh = preprocess(vv_raw, vh_raw, p["clip_range_db"], p["median_window"])
    method = SlicKMeans(rec["k"], rec["n_segments"], rec["compactness"], rec["features"], rec["seed"],
                        n_init=rec["n_init"], max_iter=rec["max_iter"], slic_max_iter=rec["slic_max_num_iter"])
    cmap = method.cluster_map(vv, vh)
    water = water_cluster_lowest_mean_vv(cmap, vv)
    pred = np.zeros(vv.shape, bool) if water is None else (cmap == water)
    guard = rec.get("abstention_guard")
    return apply_abstention_ceiling(pred, vv, guard["ceiling_db"]) if guard else pred


def grey_image(vv):
    """VV in dB stretched between its 2nd and 98th percentile, as an RGB array (for display only)."""
    lo, hi = np.nanpercentile(vv, [2, 98])
    g = np.clip((np.nan_to_num(vv, nan=lo) - lo) / (hi - lo), 0, 1)
    return np.dstack([g, g, g])


def overlay(rgb, mask, colour, alpha=0.75):
    """Paint `mask` on a copy of `rgb` in `colour` (0 to 1 RGB), part-transparent so the radar shows through."""
    out = rgb.copy()
    out[mask] = (1 - alpha) * out[mask] + alpha * np.array(colour)
    return out


def figure_5():
    chip = read_chip(GUARD_CHIP)
    sel = frozen_fold("Paraguay")
    valid = image_valid_mask(chip["vv"], chip["vh"])
    domain, truth = evaluation_domain_and_truth(valid, chip["label"], chip["jrc"], MODE_FLOOD_ONLY)
    assert truth.sum() == 0, "this chip must have no flood-only truth, or it is not a flood-free example"
    preds = {v: slic_kmeans_prediction(sel[v], chip["vv"], chip["vh"]) for v in ("m2", "m2g")}
    share = {v: 100 * (preds[v] & valid).sum() / valid.sum() for v in preds}
    print(f"  {GUARD_CHIP}: valid pixels {100 * valid.mean():.1f}% of the chip; flagged share of valid pixels: "
          f"M2 {share['m2']:.1f}%, M2g {share['m2g']:.1f}% [measured]")
    base = grey_image(chip["vv"])
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.4))
    panels = [("(a) Sentinel-1 VV (dB)", base),
              (f"(b) Unguarded M2: {share['m2']:.1f}% of valid pixels\nwrongly flagged", overlay(base, preds["m2"], (0.85, 0.15, 0.15))),
              (f"(c) Guarded M2g: {share['m2g']:.1f}% of valid pixels\nflagged", overlay(base, preds["m2g"], (0.85, 0.15, 0.15)))]
    for ax, (title, img) in zip(axes, panels):
        ax.imshow(img)
        ax.set_title(title, fontsize=11)
        ax.axis("off")
    fig.suptitle(f"Chip {GUARD_CHIP}: flood-free held-out chip (no flood pixels in the hand label). "
                 f"A hand-picked illustration, not a typical chip.", fontsize=10.5)
    save(fig, "fig5_guard_effect_Paraguay_284928.png")


def figure_7():
    chip = read_chip(BEST_CHIP)
    rec = frozen_fold("Mekong")["m2g"]
    pred = slic_kmeans_prediction(rec, chip["vv"], chip["vh"])
    valid = image_valid_mask(chip["vv"], chip["vh"])
    domain, truth = evaluation_domain_and_truth(valid, chip["label"], chip["jrc"], MODE_FLOOD_ONLY)
    c = confusion_counts(pred, truth, domain)
    print(f"  {BEST_CHIP}: M2g IoU {iou(c):.4f}, precision {precision(c):.4f}, recall {recall(c):.4f} [measured]")
    base = grey_image(chip["vv"])
    pred_in, tp, fp, fn = pred & domain, pred & truth, pred & domain & ~truth, ~pred & truth
    err = overlay(overlay(overlay(base, tp, (0.15, 0.65, 0.15)), fp, (0.85, 0.15, 0.15)), fn, (0.16, 0.47, 0.84))
    fig, axes = plt.subplots(1, 4, figsize=(15, 4.3))
    panels = [("(a) Sentinel-1 VV (dB)", base), ("(b) M2g prediction", overlay(base, pred_in, (0.16, 0.47, 0.84))),
              ("(c) Hand-labelled flood truth", overlay(base, truth, (0.80, 0.62, 0.05))), ("(d) Error map", err)]
    for ax, (title, img) in zip(axes, panels):
        ax.imshow(img)
        ax.set_title(title, fontsize=11)
        ax.axis("off")
    axes[3].legend(handles=[Patch(color=(0.15, 0.65, 0.15), label="true positive"), Patch(color=(0.85, 0.15, 0.15), label="false positive"),
                            Patch(color=(0.16, 0.47, 0.84), label="false negative")], loc="lower right", fontsize=8)
    fig.suptitle(f"Chip {BEST_CHIP}, held out from tuning (leave-one-event-out). IoU {iou(c):.3f}, precision "
                 f"{precision(c):.3f}, recall {recall(c):.3f}. A hand-picked best case, not a typical chip.", fontsize=10.5)
    save(fig, "fig7_best_example_Mekong_16233.png")


# ---- Figure 8: Accra, frozen M2g on 3 June and 9 June 2020 -------------------------------------------

def load_accra_module():
    """scripts/06_accra_run.py holds the Accra readers; its file name starts with a digit, so import it by path."""
    spec = importlib.util.spec_from_file_location("accra06", REPO_ROOT / "scripts" / "06_accra_run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def figure_8():
    m06 = load_accra_module()
    aoi = m06.read_bands(m06.DATA / "aoi_mask.tif", ["aoi"])[0]["aoi"] > 0.5
    rec = m06.load_frozen()["m2g"]
    stored = {(r["image"], r["variant"]): r for r in json.loads((m06.OUT / "accra_tables.json").read_text())
              if r["sensitivity"] == "frozen"}
    fig, axes = plt.subplots(1, 2, figsize=(9, 9.5))
    for ax, (label, title) in zip(axes, (("2020-06-03_pre", "(a) 3 June 2020, six days before the event"),
                                         ("2020-06-09_event", "(b) 9 June 2020, event image"))):
        arrs, nodata, _ = m06.read_bands(m06.DATA / f"s1_{label}.tif", ["VV", "VH"])
        vv, vh = arrs["VV"], arrs["VH"]
        if nodata is not None:  # same nodata handling as scripts/06_accra_run.py
            vv[vv == nodata] = np.nan
            vh[vh == nodata] = np.nan
        flagged = slic_kmeans_prediction(rec, vv, vh) & aoi
        n_stored = stored[(label, "m2g")]["flagged_pixels"]
        assert int(flagged.sum()) == n_stored, f"{label}: {int(flagged.sum())} flagged pixels, stored table says {n_stored}"
        print(f"  {label}: M2g flagged {flagged.sum() * m06.PIXEL_HA:.2f} ha inside the catchment, equal to the stored table [measured]")
        ax.imshow(overlay(grey_image(vv), flagged, (0.16, 0.47, 0.84), alpha=1.0))
        ax.contour(aoi.astype(float), levels=[0.5], colors="yellow", linewidths=1.2)
        ax.set_title(f"{title}\nM2g flagged {flagged.sum() * m06.PIXEL_HA:.2f} ha", fontsize=11)
        ax.axis("off")
    fig.suptitle("Odaw catchment (yellow), frozen M2g; predicted flood in blue.\nUNVALIDATED: no ground truth.", fontsize=11)
    save(fig, "fig8_accra_m2g_3june_vs_9june.png")


if __name__ == "__main__":
    figure_1()
    figure_3()
    figure_4()
    figure_6()
    figure_5()
    figure_7()
    figure_8()
