import csv
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "regione-sicilia"
REFERENCE = ROOT / "data" / "reference"

NUM = re.compile(r"-?\d{1,3}(?:\.\d{3})+(?![\d,])|-?\d+(?:,\d+)?")
DATE = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")


class ExtractionError(Exception):
    pass


def parse_mc(tok):
    """'20.572.303' -> 20572303 (cubic metres, dot as thousands separator)."""
    if not re.fullmatch(r"\d{1,3}(?:\.\d{3})*", tok):
        raise ExtractionError(f"not an mc number: {tok!r}")
    return int(tok.replace(".", ""))


def parse_mmc(tok):
    """'98,83' -> 98830000 (millions of cubic metres, decimal comma; a few 2023 files use a dot)."""
    if not re.fullmatch(r"-?\d+(?:,\d+|\.\d{1,2})?", tok):
        raise ExtractionError(f"not an Mmc number: {tok!r}")
    return int((Decimal(tok.replace(",", ".")) * 1_000_000).to_integral_value())


def parse_date(text):
    m = DATE.search(text)
    if not m:
        raise ExtractionError(f"no date in {text!r}")
    d, mo, y = map(int, m.groups())
    return date(y, mo, d).isoformat()


def numbers(line):
    """Numeric tokens of a line, dates removed first."""
    return NUM.findall(DATE.sub(" ", line))


def load_reservoirs():
    with open(REFERENCE / "reservoirs.csv", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    alias = {}
    for r in rows:
        for name in [r["name"], *r["printed_names"].split(";")]:
            alias[norm(name)] = r["id"]
    return rows, alias


def norm(name):
    return re.sub(r"\s+", " ", name.strip().casefold())


def reservoir_id(printed, alias):
    try:
        return alias[norm(printed)]
    except KeyError:
        raise ExtractionError(f"reservoir name not in canonical list: {printed!r}") from None
