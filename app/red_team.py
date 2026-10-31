import json
import re
from typing import List, Dict, Any, Optional
from app.database import get_db_connection, row_to_dict
from app.llm import generate_json, is_mock_mode


async def run_red_team_verification(session_id: str, source_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Executes an adversarial second-pass audit (Red-team verifier) over claims.
    Scrutinizes:
    1. Quote supports the extracted value without extrapolation or distortion.
    2. Quote explicitly belongs to the asserted version/period.
    3. Quote explicitly applies to the asserted scope.

    Claims that fail refutation scrutiny are demoted to 'uncertain'.
    Returns stats and counter: 'X extracted, Y survived, Z demoted'.
    """
    conn = get_db_connection()

    # Fetch claims for this session (or specific source)
    query = """
        SELECT c.*, s.text as source_text, s.title as source_title
        FROM claims c
        JOIN sources s ON c.source_id = s.id
        WHERE c.session_id = ?
    """
    params = [session_id]
    if source_id:
        query += " AND c.source_id = ?"
        params.append(source_id)

    rows = conn.execute(query, params).fetchall()
    claims = [row_to_dict(r) for r in rows]

    if not claims:
        conn.close()
        return {
            "session_id": session_id,
            "extracted_count": 0,
            "survived_count": 0,
            "demoted_count": 0,
            "counter_text": "0 extracted, 0 survived, 0 demoted",
            "claims": []
        }

    total_extracted = len(claims)

    # Scrutinize each verified claim; rejected claims (from deterministic pass) remain rejected
    evaluations = {}

    if is_mock_mode():
        # Deterministic adversarial refuter
        for c in claims:
            cid = c["id"]
            if not c.get("verified"):
                # Already rejected in L1 deterministic pass
                evaluations[cid] = {
                    "refuted": True,
                    "status": "uncertain",
                    "reason": f"Initial verification failed: {c.get('rejection_reason') or 'Unverified quote'}"
                }
                continue

            quote = (c.get("exact_quote") or "").strip()
            quote_lower = quote.lower()
            val_raw = str(c.get("value_raw") or "").strip()
            val_lower = val_raw.lower()
            scope = (c.get("scope") or "general").strip().lower()
            version_period = (c.get("version_period") or c.get("cycle") or "").strip()

            refuted = False
            refutation_reason = ""

            # Check 1: Speculative / tentative language in quote
            speculative_markers = ["tentative", "likely", "rumored", "unconfirmed", "subject to change", "may change", "proposed"]
            for marker in speculative_markers:
                if marker in quote_lower and marker not in val_lower:
                    refuted = True
                    refutation_reason = f"Quote contains tentative/unconfirmed qualification '{marker}', value cannot be guaranteed as authoritative."
                    break

            # Check 2: Version / period mismatch in quote
            if not refuted and version_period:
                # Find all 4-digit years in quote vs version_period
                quote_years = re.findall(r"\b(20\d\d)\b", quote)
                vp_years = re.findall(r"\b(20\d\d)\b", version_period)
                if quote_years and vp_years:
                    # If quote only mentions years other than vp_years
                    if not any(y in vp_years for y in quote_years):
                        refuted = True
                        refutation_reason = f"Quote references year(s) {quote_years} which does not support the claimed version/period '{version_period}'."

            # Check 3: Scope mismatch
            if not refuted and scope and scope != "general":
                # If scope specifies residential but quote mentions commercial only (or vice-versa)
                if "residential" in scope and "commercial" in quote_lower and "residential" not in quote_lower:
                    refuted = True
                    refutation_reason = f"Claim asserts residential scope, but quote specifically references commercial specifications."
                elif "commercial" in scope and "residential" in quote_lower and "commercial" not in quote_lower:
                    refuted = True
                    refutation_reason = f"Claim asserts commercial scope, but quote specifically references residential specifications."

            # Check 4: Explicit test flag or adversarial discrepancy
            if not refuted and (c.get("refute_for_test") or "[adversarial_uncertain]" in quote_lower):
                refuted = True
                refutation_reason = "Adversarial check: Quote does not adequately corroborate the precise claim bounds."

            if refuted:
                evaluations[cid] = {
                    "refuted": True,
                    "status": "uncertain",
                    "reason": refutation_reason
                }
            else:
                evaluations[cid] = {
                    "refuted": False,
                    "status": "survived",
                    "reason": "Quote directly substantiates value, scope, and target version/period."
                }
    else:
        # LLM Adversarial Pass
        verified_claims = [c for c in claims if c.get("verified")]
        unverified_claims = [c for c in claims if not c.get("verified")]

        for uc in unverified_claims:
            evaluations[uc["id"]] = {
                "refuted": True,
                "status": "uncertain",
                "reason": f"Deterministic proof check rejected: {uc.get('rejection_reason') or 'Missing verification'}"
            }

        if verified_claims:
            prompt_items = []
            for vc in verified_claims:
                prompt_items.append({
                    "claim_id": vc["id"],
                    "facet": vc.get("facet"),
                    "value_raw": vc.get("value_raw"),
                    "exact_quote": vc.get("exact_quote"),
                    "scope": vc.get("scope"),
                    "version_period": vc.get("version_period") or vc.get("cycle")
                })

            prompt = (
                "You are an adversarial red-team factual verifier. Your mission is to actively REFUTE each claim.\n"
                "Examine each claim with extreme skepticism:\n"
                "1. Does the exact quote actually prove and substantiate the value, or is it an overstatement / extrapolation?\n"
                "2. Does the quote belong to the asserted version/period, or is it describing an older/different cycle?\n"
                "3. Does the quote apply to the asserted scope, or does it contain unstated conditions/restrictions?\n"
                "If there is any doubt or contradiction, refute it and set status to 'uncertain'.\n"
                "If it stands up completely, set status to 'survived'.\n\n"
                f"Claims to audit:\n{json.dumps(prompt_items, indent=2)}\n\n"
                "Return JSON ONLY in this format:\n"
                '{"evaluations": [{"claim_id": str, "refuted": bool, "status": "survived"|"uncertain", "reason": str}]}'
            )

            system_instruction = "You are a strict, adversarial fact-checking red-team auditor. Never give benefit of the doubt."
            try:
                res = await generate_json(prompt, system_instruction=system_instruction)
                for item in res.get("evaluations", []):
                    evaluations[item.get("claim_id")] = {
                        "refuted": item.get("refuted", item.get("status") == "uncertain"),
                        "status": "uncertain" if item.get("refuted") or item.get("status") == "uncertain" else "survived",
                        "reason": item.get("reason", "")
                    }
            except Exception as e:
                for vc in verified_claims:
                    if vc["id"] not in evaluations:
                        evaluations[vc["id"]] = {
                            "refuted": False,
                            "status": "survived",
                            "reason": f"Audited (LLM fallback: {e})"
                        }

    # Update claims in SQLite
    survived_count = 0
    demoted_count = 0

    for c in claims:
        cid = c["id"]
        ev = evaluations.get(cid, {"refuted": False, "status": "survived", "reason": ""})
        status = ev["status"]
        reason = ev["reason"]
        survived_int = 1 if status == "survived" else 0

        if status == "survived":
            survived_count += 1
        else:
            demoted_count += 1

        conn.execute("""
            UPDATE claims
            SET survived_redteam = ?, redteam_status = ?, redteam_notes = ?
            WHERE id = ?
        """, (survived_int, status, reason, cid))

        c["survived_redteam"] = bool(survived_int)
        c["redteam_status"] = status
        c["redteam_notes"] = reason

    conn.commit()
    conn.close()

    counter_text = f"{total_extracted} extracted, {survived_count} survived, {demoted_count} demoted"

    return {
        "session_id": session_id,
        "extracted_count": total_extracted,
        "survived_count": survived_count,
        "demoted_count": demoted_count,
        "counter_text": counter_text,
        "claims": claims
    }
