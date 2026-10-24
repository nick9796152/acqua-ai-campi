# Deploying Acqua ai Campi (Hetzner VPS + Caddy)

Everything below you do yourself: it creates accounts, spends money and puts the code on a server. I have **not** run the server files on a real machine (see "What is tested" at the end), so expect to fix small things on first run and tell me what the log says.

## 1. Server

1. In Hetzner Cloud create a project and a server: location Falkenstein or Nuremberg, image **Ubuntu 24.04**, type **CX22** (about €4–5/month), add your SSH public key, enable backups (+20%).
2. Note the server's IPv4 address. In the Hetzner firewall allow TCP 22, 80, 443.
3. Log in: `ssh root@<ip>`. Update: `apt-get update && apt-get -y upgrade`.

## 2. Code on Codeberg

On your PC, in `C:\Users\nicho\Documents\acqua-ai-campi`:

```bash
git init
git add .
git commit -m "Acqua ai Campi M1-M5"
git branch -M main
git remote add origin https://codeberg.org/<your-user>/acqua-ai-campi.git
git push -u origin main
```

Create the (empty) repository on codeberg.org first. `.gitignore` keeps out the raw PDFs, the database and the generated site. Make the repository **public** if you want the server to clone without a token; otherwise create a read-only deploy key on Codeberg and use the SSH URL.

## 3. Install

On the server:

```bash
git clone https://codeberg.org/<your-user>/acqua-ai-campi.git /tmp/acqua && sh /tmp/acqua/deploy/bootstrap.sh https://codeberg.org/<your-user>/acqua-ai-campi.git
```

The script installs Caddy, Python and git, creates the `acqua` user, clones the code to `/srv/acqua/app`, builds the Python environment, installs the systemd units, **runs the update-job tests on the server** (this is the first real test of the atomic site switch) and enables the daily timer. If a step fails it stops; read the message.

## 4. Move the raw archive

The raw PDFs are the audit trail and are not in git. From your PC (Git Bash):

```bash
rsync -av /c/Users/nicho/Documents/acqua-ai-campi/data/raw/ root@<ip>:/srv/acqua/app/data/raw/
ssh root@<ip> chown -R acqua:acqua /srv/acqua/app/data/raw
```

Without it the first run would have to re-download everything from the Authority's site, which also works.

## 5. Telegram alerts

1. In Telegram talk to **@BotFather**, send `/newbot`, follow the steps; you get a token like `123456:ABC...`.
2. Send any message to your new bot, then open `https://api.telegram.org/bot<token>/getUpdates` in a browser; the number after `"chat":{"id":` is your chat id.
3. On the server: `nano /etc/acqua.env` and fill `TELEGRAM_BOT_TOKEN=` and `TELEGRAM_CHAT_ID=`. The file is readable by root only. Do not paste the token anywhere else, including to me.
4. Test: 
```bash
sudo -u acqua sh -c 'set -a; . /etc/acqua.env; set +a; cd /srv/acqua/app && PYTHONPATH=src /srv/acqua/venv/bin/python -m acqua.update --root /srv/acqua/state --notify-test'
```
You should get "Acqua ai Campi: test message." on your phone.

## 6. Domain

Buy a domain (a `.it` may require an EU presence, brief open question 1), add an **A** record pointing to the server IP, then uncomment `ACQUA_DOMAIN=` in `/etc/acqua.env` with the name and run `systemctl restart caddy`. Caddy gets the HTTPS certificate on its own. Until then the site answers on `http://<ip>/`.

## 7. First run

```bash
systemctl start acqua-update.service
journalctl -fu acqua-update
```

Expect about two minutes. When it says `published <timestamp> (436 pages)`, open the site. The timer then runs every day at about 06:30 Rome time.

## What the job does, and when it alerts

- **Daily:** looks at the Authority's year pages and downloads new monthly tables. If nothing changed (documents, reference data, code), it stops there.
- **When something changed:** rebuilds the database in a copy, runs all validations, builds the site in a staging folder, checks it (page count within 10% of the live site, home page shows volumes, sources page present), and only then switches `current` to the new release in one atomic step.
- **If anything fails:** the live site is not touched, the database is not replaced, and you get one Telegram message with the reason. The same problem is reported again after 24 hours; a different problem is reported at once; when it works again you get "update works again".
- **If the job crashes** before it can report (broken environment, full disk), systemd sends a fallback message.
- **If the Authority stops publishing:** after 45 days without a newer monthly table you get a warning (the site stays up with the old data and its dates).
- The five most recent releases are kept in `/srv/acqua/state/releases`.

## Everyday tasks

| Task | Command |
|---|---|
| See what happened | `journalctl -u acqua-update -n 100` and `/srv/acqua/state/logs/update.log` |
| Run an update now | `systemctl start acqua-update.service` |
| Force a rebuild | `sudo -u acqua sh -c 'cd /srv/acqua/app && PYTHONPATH=src /srv/acqua/venv/bin/python -m acqua.update --root /srv/acqua/state --force'` |
| Go back to an earlier release | `cd /srv/acqua/state && ls releases` then `ln -sfn releases/<name> current.new && mv -T current.new current` |
| Update the code | push to Codeberg; the next daily run pulls it (a code change counts as "changed" and rebuilds) |
| Back up | enable Hetzner backups; `data/raw` is the only irreplaceable folder, and the Authority's site also keeps most of it |

## What is tested, and what is not

- Tested here (Windows, Python 3.12): the update job's behaviour with fake steps (publishing, skipping when nothing changed, 8 failure cases, alert de-duplication, lock, stale-source warning, token scrubbing), and one real end-to-end run on the real data (436 pages).
- **Not tested:** the atomic symlink switch (this PC has no symlink rights; the bootstrap script runs that test on the server), the Caddyfile, the systemd units and `bootstrap.sh` (no Linux or Caddy here), and the real Telegram call. The bootstrap script runs `caddy validate`.
- Python on the server should be 3.10 or newer; I checked the code only on 3.12.
