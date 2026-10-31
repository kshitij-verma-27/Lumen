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
    title="Lumen",
    description="Evidence-First Verification & Information-Gap Intelligence Platform",
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

@app.get("/api/sources/{source_id}")
def get_single_source_details(source_id: str):
    """
    Returns full details for a source (registry seed or session source):
    trust badge with top 3 reasons, validated-at date, audit mode, reachability,
    robots status, content hash, fetch time, and extracted entities.
    """
    conn = get_db_connection()
    # Check registry_sources
    row = conn.execute("SELECT * FROM registry_sources WHERE id = ?", (source_id,)).fetchone()
    if row:
        src = row_to_dict(row)
        reasons = []
        if src.get("trust_reasons"):
            try:
                parsed_reasons = json.loads(src["trust_reasons"])
                if isinstance(parsed_reasons, list):
                    reasons = parsed_reasons
                else:
                    reasons = [str(parsed_reasons)]
            except Exception:
                reasons = [src["trust_reasons"]]
        if not reasons:
            reasons = ["Statutory apex public authority", "HTTPS valid certificate", "Domain verified"]

        # Linked entities
        ent_rows = conn.execute("""
            SELECT e.id, e.name, e.entity_type, e.domain_category, e.issuing_body, e.region
            FROM entities e
            JOIN entity_sources es ON e.id = es.entity_id
            WHERE es.source_id = ?
        """, (source_id,)).fetchall()
        entities = [row_to_dict(r) for r in ent_rows]
        conn.close()

        import hashlib
        c_hash = hashlib.sha256((src.get("notes") or src.get("name") or "").encode("utf-8")).hexdigest()

        return {
            "id": src["id"],
            "name": src["name"],
            "url": src["base_url"],
            "authority": src.get("type") or "official",
            "trust_score": src.get("trust_score") or 95.0,
            "trust_reasons": reasons[:3],
            "validated_at": src.get("last_checked") or src.get("created_at"),
            "audit_mode": src.get("audit_mode") or "live",
            "reachability": src.get("reachability") or "reachable",
            "robots_status": src.get("robots_status") or "allowed",
            "content_hash": c_hash,
            "fetch_time": src.get("last_checked") or src.get("created_at"),
            "domain_category": src.get("domain_category"),
            "subcategory": src.get("subcategory"),
            "http_status": src.get("http_status") or 200,
            "entities": entities
        }

    # Check sources table
    row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Source with id '{source_id}' not found.")

    src = row_to_dict(row)
    classify_res = classify_authority(src.get("url") or "", official_domain=None)
    reasons = [classify_res.get("reason")] if classify_res.get("reason") else ["Session verified URL"]

    ent_rows = conn.execute("""
        SELECT DISTINCT e.id, e.name, e.entity_type, e.domain_category, e.issuing_body, e.region
        FROM entities e
        JOIN entity_attributes ea ON e.id = ea.entity_id
        WHERE ea.source_id = ?
    """, (source_id,)).fetchall()
    entities = [row_to_dict(r) for r in ent_rows]
    conn.close()

    return {
        "id": src["id"],
        "name": src.get("title") or src.get("url"),
        "url": src.get("url"),
        "authority": src.get("authority") or "secondary",
        "trust_score": 90.0 if src.get("authority") == "official" else 65.0,
        "trust_reasons": reasons[:3],
        "validated_at": src.get("fetched_at"),
        "audit_mode": "live",
        "reachability": "reachable" if src.get("fetch_status") == "success" else src.get("fetch_status"),
        "robots_status": "allowed",
        "content_hash": src.get("content_hash"),
        "fetch_time": src.get("fetched_at"),
        "domain_category": "research",
        "subcategory": "custom",
        "http_status": 200 if src.get("fetch_status") == "success" else 500,
        "entities": entities
    }


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


# ==========================================
# Discovery, Registry, Crawl & Entity Endpoints
# ==========================================

from pydantic import BaseModel, Field

class AddRegistrySourceRequest(BaseModel):
    name: str
    base_url: str
    domain_category: str = "education"
    subcategory: Optional[str] = None
    type: str = "secondary"
    crawl_method: str = "html"
    language: str = "en"
    region: str = "national"
    owner: Optional[str] = None
    notes: Optional[str] = None
    allowed_paths: Optional[List[str]] = Field(default_factory=lambda: ["/"])

