"""Reference mapping: consortia, comune -> consortium, reservoir -> consortium.

The three CSVs in data/reference/ are versioned, hand-checked data. Every row names the file and page
it comes from. This module loads them, checks them, and validate_mapping() reports problems as errors.
"""
import csv
from pathlib import Path

from .util import ROOT, load_reservoirs

REF = ROOT / "data" / "reference"
CB9_TOTAL_HA = 71_304   # printed in the Statuto, art. 3


def _read(name):
    with open(REF / name, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load():
    return {"consortia": _read("consortia.csv"),
            "comune_consortium": _read("comune_consortium.csv"),
            "reservoir_consortium": _read("reservoir_consortium.csv")}


def validate_mapping(m):
    errors = []
    err = lambda code, msg: errors.append({"severity": "error", "code": code, "message": msg,
                                           "source_file": None, "source_page": None, "reservoir_id": None})
    consortia = {c["id"] for c in m["consortia"]}
    reservoirs = {r["id"] for r in load_reservoirs()[0]}
    for c in m["consortia"]:
        if c["parent_id"] and c["parent_id"] not in consortia:
            err("mapping_unknown_parent", f"{c['id']}: parent {c['parent_id']}")
    for table, rows in m.items():
        for r in rows:
            src = r["source_file"]
            if not src or not (ROOT / src).exists():
                err("mapping_missing_source", f"{table}: {r.get('id') or r.get('comune') or r.get('reservoir_id')}: "
                                              f"source file {src!r} not found")
            if not str(r["source_page"]).isdigit():
                err("mapping_missing_page", f"{table}: {r}")
    seen = set()
    for r in m["comune_consortium"]:
        if r["consortium_id"] not in consortia:
            err("mapping_unknown_consortium", f"{r['comune']}: {r['consortium_id']}")
        k = (r["istat_code"], r["consortium_id"])
        if k in seen:
            err("mapping_duplicate", f"{r['comune']} listed twice for {r['consortium_id']}")
        seen.add(k)
    ha = [int(r["area_ha_in_comprensorio"]) for r in m["comune_consortium"]
          if r["consortium_id"] == "cb9-catania" and r["area_ha_in_comprensorio"]]
    if ha and sum(ha) != CB9_TOTAL_HA:
        err("mapping_cb9_area", f"CB9 areas sum to {sum(ha)} ha, the statute prints {CB9_TOTAL_HA}")
    for r in m["reservoir_consortium"]:
        if r["reservoir_id"] not in reservoirs:
            err("mapping_unknown_reservoir", r["reservoir_id"])
        if r["consortium_id"] not in consortia:
            err("mapping_unknown_consortium", f"{r['reservoir_id']}: {r['consortium_id']}")
    return errors


def store(con, m):
    """Reference data, replaced on every run (history of readings and plans is not touched)."""
    for c in m["consortia"]:
        con.execute("INSERT OR REPLACE INTO consortia (id, name, parent_id, kind, contact, contact_source_file, "
                    "contact_source_page, note) VALUES (?,?,?,?,?,?,?,?)",
                    [c["id"], c["name"], c["parent_id"] or None, c["kind"], c["pec"] or None,
                     c["source_file"], int(c["source_page"]), c["note"]])
    con.execute("DELETE FROM comune_consortium")
    con.execute("DELETE FROM reservoir_consortium")
    from .mapping_extract import istat_index   # all 391 comuni of Sicily, so every town can be searched
    consortia_of = {}
    for r in m["comune_consortium"]:
        consortia_of.setdefault(r["istat_code"], []).append(r["consortium_id"])
    for code, name, province in istat_index().values():
        con.execute("INSERT OR REPLACE INTO comuni (istat_code, name, province, consortium_ids) VALUES (?,?,?,?)",
                    [code, name, province, ",".join(sorted(consortia_of.get(code, []))) or None])
    for r in m["comune_consortium"]:
        con.execute("INSERT INTO comune_consortium (istat_code, consortium_id, area_ha_in_comprensorio, zone, "
                    "source_file, source_page, note) VALUES (?,?,?,?,?,?,?)",
                    [r["istat_code"], r["consortium_id"],
                     int(r["area_ha_in_comprensorio"]) if r["area_ha_in_comprensorio"] else None,
                     r["zone"] or None, r["source_file"], int(r["source_page"]), r["note"]])
    for r in m["reservoir_consortium"]:
        con.execute("INSERT INTO reservoir_consortium (reservoir_id, consortium_id, relation, source_file, "
                    "source_page, note) VALUES (?,?,?,?,?,?)",
                    [r["reservoir_id"], r["consortium_id"], r["relation"], r["source_file"],
                     int(r["source_page"]), r["note"]])
