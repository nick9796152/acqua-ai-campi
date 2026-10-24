# Acqua ai Campi

Project spec: see [BRIEF.md](BRIEF.md). Follow its principles (§3) and milestones (§6).

- Milestones: M1-M4 approved. M5 rebuilt for free GitHub Pages (no server): `.github/workflows/update.yml`, `docs/github-pages.md`, `docs/m5-notes.md`. Waiting for Nick to create the GitHub repository; then push to remote `github`. Codeberg (`origin`) is a second copy.
- Fetch new tables: `PYTHONPATH=src python -m acqua.fetch`. Pipeline: `python -m acqua.pipeline`. Build: `python -m acqua.site [--base /acqua-ai-campi]`. Gates: `python -m acqua.checks site|fresh`. Tests: `python -m unittest discover -s tests`. Python 3.12; `requirements.txt` lists pdfplumber, openpyxl, jinja2.
- Every figure on the site must carry a date and a source link; `tests/test_m4_site.py` enforces it. Never put tokens in the repo.
- `data/reference/*.csv` is hand-checked reference data; every row names its source file and page.
- Never invent numbers; every figure carries source, date and page.
- Italian-only UI text. Do not use GitHub, GitHub Actions or Azure.
- Raw downloads go in `data/raw/{source}/{YYYY-MM-DD}_{filename}`.
