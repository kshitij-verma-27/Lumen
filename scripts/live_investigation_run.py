import asyncio
import os
import sys
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Use DARKSPOT_DB for live test so production darkspot.db is untouched
os.environ["DARKSPOT_DB"] = "scratch/live_investigation_test.db"
os.environ["FORCE_MOCK"] = "false"

from app.database import init_db, get_db_connection, row_to_dict
from app.fetch import fetch_url
from app.extract import extract_claims_for_source, get_template_facets
from app.trust import verify_claim_in_source, classify_authority
from app.detect import run_gap_detection
from app.llm import get_llm_status
import uuid


async def run_live_investigation():
    print("==================================================")
    print("  RUNNING LIVE INVESTIGATION ON REAL OFFICIAL PAGE")
    print("==================================================")
    
    init_db()
    llm_info = get_llm_status()
    print(f"LLM Status: mode={llm_info.get('mode')}, model={llm_info.get('model')}")
    
    target_url = "https://nta.ac.in"
    print(f"\n1. Ingesting live official source: {target_url}")
    fetch_res = await fetch_url(target_url)
    
    status_code = fetch_res.get("status_code", 0)
    fetch_status = fetch_res.get("fetch_status", "unknown")
    text = fetch_res.get("text", "")
    content_hash = fetch_res.get("content_hash", "")
    print(f"   Fetch Status: {fetch_status} | HTTP {status_code}")
    session_id = f"live_sess_{uuid.uuid4().hex[:10]}"
    source_id = f"src_{uuid.uuid4().hex[:10]}"
    
    facets = [
        {
            "id": "agency_name",
            "name": "Testing Agency Name",
            "description": "Official name of the testing organization or authority",
            "expected_type": "text",
            "importance": "high",
            "consequence": "Must be official National Testing Agency.",
            "is_deadline": False
        },
        {
            "id": "exam_announcement",
            "name": "Official Exam Notification",
            "description": "Active examination notifications, dates extension, or circulars",
            "expected_type": "text",
            "importance": "critical",
            "consequence": "Students must follow active official exam circulars.",
            "is_deadline": False
        },
        {
            "id": "exam_session",
            "name": "Examination Session / Cycle",
            "description": "Target semester or session year for active exams",
            "expected_type": "text",
            "importance": "high",
            "consequence": "Must match active academic cycle.",
            "is_deadline": False
        },
        {
            "id": "registration_status",
            "name": "Registration & Submission Advisory",
            "description": "Advisories or instructions regarding online application forms and registration process",
            "expected_type": "text",
            "importance": "high",
            "consequence": "Failure to follow advisory causes form rejection.",
            "is_deadline": False
        }
    ]
    conn = get_db_connection()
    conn.execute("""
        INSERT INTO research_sessions (id, goal, domain_type, official_domain, facets_json)
        VALUES (?, ?, 'education', 'nta.ac.in', ?)
    """, (session_id, "What active exam registrations, session schedules, and examination guidelines are announced by NTA?", json.dumps(facets)))
    
    authority = classify_authority(target_url, official_domain="nta.ac.in")
    
    conn.execute("""
        INSERT INTO sources (id, session_id, url, content_hash, authority, text, title, fetch_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (source_id, session_id, target_url, content_hash, authority, text, fetch_res.get("title") or "NTA Portal", fetch_status))
    conn.commit()
    conn.close()
    
    print(f"\n2. Extracting & verifying claims from live source...")
    processed_claims = await extract_claims_for_source(session_id, source_id)
    print(f"   Extracted & verified {len(processed_claims)} candidate claims")
    
    verified_count = 0
    raw_results = []
    
    for c in processed_claims:
        is_verified = bool(c.get("verified"))
        if is_verified:
            verified_count += 1
        raw_results.append({
            "facet": c.get("facet"),
            "value": c.get("value_raw"),
            "quote": c.get("exact_quote"),
            "verified": is_verified,
            "score": c.get("verification_score"),
            "reason": c.get("rejection_reason")
        })
        print(f"   - Facet: {c.get('facet'):15s} | Verified: {str(is_verified):5s} | Score: {c.get('verification_score', 0):.2f} | Reason: {c.get('rejection_reason')}")
    
    print(f"\n3. Running gap & coverage detection...")
    gap_res = run_gap_detection(session_id)
    print(f"   Coverage Score: {gap_res.get('coverage_score', 0)}%")
    print(f"   Gaps Detected: {len(gap_res.get('gaps', []))}")
    print(f"   Actions Suggested: {len(gap_res.get('actions', []))}")
    
    output_summary = {
        "target_url": target_url,
        "http_status": status_code,
        "fetch_status": fetch_status,
        "text_length": len(text),
        "content_hash": content_hash,
        "llm_model": llm_info.get("model"),
        "total_claims_extracted": len(processed_claims),
        "verified_claims_count": verified_count,
        "coverage_score": gap_res.get("coverage_score"),
        "claims": raw_results
    }
    
    # Save raw output
    scratch_out = Path("scratch/live_investigation_output.json")
    scratch_out.write_text(json.dumps(output_summary, indent=2), encoding="utf-8")
    print(f"\n[OK] Live investigation completed successfully. Raw output written to {scratch_out}")


if __name__ == "__main__":
    asyncio.run(run_live_investigation())