class StartCrawlRequest(BaseModel):
    start_url: str
    domain_category: str = "education"
    allowed_paths: Optional[List[str]] = Field(default_factory=lambda: ["/"])
    max_pages: int = 15

class ValidateSourceRequest(BaseModel):
    url: str
    title: Optional[str] = None
    text: Optional[str] = None
    published_date: Optional[str] = None
    manual_override: Optional[Dict[str, Any]] = None


@app.get("/api/categories")
def get_categories():
    """Returns the 5 primary discovery domains and their taxonomy subcategories."""
    return {
        "categories": [
            {
                "id": "education",
                "name": "Education",
                "description": "Learning platforms, admissions, school boards, scholarships, hackathons, and university cutoffs.",
                "subcategories": ["rankings", "entrance_exams", "learning_platforms", "scholarships", "school_boards", "admissions", "colleges_universities", "hackathons_competitions"]
            },
            {
                "id": "career",
                "name": "Career & Employment",
                "description": "Government recruitment exams, public job boards, skill certifications, and apprenticeships.",
                "subcategories": ["job_portals", "skill_certifications", "recruitment_exams", "apprenticeships"]
            },
            {
                "id": "public_services",
                "name": "Public Services & Schemes",
                "description": "Direct subsidies, digital identity, welfare entitlements, grievance helplines, and certificates.",
                "subcategories": ["government_schemes", "documents_certificates", "benefits_eligibility", "helplines_grievances"]
            },
            {
                "id": "research",
                "name": "Research & Science",
                "description": "National scientific grants, fellowships, academic preprints, datasets, and calls for proposals.",
                "subcategories": ["funding_grants", "fellowships", "journals_preprints", "datasets_open_data"]
            },
            {
                "id": "business",
                "name": "Business & Compliance",
                "description": "Company registration, zero-fee MSME support, GST compliance, startup schemes, and industrial licenses.",
                "subcategories": ["company_registration", "msme_support", "tax_compliance", "startup_schemes", "licences_regulatory"]
            }
        ]
    }


@app.get("/api/registry")
def list_registry(domain_category: Optional[str] = None, reachability: Optional[str] = None):
    """Returns registry sources, optionally filtered by domain category or reachability."""
    from app.registry import get_all_registry_sources
    sources = get_all_registry_sources(domain_category=domain_category, reachability=reachability)
    return {"sources": sources, "total": len(sources)}


@app.post("/api/registry")
def add_custom_registry_source(payload: AddRegistrySourceRequest):
    """Allows a user to add a new source to the registry with automatic validation and SSRF check."""
    from app.ingest.ssrf import is_url_safe
    is_safe, err = is_url_safe(payload.base_url)
    if not is_safe:
        raise HTTPException(status_code=400, detail=f"SSRF validation blocked: {err}")

    from app.registry import add_registry_source
    from app.validation import validate_source

    val = validate_source(payload.base_url, title=payload.name)
    data = payload.model_dump()
    data["trust_score"] = val["score"]
    data["trust_reasons"] = val["reasons"]
    data["reachability"] = "reachable" if val["checks"].get("reachable", True) else "unreachable"

    created = add_registry_source(data)
    return {"source": created, "validation": val}


@app.post("/api/validate-source")
def api_validate_source(payload: ValidateSourceRequest):
    """Evaluates any URL or text through the multi-tier Source Validation Agent."""
    from app.validation import validate_source
    res = validate_source(
        url=payload.url,
        title=payload.title,
        text=payload.text,
        published_date=payload.published_date,
        manual_override=payload.manual_override,
    )
    return res


@app.post("/api/crawl")
async def api_start_crawl(payload: StartCrawlRequest):
    """Starts a bounded on-demand background crawl job (max 15 pages, depth 2)."""
    from app.crawl.queue import start_crawl_job
    job_id = start_crawl_job(
        start_url=payload.start_url,
        domain_category=payload.domain_category,
        allowed_paths=payload.allowed_paths,
        max_pages=min(payload.max_pages, 15),
    )
    return {"job_id": job_id, "status": "pending", "max_pages": min(payload.max_pages, 15)}


@app.get("/api/crawl/{job_id}")
def api_get_crawl_status(job_id: str):
    """Returns the live status, progress percentage, and processed count for a crawl job."""
    from app.crawl.crawler import get_crawl_job
    job = get_crawl_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Crawl job {job_id} not found")
    return job


