"""
Amendment 19 (A19.2): fetch the two extra orbit-147 scenes (22 and 28 May 2020) with 06's own download()
(same AOI bounds, EPSG:32630, 10 m, VV+VH). Scene IDs are the ones fixed in the protocol.

  PYTHONPATH=. python scripts/10a_fetch_may_scenes.py
"""
import importlib.util

import ee

from src.config import REPO_ROOT

_s = importlib.util.spec_from_file_location("m06", REPO_ROOT / "scripts" / "06_accra_run.py")
m06 = importlib.util.module_from_spec(_s)
_s.loader.exec_module(m06)

SCENES = {
    "2020-05-22_ref": "COPERNICUS/S1_GRD/S1B_IW_GRDH_1SDV_20200522T181724_20200522T181749_021698_0292FB_9ACA",
    "2020-05-28_ref": "COPERNICUS/S1_GRD/S1A_IW_GRDH_1SDV_20200528T181804_20200528T181833_032769_03CBB7_64D8",
}

m06.ee_init()
bounds = m06.aoi_geometry().bounds(maxError=1, proj=m06.CRS).getInfo()["coordinates"]
for label, asset in SCENES.items():
    m06.download(ee.Image(asset).select(["VV", "VH"]), bounds, m06.DATA / f"s1_{label}.tif", ["VV", "VH"])
    print("fetched", label, flush=True)
