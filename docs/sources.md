# Sources (M1 discovery)

> **Update after M3:** the index of the monthly volume tables was found, and the latest table is October 2026, not May (see `docs/m3-notes.md`). Sections S3 and S6 below describe the state at M1.

Discovery run on 2026-10-23. Raw files are in `data/raw/regione-sicilia/` (prefixed with the download date). Nothing here is loaded into a database yet.

## Headline findings

1. **The URL in the brief is wrong, the file is real.** `/sites/default/files/2026-05/...` returns 404. The same file works under `/system/files/2026-05/...`. Search engines index the `/sites/default/files/` form, so don't trust search-result links.
2. **Both 2026 planning PDFs exist** (western and eastern), both dated 02/04/2026 (Prot. 10116 and 10109), data as of 16/03/2026 (one eastern row is older, see below).
3. **There is a monthly reservoir volume table** from the same Authority: "Prospetto volumi invasati nelle dighe della Sicilia" (30 reservoirs, text-based PDF, easy to parse). The latest I found is dated **1 May 2026**. I did not find anything newer, but I searched only briefly; finding the index page that lists the monthly tables is the first task for M2.
4. **No official consortium announcements found yet.** Season-start and booking news appears only in the press. The consortium sites did not come up in search.
5. **No comune ↔ consortium ↔ reservoir mapping exists as a dataset.** It will have to be assembled by hand.

## S1. Western Sicily irrigation planning 2026

| | |
|---|---|
| File | `2026-10-23_4_2026-10116-pianificazione_irriguo_sicilia_occ.pdf` (4 pages, text-based, 537 KB) |
| URL | https://www.regione.sicilia.it/system/files/2026-05/4_2026-10116-pianificazione_irriguo_sicilia_occ.pdf |
| Publisher | Autorità di Bacino del Distretto Idrografico della Sicilia, Servizio 1 |
| Index page | https://www.regione.sicilia.it/istituzioni/regione/strutture-regionali/presidenza-regione/autorita-bacino-distretto-idrografico-sicilia/anno-2026-1 ("Pianificazione risorsa idrica 2026", 8 PDFs, page last updated 18/08/2026) |
| Data date | 16/03/2026 (volumes); plan valid 01/01–31/12/2026 |
| Frequency | Once a year, plus later single-reservoir provvedimenti |
| Fields | Volume invasato, volume utile netto per utilizzatori, fabbisogni consorzi, pianificato consorzi, notes (all in mc) |
| Format | Table on pages 3–4. `pdfplumber` finds tables on those pages but the notes column wraps across rows, so extraction needs per-reservoir handling. |

**Reservoirs covered (11):** Arancio, Cimia, Disueri, Comunelli, Gorgo, Paceco, Rubino, San Giovanni, Furore, Trinità, Zaffarana.

Sample (copied from the PDF, mc):

| Invaso | Invasato | Utile netto | Fabbisogno | Pianificato |
|---|---|---|---|---|
| Arancio | 20.572.303 | 17.163.103 | 8.000.000 | 8.000.000 |
| Paceco | 5.706.989 | 3.562.042 | 2.000.000 | 2.000.000 |
| Rubino | 4.886.231 | 3.272.084 | 3.500.000 | 3.272.084 |
| Trinità | 2.480.677 | 313.920 | 5.000.000 | 313.920 |
| Zaffarana | 355.490 | 292.203 | 250.000 | 250.000 |

**Caveats**
- The protocol number and date on page 1 are blank (`Protocollo n. ________ del ____/04/2026`). The index page lists it as Prot. 10116 of 02.04.2026. The published file looks like an unsigned version. Record both and note it on "Fonti e metodo".
- Some rows are merged: Cimia/Disueri share one planned figure (the text says the plan is for the whole Cimia–Disueri system), and San Giovanni/Furore share one. The schema needs a "system" concept, or the planned volume has to be stored against a group of reservoirs.
- Several large western reservoirs (Garcia, Poma, Rosamarina, Castello) are **not** in this table. They have separate provvedimenti ("Castello" Prot. 14046 of 11.05.2026, "Sistema Palermo" Prot. 14387 of 14.05.2026). I have not opened those yet.
- Mmc/mc: this document uses mc with dots as thousands separators. The eastern one uses Mmc with decimal commas. Parsers must handle both.

## S2. Eastern Sicily irrigation and industrial planning 2026

