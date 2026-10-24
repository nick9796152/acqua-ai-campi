"""Monthly 'Prospetto volumi invasati nelle dighe della Sicilia' (one-page PDF).

The layout changed over the years (row index column present or not, page footnotes, markers
such as (*) after names), so columns are located from the header words of each file and a
row is any text line carrying exactly five decimal numbers in the number columns.
"""
import re

import pdfplumber

from .util import ExtractionError, load_reservoirs, norm, parse_mmc, reservoir_id

ALIAS = load_reservoirs()[1]

MONTHS = {"gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
          "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12}
MARKER = re.compile(r"^\((?:\*+|°+|□)\)$")
DECIMAL = re.compile(r"^-?\d+(?:,\d+|\.\d{1,2})$")


def _header(words):
    """x positions of the header columns and the y where the body starts."""
    corso = [w for w in words if w["text"] == "CORSO" and w["top"] < 260]
    if len(corso) != 1:
        raise ExtractionError(f"header word 'CORSO' not found exactly once (found {len(corso)})")
    top = corso[0]["top"]
    near = [w for w in words if abs(w["top"] - top) < 6]

    def x(text):
        xs = [w["x0"] for w in near if w["text"] == text]
        if len(xs) != 1:
            raise ExtractionError(f"header word {text!r} not found exactly once (found {len(xs)})")
        return xs[0]

    body_top = max(w["top"] for w in words if top - 2 <= w["top"] <= top + 16) + 4
    # Use and manager columns are centred under their headers; the manager text starts left of its own
    # header ('ENTE GESTORE'), so the boundary is taken just right of the end of 'UTILIZZAZIONE'.
    use_end = next(w["x1"] for w in near if w["text"] == "UTILIZZAZIONE")
    return x("CORSO") - 4, x("TOTALE") - 12, x("UTILIZZAZIONE") - 22, use_end + 12, body_top


def _split_name_river(words):
    """Diga name and corso d'acqua sit in adjacent columns; split at the first wide gap."""
    words = [w for w in words if not re.fullmatch(r"\d{1,2}", w["text"])]   # row index column (newer files)
    for k in range(len(words), 0, -1):                      # longest prefix that is a known reservoir name
        if norm(" ".join(w["text"] for w in words[:k])) in ALIAS:
            return (" ".join(w["text"] for w in words[:k]), " ".join(w["text"] for w in words[k:]))
    cut = next((i for i in range(1, len(words)) if words[i]["x0"] - words[i - 1]["x1"] > 7), len(words))
    return (" ".join(w["text"] for w in words[:cut]), " ".join(w["text"] for w in words[cut:]))


def extract(path):
    """Return (readings, reservoirs, totals, as_of_iso) for one monthly table."""
    _, alias = load_reservoirs()
    with pdfplumber.open(path) as pdf:
        page = pdf.pages[0]
        text = page.extract_text()
        words = page.extract_words()
    m = re.search(r"AL 1° (\w+) (\d{4})", text)
    if not m or m.group(1).lower() not in MONTHS:
        raise ExtractionError("cannot read the as-of month from the title")
    month_name, year = m.group(1).lower(), int(m.group(2))
    month = MONTHS[month_name]
    as_of = f"{year:04d}-{month:02d}-01"
    prev_month = f"{year - (month == 1):04d}-{(month - 2) % 12 + 1:02d}"
    prev_year = f"{year - 1:04d}-{month:02d}"

    x_river, x_numbers, x_use, x_manager, body_top = _header(words)

    nums = [w for w in words if w["top"] > body_top and x_numbers <= w["x0"] < x_use
            and DECIMAL.match(w["text"])]
    tops = sorted({round(w["top"]) for w in nums})
    # merge tops that belong to one text line (rows are ~11 pt apart, words of a line within 3 pt)
    lines = []
    for t in tops:
        if lines and t - lines[-1][-1] <= 3:
            lines[-1].append(t)
        else:
            lines.append([t])
    # A name wrapped over two text lines leaves an orphan line without numbers; give it to the nearest row.
    ranges = [(g[0] - 3, g[-1] + 3) for g in lines]
    orphans = {i: [] for i in range(len(lines))}
    for w in words:
        if w["top"] > body_top and w["x0"] < x_numbers and not any(a <= w["top"] <= b for a, b in ranges) \
                and not MARKER.match(w["text"]):
            near = min(range(len(ranges)), key=lambda i: abs(w["top"] - sum(ranges[i]) / 2))
            if abs(w["top"] - sum(ranges[near]) / 2) <= 14:
                orphans[near].append(w)
    readings, reservoirs, seen = [], [], set()
    for n_line, group in enumerate(lines):
        lo, hi = group[0] - 3, group[-1] + 3
        row = sorted((w for w in words if lo <= w["top"] <= hi), key=lambda w: w["x0"])
        # name words in reading order: orphan line above, the row's own line, orphan line below
        band = lambda w: -1 if w["top"] < lo else (1 if w["top"] > hi else 0)
        name_words = sorted(orphans[n_line] + [w for w in row if w["x0"] < x_numbers],
                            key=lambda w: (band(w), w["x0"]))
        values = [w["text"] for w in row if x_numbers <= w["x0"] < x_use and DECIMAL.match(w["text"])]
        if len(values) != 5:
            continue                      # the TOTALI row has 4 numbers in these columns and is handled below
        join = lambda a, b: " ".join(w["text"] for w in row if a <= w["x0"] < b and not MARKER.match(w["text"]))
        printed, river = _split_name_river([w for w in name_words if not MARKER.match(w["text"])])
        use = join(x_use, x_manager)
        manager = join(x_manager, 10_000)
        rid = reservoir_id(printed, alias)
        if rid in seen:
            raise ExtractionError(f"duplicate reservoir {rid}")
        seen.add(rid)
        cap, cur, prev, _gap, last = (parse_mmc(n) for n in values)
        reservoirs.append({"id": rid, "printed_name": printed, "river": river, "capacity_m3": cap,
                           "use_label": use, "manager": manager})
        for col, when, precision, value in (
            (f"volume {month_name} {year}", as_of, "day", cur),
            (f"volume mese precedente ({prev_month})", prev_month, "month", prev),
            (f"volume stesso mese anno precedente ({prev_year})", prev_year, "month", last),
        ):
            readings.append({"reservoir_id": rid, "as_of_date": when, "date_precision": precision,
                             "stored_m3": value, "usable_m3": None, "source_page": 1,
                             "source_column": col, "notes": f"{printed} (riga {len(reservoirs)} del prospetto)"})

    t = re.search(r"TOTALI\s+([\d,.]+)\s+([\d,.]+)\s+(-?[\d,.]+)\s+([\d,.]+)", text)
    totals = None
    if t:
        totals = {"current_m3": parse_mmc(t.group(1)), "previous_month_m3": parse_mmc(t.group(2)),
                  "last_year_m3": parse_mmc(t.group(4))}
    return readings, reservoirs, totals, as_of
