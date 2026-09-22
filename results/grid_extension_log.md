# Grid-extension log (protocol Amendment 2, item A2.5)

One dated entry per extension: tuning set, parameter, old edge, new value, and the tuning-set criterion
value at the old edge and at the new value. Decided per tuning set, from that tuning set's data only.

## 2026-09-20, after Stage 1 (A6.5): rule triggered, NOT yet executed (waiting for the project owner)

- **median window**, upper edge 7: winner at the edge in 12/12 tuning sets for B2-VV, B2-VH, B2g (both), M2; in 10/12 for M1; in 4/12 for M1g and M2g.
  Proposed step: 7 to 9 (4 new options, 1,760 units, about 21 min).
- **guard ceiling**, permissive edge -12: winner at the edge in 12/12 tuning sets for every guarded variant. Proposed step: -12 to -9 (needs a 7,040-unit re-run, about 81 min).
- Nothing else is at an edge: B1 thresholds -14/-15 are interior; the clip is categorical and never extended.


## 2026-09-20 to 21, after the amended criterion (A7): every trigger, executed or not

Rankings under the primary criterion (pooled flood-only IoU over all tuning chips) and the sensitivity criterion (declared, mean per-chip IoU); extensions are decided per criterion, tuning set and variant.

| Parameter | Step | Status | Reason and numbers |
|---|---|---|---|
| median window | 7 to 9 | EXECUTED | winners at 7 in both criteria; 1,760 units, 22.2 min |
| median window | 9 to 11 | EXECUTED | winners moved to 9 (primary: B1 12 sets extended, B2 VV/VH 12, B2g 11, M1 12, M1g 7, M2 12; sensitivity: B2 12, B2g 12, M1 10, M1g 4, M2 12, M2g 4); 1,760 units, 23.4 min |
| median window | 11 to 13 | NOT EXECUTED | cap of 2 extensions reached (A2.5). Winners still at 11: primary B2 VH 11/12, B1 1/12, B2 VV 1/12, B2g VH 1/12, M2 2/12; sensitivity M2 11/12, M2g 2/12 |
| guard ceiling | -12 to -9 | NOT EXECUTED | primary: no longer triggers (winners at -12: 0/12 in every guarded variant). sensitivity: triggers 12/12 but not run, by declaration in A7.4 (the guard cannot win under that criterion; the run would take about 96 min to approach the plain method) |
| guard ceiling | -18 to -21 | NOT EXECUTED, WAITING FOR THE PROJECT OWNER | primary: M1g winner at -18 in 3/12 tuning sets (`loeo:Bolivia`, `loeo:India`, `official_valid`). B2g VV/VH and M2g: 0/12 at an edge. Cost about 96 min (M1 over 24 options x 440 chips) |
| B1 threshold | +/- 1 dB | NOT TRIGGERED | winners -16, -15, -14 dB; grid edges -30 and -8 |
| clip | n/a | NEVER EXTENDED | categorical |


## 2026-09-21, after Amendment 8: ceiling extension executed, median optimum logged as unresolved

