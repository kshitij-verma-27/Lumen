from datetime import datetime
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse
import dateparser


def assess_content_quality(
    url: str,
    text: str,
    published_date: Optional[str] = None
) -> Tuple[int, List[str], Dict[str, bool]]:
    """
    Evaluates basic content quality, contact information, freshness, and structural integrity.
    Returns: (quality_score_delta, reasons, check_results)
    """
    checks = {}
    reasons = []
    score = 0

    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    domain = parsed.netloc.split(":")[0].lower()

    # 1. HTTPS Valid
    is_https = scheme == "https"
    checks["https_valid"] = is_https
    if is_https:
        score += 15
        reasons.append("HTTPS encrypted connection verified")
    else:
        score -= 25
        reasons.append("Insecure plain HTTP connection (no TLS)")

    # 2. Thin content check
    from app.ingest.text_extractor import check_thin_page
    is_thin, thin_msg = check_thin_page(text, text)
    checks["adequate_content_length"] = not is_thin
    if is_thin:
        score -= 30
        reasons.append(thin_msg or f"Thin content warning: document contains only {len(text.split())} words")
    else:
        score += 10

    # 3. Contact details present
    email_match = re.search(r"[a-zA-Z0-9_.+-]+@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", text)
    phone_match = re.search(r"\b(?:\+91[-\s]?)?[6-9]\d{9}\b|\b011[-\s]?\d{7,8}\b|\b1800[-\s]?\d{3}[-\s]?\d{3,4}\b", text)
    has_contact = bool(email_match or phone_match)
    checks["contact_details_present"] = has_contact

    if has_contact:
        score += 10
        if email_match:
            contact_domain = email_match.group(1).lower()
            if contact_domain in domain or domain.endswith("." + contact_domain) or contact_domain.endswith(".gov.in"):
                reasons.append(f"Official contact details verified: {email_match.group(0)}")
                score += 5
            else:
                reasons.append(f"Contact email domain ({contact_domain}) differs from website host ({domain})")
    else:
        score -= 10
        reasons.append("No visible contact telephone or email found on page")

    # 4. Date freshness
    checks["visible_date"] = bool(published_date)
    if published_date:
        parsed_d = dateparser.parse(published_date)
        if parsed_d:
            years_old = (datetime.utcnow() - parsed_d).days / 365.25
            if years_old > 2.0:
                score -= 15
                reasons.append(f"Stale content notice: publication date ({published_date}) is over 2 years old")
            else:
                score += 10
                reasons.append(f"Fresh official updates visible (dated {published_date})")
    else:
        score -= 5
        reasons.append("Publication date not explicitly declared")

    return score, reasons, checks
