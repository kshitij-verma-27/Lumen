import re
from typing import Dict, List, Tuple
from urllib.parse import urlparse

# Inherently zero-fee schemes and portals
FREE_SCHEMES_KEYWORDS = [
    "udyam registration",
    "msme registration",
    "national scholarship portal",
    "nsp scholarship",
    "pm surya ghar",
    "pm suryaghar",
    "digilocker",
    "mygov",
    "swayam course",
]

URGENCY_PATTERNS = [
    r"\b(act immediately|urgent deadline|apply right now|last chance to claim|offer expires today)\b",
    r"\b(only \d+ seats left|hurry up|immediate selection guaranteed)\b",
    r"\b(instant approval|limited time scheme)\b",
]

GUARANTEE_PATTERNS = [
    r"\b(100% (guaranteed|selection|approval|pass))\b",
    r"\b((direct|guaranteed)?\s*(job|appointment|selection) without (any )?exam)\b",
    r"\b(guaranteed (job|employment|placement|grant|scholarship|loan|subsidy|result))\b",
    r"\b(pay to get job|money back guarantee)\b",
]

SHORTENER_DOMAINS = {
    "bit.ly", "tinyurl.com", "t.co", "cutt.ly", "rb.gy", "is.gd", "ow.ly", "goo.gl", "rebrand.ly"
}

SENSITIVE_HARVEST_PATTERNS = [
    r"\b(aadhaar otp|bank password|atm pin|upi pin|credit card cvv)\b",
    r"\b(send otp to verify|enter otp to receive money)\b",
]

OFFICIAL_BODY_CLAIMS = [
    r"\b(official portal of government of india|ministry of education official|ministry of msme)\b",
    r"\b(authorized national recruitment portal|statutory government body)\b",
]


def detect_scam_signals(url: str, text: str) -> Tuple[bool, List[str], int]:
    """
    Analyzes page text and URL for deceptive, fraudulent, or scam indicators.
    Returns: (scam_detected, signal_reasons, penalty_points)
    """
    signals = []
    penalty = 0

    url_lower = url.lower()
    text_lower = text.lower()
    parsed = urlparse(url_lower)
    domain = parsed.netloc.split(":")[0]

    is_official_domain = (
        domain.endswith(".gov.in")
        or domain.endswith(".nic.in")
        or domain.endswith(".ac.in")
        or domain.endswith(".res.in")
    )

    # 1. Fee for free schemes
    for scheme in FREE_SCHEMES_KEYWORDS:
        if scheme in text_lower:
            fee_match = re.search(r"\b(fee|charges?|cost|pay|payment|amount)\b(?:[\s\w]{0,15}?)(?:rs\.?|inr|₹)?\s*([1-9]\d{1,4})\b", text_lower)
            if fee_match and not is_official_domain:
                amount = fee_match.group(2)
                signals.append(f"Fee Scam: asks Rs {amount} for inherently zero-fee government scheme '{scheme}' on unofficial domain")
                penalty += 60
                break

    # 2. Urgency language
    for pat in URGENCY_PATTERNS:
        match = re.search(pat, text_lower)
        if match:
            signals.append(f"High-pressure urgency language: '{match.group(0)}'")
            penalty += 20
            break

    # 3. Guaranteed outcomes
    for pat in GUARANTEE_PATTERNS:
        match = re.search(pat, text_lower)
        if match:
            signals.append(f"Unrealistic guarantee: '{match.group(0)}'")
            penalty += 35
            break

    # 4. Shortened links in text or URL
    if domain in SHORTENER_DOMAINS:
        signals.append(f"Shortened redirect domain used: '{domain}'")
        penalty += 40

    for shortener in SHORTENER_DOMAINS:
        if shortener in text_lower:
            signals.append(f"Contains obscured shortened link '{shortener}'")
            penalty += 15
            break

    # 5. Sensitive data harvesting on non-gov domains
    if not is_official_domain:
        for pat in SENSITIVE_HARVEST_PATTERNS:
            match = re.search(pat, text_lower)
            if match:
                signals.append(f"Critical security risk: requests sensitive credential '{match.group(0)}' on non-government domain")
                penalty += 75
                break

    # 6. Misleading official body claims on commercial TLDs
    if not is_official_domain:
        for pat in OFFICIAL_BODY_CLAIMS:
            match = re.search(pat, text_lower)
            if match:
                signals.append(f"Mismatched authority claim: claims to be '{match.group(0)}' but hosted on '{domain}'")
                penalty += 30
                break

    scam_detected = penalty >= 40
    return scam_detected, signals, penalty
