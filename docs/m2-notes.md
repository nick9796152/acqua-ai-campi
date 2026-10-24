# M2 notes: pipeline for the 2026 sources

## What exists

- `python -m acqua.pipeline` extracts the nine 2026 PDFs in `data/raw/regione-sicilia/`, validates them, and appends to `data/acqua.sqlite`. If validation finds an error nothing is written. Warnings are recorded in `validation_flags`.
- Tests: `PYTHONPATH=src python -m unittest discover -s tests` (16 tests, about 50 s). Expected values were read off the page images, not from the extractor's own output.
- Result: 116 readings, 38 plan rows, 30 reservoirs, 5 warnings.

## Hand-check (acceptance: at least 5 reservoirs)

Tests in `tests/test_m2.py` pin these values to a document and page: Arancio, Cimia, Disueri, Rubino, Trinità (Prot. 10116, pp. 3–4); Lentini, Nicoletti, Don Sturzo (Prot. 10109, p. 3); Pozzillo (10706, p. 3); Castello (14046, p. 3); Poma, Rosamarina (14387, p. 4); Ragoleto, Ancipa (15267 p. 4, 21823 p. 1); Garcia, Lentini, Fanaco and the 30-row total in the monthly table. Sums of the monthly table match the printed totals row exactly (617,01 / 584,83 / 374,95 Mmc).

## Things in the sources you should know about

Warnings the pipeline records (rows are kept as printed):

1. **Rosamarina, Prot. 14387 p. 4:** stored volume prints 14.005.000 mc while usable volume is 54.153.235 mc. The stored figure equals the potable need printed next to it, so it is probably a typo in the source. The monthly table gives Rosamarina 66,71 Mmc on 1 May. The site must not show 14,0 Mmc as Rosamarina's volume from this document.
2. **Santa Rosalia:** stored volume is above capacity in both the monthly table (21,08 vs 20,00 Mmc) and Prot. 10705 (21,19 Mmc).
3. **Don Sturzo, Prot. 10109:** the volume is dated 01/03/2025, a year older than the other rows.
4. **Pozzillo, Prot. 10706:** the letter says "al 23 marzo", the table says 30/03/2026. I kept the table date.

Extraction decisions:

- **Merged cells** (Cimia+Disueri planned figure, San Giovanni+Furore need and planned figures) are stored as a plan row with `group_label` and no reservoir, so nothing is counted twice. The text layer alone misreads the Cimia row. I confirmed the real layout on the page image.
- **Dates for Prot. 14387:** the letter gives 20 April for dams run by the Dipartimento (Poma, Rosamarina, Scanzano) and 27 April for those run by ENEL (Piana degli Albanesi, Prizzi). I assigned them using the manager column of the monthly table. This is an inference and each row says so in `notes`.
- **Ancipa:** the April table has no irrigation figure (blank cells). The only irrigation allocation is the 4 Mmc decided on 10/07/2026 (Prot. 21823), stored as its own row dated 2026-07-10.
- **Potable and industrial rows** are stored too (`use` column), because they come from the same tables. The site only needs `irriguo`.
- **Consortium per plan row is empty.** The tables don't say which consortium takes which allocation, except Tabella 2 of Prot. 14387 (vettoriamento requests), which I didn't load. That table could feed M3.
- **Protocol numbers:** Prot. 10116, 10705, 10706, 14046, 10109 and 21823 are blank on the PDF itself; protocol and dates come from the Authority's index page.

## Not done (belongs to M3)

Other monthly tables (2023–2025 backfill), the index page that lists the monthly tables, the scheduled fetcher with hash checks, the comune mapping, and consortium announcements.
