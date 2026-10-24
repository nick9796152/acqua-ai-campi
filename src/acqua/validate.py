"""Sanity checks over extracted rows.

'error' blocks publishing. 'warning' records an oddity found in the source itself: the row is
kept as printed and flagged, never silently dropped.
"""
from datetime import date

from .util import load_reservoirs

EXPECTED_VOLUME_ROWS = 30
GROUPS = {"Cimia-Disueri": ["cimia", "disueri"], "San Giovanni-Furore": ["san-giovanni", "furore"]}


def flag(sev, code, msg, file=None, page=None, rid=None):
    return {"severity": sev, "code": code, "message": msg, "source_file": file,
            "source_page": page, "reservoir_id": rid}


def month_continuity(volume_docs):
    """The 'previous month' column of one table should equal the 'current' column of the month before,
    and 'same month last year' should equal the table of twelve months earlier. Differences are
    revisions made by the Authority, recorded as warnings."""
    cur = {}
    for d in volume_docs:
        for r in d["readings"]:
            if r["date_precision"] == "day":
                cur[(r["reservoir_id"], r["as_of_date"][:7])] = (r["stored_m3"], d["key"])
    flags = []
    for d in volume_docs:
        for r in d["readings"]:
            if r["date_precision"] != "month":
                continue
            then = cur.get((r["reservoir_id"], r["as_of_date"]))
            if then and then[0] != r["stored_m3"]:
                flags.append(flag("warning", "revised_value",
                                  f"{r['as_of_date']}: {r['stored_m3']} mc here ({r['source_column']}) vs {then[0]} mc "
                                  f"in {then[1]}", d["key"], r["source_page"], r["reservoir_id"]))
    return flags


def validate(docs, today=None):
    """docs: list of dicts {key, kind, readings, plans, reservoirs, totals}."""
    today = (today or date.today()).isoformat()
    ids = {r["id"] for r in load_reservoirs()[0]}
    flags = []
    volume_docs = sorted((d for d in docs if d["kind"] == "volumes"), key=lambda d: d["doc_date"])
    latest_capacity = {r["id"]: r["capacity_m3"] for r in volume_docs[-1]["reservoirs"]} if volume_docs else {}
    for d in docs:
        if d["kind"] != "volumes":
            continue
        if len(d["reservoirs"]) != EXPECTED_VOLUME_ROWS:   # dams were added to the table over time
            flags.append(flag("warning", "row_count",
                              f"{len(d['reservoirs'])} reservoirs listed, the current table has {EXPECTED_VOLUME_ROWS}; "
                              "the printed totals match the rows listed", d["key"]))
        cur = sum(x["stored_m3"] for x in d["readings"] if x["date_precision"] == "day")
        if d["totals"] is None:
            flags.append(flag("error", "totals_missing", "totals row not found", d["key"]))
        elif abs(cur - d["totals"]["current_m3"]) > 20_000:  # printed total is rounded to 0.01 Mmc
            flags.append(flag("error", "totals_mismatch",
                              f"sum {cur} != printed total {d['totals']['current_m3']}", d["key"]))

    flags += month_continuity(volume_docs)

    for d in docs:
        key = d["key"]
        # a monthly table is checked against its own capacities, planning documents against the latest ones
        capacity = {r["id"]: r["capacity_m3"] for r in d["reservoirs"]} if d["kind"] == "volumes" else latest_capacity
        for r in d["readings"]:
            rid, page = r["reservoir_id"], r["source_page"]
            if rid not in ids:
                flags.append(flag("error", "unknown_reservoir", f"{rid} not in canonical list", key, page, rid))
            for f in ("stored_m3", "usable_m3"):
                if r[f] is not None and r[f] < 0:
                    flags.append(flag("error", "negative_volume", f"{f} = {r[f]}", key, page, rid))
            if r["usable_m3"] is not None and r["stored_m3"] is not None and r["usable_m3"] > r["stored_m3"]:
                flags.append(flag("warning", "usable_gt_stored",
                                  f"Source prints usable {r['usable_m3']} mc above stored {r['stored_m3']} mc",
                                  key, page, rid))
            cap = capacity.get(rid)
            if cap and r["stored_m3"] is not None and r["stored_m3"] > cap:
                flags.append(flag("warning", "stored_gt_capacity",
                                  f"{r['as_of_date']}: stored {r['stored_m3']} mc above capacity {cap} mc "
                                  f"({r['source_column']})", key, page, rid))
            if r["as_of_date"][:10] > today:
                flags.append(flag("error", "future_date", r["as_of_date"], key, page, rid))
            if d["kind"] == "plan" and r["as_of_date"] < "2026-01-01":
                flags.append(flag("warning", "stale_reading",
                                  f"reading dated {r['as_of_date']} used for the 2026 plan", key, page, rid))
        usable = {r["reservoir_id"]: r["usable_m3"] for r in d["readings"] if r["usable_m3"] is not None}
        planned_by = {}
        for p in d["plans"]:
            rid, page = p["reservoir_id"], p["source_page"]
            if rid and rid not in ids:
                flags.append(flag("error", "unknown_reservoir", f"{rid} not in canonical list", key, page, rid))
            for f in ("needs_m3", "planned_m3"):
                if p[f] is not None and p[f] < 0:
                    flags.append(flag("error", "negative_volume", f"{f} = {p[f]}", key, page, rid))
            if p["needs_m3"] is not None and p["planned_m3"] is not None and p["planned_m3"] > p["needs_m3"]:
                flags.append(flag("warning", "planned_gt_needs",
                                  f"{p['use']}: planned {p['planned_m3']} > needs {p['needs_m3']}", key, page, rid))
            if p["planned_m3"]:
                k = p["reservoir_id"] or p["group_label"]
                planned_by[k] = planned_by.get(k, 0) + p["planned_m3"]
        for k, total in planned_by.items():
            members = GROUPS.get(k, [k])
            if all(m in usable for m in members) and total > sum(usable[m] for m in members):
                flags.append(flag("warning", "planned_gt_usable",
                                  f"planned {total} mc above usable {sum(usable[m] for m in members)} mc",
                                  key, None, k))
    return flags
