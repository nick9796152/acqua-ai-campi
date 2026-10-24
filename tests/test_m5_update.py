"""M5: the update job fails safe.

Every test uses a throw-away project folder and fake steps; the real PDFs are not read here.
"""
import os
import shutil
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path

from acqua import notify, update
from acqua.update import Config, UpdateFailed, run


def make_project(root):
    for d in ("data/raw", "data/reference", "src", "templates"):
        (root / d).mkdir(parents=True)
    (root / "data/raw/a.pdf").write_bytes(b"%PDF one")
    (root / "src/x.py").write_text("x = 1")
    (root / "templates/t.html").write_text("t")


def good_build(db, out, pages=60):
    for i in range(pages):
        d = Path(out) / f"p{i}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text("<html>15,00 milioni di m³</html>", encoding="utf-8")
    (Path(out) / "index.html").write_text("<html>409,69 milioni di m³</html>", encoding="utf-8")
    (Path(out) / "404.html").write_text("x")
    (Path(out) / "fonti-e-metodo").mkdir()
    (Path(out) / "fonti-e-metodo" / "index.html").write_text("x")


def good_pipeline(db):
    import sqlite3
    from contextlib import closing
    with closing(sqlite3.connect(db)) as c:
        c.execute("CREATE TABLE IF NOT EXISTS source_documents (doc_date TEXT, protocol TEXT)")
        c.execute("DELETE FROM source_documents")
        c.execute("INSERT INTO source_documents VALUES ('2026-10-01', NULL)")
        c.commit()


class Harness:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        make_project(self.root)
        self.cfg = Config(project=self.root, state_dir=self.root / "state", keep=2, today=date(2026, 10, 20))
        self.sent, self.calls = [], []
        self.steps = {"fetch": lambda: self.calls.append("fetch"),
                      "pipeline": lambda db: (self.calls.append("pipeline"), good_pipeline(db)),
                      "build": lambda db, out: (self.calls.append("build"), good_build(db, out))}

    def run(self, **kw):
        for k, v in kw.items():
            setattr(self.cfg, k, v)
        return run(self.cfg, self.steps, send=self.sent.append)

    def releases(self):
        return sorted(p.name for p in self.cfg.releases.iterdir())

    def live_pages(self):
        return sum(1 for _ in self.cfg.current.rglob("*.html"))

    def change_source(self, content=b"%PDF two"):
        (self.root / "data/raw/a.pdf").write_bytes(content)


class Publishing(unittest.TestCase):
    def setUp(self):
        self.h = Harness()
        self.addCleanup(self.h.tmp.cleanup)

    def test_first_run_publishes_and_records_state(self):
        self.assertEqual(self.h.run(), 0)
        self.assertTrue((self.h.cfg.current / "index.html").exists())
        self.assertEqual(len(self.h.releases()), 1)
        self.assertTrue(self.h.cfg.db.exists())
        self.assertEqual(update.load_state(self.h.cfg)["pages"], self.h.live_pages())
        self.assertEqual(self.h.sent, [])

    def test_nothing_changed_means_no_rebuild(self):
        self.h.run()
        self.h.calls.clear()
        self.assertEqual(self.h.run(), 0)
        self.assertEqual(self.h.calls, ["fetch"])             # fetched, but pipeline and build skipped
        self.assertEqual(len(self.h.releases()), 1)

    def test_force_rebuilds(self):
        self.h.run()
        time.sleep(1.1)
        self.h.calls.clear()
        self.h.run(force=True)
        self.assertIn("build", self.h.calls)
        self.assertEqual(len(self.h.releases()), 2)

    def test_changed_source_publishes_a_new_release(self):
        self.h.run()
        before = update.load_state(self.h.cfg)["release"]
        time.sleep(1.1)
        self.h.change_source()
        self.assertEqual(self.h.run(), 0)
        self.assertNotEqual(update.load_state(self.h.cfg)["release"], before)

    def test_old_releases_are_pruned(self):
        for i in range(4):
            self.h.change_source(f"%PDF {i}".encode())
            time.sleep(1.1)
            self.assertEqual(self.h.run(), 0)
        self.assertEqual(len(self.h.releases()), 2)


