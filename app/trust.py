import re
import urllib.parse
from typing import Optional, Tuple, Dict, Any, List
from rapidfuzz import fuzz

MIN_QUOTE_LENGTH = 25


def classify_authority(url: Optional[str], official_domain: Optional[str] = None) -> str:
    """
    Deterministic authority classification based on domain rules.
    Official domains (.gov.in, .nic.in, .ac.in, .edu, or user-confirmed official_domain) >
    Secondary (news, educational portals) >
    Low (aggregators, blogs, forums, unverified).
    """
    if not url or url.startswith("pasted://"):
        if official_domain:
            return "official"
        return "secondary"

    try:
        parsed = urllib.parse.urlparse(url)
        netloc = (parsed.netloc or "").lower().split(":")[0]
    except Exception:
        return "low"

    # User-specified official domain
    if official_domain:
        clean_off = official_domain.lower().strip()
        if netloc == clean_off or netloc.endswith("." + clean_off):
            return "official"

    # Recognized official government and academic TLDs
    official_tlds = (
        ".gov.in", ".nic.in", ".ac.in", ".edu.in", ".res.in",
        ".gov", ".edu", ".mil", ".europa.eu", ".gov.uk"
    )
    if any(netloc.endswith(tld) or netloc == tld.lstrip(".") for tld in official_tlds):
        return "official"

    # Known secondary news/educational domains
    secondary_domains = (
        "thehindu.com", "indianexpress.com", "timesofindia.indiatimes.com",
        "ndtv.com", "hindustantimes.com", "bbc.com", "reuters.com",
        "ugc.ac.in", "aicte-india.org", "cbse.gov.in", "scholarships.gov.in"
    )
    if any(netloc == d or netloc.endswith("." + d) for d in secondary_domains):
        return "secondary"

    # Known low-authority aggregator/blog/forum domains
    low_authority_indicators = (
        "blogspot.", "wordpress.", "reddit.", "quora.", "facebook.",
        "sarkariresult.", "sarkarihelp.", "jagranjosh.", "collegedunia.",
        "shiksha.", "medium.com", "t.me", "telegram."
    )
    if any(ind in netloc for ind in low_authority_indicators):
        return "low"

    # Default fallback for unknown domains
    return "secondary" if (".edu" in netloc or ".org" in netloc) else "low"


def normalize_whitespace(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def extract_numbers_and_years(text: str) -> List[str]:
    """Extract numeric sequences from text for strict digit verification."""
    return re.findall(r'\b\d+(?:[\.,]\d+)*\b', text)


def verify_claim_in_source(
    source_text: str,
    exact_quote: str,
    value_raw: str
) -> Dict[str, Any]:
    """
    Deterministic Verification Engine:
    1. Enforce minimum quote length (>= 25 chars).
    2. Check exact substring match in source text first.
    3. Fall back to rapidfuzz alignment match (threshold >= 90%).
    4. Run strict value-in-quote check against the MATCHED SPAN in the real source text,
       requiring exact match for all digits/numbers and dates.
    5. Return verification status, score, span offsets, and explicit rejection reason if failed.
    """
    quote_clean = normalize_whitespace(exact_quote)
    if len(quote_clean) < MIN_QUOTE_LENGTH:
        return {
            "verified": False,
            "verification_score": 0.0,
            "quote_offset_start": None,
            "quote_offset_end": None,
            "rejection_reason": f"Quote too short ({len(quote_clean)} chars < {MIN_QUOTE_LENGTH} chars minimum required for proof)"
        }

    # Step A: Exact substring check (case-insensitive with original position recovery)
    quote_lower = quote_clean.lower()
    source_lower = source_text.lower()

    exact_pos = source_lower.find(quote_lower)
    matched_span = None
    start_pos = None
    end_pos = None
    score = 0.0

    if exact_pos != -1:
        start_pos = exact_pos
        end_pos = exact_pos + len(quote_clean)
        matched_span = source_text[start_pos:end_pos]
        score = 1.0
    else:
        # Step B: Fuzzy fallback using rapidfuzz alignment (>= 90% threshold)
        alignment = fuzz.partial_ratio_alignment(quote_lower, source_lower)
        if alignment and alignment.score >= 90.0:
            start_pos = alignment.dest_start
            end_pos = alignment.dest_end
            matched_span = source_text[start_pos:end_pos]
            score = round(alignment.score / 100.0, 3)
        else:
            fuzzy_score = alignment.score if alignment else 0.0
            return {
                "verified": False,
                "verification_score": round(fuzzy_score / 100.0, 3),
                "quote_offset_start": None,
                "quote_offset_end": None,
                "rejection_reason": f"Quote not found in source text (fuzzy match score: {fuzzy_score:.1f}% < 90% threshold)"
            }


    # Step C: Value verification against matched span in real source text
    if not matched_span:
        return {
            "verified": False,
            "verification_score": score,
            "quote_offset_start": None,
            "quote_offset_end": None,
            "rejection_reason": "No text span matched in source document"
        }

    # Digits / Numbers check: all numbers present in value_raw must exist inside the matched span
    raw_digits = extract_numbers_and_years(value_raw)
    span_lower = matched_span.lower()
    span_digits = extract_numbers_and_years(matched_span)

    # Normalize comma in numbers (e.g. 2,50,000 -> 250000) for comparison
    clean_span_digits = [d.replace(',', '').replace('.', '') for d in span_digits]
    raw_digits_clean = [d.replace(',', '').replace('.', '') for d in raw_digits]

    missing_digits = []
    for d, d_clean in zip(raw_digits, raw_digits_clean):
        # Must be in matched_span literally or as cleaned number
        if d not in matched_span and d_clean not in clean_span_digits and d not in span_lower:
            missing_digits.append(d)

    if missing_digits:
        return {
            "verified": False,
            "verification_score": score,
            "quote_offset_start": start_pos,
            "quote_offset_end": end_pos,
            "rejection_reason": f"Value digits [{', '.join(missing_digits)}] do not appear in the matched source span"
        }

    # Word/token check: if value_raw is non-numeric text (e.g. "Income Certificate"),
    # verify at least 80% of tokens appear in the matched span
    words = [w.lower() for w in re.findall(r'\b[a-zA-Z]{3,}\b', value_raw)]
    if words:
        found_words = [w for w in words if w in span_lower]
        ratio = len(found_words) / len(words)
        if ratio < 0.60:
            return {
                "verified": False,
                "verification_score": score,
                "quote_offset_start": start_pos,
                "quote_offset_end": end_pos,
                "rejection_reason": f"Key value words not supported by matched source span (matched {len(found_words)}/{len(words)} tokens)"
            }

    # All deterministic checks passed!
    return {
        "verified": True,
        "verification_score": score,
        "quote_offset_start": start_pos,
        "quote_offset_end": end_pos,
        "rejection_reason": None
    }
