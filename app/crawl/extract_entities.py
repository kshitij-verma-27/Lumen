import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from rapidfuzz import fuzz

from app.ingest.models import Document
from app.llm import generate_json
from app.trust import verify_claim_in_source

logger = logging.getLogger(__name__)

ALLOWED_ENTITY_TYPES = {
    "exam",
    "scholarship",
    "scheme",
    "college",
    "hackathon",
    "job",
    "grant",
}

ALLOWED_ATTRIBUTES = {
    "name",
    "issuing_body",
    "eligibility",
    "deadlines",
    "fees",
    "dates",
    "documents",
    "apply_link",
    "contact",
}


def normalize_entity_name(name: str) -> str:
    """Produces clean normalized alphanumeric name for deduplication."""
    clean = re.sub(r"[^a-zA-Z0-9]+", " ", (name or "").lower())
    # Remove common filler words and years
    clean = re.sub(r"\b(national|portal|scheme|examination|exam|programme|program|india|online|guidelines|20\d\d)\b", " ", clean)
    return re.sub(r"\s+", " ", clean).strip()


def mock_entity_extraction(doc: Document, domain_category: str) -> List[Dict[str, Any]]:
    """Deterministic extractor for mock mode or fallback."""
    text = doc.text
    text_lower = text.lower()
    entities = []

    # Detect entity type based on category and text keywords
    if "scholarship" in text_lower or domain_category == "education":
        e_type = "scholarship" if "scholarship" in text_lower else "exam"
    elif domain_category == "career":
        e_type = "job"
    elif domain_category == "research":
        e_type = "grant"
    elif domain_category == "business":
        e_type = "scheme"
    else:
        e_type = "scheme"

    # Find name
    first_line = text.split("\n")[0].strip() if text else "National Initiative"
    name = doc.title or first_line[:60]
    if len(name) > 60:
        name = name[:60]

    # Look for exact quotes in text for attributes
    attributes = []

    # 1. Name attribute
    name_quote = name if name in text else text[:min(len(text), 40)]
    attributes.append({
        "attribute_name": "name",
        "attribute_value": name,
        "exact_quote": name_quote,
    })

    # 2. Eligibility
    elig_match = re.search(r"(eligib\w*[:\s]+[^\.\n]{15,120}\.)", text, re.IGNORECASE)
    if elig_match:
        span = elig_match.group(1).strip()
        attributes.append({
            "attribute_name": "eligibility",
            "attribute_value": span,
            "exact_quote": span,
        })

    # 3. Deadline / dates
    date_match = re.search(r"(deadline[:\s]+[^\.\n]{10,80}|last date[:\s]+[^\.\n]{10,80})", text, re.IGNORECASE)
    if date_match:
        span = date_match.group(1).strip()
        attributes.append({
            "attribute_name": "deadlines",
            "attribute_value": span,
            "exact_quote": span,
        })

    # 4. Fee
    fee_match = re.search(r"(fee[:\s]+[^\.\n]{5,50}|application fee[^\.\n]{5,50})", text, re.IGNORECASE)
    if fee_match:
        span = fee_match.group(1).strip()
        attributes.append({
            "attribute_name": "fees",
            "attribute_value": span,
            "exact_quote": span,
        })

    # 5. Issuing body
    body_match = re.search(r"(ministry of [^\.\n,]{5,50}|commission[^\.\n,]{0,40}|council[^\.\n,]{0,40})", text, re.IGNORECASE)
    if body_match:
        span = body_match.group(1).strip()
        attributes.append({
            "attribute_name": "issuing_body",
            "attribute_value": span,
            "exact_quote": span,
        })

    entities.append({
        "name": name,
        "entity_type": e_type,
        "domain_category": domain_category,
        "subcategory": "general",
        "issuing_body": body_match.group(1).strip() if body_match else "Official Authority",
        "region": "national",
        "attributes": attributes,
    })
    return entities


# Prohibited single-word status values
BANNED_STATUS_WORDS = {
    "extended", "open", "available", "closed", "active", "online", "ongoing",
    "yes", "no", "registration open", "click here", "read more"
}

