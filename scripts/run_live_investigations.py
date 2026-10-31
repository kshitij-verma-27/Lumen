import os
import sys
import json
import asyncio
from pathlib import Path

# Ensure live mode (not mock)
if "FORCE_MOCK" in os.environ:
    del os.environ["FORCE_MOCK"]

sys.path.insert(0, ".")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.database import get_db_connection
from app.llm import get_llm_status
from app.main import (
    create_session, add_sources, run_extraction,
    detect_gaps, list_claims, get_conflicts, get_coverage_matrix
)
from app.models import (
    ResearchSessionCreate, SourcesAddRequest, SourceInput
)

# Sample pasted text for Udyam Registration (Official Gazette Notification Summary)
UDYAM_PASTED_TEXT = """
MINISTRY OF MICRO, SMALL AND MEDIUM ENTERPRISES NOTIFICATION
New Delhi, the 26th June, 2020 (Updated for 2025-26)

Subject: Criteria for classification of Micro, Small and Medium Enterprises and Registration Process.

1. CLASSIFICATION CRITERIA:
(i) A micro enterprise, where the investment in plant and machinery or equipment does not exceed 1 crore rupees and turnover does not exceed 5 crore rupees;
(ii) A small enterprise, where the investment in plant and machinery or equipment does not exceed 10 crore rupees and turnover does not exceed 50 crore rupees;
(iii) A medium enterprise, where the investment in plant and machinery or equipment does not exceed 50 crore rupees and turnover does not exceed 250 crore rupees.

2. REGISTRATION PROCESS:
(1) Any person who intends to establish a micro, small or medium enterprise may file Udyam Registration online in the Udyam Registration portal: https://udyamregistration.gov.in
(2) There will be no fee for filing Udyam Registration. The registration process is completely free of cost.
(3) Aadhaar number shall be required for Udyam Registration. The Aadhaar number shall be of the proprietor in the case of a proprietorship firm, of the managing partner in the case of a partnership firm and of a karta in the case of a Hindu Undivided Family (HUF).
(4) In case of a Company or a Limited Liability Partnership or a Cooperative Society or a Society or a Trust, the organisation or its authorised signatory shall provide its GSTIN and PAN along with its Aadhaar number.
(5) No enterprise shall file more than one Udyam Registration: Provided that any number of activities including manufacturing or service or both may be specified or added in one registration.
(6) Helpline: For assistance and facilitation, contact champions.gov.in or email support at helpdesk-udyam@gov.in.
"""

INVESTIGATIONS = [
    {
        "num": 1,
        "title": "NSP Scholarships Live Investigation",
        "question": "What should I verify before applying for NSP scholarships?",
        "domain_type": "scholarship",
        "official_domain": "scholarships.gov.in",
        "sources": [
            {"url": "https://scholarships.gov.in", "title": "National Scholarship Portal Home"},
            {"url": "https://scholarships.gov.in/public/faq", "title": "NSP Official FAQ Portal"},
            {"url": "https://swayam.gov.in", "title": "SWAYAM MoE Apex Portal"}
        ]
    },
    {
        "num": 2,
        "title": "UGC & NTA Examination Live Investigation",
        "question": "What should I verify regarding eligibility, dates, and syllabus before applying for UGC and NTA examinations?",
        "domain_type": "generic",
        "official_domain": "nta.ac.in",
        "sources": [
            {"url": "https://nta.ac.in", "title": "National Testing Agency Portal"},
            {"url": "https://www.ugc.gov.in", "title": "University Grants Commission Official Site"},
            {"url": "https://csirhrdg.res.in", "title": "CSIR-HRDG Examination Authority"}
        ]
    },
    {
        "num": 3,
        "title": "Udyam Registration Live Investigation (2 Pages + 1 Pasted Text)",
        "question": "What documents, turnover limits, and conditions are required for Udyam MSME registration?",
        "domain_type": "generic",
        "official_domain": "udyamregistration.gov.in",
        "sources": [
            {"url": "https://udyamregistration.gov.in", "title": "Official Udyam Registration Portal"},
            {"url": "https://www.startupindia.gov.in", "title": "Startup India DPIIT Recognition & MSME Portal"},
            {"pasted_text": UDYAM_PASTED_TEXT, "title": "Ministry of MSME Official Gazette Notification & Guidelines"}
        ]
    }
]