| | |
|---|---|
| File | `2026-10-23_5_2026-10109_del_02.04.2026-pianificazione_uso_irriguo_e_industriale_sicilia_orientale_signed_signed_signed.pdf` (3 pages, 471 KB) |
| URL | https://www.regione.sicilia.it/system/files/2026-05/5_2026-10109_del_02.04.2026-pianificazione_uso_irriguo_e_industriale_sicilia_orientale_signed_signed_signed.pdf |
| Data date | 16/03/2026 for most rows. **Don Sturzo/Ogliastro is dated 01/03/2025**, a year older than the rest. |
| Fields | Data rilevazione, volume invasato, volume utile netto al 31.12.2026, fabbisogno and pianificato for irriguo and industriale, totale pianificato, notes (all in Mmc) |
| Format | One table on page 3. The "Data rilevazione" header is printed rotated, so `extract_text` returns it reversed ("enoizavelir ataD"). Needs column positions, not header text. |

**Reservoirs covered (5):** Don Sturzo/Ogliastro, Lentini, Nicoletti, Olivo, Sciaguana.

Sample (Mmc): Lentini 16/03/2026, invasato 99,77, utile netto 47,56, fabbisogno 11,50, pianificato 11,50. Nicoletti has an industrial share of 0,46 split 0,39 ATI Enna / 0,07 Sicily Outlet Village (stated on pages 2 and 3).

**Caveats**
- Other eastern reservoirs (Pozzillo, Santa Rosalia, Ancipa, Ragoleto) have their own provvedimenti on the same index page and are not in this table.
- The Don Sturzo date means "this season's allocation vs. current volume" would mix dates for that one reservoir. Show the date per row.

## S3. Monthly reservoir volumes ("Prospetto volumi invasati")

| | |
|---|---|
| File | `2026-10-23_2_2026.05.01_a_tabella_volumi_invasi.pdf` (1 page, 45 KB, text-based) |
| URL | https://www.regione.sicilia.it/system/files/2026-05/2_2026.05.01_a_tabella_volumi_invasi.pdf |
| Publisher | Dipartimento Regionale dell'Autorità di Bacino, Servizio 1 |
| Data date | 1 May 2026 (title: "AL 1° MAGGIO 2026"; data "rilevati da strumenti di misura o da comunicazioni dei gestori al lordo") |
| Frequency | Monthly. Older files exist for 2023-06-01, 2024-09-01, 2024-10 (same layout), which gives us a history to backfill. |
| Fields | Diga, corso d'acqua, capacità totale d'invaso (Mmc), volume this month, last month, difference, same month last year, utilizzazione, ente gestore |
| Rows | 30 reservoirs, plus a totals row |

Sample (Mmc, copied from the PDF):

| Diga | Capacità | Maggio 2026 | Aprile 2026 | Maggio 2025 | Gestore |
|---|---|---|---|---|---|
| Arancio | 34,80 | 21,45 | 21,64 | 9,06 | Dip.to Acqua e Rifiuti |
| Castello | 21,00 | 19,95 | 19,82 | 9,70 | Dip.to Acqua e Rifiuti |
| Garcia | 80,00 | 48,06 | 37,64 | 19,59 | C.B. 2 Palermo (*) |
| Lentini | 134,55 | 98,83 | 99,68 | 98,66 | Dip.to Acqua e Rifiuti |
| Pozzillo | 150,50 | 52,12 | 55,69 | 32,80 | E.N.E.L. |

This is the best source for the "now vs. last year" requirement, because the previous-year column is built in. Totals row: 617,01 Mmc this month vs. 374,95 last year (+65%).

**Caveats and validation flags**
- **Santa Rosalia: volume 21,08 exceeds capacity 20,00.** Per principle 1 we publish it as printed and flag it. (Garcia has a footnote: volume from updated bathymetry since 01/03/2026.)
- "Volume" here is the gross stored volume ("al lordo"), not usable volume. Don't label it as water available to farmers.
- Several reservoirs are not irrigation-first (Fanaco and Piano del Leone are potable/hydroelectric, managed by Siciliacque). Mark use type per reservoir.
- The totals row prints no total for capacity.
- The file names are not predictable (`2_2026.05.01_a_tabella_volumi_invasi.pdf`, `Tabella_volumi_invasi_0.pdf`, `1__2024.09.01_A_Tabella_volumi_invasi_0.pdf`), so the fetcher must scrape an index page. I have not found which page lists the monthly tables.
- Reporting frequency by dam managers: the planning letters say states of reservoirs are transmitted weekly (every Monday) and monthly (1st). Weekly data goes to the Authority; I found no evidence it is public.

