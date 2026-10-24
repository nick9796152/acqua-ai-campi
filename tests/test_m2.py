"""M2 acceptance tests.

Expected values were transcribed by hand from the PDF page images (not from the extractor's
text output). Each case names the source file and page so a reviewer can check it.
Run:  python -m unittest discover -s tests   (with PYTHONPATH=src)
"""
import copy
import sqlite3
from contextlib import closing
import tempfile
import unittest
from datetime import date
from unittest import mock
from pathlib import Path

from acqua import db, pipeline, validate

DOCS = pipeline.collect()
BY_PROTOCOL = {d["protocol"]: d for d in DOCS if d["protocol"]}
VOLUMES = next(d for d in DOCS if d["kind"] == "volumes" and d["doc_date"] == "2026-05-01")


def reading(doc, rid, col_prefix=None):
    rows = [r for r in doc["readings"] if r["reservoir_id"] == rid
            and (col_prefix is None or r["source_column"].startswith(col_prefix))]
    assert len(rows) == 1, (rid, rows)
    return rows[0]


def plan(doc, rid, use):
    rows = [p for p in doc["plans"] if p["reservoir_id"] == rid and p["use"] == use]
    assert len(rows) == 1, (rid, use, rows)
    return rows[0]


class HandChecked(unittest.TestCase):
    """Eight reservoirs, each checked against the printed table."""

    def test_arancio_west_p3(self):                    # Prot. 10116, page 3
        d = BY_PROTOCOL["10116"]
        r, p = reading(d, "arancio"), plan(d, "arancio", "irriguo")
        self.assertEqual((r["stored_m3"], r["usable_m3"], r["as_of_date"], r["source_page"]),
                         (20_572_303, 17_163_103, "2026-03-16", 3))
        self.assertEqual((p["needs_m3"], p["planned_m3"]), (8_000_000, 8_000_000))

    def test_cimia_disueri_merged_cell_west_p3(self):  # one planned figure for the system
        d = BY_PROTOCOL["10116"]
        self.assertEqual(reading(d, "cimia")["stored_m3"], 3_049_200)
        self.assertEqual(reading(d, "cimia")["usable_m3"], 1_759_200)
        self.assertEqual(plan(d, "cimia", "irriguo")["needs_m3"], 720_000)
        self.assertEqual(reading(d, "disueri")["stored_m3"], 415_870)
        self.assertEqual(reading(d, "disueri")["usable_m3"], 0)
        self.assertEqual(plan(d, "disueri", "irriguo")["needs_m3"], 2_600_000)
        group = [p for p in d["plans"] if p["group_label"] == "Cimia-Disueri"]
        self.assertEqual([(p["reservoir_id"], p["planned_m3"]) for p in group], [(None, 1_759_200)])
        self.assertIsNone(plan(d, "cimia", "irriguo")["planned_m3"])   # not double counted

    def test_rubino_trinita_west(self):
        d = BY_PROTOCOL["10116"]
        self.assertEqual((reading(d, "rubino")["stored_m3"], plan(d, "rubino", "irriguo")["planned_m3"]),
                         (4_886_231, 3_272_084))
        t = plan(d, "trinita", "irriguo")
        self.assertEqual((t["needs_m3"], t["planned_m3"], t["source_page"]), (5_000_000, 313_920, 4))

    def test_lentini_east_p3(self):                    # Prot. 10109, Mmc -> mc
        d = BY_PROTOCOL["10109"]
        r, p = reading(d, "lentini"), plan(d, "lentini", "irriguo")
        self.assertEqual((r["stored_m3"], r["usable_m3"], r["as_of_date"]), (99_770_000, 47_560_000, "2026-03-16"))
        self.assertEqual((p["needs_m3"], p["planned_m3"]), (11_500_000, 11_500_000))

    def test_nicoletti_industrial_east_p3(self):
        d = BY_PROTOCOL["10109"]
        self.assertEqual(plan(d, "nicoletti", "irriguo")["planned_m3"], 600_000)
        self.assertEqual((plan(d, "nicoletti", "industriale")["needs_m3"],
                          plan(d, "nicoletti", "industriale")["planned_m3"]), (460_000, 460_000))

    def test_don_sturzo_date_is_2025(self):
        self.assertEqual(reading(BY_PROTOCOL["10109"], "don-sturzo")["as_of_date"], "2025-03-01")

    def test_pozzillo_p3(self):                        # Prot. 10706
        d = BY_PROTOCOL["10706"]
        r, p = reading(d, "pozzillo"), plan(d, "pozzillo", "irriguo")
        self.assertEqual((r["stored_m3"], r["usable_m3"], r["as_of_date"]), (55_640_000, 47_140_000, "2026-03-30"))
        self.assertEqual((p["needs_m3"], p["planned_m3"]), (65_000_000, 47_140_000))

    def test_castello_p3(self):                        # Prot. 14046
        d = BY_PROTOCOL["14046"]
        r, p = reading(d, "castello"), plan(d, "castello", "irriguo")
        self.assertEqual((r["stored_m3"], r["usable_m3"]), (19_750_900, 13_932_400))
        self.assertEqual((p["needs_m3"], p["planned_m3"]), (11_000_000, 10_500_000))

    def test_poma_rosamarina_palermo_p4(self):         # Prot. 14387
        d = BY_PROTOCOL["14387"]
        self.assertEqual((reading(d, "poma")["stored_m3"], reading(d, "poma")["usable_m3"]), (61_520_000, 51_075_556))
        self.assertEqual(plan(d, "poma", "irriguo")["planned_m3"], 7_000_000)
        self.assertEqual(plan(d, "poma", "industriale")["planned_m3"], 40_000)
        self.assertEqual(plan(d, "rosamarina", "irriguo")["planned_m3"], 12_935_000)
        # printed as is, even though it looks like a typo in the source (see the validation test)
        self.assertEqual(reading(d, "rosamarina")["stored_m3"], 14_005_000)

    def test_ragoleto_and_ancipa(self):                # Prot. 15267 p4, 21823 p1
        d = BY_PROTOCOL["15267"]
        self.assertEqual(plan(d, "ragoleto", "irriguo")["planned_m3"], 3_800_000)
        self.assertEqual(plan(d, "ragoleto", "industriale")["planned_m3"], 1_400_000)
        self.assertEqual(reading(d, "ancipa")["stored_m3"], 24_050_000)
        self.assertEqual([p for p in d["plans"] if p["reservoir_id"] == "ancipa" and p["use"] == "irriguo"], [])
        self.assertEqual(plan(BY_PROTOCOL["21823"], "ancipa", "irriguo")["planned_m3"], 4_000_000)

    def test_monthly_volumes_1_may_2026(self):         # volume table, page 1
        garcia = reading(VOLUMES, "garcia", "volume maggio")
        self.assertEqual(garcia["stored_m3"], 48_060_000)
        self.assertEqual(reading(VOLUMES, "garcia", "volume stesso mese")["stored_m3"], 19_590_000)
        self.assertEqual(reading(VOLUMES, "lentini", "volume maggio")["stored_m3"], 98_830_000)
        self.assertEqual(reading(VOLUMES, "fanaco", "volume maggio")["stored_m3"], 16_980_000)
        cap = {r["id"]: r["capacity_m3"] for r in VOLUMES["reservoirs"]}
        self.assertEqual((cap["don-sturzo"], cap["pozzillo"], len(cap)), (110_000_000, 150_500_000, 30))
        self.assertEqual(VOLUMES["totals"]["current_m3"], 617_010_000)


