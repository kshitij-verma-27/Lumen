import re
from typing import Optional, Dict, Any, List
import dateparser

SYNONYM_MAP = {
    "aadhaar": ["aadhar", "aadhaar card", "uidai", "aadhar card"],
    "income_certificate": ["income certificate", "income proof", "salary certificate", "revenue certificate", "valid income certificate"],
    "marksheet": ["marksheet", "mark sheet", "grade card", "previous year marksheet", "passing certificate"],
    "transcripts": ["official transcripts", "academic transcripts", "transcripts", "grade report"],
    "letters_of_recommendation": ["letters of recommendation", "lor", "lors", "recommendation letters", "3 letters of recommendation"],
    "statement_of_purpose": ["statement of purpose", "sop", "personal statement", "intent essay"],
    "bank_passbook": ["bank passbook", "bank account", "passbook", "bank details"],
    "domicile": ["domicile certificate", "residence certificate", "domicile proof"],
    "caste_certificate": ["caste certificate", "category certificate", "community certificate"],
    "electricity_bill": ["electricity bill", "power bill", "latest electricity bill", "utility bill"],
}


def normalize_currency(text: str) -> Optional[Dict[str, Any]]:
    """
    Normalizes monetary amounts across ALL currencies:
    USD ($), EUR (€), GBP (£), INR (₹, Rs), CAD, AUD, JPY (¥), CNY, etc.
    Supports units like Lakh, Crore, k, M, and periods (annual, monthly, per credit, one-time).
    Returns: {"amount": float, "currency": str, "period": str, "raw": str} or None
    """
    if not text:
        return None

    clean = text.strip()
    lower = clean.lower()

    # Detect currency
    currency = "USD"  # default international fallback
    if "$" in clean or "usd" in lower or "dollar" in lower:
        currency = "USD"
    elif "€" in clean or "eur" in lower or "euro" in lower:
        currency = "EUR"
    elif "£" in clean or "gbp" in lower or "pound" in lower:
        currency = "GBP"
    elif "₹" in clean or "rs" in lower or "inr" in lower or "rupee" in lower or "lakh" in lower or "crore" in lower:
        currency = "INR"
    elif "¥" in clean or "jpy" in lower or "cny" in lower or "yen" in lower or "yuan" in lower:
        currency = "JPY"
    elif "cad" in lower:
        currency = "CAD"
    elif "aud" in lower:
        currency = "AUD"

    # Detect period
    period = "total"
    if "month" in lower or "/mo" in lower or "per month" in lower:
        period = "monthly"
    elif "year" in lower or "annum" in lower or "annual" in lower or "/yr" in lower or "p.a." in lower:
        period = "annual"
    elif "credit" in lower:
        period = "per credit"

    # Check for Indian Lakhs / Crores
    lakh_match = re.search(r'([\d\.]+)\s*(?:lakh|lac)s?', lower)
    if lakh_match:
        try:
            num = float(lakh_match.group(1))
            amount = float(num * 100000)
            return {"amount": amount, "currency": currency or "INR", "period": period, "raw": text}
        except ValueError:
            pass

    crore_match = re.search(r'([\d\.]+)\s*crores?', lower)
    if crore_match:
        try:
            num = float(crore_match.group(1))
            amount = float(num * 10000000)
            return {"amount": amount, "currency": currency or "INR", "period": period, "raw": text}
        except ValueError:
            pass

    # Check for Western k / M: e.g. "35k", "2.5M"
    km_match = re.search(r'[\$€£₹]?\s*([\d\.]+)\s*([km])\b', lower)
    if km_match:
        try:
            val = float(km_match.group(1))
            mult = 1000 if km_match.group(2) == 'k' else 1000000
            return {"amount": float(val * mult), "currency": currency, "period": period, "raw": text}
        except ValueError:
            pass

    # Match raw digits with commas/decimals: e.g. "$2,299", "1,550", "₹78,000", "35,000", "2149.99"
    digit_match = re.search(r'[\$€£₹]?\s*([0-9]{1,3}(?:,[0-9]{2,3})+|[0-9]{2,})(?:\.([0-9]{1,2}))?', clean)
    if digit_match:
        raw_num = digit_match.group(1).replace(',', '')
        decimal_part = f".{digit_match.group(2)}" if digit_match.group(2) else ""
        try:
            amount = float(raw_num + decimal_part)
            return {"amount": amount, "currency": currency, "period": period, "raw": text}
        except ValueError:
            pass

    return None

# Alias for backward compatibility
normalize_money = normalize_currency


