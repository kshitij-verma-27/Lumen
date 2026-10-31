import json
import uuid
from typing import List, Dict, Any, Optional
from app.database import get_db_connection, row_to_dict
from app.models import FacetDefinition
from app.llm import generate_json
from app.trust import verify_claim_in_source

# Predefined Domain Templates (Optional Quick-Starts)
DEFAULT_LAPTOP_FACETS = [
    FacetDefinition(
        id="gpu_tgp",
        name="GPU TGP / Power Limit",
        description="Total Graphics Power rating and maximum wattage (e.g. 140W, 175W)",
        expected_type="unit_number",
        importance="critical",
        consequence="A lower TGP severely throttles rendering and training throughput even with the same GPU model designation.",
        is_deadline=False
    ),
    FacetDefinition(
        id="ram_spec",
        name="RAM Capacity & Upgradability",
        description="Installed memory capacity and whether RAM is upgradeable SODIMM vs soldered",
        expected_type="unit_number",
        importance="critical",
        consequence="Soldered RAM prevents future memory expansion, causing premature hardware obsolescence.",
        is_deadline=False
    ),
    FacetDefinition(
        id="total_price",
        name="Total Price & Currency",
        description="MSRP base price or retail purchase price",
        expected_type="currency",
        importance="high",
        consequence="Hidden taxes, retailer markup, or mismatched currency rates can cause unexpected budget overruns.",
        is_deadline=False
    ),
    FacetDefinition(
        id="return_window",
        name="Return Policy & Deadline",
        description="Return window duration or promotional expiration date",
        expected_type="date",
        importance="high",
        consequence="Missing the return deadline leaves you stuck with incompatible or defective hardware.",
        is_deadline=True
    ),
    FacetDefinition(
        id="warranty_period",
        name="Warranty & Support Coverage",
        description="Manufacturer warranty duration and accidental damage coverage",
        expected_type="text",
        importance="medium",
        consequence="Unconfirmed warranty coverage leaves expensive repairs completely out of pocket.",
        is_deadline=False
    ),
    FacetDefinition(
        id="display_spec",
        name="Display Resolution & Refresh Rate",
        description="Screen resolution, panel technology, and refresh rate (Hz)",
        expected_type="unit_number",
        importance="medium",
        consequence="Sub-standard panel specs result in color inaccuracy for creative workflows.",
        is_deadline=False
    )
]

DEFAULT_COLLEGE_FACETS = [
    FacetDefinition(
        id="application_deadline",
        name="Application Deadline",
        description="Final date to submit online application and all credentials",
        expected_type="date",
        importance="critical",
        consequence="Submitting past the portal closing deadline guarantees automatic rejection.",
        is_deadline=True
    ),
    FacetDefinition(
        id="gre_toefl_requirement",
        name="Standardized Test Requirements (GRE/TOEFL)",
        description="Whether GRE is mandatory/waived and minimum TOEFL/IELTS language score",
        expected_type="text",
        importance="critical",
        consequence="Omitting mandatory GRE or failing language cutoffs causes administrative disqualification.",
        is_deadline=False
    ),
    FacetDefinition(
        id="tuition_fees",
        name="Tuition & Mandatory Fees",
        description="Per credit hour tuition or total annual academic cost",
        expected_type="currency",
        importance="high",
        consequence="Underestimating tuition and campus fees causes funding shortages or loan denial.",
        is_deadline=False
    ),
    FacetDefinition(
        id="required_documents",
        name="Required Application Documents",
        description="Official Transcripts, Letters of Recommendation (LORs), Statement of Purpose (SOP)",
        expected_type="list",
        importance="high",
        consequence="Missing a required letter of recommendation or official transcript delays dossier review.",
        is_deadline=False
    ),
    FacetDefinition(
        id="min_gpa_cutoff",
        name="Minimum GPA / Academic Cutoff",
        description="Minimum undergraduate GPA or grade percentage requirement",
        expected_type="percentage",
        importance="high",
        consequence="Applying with a GPA below hard minimums leads to instant algorithmic filter rejection.",
        is_deadline=False
    ),
    FacetDefinition(
        id="acceptance_rate",
        name="Acceptance Rate / Program Competitiveness",
        description="Historical selectivity percentage or incoming cohort size",
        expected_type="percentage",
        importance="medium",
        consequence="Misjudging program competitiveness leads to an unbalanced university application strategy.",
        is_deadline=False
    )
]

