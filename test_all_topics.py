import sys
import asyncio
import json
from pathlib import Path

# Configure utf-8 stdout for Windows console
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app.database import init_db, get_db_connection
from app.models import FacetDefinition, ResearchSessionCreate, SourcesAddRequest, SourceInput
from app.llm import generate_facets_from_goal
from app.extract import extract_claims_for_source, get_template_facets
from app.detect import run_gap_detection, build_coverage_matrix
from app.normalize import normalize_currency, normalize_unit_value, normalize_percentage, normalize_version_period, normalize_list, normalize_date

init_db()

async def test_normalizers():
    print("=" * 70)
    print("STEP 0: TESTING GENERALIZED NORMALIZERS ACROSS ALL UNITS & CURRENCIES")
    print("=" * 70)

    # 1. Currency
    usd = normalize_currency("$2,299 USD")
    eur = normalize_currency("€1,450 / month")
    gbp = normalize_currency("£35,000 per year")
    inr = normalize_currency("₹78,000")
    lakh = normalize_currency("Rs. 2.5 Lakhs")
    credit = normalize_currency("$1,550 per credit hour")

    assert usd["amount"] == 2299.0 and usd["currency"] == "USD", f"USD failed: {usd}"
    assert eur["amount"] == 1450.0 and eur["currency"] == "EUR" and eur["period"] == "monthly", f"EUR failed: {eur}"
    assert gbp["amount"] == 35000.0 and gbp["currency"] == "GBP" and gbp["period"] == "annual", f"GBP failed: {gbp}"
    assert inr["amount"] == 78000.0 and inr["currency"] == "INR", f"INR failed: {inr}"
    assert lakh["amount"] == 250000.0 and lakh["currency"] == "INR", f"Lakh failed: {lakh}"
    assert credit["amount"] == 1550.0 and credit["period"] == "per credit", f"Credit failed: {credit}"
    print("  ✓ Multi-Currency ($ USD, € EUR, £ GBP, ₹ INR, Lakhs, per credit) normalized correctly.")

    # 2. Physical & Technical Units
    tgp = normalize_unit_value("175W TGP")
    tgp2 = normalize_unit_value("140 Watts")
    ram = normalize_unit_value("32GB DDR5")
    freq = normalize_unit_value("240 Hz")
    solar_kw = normalize_unit_value("3 kW rooftop")

    assert tgp["value"] == 175.0 and tgp["unit"] == "W", f"TGP failed: {tgp}"
    assert tgp2["value"] == 140.0 and tgp2["unit"] == "W", f"TGP2 failed: {tgp2}"
    assert ram["value"] == 32.0 and ram["unit"] == "GB", f"RAM failed: {ram}"
    assert freq["value"] == 240.0 and freq["unit"] == "Hz", f"Hz failed: {freq}"
    assert solar_kw["value"] == 3.0 and solar_kw["unit"] == "kW", f"kW failed: {solar_kw}"
    print("  ✓ Technical Units (Watts, GB, Hz, kW) normalized correctly.")

    # 3. Percentages
    pct1 = normalize_percentage("80% minimum marks")
    pct2 = normalize_percentage("acceptance rate 12.5 percent")
    assert pct1["percentage"] == 80.0, f"Pct1 failed: {pct1}"
    assert pct2["percentage"] == 12.5, f"Pct2 failed: {pct2}"
    # 3.5 Dates vs Policy Durations
    d_exact = normalize_date("15th December 2024")
    assert d_exact is not None and d_exact["iso"] == "2024-12-15", f"Date failed: {d_exact}"
    assert normalize_date("30 days") is None, "30 days duration must not be parsed as a calendar date"
    assert normalize_date("return window") is None, "return window must not be parsed as a calendar date"
    assert normalize_date("within 14 days") is None, "within 14 days must not be parsed as a calendar date"
    print("  ✓ Calendar Dates parsed & Policy Durations (30 days, return window) correctly rejected.")

    # 4. Version / Period
    vp_cycle = normalize_version_period("2025-26")
    vp_term = normalize_version_period("Fall 2025")
    vp_gen = normalize_version_period("Lenovo Legion Gen 7")
    vp_year = normalize_version_period("Model Year 2024")
    assert vp_cycle == "2025-26", f"Cycle failed: {vp_cycle}"
    assert vp_term == "Fall 2025", f"Term failed: {vp_term}"
    assert vp_gen == "Gen 7", f"Gen failed: {vp_gen}"
    assert vp_year == "2024", f"Year failed: {vp_year}"
    print("  ✓ Version / Period (Cycles, Semesters, Hardware Gens) normalized correctly.")

    # 5. Lists & Overlaps
    lst_a = normalize_list("Transcripts, 3 Letters of Recommendation, Statement of Purpose")
    lst_b = normalize_list("Transcripts, Letters of Recommendation, Statement of Purpose, Resume, Portfolio")
    set_a = set(lst_a)
    set_b = set(lst_b)
    assert "transcripts" in set_a and "letters_of_recommendation" in set_a
    assert set_a < set_b, "set_a should be subset of set_b"
    extra = set_b - set_a
    assert "resume" in extra and "portfolio" in extra
    print("  ✓ List Normalization & Subset/Superset identification working.")
    print()


