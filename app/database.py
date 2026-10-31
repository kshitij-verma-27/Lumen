import sqlite3
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(os.environ.get("LUMEN_DB_PATH", "darkspot.db"))


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS research_sessions (
        id TEXT PRIMARY KEY,
        goal TEXT NOT NULL,
        domain_type TEXT NOT NULL DEFAULT 'scholarship',
        official_domain TEXT,
        target_cycle TEXT,
        target_version_period TEXT,
        facets_json TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS sources (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        url TEXT,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        content_hash TEXT NOT NULL,
        published_date TEXT,
        published_date_origin TEXT DEFAULT 'none',
        authority TEXT CHECK(authority IN ('official', 'secondary', 'low')) NOT NULL,
        original_group_id TEXT,
        text TEXT NOT NULL,
        title TEXT,
        fetch_status TEXT CHECK(fetch_status IN ('success', 'failed', 'cached', 'pasted')) NOT NULL,
        error_message TEXT,
        FOREIGN KEY(session_id) REFERENCES research_sessions(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS claims (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        source_id TEXT NOT NULL,
        facet TEXT NOT NULL,
        value_raw TEXT NOT NULL,
        value_normalized TEXT,
        exact_quote TEXT NOT NULL,
        scope TEXT DEFAULT 'general',
        cycle TEXT,
        version_period TEXT,
        verified INTEGER NOT NULL DEFAULT 0,
        verification_score REAL DEFAULT 0,
        quote_offset_start INTEGER,
        quote_offset_end INTEGER,
        rejection_reason TEXT,
        survived_redteam INTEGER DEFAULT 1,
        redteam_notes TEXT,
        FOREIGN KEY(source_id) REFERENCES sources(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS cache (
        cache_key TEXT PRIMARY KEY,
        cache_type TEXT NOT NULL,
        payload TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_sources_session ON sources(session_id);
    CREATE INDEX IF NOT EXISTS idx_claims_session ON claims(session_id);
    CREATE INDEX IF NOT EXISTS idx_claims_source ON claims(source_id);
    CREATE INDEX IF NOT EXISTS idx_claims_facet ON claims(facet);
    """)

    # Column migrations
    cursor.execute("PRAGMA table_info(research_sessions);")
    sess_cols = [r[1] for r in cursor.fetchall()]
    if "target_cycle" not in sess_cols:
        cursor.execute("ALTER TABLE research_sessions ADD COLUMN target_cycle TEXT;")
    if "target_version_period" not in sess_cols:
        cursor.execute("ALTER TABLE research_sessions ADD COLUMN target_version_period TEXT;")

    cursor.execute("PRAGMA table_info(claims);")
    claim_cols = [r[1] for r in cursor.fetchall()]
    if "version_period" not in claim_cols:
        cursor.execute("ALTER TABLE claims ADD COLUMN version_period TEXT;")
    if "redteam_status" not in claim_cols:
        cursor.execute("ALTER TABLE claims ADD COLUMN redteam_status TEXT DEFAULT 'survived';")
    if "redteam_notes" not in claim_cols:
        cursor.execute("ALTER TABLE claims ADD COLUMN redteam_notes TEXT;")

    cursor.execute("PRAGMA table_info(sources);")
    src_cols = [r[1] for r in cursor.fetchall()]
    if "last_checked_at" not in src_cols:
        cursor.execute("ALTER TABLE sources ADD COLUMN last_checked_at TIMESTAMP;")

    conn.commit()
    conn.close()


def row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    if row is None:
        return {}
    return {k: row[k] for k in row.keys()}
