"""
Amendment 19 (A19.7, A19-R5), Step 4: point checks at reported flood sites vs 200 built-up control points.
UNVALIDATED: no ground truth; a descriptive screen, not validation. Interpretation limit (A19-R5.4): read ONLY as a test
of the 8-9 June overnight storm; the heaviest IMERG rain is 10 June 15:30-18:00 UTC, after the 9 June pass; 15 June values are
not evidence about 9 June.

  PYTHONPATH=. python scripts/14_accra_point_checks.py
"""
import csv
import importlib.util

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from rasterio.warp import transform as rtransform
from scipy.ndimage import binary_erosion

from src.config import REPO_ROOT
from src.preprocess import preprocess

_s = importlib.util.spec_from_file_location("cd10", REPO_ROOT / "scripts" / "10_accra_cd_baseline.py")
cd = importlib.util.module_from_spec(_s)
_s.loader.exec_module(cd)
m06, m07 = cd.m06, cd.m07
LABEL = "UNVALIDATED: no ground truth"
SEED, N_CONTROLS, MIN_SEP_M, RADII = 20200609, 200, 100.0, (50, 100)

# (site, role, OSM object, lat, lon) -- coordinates exactly as in A19-R5.2
SITES = [
    ("Odawna", "headline", "way 664056985 Odawna Market", 5.5653020, -0.2172281),
    ("Odawna", "alternative centroid", "way 126879329 Odawna Close (residential)", 5.5587104, -0.2160583),
    ("Odawna", "alternative centroid", "way 1488444430 Odawna Close (service)", 5.5594046, -0.2170041),
    ("Kwame Nkrumah Circle", "headline", "node 1133566054 Kwame Nkrumah Interchange", 5.5695876, -0.2153479),
    ("Kwame Nkrumah Circle", "alternative centroid", "way 11664610", 5.5692221, -0.2152750),
    ("Kwame Nkrumah Circle", "alternative centroid", "way 510252753", 5.5697463, -0.2150897),
    ("Kwame Nkrumah Circle", "alternative centroid", "way 510252751", 5.5699063, -0.2155186),
    ("Kwame Nkrumah Circle", "alternative centroid", "way 510252749", 5.5694954, -0.2157619),
    ("Kwame Nkrumah Circle", "alternative centroid", "mean of the four segment points (computed)",
     np.mean([5.5692221, 5.5697463, 5.5699063, 5.5694954]), np.mean([-0.2152750, -0.2150897, -0.2155186, -0.2157619])),
    ("Taifa", "headline", "node 9703337660 Taifa (place=suburb)", 5.6566514, -0.2500244),
    ("Taifa", "alternative centroid", "node 5008220723 Taifa bus stop", 5.6583888, -0.2528530),
    ("Taifa", "alternative centroid", "way 628294317 Accra Nsawam Highway", 5.6474190, -0.2488051),
    ("Taifa", "alternative centroid", "way 1517822465 Charismatic Baptist Church", 5.6541196, -0.2555847),
    ("Lapaz", "headline", "node 5566513301 Lapaz (place=suburb)", 5.6073648, -0.2486900),
]

# ---- rasters (all on the same 3462x1480 EPSG:32630 10 m grid, verified earlier)
aoi_arr, _, tr = m06.read_bands(m06.DATA / "aoi_mask.tif", ["aoi"])
aoi = aoi_arr["aoi"] > 0.5
jrc = m06.read_bands(m06.DATA / "jrc_occurrence.tif", ["occurrence"])[0]["occurrence"] >= 50.0
wc = m06.read_bands(m06.DATA / "worldcover_v100.tif", ["Map"])[0]["Map"].astype(int)
sub = m07.rasterize_pieces(m07.load_pieces(), aoi.shape, tr)
H, W = aoi.shape
X = tr.c + tr.a * (np.arange(W) + 0.5)   # pixel-centre easting per column
Y = tr.f + tr.e * (np.arange(H) + 0.5)   # pixel-centre northing per row

v3, h3, ok3 = cd.load_scene("2020-06-03")
v9, h9, ok9 = cd.load_scene("2020-06-09")
v15, h15, ok15 = cd.load_scene("2020-06-15")
valid = ok3 & ok9 & ok15 & ~jrc
dvv = v9 - v3
cd_masks, _, _ = cd.pair_masks("2020-06-03", "2020-06-09")

# frozen predictions on the 9 June image (A19-R5.3)
arrs, nodata, _ = m06.read_bands(m06.DATA / "s1_2020-06-09_event.tif", ["VV", "VH"])
vv_raw, vh_raw = arrs["VV"], arrs["VH"]
vv_raw[vv_raw == nodata] = np.nan
vh_raw[vh_raw == nodata] = np.nan
sel = m06.load_frozen()
flags = {}
for variant in ("b1", "b2g_vh", "m1g", "m2g"):
    method, clip, median, guard = m06.build_method(sel[variant])
    p_vv, p_vh = preprocess(vv_raw, vh_raw, clip, median)
    flags[variant] = m06.predict(method, p_vv, p_vh, guard)
    print(f"frozen {variant}: {int(flags[variant].sum())} px flagged on 9 June (whole raster)", flush=True)
