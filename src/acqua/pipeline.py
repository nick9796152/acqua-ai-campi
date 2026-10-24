"""extract -> validate -> store. Nothing is written if validation finds an error.

Usage:  python -m acqua.pipeline [--db data/acqua.sqlite]
"""
import argparse
import hashlib
import sys
from datetime import date
from pathlib import Path

from . import db, mapping, extract_plans as ep, extract_volumes as ev, fetch, validate as val
from .util import RAW, ROOT, load_reservoirs

BASE = "https://www.regione.sicilia.it/system/files/"

# pattern (in data/raw/regione-sicilia), kind, extractor, protocol, document date, title, url path
SOURCES = [
    ("*2026-10116-pianificazione_irriguo_sicilia_occ.pdf", "plan", ep.west_irrigation, "10116", "2026-04-02",
     "Pianificazione risorsa idrica 2026 - invasi uso irriguo Sicilia occidentale",
     "2026-05/4_2026-10116-pianificazione_irriguo_sicilia_occ.pdf"),
    ("*2026-10109_del_02.04.2026-pianificazione*orientale*.pdf", "plan", ep.east_irrigation_industrial, "10109",
     "2026-04-02", "Pianificazione risorsa idrica 2026 - invasi uso irriguo e industriale Sicilia orientale",
     "2026-05/5_2026-10109_del_02.04.2026-pianificazione_uso_irriguo_e_industriale_sicilia_orientale_signed_signed_signed.pdf"),
    ("*2026-10705-provvedimento*santa_rosalia*.pdf", "plan", ep.santa_rosalia, "10705", "2026-04-09",
     "Provvedimento pianificazione 2026 - invaso Santa Rosalia",
     "2026-05/3_2026-10705-provvedimento_pianificazione_2026_santa_rosalia_signed_signed.pdf"),
    ("*2026-10706-provvedimento*pozzillo*.pdf", "plan", ep.pozzillo, "10706", "2026-04-09",
     "Provvedimento pianificazione 2026 - invaso Pozzillo",
     "2026-05/2_2026-10706-provvedimento_pianificazione_2026_pozzillo_signed_signed_0.pdf"),
    ("*2026-14046_11.05.2026*castello*.pdf", "plan", ep.castello, "14046", "2026-05-11",
     "Provvedimento pianificazione 2026 - invaso Castello",
     "2026-05/1_2026-14046_11.05.2026-provvedimento_pianificazione_2026-castello_signed_signed.pdf"),
    ("*2026-14387_14.05.2026*sistemapalermo*.pdf", "plan", ep.sistema_palermo, "14387", "2026-05-14",
     "Provvedimento pianificazione 2026 - invasi a uso plurimo area metropolitana di Palermo e Prizzi",
     "2026-05/0_2026-14387_14.05.2026-provvedimento_pianificazione_2026-sistemapalermo_signed_signed_signed.pdf"),
    ("*15267_del_21.05.2026*ancipa_ragoleto*.pdf", "plan", ep.ancipa_ragoleto, "15267", "2026-05-21",
     "Provvedimento pianificazione 2026 - invasi Ancipa e Ragoleto",
     "2026-08/prot._n._15267_del_21.05.2026_provvedimento_pianificazione_2026_ancipa_ragoleto_sicilia_orientale.pdf"),
    ("*21823_del_28.07.2026_assegnazione_irriguo_ancipa.pdf", "plan", ep.ancipa_assignment, "21823", "2026-07-28",
     "Assegnazione acque per uso irriguo dall'invaso Ancipa",
     "2026-08/prot._n._21823_del_28.07.2026_assegnazione_irriguo_ancipa.pdf"),
]

def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


MONTHS_IT = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
             "settembre", "ottobre", "novembre", "dicembre"]


def collect_volumes():
    """Monthly volume tables listed in the fetch manifest (url and month come from the Authority's page)."""
    docs = []
    for rel, info in sorted(fetch.load_manifest().items(), key=lambda kv: kv[1]["month"]):
        path = ROOT / rel
        y, m = info["month"].split("-")
        readings, reservoirs, totals, as_of = ev.extract(path)
        if as_of[:7] != info["month"]:
            raise SystemExit(f"{path.name}: page lists {info['month']} but the PDF says {as_of}")
        if sha256(path) != info["sha256"]:
            raise SystemExit(f"{path.name}: file changed since the fetch manifest was written")
        docs.append({"key": path.name, "file": rel, "sha256": info["sha256"], "url": info["url"],
                     "protocol": None, "doc_date": as_of, "kind": "volumes",
                     "title": f"Prospetto volumi invasati nelle dighe della Sicilia al 1° {MONTHS_IT[int(m) - 1]} {y}",
                     "readings": readings, "plans": [], "reservoirs": reservoirs, "totals": totals,
                     "source_file_readings": True})
        for r in readings:
            r["source_file"] = path.name
    return docs


