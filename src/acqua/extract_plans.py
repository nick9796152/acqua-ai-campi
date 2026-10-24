"""Authority of Basin planning documents for 2026 (one extractor per layout).

Every table layout differs, so each function names its columns explicitly.
Column order was checked against rendered page images; the tests pin the values.
Merged cells (a single planned/need figure for two reservoirs) become a plan row
with `group_label` and no reservoir_id, so nothing is counted twice.
"""
import re

import pdfplumber

from .util import (ExtractionError, load_reservoirs, numbers, parse_date, parse_mc,
                   parse_mmc, reservoir_id)

_, ALIAS = load_reservoirs()


def _pages(path):
    with pdfplumber.open(path) as pdf:
        return [(p.extract_text() or "") for p in pdf.pages]


def _row(pages, label, count, parse, *, only_page=None):
    """Find 'label n1 n2 ...' at line start; return (page_no, [parsed numbers], rest of line)."""
    pat = re.compile(rf"^{re.escape(label)}\s+(\d.*)$", re.M)
    hits = [(i + 1, m.group(1)) for i, t in enumerate(pages) for m in pat.finditer(t)
            if only_page in (None, i + 1)]
    if len(hits) != 1:
        raise ExtractionError(f"{label!r}: expected one row, found {len(hits)}")
    page, rest = hits[0]
    toks = numbers(rest)[:count]
    if len(toks) != count:
        raise ExtractionError(f"{label!r}: expected {count} numbers in {rest!r}")
    return page, [parse(t) for t in toks], rest


def _mc(n):
    return f"{n:,}".replace(",", ".") + " mc"


def _need(pages, phrase):
    flat = re.sub(r"-\n", "", " ".join(pages)).replace("’", "'")
    flat = re.sub(r"\s+", " ", flat)
    if phrase not in flat:
        raise ExtractionError(f"expected text not found: {phrase!r}")


def _reading(rid, as_of, stored, usable, page, col, notes=None):
    return {"reservoir_id": rid, "as_of_date": as_of, "date_precision": "day", "stored_m3": stored,
            "usable_m3": usable, "source_page": page, "source_column": col, "notes": notes}


def _plan(rid, use, needs, planned, as_of, page, notes=None, group=None):
    return {"reservoir_id": rid, "group_label": group, "season_year": 2026, "use": use,
            "needs_m3": needs, "planned_m3": planned, "as_of_date": as_of,
            "source_page": page, "notes": notes}


def _rid(name):
    return reservoir_id(name, ALIAS)


# --------------------------------------------------------------------------- west

