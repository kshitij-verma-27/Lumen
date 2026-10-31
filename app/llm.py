import os
import json
import re
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
def get_config():
    load_dotenv(override=True)
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
    force_mock = os.getenv("FORCE_MOCK", "false").lower() in ("true", "1", "yes")
    return api_key, model, force_mock

_client = None
_cached_key = None
_cached_model = None
_fallback_reason = None


def is_mock_mode() -> bool:
    """Returns True if running in Mock/Offline mode."""
    global _fallback_reason
    api_key, model, force_mock = get_config()
    if force_mock:
        _fallback_reason = "Mock mode explicitly forced via FORCE_MOCK=true"
        return True
    if not api_key:
        _fallback_reason = "GEMINI_API_KEY is not set or empty in .env"
        return True
    return False


def get_llm_status() -> Dict[str, Any]:
    api_key, model, force_mock = get_config()
    mock_active = is_mock_mode()
    client = _get_client() if not mock_active else None
    
    return {
        "gemini_configured": bool(api_key),
        "mode": "mock" if (mock_active or client is None) else "live",
        "model": model if (not mock_active and client is not None) else "deterministic-mock-extractor",
        "fallback_reason": _fallback_reason
    }


def _get_client():
    global _client, _cached_key, _cached_model, _fallback_reason
    api_key, model, force_mock = get_config()

    if force_mock:
        _fallback_reason = "Mock mode explicitly forced via FORCE_MOCK=true"
        return None

    if not api_key:
        _fallback_reason = "GEMINI_API_KEY is not configured in .env"
        return None

    # Reinitialize if key or model changed
    if _client is not None and _cached_key == api_key and _cached_model == model:
        return _client

    try:
        from google import genai
        client = genai.Client(api_key=api_key)

        # Verify model name against SDK's current model list
        try:
            models_pager = client.models.list()
            known_models = []
            for m in models_pager:
                name = getattr(m, "name", str(m))
                known_models.append(name.replace("models/", ""))

            if known_models and model not in known_models:
                reason = f"Model '{model}' not found in current Gemini SDK model list. Available flash models: {[m for m in known_models if 'flash' in m][:5]}"
                _fallback_reason = reason
                print(f"\n>>> [LLM FALLBACK TO MOCK MODE] Reason: {reason}\n")
                return None

        except Exception as check_err:
            print(f"[LLM] Model list check note: {check_err}. Proceeding with direct API call.")

        _client = client
        _cached_key = api_key
        _cached_model = model
        _fallback_reason = None
        return _client

    except Exception as e:
        reason = f"Failed to initialize Google GenAI Client: {e}"
        _fallback_reason = reason
        print(f"\n>>> [LLM FALLBACK TO MOCK MODE] Reason: {reason}\n")
        _client = None
        return None


def clean_json_text(text: str) -> str:
    """Strip markdown code fence blocks if returned by LLM."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


async def generate_json(prompt: str, system_instruction: Optional[str] = None) -> Any:
    """
    Generate structured JSON response using Gemini API or fallback to mock mode.
    Temperature is always 0 for deterministic extraction.
    """
    global _fallback_reason
    client = _get_client()
    api_key, model, force_mock = get_config()

    if client is not None and not is_mock_mode():
        try:
            from google.genai import types

            config = types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
                system_instruction=system_instruction or "You are a precise, deterministic information extraction engine. Return ONLY valid JSON."
            )

            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=config
            )

            raw_text = response.text or "{}"
            cleaned = clean_json_text(raw_text)
            return json.loads(cleaned)

        except Exception as e:
            err_str = str(e)
            _fallback_reason = f"Live API call failed on model '{model}': {err_str}"
            print(f"\n>>> [LLM FALLBACK TO MOCK MODE] Reason: {_fallback_reason}\n")

    # Mock mode / Fallback extractor
    if not _fallback_reason:
        _fallback_reason = "Running in deterministic mock mode"
        print(f"\n>>> [LLM FALLBACK TO MOCK MODE] Reason: {_fallback_reason}\n")
    return mock_extract(prompt)


async def generate_facets_from_goal(goal: str, domain_type: Optional[str] = None) -> Dict[str, Any]:
    """
    Dynamically generates 5-8 research facets tailored to the user's question or goal using Gemini.
    Each facet includes: id, name, description, expected_type, importance, consequence, is_deadline.
    Falls back to intelligent deterministic generation if in mock mode or API is unavailable.
    """
    client = _get_client()
    if client is not None and not is_mock_mode():
        prompt = f"""
