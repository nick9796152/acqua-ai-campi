"""Build data/reference/comune_consortium.csv from the two consortium documents we hold.

Usage:  python -m acqua.mapping_extract        (rewrites the CSV; review it with `git diff`)

Sources (each row of the CSV records file and page):
  - Consorzio di Bonifica 9 Catania: Statuto (annex of Giunta regionale deliberation n. 194 of 14/05/2026),
    art. 3 (comuni with surface in ha inside the comprensorio) and the seven comuni added as "Area Z".
  - Consorzio di Bonifica 3 Agrigento: Relazione generale of the 2025-2027 public works programme, p. 3.
The other consortia have no list yet (see docs/mapping-notes.md); add their rows to the CSV by hand,
with a source for every row, and keep this script for the two it reads.
"""
import csv
import glob
import re
import sys
import unicodedata

import openpyxl
import pdfplumber

from .util import RAW, ROOT, ExtractionError

REF = ROOT / "data" / "reference"
GIUNTA = glob.glob(str(ROOT / "data" / "raw" / "regione-sicilia-giunta" / "*N.194_14.05.2026.pdf"))
CB3 = glob.glob(str(ROOT / "data" / "raw" / "bonifica3ag" / "*RELAZIONE_PROGR_TRIENNALE*.pdf"))
ISTAT = glob.glob(str(ROOT / "data" / "raw" / "istat" / "*Elenco-comuni-italiani.xlsx"))

# Spellings in the source documents that differ from ISTAT's official name.
ALIASES = {
    "motta s. anastasia": "Motta Sant'Anastasia", "s.teodoro": "San Teodoro",
    "castel di judica": "Castel di Iudica", "acicastello": "Aci Castello",
    "santa margherita belice": "Santa Margherita di Belice", "lampedusa": "Lampedusa e Linosa",
}
FIELDS = ["comune", "province", "istat_code", "consortium_id", "area_ha_in_comprensorio", "zone",
          "source_file", "source_page", "note"]


def key(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9. ]", "", re.sub(r"[’`´]", "'", s).replace("'", "")).strip()


def istat_index():
    wb = openpyxl.load_workbook(ISTAT[0], read_only=True)
    idx = {}
    for r in wb[wb.sheetnames[0]].iter_rows(min_row=2, values_only=True):
        if r[0] is not None and str(r[0]).strip() == "19":
            idx[(key(r[6]), r[11])] = (r[4], r[6], r[11])          # (code, name, province)
    return idx


def resolve(name, province, idx):
    for cand in (ALIASES.get(name.lower(), name), name):
        hit = idx.get((key(cand), province))
        if hit:
            return hit
    raise ExtractionError(f"{name!r} ({province}) not found in the ISTAT list for Sicily")


def cb9(idx):
    rows = []
    with pdfplumber.open(GIUNTA[0]) as pdf:
        text = {p: pdf.pages[p - 1].extract_text() for p in (17, 18)}
    province = None
    seen = []
    for page in (17, 18):
        for line in text[page].split("\n"):
            m = re.match(r"^Provincia di (\w+)", line)
            if m:
                province = m.group(1).capitalize()
            m = re.match(r"^(\d+)\) (.+?) (?:superficie )?[\"“”] ?Ha ([\d.]+)$|^(\d+)\) (.+?) superficie Ha ([\d.]+)$", line)
            if m:
                n, name, ha = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(4), m.group(5), m.group(6))
                name = re.sub(r"\s+l$", "", name.strip())          # stray 'l' in the PDF text of row 4
                seen.append((int(n), name, province, int(ha.replace(".", "")), page))
    if [s[0] for s in seen] != list(range(1, 21)):
        raise ExtractionError(f"CB9: expected comuni 1..20, got {[s[0] for s in seen]}")
    total = sum(s[3] for s in seen)
    if total != 71_304:
        raise ExtractionError(f"CB9: areas sum to {total} ha, the statute prints 71.304")
    for _, name, prov, ha, page in seen:
        code, official, pname = resolve(name, prov, idx)
        rows.append(dict(comune=official, province=pname, istat_code=code, consortium_id="cb9-catania",
                         area_ha_in_comprensorio=ha, zone="", source_file=_rel(GIUNTA[0]), source_page=page,
                         note=f"Statuto art. 3, n. {_}; la superficie e' quella del comprensorio nel comune, non del comune"))
    flat = re.sub(r"\s+", " ", text[17].replace("\n", " "))
    m = re.search(r"quelli di (.+?) che costituiscono l.AREA Z", flat)
    if not m:
        raise ExtractionError("CB9: Area Z sentence not found")
    for name in re.split(r", | e (?=San Gregorio)", m.group(1)):
        code, official, pname = resolve(name.strip(), "Catania", idx)
        rows.append(dict(comune=official, province=pname, istat_code=code, consortium_id="cb9-catania",
                         area_ha_in_comprensorio="", zone="Area Z", source_file=_rel(GIUNTA[0]), source_page=17,
                         note="Aggiunto al comprensorio con la modifica dello Statuto (Giunta, delibera 194 del 14/05/2026); superficie non indicata"))
    if len([r for r in rows if r["zone"] == "Area Z"]) != 7:
        raise ExtractionError("CB9: expected seven Area Z comuni")
    return rows


def cb3(idx):
    with pdfplumber.open(CB3[0]) as pdf:
        text = pdf.pages[2].extract_text()
    flat = re.sub(r"\s+", " ", text)
    rows, count = [], 0
    for prov in ("Agrigento", "Caltanissetta", "Palermo", "Trapani"):
        nxt = {"Agrigento": "Caltanissetta", "Caltanissetta": "Palermo", "Palermo": "Trapani", "Trapani": "Al fine"}[prov]
        m = re.search(rf"• Provincia di {prov} (.+?) (?:• Provincia di {nxt}|{nxt})", flat)
        if not m:
            raise ExtractionError(f"CB3: province block {prov} not found")
        names = [n.strip().rstrip(".") for n in re.split(r", | e (?=[A-Z])", m.group(1))]
        for name in names:
            code, official, pname = resolve(name, prov, idx)
            rows.append(dict(comune=official, province=pname, istat_code=code, consortium_id="cb3-agrigento",
                             area_ha_in_comprensorio="", zone="", source_file=_rel(CB3[0]), source_page=3,
                             note="Elenco dei comuni del comprensorio; superficie per comune non indicata"))
        count += len(names)
    return rows, count


def _rel(path):
    return str(path).replace("\\", "/").split("acqua-ai-campi/")[-1]


def main():
    idx = istat_index()
    nine = cb9(idx)
    three, n3 = cb3(idx)
    REF.mkdir(parents=True, exist_ok=True)
    with open(REF / "comune_consortium.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        w.writerows(nine + three)
    print(f"CB9: {len(nine)} comuni; CB3: {n3} comuni listed (the document text says 56)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