def west_irrigation(path):
    """Prot. 10116 'Sicilia occidentale': mc; columns invasato, utile netto, fabbisogno, pianificato."""
    pages = _pages(path)
    asof = "2026-03-16"
    _need(pages, "Dati al 16/03/2026")
    readings, plans = [], []
    col = "volume invasato / volume utile netto (dati al 16/03/2026)"

    def simple(name, note=None):
        page, (inv, use, need, plan), _ = _row(pages, name, 4, parse_mc)
        rid = _rid(name)
        readings.append(_reading(rid, asof, inv, use, page, col))
        plans.append(_plan(rid, "irriguo", need, plan, asof, page, note))

    for name in ("Arancio", "Comunelli", "Gorgo", "Paceco", "Rubino", "Zaffarana"):
        simple(name)
    simple("Trinità", "Volume assegnato sulla base delle attuali disponibilità")
    _need(pages, "Il volume viene assegnato sulla base delle attuali disponibilità")

    # Cimia / Disueri: the invasato of Cimia sits on its own line, the planned figure is merged.
    pg_c, (cimia_use, cimia_need), _ = _row(pages, "Cimia", 2, parse_mc)
    cimia_inv = parse_mc(re.search(r"^(\d{1,3}(?:\.\d{3})+)$", pages[pg_c - 1], re.M).group(1))
    pg_d, (dis_inv, dis_use, dis_need), _ = _row(pages, "Disueri", 3, parse_mc)
    group_plan = parse_mc(re.search(r"^(1\.759\.200)$", pages[pg_c - 1], re.M).group(1))
    if (cimia_inv, cimia_use, cimia_need, group_plan) != (3049200, 1759200, 720000, 1759200):
        raise ExtractionError("Cimia/Disueri row changed, re-check against the PDF image")
    # The merged planned figure is printed between the two halves of the note.
    _need(pages, "La pianificazione è intesa per l'intero")
    _need(pages, "sistema Cimia-Disueri")
    readings += [_reading("cimia", asof, cimia_inv, cimia_use, pg_c, col),
                 _reading("disueri", asof, dis_inv, dis_use, pg_d, col)]
    plans += [_plan("cimia", "irriguo", cimia_need, None, asof, pg_c, "Pianificato indicato per l'intero sistema Cimia-Disueri"),
              _plan("disueri", "irriguo", dis_need, None, asof, pg_d, "Pianificato indicato per l'intero sistema Cimia-Disueri"),
              _plan(None, "irriguo", None, group_plan, asof, pg_c,
                    "Pianificazione intesa per l'intero sistema Cimia-Disueri", group="Cimia-Disueri")]

    # San Giovanni / Furore: need and planned figures are merged cells.
    pg_s, (sg_inv, sg_use), _ = _row(pages, "San Giovanni", 2, parse_mc)
    pg_f, (fu_inv, fu_use), _ = _row(pages, "Furore", 2, parse_mc)
    m = re.search(r"^(6\.000\.000) (6\.000\.000)\b", pages[pg_s - 1], re.M)
    if not m:
        raise ExtractionError("San Giovanni/Furore merged need/planned not found")
    _need(pages, "La pianificazione è intesa per l'intero")
    _need(pages, "San Giovanni Furore")
    _need(pages, "Si assegna quanto richiesto")
    readings += [_reading("san-giovanni", asof, sg_inv, sg_use, pg_s, col),
                 _reading("furore", asof, fu_inv, fu_use, pg_f, col)]
    plans.append(_plan(None, "irriguo", parse_mc(m.group(1)), parse_mc(m.group(2)), asof, pg_s,
                       "Pianificazione intesa per l'intero sistema San Giovanni-Furore. Si assegna quanto richiesto",
                       group="San Giovanni-Furore"))
    return readings, plans


# --------------------------------------------------------------------------- east

def east_irrigation_industrial(path):
    """Prot. 10109 'Sicilia orientale': Mmc; one row per reservoir, per-row date."""
    pages = _pages(path)
    readings, plans = [], []
    for label in ("Don Sturzo/Ogliastro", "Lentini", "Nicoletti", "Olivo", "Sciaguana"):
        pat = re.compile(rf"^{re.escape(label)}\s+(\d{{2}}/\d{{2}}/\d{{4}})\s+(.*)$", re.M)
        hits = [(i + 1, m) for i, t in enumerate(pages) for m in pat.finditer(t)]
        if len(hits) != 1:
            raise ExtractionError(f"{label!r}: expected one row")
        page, m = hits[0]
        asof = parse_date(m.group(1))
        n = [parse_mmc(t) for t in numbers(m.group(2))]
        rid = _rid(label)
        if len(n) == 5:        # inv, utile, fabb irr, pian irr, totale
            inv, use, fi, pi, tot = n
            fx = px = None
        elif len(n) == 7:      # ... plus fabb ind, pian ind
            inv, use, fi, pi, fx, px, tot = n
        else:
            raise ExtractionError(f"{label!r}: unexpected number count {len(n)}")
        if tot != pi + (px or 0):
            raise ExtractionError(f"{label!r}: totale pianificato does not equal irriguo+industriale")
        readings.append(_reading(rid, asof, inv, use, page,
                                 f"volume invasato / utile netto al 31.12.2026 (rilevazione {m.group(1)})"))
        plans.append(_plan(rid, "irriguo", fi, pi, asof, page))
        if px is not None:
            plans.append(_plan(rid, "industriale", fx, px, asof, page,
                               "Pianificato industriale ripartito: 0,39 Mmc ATI Enna, 0,07 Mmc Sicily Outlet Village"))
    _need(pages, "è ripartito in 0,39 Mmc per ATI Enna, 0,07 Mmc per gli usi di Sicily Outlet Village")
    return readings, plans