| Parameter | Step | Status | Reason and numbers |
|---|---|---|---|
| guard ceiling | -18 to -21 | **EXECUTED** (derived from the stored mean VV, exact) | primary criterion: M1g winner at -18 in 3/12 tuning sets (`loeo:Bolivia`, `loeo:India`, `official_valid`). Result: -21 scored LOWER than -18 in all three, so the winners stay at -18, now interior; no further trigger. B2g VV/VH and M2g: no set at an edge |
| guard ceiling | -12 to -9 | NOT EXECUTED | primary: no winner at -12 (0/12 in every guarded variant). Sensitivity criterion: triggers 12/12 but remains not run by declaration (A7.4), although now free |
| median window | 11 to 13 | NOT EXECUTED, **OPTIMUM UNRESOLVED** | cap of 2 extensions reached (A2.5; owner's decision A8.2). Winners still at 11: primary B2 VH 11/12 (B1, B2 VV, B2g VH 1/12 each; M2 2/12); sensitivity M2 11/12 (M2g 2/12). **Median windows of 9 to 11 pixels are 90 to 110 m and may blur narrow drains and small water bodies**; state this wherever such a configuration is used. Accra: run with a small-window sensitivity variant (A8.5) |


## 2026-09-21, Stage 2 M2 grid-edge rule (A9.2): every trigger, executed or not

Counts are (tuning set, variant) pairs whose winner sat at an edge of `n_segments` or `compactness`. Projected time is from the measured Stage 2 per-unit times on 4 workers; the declared rule was run if <= 3 h.

| Round | Trigger (pairs at an edge) | Projection | Status | Measured |
|---|---|---|---|---|
| 1 | primary M2 10, primary M2g 2, sensitivity M2 7, sensitivity M2g 11 | 1.08 h | **EXECUTED** (`m2x1`, 5,280 units) | 71.2 min, 0 errors |
| 2 | primary M2 8, sensitivity M2 1, sensitivity M2g 10 | 0.87 h | **EXECUTED** (`m2x2`, 3,080 units) | 51.6 min, 0 errors |
| 3 | `n_segments`: no winner at an edge in any variant or criterion. `compactness`: see below | n/a | NOT EXECUTED, cap of 2 steps per parameter reached (A2.5) | n/a |

**Compactness optimum UNRESOLVED for primary M2.** After the cap, 4 of 12 tuning sets still choose the lowest compactness in their extended grid (0.0004, e.g. `n1000_c0.0004`). Primary M2g and both sensitivity variants have no winner at an edge. A compactness that low means the superpixels follow intensity almost exclusively and are free to become irregular in shape; the true optimum may be lower still and was not searched. State this wherever the primary M2 configuration is used.


## 2026-09-22, primary M2 compactness: one-off cap override, owner-authorized, scoped to 4 sets

The project owner explicitly authorized a 3rd compactness step (cap normally 2, A2.5/A9.2) for exactly
the 4 (tuning set, variant, criterion) triples that were still at the compactness edge after the cap:
primary M2 (unguarded) at `loeo:India`, `loeo:Pakistan`, `loeo:Somalia`, `loeo:Spain` (all at 0.0004).
Checked first that no other triple was at a reached edge, so nothing else could be affected.

- New compactness value: 0.0004 / 5 = 0.00008. Needed configurations: only 2 distinct preprocessing
  options are shared across the 4 sets (`clip=none,median=7`, `clip=medium,median=7`), each crossed
  with its own current `n_segments` list -> 10 new configurations (440 chips each).
- Projected 0.19 h (11.4 min), under the owner's 30-minute bar for this round -> **EXECUTED**
  (`m2x3`, 880 units, 13.0 min, 0 errors).
- Result: `loeo:Pakistan`'s winner moved to `n2000_c0.00008` (pooled IoU 0.168196 to 0.168282, a
  0.00009 improvement) and is again at the new (lowest) compactness edge; `loeo:India`, `loeo:Somalia`
  and `loeo:Spain` kept `n1000_c0.0004` (0.00008 scored lower for all three). No further step was run:
  the owner authorized exactly one additional step, not a further cap raise.
- **Compactness optimum for primary M2 is therefore still unresolved for `loeo:Pakistan`** (now at
  0.00008), and remains unresolved for `loeo:India` and `loeo:Somalia` at 0.0004 from the earlier cap
  (`loeo:Spain`'s frozen choice is unaffected in substance: 0.0004 still wins). State this wherever the
  primary M2 configuration for these tuning sets is used.
- Stage 3 was re-run for the one new (option, n_segments, compactness) triple this created
  (`clip=medium,median=7`, 2000, 0.00008): 440 new units, 1.6 min, reusing the SLIC segmentation cached
  during the `m2x3` round. The frozen configurations were regenerated; the diff against the previous
  `frozen_summary.txt` confirms the **only** change is `loeo:Pakistan`'s primary M2 entry (now
  `clip=medium,median=7`, SLIC 2000/0.00008, `vv_vh`, k=4) -- every other (criterion, tuning set,
  variant) is byte-identical.

