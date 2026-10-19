"""
Amendment 19 (A19.6, A19-R2.4), Step 3: coastal positive control. UNVALIDATED: no ground truth.
Where do the pixels accepted by the frozen M2g on 9 June fall? Recomputed with 06's exact whole-raster procedure.

Categories, in this order so shares sum to 100%:
  (a) JRC permanent water (occurrence >= 50)
  (b) sea. OSM coastline query FAILED (Overpass HTTP 502 'at capacity', twice), so per A19-R2.4 the fallback is
      ESA WorldCover v100 class 80 (permanent water bodies), not already in (a). No other substitute.
  (c) Korle Lagoon: not computed (Nominatim/Overpass unavailable: Nominatim has no object named "Korle Lagoon",
      0 matches over 4 phrasings; Overpass returned 502). Bounded above by category (d), whose share is printed below.
      Nothing is claimed about where the lagoon lies relative to (a) or (b).
  (d) none of the above
  PYTHONPATH=. python scripts/12_accra_coastal_control.py
"""
import csv
import importlib.util
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

from src.config import REPO_ROOT
from src.io import image_valid_mask
from src.preprocess import preprocess

_s = importlib.util.spec_from_file_location("m06", REPO_ROOT / "scripts" / "06_accra_run.py")
m06 = importlib.util.module_from_spec(_s)
_s.loader.exec_module(m06)
LABEL = "UNVALIDATED: no ground truth"
EXPECTED = 144927
WC = {10: "tree cover", 20: "shrubland", 30: "grassland", 40: "cropland", 50: "built-up", 60: "bare/sparse",
      70: "snow/ice", 80: "permanent water", 90: "herbaceous wetland", 95: "mangroves", 100: "moss/lichen"}

arrs, nodata, _ = m06.read_bands(m06.DATA / "s1_2020-06-09_event.tif", ["VV", "VH"])
vv_raw, vh_raw = arrs["VV"], arrs["VH"]
vv_raw[vv_raw == nodata] = np.nan
vh_raw[vh_raw == nodata] = np.nan
rec = m06.load_frozen()["m2g"]
method, clip, median, guard = m06.build_method(rec)
vv, vh = preprocess(vv_raw, vh_raw, clip, median)
pred = m06.predict(method, vv, vh, guard)
n = int(pred.sum())
print(f"frozen M2g, 9 June, whole raster, no AOI restriction: {n} accepted pixels (expected {EXPECTED})")
if n != EXPECTED:
    raise SystemExit(f"STOP (A19.6): count {n} != {EXPECTED}; not continuing")

aoi = m06.read_bands(m06.DATA / "aoi_mask.tif", ["aoi"])[0]["aoi"] > 0.5
jrc = m06.read_bands(m06.DATA / "jrc_occurrence.tif", ["occurrence"])[0]["occurrence"] >= 50.0
wc = m06.read_bands(m06.DATA / "worldcover_v100.tif", ["Map"])[0]["Map"].astype(int)
wc80 = wc == 80

a = pred & jrc
b = pred & ~jrc & wc80
d = pred & ~jrc & ~wc80
rows = []
def add(name, mask, indep=False):
    k = int(mask.sum())
    rows.append({"label": LABEL, "item": name, "pixels": k, "share_of_accepted": k / n, "hectares": k * m06.PIXEL_HA,
                 "pixels_inside_AOI": int((mask & aoi).sum()), "pixels_outside_AOI": int((mask & ~aoi).sum())})
add("(a) JRC permanent water", a)
add("(b) sea = WorldCover v100 class 80, not in (a) [FALLBACK per A19-R2.4]", b)
add(f"(c) Korle Lagoon: not computed (Nominatim/Overpass unavailable); bounded above by category (d) = {100 * d.sum() / n:.1f}%", np.zeros_like(pred))
for k in ("pixels", "share_of_accepted", "hectares", "pixels_inside_AOI", "pixels_outside_AOI"):
    rows[-1][k] = "not computed"  # (c) is not a measured zero