# ------------------------------------------------------------ single-reservoir docs

def santa_rosalia(path):
    pages = _pages(path)
    t = pages[2]
    # The label and date are split over two lines ("Santa 16/03/20" / "Rosalia 26").
    if not re.search(r"^Santa 16/03/20$", t, re.M) or not re.search(r"^Rosalia 26\b", t, re.M):
        raise ExtractionError("Santa Rosalia label/date not found")
    m = re.search(r"^((?:\d+(?:,\d+)? ){6}\d+(?:,\d+)?)\b", t, re.M)
    if not m:
        raise ExtractionError("Santa Rosalia numbers not found")
    inv, use, pot_n, pot_p, irr_n, irr_p, tot = (parse_mmc(x) for x in m.group(1).split())
    if tot != pot_p + irr_p:
        raise ExtractionError("Santa Rosalia totale mismatch")
    asof = "2026-03-16"
    return ([_reading("santa-rosalia", asof, inv, use, 3, "volume invasato / utile netto al 30.09.2026")],
            [_plan("santa-rosalia", "potabile", pot_n, pot_p, asof, 3,
                   "Fabbisogno potabile stimato provvisoriamente (1,0 Mmc consorzio + 0,5 Mmc ATI Ragusa sulla base degli anni passati)"),
             _plan("santa-rosalia", "irriguo", irr_n, irr_p, asof, 3)])


def pozzillo(path):
    pages = _pages(path)
    page, n, rest = _row(pages, "Pozzillo", 4, parse_mmc)
    asof = parse_date(rest if DATE_HAS(rest) else pages[page - 1])
    inv, use, need, plan = n
    # The covering letter says 'al 23 marzo', the table says 30/03/2026: keep the table date.
    return ([_reading("pozzillo", asof, inv, use, page, "volume invasato / utile netto al 30.09.2026",
                      "La lettera di accompagnamento cita i volumi utili 'al 23 marzo', la tabella indica il 30/03/2026")],
            [_plan("pozzillo", "irriguo", need, plan, asof, page,
                   "Tutto il volume utile è riservato agli usi irrigui")])


def DATE_HAS(s):
    return bool(re.search(r"\d{2}/\d{2}/\d{4}", s))


def castello(path):
    pages = _pages(path)
    page, n, _ = _row(pages, "Castello", 7, parse_mc)
    inv, use, pot_need, pot_q1, pot_plan, irr_need, irr_plan = n
    asof = "2026-04-20"   # covering letter: 'volumi utili al 20 aprile u.s.'
    _need(pages, "volumi utili al 20 aprile u.s.")
    note = "Data dal testo della lettera (volumi utili al 20 aprile)"
    return ([_reading("castello", asof, inv, use, page, "volume invasato / utile netto", note)],
            [_plan("castello", "potabile", pot_need, pot_plan, asof, page,
                   f"Fabbisogno potabile 1° trimestre 2027: {_mc(pot_q1)}"),
             _plan("castello", "irriguo", irr_need, irr_plan, asof, page)])


