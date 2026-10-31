import json
import html
from datetime import datetime, timezone
from typing import Dict, Any, List

from app.database import get_db_connection, row_to_dict
from app.detect import run_gap_detection
from app.email_drafts import get_session_email_drafts
from app.independence import detect_and_group_sources


def build_audit_trail_data(session_id: str) -> Dict[str, Any]:
    """
    Assembles a comprehensive audit trail data packet containing every finding,
    exact quotes, source provenance, hashes, timestamps, and red-team audits.
    """
    conn = get_db_connection()
    sess_row = conn.execute("SELECT * FROM research_sessions WHERE id = ?", (session_id,)).fetchone()
    if not sess_row:
        conn.close()
        raise ValueError(f"Session '{session_id}' not found.")

    sess = row_to_dict(sess_row)

    # Parse facets
    facets = []
    try:
        facets = json.loads(sess.get("facets_json") or "[]")
    except Exception:
        facets = []
    facet_map = {f.get("id"): f.get("name") for f in facets}

    # Fetch sources
    src_rows = conn.execute("SELECT * FROM sources WHERE session_id = ? ORDER BY fetched_at ASC", (session_id,)).fetchall()
    sources = [row_to_dict(r) for r in src_rows]
    source_map = {s["id"]: s for s in sources}

    # Independence grouping
    indep = detect_and_group_sources(session_id, conn)

    # Fetch claims
    claim_rows = conn.execute("""
        SELECT c.*, s.title as source_title, s.url as source_url, s.authority as source_authority,
               s.content_hash as source_content_hash, s.fetched_at as source_fetched_at,
               s.last_checked_at as source_last_checked_at
        FROM claims c
        JOIN sources s ON c.source_id = s.id
        WHERE c.session_id = ?
        ORDER BY c.facet ASC, c.verified DESC
    """, (session_id,)).fetchall()

    claims = [row_to_dict(r) for r in claim_rows]
    conn.close()

    # Gap detection & drafts
    det_results = run_gap_detection(session_id)
    email_drafts = get_session_email_drafts(session_id, gaps=det_results.get("gaps", []))

    # Findings formatting
    findings = []
    for c in claims:
        fid = c.get("facet")
        findings.append({
            "claim_id": c.get("id"),
            "facet_id": fid,
            "facet_name": facet_map.get(fid, fid),
            "value_raw": c.get("value_raw"),
            "value_normalized": c.get("value_normalized"),
            "exact_quote": c.get("exact_quote"),
            "scope": c.get("scope"),
            "version_period": c.get("version_period") or c.get("cycle"),
            "verified": bool(c.get("verified")),
            "verification_score": c.get("verification_score"),
            "rejection_reason": c.get("rejection_reason"),
            "survived_redteam": bool(c.get("survived_redteam", 1)),
            "redteam_status": c.get("redteam_status") or ("survived" if c.get("survived_redteam", 1) else "uncertain"),
            "redteam_notes": c.get("redteam_notes"),
            "source_id": c.get("source_id"),
            "source_title": c.get("source_title"),
            "source_url": c.get("source_url"),
            "source_authority": c.get("source_authority"),
            "source_content_hash": c.get("source_content_hash"),
            "source_fetched_at": c.get("source_fetched_at"),
            "source_last_checked_at": c.get("source_last_checked_at")
        })

    # Stats
    total_findings = len(findings)
    verified_findings = sum(1 for f in findings if f["verified"])
    survived_redteam = sum(1 for f in findings if f["survived_redteam"] and f["verified"])
    demoted_redteam = sum(1 for f in findings if not f["survived_redteam"] or f["redteam_status"] == "uncertain")

    return {
        "export_type": "lumen_audit_trail",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "session": {
            "id": sess.get("id"),
            "goal": sess.get("goal"),
            "domain_type": sess.get("domain_type"),
            "official_domain": sess.get("official_domain"),
            "target_version_period": sess.get("target_version_period") or sess.get("target_cycle"),
            "created_at": sess.get("created_at")
        },
        "stats": {
            "total_sources": len(sources),
            "independent_originals": indep.get("independent_count", len(sources)),
            "independence_badge": indep.get("badge_text", f"{len(sources)} sources"),
            "total_extracted_claims": total_findings,
            "verified_claims": verified_findings,
            "redteam_survived": survived_redteam,
            "redteam_demoted": demoted_redteam,
            "redteam_counter": f"{total_findings} extracted, {survived_redteam} survived, {demoted_redteam} demoted",
            "active_conflicts": len(det_results.get("conflicts", [])),
            "dark_spots": len(det_results.get("dark_spots", []))
        },
        "sources": sources,
        "findings": findings,
        "gaps_and_conflicts": det_results.get("gaps", []),
        "action_checklist": det_results.get("action_checklist", []),
        "email_drafts": email_drafts.get("email_drafts", [])
    }