You are an expert investigative decision-support and blindspot detection analyst.
The user is researching the following goal / question:
"{goal}"

Generate 5 to 8 focused, verifiable facets (specifications, criteria, costs, deadlines, or rules) that the user MUST verify across multiple sources to make an informed decision and avoid misinformation or costly blindspots.

For EACH facet provide:
1. "id": short snake_case identifier (e.g. "gpu_tgp", "tuition_fees", "application_deadline", "rooftop_subsidy_amount")
2. "name": clear human-readable name (e.g. "GPU TGP / Power Limit", "Tuition & Mandatory Fees")
3. "description": concise description of what information to extract from documents
4. "expected_type": ONE of ["currency", "unit_number", "percentage", "date", "list", "text"]
5. "importance": ONE of ["critical", "high", "medium"]
6. "consequence": a sharp, specific one-line consequence of what goes wrong if this facet is missing, contradictory, or unverified
7. "is_deadline": true if this facet represents a deadline, expiration, or cutoff date, otherwise false

Also provide:
- "suggested_domain": brief domain title (e.g. "Hardware / Laptop Purchase", "Graduate University Admissions", "Clean Energy Subsidy Scheme")
- "suggested_official_domain": the primary official vendor / university / government domain if identifiable (e.g. "lenovo.com", "gatech.edu", "pmsuryaghar.gov.in"), or null.