DEFAULT_GOVERNMENT_SCHEME_FACETS = [
    FacetDefinition(
        id="rooftop_subsidy_amount",
        name="Rooftop Solar Subsidy Amount",
        description="Maximum financial subsidy assistance per kilowatt or total cap",
        expected_type="currency",
        importance="critical",
        consequence="Miscalculating subsidy amounts causes major out-of-pocket capital shortfalls.",
        is_deadline=False
    ),
    FacetDefinition(
        id="eligibility_criteria",
        name="Consumer Eligibility Criteria",
        description="Electricity connection requirements, residential status, and capacity limits",
        expected_type="text",
        importance="critical",
        consequence="Installing without meeting Discom eligibility forfeits all government subsidies.",
        is_deadline=False
    ),
    FacetDefinition(
        id="application_deadline",
        name="Application / Tranche Deadline",
        description="Closing date to apply or portal validity schedule",
        expected_type="date",
        importance="high",
        consequence="Applying after the subsidy tranche expires forfeits government financial support.",
        is_deadline=True
    ),
    FacetDefinition(
        id="required_documents",
        name="Required Documents & Bills",
        description="Electricity consumer bill, bank passbook, Aadhaar, and identity proofs",
        expected_type="list",
        importance="high",
        consequence="Mismatched names on electricity bill vs bank account blocks direct subsidy transfer.",
        is_deadline=False
    ),
    FacetDefinition(
        id="application_fee",
        name="Application & Feasibility Fee",
        description="Fee charged by Discom or portal for technical feasibility review",
        expected_type="currency",
        importance="medium",
        consequence="Paying unverified third-party fees leads to fraudulent agent scams.",
        is_deadline=False
    ),
    FacetDefinition(
        id="portal_authority",
        name="Implementing Agency / Official Portal",
        description="Designated national portal URL and state Discom authority",
        expected_type="text",
        importance="high",
        consequence="Submitting on fraudulent aggregator websites exposes personal identity documents.",
        is_deadline=False
    )
]

DEFAULT_SCHOLARSHIP_FACETS = [
    FacetDefinition(
        id="eligibility_criteria",
        name="Eligibility Criteria",
        description="Academic score, minimum percentage, category, or course requirements",
        expected_type="text",
        importance="critical",
        consequence="Applying without meeting eligibility guarantees immediate disqualification.",
        is_deadline=False
    ),
    FacetDefinition(
        id="family_income_limit",
        name="Family Income Limit",
        description="Maximum annual family income ceiling (e.g. Rs. 2.5 Lakhs)",
        expected_type="currency",
        importance="critical",
        consequence="Exceeding the income ceiling invalidates the application during revenue verification.",
        is_deadline=False
    ),
    FacetDefinition(
        id="benefit_amount",
        name="Scholarship / Benefit Amount",
        description="Stipend, tuition waiver, maintenance allowance, or monetary assistance",
        expected_type="currency",
        importance="high",
        consequence="Relying on inflated third-party estimates results in financial deficits.",
        is_deadline=False
    ),
    FacetDefinition(
        id="deadline",
        name="Application Deadline",
        description="Last date to apply or portal closing date",
        expected_type="date",
        importance="critical",
        consequence="Missing the closing date prevents application submission for the entire cycle.",
        is_deadline=True
    ),
    FacetDefinition(
        id="required_documents",
        name="Required Documents",
        description="Mandatory certificates, marksheet, income certificate, Aadhaar, etc.",
        expected_type="list",
        importance="high",
        consequence="Missing documents lead to portal rejection during scrutiny.",
        is_deadline=False
    ),
    FacetDefinition(
        id="application_fee",
        name="Application Fee",
        description="Cost to apply (free or specific amount)",
        expected_type="currency",
        importance="medium",
        consequence="Paying unauthorized fees to scam agents causes financial loss.",
        is_deadline=False
    ),
    FacetDefinition(
        id="selection_process",
        name="Selection Process",
        description="Merit list, entrance test, reservation quota, or interview",
        expected_type="text",
        importance="medium",
        consequence="Ignoring quota rules leads to applying under the wrong admission stream.",
        is_deadline=False
    ),
    FacetDefinition(
        id="renewal_policy",
        name="Renewal Conditions",
        description="Attendance requirement, minimum GPA/marks for subsequent years",
        expected_type="text",
        importance="medium",
        consequence="Failing renewal thresholds cuts off ongoing funding mid-degree.",
        is_deadline=False
    )
]

