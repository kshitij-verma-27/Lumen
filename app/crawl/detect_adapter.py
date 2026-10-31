import json
import logging
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime

from app.database import get_db_connection, row_to_dict
from app.crawl.store import get_entity_by_id
from app.detect import run_gap_detection, build_coverage_matrix
from app.normalize import normalize_claim_value

logger = logging.getLogger(__name__)

STANDARD_ENTITY_FACETS = [
    {
        "id": "eligibility",
        "name": "Eligibility Criteria",
        "description": "Who is eligible to apply or participate",
        "expected_type": "text",
        "importance": "critical",
        "consequence": "Ineligible applications will be rejected without refund.",
        "is_deadline": False,
    },
    {
        "id": "deadlines",
        "name": "Application Deadline",
        "description": "Last date and time to submit application",
        "expected_type": "date",
        "importance": "critical",
        "consequence": "Submissions after deadline are strictly barred.",
        "is_deadline": True,
    },
    {
        "id": "fees",
        "name": "Application / Registration Fee",
        "description": "Cost to register or apply",
        "expected_type": "currency",
        "importance": "high",
        "consequence": "Unpaid or incorrect fee results in invalid application.",
        "is_deadline": False,
    },
    {
        "id": "dates",
        "name": "Key Event / Exam Dates",
        "description": "Schedule of exam, interview, or disbursement",
        "expected_type": "date",
        "importance": "high",
        "consequence": "Missing schedule dates causes missed opportunities.",
        "is_deadline": False,
    },
    {
        "id": "documents",
        "name": "Required Documents",
        "description": "Certificates, marksheets, identity proof",
        "expected_type": "list",
        "importance": "medium",
        "consequence": "Missing documents delay verification.",
        "is_deadline": False,
    },
    {
        "id": "apply_link",
        "name": "Official Application Portal Link",
        "description": "Direct portal URL for submission",
        "expected_type": "text",
        "importance": "critical",
        "consequence": "Using fake portals leads to scams and data theft.",
        "is_deadline": False,
    },
    {
        "id": "contact",
        "name": "Official Helplines and Contact",
        "description": "Email address and telephone numbers",
        "expected_type": "text",
        "importance": "medium",
        "consequence": "Cannot resolve submission issues without official contact.",
        "is_deadline": False,
    },
]


def sync_entity_to_session(entity_id: str) -> str:
    """
    Creates or updates a research session for an entity, bridging entity attributes
    into claims so the full detect.py analysis engine operates on it seamlessly.
    """
    entity = get_entity_by_id(entity_id)
    if not entity:
        raise ValueError(f"Entity {entity_id} not found")

    session_id = f"sess_{entity_id}"
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Upsert research session
    cursor.execute(
        """
        INSERT INTO research_sessions (
            id, goal, domain_type, official_domain, target_version_period, facets_json
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            goal = excluded.goal,
            official_domain = excluded.official_domain,
            facets_json = excluded.facets_json;
        """,
        (
            session_id,
            f"Verification of {entity['name']}",
            entity.get("domain_category", "general"),
            entity.get("issuing_body", "official.gov.in"),
            "2026",
            json.dumps(STANDARD_ENTITY_FACETS),
        ),
    )

    # 2. Sync all sources linked to this entity or referenced by its attributes
    linked_sources = entity.get("sources", [])
    source_map = {s.get("source_id"): s for s in linked_sources if s.get("source_id")}
    all_needed_source_ids = set(source_map.keys())
    for attr in entity.get("attributes", []):
        if attr.get("source_id"):
            all_needed_source_ids.add(attr["source_id"])

    if not all_needed_source_ids:
        all_needed_source_ids.add(f"src_primary_{entity_id}")

    for s_id in all_needed_source_ids:
        s = source_map.get(s_id, {})
        base_url = s.get("base_url") or s.get("url") or f"https://source.portal/{s_id}"
        title = s.get("registry_name") or s.get("title") or s.get("name") or entity["name"]
        text = s.get("text") or s.get("source_text") or f"Source record for {entity['name']}"
        trust = s.get("trust_score") or 85
        auth = "official" if trust >= 80 else "secondary"

        cursor.execute(
            """
            INSERT OR REPLACE INTO sources (
                id, session_id, url, text, title, authority, fetch_status, content_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                s_id,
                session_id,
                base_url,
                text,
                title,
                auth,
                "success",
                f"hash_{s_id}",
            ),
        )

    # 3. Sync claims from entity attributes
    # Clear existing claims for session
    cursor.execute("DELETE FROM claims WHERE session_id = ?;", (session_id,))

    for attr in entity.get("attributes", []):
        claim_id = f"claim_{attr['id']}"
        val = attr["attribute_value"]
        facet = attr["attribute_name"]
        norm_val = json.dumps(normalize_claim_value(facet, val))
        src_id = attr.get("source_id")
        if not src_id or src_id not in all_needed_source_ids:
            src_id = list(all_needed_source_ids)[0]

        cursor.execute(
            """
            INSERT INTO claims (
                id, session_id, source_id, facet, value_raw, value_normalized,
                exact_quote, verified, verification_score, rejection_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                claim_id,
                session_id,
                src_id,
                facet,
                val,
                norm_val,
                attr.get("exact_quote", val),
                attr.get("verified", 0),
                attr.get("verification_score", 1.0),
                attr.get("rejection_reason"),
            ),
        )

    conn.commit()
    conn.close()
    return session_id


def analyze_entity_gaps(entity_id: str) -> Dict[str, Any]:
    """
    Runs the full detect.py information gap engine on an entity.
    Returns: gaps, conflicts, outdated warnings, coverage matrix, and checklist.
    """
    session_id = sync_entity_to_session(entity_id)
    analysis = run_gap_detection(session_id)
    matrix = build_coverage_matrix(session_id)
    analysis["coverage_matrix"] = matrix
    return analysis