Return ONLY a JSON object:
{{
  "suggested_domain": "...",
  "suggested_official_domain": "...",
  "facets": [ ... ]
}}
"""
        try:
            from google.genai import types
            config = types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
                system_instruction="You are a precise requirements and blindspot analyst. Return ONLY valid JSON."
            )
            api_key, model, _ = get_config()
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=config
            )
            raw = clean_json_text(response.text or "{}")
            res = json.loads(raw)
            if "facets" in res and isinstance(res["facets"], list) and len(res["facets"]) > 0:
                return res
        except Exception as e:
            print(f"[LLM] Live facet generation failed: {e}. Using deterministic generator.")

    return mock_generate_facets(goal, domain_type)


def mock_generate_facets(goal: str, domain_type: Optional[str] = None) -> Dict[str, Any]:
    """
    Deterministic mock facet generator for offline testing and instant local runs across any topic.
    """
    g_lower = goal.lower()

    # 1. Laptop / Hardware Purchase
    if any(k in g_lower for k in ("laptop", "computer", "hardware", "gpu", "macbook", "thinkpad", "dell", "notebook", "pc")):
        return {
            "suggested_domain": "Hardware / Laptop Purchase",
            "suggested_official_domain": "lenovo.com" if "thinkpad" in g_lower or "lenovo" in g_lower else "dell.com" if "dell" in g_lower else "apple.com" if "mac" in g_lower else "vendor-official.com",
            "facets": [
                {
                    "id": "gpu_tgp",
                    "name": "GPU TGP / Power Limit",
                    "description": "Total Graphics Power rating and maximum wattage (e.g. 140W, 175W)",
                    "expected_type": "unit_number",
                    "importance": "critical",
                    "consequence": "A lower TGP severely throttles rendering and training throughput even with the same GPU model designation.",
                    "is_deadline": False
                },
                {
                    "id": "ram_spec",
                    "name": "RAM Capacity & Upgradability",
                    "description": "Installed memory capacity and whether RAM is upgradeable SODIMM vs soldered",
                    "expected_type": "unit_number",
                    "importance": "critical",
                    "consequence": "Soldered RAM prevents future memory expansion, causing premature hardware obsolescence.",
                    "is_deadline": False
                },
                {
                    "id": "total_price",
                    "name": "Total Price & Currency",
                    "description": "MSRP base price or retail purchase price",
                    "expected_type": "currency",
                    "importance": "high",
                    "consequence": "Hidden taxes, retailer markup, or mismatched currency rates can cause unexpected budget overruns.",
                    "is_deadline": False
                },
                {
                    "id": "return_window",
                    "name": "Return Policy & Deadline",
                    "description": "Return window duration or promotional expiration date",
                    "expected_type": "date",
                    "importance": "high",
                    "consequence": "Missing the return deadline leaves you stuck with incompatible or defective hardware.",
                    "is_deadline": True
                },
                {
                    "id": "warranty_period",
                    "name": "Warranty & Support Coverage",
                    "description": "Manufacturer warranty duration and accidental damage coverage",
                    "expected_type": "text",
                    "importance": "medium",
                    "consequence": "Unconfirmed warranty coverage leaves expensive repairs completely out of pocket.",
                    "is_deadline": False
                },
                {
                    "id": "display_spec",
                    "name": "Display Resolution & Refresh Rate",
                    "description": "Screen resolution, panel technology, and refresh rate (Hz)",
                    "expected_type": "unit_number",
                    "importance": "medium",
                    "consequence": "Sub-standard panel specs result in color inaccuracy for creative workflows.",
                    "is_deadline": False
                }
            ]
        }

    # 2. College / University Admission
    if any(k in g_lower for k in ("admission", "college", "university", "master", "ms in", "phd", "gatech", "stanford", "degree", "tuition")):
        return {
            "suggested_domain": "Graduate University Admissions",
            "suggested_official_domain": "gatech.edu" if "gatech" in g_lower or "georgia" in g_lower else "stanford.edu" if "stanford" in g_lower else "university.edu",
            "facets": [
                {
                    "id": "application_deadline",
                    "name": "Application Deadline",
                    "description": "Final date to submit online application and all credentials",
                    "expected_type": "date",
                    "importance": "critical",
                    "consequence": "Submitting past the portal closing deadline guarantees automatic rejection.",
                    "is_deadline": True
                },
                {
                    "id": "gre_toefl_requirement",
                    "name": "Standardized Test Requirements (GRE/TOEFL)",
                    "description": "Whether GRE is mandatory/waived and minimum TOEFL/IELTS language score",
                    "expected_type": "text",
                    "importance": "critical",
                    "consequence": "Omitting mandatory GRE or failing language cutoffs causes administrative disqualification.",
                    "is_deadline": False
                },
                {
                    "id": "tuition_fees",
                    "name": "Tuition & Mandatory Fees",
                    "description": "Per credit hour tuition or total annual academic cost",
                    "expected_type": "currency",
                    "importance": "high",
                    "consequence": "Underestimating tuition and campus fees causes funding shortages or loan denial.",
                    "is_deadline": False
                },
                {
                    "id": "required_documents",
                    "name": "Required Application Documents",
                    "description": "Official Transcripts, Letters of Recommendation (LORs), Statement of Purpose (SOP)",
                    "expected_type": "list",
                    "importance": "high",
                    "consequence": "Missing a required letter of recommendation or official transcript delays dossier review.",
                    "is_deadline": False
                },
                {
                    "id": "min_gpa_cutoff",
                    "name": "Minimum GPA / Academic Cutoff",
                    "description": "Minimum undergraduate GPA or grade percentage requirement",
                    "expected_type": "percentage",
                    "importance": "high",
                    "consequence": "Applying with a GPA below hard minimums leads to instant algorithmic filter rejection.",
                    "is_deadline": False
                },
                {
                    "id": "acceptance_rate",
                    "name": "Acceptance Rate / Program Competitiveness",
                    "description": "Historical selectivity percentage or incoming cohort size",
                    "expected_type": "percentage",
                    "importance": "medium",
                    "consequence": "Misjudging program competitiveness leads to an unbalanced university application strategy.",
                    "is_deadline": False
                }
            ]
        }

    # 3. Government Welfare / Subsidy Scheme
    if any(k in g_lower for k in ("scheme", "subsidy", "surya", "pmsuryaghar", "yojana", "solar", "rooftop", "welfare", "bijli")):
        return {
            "suggested_domain": "Government Subsidy Scheme",
            "suggested_official_domain": "pmsuryaghar.gov.in" if "surya" in g_lower or "solar" in g_lower or "bijli" in g_lower else "india.gov.in",
            "facets": [
                {
                    "id": "rooftop_subsidy_amount",
                    "name": "Rooftop Solar Subsidy Amount",
                    "description": "Maximum financial subsidy assistance per kilowatt or total cap",
                    "expected_type": "currency",
                    "importance": "critical",
                    "consequence": "Miscalculating subsidy amounts causes major out-of-pocket capital shortfalls.",
                    "is_deadline": False
                },
                {
                    "id": "eligibility_criteria",
                    "name": "Consumer Eligibility Criteria",
                    "description": "Electricity connection requirements, residential status, and capacity limits",
                    "expected_type": "text",
                    "importance": "critical",
                    "consequence": "Installing without meeting Discom eligibility forfeits all government subsidies.",
                    "is_deadline": False
                },
                {
                    "id": "application_deadline",
                    "name": "Application / Tranche Deadline",
                    "description": "Closing date to apply or portal validity schedule",
                    "expected_type": "date",
                    "importance": "high",
                    "consequence": "Applying after the subsidy tranche expires forfeits government financial support.",
                    "is_deadline": True
                },
                {
                    "id": "required_documents",
                    "name": "Required Documents & Bills",
                    "description": "Electricity consumer bill, bank passbook, Aadhaar, and identity proofs",
                    "expected_type": "list",
                    "importance": "high",
                    "consequence": "Mismatched names on electricity bill vs bank account blocks direct subsidy transfer.",
                    "is_deadline": False
                },
                {
                    "id": "application_fee",
                    "name": "Application & Feasibility Fee",
                    "description": "Fee charged by Discom or portal for technical feasibility review",
                    "expected_type": "currency",
                    "importance": "medium",
                    "consequence": "Paying unverified third-party fees leads to fraudulent agent scams.",
                    "is_deadline": False
                },
                {
                    "id": "portal_authority",
                    "name": "Implementing Agency / Official Portal",
                    "description": "Designated national portal URL and state Discom authority",
                    "expected_type": "text",
                    "importance": "high",
                    "consequence": "Submitting on fraudulent aggregator websites exposes personal identity documents.",
                    "is_deadline": False
                }
            ]
        }

    # 4. Scholarship (Preserved quick-start)
    if "scholarship" in g_lower or "stipend" in g_lower or "fellowship" in g_lower:
        return {
            "suggested_domain": "Scholarship & Welfare Schemes",
            "suggested_official_domain": "scholarships.gov.in",
            "facets": [
                {
                    "id": "eligibility_criteria",
                    "name": "Eligibility Criteria",
                    "description": "Academic score, minimum percentage, category, or course requirements",
                    "expected_type": "text",
                    "importance": "critical",
                    "consequence": "Applying without meeting eligibility guarantees immediate disqualification.",
                    "is_deadline": False
                },
                {
                    "id": "family_income_limit",
                    "name": "Family Income Limit",
                    "description": "Maximum annual family income ceiling (e.g. Rs. 2.5 Lakhs)",
                    "expected_type": "currency",
                    "importance": "critical",
                    "consequence": "Exceeding the income ceiling invalidates the application during revenue verification.",
                    "is_deadline": False
                },
                {
                    "id": "benefit_amount",
                    "name": "Scholarship / Benefit Amount",
                    "description": "Stipend, tuition waiver, maintenance allowance, or monetary assistance",
                    "expected_type": "currency",
                    "importance": "high",
                    "consequence": "Relying on inflated third-party estimates results in financial deficits.",
                    "is_deadline": False
                },
                {
                    "id": "deadline",
                    "name": "Application Deadline",
                    "description": "Last date to apply or portal closing date",
                    "expected_type": "date",
                    "importance": "critical",
                    "consequence": "Missing the closing date prevents application submission for the entire cycle.",
                    "is_deadline": True
                },
                {
                    "id": "required_documents",
                    "name": "Required Documents",
                    "description": "Mandatory certificates, marksheet, income certificate, Aadhaar, etc.",
                    "expected_type": "list",
                    "importance": "high",
                    "consequence": "Missing documents lead to portal rejection during scrutiny.",
                    "is_deadline": False
                },
                {
                    "id": "application_fee",
                    "name": "Application Fee",
                    "description": "Cost to apply (free or specific amount)",
                    "expected_type": "currency",
                    "importance": "medium",
                    "consequence": "Paying unauthorized fees to scam agents causes financial loss.",
                    "is_deadline": False
                }
            ]
        }

    # Generic Fallback
    return {
        "suggested_domain": "General Policy & Research Goal",
        "suggested_official_domain": None,
        "facets": [
            {
                "id": "key_requirements",
                "name": "Key Requirements & Rules",
                "description": "Mandatory qualifications or rules",
                "expected_type": "text",
                "importance": "critical",
                "consequence": "Failing to meet key requirements causes immediate disqualification.",
                "is_deadline": False
            },
            {
                "id": "important_deadlines",
                "name": "Important Dates / Deadlines",
                "description": "Closing dates or cutoff milestones",
                "expected_type": "date",
                "importance": "critical",
                "consequence": "Missing critical deadlines invalidates participation.",
                "is_deadline": True
            },
            {
                "id": "financial_terms",
                "name": "Costs, Fees or Financial Terms",
                "description": "Monetary costs, benefits, or pricing terms",
                "expected_type": "currency",
                "importance": "high",
                "consequence": "Unclear financial terms cause unexpected expenses or budget shortfalls.",
                "is_deadline": False
            },
            {
                "id": "required_documentation",
                "name": "Required Documentation & Proofs",
                "description": "Necessary forms, identity proof, or filings",
                "expected_type": "list",
                "importance": "high",
                "consequence": "Incomplete documentation halts processing or review.",
                "is_deadline": False
            },
            {
                "id": "scope_and_coverage",
                "name": "Target Scope & Exclusions",
                "description": "Who this applies to, terms, and exclusions",
                "expected_type": "text",
                "importance": "medium",
                "consequence": "Misunderstanding terms leads to relying on void provisions.",
                "is_deadline": False
            }
        ]
    }


def mock_extract(prompt: str) -> Dict[str, Any]:
    """
    Deterministic rule-based mock extractor for offline testing and zero-cost local runs across ALL topics.
    Extracts patterns for Laptop specs, College admissions, Government schemes, and Scholarships.
    """
    doc_match = re.search(r'SOURCE DOCUMENT:\s*(?:"""|\"\"\"|\'\'\')?\s*(.*?)(?:"""|\"\"\"|\'\'\')?\s*$', prompt, re.DOTALL)
    source_text = doc_match.group(1) if doc_match else prompt

    claims = []

    def get_full_sentence(text: str, match_start: int, match_end: int) -> str:
        left = max(0, text.rfind("\n", 0, match_start))
        dot_left = text.rfind(".", 0, match_start)
        if dot_left > left:
            left = dot_left + 1

        right = text.find("\n", match_end)
        dot_right = text.find(".", match_end)
        if right == -1 or (dot_right != -1 and dot_right < right):
            right = dot_right + 1 if dot_right != -1 else len(text)

        sentence = text[left:right].strip()
        if len(sentence) < 25:
            start = max(0, match_start - 35)
            end = min(len(text), match_end + 35)
            sentence = text[start:end].strip()
        return sentence

    # Detect version/period/cycle from text
    doc_version_period = None
    if "2025-26" in source_text or "2025-2026" in source_text:
        doc_version_period = "2025-26"
    elif "2023-24" in source_text or "2023-2024" in source_text:
        doc_version_period = "2023-24"
    elif "Fall 2025" in source_text:
        doc_version_period = "Fall 2025"
    elif "Fall 2023" in source_text:
        doc_version_period = "Fall 2023"
    elif "Gen 7" in source_text or "P1 Gen 7" in source_text or "Legion Pro 7i" in source_text:
        doc_version_period = "Gen 7"
    elif "Gen 6" in source_text or "P1 Gen 6" in source_text:
        doc_version_period = "Gen 6"
    elif "2025" in source_text:
        doc_version_period = "2025"
    elif "2023" in source_text:
        doc_version_period = "2023"

    # ==========================
    # 1. LAPTOP / HARDWARE SPEC EXTRACTIONS
    # ==========================
    # GPU TGP: e.g. "175W TGP", "140W TGP", "up to 175 Watts", "140 W"
    tgp_match = re.search(r'(?:tgp|power\s*limit|graphics\s*power)[^\.\n]{0,30}?[:\-]?\s*(\d{2,3}\s*W(?:atts)?)', source_text, re.IGNORECASE)
    if not tgp_match:
        tgp_match = re.search(r'\b(\d{2,3}\s*W)\s*(?:tgp|maximum\s*graphics\s*power)', source_text, re.IGNORECASE)
    if tgp_match:
        val = tgp_match.group(1).strip()
        quote = get_full_sentence(source_text, tgp_match.start(), tgp_match.end())
        claims.append({
            "facet": "gpu_tgp",
            "value_raw": val,
            "exact_quote": quote,
            "scope": "general",
            "cycle": doc_version_period
        })

    # RAM: e.g. "32GB DDR5 expandable", "32 GB", "16GB soldered"
    ram_match = re.search(r'\b(\d{1,3}\s*GB)\s*(?:ddr\d|ram|memory|soldered|expandable|sodimm)', source_text, re.IGNORECASE)
    if ram_match:
        val = ram_match.group(1).strip()
        quote = get_full_sentence(source_text, ram_match.start(), ram_match.end())
        claims.append({
            "facet": "ram_spec",
            "value_raw": val,
            "exact_quote": quote,
            "scope": "soldered" if "soldered" in quote.lower() else "expandable" if "expandable" in quote.lower() or "sodimm" in quote.lower() else "general",
            "cycle": doc_version_period
        })

    # Laptop Price: e.g. "$2,299", "$2,149", "$1,899"
    laptop_price_match = re.search(r'(?:price|msrp|retail\s*price|starts\s*at|cost)[^\.\n]{0,30}?[:\-]?\s*(\$\s*[\d,]+(?:\.\d{2})?)', source_text, re.IGNORECASE)
    if not laptop_price_match and "$" in source_text:
        laptop_price_match = re.search(r'(\$\s*[1-9][\d,]{2,}(?:\.\d{2})?)', source_text)
    if laptop_price_match:
        val = laptop_price_match.group(1).strip()
        quote = get_full_sentence(source_text, laptop_price_match.start(), laptop_price_match.end())
        claims.append({
            "facet": "total_price",
            "value_raw": val,
            "exact_quote": quote,
            "scope": "general",
            "cycle": doc_version_period
        })

    # Return window: e.g. "30-day return window", "15th December 2024", "2024-12-15"
    return_match = re.search(r'(?:return\s*window|return\s*policy|promo\s*ends?|offer\s*valid\s*until)[^\.\n]{0,40}?[:\-]?\s*([0-9]{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s+20\d\d|[0-9]{1,2}[/-][0-9]{1,2}[/-]20\d\d|20\d\d-\d{2}-\d{2}|\d{1,2}\s*days?)', source_text, re.IGNORECASE)
    if return_match:
        val = return_match.group(1).strip()
        quote = get_full_sentence(source_text, return_match.start(), return_match.end())
        claims.append({
            "facet": "return_window",
            "value_raw": val,
            "exact_quote": quote,
            "scope": "general",
            "cycle": doc_version_period
        })

    # Warranty: e.g. "1-year warranty", "3-year premier support"
    warranty_match = re.search(r'(\d+[\s\-]years?\s*(?:standard\s*warranty|warranty|premier\s*support))', source_text, re.IGNORECASE)
    if warranty_match:
        val = warranty_match.group(1).strip()
        quote = get_full_sentence(source_text, warranty_match.start(), warranty_match.end())
        claims.append({
            "facet": "warranty_period",
            "value_raw": val,
            "exact_quote": quote,
            "scope": "general",
            "cycle": doc_version_period
        })

    # ==========================
    # 2. UNIVERSITY ADMISSION EXTRACTIONS
    # ==========================
    # GRE / TOEFL Requirement:
    gre_match = re.search(r'(?:GRE\s*(?:is\s*)?(?:not\s*required|optional|mandatory|waived)[^\.\n]{0,50}|GRE\s*score\s*minimum\s*\d{3})', source_text, re.IGNORECASE)
    if gre_match:
        val = gre_match.group(0).strip()
        quote = get_full_sentence(source_text, gre_match.start(), gre_match.end())
        claims.append({
            "facet": "gre_toefl_requirement",
            "value_raw": val,
            "exact_quote": quote,
            "scope": "general",
            "cycle": doc_version_period
        })

    # Tuition fees: e.g. "$1,550 per credit hour", "$35,000 per year"
    tuition_match = re.search(r'(?:tuition|tuition\s*fees?)[^\.\n]{0,40}?[:\-]?\s*(\$\s*[\d,]+(?:\s*(?:per\s*credit\s*hour|per\s*credit|per\s*year|annually|per\s*semester))?)', source_text, re.IGNORECASE)
    if tuition_match:
        val = tuition_match.group(1).strip()
        quote = get_full_sentence(source_text, tuition_match.start(), tuition_match.end())
        claims.append({
            "facet": "tuition_fees",
            "value_raw": val,
            "exact_quote": quote,
            "scope": "general",
            "cycle": doc_version_period
        })

    # Required Documents (College / General):
    coll_docs_match = re.search(r'(?:required\s*documents|application\s*documents|required\s*application\s*documents|materials\s*include)[^\.\n]{0,30}?[:\-]?\s*([^\.\n]+)', source_text, re.IGNORECASE)
    if coll_docs_match and any(d in coll_docs_match.group(1).lower() for d in ("transcript", "lor", "recommendation", "sop", "statement", "resume", "bill", "passbook", "aadhaar", "pan")):
        val = coll_docs_match.group(1).strip()
        quote = get_full_sentence(source_text, coll_docs_match.start(), coll_docs_match.end())
        claims.append({
            "facet": "required_documents",
            "value_raw": val[:90],
            "exact_quote": quote,
            "scope": "general",
            "cycle": doc_version_period
        })

    # ==========================
    # 3. GOVERNMENT SCHEME / SOLAR SUBSIDY EXTRACTIONS
    # ==========================
    # Solar subsidy: e.g. "₹78,000", "Rs. 78,000", "₹1,00,000", "Rs. 1 Lakh"
    subsidy_match = re.search(r'(?:subsidy\s*amount|solar\s*subsidy|financial\s*assistance|subsidy\s*up\s*to)[^\.\n]{0,30}?[:\-]?\s*((?:₹|Rs\.?)\s*[\d,\.]+(?:\s*(?:lakhs?|crores?))?)', source_text, re.IGNORECASE)
    if subsidy_match:
        val = subsidy_match.group(1).strip()
        quote = get_full_sentence(source_text, subsidy_match.start(), subsidy_match.end())
        claims.append({
            "facet": "rooftop_subsidy_amount",
            "value_raw": val,
            "exact_quote": quote,
            "scope": "general",
            "cycle": doc_version_period
        })

    # ==========================
    # 4. SCHOLARSHIP & GENERAL EXTRACTIONS
    # ==========================
    # Income limit:
    income_match = re.search(
        r'income\s*(?:ceiling|limit)?(?:\s*of\s*parents|\s*from\s*all\s*sources)?\s*(?:should|is|must)?\s*(?:not\s*more\s*than|not\s*(?:to\s*)?exceed|less\s*than|up\s*to)?\s*[:\-]?\s*((?:Rs\.?|₹)\s*[\d,\.]+(?:\s*(?:lakhs?|crores?|/-\s*per\s*annum|per\s*year))?)',
        source_text,
        re.IGNORECASE
    )
    if income_match:
        val = income_match.group(1).strip()
        quote = get_full_sentence(source_text, income_match.start(), income_match.end())
        claims.append({
            "facet": "family_income_limit",
            "value_raw": val,
            "exact_quote": quote,
            "scope": "general",
            "cycle": doc_version_period
        })

    # Deadline / Expiry across all domains:
    deadline_match = re.search(
        r'(?:closing\s*date|deadline|last\s*date|application\s*deadline)(?:[^\.\n]{0,160}?)\s*(?:[:\-]|\bis\b|\bwas\b)?\s*([0-9]{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s+20\d\d|[0-9]{1,2}[/-][0-9]{1,2}[/-]20\d\d|[A-Za-z]+\s+[0-9]{1,2},?\s+20\d\d)',
        source_text,
        re.IGNORECASE
    )
    if deadline_match:
        val = deadline_match.group(1).strip()
        quote = get_full_sentence(source_text, deadline_match.start(), deadline_match.end())
        claim_cyc = doc_version_period or ("2025-26" if "2025" in quote else "2023-24" if "2023" in quote else None)
        # Avoid duplicate if already added
        if not any(c["facet"] in ("application_deadline", "deadline") for c in claims):
            target_id = "application_deadline" if any(f in prompt for f in ("application_deadline",)) else "deadline"
            claims.append({
                "facet": target_id,
                "value_raw": val,
                "exact_quote": quote,
                "scope": "general",
                "cycle": claim_cyc,
                "version_period": claim_cyc
            })

    # Benefit amount (Scholarship):
    benefit_match = re.search(
        r'(?:amount\s*of\s*scholarship|scholarship\s*amount|financial\s*assistance|stipend)\s*(?:is\s*)?[:\-]?\s*((?:Rs\.?|₹)\s*[\d,\.]+(?:\s*(?:per\s*annum|per\s*month|yearly\s*stipend|lakhs?))?)',
        source_text,
        re.IGNORECASE
    )
    if benefit_match:
        val = benefit_match.group(1).strip()
        quote = get_full_sentence(source_text, benefit_match.start(), benefit_match.end())
        claims.append({
            "facet": "benefit_amount",
            "value_raw": val,
            "exact_quote": quote,
            "scope": "general",
            "cycle": doc_version_period
        })

    # Eligibility criteria:
    eligibility_match = re.search(
        r'(?:ELIGIBILITY\s*CRITERIA:\s*|eligibility\s*criteria\s*[:\-]?\s*)([^\.\n]+(?:\.|\n))',
        source_text,
        re.IGNORECASE
    )
    if eligibility_match:
        val = eligibility_match.group(1).strip()
        quote = get_full_sentence(source_text, eligibility_match.start(), eligibility_match.end())
        claims.append({
            "facet": "eligibility_criteria",
            "value_raw": val[:80],
            "exact_quote": quote,
            "scope": "general",
            "cycle": doc_version_period
        })

    # Application fee:
    fee_match = re.search(
        r'(?:application\s*fee|registration\s*fee)\s*[:\-]?\s*(?:is\s*)?([^\.\n]+)',
        source_text,
        re.IGNORECASE
    )
    if fee_match:
        val = fee_match.group(1).strip()
        quote = get_full_sentence(source_text, fee_match.start(), fee_match.end())
        claims.append({
            "facet": "application_fee",
            "value_raw": val[:60],
            "exact_quote": quote,
            "scope": "general",
            "cycle": None
        })

    # Required documents (Scholarship / General):
    docs_match = re.search(
        r'(?:mandatory\s*documents|required\s*documents|documents\s*include)\s*[:\-]?\s*(?:include\s*)?([^\.\n]+)',
        source_text,
        re.IGNORECASE
    )
    if docs_match and not any(c["facet"] == "required_documents" for c in claims):
        val = docs_match.group(1).strip()
        quote = get_full_sentence(source_text, docs_match.start(), docs_match.end())
        claims.append({
            "facet": "required_documents",
            "value_raw": val[:90],
            "exact_quote": quote,
            "scope": "general",
            "cycle": None
        })

    return {"claims": claims}