def collect(raw=RAW):
    docs = collect_volumes()
    for pattern, kind, fn, protocol, doc_date, title, url in SOURCES:
        files = sorted(Path(raw).glob(pattern))
        if len(files) != 1:
            raise SystemExit(f"{pattern}: expected one file in {raw}, found {len(files)}")
        path = files[0]
        meta = {"key": path.name, "file": str(path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256(path), "url": BASE + url, "protocol": protocol,
                "doc_date": doc_date, "title": title, "kind": kind,
                "readings": [], "plans": [], "reservoirs": [], "totals": None}
        if kind == "volumes":
            meta["readings"], meta["reservoirs"], meta["totals"], _ = fn(path)
        else:
            meta["readings"], meta["plans"] = fn(path)
        for r in meta["readings"] + meta["plans"]:
            r["source_file"] = meta["key"]
        docs.append(meta)
    return docs


MAPPING = None


def store(con, docs, flags, today):
    names = {r["id"]: r["name"] for r in load_reservoirs()[0]}
    for d in docs:
        old = con.execute("SELECT sha256 FROM source_documents WHERE key=?", [d["key"]]).fetchone()
        if old is None:
            con.execute("INSERT INTO source_documents (key, file, sha256, url, protocol, doc_date, title, "
                        "ingested_on) VALUES (?,?,?,?,?,?,?,?)",
                        [d["key"], d["file"], d["sha256"], d["url"], d["protocol"], d["doc_date"],
                         d["title"], today])
        elif old[0] != d["sha256"]:
            raise db.Conflict(f"{d['key']}: file content changed since it was first ingested")
    # reservoirs is reference data: it carries the latest table's capacity, manager and use.
    latest = max((d for d in docs if d["kind"] == "volumes"), key=lambda d: d["doc_date"])
    for r in latest["reservoirs"]:
        con.execute("INSERT OR REPLACE INTO reservoirs (id, name, river, capacity_m3, use_label, manager, "
                    "capacity_source_file) VALUES (?,?,?,?,?,?,?)",
                    [r["id"], names[r["id"]], r["river"], r["capacity_m3"], r["use_label"], r["manager"],
                     latest["key"]])
    known = {r[0] for r in con.execute("SELECT id FROM reservoirs")}
    for d in docs:                                   # reservoirs only seen in older tables
        for r in d["reservoirs"]:
            if r["id"] not in known:
                con.execute("INSERT INTO reservoirs (id, name, river, capacity_m3, use_label, manager, "
                            "capacity_source_file) VALUES (?,?,?,?,?,?,?)",
                            [r["id"], names[r["id"]], r["river"], r["capacity_m3"], r["use_label"],
                             r["manager"], d["key"]])
                known.add(r["id"])
    mapping.store(con, MAPPING)
    for d in docs:
        for r in d["readings"]:
            db.append(con, "reservoir_readings",
                      ["reservoir_id", "as_of_date", "source_file", "source_column"], r, db.READING_COLS)
        for p in d["plans"]:
            db.append(con, "irrigation_plans",
                      ["reservoir_id", "group_label", "season_year", "use", "as_of_date", "source_file"],
                      p, db.PLAN_COLS)
    for f in flags:
        con.execute("INSERT OR IGNORE INTO validation_flags (severity, code, source_file, source_page, "
                    "reservoir_id, message, recorded_on) VALUES (?,?,?,?,?,?,?)",
                    [f["severity"], f["code"], f["source_file"], f["source_page"], f["reservoir_id"],
                     f["message"], today])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "data" / "acqua.sqlite"))
    args = ap.parse_args(argv)
    today = date.today().isoformat()
    global MAPPING
    docs = collect()
    MAPPING = mapping.load()
    flags = val.validate(docs) + mapping.validate_mapping(MAPPING)
    errors = [f for f in flags if f["severity"] == "error"]
    for f in flags:
        print(f"[{f['severity']}] {f['code']} {f['reservoir_id'] or ''} {f['source_file'] or ''}: {f['message']}")
    if errors:
        print(f"{len(errors)} error(s): nothing written, last good database kept.", file=sys.stderr)
        return 1
    con = db.connect(args.db)
    try:
        with con:
            store(con, docs, flags, today)
    finally:
        con.close()
    print(f"ok: {sum(len(d['readings']) for d in docs)} readings, {sum(len(d['plans']) for d in docs)} plans, "
          f"{len(flags)} warning(s) -> {args.db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
