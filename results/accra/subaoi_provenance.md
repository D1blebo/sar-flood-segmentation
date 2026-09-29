# Odaw sub-AOI (three named-place fragments): derivation (measured, reproducible, owner-decided pieces below)

**Proposed file:** `results/accra/subaoi_corridor.geojson` (MultiPolygon, 3 pieces, WGS84).

## Method

1. **Source**: OpenStreetMap, queried directly via the Nominatim search API
   (`nominatim.openstreetmap.org/search`, `format=jsonv2&polygon_geojson=1`), ODbL 1.0 licence. No
   coordinate was hand-drawn or guessed; every geometry below is a real Nominatim response, read and
   recorded, not estimated.
2. **Five of the seven named places resolved to real OSM administrative-boundary polygons** (`place`
   relations):

   | Place | OSM relation ID | Buffered area (km2) |
   |---|---|---|
   | Kaneshie | 20421178 | 2.215 |
   | Adabraka | 20411491 | 4.044 |
   | Alajo | 20423074 | 2.910 |
   | Avenor | 20421173 | 2.531 |
   | Darkuman | 20421327 | 6.819 |

3. **Two did not resolve to a neighbourhood polygon** in OSM and are represented by a point instead:
   - **Kwame Nkrumah Circle**: OSM has no polygon for this name; it only maps the interchange's road
     geometry (four `highway=primary` ways). Represented by the mean of those ways' Nominatim
     centroids: 5.5697 N, 0.2155 W.
   - **Odawna**: OSM has no neighbourhood polygon for this name either; the only matches are
     `Odawna Close`/`Odawna Street` (residential/service ways) and a separately-mapped `Odawna Market`
     polygon. The street centroid (5.5591 N, 0.2165 W) was used as the representative point, since it
     names the area rather than one building; the market polygon was found but not used.
   - "First Light" (mentioned alongside Kaneshie) returned no distinct OSM match and is treated as
     part of the Kaneshie polygon, not a separate feature.

4. **Buffer: 300 m, applied to all seven features alike** `[my choice]`. Reasoning: large enough to
   bridge the street-width/minor gaps between adjacent OSM administrative polygons (so genuinely
   neighbouring named areas merge into one shape rather than staying separated by a sliver), while
   small (roughly a fifth to a tenth of each neighbourhood's own extent) so it does not pull in
   unrelated areas. Not tuned against any output -- chosen before the buffer was run, based only on
   typical Accra block/street scale.
5. Each of the three resulting pieces was built separately (not dissolved into one shape): the
   Adabraka/Alajo/Avenor/Circle/Odawna group unioned together (they overlap at 300 m); Kaneshie on its
   own; Darkuman on its own.

## Owner's decision (recorded): three pieces, Darkuman clipped, buffer unchanged

The project owner reviewed the unclipped result (17.483 km2, Darkuman's buffer 37% outside the main
Odaw AOI) and decided: **keep three separate, explicitly disconnected pieces** (do not smooth or merge
them into one "corridor" shape); **leave the 300 m buffer and the isolated Kaneshie piece unchanged**
(no enlargement to force connectivity); **clip only Darkuman's buffered area to the main Odaw
HydroBASINS AOI boundary** (`results/accra/odaw_aoi.geojson`) so no sub-AOI area falls outside the
parent watershed.

**Final result, stated plainly as three disconnected pieces, total area 14.977 km2:**

| Piece | Members | Area (km2) | Notes |
|---|---|---|---|
| **core** | Adabraka + Alajo + Avenor + Kwame Nkrumah Circle + Odawna | 8.449 | connected at 300 m |
| **kaneshie** | Kaneshie | 2.215 | isolated, ~2 km from the core, left unchanged |
| **darkuman_clipped** | Darkuman, clipped to the main Odaw AOI | 4.313 | was 6.819 km2 unclipped; 2.506 km2 removed (confirmed 0 km2 now outside the main AOI) |

**This is not reported as a single connected corridor.** `results/accra/subaoi_corridor.geojson` is a
3-feature `FeatureCollection`, one feature per piece, each carrying its own `piece`/`members`/`area_km2`
properties -- not a dissolved MultiPolygon presented as one shape.

## Rule (a) confirmed unchanged for this sub-AOI (measured, not assumed)

Re-ran the same Sentinel-1 filter (`COPERNICUS/S1_GRD`, relative orbit 147, ascending, June 2020)
against the union of the three pieces. **The same three images intersect it**, with identical
timestamps (acquisition time is a property of the image, not the AOI, but this was verified rather
than assumed):

| Image | Time (UTC) | Offset from the 8-9 June peak window |
|---|---|---|
| 2020-06-03 (pre) | 18:17:25 | -131.7 to -123.7 h |
| **2020-06-09 (event)** | **18:18:05** | **+12.3 to +20.3 h -- unchanged, still passes rule (a)** |
| 2020-06-15 (next) | 18:17:25 | +156.3 to +164.3 h |

## What this sub-AOI is and is not

- It is a real, OSM-sourced, reproducible construction from the seven named places plus a stated
  buffer -- not hand-drawn coordinates.
- It is explicitly **three disconnected pieces**, by the owner's decision, not a single corridor shape.
- Every downstream number from this sub-AOI, once running is approved, still carries every existing
  Accra caveat: UNVALIDATED, no ground truth, frozen (not retuned) methods, agreement-not-accuracy
  against Sentinel-2.
