"""M3: monthly volume tables 2022-01 .. 2026-10 (fetched via the Authority's year pages).

Hand-checked values were read from the PDFs' printed rows. The strongest check is structural:
for every one of the 58 tables the extracted rows sum to the printed TOTALI row.
"""
import unittest
from datetime import date

from acqua import validate

from test_m2 import DOCS

MONTHLY = {d["doc_date"][:7]: d for d in DOCS if d["kind"] == "volumes"}


def current(month, rid):
    rows = [r for r in MONTHLY[month]["readings"]
            if r["reservoir_id"] == rid and r["date_precision"] == "day"]
    assert len(rows) == 1, (month, rid)
    return rows[0]["stored_m3"]


class Monthly(unittest.TestCase):
    def test_every_month_from_2022_01_to_2026_10_is_present(self):
        expected = [f"{y}-{m:02d}" for y in range(2022, 2027) for m in range(1, 13)][:58]
        self.assertEqual(sorted(MONTHLY), expected)

    def test_rows_sum_to_printed_totals_in_every_table(self):
        for month, d in MONTHLY.items():
            total = sum(r["stored_m3"] for r in d["readings"] if r["date_precision"] == "day")
            self.assertLessEqual(abs(total - d["totals"]["current_m3"]), 20_000, month)
            last_year = sum(r["stored_m3"] for r in d["readings"]
                            if r["source_column"].startswith("volume stesso mese"))
            self.assertLessEqual(abs(last_year - d["totals"]["last_year_m3"]), 20_000, month)

    def test_hand_checked_rows_from_older_layouts(self):
        self.assertEqual(current("2024-06", "ancipa"), 6_780_000)        # printed 6,78, no index column
        self.assertEqual(MONTHLY["2024-06"]["totals"]["current_m3"], 288_450_000)
        self.assertEqual(current("2022-05", "scanzano"), 7_440_000)
        self.assertEqual(current("2022-05", "poma"), 68_910_000)
        self.assertEqual(MONTHLY["2023-06"]["totals"]["current_m3"], 520_820_000)  # this file prints dots

    def test_piano_del_leone_name_is_cut_in_the_pdf_text_layer(self):
        # 2023-03 .. 2024-09 print only 'LEONE'; the row is identified by the alias list
        self.assertEqual(current("2024-06", "piano-del-leone"), 1_220_000)

    def test_dams_added_over_time(self):
        self.assertEqual(len(MONTHLY["2022-05"]["reservoirs"]), 25)
        self.assertEqual(len(MONTHLY["2026-10"]["reservoirs"]), 30)

    def test_revisions_between_tables_are_warnings_not_errors(self):
        flags = validate.validate(DOCS, today=date(2026, 10, 23))
        self.assertEqual([f for f in flags if f["severity"] == "error"], [])
        self.assertTrue(any(f["code"] == "revised_value" and f["reservoir_id"] == "olivo" for f in flags))

    def test_every_monthly_row_has_source_url(self):
        for d in MONTHLY.values():
            self.assertTrue(d["url"].startswith("https://www.regione.sicilia.it/system/files/"), d["key"])


if __name__ == "__main__":
    unittest.main()