async def run_single_investigation(inv: dict):
    print("\n" + "="*80)
    print(f"RUNNING LIVE INVESTIGATION #{inv['num']}: {inv['title']}")
    print(f"Question: \"{inv['question']}\"")
    print(f"Official Domain: {inv['official_domain']}")
    print(f"LLM Status: {get_llm_status()}")
    print("="*80 + "\n")

    # 1. Create Session
    create_req = ResearchSessionCreate(
        goal=inv["question"],
        domain_type=inv["domain_type"],
        official_domain=inv["official_domain"]
    )
    sess_res = create_session(create_req)
    session_id = sess_res["session_id"]
    print(f"[+] Created Session ID: {session_id}")

    # 2. Add Sources
    source_inputs = []
    for s in inv["sources"]:
        if "url" in s:
            source_inputs.append(SourceInput(url=s["url"], title=s["title"]))
        elif "pasted_text" in s:
            source_inputs.append(SourceInput(pasted_text=s["pasted_text"], title=s["title"]))

    print(f"[+] Fetching and adding {len(source_inputs)} live sources...")
    src_res = await add_sources(session_id, SourcesAddRequest(sources=source_inputs))
    print(f"    Added {src_res.get('added_count')} sources:")
    for s in src_res.get("sources", []):
        print(f"    - [{s.get('authority')}] {s.get('title')} ({s.get('url')}) -> Status: {s.get('fetch_status')}, Len: {s.get('text_length')}")

    # 3. Run Live Extraction & Code Verification
    print(f"\n[+] Running Extraction & Verification across all sources...")
    ext_res = await run_extraction(session_id)
    print(f"    Extraction completed:")
    print(f"    - Total claims extracted: {ext_res.get('total_claims_extracted')}")
    print(f"    - Verified claims: {ext_res.get('verified_claims_count')}")
    print(f"    - Rejected claims: {ext_res.get('rejected_claims_count')}")

    # 4. Fetch Claims
    claims_data = list_claims(session_id, verified_only=False)
    all_claims = claims_data.get("claims", [])

    print(f"\n[+] CLAIMS BREAKDOWN ({len(all_claims)} total):")
    for idx, c in enumerate(all_claims, 1):
        status_str = "VERIFIED" if c.get("verified") else f"REJECTED ({c.get('rejection_reason')})"
        score = c.get("verification_score")
        print(f"    {idx}. [{c.get('facet')}] Value: '{c.get('value_raw')}' | Status: {status_str} | Score: {score}")
        print(f"       Quote: \"{c.get('exact_quote')[:140]}...\"")
        print(f"       Source: {c.get('source_title')} ({c.get('source_authority')})")

    # 5. Detect Gaps, Conflicts, & Prioritized Checklist
    gap_res = detect_gaps(session_id)

    # Print Facets
    print(f"\n[+] TARGET FACETS:")
    conn = get_db_connection()
    sess_row = conn.execute("SELECT facets_json FROM research_sessions WHERE id = ?", (session_id,)).fetchone()
    conn.close()
    if sess_row:
        facets_list = json.loads(sess_row["facets_json"])
        for f in facets_list:
            covered = f["id"] in gap_res.get("covered_facets", [])
            cov_str = "[COVERED]" if covered else "[DARK SPOT / GAP]"
            print(f"    - {cov_str:18s} {f['id']}: {f['name']} (Importance: {f.get('importance', 'medium')})")

    # Print Gaps
    print(f"\n[+] INFORMATION GAPS / DARK SPOTS ({len(gap_res.get('gaps', []))} missing facets):")
    for g in gap_res.get("gaps", []):
        print(f"    - {g['facet']}: {g['facet_name']} (Importance: {g.get('importance')}) -> {g.get('consequence')}")

    # Print Conflicts
    conflicts = gap_res.get("conflicts", [])
    print(f"\n[+] CONFLICTS DETECTED ({len(conflicts)}):")
    if not conflicts:
        print("    None (no contradicting values across independent authorities)")
    else:
        for cf in conflicts:
            print(f"    - Facet: {cf.get('facet')}")
            for v in cf.get("values", []):
                print(f"      * {v.get('source_title')} ({v.get('authority')}): '{v.get('value_raw')}'")

    # Print Prioritized Checklist
    checklist = gap_res.get("checklist", [])
    print(f"\n[+] PRIORITIZED VERIFICATION CHECKLIST ({len(checklist)} items):")
    for item in checklist:
        print(f"    - [Step {item.get('priority')}] {item.get('title')}: {item.get('action')}")
        print(f"      Consequence if ignored: {item.get('consequence')}")

    return {
        "num": inv["num"],
        "title": inv["title"],
        "session_id": session_id,
        "claims_count": len(all_claims),
        "verified_count": ext_res.get("verified_claims_count"),
        "rejected_count": ext_res.get("rejected_claims_count"),
        "gaps_count": len(gap_res.get("gaps", [])),
        "conflicts_count": len(conflicts),
        "checklist_count": len(checklist)
    }


async def main():
    print("STARTING LIVE END-TO-END INVESTIGATIONS (STABILIZATION SPRINT ITEM B)...")
    results = []
    for inv in INVESTIGATIONS:
        res = await run_single_investigation(inv)
        results.append(res)

    print("\n" + "="*80)
    print("LIVE INVESTIGATIONS SUMMARY")
    print("="*80)
    for r in results:
        print(f"Investigation #{r['num']} ({r['title']}):")
        print(f"  Session ID: {r['session_id']}")
        print(f"  Claims: {r['claims_count']} ({r['verified_count']} verified, {r['rejected_count']} rejected)")
        print(f"  Gaps: {r['gaps_count']} | Conflicts: {r['conflicts_count']} | Checklist Items: {r['checklist_count']}")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(main())
