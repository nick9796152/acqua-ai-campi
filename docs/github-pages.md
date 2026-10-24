# Publishing on GitHub Pages (free)

The site is published by a GitHub "workflow" in `.github/workflows/update.yml`. Once a day it checks the government site for new data, rebuilds the pages if there is something new, checks them, and replaces the live site. If anything fails, the live site stays as it was and GitHub emails you.

The address will be `https://<your-github-name>.github.io/acqua-ai-campi/`.

## Steps for you

1. **Create a free GitHub account** at https://github.com/signup (skip if you have one).
2. **Create an empty repository**: github.com → "+" → New repository. Name: `acqua-ai-campi`. Choose **Public** (free hosting needs it). Do **not** add a README or other files. Create it.
3. **Add the SSH key** (so the push needs no password): github.com → your picture → Settings → SSH and GPG keys → New SSH key. Title `acqua-pc`, key type "Authentication key", paste this line, and save:

```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHhA5FGPFw4hkK1fdDaxQxm+7w4mC6uRRGIcxSVeMnPP acqua-ai-campi 2026-10-24
```

4. **Tell Claude your GitHub user name.** Claude then connects the project and sends the code up.
5. **Turn on Pages**: in the repository → Settings → Pages → "Build and deployment" → Source: **GitHub Actions**.
6. **Allow the workflow to save new documents**: Settings → Actions → General → "Workflow permissions" → **Read and write permissions** → Save.
7. **Start the first run**: repository → Actions → "Update site" → "Run workflow". It takes about 3–5 minutes. When the run turns green, open the address above.

## What happens every day

- 05:30 UTC the workflow downloads any new monthly reservoir table.
- **Nothing new:** it stops, the site stays as it is.
- **Something new, or the code changed:** it reads and checks all documents, builds the pages, checks them (at least 400 pages, home page shows volumes, every internal link works), saves the new documents in the repository, and replaces the live site.
- **Any check fails:** nothing is replaced and GitHub sends you an email about the failed run. Open the run to see which step failed.
- **Mondays:** a separate check emails you if there has been no new reservoir table for 45 days.

## Good to know

- GitHub switches off scheduled workflows after 60 days with no activity in the repository. New documents are saved into the repository about once a month, which counts as activity. If the daily runs ever stop, press "Run workflow" once.
- The full archive of source PDFs is now in the repository (about 13 MB). The database and the generated site are not saved; they are rebuilt each time.
- Codeberg (`origin`) stays as a second copy of the code. `git push` sends to Codeberg; `git push github main` sends to GitHub.
- The unit tests in `tests/` are not run by the workflow, because some pin October 2026 values and would fail when a new month arrives. The workflow's gate is the document validation plus the site check.
- Free GitHub Pages limits are far above this site's needs (about 1 GB of site, 100 GB of traffic a month).
- A custom domain can be added later in Settings → Pages (free apart from the domain itself).