DEFAULT_GENERIC_FACETS = [
    FacetDefinition(
        id="key_requirements",
        name="Key Requirements & Rules",
        description="Mandatory qualifications or rules",
        expected_type="text",
        importance="critical",
        consequence="Failing to meet key requirements causes immediate disqualification.",
        is_deadline=False
    ),
    FacetDefinition(
        id="important_deadlines",
        name="Important Dates / Deadlines",
        description="Closing dates or cutoff milestones",
        expected_type="date",
        importance="critical",
        consequence="Missing critical deadlines invalidates participation.",
        is_deadline=True
    ),
    FacetDefinition(
        id="financial_terms",
        name="Costs, Fees or Financial Terms",
        description="Monetary costs, benefits, or pricing terms",
        expected_type="currency",
        importance="high",
        consequence="Unclear financial terms cause unexpected expenses or budget shortfalls.",
        is_deadline=False
    ),
    FacetDefinition(
        id="required_documentation",
        name="Required Documentation & Proofs",
        description="Necessary forms, identity proof, or filings",
        expected_type="list",
        importance="high",
        consequence="Incomplete documentation halts processing or review.",
        is_deadline=False
    ),
    FacetDefinition(
        id="scope_and_coverage",
        name="Target Scope & Exclusions",
        description="Who this applies to, terms, and exclusions",
        expected_type="text",
        importance="medium",
        consequence="Misunderstanding terms leads to relying on void provisions.",
        is_deadline=False
    )
]


def get_template_facets(domain_type: str = "custom") -> List[FacetDefinition]:
    dt = domain_type.lower()
    if dt in ("laptop", "hardware"):
        return DEFAULT_LAPTOP_FACETS
    elif dt in ("college", "college_admission", "university"):
        return DEFAULT_COLLEGE_FACETS
    elif dt in ("government", "government_scheme", "subsidy", "scheme"):
        return DEFAULT_GOVERNMENT_SCHEME_FACETS
    elif dt in ("scholarship", "welfare"):
        return DEFAULT_SCHOLARSHIP_FACETS
    return DEFAULT_GENERIC_FACETS