def normalize_unit_value(text: str) -> Optional[Dict[str, Any]]:
    """
    Normalizes values with physical or technical measurement units:
    - Watts/Power: e.g. '175W', '140 W', '175 Watts', '3 kW'
    - Memory/Storage: e.g. '32GB', '16 GB', '1TB', '512GB'
    - Display/Refresh: e.g. '15.6 inch', '16"', '144Hz', '240 Hz'
    - Duration/Weight: e.g. '10 hours', '4.5 kg', '2.1 lbs'
    Returns: {"value": float, "unit": str, "raw": str}
    """
    if not text:
        return None

    clean = text.strip()
    match = re.search(
        r'([\d\.]+)\s*(watts?|w|kw|ghz|mhz|hz|gb|tb|mb|inch|inches|"|\'|hours?|hrs?|kg|lbs?|nits)\b',
        clean,
        re.IGNORECASE
    )
    if match:
        try:
            val = float(match.group(1))
            unit = match.group(2).lower()
            if unit in ('w', 'watts', 'watt'):
                unit = 'W'
            elif unit in ('kw',):
                unit = 'kW'
            elif unit in ('gb',):
                unit = 'GB'
            elif unit in ('tb',):
                unit = 'TB'
            elif unit in ('hz',):
                unit = 'Hz'
            elif unit in ('inch', 'inches', '"'):
                unit = 'inch'
            elif unit in ('hours', 'hour', 'hrs', 'hr'):
                unit = 'hours'
            elif unit in ('kg',):
                unit = 'kg'

            return {"value": val, "unit": unit, "raw": text}
        except ValueError:
            pass

    return None


def normalize_percentage(text: str) -> Optional[Dict[str, Any]]:
    """
    Normalizes percentages and academic scores:
    e.g. '60%', '75.5 %', 'minimum 80 percent', 'acceptance rate 12%'
    Returns: {"percentage": float, "raw": str}
    """
    if not text:
        return None

    clean = text.strip()
    match = re.search(r'([\d\.]+)\s*(?:%|percent)', clean, re.IGNORECASE)
    if match:
        try:
            val = float(match.group(1))
            return {"percentage": val, "raw": text}
        except ValueError:
            pass

    return None


MONTH_NAMES_PATTERN = r'(?:january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)'
CALENDAR_DATE_PATTERN = rf'(?:20\d\d|{MONTH_NAMES_PATTERN}\s+\d{{1,2}}|\d{{1,2}}(?:st|nd|rd|th)?\s+{MONTH_NAMES_PATTERN}|\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{2,4}})'
DURATION_PATTERN = r'(?:\b\d+\s*(?:days?|weeks?|months?|hours?|business\s*days?)\b|return\s*window|return\s*policy)'


def is_duration_expression(text: str) -> bool:
    """
    Returns True if text is a duration or timeframe policy (e.g. '30 days', 'return window', 'within 14 days')
    rather than an absolute calendar date cutoff.
    """
    if not text:
        return False
    is_dur = bool(re.search(DURATION_PATTERN, str(text), re.IGNORECASE))
    has_date = bool(re.search(CALENDAR_DATE_PATTERN, str(text), re.IGNORECASE))
    return is_dur and not has_date


def normalize_date(text: str) -> Optional[Dict[str, Any]]:
    """
    Normalizes dates to ISO YYYY-MM-DD across various international formats.
    e.g. '31st October 2025' -> '2025-10-31', 'Feb 1, 2025' -> '2025-02-01', '30-09-2023' -> '2023-09-30'
    Rejects durations like '30 days' or 'return window' that are not calendar dates.
    """
    if not text:
        return None

    clean = str(text).strip()
    # Explicitly reject duration phrases so dateparser doesn't convert them to relative dates
    if is_duration_expression(clean):
        return None

    parsed = dateparser.parse(
        clean,
        settings={'PREFER_DAY_OF_MONTH': 'first', 'DATE_ORDER': 'DMY'}
    )
    if parsed:
        iso_str = parsed.strftime("%Y-%m-%d")
        return {"iso": iso_str, "year": parsed.year, "raw": text}

    ymd = re.search(r'\b(20\d\d)[/-](\d{1,2})[/-](\d{1,2})\b', text)
    if ymd:
        return {"iso": f"{ymd.group(1)}-{ymd.group(2).zfill(2)}-{ymd.group(3).zfill(2)}", "year": int(ymd.group(1)), "raw": text}

    dmy = re.search(r'\b(\d{1,2})[/-](\d{1,2})[/-](20\d\d)\b', text)
    if dmy:
        return {"iso": f"{dmy.group(3)}-{dmy.group(2).zfill(2)}-{dmy.group(1).zfill(2)}", "year": int(dmy.group(3)), "raw": text}

    return None


