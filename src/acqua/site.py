"""Static site generator.  Usage:  python -m acqua.site [--db data/acqua.sqlite] [--out site]

Pages: home, /comune/<slug>/, /invaso/<slug>/, /consorzio/<id>/, /fonti-e-metodo/.
All text is Italian. Every figure is rendered through the `fig`/`src` macros in templates/macros.html,
which always print the date of the source data and a link to the source document.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import sitedata
from .sitedata import it_date
from .util import ROOT

TEMPLATES = ROOT / "templates"
RELATIONS = {
    "fabbisogno_piano": "Nel piano 2026 il consorzio ha comunicato fabbisogni d'acqua da questo invaso",
    "destinatario_provvedimento": "Il consorzio è destinatario del provvedimento di pianificazione di questo invaso",
    "richiesta_volume": "Il consorzio ha richiesto volumi da questo invaso (tabella 2 del provvedimento)",
    "gestore_invaso": "Il consorzio gestisce l'invaso (prospetto dei volumi)",
}
USES = {"irriguo": "Irriguo", "potabile": "Potabile", "industriale": "Industriale"}
GROUP_MEMBERS = {"Cimia-Disueri": ["cimia", "disueri"], "San Giovanni-Furore": ["san-giovanni", "furore"]}
NA = "Dato non disponibile"


def vol(m3):
    """Cubic metres -> readable Italian text. Millions with two decimals, smaller values in m³."""
    if m3 is None:
        return NA
    if m3 >= 1_000_000:
        return f"{m3 / 1_000_000:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " milioni di m³"
    return f"{m3:,}".replace(",", ".") + " m³"


def pct(part, whole):
    return None if not whole or part is None else part / whole * 100


def fmt_pct(x, digits=0):
    return NA if x is None else f"{x:.{digits}f}".replace(".", ",") + "%"


def signed_pct(x):
    return NA if x is None else ("+" if x > 0 else "−" if x < 0 else "") + f"{abs(x):.0f}".replace(".", ",") + "%"


def src_url(doc, page=None):
    return doc["url"] + (f"#page={page}" if page else "")


def src_label(doc):
    if doc["protocol"]:
        return f"{doc['title'].split(' - ')[-1]} (prot. {doc['protocol']}, {it_date(doc['doc_date'])})"
    return f"Prospetto volumi invasati al {it_date(doc['doc_date'])}"


def chart(series, capacity):
    """Inline SVG line chart of stored volume per monthly table; returns markup (no JS)."""
    pts = [(p["as_of_date"], p["stored_m3"]) for p in series if p["stored_m3"] is not None]
    if len(pts) < 2:
        return ""
    w, h, left, bottom, top = 640, 220, 44, 24, 10
    ymax = max(capacity or 0, max(v for _, v in pts)) / 1e6
    ymax = max(1, ymax)
    n = len(pts)
    x = lambda i: left + (w - left - 8) * i / (n - 1)
    y = lambda v: top + (h - top - bottom) * (1 - v / 1e6 / ymax)
    path = " ".join(("M" if i == 0 else "L") + f"{x(i):.1f},{y(v):.1f}" for i, (_, v) in enumerate(pts))
    grid = ""
    step = 10 if ymax > 60 else 5 if ymax > 25 else 2 if ymax > 8 else 1
    g = 0
    while g <= ymax:
        grid += (f'<line class="grid" x1="{left}" x2="{w - 8}" y1="{y(g * 1e6):.1f}" y2="{y(g * 1e6):.1f}"/>'
                 f'<text class="ax" x="{left - 6}" y="{y(g * 1e6) + 4:.1f}" text-anchor="end">{g}</text>')
        g += step
    ticks = ""
    for i, (d, _) in enumerate(pts):
        if d[5:7] == "01":
            ticks += (f'<line class="grid" x1="{x(i):.1f}" x2="{x(i):.1f}" y1="{top}" y2="{h - bottom}"/>'
                      f'<text class="ax" x="{x(i):.1f}" y="{h - 6}" text-anchor="middle">{d[:4]}</text>')
    cap = ""
    if capacity:
        cap = f'<line class="cap" x1="{left}" x2="{w - 8}" y1="{y(capacity):.1f}" y2="{y(capacity):.1f}"/>'
    last = f'<circle class="dot" cx="{x(n - 1):.1f}" cy="{y(pts[-1][1]):.1f}" r="4"/>'
    desc = (f"Volume invasato in milioni di metri cubi, da {it_date(pts[0][0])} a {it_date(pts[-1][0])}. "
            f"L'ultimo valore è {vol(pts[-1][1])}.")
    return (f'<svg viewBox="0 0 {w} {h}" role="img" aria-labelledby="ct cd" class="chart">'
            f'<title id="ct">Volume nel tempo</title><desc id="cd">{desc}</desc>'
            f'{grid}{ticks}{cap}<path class="line" d="{path}"/>{last}</svg>')


SOURCE_URLS = {
    "N.194_14.05.2026.pdf": ("https://www2.regione.sicilia.it/deliberegiunta/file/giunta/allegati/N.194_14.05.2026.pdf",
                             "14 maggio 2026", "dallo statuto allegato alla delibera di Giunta del"),
    "RELAZIONE_PROGR_TRIENNALE_2025-2027_SCHEMA_SCHEDE.pdf": (
        "https://bonifica3ag.com/images/upload/segreteria/PROGR._TRIENN._OO.PP/2025-2027/"
        "RELAZIONE_PROGR._TRIENNALE_2025-2027_-_SCHEMA_-SCHEDE.pdf", "2025–2027",
        "dalla relazione del programma triennale"),
}


def mapping_source(m):
    """Public URL, date text and lead-in label for a comune_consortium row (source files are local paths)."""
    name = m["source_file"].replace("\\", "/").split("/")[-1]
    for suffix, (url, date_text, label) in SOURCE_URLS.items():
        if name.endswith(suffix):
            return {"url": f"{url}#page={m['source_page']}", "date_text": date_text, "label": label}
    raise KeyError(f"no public URL known for mapping source {name}")


def build(db, out):
    d = sitedata.load(db)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for child in out.iterdir():          # empty the folder, not the folder itself (a server may be using it)
        shutil.rmtree(child) if child.is_dir() else child.unlink()
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]),
                      trim_blocks=True, lstrip_blocks=True)
    env.filters.update(vol=vol, it_date=it_date, pct=fmt_pct, spct=signed_pct)
    env.globals.update(src_url=src_url, src_label=src_label, NA=NA, USES=USES)

    for c in d["consortia"].values():
        doc = d["docs"].get((c["contact_source_file"] or "").replace("\\", "/").split("/")[-1])
        c["contact_doc"], c["contact_date"] = doc, (doc["doc_date"] if doc else None)
        if c["contact"] and not doc:
            c["contact"] = None            # never show an address without a linkable source
    for cm in d["comuni"]:
        for m in cm["consortia"]:
            m.update(mapping_source(m))
    docs_by_key = d["docs"]
    reservoirs = sorted(d["reservoirs"].values(), key=lambda r: r["name"])
    latest = d["latest"]
    consortia, comuni = d["consortia"], d["comuni"]

    def write(path, template, **ctx):
        target = out / path / "index.html" if path else out / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(env.get_template(template).render(
            built_on=d["built_on"], latest=latest, **ctx), encoding="utf-8")

    # ---- derived tables ------------------------------------------------------------------
    for r in reservoirs:
        r["pct_full"] = pct(r["now"]["stored_m3"], r["capacity_m3"]) if r["now"] else None
        r["over_capacity"] = bool(r["now"] and r["capacity_m3"] and r["now"]["stored_m3"] > r["capacity_m3"])
        r["change_year"] = (pct(r["now"]["stored_m3"] - r["last_year"]["stored_m3"], r["last_year"]["stored_m3"])
                            if r["now"] and r["last_year"] and r["last_year"]["stored_m3"] else None)
    total_now = sum(r["now"]["stored_m3"] for r in reservoirs if r["now"])
    total_ly = sum(r["last_year"]["stored_m3"] for r in reservoirs if r["last_year"])
    summary = {"now": total_now, "last_year": total_ly, "change": pct(total_now - total_ly, total_ly),
               "n": len([r for r in reservoirs if r["now"]]),
               "last_year_label": it_date(next(r["last_year"]["as_of_date"] for r in reservoirs if r["last_year"]))}

    links_by_res, links_by_cons = {}, {}
    for l in d["reservoir_consortium"]:
        links_by_res.setdefault(l["reservoir_id"], []).append(l)
        links_by_cons.setdefault(l["consortium_id"], []).append(l)

    plans_by_res = {}
    for p in d["plans"]:
        members = GROUP_MEMBERS.get(p["group_label"], [p["reservoir_id"]]) if p["group_label"] else [p["reservoir_id"]]
        for rid in members:
            plans_by_res.setdefault(rid, []).append(p)

    def usable_for(rid, plan):
        u = d["usable"].get((rid, plan["source_file"]))
        return u

    notes_by_res = {}
    for f in d["flags"]:
        if f["reservoir_id"] and f["code"] in ("usable_gt_stored", "stale_reading"):
            notes_by_res.setdefault(f["reservoir_id"], []).append(f)

    comuni_by_cons = {}
    for c in comuni:
        for m in c["consortia"]:
            comuni_by_cons.setdefault(m["consortium_id"], []).append((c, m))

    # ---- pages ---------------------------------------------------------------------------
    index = [[c["name"], c["province"], f"/comune/{c['slug']}/"] for c in comuni]
    provinces = {}
    for c in comuni:
        provinces.setdefault(c["province"], []).append(c)
    write("", "index.html", reservoirs=reservoirs, summary=summary, comuni_index=json.dumps(index, ensure_ascii=False),
          provinces=dict(sorted(provinces.items())), consortia=consortia, title="Acqua ai Campi",
          description="Quanta acqua c'è negli invasi della Sicilia e quanta ne è prevista per l'irrigazione. Cerca il tuo comune.")

    for r in reservoirs:
        rid = r["id"]
        links = links_by_res.get(rid, [])
        direct = [l for l in links if consortia[l["consortium_id"]]["parent_id"]]
        comuni_served = sorted({c["name"]: (c, m) for l in direct
                                for c, m in comuni_by_cons.get(l["consortium_id"], [])}.values(), key=lambda t: t[0]["name"])
        plan_rows, shown_usable = [], set()
        for p in sorted(plans_by_res.get(rid, []), key=lambda p: (p["use"] != "irriguo", p["as_of_date"])):
            u = usable_for(rid, p)
            if u and p["source_file"] in shown_usable:
                u = None                          # show the usable volume once per document
            shown_usable.add(p["source_file"])
            plan_rows.append({**p, "usable": u, "group": p["group_label"],
                              "group_members": [d["reservoirs"][m]["name"] for m in GROUP_MEMBERS.get(p["group_label"], [])]})
        write(f"invaso/{r['slug']}", "invaso.html", r=r, docs_by_key=docs_by_key, links=links, relations=RELATIONS, consortia=consortia,
              comuni_served=comuni_served, plans=plan_rows, notes=notes_by_res.get(rid, []),
              chart=chart(r["series"], r["capacity_m3"]), title=f"Invaso {r['name']}",
              description=f"Volume dell'invaso {r['name']}, piano di irrigazione 2026 e consorzi collegati.")

    for cid, c in consortia.items():
        direct = links_by_cons.get(cid, [])
        parent = consortia.get(c["parent_id"]) if c["parent_id"] else None
        regional = links_by_cons.get(parent["id"], []) if parent else []
        children = [x for x in consortia.values() if x["parent_id"] == cid]
        write(f"consorzio/{c['id']}", "consorzio.html", c=c, parent=parent, children=children,
              direct=direct, regional=regional, reservoirs=d["reservoirs"], relations=RELATIONS,
              comuni_list=sorted(comuni_by_cons.get(cid, []), key=lambda t: t[0]["name"]),
              docs=d["docs"], title=c["name"], description=f"{c['name']}: invasi collegati, comuni e contatti.")

    for cm in comuni:
        cons = []
        for m in cm["consortia"]:
            c = consortia[m["consortium_id"]]
            parent = consortia.get(c["parent_id"]) if c["parent_id"] else None
            direct = links_by_cons.get(c["id"], [])
            regional = [l for l in links_by_cons.get(parent["id"], []) if l["reservoir_id"] not in
                        {x["reservoir_id"] for x in direct}] if parent else []
            res = {}
            for l in direct:
                res.setdefault(l["reservoir_id"], []).append(l)
            cons.append({"c": c, "parent": parent, "m": m, "direct": [d["reservoirs"][k] for k in res],
                         "regional_n": len({l["reservoir_id"] for l in regional})})
        plans = {r["id"]: [p for p in plans_by_res.get(r["id"], []) if p["use"] == "irriguo"] for k in cons for r in k["direct"]}
        write(f"comune/{cm['slug']}", "comune.html", cm=cm, cons=cons, plans=plans,
              title=f"Acqua per l'irrigazione a {cm['name']}",
              description=f"Consorzio, invasi e piano di irrigazione 2026 per il comune di {cm['name']} ({cm['province']}).")

    fonti_docs = sorted((x for x in d["docs"].values() if x["protocol"]), key=lambda x: x["doc_date"])
    monthly = sorted((x for x in d["docs"].values() if not x["protocol"]), key=lambda x: x["doc_date"])
    flags = [f for f in d["flags"] if f["code"] not in ("revised_value", "row_count")]
    n_revised = sum(1 for f in d["flags"] if f["code"] == "revised_value")
    n_short = sum(1 for f in d["flags"] if f["code"] == "row_count")
    write("fonti-e-metodo", "fonti.html", plan_docs=fonti_docs, monthly=monthly, flags=flags, n_revised=n_revised,
          n_short=n_short, reservoirs=d["reservoirs"], title="Fonti e metodo",
          description="Da dove vengono i dati, come sono stati estratti, limiti noti e date di aggiornamento.")
    write("404", "notfound.html", title="Pagina non trovata", description="")
    (out / "404.html").write_text((out / "404" / "index.html").read_text(encoding="utf-8"), encoding="utf-8")
    shutil.rmtree(out / "404")
    (out / "robots.txt").write_text("User-agent: *\nAllow: /\n", encoding="utf-8")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "data" / "acqua.sqlite"))
    ap.add_argument("--out", default=str(ROOT / "site"))
    a = ap.parse_args(argv)
    out = build(a.db, a.out)
    print(f"site written to {out} ({sum(1 for _ in out.rglob('*.html'))} pages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
