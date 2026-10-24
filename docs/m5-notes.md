# M5 notes: automation and publishing (free, on GitHub)

Nick has no server and wants a free way, so M5 was changed from "Hetzner VPS + Caddy" to **GitHub Pages + GitHub Actions**. The server files, the server-side update job and the Telegram alert were removed (they stay in the git history, commit `d2db4ef` and earlier). Steps for Nick: [github-pages.md](github-pages.md).

## What it does

| Piece | Role |
|---|---|
| `.github/workflows/update.yml` | Daily job: fetch → decide → validate → build → check → archive → deploy |
| `src/acqua/checks.py site` | Gate: at least 400 pages, home shows volumes, sources page and 404 exist, every internal link resolves |
| `src/acqua/checks.py fresh` | Mondays: fails (so GitHub emails) if no new monthly table for 45 days |
| `ACQUA_BASE` / `--base` | Builds every link under `/<repository>/`, as GitHub project sites require |
| Raw PDFs now tracked | The CI job starts empty, so the archive lives in the repository (13 MB) |

## Safe failure

- Every publish step is conditional on the previous one. A validation error (rows not matching printed totals, unknown reservoir, negative volume), a build error or a failed site check stops the job **before** the deploy job runs. GitHub Pages keeps serving the previous deployment, and GitHub emails the owner.
- A daily run only rebuilds when a new document was downloaded; a push or manual run always rebuilds.
- New documents are committed to the repository only after validation passes, so a document that fails validation is retried (and reported) on the next run instead of being archived silently.
- Fail closed, as before: one unreadable or inconsistent document blocks publishing until the extractor is fixed.

## What was tested

- Locally: 47 tests pass (page content, sources and dates on every figure, base-path links, over-capacity flag, volumes, mapping, extraction).
- **Clean-room rehearsal** of the workflow's commands: fresh clone → new virtual environment → `pip install -r requirements.txt` → fetch (0 new files) → pipeline (4,976 readings, 38 plans) → build with `ACQUA_BASE=/acqua-ai-campi` (436 pages) → site check → freshness check: all passed.
- The workflow file parses as valid YAML.

## Not tested (GitHub is needed)

- The workflow itself has never run on GitHub: action versions (`checkout@v4`, `setup-python@v5`, `upload-pages-artifact@v3`, `deploy-pages@v4`), the permissions, the commit-back step and the Pages deployment. Expect to fix small things on the first run; the run log will say which step failed.
- The scheduled trigger and the failure emails.
- Live Lighthouse scores (the earlier ones were local).
- The `.github.io` address does not exist until Nick creates the repository.

## Still open

- Native Italian review of the copy; consortium comune lists for the other 311 comuni; official season and booking notices; a real domain, if wanted.
- Unit tests pin October 2026 data (for example the home page total) and will need updating when new months arrive; the workflow does not run them.
