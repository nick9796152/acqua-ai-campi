"""M4: static site. Builds into a temp folder and audits the generated HTML.

Acceptance rules from BRIEF.md section 6 that can be checked without a browser:
- every number (volume in m³) sits in a figure or data row that carries a date and a link to a source;
- the key information is in the HTML itself (no JS needed);
- Italian, mobile viewport, no external requests, small pages.
"""
import re
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from acqua import site
from acqua.util import ROOT

DB = ROOT / "data" / "acqua.sqlite"
TMP = tempfile.TemporaryDirectory()
OUT = Path(TMP.name)
site.build(str(DB), OUT)
PAGES = {str(p.relative_to(OUT)).replace("\\", "/"): p.read_text(encoding="utf-8") for p in OUT.rglob("*.html")}
VOLUME = re.compile(r"\d[\d.,]*\s*(?:milioni di )?m³")
DATE_WORD = re.compile(r"(aggiornato al|dati al|nel prospetto del|dal documento del|dalla|dallo|indirizzo da)")


class Audit(HTMLParser):
    """Collects volume text nodes that are not inside a .fig / .datarow element, and counts links."""

    def __init__(self):
        super().__init__()
        self.stack, self.bad, self.scripts_src, self.stylesheets, self.ext_img = [], [], 0, 0, 0
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "link", "img") and (a.get("src") or a.get("href", "").startswith("http")) \
                and not (tag == "link" and a.get("rel") == "icon"):
            if tag == "script" and a.get("src"):
                self.scripts_src += 1
            if tag == "link" and a.get("rel") == "stylesheet":
                self.stylesheets += 1
            if tag == "img":
                self.ext_img += 1
        if tag not in ("br", "meta", "link", "img", "input", "path", "line", "circle"):
            self.stack.append((tag, a.get("class", "")))
        if tag in ("svg", "script", "style", "title"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("svg", "script", "style", "title"):
            self.skip -= 1
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self.skip > 0 or not VOLUME.search(data):
            return
        if not any(re.search(r"\b(fig|datarow)\b", c) for _, c in self.stack):
            self.bad.append(data.strip()[:80])


def audit(html):
    p = Audit()
    p.feed(html)
    return p


class Structure(unittest.TestCase):
    def test_page_counts(self):
        self.assertEqual(sum(k.startswith("comune/") for k in PAGES), 391)
        self.assertEqual(sum(k.startswith("invaso/") for k in PAGES), 30)
        self.assertEqual(sum(k.startswith("consorzio/") for k in PAGES), 12)
        for k in ("index.html", "fonti-e-metodo/index.html", "404.html"):
            self.assertIn(k, PAGES)

    def test_italian_mobile_and_self_contained(self):
        for name, html in PAGES.items():
            self.assertIn('<html lang="it">', html, name)
            self.assertIn('name="viewport"', html, name)
            self.assertIn("<title>", html, name)
            a = audit(html)
            self.assertEqual((a.scripts_src, a.stylesheets, a.ext_img), (0, 0, 0), name)

    def test_pages_are_light(self):
        for name, html in PAGES.items():
            self.assertLess(len(html.encode()), 90_000, name)
        self.assertLess(len(PAGES["comune/ribera/index.html"].encode()), 20_000)


class Sources(unittest.TestCase):
    def test_every_volume_has_a_date_and_a_source_link(self):
        for name, html in PAGES.items():
            self.assertEqual(audit(html).bad, [], name)

    def test_figures_and_data_rows_have_date_and_link(self):
        class Rows(HTMLParser):
            def __init__(self):
                super().__init__()
                self.depth, self.cur, self.items = 0, None, []

            def handle_starttag(self, tag, attrs):
                cls = dict(attrs).get("class", "")
                if self.cur is None and re.search(r"\b(fig|datarow)\b", cls):
                    self.cur, self.depth, self.text, self.links = tag, 1, "", []
                elif self.cur is not None:
                    self.depth += tag == self.cur
                    if tag == "a":
                        self.links.append(dict(attrs).get("href", ""))

            def handle_endtag(self, tag):
                if self.cur is not None and tag == self.cur:
                    self.depth -= 1
                    if self.depth == 0:
                        self.items.append((self.text, self.links))
                        self.cur = None

            def handle_data(self, data):
                if self.cur is not None:
                    self.text += data

        total = 0
        for name, html in PAGES.items():
            r = Rows()
            r.feed(html)
            for text, links in r.items:
                if not re.search(r"\d", text):
                    continue                              # a row that only says 'Dato non disponibile'
                total += 1
                self.assertTrue(any(l.startswith("http") for l in links), (name, text[:60]))
                self.assertTrue(DATE_WORD.search(text) or re.search(r"\b20\d\d\b", text), (name, text[:60]))
        self.assertGreater(total, 1000)

    def test_missing_data_says_so_in_italian(self):
        unmapped = PAGES["comune/palermo/index.html"]
        self.assertIn("Per questo comune non abbiamo ancora il consorzio", unmapped)
        self.assertIn("Dato non disponibile", unmapped)
        self.assertIn("Dato non disponibile", PAGES["comune/ribera/index.html"])   # season start and bookings

    def test_no_invented_season_dates(self):
        for name, html in PAGES.items():
            if name.startswith("comune/") and "consorzio-di-bonifica" in html.lower():
                self.assertRegex(html, r"Apertura della stagione irrigua:</strong> <span class=\"na\">Dato non disponibile")


class OverCapacity(unittest.TestCase):
    def test_value_above_capacity_is_shown_and_flagged(self):
        import shutil
        import sqlite3
        from contextlib import closing
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "x.sqlite"
            shutil.copy(DB, db)
            with closing(sqlite3.connect(db)) as con:
                con.execute("UPDATE reservoir_readings SET stored_m3 = 21000000 WHERE reservoir_id='santa-rosalia' "
                            "AND as_of_date='2026-10-01' AND date_precision='day'")
                con.commit()
            out = Path(tmp) / "site"
            site.build(str(db), out)
            page = (out / "invaso" / "santa-rosalia" / "index.html").read_text(encoding="utf-8")
            home = (out / "index.html").read_text(encoding="utf-8")
        self.assertIn("più alto", page)
        self.assertIn("21,00 milioni di m³", page)
        self.assertIn("supera la capacità indicata", home)
        self.assertEqual(audit(page).bad, [])


class KeyInformationWithoutJs(unittest.TestCase):
    def test_home(self):
        h = PAGES["index.html"]
        self.assertIn("409,69 milioni di m³", h)          # island total at 1 October 2026
        self.assertIn("/invaso/lentini/", h)
        self.assertIn("/comune/ribera/", h)               # full comune list is plain HTML
        self.assertEqual(h.count("<script"), 2)           # JSON index + the tiny search script only

    def test_ribera_page_matches_the_database_values(self):
        h = PAGES["comune/ribera/index.html"]
        for expected in ("Consorzio di Bonifica 3 Agrigento", "Invaso Castello", "10,50 milioni di m³",
                         "11,00 milioni di m³", "agrigento@pec.consorzibonificasicilia.it", "1 ottobre 2026"):
            self.assertIn(expected, h)

    def test_catania_comune_shows_hectares_and_pozzillo(self):
        h = PAGES["comune/catania/index.html"]
        self.assertIn("10378 ettari", h)
        self.assertIn("Invaso Pozzillo", h)
        self.assertIn("47,14 milioni di m³", h)           # planned 2026, Prot. 10706

    def test_reservoir_pages(self):
        r = PAGES["invaso/rosamarina/index.html"]
        self.assertIn("Anomalia nel documento originale", r)
        self.assertNotIn("14,01 milioni di m³ aggiornato al 20 aprile 2026 · fonte</small></span></td></tr>\n<tr class=\"datarow\"><th scope=\"row\" style=\"font-weight:400\">Richiesto", "")
        self.assertNotIn("più alto", PAGES["invaso/santa-rosalia/index.html"])   # 17,91 of 20,00 in October 2026
        self.assertIn("<svg", PAGES["invaso/lentini/index.html"])
        self.assertIn("Dato non disponibile", PAGES["invaso/lentini/index.html"])   # no comune list for CB links

    def test_fonti_lists_sources_and_gaps(self):
        f = PAGES["fonti-e-metodo/index.html"]
        for expected in ("prot. 10116", "prot. 21823", "58 prospetti", "Che cosa non c'è ancora", "Anomalie"):
            self.assertIn(expected, f)


if __name__ == "__main__":
    unittest.main()
