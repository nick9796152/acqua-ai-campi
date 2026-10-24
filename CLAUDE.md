# Acqua ai Campi

Project spec: see [BRIEF.md](BRIEF.md). Follow its principles (§3) and milestones (§6).

- Milestones: M1–M4 approved (`docs/sources.md`, `m2-notes.md`, `m3-notes.md`, `m4-notes.md`). M5 built (`docs/m5-notes.md`, `docs/deploy.md`), awaiting Nick's review and the server setup he does himself. Host: Hetzner VPS + Caddy; alerts: Telegram; code: Codeberg. M6 not started.
- Scheduled job: `PYTHONPATH=src python -m acqua.update --root <dir>` (fails safe; see `deploy/`). Never put the Telegram token in the repo.
- Build the site: `PYTHONPATH=src python -m acqua.site` (writes `site/`; needs `jinja2`). Every figure on the site must carry a date and a source link; `tests/test_m4_site.py` enforces it.
- Fetch new monthly tables: `PYTHONPATH=src python -m acqua.fetch`. Run the pipeline: `PYTHONPATH=src python -m acqua.pipeline`. Tests: `PYTHONPATH=src python -m unittest discover -s tests`. Python 3.12 with `pdfplumber` and `openpyxl` (`requirements.txt`).
- `data/reference/*.csv` is hand-checked reference data; every row names its source file and page.
- Never invent numbers; every figure carries source, date and page.
- Italian-only UI text. Do not use GitHub, GitHub Actions or Azure.
- Raw downloads go in `data/raw/{source}/{YYYY-MM-DD}_{filename}`.