## S4. Other planning provvedimenti on the 2026 page (not yet opened)

| Prot. | Date | Subject |
|---|---|---|
| 10705 | 09/04/2026 | Santa Rosalia |
| 10706 | 09/04/2026 | Pozzillo |
| 14046 | 11/05/2026 | Castello |
| 14387 | 14/05/2026 | Sistema Palermo |
| 15267 | 21/05/2026 | Ancipa–Ragoleto (Sicilia orientale) |
| 21823 | 28/07/2026 | Assegnazione irriguo Ancipa |

File URLs are on the index page (S1). These likely hold the planned allocations for the reservoirs missing from S1 and S2. Reading them is the first M2 task.

## S5. Consortium announcements (season start, bookings, fees)

Nothing official found. What exists:

- La Sicilia, 14 June 2026: Consorzi di bonifica 7 (Caltagirone) and 9 (Catania). Director Gaetano Punzi said bookings open the next day and the season starts by end of June. Source: https://www.lasicilia.it/news/cronaca/3048828/dighe-piene-ma-campi-a-secco.html
- QdS: Consorzio Sicilia Occidentale, commissioner Baldo Giarraputo, says the Authority guaranteed a 2026/2027 irrigation programme; Castello holds 10,5 Mmc. Date not verified. Source: https://qds.it/sicilia-la-stagione-irrigua-riparte-con-riserve-raddoppiate/
- Consortium PEC addresses appear in the planning PDFs (S1, S2). No website URL has been confirmed.

Press reports are not primary sources. For the site, announcements must come from the consortia themselves or the Regione. Next step: find the official sites (the eastern PEC domain suggests `consorzibonificasicilia.it`; unverified).

**Governance risk:** a Giunta resolution of 29/01/2026 (https://www2.regione.sicilia.it/deliberegiunta/file/giunta/allegati/N.043_29.01.2026.pdf) approves a draft law reorganizing the consortia. Consortium names and boundaries may change. Keep consortium identifiers independent of names.

## S6. Comune ↔ consortium ↔ reservoir mapping

No dataset found. Partial evidence:

- Regione press release, 19/05/2026: Consorzio 9 Catania adds seven comuni (Valverde, Aci Sant'Antonio, Aci Bonaccorsi, Aci Catena, San Giovanni la Punta, Acicastello, San Gregorio di Catania) to a comprensorio of "venti comuni". The twenty are not listed. https://www.regione.sicilia.it/la-regione-informa/agricoltura-altri-sette-comuni-nel-comprensorio-consorzio-bonifica-9
- A 2025 ordinance names western districts CB1 Trapani, CB2 Palermo, CB3 Agrigento (served by Garcia). Not a comune list.
- The reservoir → consortium link comes from the planning documents, but the comune → consortium link needs the consortium statutes or comprensorio maps. This is the main risk to the "type your town" feature. Irrigation districts cross comune borders, so a comune may map to several consortia, or to part of one.

## S7. Comuni list and boundaries

- ISTAT list of comuni with codes: https://www.istat.it/storage/codici-unita-amministrative/Elenco-comuni-italiani.xlsx (stated to be a permanent link, updated 21/02/2026). I have not downloaded it yet.
- Boundaries: ISTAT's page points to the SITUAS portal (https://situas.istat.it/web/#/home); no direct file link or license was confirmed. Boundaries are only needed if we draw maps, which the brief doesn't require.

## Answers to the M1 questions

- **Regular reservoir volumes?** Yes, monthly (1st of month), one PDF per month, 30 dams, with last-year comparison. Backfill to at least 2023 looks possible. Weekly data exists but isn't confirmed public.
- **Eastern and western 2026 planning docs both exist?** Yes (S1, S2), plus six single-reservoir provvedimenti (S4) that complete the picture.
- **Comune ↔ consortium mapping?** Not available as data. Manual build from statutes and consortium pages; the CB9 comune list is a start.

## Open points for Nick

1. The brief's "farmer sees a planned allocation per consortium" simplifies reality: plans are per **reservoir** (sometimes per system), and the consortium needs are per reservoir. I suggest the comune page shows the reservoir's plan and not a per-consortium split unless a source gives one.
2. S1 is an unsigned-looking draft in the public copy. Do you want me to treat the signed provvedimenti as authoritative where they exist?
3. Scope for M2: S1 only (as the brief says) or S1 + S2 + S3 together? They share the same parser approach and S3 is the simplest.
