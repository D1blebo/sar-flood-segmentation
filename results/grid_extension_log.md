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
