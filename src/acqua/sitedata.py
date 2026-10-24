"""Read everything the site shows from data/acqua.sqlite. No number is computed except sums and
ratios of stored figures; anything missing stays None and the templates print 'Dato non disponibile'."""
import re
import sqlite3
import unicodedata
from datetime import date

MONTHS_IT = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
             "settembre", "ottobre", "novembre", "dicembre"]


def it_date(iso):
    """'2026-10-01' -> '1 ottobre 2026'; '2025-10' -> 'ottobre 2025'."""
    if iso is None:
        return None
    y, m, *d = iso.split("-")
    return f"{int(d[0])} {MONTHS_IT[int(m) - 1]} {y}" if d else f"{MONTHS_IT[int(m) - 1]} {y}"


def slug(text):
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s)).strip("-")


def _rows(con, sql, *args):
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(sql, args)]


def load(db_path):
    con = sqlite3.connect(db_path)
    docs = {d["key"]: d for d in _rows(con, "SELECT * FROM source_documents")}
    reservoirs = {r["id"]: r for r in _rows(con, "SELECT * FROM reservoirs")}
    monthly = sorted(k for k, d in docs.items() if d["protocol"] is None)
    latest_key = max(monthly, key=lambda k: docs[k]["doc_date"])
    latest = docs[latest_key]

    # time series: one point per monthly table, from the 'current month' column
    series = {rid: [] for rid in reservoirs}
    for r in _rows(con, "SELECT reservoir_id, as_of_date, stored_m3, source_file, source_page FROM reservoir_readings "
                        "WHERE date_precision='day' AND source_file IN (%s) ORDER BY as_of_date"
                   % ",".join("?" * len(monthly)), *monthly):
        series[r["reservoir_id"]].append(r)

    year, month = latest["doc_date"][:4], latest["doc_date"][5:7]
    for r in _rows(con, "SELECT reservoir_id, as_of_date, date_precision, stored_m3, source_column, source_page "
                        "FROM reservoir_readings WHERE source_file = ?", latest_key):
        rid = r["reservoir_id"]
        reservoirs[rid].setdefault("monthly", {})
        kind = ("now" if r["date_precision"] == "day" else
                "prev" if r["source_column"].startswith("volume mese precedente") else "last_year")
        reservoirs[rid]["monthly"][kind] = r
    for rid, r in reservoirs.items():
        r["slug"] = slug(r["name"].split(" (")[0]) if r["id"] not in ("don-sturzo", "garcia", "ragoleto") \
            else slug(r["name"].split(" (")[0])
        r["series"] = series[rid]
        r["now"] = r.get("monthly", {}).get("now")
        r["last_year"] = r.get("monthly", {}).get("last_year")
        r["prev"] = r.get("monthly", {}).get("prev")

    plans = _rows(con, "SELECT * FROM irrigation_plans ORDER BY season_year, use")
    usable = {(x["reservoir_id"], x["source_file"]): x for x in _rows(
        con, "SELECT * FROM reservoir_readings WHERE usable_m3 IS NOT NULL")}
    for p in plans:
        p["doc"] = docs[p["source_file"]]
    flags = _rows(con, "SELECT * FROM validation_flags")

    consortia = {c["id"]: c for c in _rows(con, "SELECT * FROM consortia")}
    for c in consortia.values():
        c["slug"] = c["id"]
    comuni = _rows(con, "SELECT * FROM comuni ORDER BY name")
    seen = set()
    for c in comuni:
        s = slug(c["name"])
        c["slug"] = s if s not in seen else f"{s}-{slug(c['province'])}"
        seen.add(c["slug"])
        c["consortia"] = []
    by_code = {c["istat_code"]: c for c in comuni}
    for m in _rows(con, "SELECT * FROM comune_consortium"):
        by_code[m["istat_code"]]["consortia"].append(m)
    rc = _rows(con, "SELECT * FROM reservoir_consortium")
    for r in rc:
        r["doc"] = docs.get(r["source_file"].replace("\\", "/").split("/")[-1])
    con.close()
    return {"docs": docs, "reservoirs": reservoirs, "latest": latest, "plans": plans, "usable": usable,
            "flags": flags, "consortia": consortia, "comuni": comuni, "reservoir_consortium": rc,
            "built_on": date.today().isoformat()}
