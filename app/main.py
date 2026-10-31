import os
import uuid
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse

from app.database import init_db, get_db_connection, row_to_dict
from app.models import (
    ResearchSessionCreate, SessionDetailResponse, SourcesAddRequest,
    ClaimResponse, SourceResponse, HealthStatus, FacetDefinition,
    CycleOverridePayload, VersionPeriodOverridePayload,
    GenerateFacetsRequest, GenerateFacetsResponse, UpdateFacetsRequest
)
from app.normalize import normalize_cycle, normalize_version_period
from app.fetch import fetch_url, process_pasted_text
from app.trust import classify_authority
from app.extract import get_template_facets, extract_claims_for_source
from app.llm import get_llm_status, is_mock_mode, generate_facets_from_goal
from app.independence import detect_and_group_sources

# Initialize database on startup
init_db()

app = FastAPI(
    title="Digital Dark Spot",
    description="AI-assisted information-gap detection platform (Evidence-first verification engine)",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthStatus)
def health_check():
    llm_info = get_llm_status()
    return HealthStatus(
        status="ok",
        gemini_configured=llm_info["gemini_configured"],
        mode=llm_info["mode"],
        model=llm_info["model"],
        database="connected",
        fallback_reason=llm_info.get("fallback_reason")
    )


@app.get("/api/templates")
def list_templates():
    return {
        "templates": [
            {
                "id": "laptop",
                "name": "Hardware & Laptop Purchase (6 Facets)",
                "default_official_domain": "lenovo.com",
                "facets": [f.model_dump() for f in get_template_facets("laptop")]
            },
            {
                "id": "college_admission",
                "name": "Graduate University Admissions (6 Facets)",
                "default_official_domain": "gatech.edu",
                "facets": [f.model_dump() for f in get_template_facets("college_admission")]
            },
            {
                "id": "government_scheme",
                "name": "Government Welfare / Subsidy Scheme (6 Facets)",
                "default_official_domain": "pmsuryaghar.gov.in",
                "facets": [f.model_dump() for f in get_template_facets("government_scheme")]
            },
            {
                "id": "scholarship",
                "name": "Scholarship & Welfare Schemes (Optional Quick-Start)",
                "default_official_domain": "scholarships.gov.in",
                "facets": [f.model_dump() for f in get_template_facets("scholarship")]
            },
            {
                "id": "generic",
                "name": "General Policy & Research Goal (5 Facets)",
                "default_official_domain": "",
                "facets": [f.model_dump() for f in get_template_facets("generic")]
            }
        ]
    }


@app.post("/api/facets/generate", response_model=GenerateFacetsResponse)
async def generate_facets_endpoint(payload: GenerateFacetsRequest):
    """
    Dynamically generates 5-8 research facets with importance levels and consequences
    tailored to the user's research question using Gemini (or deterministic fallback).
    """
    if not payload.goal or not payload.goal.strip():
        raise HTTPException(status_code=400, detail="Research goal/question is required")

    result = await generate_facets_from_goal(payload.goal, payload.domain_type)
    facets = [FacetDefinition(**f) for f in result.get("facets", [])]
    return GenerateFacetsResponse(
        goal=payload.goal,
        suggested_domain=result.get("suggested_domain"),
        suggested_official_domain=result.get("suggested_official_domain"),
        facets=facets
    )


