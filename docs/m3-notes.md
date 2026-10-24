# M3 notes: monthly volumes, backfill, mapping

## Monthly volume tables

- **Index page found.** https://www.regione.sicilia.it/istituzioni/regione/strutture-regionali/presidenza-regione/autorita-bacino-distretto-idrografico-sicilia/siti-tematici/risorse-idriche/volumi-invasati-nelle-dighe-della-sicilia links one page per year (2011–2026). Each year page lists a table ("Prospetto volumi invasi <Mese> <Anno>") and a chart per month. File names are not predictable, so the fetcher reads the link text.
- **This corrects `sources.md` S3:** the latest table is **1 October 2026**, not May. The 2026 page lists January to October.
- `python -m acqua.fetch --from-year 2022` downloads new tables to `data/raw/regione-sicilia-volumi/`, skips files whose SHA-256 we already hold, and writes `manifest.json` (month, URL, hash). The pipeline reads the manifest, so every row keeps its source URL.
- **Backfilled: 58 months, January 2022 to October 2026.** Years 2011–2021 have pages too; I did not fetch them. The 2022 layout differs from 2026 and I expect older years to differ again.
- **Check on every table:** the extracted rows sum to the printed TOTALI row (current month and last-year column), for all 58 files. This is what proves no dam was dropped.
- **Layout differences handled:** row index column absent before 2024-10; footnote markers `(*)`; decimal dots instead of commas (June 2023); names that differ over time (`S. ROSALIA`, `S. GIOVANNI`, `OGLIASTRO (Don Sturzo)`); and a name cut in the PDF text layer: Piano del Leone prints only `LEONE` from March 2023 to September 2024. The row is identified by its river (Verdura) and capacity; the alias is in `data/reference/reservoirs.csv`.
- **Dams were added over time.** Tables up to February 2023 list 25 dams (no Furore, Gammauta, Paceco, Sciaguana, Zaffarana); later ones 28–29; from October 2024 there are 30. Totals match each time, so these are not extraction misses. The pipeline records a `row_count` warning for the 33 shorter tables.
- **The Authority revises its own numbers.** In 58 cases the "last year" or "previous month" column of a table differs from what the earlier table printed for that month (Nicoletti, Furore, Olivo, Trinità most often; Olivo March 2025 is 4,29 Mmc in its own table and 2,89 Mmc in the March 2026 table). Both are stored. The site's "same date last year" should use the column printed in the current table and say so.
- Santa Rosalia is above its stated capacity in 20 tables, Piano del Leone in 3.

## Mapping (data/reference/)

| File | Rows | Source |
|---|---|---|
| `consortia.csv` | 12 (2 regional, 10 former consortia) | Planning documents' addressees, CB3 report p. 4, CB9 statute |
| `comune_consortium.csv` | 80 | CB9 Catania statute art. 3 (27 comuni) and CB3 Agrigento report p. 3 (53 comuni) |
| `reservoir_consortium.csv` | 30 | Planning documents (addressee, Tabella 2 requests) and the monthly table's manager column |

`python -m acqua.mapping_extract` regenerates the comune file from the two PDFs and matches every name to the ISTAT list (391 comuni of Sicily, in `comuni`). Other consortia's rows go into the CSV by hand, each with a source file and page.

**What the data says, and does not say**

- **CB9 Catania:** the statute lists 20 comuni with the hectares of each comune inside the comprensorio (they sum to the printed 71.304 ha), plus seven comuni added as "Area Z" by the statute change approved on 14/05/2026 (Giunta deliberation 194). Hectares are the consortium's area inside the comune, not the whole comune: Catania 10.378 ha, Mineo only 233 ha. A comune on this list does not mean every farm in it is served.
- **CB3 Agrigento:** the report says "56 Comuni" and lists 53 names (Agrigento 40, Caltanissetta 6, Palermo 5, Trapani 2). I stored the 53 and did not guess the other three. No hectares per comune.
- **Not covered:** comune lists for CB1 Trapani, CB2 Palermo, CB4 Caltanissetta, CB5 Gela, Enna, CB7 Caltagirone, Ragusa and Siracusa. I searched; none of these is published as a list I could open. 80 of Sicily's 391 comuni are mapped. The statutes are the thing to request from the consortia or the Regione.
- **Reservoir → consortium is mostly regional.** Documents name Sicilia Occidentale or Orientale; district level is known only where a single-reservoir document names a district PEC (Castello → CB3, Pozzillo → CB9, Santa Rosalia → Ragusa), where Tabella 2 names the requester (Rosamarina → CB2 Palermo for 0,4 Mmc), or where the monthly table names the manager (Garcia → CB2, Don Sturzo → CB7). The relation column says which of these each row is.
- **Consortium numbers:** 1, 2, 3, 4, 5, 7 and 9 are printed in documents we hold. For Enna, Ragusa and Siracusa the ids carry no number because I haven't seen it in a primary document.
- **The map may change.** A draft law approved by the Giunta in January 2026 would replace the thirteen consortia with four. Consortium ids are separate from names so a reorganisation does not break comune pages.
- **Contacts:** only PEC addresses taken from the planning documents. No consortium website is confirmed (bonifica3ag.com belongs to CB3 only).
- **Announcements (season start, bookings, fees):** still only press reports; the `announcements` table is empty. Nothing official found.

## Housekeeping

- `data/acqua.sqlite` was deleted and rebuilt: the schema gained consortium columns and two mapping tables. Readings and plans come back identically from `data/raw`. From now on the pipeline refuses to change a stored reading, but `reservoirs`, `consortia`, `comuni` and the mapping tables are reference data that the run replaces.
- Tests: 32, about 30 s once the PDFs are cached (first load of 58 monthly PDFs takes about 80 s).
