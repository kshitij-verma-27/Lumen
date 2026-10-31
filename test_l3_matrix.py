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
from app.detect import run_gap_detection, build_coverage_matrix, classify_conflict_pair


async def test_l3_matrix_and_quick_fixes():
    print("\n==================================================")
    print("  TEST: L3 COVERAGE MATRIX & QUICK FIXES")
    print("==================================================")

    init_db()
    conn = get_db_connection()

    session_id = "ses_test_l3_matrix"
    facets = get_template_facets("scholarship") + [
        FacetDefinition(
            id="hostel_subsidy",
            name="Hostel / Accommodation Subsidy",
            description="Boarding and hostel allowance rules",
            expected_type="currency"
        )
    ]
    facets_json = json.dumps([f.model_dump() for f in facets])

    conn.execute("DELETE FROM research_sessions WHERE id = ?", (session_id,))
    # Do NOT set target_cycle, so we can test Quick Fix 1 (warns when cycle is unconfirmed / unreached)
    conn.execute("""
        INSERT INTO research_sessions (id, goal, domain_type, official_domain, facets_json)
        VALUES (?, 'Test L3 Coverage Matrix and Gap Detection', 'scholarship', 'scholarships.gov.in', ?)
    """, (session_id, facets_json))

    sample_files = [
        ("sample_sources/scholarship_official_guidelines.txt", "https://scholarships.gov.in/guidelines-2025.html", "official"),
        ("sample_sources/scholarship_aggregator_blog.txt", "https://sarkarihelp-aggregators.com/alert-2025.html", "low"),
        ("sample_sources/scholarship_outdated_circular.txt", "https://scholarships.gov.in/archive/2023.html", "official")
    ]

    source_ids = []
    for fpath, url, auth in sample_files:
        text = Path(fpath).read_text(encoding="utf-8")
        doc = process_pasted_text(text, title=Path(fpath).stem)
        src_id = f"src_{Path(fpath).stem}_{session_id}"
        source_ids.append(src_id)

        conn.execute("DELETE FROM sources WHERE id = ?", (src_id,))
        conn.execute("""
            INSERT INTO sources (id, session_id, url, content_hash, published_date, published_date_origin, authority, original_group_id, text, title, fetch_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            src_id, session_id, url, doc["content_hash"], doc["published_date"],
            doc["published_date_origin"], auth, src_id, doc["text"], doc["title"], "pasted"
        ))

    conn.commit()
    conn.close()

    # Run extraction across all 3 sources
    print("Ingesting sources and extracting claims...")
    for sid in source_ids:
        await extract_claims_for_source(session_id, sid)

    # 1. Test Gap Detection & Quick Fixes
    det_results = run_gap_detection(session_id)

    print("\n--- CHECK 1: CYCLE WARNING (Quick Fix 1) ---")
    print(f"Current Cycle Derived: {det_results['current_cycle']}")
    print(f"Cycle Warning: {det_results['cycle_warning']}")
    assert det_results["cycle_warning"] is not None
    assert "no source covers the current cycle" in det_results["cycle_warning"].lower()
    cycle_gaps = [g for g in det_results["gaps"] if g.get("gap_type") == "cycle_warning"]
    assert len(cycle_gaps) > 0, "Expected 'cycle_warning' gap item in gaps list"
    print(f"✓ Quick Fix 1 Passed: System warned '{cycle_gaps[0]['title']}' instead of silently treating newest as current.")

    print("\n--- CHECK 2: DEADLINE PASSED ONLY FOR CURRENT CYCLE (Quick Fix 2) ---")
    deadline_passed_gaps = [g for g in det_results["gaps"] if g.get("gap_type") == "deadline_passed"]
    for dg in deadline_passed_gaps:
        print(f"  🚨 Deadline Passed Item: {dg['title']}")
        for s in dg.get("sources_involved", []):
            # Assert none of the deadline passed items come from the 2023-24 circular
            assert "2023" not in s["value"] and "30th September 2023" not in s["value"], \
                f"Old-cycle deadline {s['value']} should have been skipped by deadline passed check!"
    print("✓ Quick Fix 2 Passed: Outdated circular deadline (30-09-2023) was skipped by deadline-passed check and kept under outdated.")

    print("\n--- CHECK 3: TIME DIFFERENCE SEVERITY LOWER THAN REAL CONFLICT (Quick Fix 3) ---")
    time_diff_gaps = [g for g in det_results["gaps"] if g.get("gap_type") == "time_difference"]
    conflict_gaps = [g for g in det_results["gaps"] if g.get("gap_type") == "conflict"]
    assert len(conflict_gaps) > 0, "Expected real conflicts"
    assert len(time_diff_gaps) > 0, "Expected time difference gaps"
    
    for cg in conflict_gaps:
        assert cg["priority"] == "critical", f"Conflict priority should be critical, got {cg['priority']}"
    for tg in time_diff_gaps:
        assert tg["priority"] == "medium", f"Time difference priority should be medium, got {tg['priority']}"
    print(f"✓ Quick Fix 3 Passed: time_difference priority is 'medium', below real_conflict priority 'critical'.")

    # 2. Test Coverage Matrix Generator (L3 Deliverable)
    print("\n--- CHECK 4: COVERAGE MATRIX GENERATION (L3 Matrix) ---")
    matrix_data = build_coverage_matrix(session_id)

    print(f"Session ID: {matrix_data['session_id']}")
    print(f"Total Sources: {len(matrix_data['sources'])}")
    print(f"Stats: {matrix_data['stats']}")

    assert len(matrix_data["sources"]) == 3, "Expected 3 sources in matrix"
    assert matrix_data["stats"]["total_facets"] == len(facets), f"Expected {len(facets)} facets in matrix"
    assert matrix_data["stats"]["dark_spots_count"] >= 1, "Expected dark spots (e.g. Hostel Subsidy)"
    assert matrix_data["stats"]["conflicts_count"] >= 1, "Expected conflicts in matrix"
    assert matrix_data["stats"]["coverage_score"] > 0, "Expected positive coverage score"

    # Verify Rows & Cells
    print("\n[COVERAGE MATRIX ROW INSPECTION]")
    found_dark_spot = False
    found_conflict = False
    found_timediff = False

    for row in matrix_data["matrix"]:
        fid = row["facet_id"]
        status = row["status"]
        print(f"  Facet: {row['facet_name']:<32} | Status: {row['status_label']:<40} | Covered: {row['sources_covered']}/{row['total_sources']}")

        if status == "dark_spot":
            found_dark_spot = True
            for sid, cell in row["cells"].items():
                assert cell["has_claim"] is False, f"Dark spot row {fid} should have no claims in cell"
        elif status == "conflict":
            found_conflict = True
            # Verify conflicting cells have is_conflicting flag
            for sid, cell in row["cells"].items():
                if cell["has_claim"]:
                    assert cell["is_conflicting"] is True

        if status == "time_difference":
            found_timediff = True

    assert found_dark_spot, "Coverage matrix must flag dark spots correctly"
    assert found_conflict, "Coverage matrix must flag conflicting facets correctly"
    assert found_timediff, "Coverage matrix must flag time differences correctly"

    print("\n==================================================")
    print("  ALL L3 COVERAGE MATRIX & QUICK FIX CHECKS PASSED!")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(test_l3_matrix_and_quick_fixes())