@app.put("/api/sessions/{session_id}/facets")
def update_session_facets(session_id: str, payload: UpdateFacetsRequest):
    """Updates the target facets for a session prior to or during analysis."""
    conn = get_db_connection()
    row = conn.execute("SELECT id FROM research_sessions WHERE id = ?", (session_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found")

    facets_json = json.dumps([f.model_dump() for f in payload.facets])
    conn.execute("UPDATE research_sessions SET facets_json = ? WHERE id = ?", (facets_json, session_id))
    conn.commit()
    conn.close()
    return {"status": "updated", "session_id": session_id, "facets_count": len(payload.facets)}


@app.get("/api/sample-sources")
def get_sample_sources():
    """Returns pre-packaged sample scholarship documents for instant 1-click offline testing."""
    sample_dir = Path("sample_sources")
    samples = []

    files_config = [
        {
            "file": "scholarship_official_guidelines.txt",
            "title": "[Synthetic Sample Data] National Scholarship Scheme Official Guidelines 2025-26",
            "url": "https://scholarships.gov.in/guidelines-2025.html",
            "authority": "official"
        },
        {
            "file": "scholarship_aggregator_blog.txt",
            "title": "[Synthetic Sample Data] Sarkari Help Blog - Scholarship Alert 2025",
            "url": "https://sarkarihelp-aggregators.com/scholarship-alert-2025",
            "authority": "low"
        },
        {
            "file": "scholarship_outdated_circular.txt",
            "title": "[Synthetic Sample Data] Ministry Circular 2023-24 (Archived/Old Cycle)",
            "url": "https://scholarships.gov.in/archive/2023.html",
            "authority": "official"
        }
    ]

    for item in files_config:
        fpath = sample_dir / item["file"]
        if fpath.exists():
            text = fpath.read_text(encoding="utf-8")
            samples.append({
                "title": item["title"],
                "url": item["url"],
                "authority": item["authority"],
                "text": text,
                "preview": text[:200] + "..."
            })

    return {"samples": samples}


@app.post("/api/sessions")
def create_session(payload: ResearchSessionCreate):
    session_id = f"ses_{uuid.uuid4().hex[:10]}"
    facets = payload.custom_facets or get_template_facets(payload.domain_type)
    facets_json = json.dumps([f.model_dump() for f in facets])
    vp = payload.target_version_period or payload.target_cycle

    conn = get_db_connection()
    conn.execute("""
        INSERT INTO research_sessions (id, goal, domain_type, official_domain, target_cycle, target_version_period, facets_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        session_id,
        payload.goal,
        payload.domain_type,
        payload.official_domain or ("scholarships.gov.in" if payload.domain_type == "scholarship" else None),
        vp,
        vp,
        facets_json
    ))
    conn.commit()
    conn.close()

    return {
        "session_id": session_id,
        "goal": payload.goal,
        "domain_type": payload.domain_type,
        "target_version_period": vp,
        "target_cycle": vp
    }


@app.get("/api/sessions/{session_id}", response_model=SessionDetailResponse)
def get_session(session_id: str):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM research_sessions WHERE id = ?", (session_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found")

    sources_count = conn.execute("SELECT COUNT(*) as cnt FROM sources WHERE session_id = ?", (session_id,)).fetchone()["cnt"]
    claims_count = conn.execute("SELECT COUNT(*) as cnt FROM claims WHERE session_id = ?", (session_id,)).fetchone()["cnt"]
    verified_count = conn.execute("SELECT COUNT(*) as cnt FROM claims WHERE session_id = ? AND verified = 1", (session_id,)).fetchone()["cnt"]
    rejected_count = conn.execute("SELECT COUNT(*) as cnt FROM claims WHERE session_id = ? AND verified = 0", (session_id,)).fetchone()["cnt"]

    facets_data = json.loads(row["facets_json"])
    facets = [FacetDefinition(**f) for f in facets_data]
    vp = row["target_version_period"] or row["target_cycle"]
    conn.close()

    return SessionDetailResponse(
        id=row["id"],
        goal=row["goal"],
        domain_type=row["domain_type"],
        official_domain=row["official_domain"],
        target_version_period=vp,
        target_cycle=vp,
        facets=facets,
        created_at=row["created_at"],
        sources_count=sources_count,
        claims_count=claims_count,
        verified_claims_count=verified_count,
        rejected_claims_count=rejected_count
    )


@app.post("/api/sessions/{session_id}/sources")
async def add_sources(session_id: str, payload: SourcesAddRequest):
    conn = get_db_connection()
    sess = conn.execute("SELECT * FROM research_sessions WHERE id = ?", (session_id,)).fetchone()
    if not sess:
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found")

    official_domain = sess["official_domain"]
    added_sources = []

    for src_input in payload.sources:
        src_id = f"src_{uuid.uuid4().hex[:10]}"

        if src_input.pasted_text and len(src_input.pasted_text.strip()) > 0:
            doc = process_pasted_text(src_input.pasted_text, src_input.title)
        elif src_input.url:
            doc = await fetch_url(src_input.url)
        else:
            continue

        # Classify authority by domain rules
        authority = classify_authority(doc.get("url"), official_domain=official_domain)

        conn.execute("""
            INSERT INTO sources (
                id, session_id, url, content_hash, published_date,
                published_date_origin, authority, original_group_id,
                text, title, fetch_status, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            src_id,
            session_id,
            doc.get("url"),
            doc.get("content_hash", ""),
            doc.get("published_date"),
            doc.get("published_date_origin", "none"),
            authority,
            src_id,  # Initial group id (independence clustering in L3)
            doc.get("text", ""),
            doc.get("title") or src_input.title or "Untitled Source",
            doc.get("fetch_status", "success"),
            doc.get("error_message")
        ))

        added_sources.append({
            "id": src_id,
            "url": doc.get("url"),
            "title": doc.get("title"),
            "authority": authority,
            "fetch_status": doc.get("fetch_status"),
            "published_date": doc.get("published_date"),
            "published_date_origin": doc.get("published_date_origin", "none"),
            "text_length": len(doc.get("text", ""))
        })

    conn.commit()
    conn.close()
    return {"added_count": len(added_sources), "sources": added_sources}


@app.get("/api/sessions/{session_id}/sources")
def list_session_sources(session_id: str):
    conn = get_db_connection()
    indep = detect_and_group_sources(session_id, conn)
    rows = conn.execute("SELECT * FROM sources WHERE session_id = ? ORDER BY fetched_at ASC", (session_id,)).fetchall()
    sources = []
    source_details = indep.get("source_details_map", {})
    for r in rows:
        d = row_to_dict(r)
        d["text_length"] = len(d.get("text") or "")
        d["text_preview"] = (d.get("text") or "")[:240] + "..."
        det = source_details.get(d["id"], {})
        d["original_group_id"] = det.get("original_group_id", d.get("original_group_id") or d["id"])
        d["is_original"] = det.get("is_original", (d["original_group_id"] == d["id"]))
        d["copied_from_id"] = det.get("copied_from_id")
        d["copied_from_title"] = det.get("copied_from_title")
        sources.append(d)
    conn.close()
    return {
        "sources": sources,
        "independence": indep
    }


@app.post("/api/sessions/{session_id}/extract")
async def run_extraction(session_id: str):
    """
    Triggers extraction of all target facets across all sources for this session.
    Runs the LLM pass and executes deterministic verification rules.
    """
    conn = get_db_connection()
    src_rows = conn.execute("SELECT id FROM sources WHERE session_id = ? AND fetch_status != 'failed'", (session_id,)).fetchall()
    conn.close()

    if not src_rows:
        raise HTTPException(status_code=400, detail="No active sources found to extract from")

    total_extracted = 0
    for r in src_rows:
        claims = await extract_claims_for_source(session_id, r["id"])
        total_extracted += len(claims)

    # Execute Red-Team Verifier pass
    from app.red_team import run_red_team_verification
    red_team_results = await run_red_team_verification(session_id)

    # Fetch stats
    conn = get_db_connection()
    verified_count = conn.execute("SELECT COUNT(*) as cnt FROM claims WHERE session_id = ? AND verified = 1", (session_id,)).fetchone()["cnt"]
    rejected_count = conn.execute("SELECT COUNT(*) as cnt FROM claims WHERE session_id = ? AND verified = 0", (session_id,)).fetchone()["cnt"]
    conn.close()

    return {
        "status": "completed",
        "total_claims_extracted": total_extracted,
        "verified_claims_count": verified_count,
        "rejected_claims_count": rejected_count,
        "red_team": red_team_results
    }


@app.get("/api/sessions/{session_id}/claims")
def list_claims(
    session_id: str,
    verified_only: bool = Query(False, description="Filter only verified claims")
):
    conn = get_db_connection()
    query = """
        SELECT c.*, s.title as source_title, s.url as source_url, s.authority as source_authority
        FROM claims c
        JOIN sources s ON c.source_id = s.id
        WHERE c.session_id = ?
    """
    params = [session_id]
    if verified_only:
        query += " AND c.verified = 1"
    query += " ORDER BY c.facet ASC, c.verified DESC"

    rows = conn.execute(query, params).fetchall()
    claims = [row_to_dict(r) for r in rows]
    conn.close()

    # Convert verified integer to boolean
    for c in claims:
        c["verified"] = bool(c["verified"])
        c["survived_redteam"] = bool(c["survived_redteam"])

    return {
        "count": len(claims),
        "claims": claims
    }


# ==========================================
# L2 Detection & Prioritized Checklist APIs
# ==========================================

from app.detect import run_gap_detection, build_coverage_matrix


@app.post("/api/sessions/{session_id}/detect")
def detect_gaps(session_id: str):
    """
    Runs normalizers on all verified claims, detects missing facets,
    conflicts, outdated cycles, and produces a prioritized checklist.
    """
    try:
        return run_gap_detection(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gap detection failed: {e}")


@app.get("/api/sessions/{session_id}/gaps")
def get_gaps(session_id: str):
    try:
        return run_gap_detection(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gap detection failed: {e}")


@app.get("/api/sessions/{session_id}/conflicts")
def get_conflicts(session_id: str):
    """Returns the L3 Conflict Explainer taxonomy breakdown."""
    try:
        results = run_gap_detection(session_id)
        return {
            "session_id": session_id,
            "current_cycle": results.get("current_cycle"),
            "cycle_warning": results.get("cycle_warning"),
            "conflict_explanations": results.get("conflict_explanations", [])
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conflict explanation failed: {e}")


@app.get("/api/sessions/{session_id}/matrix")
def get_coverage_matrix(session_id: str):
    """Returns the L3 Coverage Matrix: Facets x Sources grid with visual dark spot indicators."""
    try:
        return build_coverage_matrix(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Coverage matrix generation failed: {e}")


@app.get("/api/sessions/{session_id}/independence")
def get_source_independence(session_id: str):
    """Returns the Source Independence Badge analysis and duplicate clustering."""
    try:
        return detect_and_group_sources(session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Independence detection failed: {e}")


@app.post("/api/sessions/{session_id}/version-period")
@app.post("/api/sessions/{session_id}/cycle")
def override_session_version_period(session_id: str, payload: VersionPeriodOverridePayload):
    """Overrides or resets the target version / period (or cycle) for the session."""
    conn = get_db_connection()
    row = conn.execute("SELECT id FROM research_sessions WHERE id = ?", (session_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found")
    raw_val = payload.target_version_period or payload.target_cycle
    norm_vp = normalize_version_period(raw_val) if raw_val and raw_val.strip() else None
    conn.execute(
        "UPDATE research_sessions SET target_version_period = ?, target_cycle = ? WHERE id = ?",
        (norm_vp, norm_vp, session_id)
    )
    conn.commit()
    conn.close()
    return run_gap_detection(session_id)


# ==========================================
# Red-Team Verifier Endpoints
# ==========================================

@app.post("/api/sessions/{session_id}/red-team")
async def run_session_red_team(session_id: str):
    """Executes the adversarial second-pass red-team audit."""
    try:
        from app.red_team import run_red_team_verification
        return await run_red_team_verification(session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Red-team verification failed: {e}")


@app.get("/api/sessions/{session_id}/red-team")
def get_session_red_team_stats(session_id: str):
    """Retrieves current red-team verification stats and counter."""
    conn = get_db_connection()
    total = conn.execute("SELECT COUNT(*) as cnt FROM claims WHERE session_id = ?", (session_id,)).fetchone()["cnt"]
    survived = conn.execute("SELECT COUNT(*) as cnt FROM claims WHERE session_id = ? AND survived_redteam = 1 AND verified = 1", (session_id,)).fetchone()["cnt"]
    demoted = conn.execute("SELECT COUNT(*) as cnt FROM claims WHERE session_id = ? AND (survived_redteam = 0 OR redteam_status = 'uncertain')", (session_id,)).fetchone()["cnt"]
    conn.close()
    return {
        "session_id": session_id,
        "extracted_count": total,
        "survived_count": survived,
        "demoted_count": demoted,
        "counter_text": f"{total} extracted, {survived} survived, {demoted} demoted"
    }


# ==========================================
# Gap-to-Action Email Drafts Endpoints
# ==========================================

@app.get("/api/sessions/{session_id}/email-drafts")
def get_email_drafts(session_id: str):
    """Generates short draft inquiry emails for all unresolved gaps and conflicts."""
    try:
        from app.email_drafts import get_session_email_drafts
        return get_session_email_drafts(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate email drafts: {e}")


# ==========================================
# Change Watch Endpoints
# ==========================================

@app.post("/api/sources/{source_id}/recheck")
async def recheck_single_source(source_id: str):
    """Re-checks a source's live content against stored SHA-256 hash and generates diffs."""
    try:
        from app.change_watch import recheck_source
        return await recheck_source(source_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Source re-check failed: {e}")


@app.post("/api/sessions/{session_id}/recheck")
async def recheck_all_session_sources(session_id: str):
    """Re-checks all sources belonging to a research session."""
    try:
        from app.change_watch import recheck_session_sources
        return await recheck_session_sources(session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Session re-check failed: {e}")


# ==========================================
# Audit-Trail Export Endpoints
# ==========================================

@app.get("/api/sessions/{session_id}/export/json")
def export_audit_trail_json(session_id: str):
    """Returns downloadable structured JSON audit trail containing findings, quotes, and hashes."""
    try:
        from app.export import build_audit_trail_data
        data = build_audit_trail_data(session_id)
        return JSONResponse(
            content=data,
            headers={
                "Content-Disposition": f'attachment; filename="audit_trail_{session_id}.json"'
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"JSON export failed: {e}")


@app.get("/api/sessions/{session_id}/export/html")
def export_audit_trail_html(session_id: str):
    """Returns a standalone printable HTML report ready for printing or PDF export."""
    try:
        from app.export import generate_printable_html_report
        html_report = generate_printable_html_report(session_id)
        return HTMLResponse(content=html_report)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"HTML report export failed: {e}")





# Frontend static files mount
frontend_path = Path("frontend")
if frontend_path.exists():
    app.mount("/static", StaticFiles(directory="frontend"), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(frontend_path / "index.html")