async def extract_claims_for_source(session_id: str, source_id: str) -> List[Dict[str, Any]]:
    """
    Extracts all target facets from a single source in one LLM call,
    then executes deterministic verification rules in code.
    Stores verified and rejected claims in the database.
    """
    conn = get_db_connection()

    # Load session and facets
    sess_row = conn.execute("SELECT * FROM research_sessions WHERE id = ?", (session_id,)).fetchone()
    if not sess_row:
        conn.close()
        raise ValueError(f"Session {session_id} not found")

    facets_data = json.loads(sess_row["facets_json"])
    target_facets = [FacetDefinition(**f) for f in facets_data]

    # Load source
    src_row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
    if not src_row:
        conn.close()
        raise ValueError(f"Source {source_id} not found")

    source_text = src_row["text"]
    if not source_text or len(source_text.strip()) < 30:
        conn.close()
        return []

    # Format prompt for single LLM call covering all facets
    facets_prompt_lines = [
        f"- {f.id} ({f.name}): {f.description} [Expected format: {f.expected_type}, Importance: {f.importance}]"
        for f in target_facets
    ]
    facets_str = "\n".join(facets_prompt_lines)

    # Process document in chunks if long, capped at 3 chunks
    chunks = []
    if len(source_text) <= 6500:
        chunks = [source_text]
    else:
        start = 0
        while start < len(source_text) and len(chunks) < 3:
            end = min(len(source_text), start + 6000)
            chunks.append(source_text[start:end])
            if end >= len(source_text):
                break
            start += 5000

    system_instruction = (
        "You are an exact information extraction engine. Return ONLY valid JSON with format: "
        '{"claims": [{"facet": str, "value_raw": str, "exact_quote": str, "scope": str, "version_period": str}]}. '
        "Never guess. If not found in text, do not include it."
    )

    extracted_items = []
    for chunk in chunks:
        prompt = f"""
Goal / Question: "{sess_row['goal']}"

You are an exact, evidence-first extraction assistant.
Extract information ONLY for the facets listed below from the provided Source Document.

TARGET FACETS:
{facets_str}

STRICT EXTRACTION RULES:
1. For every facet found in the text, you MUST provide:
   - "facet": The exact facet id from the list above.
   - "exact_quote": The EXACT verbatim sentence (at least 15 characters) from the Source Document where you found this information. Do NOT rephrase or fix typos.
   - "value_raw": The concise extracted value (e.g. "$2,299", "175W", "Feb 1, 2025", "Rs. 78,000", "GRE not required"). All digits and dates in value_raw MUST appear inside the exact_quote.
   - "scope": Who or what this applies to (e.g. "RTX 4080", "Domestic", "General", "Out-of-state", or "all").
   - "version_period": Academic year, semester, product generation, or version period if mentioned (e.g. "2025-26", "Fall 2025", "Fall 2023", "Gen 7", "2024 Model", "2025"), or null.
2. Even if the source document is from a prior academic year, older product generation, or archived cycle (e.g. Fall 2023, 2023-24, Gen 6), ALWAYS extract the facet values stated in the document and record their version_period. This is essential for detecting outdated claims.
3. If a facet is NOT explicitly mentioned or cannot be proven by an exact quote, do NOT return it. NEVER hallucinate or guess.
4. Return a JSON object with a single key "claims" containing an array of extracted claims.

SOURCE DOCUMENT:
\"\"\"
{chunk}
\"\"\"
"""
        llm_output = await generate_json(prompt, system_instruction=system_instruction)
        items = llm_output.get("claims", []) if isinstance(llm_output, dict) else []
        extracted_items.extend(items)

    processed_claims = []

    # Clean previous claims for this source if re-running
    conn.execute("DELETE FROM claims WHERE source_id = ?", (source_id,))

    seen_quotes = set()
    for item in extracted_items:
        facet = item.get("facet", "").strip()
        value_raw = str(item.get("value_raw", "")).strip()
        exact_quote = str(item.get("exact_quote", "")).strip()
        scope = str(item.get("scope", "general")).strip()
        version_period = item.get("version_period") or item.get("cycle")
        if version_period:
            version_period = str(version_period).strip()

        if not facet or not value_raw or not exact_quote:
            continue

        # Data quality filter: drop headlines, bare month/years, non-concrete values, and duplicate quotes
        from app.validation.data_quality import validate_and_dedupe_attribute
        is_valid_qual, qual_reason = validate_and_dedupe_attribute(facet, value_raw, exact_quote, seen_quotes)
        if not is_valid_qual:
            continue

        # Execute deterministic verification rules
        verif = verify_claim_in_source(source_text, exact_quote, value_raw)

        claim_id = f"clm_{uuid.uuid4().hex[:12]}"
        verified_int = 1 if verif["verified"] else 0

        conn.execute("""
            INSERT INTO claims (
                id, session_id, source_id, facet, value_raw, value_normalized,
                exact_quote, scope, cycle, version_period, verified, verification_score,
                quote_offset_start, quote_offset_end, rejection_reason, survived_redteam
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            claim_id,
            session_id,
            source_id,
            facet,
            value_raw,
            None,  # Normalizers run in L2
            exact_quote,
            scope,
            version_period,
            version_period,
            verified_int,
            verif["verification_score"],
            verif["quote_offset_start"],
            verif["quote_offset_end"],
            verif["rejection_reason"]
        ))

        processed_claims.append({
            "id": claim_id,
            "session_id": session_id,
            "source_id": source_id,
            "facet": facet,
            "value_raw": value_raw,
            "exact_quote": exact_quote,
            "scope": scope,
            "version_period": version_period,
            "cycle": version_period,
            "verified": verif["verified"],
            "verification_score": verif["verification_score"],
            "quote_offset_start": verif["quote_offset_start"],
            "quote_offset_end": verif["quote_offset_end"],
            "rejection_reason": verif["rejection_reason"]
        })

    conn.commit()
    conn.close()
    return processed_claims
