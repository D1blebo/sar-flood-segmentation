"""
Amendment 19 Step 2 companions. (1) Map of the event-pair (3 -> 9 June) CD result with the AOI and sub-AOIs
outlined. (2) POST-HOC, NOT PRE-DECLARED diagnostic: median dVV per pair over the full-AOI domain, to see whether a
per-pair radiometric offset (e.g. S1A vs S1B) could explain the event/control contrasts. UNVALIDATED.

  PYTHONPATH=. python scripts/10b_accra_cd_map_and_offsets.py
"""
import importlib.util
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from src.config import REPO_ROOT

_s = importlib.util.spec_from_file_location("cd10", REPO_ROOT / "scripts" / "10_accra_cd_baseline.py")
cd = importlib.util.module_from_spec(_s)
_s.loader.exec_module(cd)
m06, m07 = cd.m06, cd.m07

aoi_arr, _, transform = m06.read_bands(cd.DATA / "aoi_mask.tif", ["aoi"])
aoi = aoi_arr["aoi"] > 0.5
jrc = m06.read_bands(cd.DATA / "jrc_occurrence.tif", ["occurrence"])[0]["occurrence"] >= 50.0
sub = m07.rasterize_pieces(m07.load_pieces(), aoi.shape, transform)

# (2) post-hoc offsets
off = {}
for pair_set, role, a, b in cd.PAIRS:
    masks, ok, d = cd.pair_masks(a, b)
    dom = ok & ~jrc & aoi
    off[f"{pair_set}|{role}|{a}->{b}"] = {"median_dVV_dB": float(np.median(d[dom])), "mean_dVV_dB": float(d[dom].mean())}
    print(f"{pair_set:28s} {role:10s} {a}->{b}  median dVV = {np.median(d[dom]):+.3f} dB  mean = {d[dom].mean():+.3f}")
(REPO_ROOT / "results" / "accra" / "accra_cd_POSTHOC_median_dvv.json").write_text(json.dumps(
    {"label": "POST-HOC DIAGNOSTIC, NOT PRE-DECLARED, UNVALIDATED", "full_AOI_domain": off}, indent=1))

# (1) map, event pair
masks, ok, d = cd.pair_masks("2020-06-03", "2020-06-09")
dom = ok & ~jrc & aoi
f = 4  # display only: 4x4 block max so isolated 10 m pixels stay visible; counts in the CSV are at full resolution
def blockmax(a):
    h, w = (a.shape[0] // f) * f, (a.shape[1] // f) * f
    return a[:h, :w].reshape(h // f, f, w // f, f).max(axis=(1, 3))
cdm, gm = blockmax(masks["cd"] & dom), blockmax(masks["cd_guarded"] & dom)
bg = blockmax(aoi)
img = np.full(bg.shape + (3,), 1.0)
img[bg] = (0.90, 0.90, 0.90)
img[cdm] = (0.902, 0.624, 0.0)      # Okabe-Ito orange: CD
img[gm] = (0.0, 0.447, 0.698)       # Okabe-Ito blue: guarded CD (drawn on top)
fig, ax = plt.subplots(figsize=(6.2, 12.5))
ax.imshow(img, interpolation="nearest")
ax.contour(bg.astype(float), levels=[0.5], colors="black", linewidths=0.8)
for name, m in sub.items():
    ax.contour(blockmax(m).astype(float), levels=[0.5], colors="#444444", linewidths=1.0)
    ys, xs = np.nonzero(blockmax(m))
    ax.annotate(name.replace("_clipped", ""), (xs.mean(), ys.mean()), xytext=(xs.mean() + 40, ys.mean() - 25), fontsize=8,
                arrowprops=dict(arrowstyle="-", lw=0.6))
ax.set_axis_off()
n_cd, n_g = int((masks["cd"] & dom).sum()), int((masks["cd_guarded"] & dom).sum())
ax.set_title("UNVALIDATED: no ground truth. Change detection, 3 -> 9 June 2020 (orbit 147)\n"
             "dVV < -3 dB (assumed threshold), median-3 filtered, JRC water removed", fontsize=9.5)
from matplotlib.patches import Patch
ax.legend(handles=[Patch(color=(0.902, 0.624, 0.0), label=f"CD: dVV < -3 dB ({n_cd * m06.PIXEL_HA:.0f} ha)"),
                   Patch(color=(0.0, 0.447, 0.698), label=f"guarded CD: also VV(9 Jun) < -15 dB ({n_g * m06.PIXEL_HA:.0f} ha)"),
                   Patch(color=(0.90, 0.90, 0.90), label="Odaw AOI, not flagged (outlined black; sub-areas outlined grey)")],
          loc="lower left", fontsize=7.5, frameon=True)
fig.text(0.5, 0.012, f"Display only: {f}x{f}-pixel block maximum so single 10 m pixels remain visible. Hectares are counted at full resolution.",
         ha="center", fontsize=7)
fig.savefig(REPO_ROOT / "results" / "accra_cd_event_pair_map.png", dpi=130, bbox_inches="tight")
print("saved results/accra_cd_event_pair_map.png")
