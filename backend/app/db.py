import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "cqa.db"


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def create_tables() -> None:
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS conversations (
        id          TEXT PRIMARY KEY,
        group_id    TEXT NOT NULL,
        channel     TEXT NOT NULL,
        language    TEXT NOT NULL,
        transcript  TEXT NOT NULL,
        audio_url   TEXT,
        imported_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS checklists (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        name              TEXT NOT NULL,
        channel           TEXT NOT NULL,
        active_version_id INTEGER
    );

    CREATE TABLE IF NOT EXISTS checklist_versions (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        checklist_id INTEGER NOT NULL REFERENCES checklists(id),
        version      INTEGER NOT NULL,
        config       TEXT NOT NULL,
        comment      TEXT,
        created_at   TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS evaluations (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id      TEXT NOT NULL REFERENCES conversations(id),
        checklist_version_id INTEGER NOT NULL REFERENCES checklist_versions(id),
        model                TEXT NOT NULL,
        status               TEXT NOT NULL DEFAULT 'pending',
        total                TEXT,
        gross_error          INTEGER NOT NULL DEFAULT 0,
        prompt_hash          TEXT,
        raw_response         TEXT,
        cost_usd             TEXT,
        created_at           TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS criterion_results (
        evaluation_id INTEGER NOT NULL REFERENCES evaluations(id),
        criterion_id  TEXT NOT NULL,
        answer        TEXT NOT NULL,
        scale_value   INTEGER,
        points        TEXT,
        explanation   TEXT,
        evidence      TEXT,
        checked_range TEXT,
        confidence    TEXT,
        needs_review  INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (evaluation_id, criterion_id)
    );

    CREATE TABLE IF NOT EXISTS appeals (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        evaluation_id   INTEGER NOT NULL REFERENCES evaluations(id),
        criterion_id    TEXT NOT NULL,
        comment         TEXT NOT NULL,
        status          TEXT NOT NULL DEFAULT 'open',
        created_at      TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS decisions (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        appeal_id        INTEGER NOT NULL REFERENCES appeals(id),
        action           TEXT NOT NULL,
        new_answer       TEXT,
        new_scale_value  INTEGER,
        reason           TEXT NOT NULL,
        original_points  TEXT,
        final_points     TEXT,
        created_at       TEXT NOT NULL
    );
    """)
    conn.commit()
    conn.close()
