import asyncio
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

os.environ["FORCE_MOCK"] = "true"
os.environ["DARKSPOT_DB"] = "test_darkspot.db"

from app.database import init_db, get_db_connection
from app.registry import (
    seed_registry_from_yaml,
    get_all_registry_sources,
    get_registry_source_by_id,
    find_registry_match_by_url,
    add_registry_source,
    update_registry_source,
)
from app.ingest.ssrf import is_url_safe, is_ip_blocked
from app.ingest.politeness import HostRateLimiter, RobotsCache
from app.ingest.connectors import (
    process_pasted_text,
    compute_hash,
    Document,
)
from app.validation.lookalike import detect_lookalike, normalize_domain_homoglyphs
from app.validation.scam_detect import detect_scam_signals
from app.validation.quality import assess_content_quality
from app.validation.red_team_pass import red_team_source_check
from app.validation.validator import validate_source
from app.seed_validator import audit_all_seeds


async def run_phase1_tests():
    print("==================================================")
    print("  RUNNING PHASE 1 TEST SUITE (MOCK MODE)")
    print("==================================================")

    # ----------------------------------------------------
    # TEST 1: Skills Files Verification (< 60 lines each)
    # ----------------------------------------------------
    print("\n[Test 1] Skills Files Check")
    skill_names = [
        "ui-design-system",
        "frontend-architecture",
        "ux-and-accessibility",
        "responsive-qa",
        "ingestion-architecture",
        "source-validation-agent",
        "data-modeling",
        "testing-and-verification",
        "security-and-privacy",
    ]
    for s_name in skill_names:
        p1 = Path(f".agents/skills/{s_name}/SKILL.md")
        p2 = Path(f"docs/skills/{s_name}.md")
        assert p1.exists(), f"Missing {p1}"
        assert p2.exists(), f"Missing {p2}"

        with open(p1, "r", encoding="utf-8") as f:
            lines = f.readlines()
            line_count = len(lines)
            assert line_count <= 60, f"Skill {p1} exceeds 60 lines ({line_count} lines)"

        print(f"  [OK] Skill '{s_name}' exists and is {line_count} lines (<= 60)")

    # ----------------------------------------------------
    # TEST 2: Database Schema & Migration
    # ----------------------------------------------------
    print("\n[Test 2] Database Tables Check")
    init_db()
    conn = get_db_connection()
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
    conn.close()

    required_tables = [
        "research_sessions", "sources", "claims", "cache",
        "registry_sources", "crawl_jobs", "entities", "entity_attributes", "entity_sources"
    ]
    for req in required_tables:
        assert req in tables, f"Missing table {req} in SQLite schema"
    print(f"  [OK] All required SQLite tables verified: {len(required_tables)} tables present")

    # ----------------------------------------------------
    # TEST 3: Registry Seeding & Operations
    # ----------------------------------------------------
    print("\n[Test 3] Registry Seeding & Querying")
    seeded_count = seed_registry_from_yaml(force=True)
    assert seeded_count >= 25, f"Expected at least 25 seed sources, got {seeded_count}"

    sources = get_all_registry_sources()
    assert len(sources) >= seeded_count

    # Verify all 5 domain categories are represented
    categories = {s["domain_category"] for s in sources}
    expected_categories = {"education", "career", "public_services", "research", "business"}
    assert expected_categories.issubset(categories), f"Missing categories: {expected_categories - categories}"

    # Test find by URL
    matched = find_registry_match_by_url("https://scholarships.gov.in/scheme/details")
    assert matched is not None, "Failed to match scholarships.gov.in in registry"
    assert matched["id"] == "edu_nsp"

    # Test add custom source
    custom_src = add_registry_source({
        "id": "custom_test_portal",
        "name": "State Skill Council",
        "domain_category": "career",
        "subcategory": "skill_certifications",
        "base_url": "https://skill.state.gov.in",
        "type": "official",
        "trust_score": 90,
        "trust_reasons": ["State government skill mission"],
    })
    assert custom_src["id"] == "custom_test_portal"
    found_custom = get_registry_source_by_id("custom_test_portal")
    assert found_custom is not None
    assert found_custom["name"] == "State Skill Council"
    print(f"  [OK] Registry seeded {seeded_count} sources across 5 domains; custom source added & queried")

    # ----------------------------------------------------
    # TEST 4: SSRF Security Guard
    # ----------------------------------------------------
    print("\n[Test 4] SSRF Security Protection Guard")
    ssrf_tests = [
        ("http://localhost:8000/api", False),
        ("http://127.0.0.1:5000", False),
        ("http://169.254.169.254/latest/meta-data/", False),
        ("http://10.0.1.25/internal", False),
        ("http://192.168.0.1/admin", False),
        ("http://172.16.5.10/", False),
        ("file:///C:/Windows/win.ini", False),
        ("gopher://127.0.0.1:6379", False),
        ("https://www.google.com", True),
        ("https://scholarships.gov.in", True),
    ]
    for url, should_pass in ssrf_tests:
        safe, reason = is_url_safe(url)
        assert safe == should_pass, f"SSRF test failed for {url}: expected {should_pass}, got {safe} ({reason})"
    print("  [OK] All 10 SSRF attack vectors correctly identified and blocked")

    # ----------------------------------------------------
    # TEST 5: Politeness Layer (Rate Limiter & Robots Cache)
    # ----------------------------------------------------
    print("\n[Test 5] Politeness & Rate Limiter")
    limiter = HostRateLimiter(min_delay=0.1)
    # In mock mode, throttle immediately succeeds
    wait1 = await limiter.throttle("https://example.com/page1")
    assert wait1 == 0.0

    robots = RobotsCache()
    can_crawl, delay, r_status = await robots.can_fetch("https://example.com/test")
    assert can_crawl is True
    print("  [OK] Rate limiter and Robots.txt cache successfully tested")

    # ----------------------------------------------------
    # TEST 6: Connectors & Pasted Document
    # ----------------------------------------------------
    print("\n[Test 6] Connectors & Pasted Document Normalization")
    test_text = "Important notification: Application submission deadline is 25th November 2025. Fee is Rs. 100."
    pasted_doc = process_pasted_text(test_text, custom_title="Exam Notice")
    assert isinstance(pasted_doc, Document)
    assert pasted_doc.status == "ok"
    assert pasted_doc.title == "Exam Notice"
    assert pasted_doc.published_date == "2025-11-25"
    assert pasted_doc.content_hash == compute_hash(test_text)
    print("  [OK] Pasted text adapter created normalized Document with SHA-256 and parsed date")

    # ----------------------------------------------------
    # TEST 7: Adversarial Case A - Lookalike Domain
    # ----------------------------------------------------
    print("\n[Test 7] Adversarial Case: Lookalike Domain Detection")
    lookalike_cases = [
        ("https://scholarships-gov.in/apply", True, "scholarships.gov.in"),
        ("https://scholarshipsgov.in", True, "scholarships.gov.in"),
        ("https://udyamregistration.com/fee", True, "udyamregistration.gov.in"),
        ("https://nta-exam.in", True, "nta.ac.in"),
        ("https://upsc.gov.in", False, None),  # Genuine official
    ]
    for url, expected_lookalike, target in lookalike_cases:
        is_look, matched, score, reasons = detect_lookalike(url)
        assert is_look == expected_lookalike, f"Lookalike mismatch for {url}: expected {expected_lookalike}, got {is_look}"
        if expected_lookalike:
            assert matched == target, f"Expected target {target}, got {matched}"
    print("  [OK] Lookalike typosquats, hyphen affixes, and commercial lookalikes flagged")

    # ----------------------------------------------------
    # TEST 8: Adversarial Case B - Scam Signals & Fee for Free Scheme
    # ----------------------------------------------------
    print("\n[Test 8] Adversarial Case: Scam Signals & Fee-for-Free Scheme")
    scam_text_fee = (
        "Welcome to Udyam Registration Portal. Fill your MSME application here. "
        "Pay registration fee of Rs 850 for immediate certificate issuance."
    )
    is_scam, scam_reasons, penalty = detect_scam_signals("https://udyam-portal.org", scam_text_fee)
    assert is_scam is True
    assert penalty >= 40
    assert any("Fee Scam" in r for r in scam_reasons)

    scam_text_guarantee = "Guaranteed job without any exam. Act immediately, offer expires today! Only 5 seats left."
    is_scam2, scam_reasons2, penalty2 = detect_scam_signals("https://fast-job-alert.net", scam_text_guarantee)
    assert is_scam2 is True
    assert any("Unrealistic guarantee" in r for r in scam_reasons2)
    print("  [OK] Fee-for-free scam and urgency/guarantee signals flagged with high penalty")

    # Negative scam tests: legitimate sources must NOT be flagged suspicious
    c1 = validate_source(
        "https://upsc.gov.in/examinations/civil-services-2026",
        title="UPSC Civil Services Examination",
        text="Union Public Service Commission. Civil Services Examination. Candidates are required to pay a fee of Rs. 100 either by remitting money in any Branch of SBI or by online net banking. SC/ST/Female candidates are exempted from payment of fee.",
        published_date="2026-02-01"
    )
    assert c1["trust_level"] == "official", f"Expected official for UPSC exam fee, got {c1['trust_level']}"
    assert c1["trust_level"] != "suspicious"

    c2 = validate_source(
        "https://scholarships.gov.in/guidelines-2026",
        title="NSP Central Sector Scholarship",
        text="National Scholarship Portal. Ministry of Education. Central Sector Scheme. The last date and application deadline for submission is 31st October 2026. Eligible students can apply online.",
        published_date="2026-01-10"
    )
    assert c2["trust_level"] == "official", f"Expected official for scholarship deadline, got {c2['trust_level']}"
    assert c2["trust_level"] != "suspicious"

    c3 = validate_source(
        "https://www.thehindu.com/news/national/centre-announces-pm-surya-ghar-scheme/article6789.ece",
        title="Centre announces PM Surya Ghar solar rooftop scheme",
        text="The Hindu. The Union Cabinet chaired by the Prime Minister has approved the PM Surya Ghar Muft Bijli Yojana with a total outlay of Rs 75,021 crore to provide free electricity up to 300 units monthly for one crore households. For details contact info@thehindu.co.in or visit pmsuryaghar.gov.in.",
        published_date="2026-02-15"
    )
    assert c3["trust_level"] in ("secondary", "community")
    assert c3["trust_level"] != "suspicious", f"Expected secondary for news article, got {c3['trust_level']}"
    print("  [OK] Negative scam tests passed: legitimate exam fee, scholarship deadline, and news article NOT flagged suspicious")

    # ----------------------------------------------------
    # TEST 9: Adversarial Case C - Copied Blog & Red-Team Refutation
    # ----------------------------------------------------
    print("\n[Test 9] Adversarial Case: Copied Blog & Red-Team Refutation")
    blog_text = (
        "Collected from various websites. We do not take responsibility for exam schedule accuracy. "
        "Readers are advised to check official website."
    )
    survived, objections = red_team_source_check(
        "https://sarkari-blog-daily.com", "Sarkari Blog", blog_text, "official", []
    )
    assert survived is False
    assert len(objections) > 0
    print(f"  [OK] Red-team refutation successfully caught copied blog claim: '{objections[0]}'")

    # ----------------------------------------------------
    # TEST 10: Adversarial Case D - Expired Stale Content
    # ----------------------------------------------------
    print("\n[Test 10] Adversarial Case: Expired / Stale Content")
    stale_text = "Important guidelines for 2021 admissions. " * 30
    q_score, q_reasons, q_checks = assess_content_quality(
        "https://university-updates.org", stale_text, published_date="2021-05-15"
    )
    assert any("over 2 years old" in r for r in q_reasons)
    print("  [OK] Content over 2 years old received staleness penalty and warning")

    # ----------------------------------------------------
    # TEST 11: End-to-End Validation Agent & Rubric
    # ----------------------------------------------------
    print("\n[Test 11] End-to-End Source Validation Agent Rubric")

    # 1. Official Source Test
    val_official = validate_source(
        "https://scholarships.gov.in",
        title="National Scholarship Portal",
        text="Ministry of Electronics and Information Technology. Central schemes. Contact: helpdesk@nsp.gov.in, 011-23381234. Full guidelines " * 10,
        published_date="2026-01-15",
    )
    assert val_official["trust_level"] == "official"
    assert val_official["score"] >= 85
    assert len(val_official["reasons"]) <= 3
    print(f"  [OK] Official source -> trust_level={val_official['trust_level']}, score={val_official['score']}, top reasons={val_official['reasons']}")

    # 2. Lookalike Attack Test
    val_lookalike = validate_source("https://scholarships-gov.in/apply")
    assert val_lookalike["trust_level"] == "suspicious"
    assert val_lookalike["score"] <= 15
    print(f"  [OK] Lookalike domain -> trust_level={val_lookalike['trust_level']}, score={val_lookalike['score']}")

    # 3. Fee Scam on Free Scheme Test
    val_scam = validate_source(
        "https://udyam-online-reg.net/apply",
        text="Udyam registration for small businesses. Processing fee of Rs 499 must be paid online."
    )
    assert val_scam["trust_level"] == "suspicious"
    print(f"  [OK] Fee scam portal -> trust_level={val_scam['trust_level']}, score={val_scam['score']}")

    # 4. Manual Override Test
    val_override = validate_source(
        "https://community-group.org",
        manual_override={"trust_level": "official", "note": "Verified state nodal partner"}
    )
    assert val_override["trust_level"] == "official"
    assert "Manual override applied" in val_override["reasons"][0]
    print(f"  [OK] Manual override honored -> trust_level={val_override['trust_level']}, reason={val_override['reasons'][0]}")

    # ----------------------------------------------------
    # TEST 12: Seed Registry Audit Report
    # ----------------------------------------------------
    print("\n[Test 12] Seed Registry Audit Execution")
    audit_results = await audit_all_seeds(force_mock=True)
    assert len(audit_results) >= 29

    reachable = [r for r in audit_results if r["reachability"] == "reachable"]
    needs_js = [r for r in audit_results if r["reachability"] == "needs_js"]
    blocked = [r for r in audit_results if r["reachability"] == "blocked"]

    assert len(reachable) >= 15
    assert len(needs_js) >= 5
    assert len(blocked) >= 2
    print(f"  [OK] Seed audit complete: 29 audited | {len(reachable)} reachable | {len(needs_js)} need JS | {len(blocked)} blocked")

    print("\n==================================================")
    print("  ALL PHASE 1 CHECKS PASSED SUCCESSFULLY!")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(run_phase1_tests())
