# Thesis corrections, 2026-11-16

Corrected file: `Thesis_SAR_Flood_Segmentation_Accra_corrected.docx`.
The original, `Thesis_SAR_Flood_Segmentation_Accra_clean.docx`, is unchanged, so the two can be compared in Word
(Review > Compare).

Labels: **[M]** checked against a result file or by code run on 2026-11-16; **[A]** an assumption or a wording choice of mine.

## What was checked and found correct [M]

- Tables 3, 4 and 5 and every benchmark number in the text, against `results/heldout_results.json`.
- The paired event-level intervals in Section 3.5.5, recomputed independently (they match to three decimals).
- Tables 7 and 8, the Sentinel-2 comparison, the double-bounce numbers and the tiled and scaled M2g re-runs, against
  `results/accra/*.csv` and `*.json`.
- Table 1, the data-inspection figures in Section 3.2 and 3.3, against `results/data_inspection_*`.
- The four news references open and say what the thesis says they say (deaths, dates, places).

## Factual corrections

| Where | Was | Now | Source |
|---|---|---|---|
| 4.1, 5.3 | "seven different configurations" for SLIC + k-means | eight for unguarded M2, six for guarded M2g | `results/tuning/frozen_summary.txt` [M] |
| 4.1, 5.3 | lowest compactness "at the edge of the grid in 3 of the 12 tuning sets", written as if about M2g | 1 of 12 (Pakistan fold), and it concerns unguarded M2; M2g had none | `results/tuning/stage2_selection.json` [M] |
| 4.1 | guarded variants scored "0.31 to 0.44" on tuning data | 0.335 to 0.442 (B1 0.330 to 0.413) | `frozen_summary.txt` [M] |
| Table 2, 3.5.2 | SLIC segments 200 to 2000 only; compactness extended "to 0.0004 and 0.00008" | segments extended to 4000 and 8000; compactness to 0.002, 0.0004 and (four sets) 0.00008 | `results/tuning/stage2_ext_*_plan.json` [M] |
| Table 2, 3.5.2 | k for M2 "2 to 5" | 2 to 5 were candidates; none with k = 5 survived pruning | `configs/config.yaml` [M] |
| 3.5.3 | "35 to 37% of comparisons"; more restarts "did not help" | 35.0% and 37.5%; 10 restarts lowered it only to 20.6% and 28.1%, above the 10% limit | `results/seed_*_output.txt` [M] |
| 3.5.5, 4.2, 5.3 | paired bootstrap presented as part of the method | labelled post hoc: it is not in the pre-declared protocol | protocol has no such rule [M] |
| 4.5.1, Table 6 | 14 candidates; 10 Oct 2020 offset "calculated from the pass schedule, not confirmed" | 15 candidates; 10 Oct 2020 confirmed at +84.3 h from the catalogue | Amendment 20 summary [M] |
| 1.3, 5.2, 5.4 | change detection "discussed only as future work" | a change-detection baseline was run on Accra and was inconclusive | Amendment 19 summary [M] |
| 1.2 | Ghana benchmark event "is a riverine flood" | "lies in northern Ghana" | the project's own inspection report says the mechanism was not verified [M] |
| Table 1 | "Ghana (White Volta, north)" | "Ghana (north)" | river name not verified in this project [A] |

## Added

- **Section 4.5.5 Follow-Up Checks** (new): the change-detection baseline, the coastal positive control, the rainfall and
  gauge records and the point checks, all from `results/accra_followup_summary.md`,
  `results/accra_POSTHOC_dfo_kotoka_summary.md` and `results/accra_POSTHOC_kotoka_isd_summary.md` [M]. Two sentences in it
  are my reading and are marked as such in the text: that a two-cluster split of the whole scene mainly separates sea from
  land, and that wet ground is a possible cause of the brighter 28 May image [A].
- Five limitations (5.3) and one recommendation (5.4) that follow from those checks.
- Abstract, 3.1.2, 4.6, 5.1 (v) and 5.2: one sentence each pointing to the follow-up checks.
- Acknowledgement: ESA WorldCover, NASA GPM IMERG and NOAA station records.

## Structure and formatting

- **Discussion (4.6):** a block of about 280 words was a word-for-word copy of the second paragraph of 4.5.4. It is replaced
  by two sentences that refer to 4.5.4.
- **Appendix A and "Data and code availability":** each was one long paragraph styled as a chapter heading, placed before the
  references, so the whole paragraph would have appeared as a table-of-contents entry. Each now has a short heading and normal
  body text, and both come after the references (Appendix A, Appendix B).
- **Table of contents and lists of figures and tables:** regenerated. The old contents page pointed "REFERENCES" at the
  appendix. Page numbers were computed by LibreOffice; if you open the file in Word, right-click the contents and choose
  Update Field so the numbers match Word's layout.
- **Numbered lists** (specific objectives, summary of findings): checked, they read (i) to (v).
- **References:** FloodList 2018 and 2020 and Citi Newsroom titles and dates corrected to the published ones; DOI added for
  Zhao et al. (2024a); UNOSAT (2023) is now cited in the text (it was in the list but never cited).

## Second round, 2026-11-16 (later the same day)

