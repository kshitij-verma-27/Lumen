import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse
from rapidfuzz.distance import Levenshtein

# Common homoglyph mappings (Cyrillic, Greek, lookalikes -> Latin)
HOMOGLYPH_MAP = {
    'а': 'a', 'с': 'c', 'е': 'e', 'о': 'o', 'р': 'p', 'х': 'x', 'у': 'y',
    'і': 'i', 'ј': 'j', 'ѕ': 's', 'ԁ': 'd', 'ԛ': 'q', 'ԝ': 'w',
    '0': 'o', '1': 'l', '3': 'e', '5': 's', '8': 'b',
}

KNOWN_OFFICIAL_DOMAINS = [
    "scholarships.gov.in",
    "nta.ac.in",
    "upsc.gov.in",
    "ssc.gov.in",
    "swayam.gov.in",
    "nptel.ac.in",
    "ncert.nic.in",
    "aicte-india.org",
    "ugc.gov.in",
    "sih.gov.in",
    "diksha.gov.in",
    "ncs.gov.in",
    "skillindiadigital.gov.in",
    "india.gov.in",
    "mygov.in",
    "digilocker.gov.in",
    "umang.gov.in",
    "pmsuryaghar.gov.in",
    "anrfonline.in",
    "dst.gov.in",
    "csirhrdg.res.in",
    "data.gov.in",
    "startupindia.gov.in",
    "udyamregistration.gov.in",
    "gst.gov.in",
    "mca.gov.in",
    "dpiit.gov.in",
]


def normalize_domain_homoglyphs(domain: str) -> str:
    """Replaces common homoglyph characters with standard latin characters."""
    normalized = []
    for char in domain.lower():
        normalized.append(HOMOGLYPH_MAP.get(char, char))
    return "".join(normalized)


def extract_domain_from_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        netloc = (parsed.netloc or url).lower().split(":")[0]
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return url.lower()


def detect_lookalike(
    candidate_url_or_domain: str,
    registry_domains: Optional[List[str]] = None
) -> Tuple[bool, Optional[str], float, List[str]]:
    """
    Detects if a candidate domain is a typosquat, homoglyph, or deceptive lookalike
    of a known official or registry domain.
    Returns: (is_lookalike, matched_target, similarity_ratio, reasons)
    """
    candidate = extract_domain_from_url(candidate_url_or_domain)
    candidate_norm = normalize_domain_homoglyphs(candidate)

    targets = list(set((registry_domains or []) + KNOWN_OFFICIAL_DOMAINS))
    reasons = []

    # If candidate is already an exact official domain, it's not a lookalike
    if candidate in targets:
        return False, None, 1.0, []

    for target in targets:
        target_clean = extract_domain_from_url(target)
        if candidate == target_clean:
            continue

        target_base = target_clean.split(".")[0]
        candidate_base = candidate.split(".")[0]

        # 1. Check if candidate mimics gov/nic domain on a commercial TLD
        # e.g., scholarships-gov.in, scholarshipsgov.in, udyamregistration.com, pmsuryaghar.org
        if target_clean.endswith(".gov.in") or target_clean.endswith(".nic.in"):
            official_keyword = target_clean.replace(".gov.in", "").replace(".nic.in", "").replace("-", "")
            cand_no_punct = candidate.replace("-", "").replace(".", "")

            if official_keyword in cand_no_punct and not (candidate.endswith(".gov.in") or candidate.endswith(".nic.in")):
                reasons.append(
                    f"Lookalike: domain mimics official portal '{target_clean}' on non-government extension '{candidate.split('.')[-1]}'"
                )
                return True, target_clean, 0.95, reasons

        # 2. Homoglyph difference
        if candidate != candidate_norm:
            dist = Levenshtein.distance(candidate_norm, target_clean)
            if dist <= 2:
                reasons.append(f"Homoglyph attack detected: character substitution mimicking '{target_clean}'")
                return True, target_clean, 0.90, reasons

        # 3. Levenshtein edit distance check on full domain or base name
        dist_full = Levenshtein.distance(candidate, target_clean)
        if 1 <= dist_full <= 2 and len(target_clean) >= 8:
            reasons.append(f"Typosquat: domain is only {dist_full} character(s) different from official '{target_clean}'")
            return True, target_clean, 0.88, reasons

        # 4. Base name similarity with hyphen additions: e.g. "nta-exam.in" vs "nta.ac.in"
        if candidate_base.startswith(target_base + "-") or candidate_base.endswith("-" + target_base):
            if not (candidate.endswith(".gov.in") or candidate.endswith(".nic.in") or candidate.endswith(".ac.in")):
                reasons.append(f"Deceptive name affix: domain uses official brand name '{target_base}' with hyphens on unofficial host")
                return True, target_clean, 0.85, reasons

    return False, None, 0.0, []
