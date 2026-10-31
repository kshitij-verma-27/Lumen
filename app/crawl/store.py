import hashlib
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
from app.database import get_db_connection, row_to_dict

logger = logging.getLogger(__name__)


def generate_entity_id(name: str, domain_category: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9]", "", name.lower())
    h = hashlib.sha256(f"{clean}_{domain_category}".encode("utf-8")).hexdigest()[:10]
    return f"ent_{clean[:12]}_{h}"


def save_entity(entity_data: Dict[str, Any], conn: Optional[sqlite3.Connection] = None) -> str:
    """
    Saves an entity, its verified attributes, and linked sources into SQLite,
    and updates the FTS5 full-text index.
    """
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True
    cursor = conn.cursor()

    entity_id = entity_data.get("id") or generate_entity_id(
        entity_data["name"], entity_data.get("domain_category", "general")
    )

    # 1. Insert or update entity
    cursor.execute(
        """
        INSERT INTO entities (
            id, name, normalized_name, entity_type, domain_category,
            subcategory, issuing_body, region
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            entity_type = excluded.entity_type,
            domain_category = excluded.domain_category,
            subcategory = excluded.subcategory,
            issuing_body = excluded.issuing_body,
            region = excluded.region;
        """,
        (
            entity_id,
            entity_data["name"],
            entity_data.get("normalized_name") or entity_data["name"].lower(),
            entity_data.get("entity_type", "scheme"),
            entity_data.get("domain_category", "education"),
            entity_data.get("subcategory", "general"),
            entity_data.get("issuing_body", "Official Authority"),
            entity_data.get("region", "national"),
        ),
    )

    # 2. Insert attributes
    attr_texts = []
    seen_quotes = set()
    for attr in entity_data.get("attributes", []):
        from app.validation.data_quality import validate_and_dedupe_attribute
        is_valid_qual, qual_reason = validate_and_dedupe_attribute(
            attr.get("attribute_name", ""),
            attr.get("attribute_value", ""),
            attr.get("exact_quote", ""),
            seen_quotes
        )
        if not is_valid_qual:
            logger.debug(f"save_entity data quality skip for {attr.get('attribute_name')}: {qual_reason}")
            continue

        attr_id = f"attr_{entity_id}_{attr['attribute_name']}_{os.urandom(3).hex()}"
        cursor.execute(
            """
            INSERT INTO entity_attributes (
                id, entity_id, attribute_name, attribute_value, exact_quote,
                source_id, verified, uncertain
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                attr_id,
                entity_id,
                attr["attribute_name"],
                attr["attribute_value"],
                attr.get("exact_quote"),
                attr.get("source_id"),
                attr.get("verified", 0),
                attr.get("uncertain", 0),
            ),
        )
        attr_texts.append(f"{attr['attribute_name']}: {attr['attribute_value']}")

    # 3. Link sources
    for src_id in entity_data.get("source_ids", []):
        link_id = f"link_{entity_id}_{src_id}"
        cursor.execute(
            """
            INSERT OR IGNORE INTO entity_sources (id, entity_id, source_id)
            VALUES (?, ?, ?);
            """,
            (link_id, entity_id, src_id),
        )

    # 4. Synchronize FTS5 search index
    combined_attributes_text = " ".join(attr_texts)
    try:
        # Delete old FTS entry if exists
        cursor.execute("DELETE FROM entities_fts WHERE entity_id = ?;", (entity_id,))
        cursor.execute(
            """
            INSERT INTO entities_fts (
                entity_id, name, domain_category, subcategory, issuing_body, attributes_text
            ) VALUES (?, ?, ?, ?, ?, ?);
            """,
            (
                entity_id,
                entity_data["name"],
                entity_data.get("domain_category", ""),
                entity_data.get("subcategory", ""),
                entity_data.get("issuing_body", ""),
                combined_attributes_text,
            ),
        )
    except Exception as e:
        logger.warning(f"FTS5 index insert skipped: {e}")

    if should_close:
        conn.commit()
        conn.close()
    return entity_id


def get_entity_by_id(entity_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves full entity details including verified attributes and sources."""
    conn = get_db_connection()
    e_row = conn.execute("SELECT * FROM entities WHERE id = ?;", (entity_id,)).fetchone()
    if not e_row:
        conn.close()
        return None

    entity = row_to_dict(e_row)

    # Attributes
    attr_rows = conn.execute(
        """
        SELECT * FROM entity_attributes
        WHERE entity_id = ?
        ORDER BY verified DESC, attribute_name ASC;
        """,
        (entity_id,),
    ).fetchall()
    entity["attributes"] = [row_to_dict(r) for r in attr_rows]

    # Sources
    src_rows = conn.execute(
        """
        SELECT es.source_id as source_id, rs.name as registry_name, rs.base_url, rs.trust_score,
               s.url as source_url, s.title as source_title, s.authority, s.text as source_text
        FROM entity_sources es
        LEFT JOIN registry_sources rs ON es.source_id = rs.id
        LEFT JOIN sources s ON es.source_id = s.id
        WHERE es.entity_id = ?;
        """,
        (entity_id,),
    ).fetchall()
    entity["sources"] = [row_to_dict(r) for r in src_rows]

    conn.close()
    return entity


def search_entities(
    query: Optional[str] = None,
    domain_category: Optional[str] = None,
    entity_type: Optional[str] = None,
    region: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    Searches entities using FTS5 when a query is provided, or structured filters.
    """
    conn = get_db_connection()

    if query and query.strip():
        # FTS5 Match
        clean_q = re.sub(r"[^\w\s]", "", query).strip()
        fts_query = f"{clean_q}*"
        try:
            sql = """
            SELECT e.*, snippet(entities_fts, 5, '<b>', '</b>', '...', 15) as snippet
            FROM entities_fts f
            JOIN entities e ON f.entity_id = e.id
            WHERE entities_fts MATCH ?
            """
            params: List[Any] = [fts_query]

            if domain_category:
                sql += " AND e.domain_category = ?"
                params.append(domain_category)
            if entity_type:
                sql += " AND e.entity_type = ?"
                params.append(entity_type)
            if region:
                sql += " AND e.region = ?"
                params.append(region)

            sql += " LIMIT ?;"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            results = [row_to_dict(r) for r in rows]
            conn.close()
            return results
        except Exception as e:
            logger.warning(f"FTS5 query failed, falling back to LIKE: {e}")

    # Standard SQL Filter Fallback
    sql = "SELECT * FROM entities WHERE 1=1"
    params = []

    if query and query.strip():
        sql += " AND (name LIKE ? OR issuing_body LIKE ?)"
        like_q = f"%{query.strip()}%"
        params.extend([like_q, like_q])
    if domain_category:
        sql += " AND domain_category = ?"
        params.append(domain_category)
    if entity_type:
        sql += " AND entity_type = ?"
        params.append(entity_type)
    if region:
        sql += " AND region = ?"
        params.append(region)

    sql += " ORDER BY created_at DESC LIMIT ?;"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    results = [row_to_dict(r) for r in rows]
    conn.close()
    return results