CHUNK_SIZE = 6000
CHUNK_OVERLAP = 1000
MAX_CHUNKS_PER_DOC = 3


def chunk_document_text(text: str) -> List[str]:
    """Splits long document text into overlapping chunks, capped at MAX_CHUNKS_PER_DOC."""
    if len(text) <= CHUNK_SIZE:
        return [text]
    chunks = []
    start = 0
    while start < len(text) and len(chunks) < MAX_CHUNKS_PER_DOC:
        end = min(len(text), start + CHUNK_SIZE)
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start += (CHUNK_SIZE - CHUNK_OVERLAP)
    return chunks


def extract_deterministic_links_and_contacts(
    doc: Document,
    source_id: str
) -> List[Dict[str, Any]]:
    """
    Extracts apply_link and contact deterministically from HTML anchors,
    mailto and tel links, or verified patterns in doc.text.
    """
    attrs = []
    anchors = list(doc.metadata.get("anchors", []))

    # Also parse markdown links [text](url) from doc.text
    for m in re.finditer(r'\[([^\]]+)\]\((https?://[^\s\)\'\"]+)\)', doc.text):
        anchors.append({"text": m.group(1).strip(), "href": m.group(2).strip()})

    # 1. Apply Link
    apply_url = None
    apply_quote = None
    apply_keywords = re.compile(r'\b(apply|register|registration|application|candidate portal|new registration|login)\b', re.I)

    for a in anchors:
        text = a.get("text", "")
        href = a.get("href", "")
        if href.startswith(("http://", "https://")):
            if apply_keywords.search(text) or apply_keywords.search(href):
                if f"[{text}]({href})" in doc.text:
                    apply_url = href
                    apply_quote = f"[{text}]({href})"
                    break
                elif href in doc.text:
                    idx = doc.text.find(href)
                    s_start = max(0, doc.text.rfind('.', 0, idx) + 1)
                    s_end = doc.text.find('.', idx)
                    if s_end == -1: s_end = min(len(doc.text), idx + len(href) + 40)
                    candidate = doc.text[s_start:s_end].strip()
                    if candidate and href in candidate:
                        apply_url = href
                        apply_quote = candidate
                        break
                elif text and len(text) >= 4 and text in doc.text:
                    idx = doc.text.find(text)
                    s_start = max(0, doc.text.rfind('.', 0, idx) + 1)
                    s_end = doc.text.find('.', idx)
                    if s_end == -1: s_end = min(len(doc.text), idx + len(text) + 40)
                    candidate = doc.text[s_start:s_end].strip()
                    if candidate and text in candidate:
                        apply_url = href
                        apply_quote = candidate
                        break

    # Also check doc.text for apply keywords followed by URL
    if not apply_url:
        url_match = re.search(r'\b(?:apply|register|portal|scholarships|registration)[^\.\n]*?(https?://[^\s\)\'\"]+)', doc.text, re.I)
        if url_match:
            cand_url = url_match.group(1).strip()
            if not anchors or any(cand_url in a.get("href", "") for a in anchors):
                apply_url = cand_url
                idx = url_match.start()
                s_start = max(0, doc.text.rfind('.', 0, idx) + 1)
                s_end = doc.text.find('.', url_match.end())
                if s_end == -1: s_end = min(len(doc.text), url_match.end() + 40)
                apply_quote = doc.text[s_start:s_end].strip()

    if apply_url and apply_quote and apply_quote in doc.text:
        attrs.append({
            "attribute_name": "apply_link",
            "attribute_value": apply_url,
            "exact_quote": apply_quote,
            "source_id": source_id,
            "verified": 1,
            "uncertain": 0,
            "verification_score": 1.0,
            "rejection_reason": None,
        })

    # 2. Contact Information (Email or Helpline Phone)
    contact_val = None
    contact_quote = None

    for a in anchors:
        href = a.get("href", "")
        if href.startswith("mailto:"):
            email = href.replace("mailto:", "").split("?")[0].strip()
            if email and "@" in email and email in doc.text:
                idx = doc.text.find(email)
                s_start = max(0, doc.text.rfind('.', 0, idx) + 1)
                s_end = doc.text.find('.', idx)
                if s_end == -1: s_end = min(len(doc.text), idx + len(email) + 40)
                candidate = doc.text[s_start:s_end].strip()
                contact_val = email
                contact_quote = candidate
                break
        elif href.startswith("tel:"):
            phone = href.replace("tel:", "").strip()
            if len(phone) >= 7 and phone in doc.text:
                idx = doc.text.find(phone)
                s_start = max(0, doc.text.rfind('.', 0, idx) + 1)
                s_end = doc.text.find('.', idx)
                if s_end == -1: s_end = min(len(doc.text), idx + len(phone) + 40)
                candidate = doc.text[s_start:s_end].strip()
                contact_val = phone
                contact_quote = candidate
                break

    if not contact_val:
        email_match = re.search(r'\b([a-zA-Z0-9_.+-]+@(?:[a-zA-Z0-9-]+\.)+(?:gov\.in|nic\.in|ac\.in|org|in|com))\b', doc.text)
        if email_match:
            contact_val = email_match.group(1).strip()
            idx = email_match.start()
            s_start = max(0, doc.text.rfind('.', 0, idx) + 1)
            s_end = doc.text.find('.', idx)
            if s_end == -1: s_end = min(len(doc.text), idx + 80)
            contact_quote = doc.text[s_start:s_end].strip()
            if len(contact_quote) < 15:
                contact_quote = doc.text[max(0, idx - 20):min(len(doc.text), idx + 60)].strip()

    if not contact_val:
        phone_match = re.search(r'\b(1800[-\s]?\d{3}[-\s]?\d{3,4}|011[-\s]?\d{7,8}|\+91[-\s]?\d{10})\b', doc.text)
        if phone_match:
            contact_val = phone_match.group(1).strip()
            idx = phone_match.start()
            s_start = max(0, doc.text.rfind('.', 0, idx) + 1)
            s_end = doc.text.find('.', idx)
            if s_end == -1: s_end = min(len(doc.text), idx + 80)
            contact_quote = doc.text[s_start:s_end].strip()
            if len(contact_quote) < 15:
                contact_quote = doc.text[max(0, idx - 20):min(len(doc.text), idx + 60)].strip()

    if contact_val and contact_quote and contact_quote in doc.text:
        attrs.append({
            "attribute_name": "contact",
            "attribute_value": contact_val,
            "exact_quote": contact_quote,
            "source_id": source_id,
            "verified": 1,
            "uncertain": 0,
            "verification_score": 1.0,
            "rejection_reason": None,
        })

    return attrs


