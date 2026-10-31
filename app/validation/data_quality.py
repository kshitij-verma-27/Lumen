import re
from typing import Optional, Set, Tuple
from rapidfuzz import fuzz

MONTHS_REGEX = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)

# Date indicators: specific day + month + year, or ISO date
DATE_PATTERN = re.compile(
    r"\b(?:\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}|\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2}|"
    rf"\d{{1,2}}(?:st|nd|rd|th)?\s+{MONTHS_REGEX}(?:\s+\d{{2,4}})?|"
    rf"{MONTHS_REGEX}\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,\s*\d{{2,4}})?|"
    r"within\s+\d+\s+days|last\s+date\s*[:\-]\s*[^\.\n]{5,30})\b",
    re.IGNORECASE
)

# Amount / Fee indicators: currency symbol, lakh, crore, free/nil, or monetary values
AMOUNT_PATTERN = re.compile(
    r"(?:[₹$€£]|rs\.?|inr)\s*\d+(?:[,\.]\d+)*|"
    r"\b\d+(?:[,\.]\d+)*\s*(?:lakh|crore|inr|usd|rupees|rs)\b|"
    r"\b(?:no\s+fee|free\s+of\s+cost|waived|nil|exempted|stipend\s*[:\-]?\s*[₹$Rs\d]+)\b",
    re.IGNORECASE
)

# Contact indicators: email, phone, helpline
CONTACT_PATTERN = re.compile(
    r"\b[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+\b|"
    r"\b(?:1800[-\s]?\d{3}[-\s]?\d{3,4}|011[-\s]?\d{7,8}|\+91[-\s]?[6-9]\d{9}|[6-9]\d{9})\b|"
    r"https?://[^\s]+",
    re.IGNORECASE
)

# Condition / Eligibility indicators: percentage, marks, class, passed, degree, age, income
CONDITION_PATTERN = re.compile(
    r"\b(?:\d{1,2}%|\d{1,2}\s*percent|class\s*(?:10|12|x|xii|\d+)|"
    r"passed|graduate|undergraduate|postgraduate|degree|diploma|"
    r"income\s*(?:less\s+than|below|up\s+to|not\s+exceeding)|"
    r"age\s*(?:between|limit|below|above|\d+\s*-\s*\d+)|"
    r"minimum|domicile|resident|merit|adhaar|aadhaar|certificate|category|sc/st|obc|ews)\b",
    re.IGNORECASE
)

# Document indicators: academic transcripts, identity proofs, LORs, certificates
DOCUMENT_PATTERN = re.compile(
    r"\b(?:aadhaar|adhaar|marksheet|certificate|photograph|signature|id\s+proof|ration\s+card|"
    r"affidavit|caste\s+certificate|income\s+certificate|transcripts?|recommendation|lors?|"
    r"statement\s+of\s+purpose|sop|resume|cv|diploma|passbook)\b",
    re.IGNORECASE
)


def is_headline_value(value: str, quote: str = "") -> bool:
    """Detects if value is a full headline or announcement title rather than an atomic datum."""
    v = value.strip()
    words = v.split()

    # Substantive document lists or eligibility criteria are not headlines
    if DOCUMENT_PATTERN.search(v) or CONDITION_PATTERN.search(v) or AMOUNT_PATTERN.search(v):
        return False

    # Announcement and advisory headline prefixes
    if re.match(r"^(?:announcement|clarification|advisory|extension\s+of|notification|instructions|public\s+notice)\b", v, re.IGNORECASE):
        return True

    # Indian portal circular / headline suffixes
    if re.search(r"\b(?:reg\.|circular|notice)\s*$", v, re.IGNORECASE):
        return True

    # Exceptionally long verbatim reproduction of full headline without data
    if len(words) >= 12 and len(v) >= 80:
        if quote and fuzz.ratio(v.lower(), quote.strip().lower()) >= 90:
            return True

    return False


def is_only_month_or_year(value: str) -> bool:
    """Returns True if the value holds only a bare month or year without date or amount."""
    v = value.strip()
    # Bare year: "2026", "2025-26", "2024"
    if re.fullmatch(r"(?:19|20)\d\d(?:[-/]\d{2,4})?", v):
        return True

    # Bare month or month+year: "July", "July 2026", "Session 1", "Semester 1"
    if re.fullmatch(rf"{MONTHS_REGEX}(?:\s+(?:19|20)\d\d)?", v, re.IGNORECASE):
        return True

    if re.fullmatch(r"(?:session|semester|term|phase)\s+\d+", v, re.IGNORECASE):
        return True

    return False


# Technical specification metrics (TGP, RAM, storage, frequency, GPU model, warranty duration)
SPEC_METRIC_PATTERN = re.compile(
    r"\b(?:\d+(?:\.\d+)?\s*(?:w|watt|watts|tgp|gb|tb|mb|ghz|mhz|kg|lbs|inch|cm|mm|core|cores|threads|fps|nit|nits|hz)|"
    r"rtx\s*\d+|gtx\s*\d+|geforce|intel|ryzen|snapdragon|m\d+\s*pro|m\d+\s*max|\d+\s*years?|\d+\s*months?)\b",
    re.IGNORECASE
)

def holds_concrete_datum(attr_name: str, value: str) -> bool:
    """
    Returns True only if the value holds a concrete date, amount, deadline, condition or contact.
    """
    v = value.strip()
    if not v:
        return False

    name = attr_name.lower().strip()

    # Pass primary metadata entities if clean
    if name in ("name", "issuing_body", "portal"):
        return len(v) >= 3 and not is_headline_value(v)

    # 1. Concrete date or deadline
    if DATE_PATTERN.search(v):
        return True

    # 2. Amount or fee
    if AMOUNT_PATTERN.search(v):
        return True

    # 3. Contact information
    if CONTACT_PATTERN.search(v):
        return True

    # 4. Condition / eligibility requirement
    if CONDITION_PATTERN.search(v):
        return True

    # 5. Required document
    if DOCUMENT_PATTERN.search(v):
        return True

    # 6. Specific numerical metric / spec (e.g. 175W, 32GB, 1-year warranty)
    if SPEC_METRIC_PATTERN.search(v):
        return True

    return False


def validate_and_dedupe_attribute(
    attr_name: str,
    value: str,
    quote: str,
    seen_quotes: Set[str]
) -> Tuple[bool, Optional[str]]:
    """
    Quality gatekeeper:
    - Drops headline values
    - Drops bare year or month values
    - Ensures value contains concrete date, amount, deadline, condition or contact
    - Dedupes repeated quotes across facets
    """
    if not value or not quote:
        return False, "Empty value or quote"

    # 1. Headline check
    if is_headline_value(value, quote):
        return False, f"Dropped headline value ({len(value)} chars equals announcement title)"

    # 2. Bare year or month check
    if is_only_month_or_year(value):
        return False, f"Dropped bare month/year value ('{value}')"

    # 3. Concrete datum requirement
    if not holds_concrete_datum(attr_name, value):
        return False, f"Value '{value}' lacks concrete date, amount, deadline, condition or contact"

    # 4. Dedupe repeated quotes across facets
    norm_quote = re.sub(r"\s+", " ", quote.strip().lower())
    if norm_quote in seen_quotes:
        return False, f"Duplicate quote already assigned to another facet/attribute"

    seen_quotes.add(norm_quote)
    return True, None