flags["cd"], flags["cd_guarded"] = cd_masks["cd"], cd_masks["cd_guarded"]


def to_xy(lat, lon):
    x, y = rtransform("EPSG:4326", m06.CRS, [lon], [lat])
    return x[0], y[0]


def window(x, y, r):
    """Rows/cols of pixels whose centre is within r metres of (x, y)."""
    c0, c1 = np.searchsorted(X, x - r), np.searchsorted(X, x + r, side="right")
    r_idx = np.where((Y >= y - r) & (Y <= y + r))[0]
    cols = np.arange(c0, c1)
    if len(r_idx) == 0 or len(cols) == 0:
        return np.array([], int), np.array([], int)
    rr, cc = np.meshgrid(r_idx, cols, indexing="ij")
    keep = (X[cc] - x) ** 2 + (Y[rr] - y) ** 2 <= r * r
    return rr[keep], cc[keep]


def stats(x, y, r):
    rr, cc = window(x, y, r)
    ok = valid[rr, cc]
    rr, cc = rr[ok], cc[ok]
    n = len(rr)
    out = {"n_valid_pixels": n}
    if n == 0:
        return {**out, **{k: float("nan") for k in ("median_VV_3jun_dB", "median_VV_9jun_dB", "median_VV_15jun_dB",
                "median_dVV_3to9_dB", "frac_B1", "frac_B2g_VH", "frac_M1g", "frac_M2g", "frac_CD", "frac_CD_guarded")}}
    out.update({"median_VV_3jun_dB": float(np.median(v3[rr, cc])), "median_VV_9jun_dB": float(np.median(v9[rr, cc])),
                "median_VV_15jun_dB": float(np.median(v15[rr, cc])), "median_dVV_3to9_dB": float(np.median(dvv[rr, cc])),
                "frac_B1": float(flags["b1"][rr, cc].mean()), "frac_B2g_VH": float(flags["b2g_vh"][rr, cc].mean()),
                "frac_M1g": float(flags["m1g"][rr, cc].mean()), "frac_M2g": float(flags["m2g"][rr, cc].mean()),
                "frac_CD": float(flags["cd"][rr, cc].mean()), "frac_CD_guarded": float(flags["cd_guarded"][rr, cc].mean())})
    return out


# ---- controls (A19.7, A19-R5.2): seed 20200609, built-up (WorldCover 50), 100 m buffer inside AOI, >=100 m from all sites and each other
site_xy = [to_xy(s[3], s[4]) for s in SITES]
yy, xx = np.mgrid[-10:11, -10:11]
disk = (yy ** 2 + xx ** 2) <= 100  # 10 px = 100 m radius on 10 m pixels
inner = binary_erosion(aoi, structure=disk, border_value=0)
cand = inner & (wc == 50) & valid
cr, cc_ = np.nonzero(cand)
print(f"control candidates: {len(cr)} pixels (built-up, 100 m buffer inside AOI, valid in all 3 scenes, not JRC)", flush=True)
rng = np.random.default_rng(SEED)
order = rng.permutation(len(cr))
sx, sy = np.array([p[0] for p in site_xy]), np.array([p[1] for p in site_xy])
acc = []
for i in order:
    x, y = X[cc_[i]], Y[cr[i]]
    if np.min(np.hypot(sx - x, sy - y)) < MIN_SEP_M:
        continue
    if acc and np.min(np.hypot(np.array([a[0] for a in acc]) - x, np.array([a[1] for a in acc]) - y)) < MIN_SEP_M:
        continue
    acc.append((x, y, int(cr[i]), int(cc_[i])))
    if len(acc) == N_CONTROLS:
        break
if len(acc) < N_CONTROLS:
    raise SystemExit(f"STOP (A19.7): only {len(acc)} controls could be accepted")
print(f"controls accepted: {len(acc)}", flush=True)

rows = []
ctrl = {r: [stats(x, y, r) for x, y, _, _ in acc] for r in RADII}
for r in RADII:
    for k, (x, y, row, col) in enumerate(acc):
        rows.append({"label": LABEL, "kind": "control", "site": f"control_{k + 1:03d}", "centroid_role": "control",
                     "osm_object": "", "lat": "", "lon": "", "buffer_m": r, "in_AOI": True, "sub_area": "",
                     **ctrl[r][k], "pctile_rank_VV9": "", "pctile_rank_dVV": "", "stands_out_VV9": "", "stands_out_dVV": ""})


def midrank(val, ref):
    ref = np.array(ref, float)
    return 100.0 * ((ref < val).sum() + 0.5 * (ref == val).sum()) / len(ref)


