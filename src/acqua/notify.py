"""Telegram alerts. Credentials come from the environment (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID),
never from the repository. Without them, alerts are only logged."""
import json
import logging
import os
import urllib.parse
import urllib.request

log = logging.getLogger("acqua.notify")


def scrub(text, secrets):
    for s in secrets:
        if s:
            text = text.replace(s, "***")
    return text


def send(text, env=None, opener=urllib.request.urlopen):
    """Send `text` to the configured Telegram chat. Returns True if sent; never raises."""
    env = os.environ if env is None else env
    token, chat = env.get("TELEGRAM_BOT_TOKEN"), env.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        log.warning("alert not sent (no Telegram credentials): %s", text)
        return False
    body = urllib.parse.urlencode({"chat_id": chat, "text": text[:3500], "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body)
    try:
        with opener(req, timeout=20) as r:
            ok = json.loads(r.read().decode()).get("ok", False)
        if not ok:
            log.error("Telegram refused the alert")
        return bool(ok)
    except Exception as e:                     # an alert must never take the update down
        log.error("alert failed: %s", scrub(str(e), [token, chat]))
        return False
