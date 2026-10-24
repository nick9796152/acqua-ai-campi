# Project Brief: Sicily Irrigation Water Transparency Site

*Working name: **Acqua ai Campi** (rename freely)*
*Owner: Nick (ClarityPoint Data Services)*
*Hand this file to Claude Code as the project spec. Save it in the repo as `BRIEF.md` and reference it from `CLAUDE.md`.*

---

## 1. Why this exists

In 2026 Sicily's reservoirs are full after heavy rains, but farmers still can't reliably get irrigation water. Irrigation consortia (*consorzi di bonifica*) have been run by temporary commissioners for decades and are underfunded. They often don't tell farmers in time how much water they'll get or when the season starts, so farmers can't plan planting or investment. Meanwhile the basin authority (*Autorità di Bacino del Distretto Idrografico della Sicilia*) already publishes reservoir volumes and planned irrigation allocations per consortium. It publishes them as signed PDFs that almost nobody reads.

**This project turns those PDFs into a free, plain-Italian, phone-friendly site.** A farmer types their town and immediately sees:
- which reservoir(s) and which consortium serve them,
- how full those reservoirs are now vs. last year,
- how much water is planned for irrigation this season,
- when the irrigation season opens and how to book,
- when the data was last updated, with a link to the original source document.

It's also Nick's calling card. It shows Sicilian farmer associations (Coldiretti, Liberi Agricoltori), water utilities and engineering firms that he delivers useful work on Sicilian water data. It's step 1 of a larger plan (see §9).

## 2. Users

- **Primary:** Sicilian farmers, often older and on a phone, sometimes on a weak connection. Italian only. Not technical.
- **Secondary:** farmer associations, local journalists, municipal officials, researchers.

Design for the primary user. If a 60-year-old citrus grower near Ribera can't get his answer in two taps, it's wrong.

## 3. Principles (non-negotiable)

1. **Never invent or estimate a number.** Every figure on the site comes from a source document, with its date and a link to it. If data is missing, say so plainly ("Dato non disponibile").
2. **Show freshness everywhere.** Every number shows "aggiornato al [date of source data]", which is the date in the document, not the scrape date.
3. **Italian first.** All UI text in Italian. English is optional later.
4. **Mobile first, light pages.** Static HTML, minimal JS, fast on 3G. No heavy frameworks unless clearly justified.
5. **Free, no login, no tracking.** Privacy-respecting analytics at most (e.g. Plausible or none).
6. **Neutral tone.** Inform, don't editorialize against consortia or the region. The site's credibility is its value.
7. **Auditable pipeline.** Raw PDFs are archived. Every extracted row records its source file and page.

## 4. Data sources

> ⚠️ Source URLs and formats must be verified at build time. Start with discovery (Milestone 1).

Known starting point:
- **Basin authority irrigation planning PDF, western Sicily, 2026.** It contains, per reservoir: stored volume, net usable volume, consortium needs, and planned allocation, with data as of 16/03/2026. Example:
  `https://www.regione.sicilia.it/sites/default/files/2026-05/4_2026-10116-pianificazione_irriguo_sicilia_occ.pdf`

To discover and confirm:
- The equivalent planning document for **eastern Sicily** (Consorzio di Bonifica Sicilia Orientale, which covers e.g. Catania/Consorzio 9 and Caltagirone/Consorzio 7).
- **Periodic reservoir volume bulletins** (*volumi invasati*), likely published by the Regione's Dipartimento dell'Acqua e dei Rifiuti and/or the Autorità di Bacino. Find where, how often, and in what format.
- **Consortium announcements** of irrigation season start, booking windows and fees (*prenotazioni, stagione irrigua, canone*). These are probably HTML news pages or PDFs on consortium/regional sites.
- **Reservoir → consortium → municipality mapping.** Which *comuni* each consortium/irrigation district serves. This may have to be assembled by hand from consortium statutes and regional documents. Store it as a versioned CSV with a source column per row.
- **Municipality list and geometry**: ISTAT codes and boundaries for Sicilian comuni (open data).

Use the Italian names exactly as they appear in source documents (reservoir names like Arancio, Castello, Poma, Garcia, Ancipa, Rosamarina, etc.).

## 5. What to build

### 5.1 Ingestion pipeline (Python)
- `fetch/`: download source PDFs/pages on a schedule. Save the raw files to `data/raw/{source}/{YYYY-MM-DD}_{filename}`. Don't re-download unchanged files; compare by hash.
- `extract/`: parse tables from the PDFs (pdfplumber or camelot; OCR fallback only if a PDF is scanned). Output tidy rows.
- `validate/`: sanity checks. Volumes are non-negative. Usable volume ≤ stored volume. Reservoir names match the canonical list. Dates parse. Flag anything odd, never silently drop it.
- `store/`: a single DuckDB or SQLite file. Core tables:
  - `reservoirs` (id, name, capacity_m3 if known, location, consortium_ids)
  - `reservoir_readings` (reservoir_id, as_of_date, stored_m3, usable_m3, source_file, source_page)
  - `irrigation_plans` (reservoir_id, consortium_id, season_year, needs_m3, planned_m3, notes, as_of_date, source_file, source_page)
  - `consortia` (id, name, website, contact)
  - `comuni` (istat_code, name, province, consortium_ids)
  - `announcements` (consortium_id, date, type [season_open/booking/fee/other], summary_it, url)