site_rows = {}
for (site, role, obj, lat, lon), (x, y) in zip(SITES, site_xy):
    c, rr_ = int((x - tr.c) // tr.a), int((y - tr.f) // tr.e)
    inside = bool(0 <= rr_ < H and 0 <= c < W and aoi[rr_, c])
    sa = [k for k, v in sub.items() if 0 <= rr_ < H and 0 <= c < W and v[rr_, c]]
    for r in RADII:
        st = stats(x, y, r)
        p_vv = midrank(st["median_VV_9jun_dB"], [d["median_VV_9jun_dB"] for d in ctrl[r]]) if st["n_valid_pixels"] else float("nan")
        p_dv = midrank(st["median_dVV_3to9_dB"], [d["median_dVV_3to9_dB"] for d in ctrl[r]]) if st["n_valid_pixels"] else float("nan")
        row = {"label": LABEL, "kind": "site", "site": site, "centroid_role": role, "osm_object": obj, "lat": lat, "lon": lon,
               "buffer_m": r, "in_AOI": inside, "sub_area": "+".join(sa) or "none", **st, "pctile_rank_VV9": p_vv,
               "pctile_rank_dVV": p_dv, "stands_out_VV9": bool(p_vv < 5 or p_vv > 95), "stands_out_dVV": bool(p_dv < 5 or p_dv > 95)}
        rows.append(row)
        site_rows[(site, role, obj, r)] = row

out = REPO_ROOT / "results" / "accra_point_checks.csv"
with open(out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

for r in RADII:
    print(f"\n=== buffer {r} m (headline = 50 m) ===")
    for (site, role, obj, rr), row in site_rows.items():
        if rr != r:
            continue
        print(f"{site:21s} {role:21s} {obj[:44]:44s} n={row['n_valid_pixels']:3d} VV3={row['median_VV_3jun_dB']:7.2f} VV9={row['median_VV_9jun_dB']:7.2f} "
              f"VV15={row['median_VV_15jun_dB']:7.2f} dVV={row['median_dVV_3to9_dB']:+6.2f} | B1 {row['frac_B1']:.2f} B2g {row['frac_B2g_VH']:.2f} "
              f"M1g {row['frac_M1g']:.2f} M2g {row['frac_M2g']:.2f} CD {row['frac_CD']:.2f} gCD {row['frac_CD_guarded']:.2f} | "
              f"pct VV9 {row['pctile_rank_VV9']:5.1f} dVV {row['pctile_rank_dVV']:5.1f} out: {row['stands_out_VV9']}/{row['stands_out_dVV']}")
    cv9 = np.array([d["median_VV_9jun_dB"] for d in ctrl[r]]); cdv = np.array([d["median_dVV_3to9_dB"] for d in ctrl[r]])
    print(f"controls ({r} m): VV9 median {np.median(cv9):.2f} dB (p5 {np.percentile(cv9, 5):.2f}, p95 {np.percentile(cv9, 95):.2f}); "
          f"dVV median {np.median(cdv):+.2f} dB (p5 {np.percentile(cdv, 5):+.2f}, p95 {np.percentile(cdv, 95):+.2f}); "
          f"n_valid min/median/max {min(d['n_valid_pixels'] for d in ctrl[r])}/{int(np.median([d['n_valid_pixels'] for d in ctrl[r]]))}/{max(d['n_valid_pixels'] for d in ctrl[r])}")

# ---- figure: control dVV histogram (50 m headline) with the four headline sites marked
cdv50 = np.array([d["median_dVV_3to9_dB"] for d in ctrl[50]])
fig, ax = plt.subplots(figsize=(9, 4.6))
ax.hist(cdv50, bins=24, color="#0072B2", alpha=0.85, edgecolor="white", linewidth=0.6)
top = ax.get_ylim()[1]
for i, ((site, role, obj, rr), row) in enumerate([(k, v) for k, v in site_rows.items() if k[1] == "headline" and k[3] == 50]):
    ax.axvline(row["median_dVV_3to9_dB"], color="black", linewidth=1.1)
    ax.text(row["median_dVV_3to9_dB"], top * (0.97 - 0.11 * i), f" {site}\n {row['median_dVV_3to9_dB']:+.2f} dB, pctile {row['pctile_rank_dVV']:.0f}",
            fontsize=7.5, va="top", ha="left", bbox=dict(facecolor="white", edgecolor="none", alpha=0.85, pad=1.5))
ax.set_xlabel("median dVV, 3 -> 9 June 2020, 50 m buffer (dB; median-3 filtered)")
ax.set_ylabel("control points (n = 200)")
ax.spines[["top", "right"]].set_visible(False)
ax.set_title("UNVALIDATED: no ground truth. dVV at 200 built-up control points, with the four reported sites (black lines)\n"
             "Descriptive screen only; read as a test of the 8-9 June overnight storm (heaviest rain is 10 June, after the pass)", fontsize=9)
fig.savefig(REPO_ROOT / "results" / "accra_point_checks_dvv_hist.png", dpi=130, bbox_inches="tight")
print("\nsaved results/accra_point_checks.csv and results/accra_point_checks_dvv_hist.png")
