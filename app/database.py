import sqlite3
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

def get_db_path() -> Path:
    return Path(os.environ.get("DARKSPOT_DB") or os.environ.get("LUMEN_DB_PATH") or "darkspot.db")


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(get_db_path()))
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

    CREATE TABLE IF NOT EXISTS registry_sources (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        domain_category TEXT NOT NULL,
        subcategory TEXT,
        base_url TEXT NOT NULL,
        allowed_paths TEXT,
        type TEXT CHECK(type IN ('official', 'secondary', 'community', 'aggregator')) NOT NULL,
        crawl_method TEXT CHECK(crawl_method IN ('api', 'rss', 'sitemap', 'html', 'pdf')) NOT NULL DEFAULT 'html',
        robots_status TEXT DEFAULT 'unverified',
        last_checked TIMESTAMP,
        reachability TEXT DEFAULT 'unverified',
        trust_score REAL DEFAULT 0,
        trust_reasons TEXT,
        language TEXT DEFAULT 'en',
        region TEXT DEFAULT 'national',
        owner TEXT,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS crawl_jobs (
        id TEXT PRIMARY KEY,
        category TEXT,
        domain TEXT,
        status TEXT CHECK(status IN ('pending', 'running', 'completed', 'failed')) DEFAULT 'pending',
        progress_pct REAL DEFAULT 0,
        processed_count INTEGER DEFAULT 0,
        total_count INTEGER DEFAULT 0,
        error TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS entities (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        normalized_name TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        domain_category TEXT NOT NULL,
        subcategory TEXT,
        issuing_body TEXT,
        region TEXT DEFAULT 'national',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS entity_attributes (
        id TEXT PRIMARY KEY,
        entity_id TEXT NOT NULL,
        attribute_name TEXT NOT NULL,
        attribute_value TEXT NOT NULL,
        exact_quote TEXT,
        source_id TEXT,
        verified INTEGER DEFAULT 0,
        uncertain INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS entity_sources (
        id TEXT PRIMARY KEY,
        entity_id TEXT NOT NULL,
        source_id TEXT NOT NULL,
        linked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_sources_session ON sources(session_id);
    CREATE INDEX IF NOT EXISTS idx_claims_session ON claims(session_id);
    CREATE INDEX IF NOT EXISTS idx_claims_source ON claims(source_id);
    CREATE INDEX IF NOT EXISTS idx_claims_facet ON claims(facet);
    CREATE INDEX IF NOT EXISTS idx_registry_category ON registry_sources(domain_category);
    CREATE INDEX IF NOT EXISTS idx_registry_base_url ON registry_sources(base_url);
    CREATE INDEX IF NOT EXISTS idx_entities_category ON entities(domain_category);
    CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
    CREATE INDEX IF NOT EXISTS idx_entity_attributes_entity ON entity_attributes(entity_id);
    CREATE INDEX IF NOT EXISTS idx_entity_sources_entity ON entity_sources(entity_id);
    """)

    # FTS5 virtual table
    try:
        cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
            entity_id UNINDEXED,
            name,
            domain_category,
            subcategory,
            issuing_body,
            attributes_text
        );
        """)
    except Exception as e:
        print(f"Warning: FTS5 initialization error: {e}")

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

    cursor.execute("PRAGMA table_info(registry_sources);")
    reg_cols = [r[1] for r in cursor.fetchall()]
    if "needs_js" not in reg_cols:
        cursor.execute("ALTER TABLE registry_sources ADD COLUMN needs_js INTEGER DEFAULT 0;")
    if "http_status" not in reg_cols:
        cursor.execute("ALTER TABLE registry_sources ADD COLUMN http_status INTEGER DEFAULT 0;")
    if "final_url" not in reg_cols:
        cursor.execute("ALTER TABLE registry_sources ADD COLUMN final_url TEXT;")
    if "audit_mode" not in reg_cols:
        cursor.execute("ALTER TABLE registry_sources ADD COLUMN audit_mode TEXT DEFAULT 'live';")
    if "last_audited" not in reg_cols:
        cursor.execute("ALTER TABLE registry_sources ADD COLUMN last_audited TIMESTAMP;")

    # Auto-seed demo snapshot if entities table is empty
    cursor.execute("SELECT COUNT(*) FROM entities;")
    ent_count = cursor.fetchone()[0]
    if ent_count == 0:
        snap_path = Path("data/demo_snapshot.json")
        if snap_path.exists():
            try:
                with open(snap_path, "r", encoding="utf-8") as f:
                    snap_data = json.load(f)
                from app.crawl.store import save_entity
                for ent in snap_data.get("entities", []):
                    save_entity(ent, conn=conn)
            except Exception:
                pass

    conn.commit()
    conn.close()


def row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    if row is None:
        return {}
    return {k: row[k] for k in row.keys()}