async def extract_entities_from_chunk(
    chunk_text: str,
    doc_url: str,
    domain_category: str
) -> List[Dict[str, Any]]:
    """Calls Gemini with strict atomic value instructions for a single text chunk."""
    system_prompt = (
        "You are a strict factual extraction agent. Extract structured public information entities "
        "from the provided source text chunk. Return ONLY a JSON object with key 'entities'.\n"
        "JSON structure MUST strictly match:\n"
        "{\n"
        '  "entities": [\n'
        '    {\n'
        '      "name": "Full Formal Name of Exam, Scholarship, Scheme, College, Hackathon, Job, or Grant",\n'
        '      "entity_type": "exam | scholarship | scheme | college | hackathon | job | grant",\n'
        '      "issuing_body": "Name of Authority, Commission, or Ministry",\n'
        '      "attributes": [\n'
        '        {\n'
        '          "attribute_name": "eligibility | deadlines | fees | dates | documents",\n'
        '          "attribute_value": "One atomic factual value (e.g. \'31-10-2026\', \'Rs. 100\', \'No application fee is charged\')",\n'
        '          "exact_quote": "A verbatim quote of 15 to 35 words from ONE single continuous sentence in the text that directly contains the attribute value"\n'
        '        }\n'
        '      ]\n'
        '    }\n'
        '  ]\n'
        "}\n"
        "STRICT RULES:\n"
        "1. ATOMIC VALUES: Return only one concrete factual value per claim (dates, amounts, requirements). NEVER use summary or status words as values (do NOT return 'Extended', 'Open', 'Available', 'Closed', 'Active'). If a status matters, quote the full sentence that announces it.\n"
        "2. EXACT QUOTE CONTAINMENT: The 'exact_quote' MUST contain the full 'attribute_value' verbatim. Never join separate sentences into one quote.\n"
        "3. NO HALLUCINATION: Only extract claims that explicitly appear in this chunk."
    )

    user_prompt = f"Source URL: {doc_url}\n\nDocument Text Chunk:\n{chunk_text}\n\nExtract entities JSON:"

    try:
        data = await generate_json(user_prompt, system_instruction=system_prompt)
        if isinstance(data, dict):
            return data.get("entities", [])
        elif isinstance(data, list):
            return data
    except Exception as e:
        logger.warning(f"LLM entity chunk extraction failed: {e}")
    return []


