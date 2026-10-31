from datetime import datetime
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from app.ingest.models import Document
from app.registry import find_registry_match_by_url, get_all_registry_sources
from app.validation.lookalike import detect_lookalike, extract_domain_from_url
from app.validation.scam_detect import detect_scam_signals
from app.validation.quality import assess_content_quality
from app.validation.red_team_pass import red_team_source_check

logger = logging.getLogger(__name__)


def validate_source(
    url: str,
    title: Optional[str] = None,
    text: Optional[str] = None,
    published_date: Optional[str] = None,
    manual_override: Optional[Dict[str, Any]] = None,
    document: Optional[Document] = None,
) -> Dict[str, Any]:
    """
    Validates a source through a multi-tier deterministic, scam, lookalike,
    quality, and red-team evaluation pipeline.
    """
    validated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    # If document provided, extract text and metadata
    if document:
        url = document.url or url
        title = document.title or title or ""
        text = document.text or text or ""
        published_date = document.published_date or published_date
        if document.status in ("blocked", "unreachable"):
            return {
                "trust_level": "blocked",
                "score": 0,
                "reasons": [f"Source unreachable or blocked: {document.error or 'Connection failed'}"],
                "checks": {
                    "reachable": False,
                    "robots_allowed": document.status != "disallowed",
                    "https_valid": url.startswith("https://"),
                },
                "validated_at": validated_at,
                "manual_override": manual_override,
            }

    title = title or ""
    text = text or ""
    parsed = urlparse(url)
    domain = extract_domain_from_url(url)
    scheme = parsed.scheme.lower()

    score = 50  # Baseline neutral score
    reasons: List[str] = []
    checks: Dict[str, Any] = {
        "reachable": True,
        "robots_allowed": True,
    }

    # 1. Manual Override check
    if manual_override and manual_override.get("trust_level"):
        override_level = manual_override["trust_level"]
        note = manual_override.get("note", "Manual administrator override")
        return {
            "trust_level": override_level,
            "score": 100 if override_level == "official" else 75 if override_level == "secondary" else 30,
            "reasons": [f"Manual override applied: {note}"],
            "checks": checks,
            "validated_at": validated_at,
            "manual_override": manual_override,
        }

    # 2. Lookalike Detection
    registry_sources = get_all_registry_sources()
    reg_domains = [extract_domain_from_url(s.get("base_url", "")) for s in registry_sources]

    is_lookalike, matched_target, sim_score, lookalike_reasons = detect_lookalike(url, reg_domains)
    checks["lookalike_detected"] = is_lookalike
    if is_lookalike:
        score = 5  # Immediate severe demotion
        reasons.extend(lookalike_reasons)
        return {
            "trust_level": "suspicious",
            "score": score,
            "reasons": reasons[:3],
            "checks": checks,
            "validated_at": validated_at,
            "manual_override": None,
        }

    # 3. Scam Signals Detection
    scam_found, scam_signals, scam_penalty = detect_scam_signals(url, text)
    checks["scam_signals_found"] = scam_found
    if scam_found:
        score = max(0, score - scam_penalty)
        reasons.extend(scam_signals)
        return {
            "trust_level": "suspicious",
            "score": min(score, 15),
            "reasons": reasons[:3],
            "checks": checks,
            "validated_at": validated_at,
            "manual_override": None,
        }

    # 4. Registry Matching
    reg_match = find_registry_match_by_url(url)
    checks["in_official_registry"] = bool(reg_match)
    if reg_match:
        score += 35
        reasons.append(f"Verified official registry source: {reg_match.get('name')}")
        if reg_match.get("owner"):
            reasons.append(f"Issuing body: {reg_match['owner']}")

    # 5. Domain Class Evaluation
    is_gov = domain.endswith(".gov.in") or domain.endswith(".nic.in")
    is_academic = domain.endswith(".ac.in") or domain.endswith(".edu") or domain.endswith(".res.in")
    checks["domain_class_official"] = is_gov or is_academic

    if is_gov:
        score += 30
        reasons.append("Official government domain (.gov.in / .nic.in)")
    elif is_academic:
        score += 20
        reasons.append("Recognized academic / research domain (.ac.in / .res.in)")
    elif any(domain.endswith(t) for t in (".org", ".edu.in")):
        score += 10
        reasons.append("Institutional organization domain")
    elif any(domain.endswith(t) for t in (".com", ".in", ".co.in", ".net")):
        score -= 5
        reasons.append("Commercial or generic domain extension")

    # 6. Content Quality & Freshness Assessment
    q_score, q_reasons, q_checks = assess_content_quality(url, text, published_date)
    score += q_score
    reasons.extend(q_reasons)
    checks.update(q_checks)

    # 7. Normalize Score
    final_score = max(0, min(100, score))

    # 8. Preliminary Trust Level Assignment
    if final_score >= 85 and (is_gov or (reg_match and reg_match.get("type") == "official")):
        trust_level = "official"
    elif final_score >= 65:
        trust_level = "secondary"
    elif final_score >= 45:
        trust_level = "community"
    elif final_score >= 20:
        trust_level = "low"
    else:
        trust_level = "suspicious"

    # 9. Red-Team Adversarial Pass for "official" candidates
    if trust_level == "official":
        survived, red_team_objections = red_team_source_check(url, title, text, trust_level, reasons)
        checks["red_team_survived"] = survived
        if not survived:
            trust_level = "secondary"  # Demote candidate
            final_score = min(final_score, 78)
            reasons.extend(red_team_objections)
        else:
            reasons.append("Passed adversarial red-team refutation check")
    else:
        checks["red_team_survived"] = True

    # Build top 3 distinct reasons for trust badge
    distinct_reasons = []
    for r in reasons:
        if r not in distinct_reasons:
            distinct_reasons.append(r)

    return {
        "trust_level": trust_level,
        "score": final_score,
        "reasons": distinct_reasons[:3],
        "all_reasons": distinct_reasons,
        "checks": checks,
        "validated_at": validated_at,
        "manual_override": manual_override,
    }
