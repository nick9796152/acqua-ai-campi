"""Scheduled update: fetch -> extract -> validate -> build -> publish, failing safe.

Usage:  python -m acqua.update [--root DIR] [--force] [--no-fetch] [--notify-test]
Exit codes: 0 ok or nothing to do, 3 failed safely (alert sent), 2 unexpected crash.

Safety rules (BRIEF.md 5.3):
  * Nothing is published unless every step succeeds and the new site passes the sanity checks.
  * The database is rebuilt in a copy and only replaced after the site has been published.
  * The live site is a symlink `current` -> releases/<timestamp>; switching it is one atomic rename,
    so visitors always see a complete site, and the last good release stays if anything fails.
  * A rebuild only happens when the sources, reference data or code changed.
  * Failures send one Telegram alert per distinct problem (repeated after 24 h); a recovery sends one more.
"""
import argparse
import contextlib
import hashlib
import json
import logging
import os
import shutil
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from . import notify
from .util import ROOT

log = logging.getLogger("acqua.update")

REALERT_AFTER_S = 24 * 3600
STALE_SOURCE_DAYS = 45          # the Authority publishes a table at the start of each month
STALE_REALERT_S = 7 * 24 * 3600
LOCK_MAX_AGE_S = 2 * 3600
MIN_PAGE_RATIO = 0.9
EXIT_HANDLED = 3                # update failed, live site unchanged, alert already sent


@dataclass
class Config:
    project: Path = ROOT
    state_dir: Path = None          # where releases/, current, state.json, logs/ live
    keep: int = 5
    force: bool = False
    fetch: bool = True
    today: date = field(default_factory=date.today)

    def __post_init__(self):
        self.project = Path(self.project)
        self.state_dir = Path(self.state_dir or self.project / "deploy-state")

    @property
    def releases(self): return self.state_dir / "releases"
    @property
    def current(self): return self.state_dir / "current"
    @property
    def state_file(self): return self.state_dir / "state.json"
    @property
    def lock_file(self): return self.state_dir / "update.lock"
    @property
    def db(self): return self.project / "data" / "acqua.sqlite"


class UpdateFailed(Exception):
    pass


class LockHeld(UpdateFailed):
    pass


# ---------------------------------------------------------------------------- state and lock

def load_state(cfg):
    try:
        return json.loads(cfg.state_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(cfg, state):
    tmp = cfg.state_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, cfg.state_file)


class Lock:
    """One update at a time. A lock older than two hours is treated as left over from a crash."""

    def __init__(self, path):
        self.path = Path(path)

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return self
            except FileExistsError:
                if time.time() - self.path.stat().st_mtime > LOCK_MAX_AGE_S:
                    self.path.unlink()
                    continue
                raise LockHeld("another update is running (lock file present)")
        raise UpdateFailed("could not take the update lock")

    def __exit__(self, *exc):
        with contextlib.suppress(OSError):
            self.path.unlink()


# ---------------------------------------------------------------------------- change detection

