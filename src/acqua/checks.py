"""Gate checks used by the daily GitHub workflow.

  python -m acqua.checks site [--dir site] [--min-pages 400]
      Exit 1 (so nothing gets published) if the freshly built site looks broken.
  python -m acqua.checks fresh [--max-days 45]
      Exit 1 if the newest monthly reservoir table is older than max-days; the workflow then
      emails a warning, while the site stays up with its old data and dates.
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

from .util import ROOT


def site_problems(out, min_pages=400, base=""):
    out = Path(out)
    base = "/" + base.strip("/") if base.strip("/") else ""
    problems = []
    pages = sum(1 for _ in out.rglob("*.html"))
    if pages < min_pages:
        problems.append(f"only {pages} pages were built (expected at least {min_pages})")
    home = out / "index.html"
    if not home.exists() or "m³" not in home.read_text(encoding="utf-8"):
        problems.append("home page is missing or shows no volume")
    for need in ("fonti-e-metodo/index.html", "404.html"):
        if not (out / need).exists():
            problems.append(f"{need} is missing")
    # every internal link must point to a file that exists
    broken = set()
    for page in out.rglob("*.html"):
        for href in re.findall(r'href="(/[^"#?]*)', page.read_text(encoding="utf-8")):
            if base and not href.startswith(base + "/"):
                broken.add(href)
                continue
            rel = href[len(base):].lstrip("/")
            target = out / rel / "index.html" if (rel == "" or rel.endswith("/")) else out / rel
            if not target.exists():
                broken.add(href)
    if broken:
        problems.append(f"{len(broken)} internal links point nowhere, for example {sorted(broken)[:3]}")
    return problems


def latest_table_date(manifest=None):
    """Newest monthly table we hold, as YYYY-MM-01, read from the fetch manifest (no database needed)."""
    manifest = Path(manifest or ROOT / "data" / "raw" / "regione-sicilia-volumi" / "manifest.json")
    months = [v["month"] for v in json.loads(manifest.read_text(encoding="utf-8")).values()]
    return max(months) + "-01"


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("site")
    s.add_argument("--dir", default=str(ROOT / "site"))
    s.add_argument("--min-pages", type=int, default=400)
    s.add_argument("--base", default="", help="path prefix the site was built with")
    f = sub.add_parser("fresh")
    f.add_argument("--max-days", type=int, default=45)
    a = ap.parse_args(argv)
    if a.cmd == "site":
        problems = site_problems(a.dir, a.min_pages, a.base)
        for p in problems:
            print("SITE CHECK FAILED:", p)
        print("site check ok" if not problems else "")
        return 1 if problems else 0
    latest = latest_table_date()
    age = (date.today() - date.fromisoformat(latest)).days
    if age > a.max_days:
        print(f"WARNING: the newest reservoir table is from {latest} ({age} days old). "
              "The Authority may have stopped publishing, or its page changed.")
        return 1
    print(f"newest reservoir table: {latest} ({age} days old), fine")
    return 0


if __name__ == "__main__":
    sys.exit(main())
