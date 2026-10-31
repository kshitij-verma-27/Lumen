import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
import yaml

from app.database import get_db_connection, row_to_dict

logger = logging.getLogger(__name__)

REGISTRY_YAML_PATH = Path(os.environ.get("LUMEN_REGISTRY_YAML", "data/registry.yaml"))


def load_yaml_registry(yaml_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    path = yaml_path or REGISTRY_YAML_PATH
    if not path.exists():
        logger.warning(f"Registry YAML not found at {path}")
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("sources", []) if isinstance(data, dict) else []


def seed_registry_from_yaml(force: bool = False) -> int:
    """Syncs data/registry.yaml into the registry_sources SQLite table."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM registry_sources;")
    count = cursor.fetchone()[0]

    if count > 0 and not force:
        conn.close()
        return count

    seeds = load_yaml_registry()
    inserted = 0

    for s in seeds:
        allowed_paths_json = json.dumps(s.get("allowed_paths", ["/"]))
        reasons_json = json.dumps(s.get("trust_reasons", []))

        cursor.execute(
            """
            INSERT INTO registry_sources (
                id, name, domain_category, subcategory, base_url, allowed_paths,
                type, crawl_method, robots_status, last_checked, reachability,
                trust_score, trust_reasons, language, region, owner, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                domain_category = excluded.domain_category,
                subcategory = excluded.subcategory,
                base_url = excluded.base_url,
                allowed_paths = excluded.allowed_paths,
                type = excluded.type,
                crawl_method = excluded.crawl_method,
                owner = excluded.owner,
                notes = excluded.notes;
            """,
            (
                s["id"],
                s["name"],
                s["domain_category"],
                s.get("subcategory"),
                s["base_url"].rstrip("/"),
                allowed_paths_json,
                s.get("type", "official"),
                s.get("crawl_method", "html"),
                s.get("robots_status", "unverified"),
                s.get("last_checked"),
                s.get("reachability", "unverified"),
                s.get("trust_score", 0),
                reasons_json,
                s.get("language", "en"),
                s.get("region", "national"),
                s.get("owner"),
                s.get("notes"),
            ),
        )
        inserted += 1

    conn.commit()
    conn.close()
    return inserted


def get_all_registry_sources(
    domain_category: Optional[str] = None,
    reachability: Optional[str] = None,
) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    query = "SELECT * FROM registry_sources WHERE 1=1"
    params = []

    if domain_category:
        query += " AND domain_category = ?"
        params.append(domain_category)
    if reachability:
        query += " AND reachability = ?"
        params.append(reachability)

    query += " ORDER BY trust_score DESC, name ASC;"
    rows = conn.execute(query, params).fetchall()
    conn.close()

    results = []
    for r in rows:
        d = row_to_dict(r)
        if d.get("allowed_paths"):
            try:
                d["allowed_paths"] = json.loads(d["allowed_paths"])
            except Exception:
                d["allowed_paths"] = ["/"]
        if d.get("trust_reasons"):
            try:
                d["trust_reasons"] = json.loads(d["trust_reasons"])
            except Exception:
                d["trust_reasons"] = []
        results.append(d)
    return results


def get_registry_source_by_id(source_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM registry_sources WHERE id = ?;", (source_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = row_to_dict(row)
    try:
        d["allowed_paths"] = json.loads(d.get("allowed_paths") or "[]")
    except Exception:
        d["allowed_paths"] = ["/"]
    try:
        d["trust_reasons"] = json.loads(d.get("trust_reasons") or "[]")
    except Exception:
        d["trust_reasons"] = []
    return d


def find_registry_match_by_url(url: str) -> Optional[Dict[str, Any]]:
    """Match a URL against registry entries by domain or base URL."""
    try:
        parsed = urlparse(url)
        netloc = (parsed.netloc or "").lower().split(":")[0]
        if netloc.startswith("www."):
            netloc_clean = netloc[4:]
        else:
            netloc_clean = netloc
    except Exception:
        return None

    sources = get_all_registry_sources()
    for s in sources:
        base = s.get("base_url", "")
        try:
            b_parsed = urlparse(base)
            b_netloc = (b_parsed.netloc or "").lower().split(":")[0]
            b_netloc_clean = b_netloc[4:] if b_netloc.startswith("www.") else b_netloc
            if netloc_clean == b_netloc_clean or netloc.endswith("." + b_netloc_clean):
                return s
        except Exception:
            continue
    return None


def add_registry_source(data: Dict[str, Any]) -> Dict[str, Any]:
    """Adds a new user-submitted source to the registry."""
    conn = get_db_connection()
    cursor = conn.cursor()

    source_id = data.get("id")
    if not source_id:
        # Generate id from name or domain
        parsed = urlparse(data.get("base_url", ""))
        domain = parsed.netloc.replace(".", "_").replace(":", "_").lower()
        source_id = f"custom_{domain}_{os.urandom(3).hex()}"

    allowed_paths = json.dumps(data.get("allowed_paths", ["/"]))
    trust_reasons = json.dumps(data.get("trust_reasons", []))

    cursor.execute(
        """
        INSERT OR REPLACE INTO registry_sources (
            id, name, domain_category, subcategory, base_url, allowed_paths,
            type, crawl_method, robots_status, last_checked, reachability,
            trust_score, trust_reasons, language, region, owner, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            source_id,
            data["name"],
            data.get("domain_category", "education"),
            data.get("subcategory"),
            data["base_url"].rstrip("/"),
            allowed_paths,
            data.get("type", "secondary"),
            data.get("crawl_method", "html"),
            data.get("robots_status", "unverified"),
            data.get("last_checked"),
            data.get("reachability", "unverified"),
            data.get("trust_score", 50),
            trust_reasons,
            data.get("language", "en"),
            data.get("region", "national"),
            data.get("owner"),
            data.get("notes"),
        ),
    )
    conn.commit()
    conn.close()
    return get_registry_source_by_id(source_id) or data


def update_registry_source(source_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()

    fields = []
    params = []
    for k, v in updates.items():
        if k in ("allowed_paths", "trust_reasons") and isinstance(v, (list, dict)):
            v = json.dumps(v)
        fields.append(f"{k} = ?")
        params.append(v)

    if not fields:
        conn.close()
        return get_registry_source_by_id(source_id)

    params.append(source_id)
    cursor.execute(f"UPDATE registry_sources SET {', '.join(fields)} WHERE id = ?;", params)
    conn.commit()
    conn.close()
    return get_registry_source_by_id(source_id)