add("(d) none of the above", d)
add("total accepted", pred)
add("independent: in JRC (overlaps allowed)", pred & jrc)
add("independent: in WorldCover class 80 (overlaps allowed)", pred & wc80)
add("independent: in both JRC and WorldCover 80", pred & jrc & wc80)
add("inside AOI (all categories)", pred & aoi)
add("outside AOI (all categories)", pred & ~aoi)
if d.sum() / n > 0.5:
    for code in sorted(set(wc[d].tolist())):
        add(f"(d) land cover, WorldCover v100 class {code} {WC.get(code, '?')}", d & (wc == code))
else:
    print("(d) <= 50%: land-cover breakdown not triggered")
for r in rows:
    if r["pixels"] == "not computed":
        print(f"{r['item'][:110]}: not computed"); continue
    print(f"{r['item'][:78]:78s} {r['pixels']:7d} {100*r['share_of_accepted']:6.2f}%  {r['hectares']:8.2f} ha  in AOI {r['pixels_inside_AOI']:6d}  out {r['pixels_outside_AOI']:6d}")
out = REPO_ROOT / "results" / "accra_coastal_control.csv"
with open(out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

# figure: whole scene (block max for display) + zoom on the accepted pixels' bounding box
ys, xs = np.nonzero(pred)
print(f"accepted-pixel bbox: rows {ys.min()}-{ys.max()}, cols {xs.min()}-{xs.max()}")
col = {"a": (0.0, 0.447, 0.698), "b": (0.337, 0.706, 0.914), "d": (0.835, 0.369, 0.0)}
def render(sl, f):
    def bm(x):
        x = x[sl]; h, w = (x.shape[0] // f) * f, (x.shape[1] // f) * f
        return x[:h, :w].reshape(h // f, f, w // f, f).max(axis=(1, 3))
    img = np.ones(bm(aoi).shape + (3,))
    img[bm(wc80)] = (0.80, 0.88, 0.95)
    img[bm(aoi)] = np.where(bm(wc80)[bm(aoi)][:, None], np.array([0.80, 0.88, 0.95]), np.array([0.92, 0.92, 0.92]))
    for k, m in (("d", d), ("b", b), ("a", a)):
        img[bm(m)] = col[k]
    return img, bm(aoi)
fig, axs = plt.subplots(1, 2, figsize=(11, 10), gridspec_kw={"width_ratios": [1, 1.5]})
img, bmaoi = render((slice(None), slice(None)), 4)
axs[0].imshow(img, interpolation="nearest"); axs[0].contour(bmaoi.astype(float), [0.5], colors="k", linewidths=0.7)
axs[0].set_title("whole downloaded scene (4x4 block max)", fontsize=9); axs[0].set_axis_off()
pad = 60
sl = (slice(max(ys.min() - pad, 0), ys.max() + pad), slice(max(xs.min() - pad, 0), xs.max() + pad))
img2, bmaoi2 = render(sl, 2)
axs[1].imshow(img2, interpolation="nearest"); axs[1].contour(bmaoi2.astype(float), [0.5], colors="k", linewidths=0.7)
axs[1].set_title("zoom on accepted pixels (2x2 block max)", fontsize=9); axs[1].set_axis_off()
fig.suptitle("UNVALIDATED: no ground truth. Pixels accepted by frozen M2g on 9 June 2020 (whole raster), by category\n"
             "Sea = WorldCover class 80 fallback (OSM coastline query failed); Korle Lagoon (c) not computed", fontsize=9.5)
fig.legend(handles=[Patch(color=col["a"], label=f"(a) JRC permanent water  {int(a.sum())}"),
                    Patch(color=col["b"], label=f"(b) WorldCover water, not JRC  {int(b.sum())}"),
                    Patch(color=col["d"], label=f"(d) none of these  {int(d.sum())}"),
                    Patch(color=(0.92, 0.92, 0.92), label="Odaw AOI (black outline)"),
                    Patch(color=(0.80, 0.88, 0.95), label="WorldCover water (context)")],
           loc="lower center", ncol=3, fontsize=8, frameon=False)
fig.savefig(REPO_ROOT / "results" / "accra_coastal_control_map.png", dpi=130, bbox_inches="tight")
print("saved results/accra_coastal_control.csv and results/accra_coastal_control_map.png")
