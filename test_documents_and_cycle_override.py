import asyncio
import os
import sys
import json
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Ensure UTF-8 output on Windows console
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app.database import init_db, get_db_connection
from app.models import FacetDefinition
from app.fetch import process_pasted_text
from app.extract import extract_claims_for_source, get_template_facets
from app.detect import run_gap_detection, classify_conflict_pair, build_coverage_matrix


def test_required_documents_subset_superset():
    print("\n--- TEST 1: REQUIRED DOCUMENTS SUBSET / SUPERSET (PARTIAL OVERLAP) ---")

    facet_def = FacetDefinition(
        id="required_documents",
        name="Required Documents",
        description="Documents needed",
        expected_type="list"
    )

    # Claim A: Comprehensive official list
    claim_a = {
        "source_title": "Official Guidelines 2025-26",
        "source_authority": "official",
        "facet": "required_documents",
        "value_raw": "Aadhaar Card, Marksheet, Income Certificate, and Bank Passbook",
        "norm_data": {
            "type": "list",
            "data": ["aadhaar", "bank_passbook", "income_certificate", "marksheet"]
        },
        "cycle": "2025-26",
        "scope": "general"
    }

    # Claim B: Subset list (aggregator only lists 2 items)
    claim_b = {
        "source_title": "Aggregator Quick Summary",
        "source_authority": "low",
        "facet": "required_documents",
        "value_raw": "Aadhaar Card and Marksheet",
        "norm_data": {
            "type": "list",
            "data": ["aadhaar", "marksheet"]
        },
        "cycle": "2025-26",
        "scope": "general"
    }

    # Test classification
    expl = classify_conflict_pair(claim_a, claim_b, facet_def, "2025-26")
    print(f"Classification Result: {expl['conflict_type']} ({expl['label']})")
    print(f"Explanation: {expl['explanation']}")
    print(f"Extra items listed: {expl.get('extra_items')}")

    assert expl["conflict_type"] == "partial_overlap", f"Expected partial_overlap, got {expl['conflict_type']}"
    assert expl["conflict_type"] != "real_conflict", "Must NOT be classified as real_conflict"
    assert "bank_passbook" in expl["extra_items"]
    assert "income_certificate" in expl["extra_items"]
    print("✓ Passed: Subset list was correctly classified as partial_overlap with extra items identified.")

    # Claim C: Identical list (cosmetic difference)
    claim_c = {
        "source_title": "State Portal Notification",
        "source_authority": "official",
        "facet": "required_documents",
        "value_raw": "Bank Passbook, Income Certificate, Marksheet, Aadhaar Card",
        "norm_data": {
            "type": "list",
            "data": ["aadhaar", "bank_passbook", "income_certificate", "marksheet"]
        },
        "cycle": "2025-26",
        "scope": "general"
    }
    expl_c = classify_conflict_pair(claim_a, claim_c, facet_def, "2025-26")
    assert expl_c["conflict_type"] == "formatting_difference"
    print("✓ Passed: Functionally identical lists correctly classified as formatting_difference.")


