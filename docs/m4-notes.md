# M4 notes: the static site

## Build

```
PYTHONPATH=src python -m acqua.site        # reads data/acqua.sqlite, writes site/ (436 pages)
```

Templates are in `templates/`, the generator in `src/acqua/site.py` and `src/acqua/sitedata.py`. Run the fetch and pipeline first to refresh the data. The build empties and rewrites `site/`; to preview, serve that folder (for example `python -m http.server --directory site`). Links are root-relative, so the site must be served from the root of a domain.

## Pages

| Page | Count | Content |
|---|---|---|
| Home | 1 | Search box, island total vs. a year earlier, table with a bar per reservoir, consortia list, all 391 comuni by province |
| `/comune/<nome>/` | 391 | Consortium (with hectares in the comprensorio where the source gives them), directly linked reservoirs with volume, last year and 2026 plan, season start and bookings (always «Dato non disponibile» for now), PEC contact |
| `/invaso/<id>/` | 30 | Volume now, capacity, last year and last month, chart from January 2022, plan 2026 per use, usable volume, anomalies, consortia and comuni |
| `/consorzio/<id>/` | 12 | Contact, reservoirs, comuni |
| `/fonti-e-metodo/` | 1 | Every source with link and date, method, gaps, anomalies, update times |

## Rules, and how they are enforced

- **Date and source next to every number.** Figures go through the `fig` macro or sit in a table row (`datarow`) that has a date and a link to the original PDF, opened at the right page. `tests/test_m4_site.py` parses all 436 pages and fails if a volume appears outside such an element, or if one has no link or date.
- **Missing data says so.** «Dato non disponibile» appears wherever the source has nothing: season opening, bookings, tariffs, unmapped comuni, comuni lists for reservoirs.
- **Source anomalies are shown, not hidden.** Rosamarina's implausible volume in the planning document is not used; the page explains why. A volume above capacity is flagged (tested with a modified database).
- **No JS needed.** All numbers, tables and the full list of comuni are plain HTML. JavaScript only powers the search box (about 700 bytes plus a JSON list of names); without it the page says to use the list below.
- **No tracking, no external requests,** no web fonts, one inline stylesheet, light and dark theme.
- **Wording.** Plain Italian, neutral tone, no verdicts on consortia. A comune on a consortium's list is never presented as "served": the page says the list does not guarantee water for every farm.

## Lighthouse (mobile, simulated slow 4G, Chrome headless, local server)

| Page | Performance | Accessibility | Best practices | SEO |
|---|---|---|---|---|
| Home | 100 | 100 | 100 | 100 |
| Comune (Ribera) | 100 | 100 | 100 | 100 |
| Invaso (Lentini) | 99 | 100 | 100 | 100 |
| Consorzio (Catania) | 100 | 100 | 100 | 100 |
| Fonti e metodo | 100 | 100 | 100 | 100 |

Measured against `python -m http.server` without compression. A real host should do at least as well. Re-run once deployed.

## Decisions I made that you may want to change

- **Neutral brand:** no ClarityPoint name or credit anywhere (brief, open question 3). Footer says it is independent and not institutional.
- **Home table shows only reservoirs, not the "reservoirs for my town" chain:** a comune page lists only reservoirs tied to its district consortium by a document. Of 80 mapped comuni, those under Catania see Pozzillo, those under Agrigento see Castello, and the regional consortium's other reservoirs are one link away with the caveat that the district is unknown.
- **Potable and industrial plans appear on reservoir pages** (under their own headings) because the same documents give them. Comune pages show irrigation only.
- **«Un anno fa» uses the value printed in the current table**, not the older table's value (the Authority revises some numbers; see `m3-notes.md`).
- **No sitemap:** it needs the final domain.

## Known limits

- 311 of the 391 comune pages say they have no consortium yet; the home and reservoir pages still work for them.
- Season dates, bookings and fees are empty until official consortium notices are found.
- Contacts are PEC addresses taken from planning documents, shown with the document date.
- Reservoir volumes are gross volumes («al lordo»); the pages say so.
- Only the pages built from data of 1 October 2026 and earlier exist; the build is manual until M5.
