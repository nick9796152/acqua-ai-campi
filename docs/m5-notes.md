# M5 notes: automation, safe failure, deploy

Host chosen with you: **Hetzner VPS + Caddy**, **Telegram** alerts, code on **Codeberg**. The step-by-step guide is [deploy.md](deploy.md).

## What was built

| File | Role |
|---|---|
| `src/acqua/update.py` | The scheduled job: fetch → validate/extract → build → sanity checks → publish |
| `src/acqua/notify.py` | Telegram messages; credentials only from the environment, token scrubbed from logs |
| `deploy/Caddyfile` | Static serving with compression, a strict Content-Security-Policy, 404 page, access log without IP addresses |
| `deploy/acqua-update.{service,timer}` | Daily run (06:30 Rome), hardened service, pulls new code first |
| `deploy/acqua-alert.service` | Fallback alert if the job crashes before it can report |
| `deploy/bootstrap.sh`, `deploy/acqua.env.example` | One-time server setup, safe to re-run |
| `tests/test_m5_update.py` | 21 tests of the job (one runs only on Linux) |

## Safe failure, as built

1. **Nothing is published unless everything passes.** Validation errors, a fetch error, a build crash or a failed sanity check all leave the live site, the database and the release list exactly as they were (tested for each).
2. **Atomic switch.** The site is `current` → `releases/<time>`; the link is replaced with one rename, so no visitor sees a half-built site. Old releases (5 kept) allow a one-command rollback.
3. **The database is replaced last,** after the new site is already live, from a copy that passed validation.
4. **Rebuild only on change.** A fingerprint over raw documents, reference CSVs, code and templates decides; unchanged days cost one fetch.
5. **Alerts without noise.** One message per distinct failure, repeated after 24 h, plus "works again" on recovery; a 45-day silence from the Authority gives a warning but does not take the site down.
6. **Fail closed on bad documents.** If a new PDF can't be read or fails a check (for example its rows no longer add up to the printed total), the whole update stops and alerts until the extractor is fixed. I chose this over skipping the file, because skipping would silently drop data.
7. **Exit codes:** 0 fine, 3 failed safely (alert sent), 2 crash (systemd sends the fallback alert).

## Real runs

- Real end-to-end run of `python -m acqua.update` on the real data in a temporary folder: fetched, validated, built and "published" 436 pages; a second run correctly did nothing; the real fetch step found 0 new files.
- 21 job tests pass here (1 skipped: the symlink test, which needs Linux).

## Not verified (be aware)

- The symlink switch, Caddyfile, systemd units, `bootstrap.sh` and the real Telegram call have not run anywhere yet. The bootstrap runs the symlink test and `caddy validate` on the server; send me the output if anything fails.
- Nothing is deployed: you create the server, the Codeberg repository and the bot (steps in `deploy.md`). Nothing is committed either.
- No domain is chosen; the site answers on the server's IP until you set one.
- The Lighthouse scores from M4 were measured locally without compression. Re-measure on the live URL.

## Still open from the brief

- Italian copy review by a native, ideally Sicilian, speaker (open question 4).
- Domain and name (open question 1).
- Official consortium announcements and the missing comune lists (see `m3-notes.md`); until then the site says «Dato non disponibile».
- M6 (alerts to farmers by Telegram or email) is out of this scope.