async def test_merged_deadlines_and_cycle_override():
    print("\n--- TEST 2: MERGED DEADLINE ALERTS & CURRENT CYCLE OVERRIDE ---")
    init_db()
    conn = get_db_connection()

    session_id = "ses_test_override_merge"
    facets = get_template_facets("scholarship")
    facets_json = json.dumps([f.model_dump() for f in facets])

    conn.execute("DELETE FROM research_sessions WHERE id = ?", (session_id,))
    # 1. Initialize without target_cycle (auto-detect / inferred mode)
    conn.execute("""
        INSERT INTO research_sessions (id, goal, domain_type, official_domain, target_cycle, facets_json)
        VALUES (?, 'Test Deadlines and Override', 'scholarship', 'scholarships.gov.in', NULL, ?)
    """, (session_id, facets_json))

    # Ingest sources with two different expired deadlines for cycle 2025-26
    # Source 1: Official states 31st October 2025
    # Source 2: Aggregator states 15th November 2025
    src1_id = f"src_official_{session_id}"
    src2_id = f"src_aggregator_{session_id}"

    text1 = "Application Deadline is 31st October 2025 for academic session 2025-2026. Family income must be under Rs. 3,50,000 per annum."
    text2 = "Last date to submit application is 15th November 2025 for session 2025-26. Family income must be under Rs. 1,50,000."

    doc1 = process_pasted_text(text1, title="Official Guidelines")
    doc2 = process_pasted_text(text2, title="Aggregator Post")

    for sid, doc, auth, url in [
        (src1_id, doc1, "official", "https://scholarships.gov.in/rules"),
        (src2_id, doc2, "low", "https://sarkarihelp.com/scholarship")
    ]:
        conn.execute("DELETE FROM sources WHERE id = ?", (sid,))
        conn.execute("""
            INSERT INTO sources (id, session_id, url, content_hash, published_date, published_date_origin, authority, original_group_id, text, title, fetch_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            sid, session_id, url, doc["content_hash"], doc["published_date"],
            doc["published_date_origin"], auth, sid, doc["text"], doc["title"], "pasted"
        ))

    conn.commit()
    conn.close()

    # Extract claims
    await extract_claims_for_source(session_id, src1_id)
    await extract_claims_for_source(session_id, src2_id)

    # 1. Run Detection in Auto-detect Mode
    res_auto = run_gap_detection(session_id)
    print(f"Auto-detected cycle: {res_auto['current_cycle']} (Assumed: {res_auto['is_cycle_assumed']})")
    assert res_auto["current_cycle"] == "2025-26"
    assert res_auto["is_cycle_assumed"] is True

    # Check merged deadline passed item
    deadline_passed_items = [g for g in res_auto["gaps"] if g.get("gap_type") == "deadline_passed"]
    print(f"\nNumber of deadline_passed items in gaps: {len(deadline_passed_items)}")
    for dpi in deadline_passed_items:
        print(f"  Title: {dpi['title']}")
        print(f"  Description: {dpi['description']}")
        print(f"  Action: {dpi['action_needed']}")

    assert len(deadline_passed_items) == 1, (
        f"Expected exactly ONE merged deadline_passed item for facet 'deadline', got {len(deadline_passed_items)}"
    )
    merged_item = deadline_passed_items[0]
    assert len(merged_item["sources_involved"]) == 2, "Expected both expired sources in merged item"
    print("✓ Passed: Multiple expired deadlines for the same facet were merged into ONE consolidated checklist item.")

    # 2. Test User Override: Update target_cycle to '2026-27'
    print("\n--- Overriding cycle to '2026-27' ---")
    conn = get_db_connection()
    conn.execute("UPDATE research_sessions SET target_cycle = '2026-27' WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()

    res_override = run_gap_detection(session_id)
    print(f"Updated cycle: {res_override['current_cycle']} (Assumed: {res_override['is_cycle_assumed']})")
    assert res_override["current_cycle"] == "2026-27"
    assert res_override["is_cycle_assumed"] is False
    assert "No source covers the current cycle (2026-27)" in res_override["cycle_warning"]
    print("✓ Passed: User override took effect immediately and is_cycle_assumed became False.")

    # Check Coverage Matrix reflects override
    matrix_res = build_coverage_matrix(session_id)
    assert matrix_res["current_cycle"] == "2026-27"
    assert matrix_res["is_cycle_assumed"] is False
    print("✓ Passed: Coverage matrix correctly reflects overridden target cycle.")

    print("\n==================================================")
    print("  ALL REQUIRED DOCUMENTS & OVERRIDE TESTS PASSED!")
    print("==================================================")


if __name__ == "__main__":
    test_required_documents_subset_superset()
    asyncio.run(test_merged_deadlines_and_cycle_override())