def sistema_palermo(path):
    pages = _pages(path)
    _need(pages, "al 20 aprile u.s. per gli invasi gestiti dal DAR e al 27 aprile u.s. per quelli gestiti da ENEL")
    # Dates follow the managing entity listed in the monthly volume table (DAR vs ENEL).
    dates = {"poma": "2026-04-20", "rosamarina": "2026-04-20", "scanzano": "2026-04-20",
             "piana-degli-albanesi": "2026-04-27", "prizzi": "2026-04-27"}
    readings, plans = [], []
    for label in ("Poma", "Rosamarina", "Scanzano", "Piana", "Prizzi"):
        page, n, _ = _row(pages, label, 8, parse_mc, only_page=4)
        inv, use, pot_need, pot_q1, pot_plan, irr_need, irr_plan, ind_plan = n
        rid = _rid(label)
        asof = dates[rid]
        note = "Data scelta in base al gestore (DAR o ENEL) indicato nel prospetto volumi invasati"
        extra = None
        if rid == "piana-degli-albanesi":
            extra = "Volume totale Piana + Guadalami (evaporazione riferita al solo invaso di Piana)"
        readings.append(_reading(rid, asof, inv, use, page, "volume invasato / utile netto", extra or note))
        plans.append(_plan(rid, "potabile", pot_need, pot_plan, asof, page,
                           f"Fabbisogno potabile 1° trimestre 2027: {_mc(pot_q1)}"))
        plans.append(_plan(rid, "irriguo", irr_need, irr_plan, asof, page))
        if ind_plan:
            plans.append(_plan(rid, "industriale", None, ind_plan, asof, page, "Distilleria Bertolino SpA (tabella 2)"))
    return readings, plans


def ancipa_ragoleto(path):
    pages = _pages(path)
    t = pages[3]
    ma = re.search(r"^Ancipa 27/04/2026 ([\d, ]+)$", t, re.M)
    mr = re.search(r"^Ragoleto 20/04/2026 ([\d, ]+)", t, re.M)
    if not ma or not mr:
        raise ExtractionError("Ancipa/Ragoleto rows not found")
    a = [parse_mmc(x) for x in ma.group(1).split()]
    r = [parse_mmc(x) for x in mr.group(1).split()]
    if len(a) != 6 or len(r) != 10:
        raise ExtractionError("Ancipa/Ragoleto: unexpected number of columns")
    # Ancipa: irrigation and industrial cells are blank in the PDF, so only the potable figures exist.
    a_inv, a_use, a_pot_need, a_pot_h1, a_pot_plan, a_tot = a
    (r_inv, r_use, r_pot_need, r_pot_h1, r_irr_need, r_ind_need,
     r_pot_plan, r_irr_plan, r_ind_plan, r_tot) = r
    if r_tot != r_pot_plan + r_irr_plan + r_ind_plan or a_tot != a_pot_plan:
        raise ExtractionError("Ancipa/Ragoleto totals do not add up")
    d_a, d_r = "2026-04-27", "2026-04-20"
    col = "volume invasato / utile netto al 31/12/2026"
    return ([_reading("ancipa", d_a, a_inv, a_use, 4, col), _reading("ragoleto", d_r, r_inv, r_use, 4, col)],
            [_plan("ancipa", "potabile", a_pot_need, a_pot_plan, d_a, 4,
                   f"Fabbisogno potabile 1° semestre 2027: {_mc(a_pot_h1)}. Nessun volume irriguo pianificato in questa tabella"),
             _plan("ragoleto", "potabile", r_pot_need, r_pot_plan, d_r, 4,
                   f"Fabbisogno potabile 1° semestre 2027: {_mc(r_pot_h1)}"),
             _plan("ragoleto", "irriguo", r_irr_need, r_irr_plan, d_r, 4),
             _plan("ragoleto", "industriale", r_ind_need, r_ind_plan, d_r, 4,
                   "Ripartito: 1,10 Mmc Bioraffineria di Gela, 0,30 Mmc consorzi SAIE")])


def ancipa_assignment(path):
    pages = _pages(path)
    _need(pages, "assegnazione di 4 milioni di mc per uso irriguo dall'invaso Ancipa")
    _need(pages, "seduta del 10/7/2026")
    return [], [_plan("ancipa", "irriguo", None, 4_000_000, "2026-07-10", 1,
                      "Assegnazione stabilita dall'Osservatorio nella seduta del 10/07/2026, su richiesta dell'Assessore all'agricoltura (prot. 8796 del 02/07/2026)")]
