#!/bin/sh
# One-time (and safe to re-run) setup of a fresh Debian 12 / Ubuntu 22.04+ server.
# Run as root:   sh bootstrap.sh <git-repo-url>
# Layout:  /srv/acqua/app (code)  /srv/acqua/venv  /srv/acqua/state (releases, current, logs)
set -eu

REPO_URL="${1:?usage: sh bootstrap.sh <git-repo-url>}"
APP=/srv/acqua/app

echo "== packages"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq caddy git python3 python3-venv curl rsync

echo "== user and folders"
id acqua >/dev/null 2>&1 || useradd --system --create-home --home-dir /srv/acqua --shell /usr/sbin/nologin acqua
mkdir -p /srv/acqua/state /var/log/caddy
chown -R acqua:acqua /srv/acqua
chown caddy:caddy /var/log/caddy 2>/dev/null || true

echo "== code"
if [ -d "$APP/.git" ]; then
  su -s /bin/sh acqua -c "git -C $APP pull --ff-only"
else
  su -s /bin/sh acqua -c "git clone $REPO_URL $APP"
fi

echo "== python environment"
su -s /bin/sh acqua -c "python3 -m venv /srv/acqua/venv && /srv/acqua/venv/bin/pip install --quiet -r $APP/requirements.txt"

echo "== configuration"
if [ ! -f /etc/acqua.env ]; then
  install -m 600 -o root -g root "$APP/deploy/acqua.env.example" /etc/acqua.env
  echo "   created /etc/acqua.env: edit it (domain, Telegram) before the first update"
fi
install -m 644 "$APP/deploy/Caddyfile" /etc/caddy/Caddyfile
install -m 644 "$APP/deploy/acqua-update.service" /etc/systemd/system/acqua-update.service
install -m 644 "$APP/deploy/acqua-update.timer" /etc/systemd/system/acqua-update.timer
install -m 644 "$APP/deploy/acqua-alert.service" /etc/systemd/system/acqua-alert.service
# Caddy reads the domain from the same file
mkdir -p /etc/systemd/system/caddy.service.d
printf '[Service]\nEnvironmentFile=/etc/acqua.env\n' > /etc/systemd/system/caddy.service.d/acqua.conf
systemctl daemon-reload

echo "== self-test on this server (real symlinks, fake data)"
su -s /bin/sh acqua -c "cd $APP && PYTHONPATH=src /srv/acqua/venv/bin/python -m unittest discover -s tests -p 'test_m5*.py'"

echo "== check the Caddy configuration"
( set -a; . /etc/acqua.env; set +a; caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile )

echo "== enable"
systemctl enable --now acqua-update.timer
systemctl enable caddy
systemctl restart caddy
echo
echo "Done. Next: put the raw archive in /srv/acqua/app/data/raw (see docs/deploy.md), edit /etc/acqua.env,"
echo "then run:  systemctl start acqua-update.service   and watch:  journalctl -fu acqua-update"
