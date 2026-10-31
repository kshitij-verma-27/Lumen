import asyncio
import os
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Ensure UTF-8 output on Windows console
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


from app.database import init_db, get_db_connection
from app.trust import classify_authority, verify_claim_in_source
from app.fetch import process_pasted_text
from app.extract import extract_claims_for_source, get_template_facets


async def run_l1_tests():
    print("==================================================")
    print("  RUNNING L1 CORE VERIFICATION SUITE")
    print("==================================================")

    # 1. DB Init
    init_db()
    conn = get_db_connection()
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
    print(f"✓ SQLite Tables Initialized: {tables}")
    assert "research_sessions" in tables
    assert "sources" in tables
    assert "claims" in tables
    assert "cache" in tables

    # 2. Test Authority Classification
    auth_gov = classify_authority("https://scholarships.gov.in/guidelines", official_domain="scholarships.gov.in")
    auth_blog = classify_authority("https://sarkarihelp-aggregators.com/alert", official_domain="scholarships.gov.in")
    auth_news = classify_authority("https://thehindu.com/education/news", official_domain="scholarships.gov.in")

    print(f"✓ Authority scoring test: scholarships.gov.in -> {auth_gov} (expected: official)")
    print(f"✓ Authority scoring test: sarkarihelp.com -> {auth_blog} (expected: low)")
    print(f"✓ Authority scoring test: thehindu.com -> {auth_news} (expected: secondary)")
    assert auth_gov == "official"
    assert auth_blog == "low"
    assert auth_news == "secondary"

    # 3. Test Deterministic Verification Rules in trust.py
    sample_text = (
        "The annual income of the parents from all sources should not exceed Rs. 3,50,000/- per annum. "
        "The closing date for submission of online application is 31st October 2025."
    )

    # 3a. Legitimate Claim (Exact match)
    v1 = verify_claim_in_source(
        source_text=sample_text,
        exact_quote="The annual income of the parents from all sources should not exceed Rs. 3,50,000/- per annum.",
        value_raw="Rs. 3,50,000"
    )
    print(f"\n[Test 3a: Valid Quote & Value]")
    print(f"  Verified: {v1['verified']}, Score: {v1['verification_score']}, Reason: {v1['rejection_reason']}")
    assert v1["verified"] is True
    assert v1["verification_score"] == 1.0

    # 3b. Quote too short (< 15 chars)
    v2 = verify_claim_in_source(
        source_text=sample_text,
        exact_quote="Rs. 3,50,000",
        value_raw="350000"
    )
    print(f"\n[Test 3b: Quote Too Short]")
    print(f"  Verified: {v2['verified']}, Reason: {v2['rejection_reason']}")
    assert v2["verified"] is False
    assert "Quote too short" in v2["rejection_reason"]

    # 3c. Hallucinated Quote (not in text)
    v3 = verify_claim_in_source(
        source_text=sample_text,
        exact_quote="There is a special bonus stipend of Rs 50,000 for all first year applicants.",
        value_raw="Rs 50,000"
    )
    print(f"\n[Test 3c: Hallucinated Quote Not In Text]")
    print(f"  Verified: {v3['verified']}, Reason: {v3['rejection_reason']}")
    assert v3["verified"] is False
    assert "not found in source text" in v3["rejection_reason"]

    # 3d. Adversarial Case: Value digits mismatch in matched span
    v4 = verify_claim_in_source(
        source_text=sample_text,
        exact_quote="The annual income of the parents from all sources should not exceed Rs. 3,50,000/- per annum.",
        value_raw="Rs. 1,50,000"
    )
    print(f"\n[Test 3d: Adversarial - Value Digits Mismatch (3.5L -> 1.5L)]")
    print(f"  Verified: {v4['verified']}, Reason: {v4['rejection_reason']}")
    assert v4["verified"] is False
    assert "Value digits" in v4["rejection_reason"]

    # 3e. Adversarial Case: Changed Amount (12,000 -> 25,000)
    sample_text_benefit = "The amount of scholarship is Rs. 12,000/- per annum disbursed directly into bank accounts."
    v5 = verify_claim_in_source(
        source_text=sample_text_benefit,
        exact_quote="The amount of scholarship is Rs. 12,000/- per annum disbursed directly into bank accounts.",
        value_raw="Rs. 25,000 per annum"
    )
    print(f"\n[Test 3e: Adversarial - Changed Amount (Rs. 12,000 -> Rs. 25,000)]")
    print(f"  Verified: {v5['verified']}, Reason: {v5['rejection_reason']}")
    assert v5["verified"] is False
    assert "Value digits" in v5["rejection_reason"] or "digits" in v5["rejection_reason"]

    # 3f. Adversarial Case: Changed Year (2025 -> 2027)
    sample_text_date = "The closing date for submission of online application is 31st October 2025."
    v6 = verify_claim_in_source(
        source_text=sample_text_date,
        exact_quote="The closing date for submission of online application is 31st October 2025.",
        value_raw="31st October 2027"
    )
    print(f"\n[Test 3f: Adversarial - Changed Year (2025 -> 2027)]")
    print(f"  Verified: {v6['verified']}, Reason: {v6['rejection_reason']}")
    assert v6["verified"] is False
    assert "Value digits" in v6["rejection_reason"]

    # 3g. Adversarial Case: Quote from the Wrong Source
    blog_quote = "Parents annual income must not exceed Rs. 1,50,000 per year from all sources."
    v7 = verify_claim_in_source(
        source_text=sample_text,  # official text that does not have this blog quote
        exact_quote=blog_quote,
        value_raw="Rs. 1,50,000"
    )
    print(f"\n[Test 3g: Adversarial - Quote From Wrong Source Document]")
    print(f"  Verified: {v7['verified']}, Reason: {v7['rejection_reason']}")
    assert v7["verified"] is False
    assert "not found in source text" in v7["rejection_reason"]


    # 4. End-to-End Extraction Flow
    session_id = "ses_test_l1"
    import json
    facets_json = json.dumps([f.model_dump() for f in get_template_facets("scholarship")])
    conn.execute("DELETE FROM research_sessions WHERE id = ?", (session_id,))
    conn.execute("""
        INSERT INTO research_sessions (id, goal, domain_type, official_domain, facets_json)
        VALUES (?, 'Test Scholarship Verification', 'scholarship', 'scholarships.gov.in', ?)
    """, (session_id, facets_json))

    # Load official sample text
    sample_file = Path("sample_sources/scholarship_official_guidelines.txt")
    official_text = sample_file.read_text(encoding="utf-8")
    doc = process_pasted_text(official_text, title="Official Guidelines 2025-26")

    src_id = "src_test_official"
    conn.execute("DELETE FROM sources WHERE id = ?", (src_id,))
    conn.execute("""
        INSERT INTO sources (id, session_id, url, content_hash, published_date, published_date_origin, authority, original_group_id, text, title, fetch_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        src_id, session_id, "https://scholarships.gov.in/guidelines-2025.html",
        doc["content_hash"], doc["published_date"], doc["published_date_origin"],
        "official", src_id, doc["text"], doc["title"], "pasted"
    ))
    conn.commit()
    conn.close()

    print(f"\n[Test 4: Running Extraction & Code Verification on Source]")
    claims = await extract_claims_for_source(session_id, src_id)
    print(f"  Extracted {len(claims)} total claims.")
    for c in claims:
        status_sym = "✓" if c["verified"] else "✗"
        print(f"  [{status_sym}] Facet: {c['facet']:<22} | Value: {c['value_raw']:<20} | Verified: {c['verified']}")
        if not c["verified"]:
            print(f"      Rejection Reason: {c['rejection_reason']}")

    verified_claims = [c for c in claims if c["verified"]]
    assert len(verified_claims) >= 3, "Expected at least 3 verified claims extracted from official guidelines"
    print("\n==================================================")
    print("  ALL L1 CORE VERIFICATION CHECKS PASSED SUCCESSFULLY!")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(run_l1_tests())