def generate_printable_html_report(session_id: str) -> str:
    """
    Generates a standalone, beautiful, print-ready HTML audit trail document.
    """
    data = build_audit_trail_data(session_id)
    sess = data["session"]
    stats = data["stats"]
    sources = data["sources"]
    findings = data["findings"]
    gaps = data["gaps_and_conflicts"]
    drafts = data["email_drafts"]

    # Build findings HTML rows
    findings_rows_html = []
    for f in findings:
        status_badge = '<span class="badge verified">✓ Verified</span>' if f["verified"] else f'<span class="badge rejected">✗ Rejected ({html.escape(f.get("rejection_reason") or "unverified")})</span>'
        redteam_badge = ""
        if f["verified"]:
            if f["survived_redteam"] and f["redteam_status"] != "uncertain":
                redteam_badge = '<span class="badge redteam-survived">🛡️ Red-Team Survived</span>'
            else:
                redteam_badge = f'<span class="badge redteam-uncertain" title="{html.escape(f.get("redteam_notes") or "")}">⚠️ Uncertain (Demoted)</span>'

        row = f"""
        <tr>
            <td style="font-weight:600; width:160px;">{html.escape(f['facet_name'])}</td>
            <td style="width:160px;"><strong>{html.escape(str(f['value_raw']))}</strong><br><small style="color:#64748b;">Scope: {html.escape(f['scope'])} | Period: {html.escape(str(f['version_period'] or 'N/A'))}</small></td>
            <td>
                <blockquote style="margin:0; padding:6px 12px; background:#f8fafc; border-left:3px solid #3b82f6; font-size:12px; font-style:italic;">
                    "{html.escape(f['exact_quote'])}"
                </blockquote>
                {f'<div style="font-size:11px; color:#b91c1c; margin-top:4px;"><strong>Red-team Note:</strong> {html.escape(f["redteam_notes"])}</div>' if f.get('redteam_notes') and f['redteam_status'] == 'uncertain' else ''}
            </td>
            <td style="width:180px; font-size:12px;">
                <strong>{html.escape(f['source_title'] or 'Source')}</strong><br>
                <span class="badge auth-{f['source_authority']}">{html.escape(f['source_authority'].upper())}</span><br>
                <code style="font-size:10px; color:#64748b; word-break:break-all;">hash: {html.escape((f['source_content_hash'] or '')[:16])}...</code>
            </td>
            <td style="width:140px; text-align:center;">
                {status_badge}<br>{redteam_badge}
            </td>
        </tr>
        """
        findings_rows_html.append(row)

    # Build sources HTML rows
    sources_rows_html = []
    for s in sources:
        sources_rows_html.append(f"""
        <tr>
            <td style="font-weight:600;">{html.escape(s.get('title') or s.get('id'))}</td>
            <td><a href="{html.escape(s.get('url') or '#')}" target="_blank" style="color:#2563eb; word-break:break-all;">{html.escape(s.get('url') or 'Pasted / Direct Text')}</a></td>
            <td><span class="badge auth-{s.get('authority')}">{html.escape(str(s.get('authority')).upper())}</span></td>
            <td><code style="font-size:11px;">{html.escape(s.get('content_hash') or 'N/A')}</code></td>
            <td style="font-size:12px; color:#475569;">{html.escape(s.get('fetched_at') or 'N/A')}</td>
        </tr>
        """)

    # Gaps HTML
    gaps_html = []
    for g in gaps:
        prio_color = "#dc2626" if g.get("priority") == "critical" else ("#ea580c" if g.get("priority") == "high" else "#0284c7")
        gaps_html.append(f"""
        <div style="border-left:4px solid {prio_color}; background:#fff; padding:10px 14px; margin-bottom:10px; border-radius:0 6px 6px 0; box-shadow:0 1px 3px rgba(0,0,0,0.05);">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <strong style="color:#0f172a; font-size:14px;">{html.escape(g.get('title') or g.get('facet_name') or 'Finding')}</strong>
                <span class="badge" style="background:{prio_color}; color:#fff; font-size:10px;">{html.escape(str(g.get('priority', '')).upper())}</span>
            </div>
            <p style="margin:4px 0 6px 0; font-size:12px; color:#334155;">{html.escape(g.get('action') or g.get('details') or '')}</p>
        </div>
        """)

    # Drafts HTML
    drafts_html = []
    for d in drafts:
        drafts_html.append(f"""
        <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:6px; padding:12px; margin-bottom:12px;">
            <div style="font-size:13px; font-weight:600; color:#0f172a; margin-bottom:4px;">✉️ {html.escape(d.get('subject'))}</div>
            <div style="font-size:11px; color:#64748b; margin-bottom:8px;"><strong>To:</strong> {html.escape(d.get('recipient'))}</div>
            <pre style="white-space:pre-wrap; background:#fff; border:1px solid #cbd5e1; padding:8px 10px; font-size:11px; font-family:monospace; border-radius:4px; color:#1e293b; margin:0;">{html.escape(d.get('body'))}</pre>
        </div>
        """)

    html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Audit Trail - {html.escape(sess.get('goal') or 'Lumen Verification Report')}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            color: #0f172a;
            background: #f1f5f9;
            margin: 0;
            padding: 24px;
        }}
        .report-card {{
            max-width: 1000px;
            margin: 0 auto;
            background: #ffffff;
            border-radius: 12px;
            padding: 32px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }}
        .header {{
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 20px;
            margin-bottom: 24px;
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
        }}
        .header h1 {{ margin: 0 0 6px 0; font-size: 22px; color: #0284c7; }}
        .header p {{ margin: 0; font-size: 13px; color: #64748b; }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 12px;
            margin-bottom: 28px;
        }}
        .stat-box {{
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 12px;
            text-align: center;
        }}
        .stat-num {{ font-size: 20px; font-weight: 700; color: #0f172a; }}
        .stat-lbl {{ font-size: 11px; text-transform: uppercase; color: #64748b; margin-top: 4px; }}
        h2 {{ font-size: 16px; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px; margin: 28px 0 14px 0; color: #1e293b; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
            margin-bottom: 20px;
        }}
        th, td {{
            border: 1px solid #e2e8f0;
            padding: 8px 10px;
            text-align: left;
            vertical-align: top;
        }}
        th {{ background: #f8fafc; font-weight: 600; color: #475569; }}
        .badge {{
            display: inline-block;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 600;
            margin-bottom: 2px;
        }}
        .verified {{ background: #dcfce7; color: #15803d; }}
        .rejected {{ background: #fee2e2; color: #b91c1c; }}
        .redteam-survived {{ background: #e0f2fe; color: #0369a1; }}
        .redteam-uncertain {{ background: #fef3c7; color: #b45309; }}
        .auth-official {{ background: #dbeafe; color: #1e40af; }}
        .auth-secondary {{ background: #e0e7ff; color: #3730a3; }}
        .auth-low {{ background: #f1f5f9; color: #64748b; }}
        .print-btn {{
            background: #0284c7;
            color: #ffffff;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
        }}
        .print-btn:hover {{ background: #0369a1; }}
        @media print {{
            body {{ background: #fff; padding: 0; }}
            .report-card {{ box-shadow: none; border-radius: 0; padding: 0; max-width: 100%; }}
            .no-print {{ display: none !important; }}
            tr {{ page-break-inside: avoid; }}
        }}
    </style>
</head>
<body>
    <div class="report-card">
        <div class="header">
            <div>
                <h1>Lumen Information-Gap & Evidence Audit Trail</h1>
                <p><strong>Goal:</strong> {html.escape(sess.get('goal') or 'Research Session')} | <strong>Official Domain:</strong> {html.escape(sess.get('official_domain') or 'N/A')}</p>
                <p style="margin-top:3px;"><strong>Target Period:</strong> {html.escape(str(sess.get('target_version_period') or 'N/A'))} | <strong>Exported:</strong> {html.escape(data['exported_at'])}</p>
            </div>
            <div class="no-print">
                <button class="print-btn" onclick="window.print()">🖨️ Print / Save PDF</button>
            </div>
        </div>

        <div class="stats-grid">
            <div class="stat-box">
                <div class="stat-num">{stats['total_sources']}</div>
                <div class="stat-lbl">Sources ({stats['independence_badge']})</div>
            </div>
            <div class="stat-box">
                <div class="stat-num">{stats['verified_claims']}/{stats['total_extracted_claims']}</div>
                <div class="stat-lbl">Verified Claims</div>
            </div>
            <div class="stat-box">
                <div class="stat-num" style="color:#0284c7;">{stats['redteam_survived']}</div>
                <div class="stat-lbl">Red-Team Survived ({stats['redteam_demoted']} Demoted)</div>
            </div>
            <div class="stat-box">
                <div class="stat-num" style="color:#dc2626;">{stats['active_conflicts']} / {stats['dark_spots']}</div>
                <div class="stat-lbl">Conflicts / Dark Spots</div>
            </div>
        </div>

        <h2>1. Verified Findings & Exact Evidence Proofs</h2>
        <table>
            <thead>
                <tr>
                    <th>Target Facet</th>
                    <th>Extracted Value</th>
                    <th>Exact Verbatim Quote & Proof</th>
                    <th>Source & Content Hash</th>
                    <th>Verification Audit</th>
                </tr>
            </thead>
            <tbody>
                {''.join(findings_rows_html)}
            </tbody>
        </table>

        <h2>2. Source Provenance & Content Hash Registry</h2>
        <table>
            <thead>
                <tr>
                    <th>Source Document Title</th>
                    <th>URL / Origin</th>
                    <th>Authority</th>
                    <th>SHA-256 Content Hash</th>
                    <th>Fetch Timestamp</th>
                </tr>
            </thead>
            <tbody>
                {''.join(sources_rows_html)}
            </tbody>
        </table>

        <h2>3. Information Gaps, Conflicts & Missing Dark Spots</h2>
        {''.join(gaps_html) if gaps_html else '<p style="font-size:12px; color:#64748b;">No outstanding conflicts or gaps detected.</p>'}

        <h2>4. Actionable Email Drafts for Official Authorities</h2>
        {''.join(drafts_html) if drafts_html else '<p style="font-size:12px; color:#64748b;">No inquiries drafted.</p>'}
    </div>
</body>
</html>
"""
    return html_template
