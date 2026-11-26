# Claude Code prompt: Accra follow-up checks (change detection, positive control, point checks)

Paste everything below the line into Claude Code, in the project repository.

---

I need three extra checks on the Accra case study (8 and 9 June 2020 flood). These are follow-up checks, not new tuning. Work step by step, explain each step in plain words before doing it, and stop for my go-ahead at the end of each step.

## Ground rules (do not break these)

1. **Write the amendment first.** Before running any code, add a new dated amendment to `results/evaluation_protocol.md`. It must list every rule below with its fixed values: thresholds, filter, buffer radius, number of control points, random seed and site list. Commit it with git and record the commit hash and SHA-256 of the protocol file. Only then run anything.
2. **No retuning.** Use the frozen Accra configuration exactly as it is (same median filter, same guard ceiling, same JRC mask, same AOI and sub-AOI files). Do not change any threshold after seeing a result. If a rule turns out to be unusable, stop and tell me; do not fix it silently.
3. **Label everything UNVALIDATED.** That applies to every output file, figure title and table. No ground truth exists for this event.
4. **Report everything.** Include null and inconvenient results, and every site and every number you computed. Do not drop a site because its result looks odd.
5. **Mark estimates.** In your summaries, say which numbers are measured and which are estimates or assumptions.

## Step 1: Check what imagery exists (no processing yet)

- Confirm the Sentinel-1 GRD IW scenes on relative orbit 147 for 3, 9 and 15 June 2020 (the ones already used).
- Check whether a 28 May 2020 scene exists on the **same relative orbit and pass direction**. If it does not, look for the nearest earlier same-orbit date and report it. Do not use a different orbit.
- Report the scene IDs and acquisition times (UTC). Stop.

## Step 2: Change-detection baseline (pre-declared)

Rules to write into the amendment:

- ΔVV = VV(event) − VV(reference), in dB. Apply the same preprocessing as the frozen Accra configuration (same median filter window), then compute the difference.
- **CD rule:** flood if ΔVV < −3 dB. *(The −3 dB value is a common choice in the literature, but I have not confirmed a source for it. Before running, find and cite a published source for a decrease threshold of this kind. If you cannot find one, tell me, keep −3 dB as the pre-declared value, and log it as an assumption.)*
- **Guarded CD rule:** CD rule AND VV(event) below the frozen guard ceiling.
- Remove JRC permanent water from all outputs (same mask as before).
- **Pairs:**
  - Event pair: reference 3 June, event 9 June.
  - Control pair: reference 28 May (or nearest same-orbit date from Step 1), "event" 3 June. No flood was reported between these dates.
  - Also report 9 June against 15 June, for the recession.
- **Areas:** full Odaw AOI (260.7 km²), Core, Kaneshie, Darkuman, and the three sub-areas combined.
- **Outputs:**
  - `results/accra_cd_baseline.csv`, with flagged hectares per pair, rule and area.
  - One map figure of the event-pair CD result with the AOI and sub-AOIs outlined.
  - Also apply the opposite-sign rule (ΔVV > +3 dB, i.e. brightening) to the event pair and report its hectares in the same CSV, for the double-bounce question. Same rule, no tuning.

Stop and summarise. Compare the event pair with the control pair, and say plainly whether the event pair stands out.

## Step 3: Positive control (coastal cluster)

The frozen M2g on 9 June accepted about 144,927 pixels in the downloaded scene, nearly all outside the AOI near the coast.

- For those accepted pixels, report the share that falls in:
  - (a) JRC permanent water;
  - (b) the sea (OSM coastline, or the JRC "ocean" class if available);
  - (c) Korle Lagoon (OSM polygon);
  - (d) none of these.
- Make one figure showing where they are.
- If most fall in (d), say what land cover they lie on (OSM or ESA WorldCover).

Stop and summarise.

## Step 4: Point checks at reported flood sites

**Sites.** Use only these sites, from news reports I have checked:

| Site | Evidence | Source |
|---|---|---|
| Odawna (Odawna market area) | Strong: two reports | FloodList 10 Jun 2020; The Watchers 11 Jun 2020 |
| Kwame Nkrumah Circle (interchange) | Moderate: "areas around" | same two reports |
| Taifa | Weak: one resident's account | The Watchers 11 Jun 2020 |
| Lapaz | Weak: a 2026 retrospective that dates the 2020 rains to 10 to 19 June | ModernGhana 3 Jul 2026 |

**Geocoding.**
- Geocode each site with OSM Nominatim. Use the neighbourhood or landmark centroid and record the OSM object ID and its coordinates.
- If a name gives several matches, list them all and ask me which one to use. Do not choose for me.
- Note whether each point falls inside the AOI and inside which sub-area, if any.

**Rules for the amendment.**
- Use a circular buffer of radius 50 m around each site.
- Inside each buffer, record:
  - the number of valid pixels;
  - median VV on 3, 9 and 15 June;
  - median ΔVV for the event pair (3 to 9 June);
  - the fraction of pixels flagged by B1, B2g (VH), M1g and M2g (frozen, from the existing runs);
  - the fraction flagged by the CD rule and by the guarded CD rule.

**Controls.**
- Draw 200 random points inside the AOI, restricted to built-up land (ESA WorldCover "built-up" class). Use random seed 20200609.
- Points must be at least 100 m from any reported site and from each other.
- Compute the same quantities for each control point.
- For each reported site, report its percentile rank among the controls for 9 June VV and for ΔVV.

**Sensitivity.** Repeat with 100 m buffers, as a pre-declared sensitivity check only. Keep 50 m as the headline.

**Outputs.**
- `results/accra_point_checks.csv`.
- One figure: the ΔVV distribution of the control points as a histogram, with the reported sites marked.

Stop and summarise. State plainly whether any reported site stands out from the controls on 9 June, in either direction. A percentile beyond 5 or 95 counts as "stands out". Say this is not validation.

## Step 5: Hand-back

Write `results/accra_followup_summary.md`, containing:

- the amendment number, date and commit hash;
- scene IDs;
- the tables from Steps 2 to 4;
- one paragraph per check in plain language, with measured numbers and estimates marked;
- a list of anything that did not go to plan.

Then update the README with the commands that reproduce these outputs. Run the test suite and confirm that the frozen benchmark configs and the held-out lock file are unchanged (compare hashes).
