import logging
import os
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def red_team_source_check(
    url: str,
    title: str,
    text: str,
    current_trust: str,
    reasons: List[str]
) -> Tuple[bool, List[str]]:
    """
    Adversarial red-team pass: tries to find grounds to refute an 'official' classification
    before it is permanently awarded.
    Returns: (survived: bool, red_team_reasons: List[str])
    """
    if current_trust != "official":
        return True, []

    red_team_objections = []
    parsed = urlparse(url)
    domain = parsed.netloc.split(":")[0].lower()
    text_lower = text.lower()

    # Objection 1: Commercial or blog TLD claiming official authority without statutory backing
    commercial_tlds = (".com", ".org", ".in", ".net", ".info", ".xyz", ".biz")
    is_commercial = any(domain.endswith(tld) for tld in commercial_tlds) and not (
        domain.endswith(".gov.in") or domain.endswith(".nic.in") or domain.endswith(".ac.in") or domain.endswith(".res.in")
    )

    if is_commercial:
        # Check if text contains blog / affiliate disclaimers
        if "not affiliated with" in text_lower or "unofficial" in text_lower or "information purposes only" in text_lower:
            red_team_objections.append(
                f"Red-team refutation: Site explicitly disclaims official affiliation ('{domain}')"
            )
        elif "advertisement" in text_lower or "sponsored" in text_lower:
            red_team_objections.append(
                f"Red-team refutation: Contains commercial ad copy and affiliate signals on non-gov host '{domain}'"
            )
        elif not any(keyword in text_lower for keyword in ("gazette", "statutory", "act of parliament", "autonomous institute", "council")):
            red_team_objections.append(
                f"Red-team refutation: Non-statutory domain '{domain}' lacks statutory issuing mandate in document text"
            )

    # Objection 2: High copycat phrase density
    copied_markers = [
        "source: internet",
        "collected from various websites",
        "we do not take responsibility",
        "readers are advised to check official website",
    ]
    for marker in copied_markers:
        if marker in text_lower:
            red_team_objections.append(
                f"Red-team refutation: Document admits secondary aggregation: '{marker}'"
            )
            break

    survived = len(red_team_objections) == 0
    return survived, red_team_objections
