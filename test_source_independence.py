"""
Test Suite: Source Independence Badge & Duplicate Source Detection
Validates:
1. Text similarity calculation (Jaccard, containment, sequence ratio).
2. Near-duplicate and copied source clustering with canonical original designation.
3. Badge generation: "3 sources, 1 original" and "3 sources, 2 originals".
4. Corroborated vs Single-source logic: claims appearing across copied sources
   count as a single source (single_source), while claims appearing across
   genuinely independent originals count as corroborated (corroborated).
5. Coverage matrix reflection of copy status.
"""

import sys
import uuid
import json
import sqlite3
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.database import get_db_connection, init_db, row_to_dict
from app.models import FacetDefinition
from app.independence import (
    calculate_text_similarity,
    group_sources_by_independence,
    detect_and_group_sources
)
from app.detect import run_gap_detection, build_coverage_matrix


def run_source_independence_tests():
    init_db()
    conn = get_db_connection()

    print("\n" + "=" * 65)
    print("TEST: SOURCE INDEPENDENCE & NEAR-DUPLICATE DETECTION")
    print("=" * 65)

    # ---------------------------------------------------------
    # 1. Text Similarity Unit Tests
    # ---------------------------------------------------------
    page_1_official_text = (
        "GOVERNMENT NOTIFICATION - NATIONAL MERIT SCHOLARSHIP 2025-26\n"
        "The Department of Higher Education hereby invites online applications for the National Merit Scholarship.\n"
        "1. ELIGIBILITY: Students must have secured at least 55% aggregate marks in Class VII examination.\n"
        "2. FAMILY INCOME LIMIT: Total annual income of parents/guardians from all sources must not exceed Rs. 3,50,000/- per annum.\n"
        "3. SCHOLARSHIP AMOUNT: Selected scholars will receive Rs. 12,000/- per annum disbursed directly via DBT into Aadhaar-seeded accounts.\n"
        "4. APPLICATION DEADLINE: All online registrations and school verifications close strictly on 31st October 2025.\n"
        "5. MANDATORY DOCUMENTS: Applicants must upload scanned copy of Aadhaar card, income certificate, marksheet, and bank passbook.\n"
        "Late submissions will be summarily rejected without further inquiry."
    )

    page_2_copied_blog_text = (
        "WELCOME TO SCHOLARSHIPALERTS.IN - YOUR #1 EDUCATION ADVISORY PORTAL!\n"
        "Hey students! Good news. The government has released the fresh circular for the National Merit Scholarship scheme.\n"
        "Here is the complete official notification text reprinted for your reference:\n"
        "GOVERNMENT NOTIFICATION - NATIONAL MERIT SCHOLARSHIP 2025-26\n"
        "The Department of Higher Education hereby invites online applications for the National Merit Scholarship.\n"
        "1. ELIGIBILITY: Students must have secured at least 55% aggregate marks in Class VII examination.\n"
        "2. FAMILY INCOME LIMIT: Total annual income of parents/guardians from all sources must not exceed Rs. 3,50,000/- per annum.\n"
        "3. SCHOLARSHIP AMOUNT: Selected scholars will receive Rs. 12,000/- per annum disbursed directly via DBT into Aadhaar-seeded accounts.\n"
        "4. APPLICATION DEADLINE: All online registrations and school verifications close strictly on 31st October 2025.\n"
        "5. MANDATORY DOCUMENTS: Applicants must upload scanned copy of Aadhaar card, income certificate, marksheet, and bank passbook.\n"
        "Late submissions will be summarily rejected without further inquiry.\n"
        "Join our Telegram channel and WhatsApp discussion group for live updates!"
    )

    page_3_different_text = (
        "ANNUAL REPORT ON HIGHER EDUCATION TECH ASSISTANCE AND LAPTOP SUBSIDIES\n"
        "State Council for Higher Education Policy Whitepaper 2025.\n"
        "This independent policy analysis examines digital divide remediation across state universities.\n"
        "Recommended student hardware specifications include minimum 16GB DDR5 memory, PCIe Gen 4 solid state storage, "
        "and quad-core processing units. Institutional procurement grants of $1,200 per enrolled STEM scholar are recommended.\n"
        "The statewide technology grant portal opens on 31st October 2025 for accredited state institutions.\n"
        "Independent audits confirm that direct equipment distribution reduces dropouts by 18 percent compared to cash allowances."
    )

    sim_1_2 = calculate_text_similarity(page_1_official_text, page_2_copied_blog_text)
    sim_1_3 = calculate_text_similarity(page_1_official_text, page_3_different_text)

    print(f"Similarity (Page 1 vs Page 2 Copy): {sim_1_2['overall_similarity']} (containment: {sim_1_2['containment']})")
    print(f"Similarity (Page 1 vs Page 3 Different): {sim_1_3['overall_similarity']} (containment: {sim_1_3['containment']})")

    assert sim_1_2["overall_similarity"] >= 0.70, "Near-identical copied page must have high similarity >= 0.70"
    assert sim_1_2["containment"] >= 0.80, "Copied page containment must be >= 0.80"
    assert sim_1_3["overall_similarity"] < 0.35, "Different page similarity must be < 0.35"
    print("  ✓ Text similarity metrics correctly distinguish copied sources from independent sources.")

    # ---------------------------------------------------------
    # 2. Database Session Setup with 3 Sources
    # ---------------------------------------------------------
    session_id = f"test_indep_{uuid.uuid4().hex[:8]}"
    src_1_id = f"src_official_{uuid.uuid4().hex[:6]}"
    src_2_id = f"src_copy_{uuid.uuid4().hex[:6]}"
    src_3_id = f"src_different_{uuid.uuid4().hex[:6]}"

    facets = [
        FacetDefinition(
            id="income_limit",
            name="Family Income Limit",
            description="Maximum household annual income to qualify",
            expected_type="currency",
            importance="critical",
            consequence="Exceeding the income cap disqualifies applicant"
        ),
        FacetDefinition(
            id="deadline",
            name="Application Deadline",
            description="Final closing date for registration and portal submission",
            expected_type="date",
            importance="critical",
            is_deadline=True,
            consequence="Missing deadline forfeits scholarship"
        ),
        FacetDefinition(
            id="scholarship_amount",
            name="Scholarship Amount",
            description="Total annual financial grant disbursed to selected scholars",
            expected_type="currency",
            importance="high",
            consequence="Under-budgeting causes funding shortfalls"
        )
    ]

    conn.execute("""
        INSERT INTO research_sessions (id, goal, domain_type, official_domain, target_version_period, facets_json)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        session_id,
        "What are the official requirements and deadlines for the National Merit Scholarship 2025-26?",
        "scholarship",
        "scholarships.gov.in",
        "2025-26",
        json.dumps([f.dict() for f in facets])
    ))

    # Insert 3 Sources: Page 1 (Official), Page 2 (Copy), Page 3 (Different)
    conn.execute("""
        INSERT INTO sources (id, session_id, url, title, authority, published_date, published_date_origin, content_hash, text, fetch_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        src_1_id, session_id, "https://scholarships.gov.in/circular_2025.pdf",
        "National Merit Scholarship Official Guidelines", "official", "2025-07-01", "meta_tag",
        "hash_official_111", page_1_official_text, "success"
    ))

    conn.execute("""
        INSERT INTO sources (id, session_id, url, title, authority, published_date, published_date_origin, content_hash, text, fetch_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        src_2_id, session_id, "https://scholarshipalerts.in/post/nms-2025-full-guide",
        "ScholarshipAlerts Blog Post", "low", "2025-07-05", "html_time",
        "hash_blog_222", page_2_copied_blog_text, "success"
    ))

    conn.execute("""
        INSERT INTO sources (id, session_id, url, title, authority, published_date, published_date_origin, content_hash, text, fetch_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        src_3_id, session_id, "https://higheredstate.org/reports/tech-assistance",
        "State Higher Education Board Report", "secondary", "2025-08-10", "json_ld",
        "hash_board_333", page_3_different_text, "success"
    ))
    conn.commit()

    # ---------------------------------------------------------
    # 3. Test detect_and_group_sources (2 originals, 1 copy)
    # ---------------------------------------------------------
    indep_res = detect_and_group_sources(session_id, conn)

    print("\nSource Independence Results:")
    print(f"  Total Sources: {indep_res['total_sources']}")
    print(f"  Independent Originals: {indep_res['independent_sources']}")
    print(f"  Badge Text: '{indep_res['badge_text']}'")

    assert indep_res["total_sources"] == 3
    assert indep_res["independent_sources"] == 2
    assert indep_res["badge_text"] == "3 sources, 2 originals"
    assert indep_res["source_group_map"][src_1_id] == src_1_id, "Page 1 must be its own original"
    assert indep_res["source_group_map"][src_2_id] == src_1_id, "Page 2 must be clustered under Page 1 original"
    assert indep_res["source_group_map"][src_3_id] == src_3_id, "Page 3 must be its own independent original"
    print("  ✓ Source Independence clustering correctly identified 2 originals from 3 sources.")

    # ---------------------------------------------------------
    # 4. Test "3 sources, 1 original" (all copies of one original)
    # ---------------------------------------------------------
    page_2b_second_copy_text = (
        "STUDYPORTAL LIVE REPRINT: " + page_1_official_text + "\nSource: Ministry circular."
    )
    src_2b_id = f"src_copy2_{uuid.uuid4().hex[:6]}"
    conn.execute("""
        INSERT INTO sources (id, session_id, url, title, authority, published_date, published_date_origin, content_hash, text, fetch_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        src_2b_id, session_id, "https://studyportal.com/nms-reprint",
        "StudyPortal Aggregator Copy", "low", "2025-07-06", "url_regex",
        "hash_studyportal_444", page_2b_second_copy_text, "success"
    ))
    conn.commit()

    # Cluster only src_1, src_2, and src_2b
    sample_3_copies = [
        {"id": src_1_id, "text": page_1_official_text, "authority": "official", "published_date": "2025-07-01", "title": "Official"},
        {"id": src_2_id, "text": page_2_copied_blog_text, "authority": "low", "published_date": "2025-07-05", "title": "Copy 1"},
        {"id": src_2b_id, "text": page_2b_second_copy_text, "authority": "low", "published_date": "2025-07-06", "title": "Copy 2"},
    ]
    three_copies_res = group_sources_by_independence(sample_3_copies)
    print(f"\n3 Sources (2 copies) Badge Text: '{three_copies_res['badge_text']}'")
    assert three_copies_res["badge_text"] == "3 sources, 1 original", f"Expected '3 sources, 1 original', got '{three_copies_res['badge_text']}'"
    assert three_copies_res["independent_sources"] == 1
    print("  ✓ Exact badge text '3 sources, 1 original' verified!")

    # Remove temporary src_2b so we continue with 2 near-identical + 1 different
    conn.execute("DELETE FROM sources WHERE id = ?", (src_2b_id,))
    conn.commit()

    # ---------------------------------------------------------
    # 5. Insert Verified Claims to Test Corroborated vs Single-source
    # ---------------------------------------------------------
    # Claim A1 (Official) on Income Limit: Rs. 3,50,000
    conn.execute("""
        INSERT INTO claims (id, session_id, source_id, facet, value_raw, exact_quote, cycle, version_period, verified, verification_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        f"claim_{uuid.uuid4().hex[:6]}", session_id, src_1_id, "income_limit",
        "Rs. 3,50,000", "Total annual income of parents/guardians from all sources must not exceed Rs. 3,50,000/- per annum.",
        "2025-26", "2025-26", 1, 1.0
    ))

    # Claim A2 (Copy) on Income Limit: Rs. 3,50,000 (copied verbatim from Official)
    conn.execute("""
        INSERT INTO claims (id, session_id, source_id, facet, value_raw, exact_quote, cycle, version_period, verified, verification_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        f"claim_{uuid.uuid4().hex[:6]}", session_id, src_2_id, "income_limit",
        "Rs. 3,50,000", "Total annual income of parents/guardians from all sources must not exceed Rs. 3,50,000/- per annum.",
        "2025-26", "2025-26", 1, 1.0
    ))

    # Claim B1 (Official) on Deadline: 31st October 2025
    conn.execute("""
        INSERT INTO claims (id, session_id, source_id, facet, value_raw, exact_quote, cycle, version_period, verified, verification_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        f"claim_{uuid.uuid4().hex[:6]}", session_id, src_1_id, "deadline",
        "31st October 2025", "All online registrations and school verifications close strictly on 31st October 2025.",
        "2025-26", "2025-26", 1, 1.0
    ))

    # Claim B3 (Different Page) on Deadline: 31st October 2025 (Independent corroboration!)
    conn.execute("""
        INSERT INTO claims (id, session_id, source_id, facet, value_raw, exact_quote, cycle, version_period, verified, verification_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        f"claim_{uuid.uuid4().hex[:6]}", session_id, src_3_id, "deadline",
        "31st October 2025", "The statewide technology grant portal opens on 31st October 2025 for accredited state institutions.",
        "2025-26", "2025-26", 1, 1.0
    ))

    # Claim C1 (Official) on Amount: Rs. 12,000 (only in official, not in copy or different)
    conn.execute("""
        INSERT INTO claims (id, session_id, source_id, facet, value_raw, exact_quote, cycle, version_period, verified, verification_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        f"claim_{uuid.uuid4().hex[:6]}", session_id, src_1_id, "scholarship_amount",
        "Rs. 12,000", "Selected scholars will receive Rs. 12,000/- per annum disbursed directly via DBT into Aadhaar-seeded accounts.",
        "2025-26", "2025-26", 1, 1.0
    ))
    conn.commit()
    conn.close()

    # ---------------------------------------------------------
    # 6. Run Gap Detection & Check Corroborated vs Single-source
    # ---------------------------------------------------------
    det = run_gap_detection(session_id)
    conf_summary = det["confidence_summary"]
    checklist = det["checklist"]

    print("\nGap Detection Results:")
    print("  Confidence Summary:", conf_summary)

    # 1. Income limit is present in 2 sources (Official & Copy), BUT both belong to original group src_1.
    # Therefore, it MUST NOT be counted as Corroborated! It must count as Single-source!
    assert "Corroborated" not in conf_summary["income_limit"], (
        f"Income limit must NOT be Corroborated across copied sources! Got {conf_summary['income_limit']}"
    )
    assert "single" in conf_summary["income_limit"].lower(), (
        f"Income limit must be marked as single source. Got {conf_summary['income_limit']}"
    )

    # Verify a single-source gap item was produced for income_limit noting copies
    single_copy_gaps = [g for g in checklist if g["facet"] == "income_limit" and g["gap_type"] == "single_source"]
    assert len(single_copy_gaps) >= 1, "Must generate a single_source gap item for income_limit"
    print(f"  ✓ Income Limit (in Official + Copy) correctly flagged as Single-Source: {single_copy_gaps[0]['title']}")
    print(f"    Details: {single_copy_gaps[0]['description']}")

    # 2. Deadline is present in Official (src_1) AND Independent Board Report (src_3).
    # These are 2 DIFFERENT original groups. Therefore, Deadline MUST be Corroborated!
    assert conf_summary["deadline"] == "Corroborated", (
        f"Deadline must be Corroborated across independent sources! Got {conf_summary['deadline']}"
    )
    print("  ✓ Deadline (in Official + Independent Source) correctly recognized as Corroborated!")

    # ---------------------------------------------------------
    # 7. Check Coverage Matrix Status
    # ---------------------------------------------------------
    matrix_data = build_coverage_matrix(session_id)
    rows_by_facet = {r["facet_id"]: r for r in matrix_data["matrix"]}

    # Income Limit row status
    income_row = rows_by_facet["income_limit"]
    print(f"\nCoverage Matrix Row Status for Income Limit: {income_row['status']} ({income_row['status_label']})")
    assert income_row["status"] == "single_source", (
        f"Expected coverage matrix status 'single_source' for Income Limit, got '{income_row['status']}'"
    )

    # Deadline row status
    deadline_row = rows_by_facet["deadline"]
    print(f"Coverage Matrix Row Status for Deadline: {deadline_row['status']} ({deadline_row['status_label']})")
    assert deadline_row["status"] == "corroborated", (
        f"Expected coverage matrix status 'corroborated' for Deadline, got '{deadline_row['status']}'"
    )

    # Matrix Independence payload
    assert matrix_data["independence"]["badge_text"] == "3 sources, 2 originals"
    print("  ✓ Coverage Matrix accurately reflects source independence and copy-aware consensus status.")

    print("\n" + "=" * 65)
    print("🎉 ALL SOURCE INDEPENDENCE & DUPLICATE DETECTION CHECKS PASSED!")
    print("=" * 65)


if __name__ == "__main__":
    run_source_independence_tests()