async def extract_entities_from_document(
    doc: Document,
    domain_category: str = "education",
    source_id: str = "src_default"
) -> List[Dict[str, Any]]:
    """
    Extracts structured entities from a Document with code verification on every quote.
    Entities are limited to: exam, scholarship, scheme, college, hackathon, job, grant.
    Attributes: name, issuing_body, eligibility, deadlines, fees, dates, documents, apply_link, contact.
    """
    if not doc.text or len(doc.text.strip()) < 50:
        return []

    raw_entities: List[Dict[str, Any]] = []

    # Check mock mode
    if os.environ.get("FORCE_MOCK", "").lower() == "true":
        raw_entities = mock_entity_extraction(doc, domain_category)
    else:
        # Process long pages in chunks with overlap
        chunks = chunk_document_text(doc.text)
        for idx, chunk in enumerate(chunks):
            chunk_ents = await extract_entities_from_chunk(chunk, doc.url, domain_category)
            raw_entities.extend(chunk_ents)

        if not raw_entities:
            raw_entities = mock_entity_extraction(doc, domain_category)

    # Deterministic links & contacts
    deterministic_attrs = extract_deterministic_links_and_contacts(doc, source_id)

    # CODE VERIFICATION PASS
    verified_entities = []
    for ent in raw_entities:
        if not isinstance(ent, dict):
            continue

        e_type = ent.get("entity_type", "scheme")
        if isinstance(e_type, dict):
            e_type = e_type.get("value") or e_type.get("name") or "scheme"
        e_type = str(e_type).lower().strip()
        if e_type not in ALLOWED_ENTITY_TYPES:
            e_type = "scheme"

        raw_name = ent.get("name", "Unknown Entity")
        if isinstance(raw_name, dict):
            raw_name = raw_name.get("value") or raw_name.get("name") or raw_name.get("text") or "Unknown Entity"
        name = str(raw_name).strip()
        if not name or name.lower() in ("unknown entity", "entity name"):
            continue

        raw_body = ent.get("issuing_body") or "Official Authority"
        if isinstance(raw_body, dict):
            raw_body = raw_body.get("value") or raw_body.get("name") or "Official Authority"
        issuing_body = str(raw_body).strip()

        # Collect candidate attributes
        candidate_attrs = []
        ent_attrs = ent.get("attributes")
        if isinstance(ent_attrs, list):
            candidate_attrs.extend(ent_attrs)
        elif isinstance(ent_attrs, dict):
            for k, v in ent_attrs.items():
                if isinstance(v, dict):
                    candidate_attrs.append({"attribute_name": k, **v})
                else:
                    candidate_attrs.append({"attribute_name": k, "attribute_value": str(v)})

        for k in ALLOWED_ATTRIBUTES:
            if k in ent and k not in [a.get("attribute_name") for a in candidate_attrs if isinstance(a, dict)]:
                v = ent[k]
                if isinstance(v, dict):
                    candidate_attrs.append({"attribute_name": k, **v})
                elif isinstance(v, str) and len(v.strip()) > 0:
                    candidate_attrs.append({"attribute_name": k, "attribute_value": v})

        verified_attrs = []
        seen_quotes = set()
        for attr in candidate_attrs:
            if not isinstance(attr, dict):
                continue

            attr_name = attr.get("attribute_name", "")
            if isinstance(attr_name, dict):
                attr_name = attr_name.get("name") or ""
            attr_name = str(attr_name).lower().strip()
            if attr_name not in ALLOWED_ATTRIBUTES:
                continue

            # Skip apply_link and contact from LLM; they are deterministic
            if attr_name in ("apply_link", "contact"):
                continue

            attr_val = attr.get("attribute_value") or attr.get("value") or ""
            attr_val = str(attr_val).strip()

            quote = attr.get("exact_quote") or attr.get("quote") or attr.get("text") or ""
            quote = str(quote).strip()

            if not quote or not attr_val:
                continue

            # Filter out prohibited single-word status values
            if attr_val.lower() in BANNED_STATUS_WORDS:
                continue

            # Data quality filter: concrete date/amount/deadline/condition/contact, drop headlines & month/years, dedupe quotes
            from app.validation.data_quality import validate_and_dedupe_attribute
            is_valid_qual, qual_reason = validate_and_dedupe_attribute(attr_name, attr_val, quote, seen_quotes)
            if not is_valid_qual:
                logger.debug(f"Data quality drop for {attr_name}: {qual_reason}")
                continue

            # Verify quote in document text using code verifier
            v_res = verify_claim_in_source(doc.text, quote, attr_val)
            is_verified = v_res.get("verified", False)
            score = v_res.get("verification_score", 0.0)
            reason = v_res.get("rejection_reason")

            # Store full quote without truncation
            verified_attrs.append({
                "attribute_name": attr_name,
                "attribute_value": attr_val,
                "exact_quote": quote,
                "source_id": source_id,
                "verified": 1 if is_verified else 0,
                "uncertain": 0 if is_verified else 1,
                "verification_score": score,
                "rejection_reason": reason,
            })

        # Append deterministic attributes (apply_link, contact)
        for d_attr in deterministic_attrs:
            # Check if not already added
            if not any(a["attribute_name"] == d_attr["attribute_name"] for a in verified_attrs):
                verified_attrs.append(dict(d_attr))

        verified_entities.append({
            "name": name,
            "normalized_name": normalize_entity_name(name),
            "entity_type": e_type,
            "domain_category": domain_category,
            "subcategory": str(ent.get("subcategory") or "general"),
            "issuing_body": issuing_body,
            "region": str(ent.get("region") or "national"),
            "source_id": source_id,
            "attributes": verified_attrs,
        })

    # Merge cross-chunk / cross-source duplicates
    merged_entities = merge_duplicate_entities(verified_entities)
    return merged_entities


def merge_duplicate_entities(entities_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Merges entities across sources or chunks by normalized name and fuzzy similarity >= 85.
    Combines attributes, retains full quotes, and aggregates all source citations.
    """
    merged: List[Dict[str, Any]] = []

    for ent in entities_list:
        norm_name = ent["normalized_name"]
        match_found = False

        for target in merged:
            t_norm = target["normalized_name"]
            sim = fuzz.token_sort_ratio(norm_name, t_norm)
            if sim >= 85 and ent["entity_type"] == target["entity_type"]:
                match_found = True
                src = ent.get("source_id")
                if src and src not in target.get("source_ids", []):
                    target.setdefault("source_ids", []).append(src)

                # Merge attributes (avoid exact duplicate quotes)
                existing_quotes = {a["exact_quote"] for a in target["attributes"]}
                for a in ent["attributes"]:
                    if a["exact_quote"] not in existing_quotes:
                        target["attributes"].append(a)
                        existing_quotes.add(a["exact_quote"])
                break

        if not match_found:
            new_ent = dict(ent)
            new_ent["source_ids"] = [ent.get("source_id")] if ent.get("source_id") else []
            merged.append(new_ent)

    return merged
