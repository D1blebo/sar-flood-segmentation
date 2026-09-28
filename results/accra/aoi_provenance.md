# Odaw catchment AOI: derivation (measured, reproducible)

**Proposed AOI file:** `results/accra/odaw_aoi.geojson` (single polygon, 96 vertices, WGS84).

## Method

1. **Outlet point** (measured, read directly from the source): Korle Lagoon, 5.5344 N, 0.2196 W
   (Wikipedia, "Korle Lagoon" — the Odaw River's mouth; a tertiary source, used only to anchor the
   watershed delineation below, not as the basin boundary itself).
2. **Watershed dataset** (measured, downloaded and inspected directly): HydroBASINS v1c, Africa,
   level 12, standard product (Lehner, B., Grill, G. (2013), "Global river hydrography and network
   routing", *Hydrological Processes*, 27(15): 2171-2186, doi:10.1002/hyp.9740).
   Downloaded from `https://data.hydrosheds.org/file/hydrobasins/standard/hybas_af_lev12_v1c.zip`
   (118.8 MB, 230,028 polygons for Africa).
3. Found the level-12 unit containing the outlet point by spatial query: **HYBAS_ID 1120023430**
   (PFAF_ID 145101008100), a coastal sink (`NEXT_DOWN = 0`), whose own `UP_AREA` attribute
   (HydroBASINS' precomputed total upstream drainage area) is **260.8 km2**.
4. Traced every level-12 unit upstream of it via the `NEXT_DOWN` chain (breadth-first over the full
   Africa attribute table, 230,028 rows). Result: exactly **2 units** — HYBAS_ID 1120023430 itself
   (129.2 km2) and HYBAS_ID 1122029290 (131.5 km2, `NEXT_DOWN = 1120023430`). Their `SUB_AREA` sum,
   260.7 km2, matches the target unit's own `UP_AREA` field (260.8 km2) almost exactly, confirming
   the trace is complete and correct.
5. Dissolved (unioned) the two polygons with GDAL/OGR (`ogr2ogr ... -dialect sqlite -sql
   "SELECT ST_Union(geometry) ..."`). The union is a single, non-multipart polygon (no gap between
   the two units), 96 vertices, saved as `odaw_aoi.geojson`.

## Cross-check against the literature (labelled: not independently verified by me)

A web search surfaced a paper ("The Identification of Flood-Prone Areas in Accra, Ghana Using a
Hydrological Screening Method", published in *Earth* (MDPI), https://www.mdpi.com/2624-795X/5/3/38 —
**authors and exact year not confirmed by me**, since I could not open the page; the title and venue
come from the search index, not from reading the paper) reporting the Odaw basin's delineation as
extending "from Aburi in the north at 5 deg 51' N to the
river's outlet into Korle Lagoon at 5 deg 31' N, with western-eastern extent from Ofankor at
0 deg 17' W to Adenta at 0 deg 9' W" (roughly 5.52-5.85 N, -0.283 to -0.15 E), and basin-area figures
of 204-275 km2 across cited studies.

**I could not read this paper directly** (mdpi.com returned HTTP 403 to both WebFetch and a direct
curl fetch, and the Springer Nature alternative redirected to a login wall), so that bounding
description is a search-engine synthesis of the page, not text I verified myself — it is reported
here only as context, not as a source for the AOI.

The HydroBASINS-derived polygon above was computed independently of that description. Its bounding
box is **5.5292-5.8417 N, -0.2840 to -0.150 E** and its area is **260.7-260.8 km2** — both fall
inside the unverified literature ranges quoted above, which is a reassuring (but not a substitute
for direct verification) cross-check.

## What this AOI is and is not

- It is the HydroBASINS watershed draining to the Odaw's mouth at Korle Lagoon: a real, downloaded,
  inspectable, peer-reviewed-dataset-derived polygon.
- It is **not** independently verified against a Ghanaian government hydrological survey or a
  ground-truthed catchment boundary; no such source was found or accessed in this project.
- HydroBASINS resolution (level 12) means the boundary follows global 15-arcsecond DEM-derived
  drainage, not local infrastructure or administrative boundaries; expect some disagreement with any
  locally surveyed catchment map at the scale of individual streets.