def normalize_list(text: str) -> List[str]:
    """
    General list normalizer.
    Splits items by commas, semicolons, bullets (•, -, *), 'and', newlines.
    Canonicalizes synonyms if found and returns a sorted list of unique terms.
    """
    if not text:
        return []

    tokens = [t.strip().lower() for t in re.split(r'[,;\n•\-\*]|\band\b', text) if len(t.strip()) > 1]
    canonical = set()

    for token in tokens:
        # Strip numbering like '1.', '2)'
        cleaned = re.sub(r'^\d+[\.\)]\s*', '', token).strip()
        if len(cleaned) < 2:
            continue

        matched = False
        for canon, syns in SYNONYM_MAP.items():
            if any(syn in cleaned for syn in syns):
                canonical.add(canon)
                matched = True
                break
        if not matched:
            canonical.add(cleaned)

    return sorted(list(canonical))

# Alias for backward compatibility
normalize_documents = normalize_list


def normalize_version_period(text: Optional[str]) -> Optional[str]:
    """
    Standardizes versions, periods, cycles, or product generations:
    - Academic/application cycles: '2025-2026' or '2025-26' -> '2025-26', '2023-24' -> '2023-24'
    - Semesters/Terms: 'Fall 2025' -> 'Fall 2025', 'Spring 2026' -> 'Spring 2026'
    - Product Generations / Revisions: 'Gen 7' -> 'Gen 7', 'v2.0' -> 'v2.0', '2024 Model' -> '2024 Model'
    - Single years: '2025' -> '2025'
    """
    if not text:
        return None

    clean = str(text).strip()

    # Pattern 1: Multi-year cycle '2025-26' or '2025-2026'
    match = re.search(r'(20\d\d)[/-](\d{2,4})', clean)
    if match:
        y1 = match.group(1)
        y2 = match.group(2)
        if len(y2) == 4:
            y2 = y2[-2:]
        return f"{y1}-{y2}"

    # Pattern 2: Semester/Term e.g. 'Fall 2025', 'Spring 2026'
    term_match = re.search(r'\b(Fall|Spring|Summer|Winter)\s+(20\d\d)\b', clean, re.IGNORECASE)
    if term_match:
        return f"{term_match.group(1).capitalize()} {term_match.group(2)}"

    # Pattern 3: Product Generation e.g. 'Gen 7', 'Generation 6'
    gen_match = re.search(r'\b(?:gen|generation)\s*(\d+)\b', clean, re.IGNORECASE)
    if gen_match:
        return f"Gen {gen_match.group(1)}"

    # Pattern 4: Year e.g. '2025', '2024'
    single_year = re.search(r'\b(20\d\d)\b', clean)
    if single_year:
        return single_year.group(1)

    return clean

# Alias for backward compatibility
normalize_cycle = normalize_version_period


def normalize_claim_value(facet: str, value_raw: str, expected_type: str = "text") -> Dict[str, Any]:
    """
    Master normalizer that selects the appropriate normalization rule based on facet and expected_type.
    Works for ALL domains and topics.
    """
    facet_lower = facet.lower()

    # 1. Currency
    if expected_type == "currency" or any(k in facet_lower for k in ("price", "cost", "fee", "tuition", "subsidy", "amount", "budget", "stipend")):
        money = normalize_currency(value_raw)
        if money:
            return {"type": "currency", "data": money}

    # 2. Physical / Technical Units
    if expected_type == "unit_number" or any(k in facet_lower for k in ("tgp", "watt", "power", "ram", "storage", "weight", "battery", "display_size", "capacity")):
        unit_val = normalize_unit_value(value_raw)
        if unit_val:
            return {"type": "unit_number", "data": unit_val}

    # 3. Percentages
    if expected_type == "percentage" or any(k in facet_lower for k in ("percentage", "percent", "score", "cutoff", "gpa", "rate", "efficiency", "discount")):
        pct = normalize_percentage(value_raw)
        if pct:
            return {"type": "percentage", "data": pct}

    # 4. Dates
    if expected_type == "date" or any(k in facet_lower for k in ("deadline", "date", "expiry", "closing", "expiration", "window")):
        dt = normalize_date(value_raw)
        if dt:
            return {"type": "date", "data": dt}

    # 5. Lists
    if expected_type == "list" or any(k in facet_lower for k in ("document", "requirements", "items", "features", "specs", "ports")):
        lst = normalize_list(value_raw)
        if lst:
            return {"type": "list", "data": lst}

    # Fallback text
    return {"type": "text", "data": value_raw.strip()}
