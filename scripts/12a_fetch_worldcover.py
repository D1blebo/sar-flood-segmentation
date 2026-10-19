"""
Amendment 19 (A19.6, A19.7): fetch ESA WorldCover v100 (2020, 10 m) on the same grid as the other Accra rasters,
with 06's own download() (EPSG:32630, 10 m, AOI bounds). Band 'Map': class 50 = built-up, 80 = permanent water.

  PYTHONPATH=. python scripts/12a_fetch_worldcover.py
"""
import importlib.util

import ee

from src.config import REPO_ROOT

_s = importlib.util.spec_from_file_location("m06", REPO_ROOT / "scripts" / "06_accra_run.py")
m06 = importlib.util.module_from_spec(_s)
_s.loader.exec_module(m06)
m06.ee_init()
bounds = m06.aoi_geometry().bounds(maxError=1, proj=m06.CRS).getInfo()["coordinates"]
wc = ee.ImageCollection("ESA/WorldCover/v100").first().select("Map")
m06.download(wc, bounds, m06.DATA / "worldcover_v100.tif", ["Map"], n_tiles=2)
print("fetched worldcover_v100.tif")