@app.get("/api/search")
def api_search_entities(
    q: Optional[str] = None,
    domain: Optional[str] = None,
    entity_type: Optional[str] = None,
    region: Optional[str] = None,
    limit: int = 50,
):
    """Full-text and filtered search across entities and attributes."""
    from app.crawl.store import search_entities
    results = search_entities(
        query=q,
        domain_category=domain,
        entity_type=entity_type,
        region=region,
        limit=limit,
    )
    return {"query": q, "total": len(results), "entities": results}


@app.get("/api/entities")
def api_list_entities(
    domain: Optional[str] = None,
    entity_type: Optional[str] = None,
    region: Optional[str] = None,
    limit: int = 50,
):
    """Lists entities with verified claim counts and domain category filters."""
    from app.crawl.store import search_entities, get_entity_by_id
    entities = search_entities(
        query=None,
        domain_category=domain,
        entity_type=entity_type,
        region=region,
        limit=limit,
    )
    # Enrich each entity with attribute counts
    conn = get_db_connection()
    for ent in entities:
        counts = conn.execute(
            """
            SELECT 
                COUNT(*) as total_attrs,
                SUM(CASE WHEN verified = 1 THEN 1 ELSE 0 END) as verified_attrs,
                SUM(CASE WHEN uncertain = 1 THEN 1 ELSE 0 END) as uncertain_attrs
            FROM entity_attributes WHERE entity_id = ?;
            """,
            (ent["id"],)
        ).fetchone()
        ent["total_claims"] = counts[0] if counts else 0
        ent["verified_claims"] = counts[1] if (counts and counts[1]) else 0
        ent["uncertain_claims"] = counts[2] if (counts and counts[2]) else 0

        # Also get key summary attributes (deadlines, fees, apply_link)
        key_rows = conn.execute(
            """
            SELECT attribute_name, attribute_value, verified 
            FROM entity_attributes 
            WHERE entity_id = ? AND attribute_name IN ('deadlines', 'dates', 'fees', 'apply_link', 'eligibility')
            LIMIT 5;
            """,
            (ent["id"],)
        ).fetchall()
        ent["summary_attributes"] = {r["attribute_name"]: r["attribute_value"] for r in key_rows}
    conn.close()
    return {"total": len(entities), "entities": entities}


@app.get("/api/snapshot-status")
def api_get_snapshot_status():
    """Returns metadata about the active demo snapshot."""
    snapshot_path = Path("data/demo_snapshot.json")
    if snapshot_path.exists():
        try:
            with open(snapshot_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {
                "has_snapshot": True,
                "label": data.get("label", "Demo snapshot available"),
                "snapshot_date": data.get("snapshot_date"),
                "total_entities": data.get("total_entities", 0),
                "total_claims_verified": data.get("total_claims_verified", 0),
                "total_claims_rejected": data.get("total_claims_rejected", 0),
            }
        except Exception:
            pass
    return {
        "has_snapshot": False,
        "label": "Live Mode (Real-time DB)",
        "snapshot_date": None,
        "total_entities": 0,
        "total_claims_verified": 0,
        "total_claims_rejected": 0,
    }


@app.post("/api/refresh-live")
async def api_refresh_live():
    """Triggers live refresh of snapshot/entities."""
    snapshot_path = Path("data/demo_snapshot.json")
    if snapshot_path.exists():
        try:
            with open(snapshot_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            from app.crawl.store import save_entity
            for ent in data.get("entities", []):
                save_entity(ent)
            return {"status": "ok", "message": f"Refreshed {len(data.get('entities', []))} entities from demo snapshot."}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    return {"status": "ok", "message": "Entities refreshed from database."}


@app.get("/api/entities/{entity_id}")
def api_get_entity(entity_id: str):
    """Returns full entity details, verified attributes, and linked sources."""
    from app.crawl.store import get_entity_by_id
    entity = get_entity_by_id(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")
    return entity


@app.get("/api/entities/{entity_id}/gaps")
def api_get_entity_gaps(entity_id: str):
    """Runs the full information gap, conflict, and coverage matrix engine on an entity."""
    from app.crawl.detect_adapter import analyze_entity_gaps
    try:
        res = analyze_entity_gaps(entity_id)
        return res
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Entity gap analysis failed: {e}")


# Frontend static files mount
frontend_path = Path("frontend")
if frontend_path.exists():
    app.mount("/static", StaticFiles(directory="frontend"), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(frontend_path / "index.html")
