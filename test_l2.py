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
from app.normalize import (
    normalize_money, normalize_date, normalize_documents, normalize_cycle, normalize_claim_value
)
from app.fetch import process_pasted_text
from app.extract import extract_claims_for_source, get_template_facets
from app.detect import run_gap_detection


def test_normalizers():
    print("\n--- TEST 1: NORMALIZERS ---")

    # 1. Money
    m1 = normalize_money("Rs. 3,50,000/- per annum")
    m2 = normalize_money("2.5 Lakhs")
    m3 = normalize_money("12,000 per year")
    print(f"✓ Money normalization: 'Rs. 3,50,000/- per annum' -> {m1['amount']}")
    print(f"✓ Money normalization: '2.5 Lakhs' -> {m2['amount']}")
    print(f"✓ Money normalization: '12,000 per year' -> {m3['amount']}")
    assert m1["amount"] == 350000
    assert m2["amount"] == 250000
    assert m3["amount"] == 12000

    # 2. Dates
    d1 = normalize_date("31st October 2025")
    d2 = normalize_date("30-09-2023")
    print(f"✓ Date normalization: '31st October 2025' -> {d1['iso']}")
    print(f"✓ Date normalization: '30-09-2023' -> {d2['iso']}")
    assert d1["iso"] == "2025-10-31"
    assert d2["iso"] == "2023-09-30"

    # 3. Documents
    docs = normalize_documents("Aadhaar Card, Previous Year Marksheet, and Valid Income Certificate issued by Revenue Authority")
    print(f"✓ Document normalization: canonical tokens -> {docs}")
    assert "aadhaar" in docs
    assert "marksheet" in docs
    assert "income_certificate" in docs

    # 4. Cycles
    c1 = normalize_cycle("2025-2026")
    c2 = normalize_cycle("2023-24")
    print(f"✓ Cycle normalization: '2025-2026' -> '{c1}', '2023-24' -> '{c2}'")
    assert c1 == "2025-26"
    assert c2 == "2023-24"


async def test_gap_detection_engine():
    print("\n--- TEST 2: L2 GAP DETECTION & PRIORITIZED CHECKLIST ---")
    init_db()
    conn = get_db_connection()

    session_id = "ses_test_l2"
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
    conn.execute("""
        INSERT INTO research_sessions (id, goal, domain_type, official_domain, facets_json)
        VALUES (?, 'Verify Scholarship Eligibility and Deadlines', 'scholarship', 'scholarships.gov.in', ?)
    """, (session_id, facets_json))

    # Ingest all 3 sample sources:
    # 1. Official Guidelines 2025-26
    # 2. Aggregator Blog 2025 (conflicting income 1.5L, deadline 15 Nov, amount 10000)
    # 3. Outdated Circular 2023-24 (cycle 2023-24, income 2.5L, deadline 30 Sep 2023)
    sample_files = [
        ("sample_sources/scholarship_official_guidelines.txt", "https://scholarships.gov.in/guidelines-2025.html", "official"),
        ("sample_sources/scholarship_aggregator_blog.txt", "https://sarkarihelp-aggregators.com/alert-2025.html", "low"),
        ("sample_sources/scholarship_outdated_circular.txt", "https://scholarships.gov.in/archive/2023.html", "official")
    ]

    source_ids = []
    for fpath, url, auth in sample_files:
        text = Path(fpath).read_text(encoding="utf-8")
        doc = process_pasted_text(text, title=Path(fpath).stem)
        src_id = f"src_{Path(fpath).stem}"
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
    for sid in source_ids:
        await extract_claims_for_source(session_id, sid)

    # Run Gap Detection Engine
    results = run_gap_detection(session_id)
    print(f"\n✓ Gap Detection Finished: Found {results['total_gaps']} Gaps/Dark Spots across sources.")

    # Verify detected gaps
    gap_types = [g["gap_type"] for g in results["gaps"]]
    print(f"  Detected Gap Types: {set(gap_types)}")

    assert "conflict" in gap_types, "Expected conflict gap detected"
    assert "outdated" in gap_types, "Expected outdated cycle gap detected"
    assert "missing" in gap_types, "Expected missing dark spot gap detected"

    # Print conflicts caught
    print("\n[CONFLICTS CAUGHT]")
    for g in results["gaps"]:
        if g["gap_type"] == "conflict":
            print(f"  ⚡ [{g['priority'].upper()}] {g['title']}")
            print(f"     Details: {g['description']}")
            print(f"     Action Needed: {g['action_needed']}")

    # Print outdated cycles caught
    print("\n[OUTDATED INFORMATION CAUGHT]")
    for g in results["gaps"]:
        if g["gap_type"] == "outdated":
            print(f"  ⏳ [{g['priority'].upper()}] {g['title']}")
            print(f"     Details: {g['description']}")

    # Print missing facets (dark spots)
    print("\n[DARK SPOTS (MISSING FACETS)]")
    for g in results["gaps"]:
        if g["gap_type"] == "missing":
            print(f"  🌑 [{g['priority'].upper()}] {g['title']}")
            print(f"     Consequence: {g['consequence']}")

    # Print Prioritized Checklist
    print("\n[PRIORITIZED ACTION CHECKLIST]")
    for idx, item in enumerate(results["checklist"], 1):
        print(f"  {idx}. [{item['priority'].upper()}] {item['title']}")
        print(f"     Action: {item['action_needed']}")

    assert len(results["checklist"]) > 0
    print("\n==================================================")
    print("  ALL L2 DETECTION & CHECKLIST CHECKS PASSED!")
    print("==================================================")


if __name__ == "__main__":
    test_normalizers()
    asyncio.run(test_gap_detection_engine())