def symlinks_work():
    with tempfile.TemporaryDirectory() as d:
        try:
            os.symlink(d, os.path.join(d, "l"), target_is_directory=True)
            return True
        except OSError:
            return False


@unittest.skipUnless(symlinks_work(), "no symlink rights here (Windows); runs on the Linux server")
class AtomicSwitch(unittest.TestCase):
    def test_current_is_a_symlink_and_old_release_stays_reachable_until_switched(self):
        h = Harness()
        self.addCleanup(h.tmp.cleanup)
        h.run()
        first = os.path.realpath(h.cfg.current)
        self.assertTrue(h.cfg.current.is_symlink())
        time.sleep(1.1)
        h.change_source()
        h.run()
        second = os.path.realpath(h.cfg.current)
        self.assertNotEqual(first, second)
        self.assertTrue(h.cfg.current.is_symlink())
        self.assertFalse(h.cfg.current.with_name("current.new").exists())


class FailingSafe(unittest.TestCase):
    def setUp(self):
        self.h = Harness()
        self.addCleanup(self.h.tmp.cleanup)
        self.h.run()
        self.live = update.load_state(self.h.cfg)["release"]
        self.db_before = self.h.cfg.db.read_bytes()
        time.sleep(1.1)
        self.h.change_source()

    def assert_untouched(self):
        self.assertEqual(update.load_state(self.h.cfg)["release"], self.live)
        self.assertEqual(self.h.releases(), [self.live])      # no half-built folder left behind
        self.assertTrue((self.h.cfg.current / "index.html").exists())
        self.assertEqual(self.h.cfg.db.read_bytes(), self.db_before)
        self.assertFalse((self.h.cfg.state_dir / "staging.sqlite").exists())

    def test_validation_failure_keeps_the_live_site_and_alerts_once(self):
        def bad(db):
            raise UpdateFailed("validation failed: totals_mismatch")
        self.h.steps["pipeline"] = bad
        self.assertEqual(self.h.run(), 1)
        self.assert_untouched()
        self.assertEqual(len(self.h.sent), 1)
        self.assertIn("FAILED", self.h.sent[0])
        self.assertIn("totals_mismatch", self.h.sent[0])
        self.assertEqual(self.h.run(), 1)                     # same problem again: no second alert
        self.assertEqual(len(self.h.sent), 1)

    def test_a_different_problem_alerts_again(self):
        self.h.steps["pipeline"] = lambda db: (_ for _ in ()).throw(UpdateFailed("one"))
        self.h.run()
        self.h.steps["pipeline"] = lambda db: (_ for _ in ()).throw(UpdateFailed("two"))
        self.h.run()
        self.assertEqual(len(self.h.sent), 2)

    def test_same_problem_alerts_again_after_a_day(self):
        self.h.steps["pipeline"] = lambda db: (_ for _ in ()).throw(UpdateFailed("one"))
        self.h.run()
        state = update.load_state(self.h.cfg)
        state["alert"]["at"] -= update.REALERT_AFTER_S + 5
        update.save_state(self.h.cfg, state)
        self.h.run()
        self.assertEqual(len(self.h.sent), 2)

    def test_fetch_failure_keeps_the_live_site(self):
        def no_network():
            raise OSError("network unreachable")
        self.h.steps["fetch"] = no_network
        self.assertEqual(self.h.run(), 1)
        self.assert_untouched()
        self.assertIn("network unreachable", self.h.sent[0])

    def test_build_crash_leaves_no_partial_release(self):
        def crash(db, out):
            good_build(db, out, pages=5)
            raise RuntimeError("template error")
        self.h.steps["build"] = crash
        self.assertEqual(self.h.run(), 1)
        self.assert_untouched()

    def test_site_that_lost_pages_is_not_published(self):
        self.h.steps["build"] = lambda db, out: good_build(db, out, pages=52)   # live has 63 pages
        self.assertEqual(self.h.run(), 1)
        self.assert_untouched()
        self.assertIn("sanity check failed", self.h.sent[0])

    def test_site_without_volumes_is_not_published(self):
        def empty_home(db, out):
            good_build(db, out)
            (Path(out) / "index.html").write_text("<html>vuoto</html>", encoding="utf-8")
        self.h.steps["build"] = empty_home
        self.assertEqual(self.h.run(), 1)
        self.assert_untouched()

    def test_recovery_is_announced_and_publishes(self):
        self.h.steps["pipeline"] = lambda db: (_ for _ in ()).throw(UpdateFailed("broken"))
        self.h.run()
        self.h.steps["pipeline"] = lambda db: good_pipeline(db)
        self.assertEqual(self.h.run(), 0)
        self.assertEqual(len(self.h.sent), 2)
        self.assertIn("works again", self.h.sent[1])
        self.assertNotEqual(update.load_state(self.h.cfg)["release"], self.live)


