"""SQLite access layer.

Uses Python's builtin sqlite3. One connection per request (Flask `g`),
row factory set to sqlite3.Row, all writes parameterised.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from flask import current_app, g

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS module_progress (
    module_id      TEXT PRIMARY KEY,
    mastery_score  INTEGER NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'not_started',
    last_accessed  TEXT
);

CREATE TABLE IF NOT EXISTS lesson_progress (
    lesson_id        TEXT PRIMARY KEY,
    module_id        TEXT,
    completed        INTEGER NOT NULL DEFAULT 0,
    assessment_score INTEGER NOT NULL DEFAULT 0,
    attempts         INTEGER NOT NULL DEFAULT 0,
    last_accessed    TEXT
);

CREATE TABLE IF NOT EXISTS attempts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id      TEXT NOT NULL,
    module_id        TEXT,
    context          TEXT,
    submitted_answer TEXT,
    score            INTEGER NOT NULL DEFAULT 0,
    max_score        INTEGER NOT NULL DEFAULT 1,
    feedback         TEXT,
    self_assessed    INTEGER NOT NULL DEFAULT 0,
    timestamp        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attempts_question ON attempts(question_id);

CREATE TABLE IF NOT EXISTS mission_progress (
    mission_id   TEXT PRIMARY KEY,
    status       TEXT NOT NULL DEFAULT 'open',
    score        INTEGER NOT NULL DEFAULT 0,
    attempts     INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS mission_evidence (
    mission_id   TEXT NOT NULL,
    evidence_id  TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    PRIMARY KEY (mission_id, evidence_id)
);

CREATE TABLE IF NOT EXISTS lab_progress (
    lab_id        TEXT PRIMARY KEY,
    module_id     TEXT,
    sim_score     INTEGER NOT NULL DEFAULT 0,
    sim_done      INTEGER NOT NULL DEFAULT 0,
    real_done     INTEGER NOT NULL DEFAULT 0,
    real_notes    TEXT,
    status        TEXT NOT NULL DEFAULT 'not_started',
    updated_at    TEXT
);

CREATE TABLE IF NOT EXISTS simulation_progress (
    simulation_id TEXT PRIMARY KEY,
    completed     INTEGER NOT NULL DEFAULT 0,
    score         INTEGER NOT NULL DEFAULT 0,
    updated_at    TEXT
);

CREATE TABLE IF NOT EXISTS activity (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_type      TEXT NOT NULL,
    activity_reference TEXT NOT NULL,
    xp_earned          INTEGER NOT NULL DEFAULT 0,
    timestamp          TEXT NOT NULL
);
-- XP farming guard: one award per (type, reference).
CREATE UNIQUE INDEX IF NOT EXISTS idx_activity_unique
    ON activity(activity_type, activity_reference);

CREATE TABLE IF NOT EXISTS user_settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS interview_sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    score      INTEGER NOT NULL DEFAULT 0,
    report     TEXT
);

CREATE TABLE IF NOT EXISTS interview_answers (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   INTEGER NOT NULL,
    question_id  TEXT NOT NULL,
    answer       TEXT,
    covered      TEXT,
    score        INTEGER NOT NULL DEFAULT 0,
    timestamp    TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES interview_sessions(id)
);
"""


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        db_path = Path(current_app.config["DATABASE"])
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql: str, params: tuple = (), one: bool = False):
    cur = get_db().execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    if one:
        return rows[0] if rows else None
    return rows


def execute(sql: str, params: tuple = ()):
    db = get_db()
    cur = db.execute(sql, params)
    db.commit()
    last = cur.lastrowid
    cur.close()
    return last


def init_db(app=None) -> None:
    """Create the database schema. Safe to call on every launch."""
    if app is not None:
        with app.app_context():
            db = get_db()
            db.executescript(SCHEMA)
            db.commit()
        return
    db = get_db()
    db.executescript(SCHEMA)
    db.commit()
