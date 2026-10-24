"""SQLite store. Rows are only ever appended; a re-run that disagrees with stored data is an error."""
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS source_documents (
    key TEXT PRIMARY KEY, file TEXT NOT NULL, sha256 TEXT NOT NULL, url TEXT, protocol TEXT,
    doc_date TEXT, title TEXT NOT NULL, ingested_on TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reservoirs (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, river TEXT, capacity_m3 INTEGER, use_label TEXT,
    manager TEXT, capacity_source_file TEXT);
CREATE TABLE IF NOT EXISTS reservoir_readings (
    reservoir_id TEXT NOT NULL REFERENCES reservoirs(id),
    as_of_date TEXT NOT NULL,            -- YYYY-MM-DD, or YYYY-MM when date_precision = 'month'
    date_precision TEXT NOT NULL CHECK (date_precision IN ('day','month')),
    stored_m3 INTEGER, usable_m3 INTEGER,
    source_file TEXT NOT NULL REFERENCES source_documents(key), source_page INTEGER NOT NULL,
    source_column TEXT NOT NULL, notes TEXT,
    PRIMARY KEY (reservoir_id, as_of_date, source_file, source_column));
CREATE TABLE IF NOT EXISTS consortia (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, parent_id TEXT REFERENCES consortia(id), kind TEXT,
    website TEXT, contact TEXT, contact_source_file TEXT, contact_source_page INTEGER, note TEXT);
CREATE TABLE IF NOT EXISTS irrigation_plans (
    id INTEGER PRIMARY KEY,
    reservoir_id TEXT REFERENCES reservoirs(id),   -- NULL when one figure covers a group
    group_label TEXT,
    consortium_id TEXT REFERENCES consortia(id),
    season_year INTEGER NOT NULL, use TEXT NOT NULL CHECK (use IN ('irriguo','potabile','industriale')),
    needs_m3 INTEGER, planned_m3 INTEGER, notes TEXT, as_of_date TEXT NOT NULL,
    source_file TEXT NOT NULL REFERENCES source_documents(key), source_page INTEGER NOT NULL,
    CHECK (reservoir_id IS NOT NULL OR group_label IS NOT NULL),
    UNIQUE (reservoir_id, group_label, season_year, use, as_of_date, source_file));
CREATE TABLE IF NOT EXISTS comuni (
    istat_code TEXT PRIMARY KEY, name TEXT NOT NULL, province TEXT, consortium_ids TEXT);
CREATE TABLE IF NOT EXISTS comune_consortium (
    istat_code TEXT NOT NULL REFERENCES comuni(istat_code), consortium_id TEXT NOT NULL REFERENCES consortia(id),
    area_ha_in_comprensorio INTEGER,   -- part of the comune inside the comprensorio, not the comune's area
    zone TEXT, source_file TEXT NOT NULL, source_page INTEGER NOT NULL, note TEXT,
    PRIMARY KEY (istat_code, consortium_id));
CREATE TABLE IF NOT EXISTS reservoir_consortium (
    reservoir_id TEXT NOT NULL REFERENCES reservoirs(id), consortium_id TEXT NOT NULL REFERENCES consortia(id),
    relation TEXT NOT NULL, source_file TEXT NOT NULL, source_page INTEGER NOT NULL, note TEXT,
    PRIMARY KEY (reservoir_id, consortium_id, relation, source_file));
CREATE TABLE IF NOT EXISTS announcements (
    id INTEGER PRIMARY KEY, consortium_id TEXT REFERENCES consortia(id), date TEXT,
    type TEXT CHECK (type IN ('season_open','booking','fee','other')), summary_it TEXT, url TEXT);
CREATE TABLE IF NOT EXISTS validation_flags (
    id INTEGER PRIMARY KEY, severity TEXT NOT NULL CHECK (severity IN ('warning','error')),
    code TEXT NOT NULL, source_file TEXT, source_page INTEGER, reservoir_id TEXT,
    message TEXT NOT NULL, recorded_on TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS validation_flags_dedupe ON validation_flags
    (code, IFNULL(source_file, ''), IFNULL(source_page, -1), IFNULL(reservoir_id, ''), message);
"""

READING_COLS = ["reservoir_id", "as_of_date", "date_precision", "stored_m3", "usable_m3",
                "source_file", "source_page", "source_column", "notes"]
PLAN_COLS = ["reservoir_id", "group_label", "consortium_id", "season_year", "use", "needs_m3",
             "planned_m3", "notes", "as_of_date", "source_file", "source_page"]


class Conflict(Exception):
    pass


def connect(path):
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA)
    return con


def append(con, table, key_cols, row, cols):
    """Insert unless an identical key exists; raise Conflict if the key exists with other values."""
    row = {c: row.get(c) for c in cols}
    where = " AND ".join(f"{c} IS ?" for c in key_cols)
    old = con.execute(f"SELECT {','.join(cols)} FROM {table} WHERE {where}",
                      [row[c] for c in key_cols]).fetchone()
    if old is None:
        con.execute(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                    [row[c] for c in cols])
    elif tuple(old) != tuple(row[c] for c in cols):
        raise Conflict(f"{table}: stored row differs from newly extracted row for key "
                       f"{[row[c] for c in key_cols]}: {old} vs {tuple(row[c] for c in cols)}")
