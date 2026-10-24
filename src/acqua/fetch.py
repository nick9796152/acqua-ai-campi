"""Download the monthly 'Prospetto volumi invasati' tables listed on the Authority's year pages.

Usage:  python -m acqua.fetch [--from-year 2024] [--to-year 2026] [--dry-run]

Files go to data/raw/regione-sicilia-volumi/{YYYY-MM-DD}_{filename} (download date prefix).
A file whose SHA-256 matches one we already hold (in any raw folder) is not stored again.
"""
import argparse
import hashlib
import json
import re
import sys
import urllib.request
from datetime import date
from html import unescape
from pathlib import Path
from urllib.parse import urljoin

from .util import ROOT

SITE = "https://www.regione.sicilia.it"
INDEX = (SITE + "/istituzioni/regione/strutture-regionali/presidenza-regione/"
         "autorita-bacino-distretto-idrografico-sicilia/siti-tematici/risorse-idriche/"
         "volumi-invasati-nelle-dighe-della-sicilia")
OUT = ROOT / "data" / "raw" / "regione-sicilia-volumi"
MANIFEST = OUT / "manifest.json"   # {relative file path: {month, url, sha256, first_seen}}
USER_AGENT = "acqua-ai-campi/0.1 (public water data transparency project)"

ANCHOR = re.compile(r'<a[^>]+href="([^"]+\.pdf)"[^>]*>(.*?)</a>', re.S | re.I)
TABLE_TITLE = re.compile(r"^prospetto volumi invas(?:i|ati)(?: nelle dighe)? (\w+) (\d{4})", re.I)
MONTHS = {"gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6, "luglio": 7,
          "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def year_pages():
    """{year: url} from the index page's 'Anno YYYY' links."""
    html = get(INDEX).decode("utf-8", "replace")
    pages = {}
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(?:\s|<[^>]+>)*Anno\s+(\d{4})\b', html, re.I | re.S):
        pages[int(m.group(2))] = urljoin(SITE, unescape(m.group(1)))
    return pages


def table_links(page_url):
    """[(YYYY-MM, absolute url)] for table PDFs on a year page (graphs are skipped)."""
    html = get(page_url).decode("utf-8", "replace")
    found = {}
    for m in ANCHOR.finditer(html):
        text = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", m.group(2)))).strip()
        t = TABLE_TITLE.search(text)           # "Prospetto volumi invasi <Mese> <Anno>"
        if t and t.group(1).lower() in MONTHS:
            found[f"{t.group(2)}-{MONTHS[t.group(1).lower()]:02d}"] = urljoin(SITE, unescape(m.group(1)))
    return sorted(found.items())


def load_manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}


def held_hashes():
    return {hashlib.sha256(p.read_bytes()).hexdigest(): p
            for p in (ROOT / "data" / "raw").rglob("*.pdf")}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-year", type=int, default=2024)
    ap.add_argument("--to-year", type=int, default=date.today().year)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    pages = year_pages()
    if not pages:
        print("no year pages found on the index page", file=sys.stderr)
        return 1
    held = held_hashes()
    manifest = load_manifest()
    today = date.today().isoformat()
    new = 0
    for year in range(args.from_year, args.to_year + 1):
        if year not in pages:
            print(f"{year}: no page listed on the index", file=sys.stderr)
            continue
        links = table_links(pages[year])
        print(f"{year}: {len(links)} monthly tables on {pages[year]}")
        for month, url in links:
            if args.dry_run:
                print("  ", month, url)
                continue
            data = get(url)
            digest = hashlib.sha256(data).hexdigest()
            if not data.startswith(b"%PDF"):
                print(f"  {month}: not a PDF, skipped ({url})", file=sys.stderr)
                continue
            if digest in held:
                dest = held[digest]
                print(f"  {month}: unchanged (already have {dest.name})")
            else:
                OUT.mkdir(parents=True, exist_ok=True)
                dest = OUT / f"{today}_{Path(url).name}"
                dest.write_bytes(data)
                held[digest] = dest
                new += 1
                print(f"  {month}: saved {dest.name}")
            rel = str(dest.relative_to(ROOT)).replace("\\", "/")
            manifest.setdefault(rel, {"month": month, "url": url, "sha256": digest, "first_seen": today})
    if not args.dry_run:
        OUT.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")
    print(f"{new} new file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