class Validation(unittest.TestCase):
    def test_real_documents_have_no_errors_and_expected_warnings(self):
        flags = validate.validate(DOCS, today=date(2026, 10, 23))
        self.assertEqual([f for f in flags if f["severity"] == "error"], [])
        codes = {(f["code"], f["reservoir_id"]) for f in flags}
        self.assertIn(("usable_gt_stored", "rosamarina"), codes)
        self.assertIn(("stored_gt_capacity", "santa-rosalia"), codes)
        self.assertIn(("stale_reading", "don-sturzo"), codes)

    def test_negative_and_unknown_reservoir_are_errors(self):
        docs = copy.deepcopy(DOCS)
        west = next(d for d in docs if d["protocol"] == "10116")
        west["readings"][0]["stored_m3"] = -1
        west["plans"][0]["reservoir_id"] = "diga-inventata"
        errs = {f["code"] for f in validate.validate(docs, today=date(2026, 10, 23)) if f["severity"] == "error"}
        self.assertEqual(errs, {"negative_volume", "unknown_reservoir"})

    def test_totals_mismatch_is_an_error(self):
        docs = copy.deepcopy(DOCS)
        next(d for d in docs if d["doc_date"] == "2026-05-01")["readings"][0]["stored_m3"] += 5_000_000
        errs = {f["code"] for f in validate.validate(docs, today=date(2026, 10, 23)) if f["severity"] == "error"}
        self.assertIn("totals_mismatch", errs)


class Store(unittest.TestCase):
    def setUp(self):                      # re-reading 60 PDFs three times would take minutes
        patcher = mock.patch.object(pipeline, "collect", lambda raw=None: copy.deepcopy(DOCS))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_rerun_is_idempotent_and_conflicts_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "t.sqlite")
            self.assertEqual(pipeline.main(["--db", path]), 0)
            def count():
                with closing(sqlite3.connect(path)) as c:
                    return c.execute(
                        "SELECT (SELECT COUNT(*) FROM reservoir_readings), (SELECT COUNT(*) FROM irrigation_plans), "
                        "(SELECT COUNT(*) FROM validation_flags)").fetchone()
            first = count()
            self.assertEqual(pipeline.main(["--db", path]), 0)
            self.assertEqual(count(), first)
            with closing(db.connect(path)) as con:
                with self.assertRaises(db.Conflict):
                    db.append(con, "reservoir_readings",
                              ["reservoir_id", "as_of_date", "source_file", "source_column"],
                              {**VOLUMES["readings"][0], "stored_m3": 1}, db.READING_COLS)

    def test_every_row_has_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "t.sqlite")
            pipeline.main(["--db", path])
            with closing(sqlite3.connect(path)) as con:
                for table in ("reservoir_readings", "irrigation_plans"):
                    bad = con.execute(f"SELECT COUNT(*) FROM {table} t LEFT JOIN source_documents s "
                                      "ON s.key = t.source_file WHERE s.key IS NULL OR t.source_page < 1").fetchone()[0]
                    self.assertEqual(bad, 0, table)


if __name__ == "__main__":
    unittest.main()
