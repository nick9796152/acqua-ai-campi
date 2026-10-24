"""M3: comune <-> consortium <-> reservoir mapping (versioned CSVs in data/reference/)."""
import copy
import unittest

from acqua import mapping

M = mapping.load()
BY_NAME = {}
for r in M["comune_consortium"]:
    BY_NAME.setdefault(r["comune"], []).append(r)


class Mapping(unittest.TestCase):
    def test_real_files_pass_validation(self):
        self.assertEqual(mapping.validate_mapping(M), [])

    def test_cb9_catania_statute_art3(self):
        cb9 = [r for r in M["comune_consortium"] if r["consortium_id"] == "cb9-catania"]
        original = [r for r in cb9 if not r["zone"]]
        self.assertEqual(len(original), 20)
        self.assertEqual(sum(int(r["area_ha_in_comprensorio"]) for r in original), 71_304)
        self.assertEqual(BY_NAME["Catania"][0]["area_ha_in_comprensorio"], "10378")
        self.assertEqual(BY_NAME["Mineo"][0]["area_ha_in_comprensorio"], "233")   # only 233 ha of Mineo
        self.assertEqual((BY_NAME["Lentini"][0]["province"], BY_NAME["Lentini"][0]["istat_code"]),
                         ("Siracusa", "089011"))
        self.assertEqual(BY_NAME["Castel di Iudica"][0]["area_ha_in_comprensorio"], "542")  # statute: 'Judica'

    def test_cb9_area_z_has_the_seven_added_comuni(self):
        z = sorted(r["comune"] for r in M["comune_consortium"] if r["zone"] == "Area Z")
        self.assertEqual(z, sorted(["Valverde", "Aci Bonaccorsi", "Aci Catena", "Aci Sant'Antonio",
                                    "San Giovanni la Punta", "Aci Castello", "San Gregorio di Catania"]))
        self.assertTrue(all(r["area_ha_in_comprensorio"] == "" for r in M["comune_consortium"] if r["zone"]))

    def test_cb3_agrigento_list(self):
        cb3 = [r for r in M["comune_consortium"] if r["consortium_id"] == "cb3-agrigento"]
        self.assertEqual(len(cb3), 53)       # the report says 56 but lists 53 names; see docs/mapping-notes.md
        by_prov = {p: sum(1 for r in cb3 if r["province"] == p) for p in ("Agrigento", "Caltanissetta", "Palermo", "Trapani")}
        self.assertEqual(by_prov, {"Agrigento": 40, "Caltanissetta": 6, "Palermo": 5, "Trapani": 2})
        for name in ("Ribera", "Sciacca", "Castelvetrano", "Prizzi", "Santa Margherita di Belice", "Lampedusa e Linosa"):
            self.assertIn(name, BY_NAME)

    def test_no_comune_is_in_two_consortia(self):
        self.assertTrue(all(len(v) == 1 for v in BY_NAME.values()))

    def test_every_row_names_an_existing_source_file_and_page(self):
        for table, rows in M.items():
            for r in rows:
                self.assertTrue(r["source_page"].isdigit(), (table, r))

    def test_ribera_to_castello_reservoir_chain(self):
        ribera = BY_NAME["Ribera"][0]["consortium_id"]
        reservoirs = {r["reservoir_id"] for r in M["reservoir_consortium"] if r["consortium_id"] == ribera}
        self.assertEqual(ribera, "cb3-agrigento")
        self.assertIn("castello", reservoirs)

    def test_catania_area_reaches_pozzillo(self):
        cb = BY_NAME["Paternò"][0]["consortium_id"]
        self.assertIn("pozzillo", {r["reservoir_id"] for r in M["reservoir_consortium"] if r["consortium_id"] == cb})

    def test_validation_catches_bad_rows(self):
        bad = copy.deepcopy(M)
        bad["comune_consortium"][0]["consortium_id"] = "cb99-inventato"
        bad["reservoir_consortium"][0]["reservoir_id"] = "diga-inventata"
        bad["comune_consortium"][1]["source_file"] = "data/raw/non-esiste.pdf"
        bad["comune_consortium"].append(dict(bad["comune_consortium"][2]))      # duplicate
        codes = {e["code"] for e in mapping.validate_mapping(bad)}
        self.assertTrue({"mapping_unknown_consortium", "mapping_unknown_reservoir", "mapping_missing_source",
                         "mapping_duplicate"} <= codes)


if __name__ == "__main__":
    unittest.main()