def fingerprint(project):
    """Hash of everything the site depends on: raw documents, reference CSVs, code and templates."""
    h = hashlib.sha256()
    roots = [Path(project, "data", "raw"), Path(project, "data", "reference"),
             Path(project, "src"), Path(project, "templates")]
    for root in roots:
        for p in sorted(root.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                h.update(str(p.relative_to(project)).replace("\\", "/").encode())
                h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


# ---------------------------------------------------------------------------- sanity and publish

def sanity(out, prev):
    """Reasons not to publish a freshly built site (empty list = fine)."""
    out = Path(out)
    problems = []
    pages = sum(1 for _ in out.rglob("*.html"))
    if pages < 50:
        problems.append(f"only {pages} pages were built")
    if prev.get("pages") and pages < prev["pages"] * MIN_PAGE_RATIO:
        problems.append(f"{pages} pages, the live site has {prev['pages']}")
    home = out / "index.html"
    if not home.exists() or "m³" not in home.read_text(encoding="utf-8"):
        problems.append("home page is missing or shows no volume")
    for need in ("fonti-e-metodo/index.html", "404.html"):
        if not (out / need).exists():
            problems.append(f"{need} missing")
    return problems


def swap_current(cfg, release):
    """Point `current` at `release`: create a new symlink beside it and rename it over the old one
    (atomic on Linux). Without symlink rights (Windows, development only) copy the folder instead."""
    cfg.current.parent.mkdir(parents=True, exist_ok=True)
    tmp = cfg.current.with_name(cfg.current.name + ".new")
    try:
        if tmp.is_symlink() or tmp.exists():
            tmp.unlink()
        os.symlink(release, tmp, target_is_directory=True)
        os.replace(tmp, cfg.current)
    except OSError:
        log.warning("symlinks unavailable: copying instead (not atomic, development only)")
        if cfg.current.exists():
            shutil.rmtree(cfg.current)
        shutil.copytree(release, cfg.current)


def prune(cfg):
    releases = sorted(p for p in cfg.releases.iterdir() if p.is_dir() and not p.name.endswith(".tmp"))
    for old in releases[:-cfg.keep]:
        shutil.rmtree(old, ignore_errors=True)


def latest_table_date(db):
    import sqlite3
    from contextlib import closing
    with closing(sqlite3.connect(db)) as con:
        row = con.execute("SELECT MAX(doc_date) FROM source_documents WHERE protocol IS NULL").fetchone()
    return row[0]


# ---------------------------------------------------------------------------- alerts

def alert(cfg, state, sig, text, key="alert", every=REALERT_AFTER_S, send=notify.send):
    """Send `text` unless the same signature was already alerted within `every` seconds."""
    last = state.get(key) or {}
    if last.get("sig") == sig and time.time() - last.get("at", 0) < every:
        log.info("alert suppressed (already sent): %s", sig)
        return
    send(text)
    state[key] = {"sig": sig, "at": time.time()}


# ---------------------------------------------------------------------------- the update

def default_steps():
    from . import fetch, pipeline, site

    def do_fetch():
        rc = fetch.main(["--from-year", str(date.today().year - 1)])
        if rc:
            raise UpdateFailed(f"fetch returned {rc}")

    def do_pipeline(db):
        rc = pipeline.main(["--db", str(db)])
        if rc:
            raise UpdateFailed("validation failed; see the log for the error lines")

    def do_build(db, out):
        site.build(str(db), out)

    return {"fetch": do_fetch, "pipeline": do_pipeline, "build": do_build}


def run(cfg, steps=None, send=notify.send):
    """One update. Returns 0 on success or nothing to do, 1 on failure (nothing published)."""
    steps = steps or default_steps()
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    cfg.releases.mkdir(exist_ok=True)
    try:
        with Lock(cfg.lock_file):
            state = load_state(cfg)
            return _run_locked(cfg, steps, state, send)
    except LockHeld as e:
        log.error("%s", e)
        return 1


def _run_locked(cfg, steps, state, send):
    staging_db = cfg.state_dir / "staging.sqlite"
    tmp_release = cfg.releases / "building.tmp"
    try:
        if cfg.fetch:
            steps["fetch"]()
        fp = fingerprint(cfg.project)
        if fp == state.get("fingerprint") and cfg.current.exists() and not cfg.force:
            log.info("nothing changed since the last published build")
            _recovered(state, send)
            _check_stale(cfg, state, send)
            save_state(cfg, state)
            return 0

        for p in (staging_db, tmp_release):
            if p.is_dir():
                shutil.rmtree(p)
            elif p.exists():
                p.unlink()
        if cfg.db.exists():
            shutil.copy(cfg.db, staging_db)
        steps["pipeline"](staging_db)
        steps["build"](staging_db, tmp_release)
        problems = sanity(tmp_release, state)
        if problems:
            raise UpdateFailed("sanity check failed: " + "; ".join(problems))
        pages = sum(1 for _ in tmp_release.rglob("*.html"))

        name = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        release = cfg.releases / name
        os.replace(tmp_release, release)
        swap_current(cfg, release)
        cfg.db.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging_db, cfg.db)
        prune(cfg)
        _recovered(state, send)
        state.update(fingerprint=fp, pages=pages, release=name,
                     published_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        save_state(cfg, state)
        _check_stale(cfg, state, send)
        save_state(cfg, state)
        log.info("published %s (%d pages)", name, pages)
        return 0
    except Exception as e:
        shutil.rmtree(tmp_release, ignore_errors=True)
        if staging_db.exists():
            staging_db.unlink()
        detail = f"{type(e).__name__}: {e}"
        log.error("update failed, live site unchanged: %s\n%s", detail, traceback.format_exc())
        sig = hashlib.sha256(detail.encode()).hexdigest()[:16]
        state["failing_since"] = state.get("failing_since") or datetime.now(timezone.utc).isoformat(timespec="seconds")
        alert(cfg, state, sig, f"Acqua ai Campi: update FAILED. The live site is unchanged.\n{detail[:600]}", send=send)
        save_state(cfg, state)
        return 1


def _recovered(state, send):
    if state.pop("failing_since", None):
        state.pop("alert", None)
        send("Acqua ai Campi: update works again.")


def _check_stale(cfg, state, send):
    """Warn (without failing) when no new monthly table has appeared for a long time."""
    try:
        latest = latest_table_date(cfg.db)
    except Exception:
        return
    if not latest:
        return
    age = (cfg.today - date.fromisoformat(latest)).days
    if age > STALE_SOURCE_DAYS:
        alert(cfg, state, f"stale-{latest}",
              f"Acqua ai Campi: the newest reservoir table is from {latest} ({age} days old). "
              "The Authority may have stopped publishing, or the page changed.",
              key="stale_alert", every=STALE_REALERT_S, send=send)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", help="folder for releases/, current, state.json and logs/ (default: ./deploy-state)")
    ap.add_argument("--force", action="store_true", help="rebuild even if nothing changed")
    ap.add_argument("--no-fetch", action="store_true", help="skip downloading new documents")
    ap.add_argument("--notify-test", action="store_true", help="send a test Telegram message and exit")
    a = ap.parse_args(argv)
    cfg = Config(state_dir=a.root, force=a.force, fetch=not a.no_fetch)
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    (cfg.state_dir / "logs").mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(cfg.state_dir / "logs" / "update.log", encoding="utf-8")])
    if a.notify_test:
        return 0 if notify.send("Acqua ai Campi: test message.") else 1
    try:
        rc = run(cfg)
    except Exception:                       # a crash outside the guarded part: exit 2 so systemd's OnFailure alerts
        log.exception("unexpected crash")
        return 2
    return 0 if rc == 0 else EXIT_HANDLED


if __name__ == "__main__":
    sys.exit(main())
