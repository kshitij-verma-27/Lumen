import re
from typing import List, Dict, Any, Optional
from app.database import get_db_connection, row_to_dict


def find_source_emails(session_id: str, conn: Optional[Any] = None) -> List[Dict[str, Any]]:
    """
    Scans fetched sources in the session for explicit email addresses.
    Returns matching addresses along with the verbatim quote and source title.
    Never invents or fabricates an address.
    """
    should_close = False
    if conn is None:
        conn = get_db_connection()
        should_close = True

    rows = conn.execute("""
        SELECT id, title, url, authority, text
        FROM sources
        WHERE session_id = ?
        ORDER BY CASE authority WHEN 'official' THEN 1 WHEN 'secondary' THEN 2 ELSE 3 END, fetched_at ASC
    """, (session_id,)).fetchall()

    email_regex = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')
    discovered = []

    for r in rows:
        text = r["text"] or ""
        matches = list(email_regex.finditer(text))
        for m in matches:
            email_addr = m.group(0)
            if email_addr.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".svg")):
                continue
            # Extract surrounding context quote
            start = max(0, m.start() - 50)
            end = min(len(text), m.end() + 50)
            quote = text[start:end].strip().replace("\n", " ")
            discovered.append({
                "email": email_addr,
                "quote": f"...{quote}...",
                "source_id": r["id"],
                "source_title": r["title"] or "Source Document",
                "authority": r["authority"]
            })
            break

    if should_close:
        conn.close()

    return discovered


def generate_email_draft(
    gap: Dict[str, Any],
    official_domain: Optional[str] = None,
    target_period: Optional[str] = None,
    goal: Optional[str] = None,
    discovered_contact: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generates a concise, professional draft email/query to the official body.
    Never invents email addresses:
    - If an email appears in a fetched source, uses it with the exact quote.
    - Otherwise, sets recipient to 'Find the official contact on {domain}'.
    """
    domain = (official_domain or "official-portal.org").strip()
    if "/" in domain:
        domain = domain.split("/")[0]

    facet_name = gap.get("facet_name") or gap.get("facet") or "Guidelines & Requirements"
    gap_type = gap.get("gap_type", "gap")
    details = gap.get("details") or gap.get("action") or ""
    action = gap.get("action") or ""
    period_str = f" ({target_period})" if target_period else ""

    # Subject line
    subject = f"Clarification Request: {facet_name}{period_str} - Official Inquiry"

    # Contact address resolution: NEVER invent addresses
    if discovered_contact and discovered_contact.get("email"):
        contact_email = discovered_contact["email"]
        recipient_quote = discovered_contact.get("quote")
        recipient_source = discovered_contact.get("source_title")
        recipient_label = f"{contact_email} (from {recipient_source}: “{recipient_quote}”)"
    else:
        contact_email = f"Find the official contact on {domain}"
        recipient_quote = None
        recipient_source = None
        recipient_label = f"Find the official contact on {domain}"

    # Body composition
    greeting = f"Dear {domain} Administrative / Support Team,"
    
    if gap_type == "conflict":
        problem_desc = (
            f"During our review of published documentation, we identified conflicting information regarding '{facet_name}':\n"
            f"• Issue: {details}\n\n"
            f"Could you please confirm the authoritative specification, correct figure/criterion, and official status for {target_period or 'the current period'}?"
        )
    elif gap_type == "dark_spot":
        problem_desc = (
            f"We are reviewing requirements for '{facet_name}' but could not locate official guidance in recent public releases.\n"
            f"• Inquiry: {action or details}\n\n"
            f"Could you please confirm whether '{facet_name}' is applicable, and if so, provide the official terms or documentation link?"
        )
    elif gap_type == "deadline_passed":
        problem_desc = (
            f"The published schedule indicates that the deadline for '{facet_name}' may have passed relative to today.\n"
            f"• Detail: {details}\n\n"
            f"Could you please confirm if any extension has been granted or when the next application/submission window will open?"
        )
    elif gap_type == "partial_overlap":
        problem_desc = (
            f"Different official circulars and references specify overlapping lists for '{facet_name}'.\n"
            f"• Variation: {details}\n\n"
            f"Could you please confirm which items are strictly mandatory versus optional?"
        )
    elif gap_type in ("time_difference", "version_period_difference", "outdated"):
        problem_desc = (
            f"We observed changes or differences between past and current versions for '{facet_name}'.\n"
            f"• Observation: {details}\n\n"
            f"Could you please confirm the latest active revision for {target_period or 'the current cycle'}?"
        )
    else:
        problem_desc = (
            f"We are seeking official verification regarding '{facet_name}':\n"
            f"• Note: {details or action}\n\n"
            f"Could you please confirm the official specifications on this matter?"
        )

    closing = "Thank you for your time and assistance.\n\nSincerely,\nResearch & Verification Team"

    body = f"{greeting}\n\n{problem_desc}\n\n{closing}"

    return {
        "gap_id": gap.get("id") or f"gap_{gap.get('facet')}",
        "facet_id": gap.get("facet"),
        "facet_name": facet_name,
        "recipient": contact_email,
        "recipient_quote": recipient_quote,
        "recipient_source": recipient_source,
        "recipient_label": recipient_label,
        "subject": subject,
        "body": body
    }


def get_session_email_drafts(session_id: str, gaps: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Returns email drafts for all unresolved gaps in a research session.
    """
    conn = get_db_connection()
    sess_row = conn.execute("SELECT * FROM research_sessions WHERE id = ?", (session_id,)).fetchone()
    conn.close()

    if not sess_row:
        raise ValueError(f"Session '{session_id}' not found.")

    sess = row_to_dict(sess_row)
    official_domain = sess.get("official_domain")
    target_period = sess.get("target_version_period") or sess.get("target_cycle")
    goal = sess.get("goal")

    # Discover any explicit emails in fetched sources
    discovered = find_source_emails(session_id)
    best_contact = discovered[0] if discovered else None

    if gaps is None:
        from app.detect import run_gap_detection
        det = run_gap_detection(session_id)
        gaps = det.get("gaps", [])

    drafts = []
    for g in gaps:
        d = generate_email_draft(
            g,
            official_domain=official_domain,
            target_period=target_period,
            goal=goal,
            discovered_contact=best_contact
        )
        drafts.append(d)

    return {
        "session_id": session_id,
        "official_domain": official_domain,
        "target_version_period": target_period,
        "discovered_contact": best_contact,
        "count": len(drafts),
        "email_drafts": drafts
    }