- History is kept: never overwrite a reading, append new ones.

### 5.2 Static site generator
- Build plain static HTML from the database (Jinja2 templates or similar).
- **Home page:** a search box ("Cerca il tuo comune") plus an island-wide summary: total stored water vs. last year, and a simple bar per reservoir.
- **Comune page** (`/comune/{name}/`): consortium(s) serving it, linked reservoirs with current volume and same-date-last-year, this season's planned allocation, latest announcements (season start, booking), consortium contact, and source links with dates.
- **Reservoir page** (`/invaso/{name}/`): volume over time (simple chart), planned allocation, which comuni depend on it.
- **Consortium page** (`/consorzio/{name}/`): reservoirs, comuni, announcements, contact.
- **"Fonti e metodo" page:** every source, how data is extracted, known gaps, last update times. This is what makes the site trustworthy.
- Charts: lightweight (inline SVG generated at build time, or a tiny library). No chart should require JS to show the key number.

### 5.3 Automation & hosting
- Scheduled job (e.g. daily) runs fetch → extract → validate → build → deploy, and only rebuilds if sources changed.
- If validation fails, don't publish the bad data. Keep the last good build and log/alert Nick.
- **Hosting/CI constraint:** Nick avoids products that send money to Microsoft, so **don't use GitHub, GitHub Actions or Azure**. Suggested: code on Codeberg or GitLab, a site on Cloudflare Pages (or a small Hetzner VPS with cron + Caddy). Confirm with Nick before choosing.

## 6. Milestones & acceptance criteria

**M1 — Source discovery (do first, report back before building further)**
- Produce `docs/sources.md`: every candidate source found, its URL, format, update frequency, what fields it contains, and sample extractions.
- Answer: can we get reservoir volumes regularly (how often)? Do eastern and western planning docs both exist for 2026? What's available for the comune ↔ consortium mapping?
- ✅ Done when Nick has reviewed `sources.md` and agreed the scope.

**M2 — Pipeline for one source**
- The western Sicily 2026 planning PDF is fully extracted into the DB with provenance, and validation passes.
- ✅ Done when a test shows that every extracted row matches the PDF by hand-check on at least 5 reservoirs.

**M3 — All sources + mapping**
- Reservoir bulletins and eastern Sicily added. Comune ↔ consortium ↔ reservoir mapping CSV built (manual where needed, every row sourced).

**M4 — Static site v1**
- Home, comune, reservoir, consortium and "fonti e metodo" pages, Italian, mobile-first.
- ✅ Done when a Lighthouse mobile score is ≥ 90 on performance and accessibility, the key info is visible without JS, and every number shows a date and source link.

**M5 — Automation & deploy**
- Scheduled updates, safe failure behaviour, deployed on the chosen host.

**M6 (later) — Alerts**
- Optional Telegram channel or email digest per consortium: "Season opens", "New allocation published", "Reservoir X dropped below last year". (Telegram is common in Italy and is not Microsoft. WhatsApp is Meta. Ask Nick.)

## 7. Out of scope for v1
- Sensor/IoT irrigation advice (Sicilian startups like SmartIsland already do this; partner later, don't compete).
- Farmer accounts, user-submitted data, payments.
- Opinions about consortia performance or politics.
- Urban drinking-water network losses (that's Phase 2, see §9).

## 8. Open questions for Nick
1. Final name and domain (`.it` domain may need an EU presence; check registrar rules).
2. Hosting choice (§5.3).
3. Should the site be branded ClarityPoint, or kept neutral with a small "realizzato da" credit? A neutral brand probably earns more trust.
4. Who reviews the Italian copy? Ideally a native speaker, and ideally someone Sicilian.
5. Alerts channel for M6.

## 9. Larger plan (context only; not for Claude Code to build now)

This site is step 1 of three connected efforts:
1. **Farms** — this site, then possibly a local-supply-chain map (who grows what near which towns). In October 2026 a truckers' fuel protest emptied Sicilian supermarket shelves within days, even of local produce. Shorter local chains would make the island more resilient. Design the data model so that adding growers/products later is easy.
2. **Water losses** — Sicilian utilities (AMAP Palermo, Sidra Catania, Iblea Acque, AG9 Agrigento, Enna) have tens of millions in recovery funds for district metering, smart meters and leak detection, and they lose roughly half their water. Nick's offer is data governance and non-revenue-water analytics: night-flow analysis, faulty-meter detection, and pipe-replacement prioritization. That work would come as a subcontractor to the engineering firms that win those tenders. This site is the credibility builder for that.
3. **Hiring Sicilians** — Sicily's "South Working" grant pays employers €30,000 per Sicily-resident remote worker on a permanent contract, over five years (applications via Irfis-FinSicilia, open since June 30, 2026). Once there's paid work, hire a Sicilian analyst to own the Italian-facing data work. Check first whether ClarityPoint qualifies as the direct employer (vs. an employer-of-record) with an Italian *consulente del lavoro*.
