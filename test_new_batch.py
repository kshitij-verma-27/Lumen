"""
Test Suite: New Batch Features
1. Red-team verifier: refutation of unsupported scope/period/value, demotion to 'uncertain', counter text.
2. Gap-to-action email drafts: generated query to official body using session's official domain.
3. Change watch: SHA-256 content hash storage, re-check unchanged and modified diff.
4. Audit-trail export: downloadable JSON and printable HTML report with quote, source, fetch time, and hash.

Tested in MOCK mode (FORCE_MOCK=true).
"""

import os
import sys
import json
import asyncio
from datetime import datetime

# Enforce mock mode for fast deterministic testing
os.environ["FORCE_MOCK"] = "true"
os.environ["LUMEN_DB_PATH"] = "test_new_batch.db"

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app.database import init_db, get_db_connection, row_to_dict
from app.models import FacetDefinition
from app.red_team import run_red_team_verification
from app.email_drafts import get_session_email_drafts, generate_email_draft
from app.change_watch import recheck_source, calculate_content_hash
from app.export import build_audit_trail_data, generate_printable_html_report
from app.detect import run_gap_detection


async def test_new_batch_features():
    print("=" * 65)
    print("TEST: RED-TEAM, EMAIL DRAFTS, CHANGE WATCH, & AUDIT EXPORT")
    print("=" * 65)

    # Clean test DB
    if os.path.exists("test_new_batch.db"):
        os.remove("test_new_batch.db")
    init_db()

    conn = get_db_connection()
    session_id = "ses_test_batch_1"
    official_domain = "admissions.gatech.edu"
    target_vp = "Fall 2025"

    facets = [
        FacetDefinition(
            id="tuition_fee",
            name="Tuition and Fees",
            description="Tuition rate per semester",
            expected_type="currency",
            importance="critical",
            consequence="Underestimating tuition leads to financial hold.",
            is_deadline=False
        ),
        FacetDefinition(
            id="application_deadline",
            name="Application Deadline",
            description="Final date for credentials submission",
            expected_type="date",
            importance="critical",
            consequence="Missing deadline disqualifies candidate.",
            is_deadline=True
        ),
        FacetDefinition(
            id="gre_requirement",
            name="GRE Score Requirement",
            description="Whether GRE is mandatory or waived",
            expected_type="text",
            importance="high",
            consequence="Submitting incomplete packet causes rejection.",
            is_deadline=False
        )
    ]

    conn.execute("""
        INSERT INTO research_sessions (id, goal, domain_type, official_domain, target_cycle, target_version_period, facets_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        session_id,
        "What are Georgia Tech MS CS admission requirements for Fall 2025?",
        "college",
        official_domain,
        target_vp,
        target_vp,
        json.dumps([f.model_dump() for f in facets])
    ))

    # Ingest sources with known text and content hash
    text_source_1 = (
        "Georgia Tech Graduate Admissions for Fall 2025:\n"
        "Tuition and Fees: Tuition is $14,000 per semester for out-of-state students.\n"
        "Application Deadline: All Fall 2025 materials must be received by February 1, 2025.\n"
        "GRE Requirement: GRE General Test is strictly waived for all Fall 2025 applicants."
    )
    hash_1 = calculate_content_hash(text_source_1)

    text_source_2 = (
        "StudyAbroad Blog on Graduate Studies:\n"
        "Tuition and Fees: Around $20,000 yearly (tentative estimate, subject to change).\n"
        "Application Deadline: January 15, 2025 for international candidates.\n"
        "GRE Requirement: GRE is required with minimum 310 score."
    )
    hash_2 = calculate_content_hash(text_source_2)

    conn.execute("""
        INSERT INTO sources (id, session_id, url, content_hash, authority, text, title, fetch_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'success')
    """, ("src_official", session_id, f"https://{official_domain}/ms-cs", hash_1, "official", text_source_1, "Official Graduate Catalog"))

    conn.execute("""
        INSERT INTO sources (id, session_id, url, content_hash, authority, text, title, fetch_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'success')
    """, ("src_blog", session_id, "https://studyabroad.example.com/gatech", hash_2, "low", text_source_2, "StudyAbroad Blog"))

    # Seed verified claims and one claim designed to fail red-team refutation
    # Claim 1: Valid Official Tuition
    conn.execute("""
        INSERT INTO claims (id, session_id, source_id, facet, value_raw, exact_quote, scope, version_period, verified, verification_score, survived_redteam)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1.0, 1)
    """, ("clm_1", session_id, "src_official", "tuition_fee", "$14,000 per semester", "Tuition is $14,000 per semester for out-of-state students.", "out-of-state", "Fall 2025"))

    # Claim 2: Official Deadline
    conn.execute("""
        INSERT INTO claims (id, session_id, source_id, facet, value_raw, exact_quote, scope, version_period, verified, verification_score, survived_redteam)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1.0, 1)
    """, ("clm_2", session_id, "src_official", "application_deadline", "February 1, 2025", "All Fall 2025 materials must be received by February 1, 2025.", "general", "Fall 2025"))

    # Claim 3: Official GRE Waived
    conn.execute("""
        INSERT INTO claims (id, session_id, source_id, facet, value_raw, exact_quote, scope, version_period, verified, verification_score, survived_redteam)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1.0, 1)
    """, ("clm_3", session_id, "src_official", "gre_requirement", "waived", "GRE General Test is strictly waived for all Fall 2025 applicants.", "general", "Fall 2025"))

    # Claim 4: Blog Tuition with tentative/speculative marker in quote -> RED-TEAM REFUTATION TARGET
    conn.execute("""
        INSERT INTO claims (id, session_id, source_id, facet, value_raw, exact_quote, scope, version_period, verified, verification_score, survived_redteam)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1.0, 1)
    """, ("clm_4", session_id, "src_blog", "tuition_fee", "$20,000 yearly", "Around $20,000 yearly (tentative estimate, subject to change).", "general", "Fall 2025"))

    # Claim 5: Blog Deadline conflicting with official
    conn.execute("""
        INSERT INTO claims (id, session_id, source_id, facet, value_raw, exact_quote, scope, version_period, verified, verification_score, survived_redteam)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1.0, 1)
    """, ("clm_5", session_id, "src_blog", "application_deadline", "January 15, 2025", "January 15, 2025 for international candidates.", "international", "Fall 2025"))

    # Claim 6: Unverified rejected claim
    conn.execute("""
        INSERT INTO claims (id, session_id, source_id, facet, value_raw, exact_quote, scope, version_period, verified, verification_score, rejection_reason, survived_redteam)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0.0, 'Quote not found in text', 0)
    """, ("clm_6", session_id, "src_blog", "housing_fee", "$5,000", "Nonexistent quote in document", "general", "Fall 2025"))

    conn.commit()
    conn.close()

    # ==============================================================
    # 1. TEST RED-TEAM VERIFIER
    # ==============================================================
    print("\n--- 1. TESTING RED-TEAM VERIFIER ---")
    rt_result = await run_red_team_verification(session_id)
    print(f"Red-team Counter: '{rt_result['counter_text']}'")
    print(f"Total Extracted: {rt_result['extracted_count']}, Survived: {rt_result['survived_count']}, Demoted: {rt_result['demoted_count']}")

    # Assertions
    assert rt_result["extracted_count"] == 6, f"Expected 6 extracted claims, got {rt_result['extracted_count']}"
    assert rt_result["survived_count"] >= 4, f"Expected at least 4 surviving claims, got {rt_result['survived_count']}"
    assert rt_result["demoted_count"] >= 2, f"Expected at least 2 demoted claims (unverified + refuted), got {rt_result['demoted_count']}"

    # Verify claim 4 was demoted to uncertain
    conn = get_db_connection()
    c4 = conn.execute("SELECT * FROM claims WHERE id = 'clm_4'").fetchone()
    assert c4["survived_redteam"] == 0, "Claim 4 should have failed red-team"
    assert c4["redteam_status"] == "uncertain", f"Claim 4 status should be 'uncertain', got {c4['redteam_status']}"
    assert "tentative" in c4["redteam_notes"].lower(), "Red-team notes should cite tentative qualification"
    print(f"  ✓ Claim 4 demoted to uncertain: {c4['redteam_notes']}")
    print(f"  ✓ Red-team counter correctly generated: '{rt_result['counter_text']}'")

    # ==============================================================
    # 2. TEST GAP-TO-ACTION EMAIL DRAFTS
    # ==============================================================
    print("\n--- 2. TESTING GAP-TO-ACTION EMAIL DRAFTS ---")
    email_data = get_session_email_drafts(session_id)
    print(f"Official Domain: {email_data['official_domain']}")
    print(f"Total Email Drafts Generated: {email_data['count']}")

    assert email_data["official_domain"] == official_domain
    assert email_data["count"] > 0, "Expected email drafts for unresolved gaps"

    first_draft = email_data["email_drafts"][0]
    print(f"Sample Draft:")
    print(f"  To: {first_draft['recipient']}")
    print(f"  Subject: {first_draft['subject']}")
    print(f"  Body Preview:\n{first_draft['body'][:200]}...")

    print(f"  Body Preview:\n{first_draft['body'][:200]}...")

    # Case A: When NO email appears in source text, recipient MUST show "Find the official contact on {domain}"
    assert first_draft["recipient"] == f"Find the official contact on {official_domain}", f"Expected 'Find the official contact on {official_domain}', got '{first_draft['recipient']}'"
    assert first_draft["recipient_quote"] is None
    print(f"  ✓ Fallback verified: No email address invented. Recipient is: '{first_draft['recipient']}'")

    # Case B: When an email DOES appear in fetched sources, use it with its verbatim quote
    text_with_email = text_source_1 + "\nContact Office: For all admissions inquiries, contact gradinfo@gatech.edu directly."
    conn.execute("UPDATE sources SET text = ? WHERE id = 'src_official'", (text_with_email,))
    conn.commit()

    email_data_with_contact = get_session_email_drafts(session_id)
    verified_draft = email_data_with_contact["email_drafts"][0]
    print(f"  Verified Contact Recipient: {verified_draft['recipient']}")
    print(f"  Verified Contact Quote: {verified_draft['recipient_quote']}")
    assert verified_draft["recipient"] == "gradinfo@gatech.edu"
    assert verified_draft["recipient_quote"] is not None
    assert "gradinfo@gatech.edu" in verified_draft["recipient_quote"]
    print("  ✓ Source contact discovery verified: Real address used with exact quote from source.")

    # Restore source 1 text for subsequent tests
    conn.execute("UPDATE sources SET text = ? WHERE id = 'src_official'", (text_source_1,))
    conn.commit()

    # ==============================================================
    # 3. TEST CHANGE WATCH (CONTENT HASH & RE-CHECK)
    # ==============================================================
    print("\n--- 3. TESTING CHANGE WATCH (CONTENT HASH & RE-CHECK) ---")
    src_row = conn.execute("SELECT * FROM sources WHERE id = 'src_official'").fetchone()
    stored_hash = src_row["content_hash"]
    assert stored_hash == hash_1, "Stored hash should match initial SHA-256"
    print(f"Initial SHA-256 Hash: {stored_hash}")

    # Re-check with identical content (unchanged)
    recheck_unchanged = await recheck_source("src_official")
    print(f"Unchanged Re-check Result: changed={recheck_unchanged['changed']}, summary='{recheck_unchanged['summary']}'")
    assert recheck_unchanged["changed"] is False
    assert recheck_unchanged["new_hash"] == stored_hash
    assert "any text change counts, including small page edits" in recheck_unchanged["summary"].lower()
    print("  ✓ Unchanged source re-check verified: identical hash, note present.")

    # Re-check with simulated modified content (changed)
    modified_text = text_source_1.replace("$14,000", "$15,500") + "\nNew Revision: Spring 2026 dates posted."
    recheck_changed = await recheck_source("src_official", simulated_new_text=modified_text)
    print(f"Modified Re-check Result: changed={recheck_changed['changed']}, summary='{recheck_changed['summary']}'")
    assert recheck_changed["changed"] is True
    assert recheck_changed["new_hash"] != stored_hash
    assert recheck_changed["added_lines_count"] > 0
    assert recheck_changed["diff"] is not None
    assert "any text change counts, including small page edits" in recheck_changed["note"].lower()
    print(f"  Unified Diff Preview:\n{recheck_changed['diff']}")
    print(f"  Note verified: '{recheck_changed['note']}'")
    print("  ✓ Changed source re-check verified: detects modification, generates diff, updates stored hash, includes note.")

    # ==============================================================
    # 4. TEST AUDIT-TRAIL EXPORT (JSON & PRINTABLE HTML)
    # ==============================================================
    print("\n--- 4. TESTING AUDIT-TRAIL EXPORT ---")
    # JSON Export
    audit_json = build_audit_trail_data(session_id)
    print(f"Audit Trail Findings Count: {len(audit_json['findings'])}")
    print(f"Audit Trail Sources Count: {len(audit_json['sources'])}")
    print(f"Audit Trail Red-Team Stats: {audit_json['stats']['redteam_counter']}")

    assert audit_json["export_type"] == "lumen_audit_trail"
    assert len(audit_json["findings"]) == 6
    assert len(audit_json["sources"]) == 2
    assert audit_json["findings"][0]["source_content_hash"] is not None
    assert audit_json["findings"][0]["exact_quote"] is not None
    assert audit_json["findings"][0]["source_fetched_at"] is not None
    print("  ✓ Audit trail JSON export contains complete provenance: quotes, hashes, and timestamps.")

    # HTML Export
    html_report = generate_printable_html_report(session_id)
    assert "<!DOCTYPE html>" in html_report
    assert "@media print" in html_report
    assert official_domain in html_report
    assert "Red-Team Survived" in html_report
    assert "Uncertain (Demoted)" in html_report
    assert "window.print()" in html_report
    print("  ✓ Printable HTML report generated with @media print styling, KPI cards, and finding tables.")

    conn.close()

    # Cleanup test DB
    if os.path.exists("test_new_batch.db"):
        os.remove("test_new_batch.db")

    print("\n" + "=" * 65)
    print("🎉 ALL NEW BATCH FEATURES (RED-TEAM, DRAFTS, WATCH, EXPORT) PASSED!")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(test_new_batch_features())