**Figures.** `scripts/19_thesis_figures.py` (new) draws Figures 1 and 3 to 8 into `results/figures/thesis/`, and the
corrected thesis now uses those files, so every figure except Figure 2 has code behind it. The script re-scores nothing:
Figures 3, 4 and 6 read `results/heldout_results.json`; Figures 5 and 7 run the frozen configuration on one chip each; Figure 8
re-runs frozen M2g on the two Accra scenes and stops if the flagged pixel count differs from the stored table. What it
reproduced [M]:

- Paraguay_284928: valid pixels 99.7% of the chip; unguarded M2 flags 34.6% of valid pixels, guarded M2g 0.0%. This settles
  the 99.7% figure in Section 4.3, which was unverified in the first round.
- Mekong_16233: M2g IoU 0.9241, precision 0.9865, recall 0.9360 (thesis: 0.924, 0.987, 0.936).
- Accra M2g: 8.86 ha on 3 June and 1.88 ha on 9 June inside the catchment, equal to `results/accra/accra_tables.json`.

The two example chips are fixed in the script. The code that originally picked them (the thesis says Mekong_16233 is the best
of 543 held-out chip evaluations with at least 5% flood) is **not** in the repository, so that selection is not reproduced
[M: no such script exists]. The new figures are plainer than the old ones: titles inside the pictures are shorter, and the
no-data line across the Paraguay chip is drawn dark instead of white.

**References added** (details checked on the publishers' or agencies' pages on 2026-11-16 unless noted):

| Reference | Cited in | Checked against |
|---|---|---|
| Zanaga et al. (2021), ESA WorldCover 10 m 2020 v100, doi:10.5281/zenodo.5571936 | 4.5.5 coastal control | citation block on ESA's WorldCover download page and the Zenodo record [M] |
| Smith, Lott & Vose (2011), Integrated Surface Database, BAMS 92, 704-708 | 4.5.5 gauge | NOAA NCEI's ISD page [M] |
| Huffman et al. (2023), GPM IMERG Final half-hourly V07, doi:10.5067/GPM/IMERG/3B-HH/07 | 4.5.5 rainfall | title, version and DOI from NASA's data catalogue [M]; **the year 2023 and the author list come from a USGS page that quotes the citation, because NASA's own dataset page did not load** [A] |
| Brakenridge (n.d.), Global Active Archive of Large Flood Events | 4.5.5 flood archive | form of the Observatory's own sample citation, as quoted by a web search; the URL is the one `scripts/17` read on 2026-10-20 [A] |

**Bonafilia et al. (2020).** Page range corrected from 210-211 to 835-845 and the DOI 10.1109/CVPRW50498.2020.00113 added
(university publication record and Semantic Scholar agree) [M]. The four baseline figures in Section 2.9 agree with the paper's
tables as quoted by a web search: test chips, hand-labelled model 0.2421 and Otsu on VH 0.2850; Bolivia 0.2905 and 0.3239. The
PDF itself refused my download twice, and the search text had lost the column headings, so **that these are the flood-water
columns is inferred** from the abstract (thresholding is best only for permanent water) [A]. Open the paper once and confirm.
Note 0.2850 rounds to 0.28 or 0.29 depending on the hidden next digit.

**Ansah et al. (2020).** The 14 deaths, 34,076 displaced, and the dates 18 June (Accra) and 28 June (Kumasi) 2018 match the
paper's abstract [M].

**Abstract.** Shortened from about 540 to about 450 words; it now fits on one page. No number was changed. Two sentences were
dropped (the remark that the result is consistent with known weaknesses of single-image SAR in cities, and the note on
superpixel size in Accra); both points remain in Sections 4.5.4, 4.6 and 5.3.

**Appendix B.** One sentence added saying which figures are drawn by a script in the repository.

**Still not done:** Figure 2 (the world map) has no script, because no country-outline data is installed here. Its legend and
caption say the Ghana event is "rural"; that word is still unverified.

## Things only you can fix

1. **Title page says "MASTER OF SCIENCE / MASTER OF PHILOSOPHY" and "SCHOOL OF GRADUATE STUDIES".** `CLAUDE.md` says this is an
   undergraduate final-year project. I did not change it.
2. Placeholders still in the file: student ID, names and signatures on the declaration, supervisor name, dedication,
   acknowledgement of people, and the highlighted repository link in Appendix B.
3. **Two baseline figures quoted from Bonafilia et al. (2020) in Section 2.9** (IoU 0.24 and 0.29; 0.29 and 0.32 on Bolivia) are
   not recorded anywhere in this repository, and the paper's PDF refused my download. Check them against the paper.
4. "Rural north" in the Figure 2 caption and legend is still not verifiable from the repository. (The Ansah et al. figures and
   the 99.7% coverage figure were checked in the second round, above.)
5. Formal references for IMERG, WorldCover, the NOAA station database and the flood archive were added in the second round;
   check the two marked [A] above. The NOAA daily summary (GSOD) is not named in the thesis, so it has no reference.
6. The abstract is now about 450 words on one page. Check your department's limit.
7. Figure 2 (the world map) still has no plotting script. Figures 1 and 3 to 8 now do (`scripts/19_thesis_figures.py`).