class LockAndStale(unittest.TestCase):
    def setUp(self):
        self.h = Harness()
        self.addCleanup(self.h.tmp.cleanup)

    def test_second_run_is_refused_while_locked(self):
        self.h.cfg.state_dir.mkdir(parents=True)
        self.h.cfg.lock_file.write_text("123")
        self.assertEqual(self.h.run(), 1)
        self.assertEqual(self.h.calls, [])

    def test_stale_lock_from_a_crash_is_ignored(self):
        self.h.cfg.state_dir.mkdir(parents=True)
        self.h.cfg.lock_file.write_text("123")
        old = time.time() - update.LOCK_MAX_AGE_S - 60
        os.utime(self.h.cfg.lock_file, (old, old))
        self.assertEqual(self.h.run(), 0)
        self.assertFalse(self.h.cfg.lock_file.exists())

    def test_old_source_triggers_one_warning_but_still_publishes(self):
        self.assertEqual(self.h.run(today=date(2026, 12, 20)), 0)      # newest table is 2026-10-01
        self.assertEqual(len(self.h.sent), 1)
        self.assertIn("2026-10-01", self.h.sent[0])
        self.h.run(today=date(2026, 12, 21))
        self.assertEqual(len(self.h.sent), 1)                         # not repeated every day

    def test_recent_source_is_quiet(self):
        self.h.run(today=date(2026, 10, 20))
        self.assertEqual(self.h.sent, [])


class Notify(unittest.TestCase):
    def test_without_credentials_nothing_is_sent_and_nothing_raises(self):
        self.assertFalse(notify.send("x", env={}))

    def test_message_goes_to_the_telegram_bot_api(self):
        seen = {}

        class R:
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def read(s): return b'{"ok": true}'

        def opener(req, timeout):
            seen["url"], seen["body"] = req.full_url, req.data.decode()
            return R()
        env = {"TELEGRAM_BOT_TOKEN": "123:SECRET", "TELEGRAM_CHAT_ID": "42"}
        self.assertTrue(notify.send("ciao", env=env, opener=opener))
        self.assertTrue(seen["url"].startswith("https://api.telegram.org/bot123:SECRET/sendMessage"))
        self.assertIn("chat_id=42", seen["body"])

    def test_token_never_reaches_the_log(self):
        def opener(req, timeout):
            raise OSError("failed for https://api.telegram.org/bot123:SECRET/sendMessage")
        env = {"TELEGRAM_BOT_TOKEN": "123:SECRET", "TELEGRAM_CHAT_ID": "42"}
        with self.assertLogs("acqua.notify", level="ERROR") as cm:
            self.assertFalse(notify.send("x", env=env, opener=opener))
        self.assertNotIn("SECRET", "\n".join(cm.output))


if __name__ == "__main__":
    unittest.main()