async def test_topic_laptop():
    print("=" * 70)
    print("TEST 1: LAPTOP PURCHASE TOPIC")
    print("=" * 70)

    goal = "Which high-performance laptop should I buy for AI engineering and 3D rendering under $2,500?"
    official_domain = "lenovo.com"
    print(f"Goal: {goal}")
    print(f"Official Domain: {official_domain}")

    # 1. Generate facets from question using LLM
    gen_result = await generate_facets_from_goal(goal, "laptop")
    facets = [FacetDefinition(**f) for f in gen_result["facets"]]
    print(f"\nGenerated {len(facets)} Facets from User Question:")
    for f in facets:
        print(f"  • [{f.importance.upper()}] {f.name} ({f.expected_type}): {f.consequence}")

    # Validate generated facet schema
    assert len(facets) >= 5, "At least 5 facets must be generated"
    assert any(f.importance in ("critical", "high") for f in facets), "Importance levels must be set"
    assert all(f.consequence and len(f.consequence) > 10 for f in facets), "One-line consequences must be present on every facet"
    assert any(any(k in f.id.lower() or k in f.name.lower() for k in ("tgp", "gpu", "vram", "graphics")) for f in facets), "GPU/graphics facet generated"
    assert any(any(k in f.id.lower() or k in f.name.lower() for k in ("price", "cost", "budget")) for f in facets), "Price facet generated"
    print("  ✓ Dynamic LLM facet generation validated with importance and consequences.")

    # 2. User reviews and edits/confirms facets before analysis
    confirmed_facets = get_template_facets("laptop")
    session_id = "ses_test_laptop_001"
    conn = get_db_connection()
    conn.execute("DELETE FROM research_sessions WHERE id = ?", (session_id,))
    conn.execute("DELETE FROM sources WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM claims WHERE session_id = ?", (session_id,))
    conn.execute("""
        INSERT INTO research_sessions (id, goal, domain_type, official_domain, target_version_period, target_cycle, facets_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (session_id, goal, "laptop", official_domain, "Gen 7", "Gen 7", json.dumps([f.model_dump() for f in confirmed_facets])))
    conn.commit()

    # 3. Ingest 3 Sources
    src1_id = "src_laptop_official"
    src1_text = (
        "Lenovo Legion Pro 7i Gen 7 Technical Specifications. "
        "Powered by NVIDIA GeForce RTX 4080 with 175W TGP maximum graphics power. "
        "Features 32GB DDR5 expandable memory up to 64GB across two SODIMM slots. "
        "Base retail price starts at $2,299 USD with standard 1-year warranty coverage. "
        "Promotional purchase return window closes on 15th December 2024."
    )
    conn.execute("""
        INSERT INTO sources (id, session_id, title, url, authority, text, fetch_status, content_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (src1_id, session_id, "Lenovo Official Tech Specs (Gen 7)", "https://lenovo.com/legion-pro-7i", "official", src1_text, "pasted", "h1"))

    src2_id = "src_laptop_blog"
    src2_text = (
        "Lenovo Legion Pro 7i Gaming Review and Breakdown. "
        "The RTX 4080 model comes throttled with 140W TGP power limit. "
        "It includes 32GB soldered RAM that cannot be upgraded by users. "
        "Retail price is $2,149 from discount retailers. Standard warranty is 1-year warranty."
    )
    conn.execute("""
        INSERT INTO sources (id, session_id, title, url, authority, text, fetch_status, content_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (src2_id, session_id, "TechReview Blog", "https://techreview-aggregators.com/legion", "low", src2_text, "pasted", "h2"))

    src3_id = "src_laptop_archive"
    src3_text = (
        "Lenovo Legion Pro 7 Gen 6 Archived Circular (2023). "
        "Previous generation model featuring RTX 3080 with retail price $1,899."
    )
    conn.execute("""
        INSERT INTO sources (id, session_id, title, url, authority, text, fetch_status, content_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (src3_id, session_id, "Lenovo Archived Specs (Gen 6)", "https://lenovo.com/archive-gen6", "official", src3_text, "pasted", "h3"))
    conn.commit()
    conn.close()

    # 4. Extract Claims
    print("\nRunning single-pass extraction & verification...")
    c1 = await extract_claims_for_source(session_id, src1_id)
    c2 = await extract_claims_for_source(session_id, src2_id)
    c3 = await extract_claims_for_source(session_id, src3_id)
    print(f"  Extracted: {len(c1)} claims from Official, {len(c2)} from Blog, {len(c3)} from Archive.")

    # 5. Run Gap Detection
    det = run_gap_detection(session_id)
    print(f"\nGap Detection Results:")
    print(f"  Target Version / Period: {det['current_version_period']}")
    print(f"  Total Gaps / Blindspots: {det['total_gaps']}")
    print(f"  Prioritized Checklist Items: {len(det['checklist'])}")

    # Check Real Conflict on GPU TGP
    tgp_conflicts = [c for c in det['conflict_explanations'] if c['facet'] == 'gpu_tgp' and c['conflict_type'] == 'real_conflict']
    assert len(tgp_conflicts) > 0, "Real conflict on GPU TGP (175W vs 140W) must be detected!"
    print(f"  ✓ Real Conflict detected on GPU TGP: {tgp_conflicts[0]['explanation']}")

    # Check Expired Deadline
    passed_items = [g for g in det['gaps'] if g['gap_type'] == 'deadline_passed']
    assert len(passed_items) > 0, "Expired return window date (15th Dec 2024) must trigger deadline_passed check!"
    print(f"  ✓ Deadline Expired check triggered on return window: {passed_items[0]['title']}")

    # Check Checklist actions use lenovo.com and facet consequence
    top_action = det['checklist'][0]
    assert "lenovo.com" in top_action['action_needed'], f"Action should cite lenovo.com: {top_action['action_needed']}"
    assert "scholarship" not in top_action['action_needed'].lower(), "No scholarship text should appear"
    assert "scholarship" not in top_action['consequence'].lower(), "No scholarship text should appear in consequence"
    print(f"  ✓ Top Action: {top_action['title']}")
    print(f"    ➔ Next Step: {top_action['action_needed']}")
    print(f"    ⚠️ Risk: {top_action['consequence']}")

    # 6. Build Coverage Matrix
    matrix_res = build_coverage_matrix(session_id)
    print(f"  ✓ Coverage Matrix built: {matrix_res['stats']['coverage_score']}% coverage across {matrix_res['stats']['total_facets']} facets.")
    print()


async def test_topic_college():
    print("=" * 70)
    print("TEST 2: COLLEGE ADMISSION TOPIC")
    print("=" * 70)

    goal = "What are the exact admission requirements, tuition, and deadlines for Georgia Tech MS CS Fall 2025?"
    official_domain = "gatech.edu"
    print(f"Goal: {goal}")
    print(f"Official Domain: {official_domain}")

    # 1. Generate facets from question using LLM
    gen_result = await generate_facets_from_goal(goal, "college_admission")
    facets = [FacetDefinition(**f) for f in gen_result["facets"]]
    print(f"\nGenerated {len(facets)} Facets from User Question:")
    for f in facets:
        print(f"  • [{f.importance.upper()}] {f.name} ({f.expected_type}): {f.consequence}")

    # Validate generated facet schema
    assert len(facets) >= 5, "At least 5 facets must be generated"
    assert any(f.importance in ("critical", "high") for f in facets), "Importance levels must be set"
    assert all(f.consequence and len(f.consequence) > 10 for f in facets), "Consequences must be present on every facet"
    print("  ✓ Dynamic LLM facet generation validated with importance and consequences.")

    # 2. User reviews and edits/confirms facets before analysis
    confirmed_facets = get_template_facets("college_admission")
    session_id = "ses_test_college_002"
    conn = get_db_connection()
    conn.execute("DELETE FROM research_sessions WHERE id = ?", (session_id,))
    conn.execute("DELETE FROM sources WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM claims WHERE session_id = ?", (session_id,))
    conn.execute("""
        INSERT INTO research_sessions (id, goal, domain_type, official_domain, target_version_period, target_cycle, facets_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (session_id, goal, "college_admission", official_domain, "Fall 2025", "Fall 2025", json.dumps([f.model_dump() for f in confirmed_facets])))
    conn.commit()

    # 3. Ingest Sources
    src1_id = "src_gatech_official"
    src1_text = (
        "Georgia Institute of Technology MS in Computer Science Admissions Fall 2025. "
        "The final application deadline is February 1, 2025. "
        "Standardized test policy: GRE is not required for Fall 2025 applicants. "
        "Estimated graduate tuition is $1,550 per credit hour for graduate students. "
        "Required application documents include official transcripts, 3 letters of recommendation, and statement of purpose."
    )
    conn.execute("""
        INSERT INTO sources (id, session_id, title, url, authority, text, fetch_status, content_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (src1_id, session_id, "Georgia Tech Graduate Admissions", "https://gatech.edu/ms-cs", "official", src1_text, "pasted", "h1"))

    src2_id = "src_studyabroad_blog"
    src2_text = (
        "Georgia Tech MS CS Prep Guide for Fall 2025. "
        "Beware that the application deadline is January 15, 2025. "
        "All international applicants must submit a GRE score minimum 315. "
        "Estimated annual tuition is $35,000 per year for non-residents. "
        "Required application documents include official transcripts, letters of recommendation, statement of purpose, and resume."
    )
    conn.execute("""
        INSERT INTO sources (id, session_id, title, url, authority, text, fetch_status, content_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (src2_id, session_id, "StudyAbroad Portal Blog", "https://studyabroad-prep.com/gatech", "low", src2_text, "pasted", "h2"))

    src3_id = "src_gatech_archive"
    src3_text = (
        "Georgia Institute of Technology MS in Computer Science Graduate Admissions Bulletin Fall 2023 (Archived). "
        "For the Fall 2023 admissions cycle, the final application deadline was December 15, 2022."
    )
    conn.execute("""
        INSERT INTO sources (id, session_id, title, url, authority, text, fetch_status, content_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (src3_id, session_id, "Georgia Tech Fall 2023 Archive", "https://gatech.edu/archive-2023", "official", src3_text, "pasted", "h3"))
    conn.commit()
    conn.close()

    # 4. Extract Claims
    c1 = await extract_claims_for_source(session_id, src1_id)
    c2 = await extract_claims_for_source(session_id, src2_id)
    c3 = await extract_claims_for_source(session_id, src3_id)
    print(f"\nExtracted: {len(c1)} from Official, {len(c2)} from EdTech Blog, {len(c3)} from Archive.")

    # 5. Run Gap Detection
    det = run_gap_detection(session_id)
    print(f"\nGap Detection Results:")
    print(f"  Target Version / Period: {det['current_version_period']}")

    # Check Real Conflict on GRE and Deadline
    deadline_conflicts = [c for c in det['conflict_explanations'] if c['facet'] == 'application_deadline' and c['conflict_type'] == 'real_conflict']
    assert len(deadline_conflicts) > 0, "Real conflict on application deadline (Feb 1 vs Jan 15) must be detected!"
    print(f"  ✓ Real Conflict on Application Deadline: {deadline_conflicts[0]['explanation']}")

    # Check Partial Overlap on Required Documents (extra resume)
    overlaps = [c for c in det['conflict_explanations'] if c['facet'] == 'required_documents' and c['conflict_type'] == 'partial_overlap']
    assert len(overlaps) > 0, "Partial overlap on required documents (resume extra) must be detected!"
    print(f"  ✓ Partial Overlap on Required Documents: {overlaps[0]['explanation']}")

    # Check Outdated Period Check on Fall 2023
    outdated_items = [g for g in det['gaps'] if g['gap_type'] == 'outdated']
    assert len(outdated_items) > 0, "Fall 2023 archive circular must trigger outdated version/period check!"
    print(f"  ✓ Outdated Version / Period detected: {outdated_items[0]['title']}")

    # Check Target Period Expired Warning (Fall 2025 relative to today)
    assert det["version_period_warning"] is not None, "Target period Fall 2025 should trigger expired period warning"
    assert "assumed" in det["version_period_warning"].lower(), f"Warning should state end date is assumed: {det['version_period_warning']}"
    assert "ended" in det["version_period_warning"].lower() or "expired" in det["version_period_warning"].lower(), f"Warning should state period ended: {det['version_period_warning']}"
    print(f"  ✓ Target Period Expired Warning detected: {det['version_period_warning']}")

    # Check gatech.edu in action items
    assert all("scholarship" not in item['action_needed'].lower() for item in det['checklist']), "No scholarship text in actions"
    top_item = det['checklist'][0]
    print(f"  ✓ Top Priority Action: {top_item['title']}")
    print(f"    ➔ Action: {top_item['action_needed']}")
    print(f"    ⚠️ Risk: {top_item['consequence']}")
    print()


async def test_topic_government_scheme():
    print("=" * 70)
    print("TEST 3: GOVERNMENT SCHEME TOPIC (PM SURYA GHAR SOLAR SUBSIDY)")
    print("=" * 70)

    goal = "What are the eligibility criteria, rooftop solar subsidy amount, and application procedure for PM Surya Ghar Muft Bijli Yojana?"
    official_domain = "pmsuryaghar.gov.in"
    print(f"Goal: {goal}")
    print(f"Official Domain: {official_domain}")

    # 1. Generate facets from question using LLM
    gen_result = await generate_facets_from_goal(goal, "government_scheme")
    facets = [FacetDefinition(**f) for f in gen_result["facets"]]
    print(f"\nGenerated {len(facets)} Facets from User Question:")
    for f in facets:
        print(f"  • [{f.importance.upper()}] {f.name} ({f.expected_type}): {f.consequence}")

    # Validate generated facet schema
    assert len(facets) >= 5, "At least 5 facets must be generated"
    assert any(f.importance in ("critical", "high") for f in facets), "Importance levels must be set"
    assert all(f.consequence and len(f.consequence) > 10 for f in facets), "Consequences must be present on every facet"
    print("  ✓ Dynamic LLM facet generation validated with importance and consequences.")

    # 2. User reviews and edits/confirms facets before analysis
    confirmed_facets = get_template_facets("government_scheme")
    session_id = "ses_test_scheme_003"
    conn = get_db_connection()
    conn.execute("DELETE FROM research_sessions WHERE id = ?", (session_id,))
    conn.execute("DELETE FROM sources WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM claims WHERE session_id = ?", (session_id,))
    conn.execute("""
        INSERT INTO research_sessions (id, goal, domain_type, official_domain, target_version_period, target_cycle, facets_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (session_id, goal, "government_scheme", official_domain, "2025", "2025", json.dumps([f.model_dump() for f in confirmed_facets])))
    conn.commit()

    # 3. Ingest Sources
    src1_id = "src_pmsurya_official"
    src1_text = (
        "PM Surya Ghar Muft Bijli Yojana Operational Guidelines 2025. "
        "Central financial assistance provides rooftop solar subsidy up to ₹78,000 for 3kW residential systems. "
        "ELIGIBILITY CRITERIA: residential consumers with valid electricity connection and roof ownership. "
        "The application deadline for current phase is 31st March 2025. "
        "Required documents include electricity bill, bank passbook, and Aadhaar card."
    )
    conn.execute("""
        INSERT INTO sources (id, session_id, title, url, authority, text, fetch_status, content_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (src1_id, session_id, "PM Surya Ghar Official Portal", "https://pmsuryaghar.gov.in/guidelines", "official", src1_text, "pasted", "h1"))

    src2_id = "src_solar_blog"
    src2_text = (
        "Solar Rooftop Subsidy Scheme Alert 2025. "
        "Install rooftop solar under PM Surya Ghar and get subsidy up to ₹1,00,000 from the government. "
        "The application deadline is 31st March 2025. "
        "Required documents include electricity bill, bank passbook, Aadhaar card, and PAN card."
    )
    conn.execute("""
        INSERT INTO sources (id, session_id, title, url, authority, text, fetch_status, content_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (src2_id, session_id, "Solar Energy News Blog", "https://solarnews-india.com/pm-surya", "low", src2_text, "pasted", "h2"))
    conn.commit()
    conn.close()

    # 4. Extract Claims
    c1 = await extract_claims_for_source(session_id, src1_id)
    c2 = await extract_claims_for_source(session_id, src2_id)
    print(f"\nExtracted: {len(c1)} from Official Portal, {len(c2)} from Solar Blog.")

    # 5. Run Gap Detection
    det = run_gap_detection(session_id)
    print(f"\nGap Detection Results:")
    print(f"  Target Version / Period: {det['current_version_period']}")

    # Check Real Conflict on Subsidy Amount (₹78,000 vs ₹1,00,000)
    subsidy_conflicts = [c for c in det['conflict_explanations'] if c['facet'] == 'rooftop_subsidy_amount' and c['conflict_type'] == 'real_conflict']
    assert len(subsidy_conflicts) > 0, "Real conflict on solar subsidy amount (₹78,000 vs ₹1,00,000) must be detected!"
    print(f"  ✓ Real Conflict on Subsidy Amount: {subsidy_conflicts[0]['explanation']}")

    # Check Partial Overlap on Documents (PAN card extra)
    doc_overlaps = [c for c in det['conflict_explanations'] if c['facet'] == 'required_documents' and c['conflict_type'] == 'partial_overlap']
    assert len(doc_overlaps) > 0, "Partial overlap on required documents (PAN card extra) must be detected!"
    print(f"  ✓ Partial Overlap on Documents: {doc_overlaps[0]['explanation']}")

    # Check pmsuryaghar.gov.in cited in actions
    top_action = det['checklist'][0]
    assert "pmsuryaghar.gov.in" in top_action['action_needed'], f"Action should cite pmsuryaghar.gov.in: {top_action['action_needed']}"
    assert "scholarship" not in top_action['action_needed'].lower(), "No scholarship text should appear"
    print(f"  ✓ Top Action: {top_action['title']}")
    print(f"    ➔ Next Step: {top_action['action_needed']}")
    print(f"    ⚠️ Risk: {top_action['consequence']}")
    print()


async def main():
    await test_normalizers()
    await test_topic_laptop()
    await test_topic_college()
    await test_topic_government_scheme()
    print("=" * 70)
    print("🎉 ALL 3 MULTI-TOPIC TEST SUITES PASSED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())
