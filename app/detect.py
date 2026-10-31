import json
import uuid
import re
from datetime import datetime, date
from typing import Dict, Any, List, Optional, Tuple
from app.database import get_db_connection, row_to_dict
from app.models import FacetDefinition
from app.normalize import normalize_claim_value, normalize_version_period, is_duration_expression
from app.independence import detect_and_group_sources

# Synonym map for backward compatibility
normalize_cycle = normalize_version_period


def are_version_periods_compatible(vp_a: Optional[str], vp_b: Optional[str]) -> bool:
    """Returns True if two version periods represent the same period (e.g. '2025' and '2025-26')."""
    if not vp_a or not vp_b:
        return True
    if vp_a == vp_b:
        return True
    # Handle single year vs multi-year cycle: e.g. '2025' and '2025-26'
    m_a = re.match(r'^(20\d\d)-(\d{2})$', vp_a)
    m_b = re.match(r'^(20\d\d)-(\d{2})$', vp_b)
    if m_a and not m_b:
        y1 = m_a.group(1)
        y2 = str(int(y1[:2]) * 100 + int(m_a.group(2)))
        if vp_b in (y1, y2):
            return True
    elif m_b and not m_a:
        y1 = m_b.group(1)
        y2 = str(int(y1[:2]) * 100 + int(m_b.group(2)))
        if vp_a in (y1, y2):
            return True
    return False


def get_version_period_end_date(vp: Optional[str]) -> Optional[date]:
    """
    Infers the approximate calendar end date of an academic semester, cycle, or year
    (e.g. 'Fall 2025' -> 2025-12-31, 'Spring 2025' -> 2025-05-31, '2023-24' -> 2024-06-30).
    Returns None for non-calendar product versions (e.g. 'Gen 7').
    """
    if not vp:
        return None
    vp_clean = str(vp).strip()

    # Term + Year e.g. "Fall 2025", "Spring 2026"
    m_term = re.search(r'\b(Fall|Autumn|Spring|Summer|Winter)\s+(20\d\d)\b', vp_clean, re.IGNORECASE)
    if m_term:
        term = m_term.group(1).lower()
        yr = int(m_term.group(2))
        if term in ("fall", "autumn"):
            return date(yr, 12, 31)
        elif term == "spring":
            return date(yr, 5, 31)
        elif term == "summer":
            return date(yr, 8, 31)
        elif term == "winter":
            return date(yr, 3, 31)

    # Multi-year academic cycle e.g. "2023-24", "2024-2025"
    m_cycle = re.search(r'\b(20\d\d)[/-](\d{2,4})\b', vp_clean)
    if m_cycle:
        y1 = int(m_cycle.group(1))
        y2_str = m_cycle.group(2)
        y2 = int(y2_str) if len(y2_str) == 4 else int(str(y1)[:2] + y2_str)
        return date(y2, 6, 30)

    # Single calendar year e.g. "2024", "2025"
    m_yr = re.search(r'\b(20\d\d)\b', vp_clean)
    if m_yr:
        yr = int(m_yr.group(1))
        return date(yr, 12, 31)

    return None


SCOPE_SYNONYMS = [
    {"residential", "domestic", "home", "household", "residential systems", "residential consumers"},
    {"commercial", "industrial", "business", "enterprise"},
    {"general", "all", "standard", "base", "default", "any"}
]


GENERIC_SCOPE_WORDS = {
    "general", "all", "any", "standard", "base", "default", "overall", "application", "apply",
    "guidelines", "documents", "required", "scheme", "portal", "phase", "current", "process",
    "rule", "rules", "terms", "install", "installation", "rooftop", "solar", "policy", "notice"
}


def are_scopes_compatible(scope_a: str, scope_b: str) -> bool:
    """Returns True if two scopes are equivalent or compatible (e.g. 'residential systems' vs 'domestic')."""
    sa = (scope_a or "general").strip().lower()
    sb = (scope_b or "general").strip().lower()
    if sa == sb:
        return True
    if sa in ("all", "general", "any", "standard") or sb in ("all", "general", "any", "standard"):
        return True
    if sa in sb or sb in sa:
        return True

    words_a = set(re.findall(r'\w+', sa))
    words_b = set(re.findall(r'\w+', sb))
    if (words_a and words_a.issubset(GENERIC_SCOPE_WORDS)) or (words_b and words_b.issubset(GENERIC_SCOPE_WORDS)):
        return True

    for syn_set in SCOPE_SYNONYMS:
        if (sa in syn_set and sb in syn_set) or (any(s in sa for s in syn_set) and any(s in sb for s in syn_set)):
            return True
    return False


def classify_conflict_pair(
    claim_a: Dict[str, Any],
    claim_b: Dict[str, Any],
    facet_def: FacetDefinition,
    current_version_period: Optional[str]
) -> Dict[str, Any]:
    """
    Conflict Explainer Taxonomy (Universal across all topics):
    Classifies discrepancies between two claims on the same facet into:
    1. 'version_period_difference' — originating from different cycles, semesters, or product revisions
    2. 'scope_difference' — originating from different category scopes (e.g. GPU models, residency, quota)
    3. 'formatting_difference' — functionally identical values with cosmetic phrasing differences
    4. 'partial_overlap' — list facets with shared vs additional items
    5. 'real_conflict' — true factual contradiction within the same scope and version/period
    """
    val_a_raw = claim_a["value_raw"]
    val_b_raw = claim_b["value_raw"]

    vp_a = normalize_version_period(claim_a.get("version_period") or claim_a.get("cycle"))
    vp_b = normalize_version_period(claim_b.get("version_period") or claim_b.get("cycle"))

    scope_a = (claim_a.get("scope") or "general").strip().lower()
    scope_b = (claim_b.get("scope") or "general").strip().lower()

    norm_a = claim_a.get("norm_data", {})
    norm_b = claim_b.get("norm_data", {})

    # Check 1: Version / Period Difference
    if vp_a and vp_b and not are_version_periods_compatible(vp_a, vp_b):
        return {
            "conflict_type": "version_period_difference",
            "label": "Version / Period Difference",
            "severity": "medium",
            "explanation": (
                f"Source '{claim_a['source_title']}' quotes version/period {vp_a} ('{val_a_raw}'), "
                f"whereas source '{claim_b['source_title']}' quotes version/period {vp_b} ('{val_b_raw}'). "
                "This is a version, cycle, or product revision difference over time, not a direct contradiction within the same period."
            ),
            "sources": [claim_a, claim_b]
        }

    # Check 2: Scope Difference
    if not are_scopes_compatible(scope_a, scope_b):
        return {
            "conflict_type": "scope_difference",
            "label": "Scope Difference (Category / Variant Variance)",
            "severity": "medium",
            "explanation": (
                f"Discrepancy is due to category or variant scope: '{val_a_raw}' applies to '{claim_a.get('scope')}', "
                f"while '{val_b_raw}' applies to '{claim_b.get('scope')}'. "
                "Specifications, standards, or criteria differ per variant."
            ),
            "sources": [claim_a, claim_b]
        }

    # Check 3: Formatting Difference (Functional Equivalence) & Partial Overlap
    if norm_a and norm_b and norm_a.get("type") == norm_b.get("type"):
        ntype = norm_a.get("type")

        # Currency Comparison
        if ntype == "currency":
            amt_a = norm_a.get("data", {}).get("amount")
            amt_b = norm_b.get("data", {}).get("amount")
            cur_a = norm_a.get("data", {}).get("currency")
            cur_b = norm_b.get("data", {}).get("currency")
            if amt_a is not None and amt_b is not None and amt_a == amt_b:
                cur_label = cur_a or "units"
                return {
                    "conflict_type": "formatting_difference",
                    "label": "Formatting Difference (Functionally Equivalent)",
                    "severity": "low",
                    "explanation": f"Functionally equivalent amount ({cur_label} {amt_a:g}), differing only in phrasing ('{val_a_raw}' vs '{val_b_raw}').",
                    "sources": [claim_a, claim_b]
                }

        # Unit Number Comparison (Watts, GB, TB, Hz, etc.)
        elif ntype == "unit_number":
            val_a = norm_a.get("data", {}).get("value")
            val_b = norm_b.get("data", {}).get("value")
            unit_a = norm_a.get("data", {}).get("unit")
            unit_b = norm_b.get("data", {}).get("unit")
            if val_a is not None and val_b is not None and val_a == val_b and unit_a == unit_b:
                return {
                    "conflict_type": "formatting_difference",
                    "label": "Formatting Difference (Functionally Equivalent)",
                    "severity": "low",
                    "explanation": f"Functionally equivalent specification ({val_a} {unit_a}), differing only in cosmetic wording ('{val_a_raw}' vs '{val_b_raw}').",
                    "sources": [claim_a, claim_b]
                }

        # Percentage Comparison
        elif ntype == "percentage":
            pct_a = norm_a.get("data", {}).get("percentage")
            pct_b = norm_b.get("data", {}).get("percentage")
            if pct_a is not None and pct_b is not None and pct_a == pct_b:
                return {
                    "conflict_type": "formatting_difference",
                    "label": "Formatting Difference (Functionally Equivalent)",
                    "severity": "low",
                    "explanation": f"Functionally equivalent percentage ({pct_a}%), differing only in wording ('{val_a_raw}' vs '{val_b_raw}').",
                    "sources": [claim_a, claim_b]
                }

        # Date Comparison
        elif ntype == "date":
            iso_a = norm_a.get("data", {}).get("iso")
            iso_b = norm_b.get("data", {}).get("iso")
            if iso_a and iso_b and iso_a == iso_b:
                return {
                    "conflict_type": "formatting_difference",
                    "label": "Formatting Difference (Functionally Equivalent)",
                    "severity": "low",
                    "explanation": f"Functionally equivalent date ({iso_a}), differing only in date format phrasing.",
                    "sources": [claim_a, claim_b]
                }

        # List Comparison (Shared vs Extra Items)
        elif ntype == "list":
            items_a = set(norm_a.get("data") or [])
            items_b = set(norm_b.get("data") or [])
            if items_a and items_b:
                if items_a == items_b:
                    return {
                        "conflict_type": "formatting_difference",
                        "label": "Formatting Difference (Functionally Equivalent)",
                        "severity": "low",
                        "explanation": f"Functionally equivalent list of items: {', '.join(sorted(items_a))}.",
                        "sources": [claim_a, claim_b]
                    }
                else:
                    shared_items = sorted(list(items_a & items_b))
                    extra_a = sorted(list(items_a - items_b))
                    extra_b = sorted(list(items_b - items_a))
                    all_extra = sorted(list(items_a ^ items_b))

                    detail_parts = []
                    if shared_items:
                        detail_parts.append(f"Shared: [{', '.join(shared_items)}]")
                    if extra_a:
                        detail_parts.append(f"Extra in '{claim_a['source_title']}': [{', '.join(extra_a)}]")
                    if extra_b:
                        detail_parts.append(f"Extra in '{claim_b['source_title']}': [{', '.join(extra_b)}]")

                    return {
                        "conflict_type": "partial_overlap",
                        "label": "Partial Overlap (Additional Items / Discrepancy)",
                        "severity": "medium",
                        "explanation": (
                            f"List items have partial overlap rather than a direct contradiction. "
                            f"{'; '.join(detail_parts)}."
                        ),
                        "shared_items": shared_items,
                        "extra_items": all_extra,
                        "sources": [claim_a, claim_b]
                    }

    # Check 4: Real Factual Conflict
    return {
        "conflict_type": "real_conflict",
        "label": "Real Factual Conflict",
        "severity": "critical",
        "explanation": (
            f"Direct factual contradiction within the same version/period and scope: '{claim_a['source_title']}' ({claim_a['source_authority']}) "
            f"states '{val_a_raw}' while '{claim_b['source_title']}' ({claim_b['source_authority']}) states '{val_b_raw}'."
        ),
        "sources": [claim_a, claim_b]
    }


def is_deadline_or_expiry_facet(facet_def: FacetDefinition) -> bool:
    """Returns True if the facet is a deadline, expiration, return window, or cutoff date."""
    if facet_def.is_deadline:
        return True
    fid = facet_def.id.lower()
    fname = facet_def.name.lower()
    keywords = ("deadline", "expiry", "closing", "expiration", "last_date", "valid_until", "return_window", "promo_end")
    return any(k in fid or k in fname for k in keywords)


def run_gap_detection(session_id: str) -> Dict[str, Any]:
    """
    Deterministic Gap Detection Engine (Universal across all topics):
    1. Normalizes all verified claims in the session.
    2. Derives current version/period from user-set value or newest official source.
    3. Runs Conflict Explainer: classifies real conflicts, version/period differences, and list overlaps.
    4. Evaluates deadline/expiry passed status against current calendar date.
    5. Produces consequence-weighted, specific actionable checklist using session's official domain.
    """
    conn = get_db_connection()

    # 1. Load session & target facets
    sess = conn.execute("SELECT * FROM research_sessions WHERE id = ?", (session_id,)).fetchone()
    if not sess:
        conn.close()
        raise ValueError(f"Session {session_id} not found")

    target_facets_data = json.loads(sess["facets_json"])
    target_facets = {f["id"]: FacetDefinition(**f) for f in target_facets_data}
    official_domain = sess["official_domain"] or "the official website/portal"

    # 1.5 Run Source Independence clustering (detects near-duplicates and updates original_group_id)
    independence_data = detect_and_group_sources(session_id, conn)

    # 2. Load verified claims joined with source metadata
    rows = conn.execute("""
        SELECT c.*, s.title as source_title, s.url as source_url,
               s.authority as source_authority, s.published_date, s.published_date_origin,
               s.original_group_id
        FROM claims c
        JOIN sources s ON c.source_id = s.id
        WHERE c.session_id = ? AND c.verified = 1
        ORDER BY c.facet ASC
    """, (session_id,)).fetchall()

    claims = [row_to_dict(r) for r in rows]

    # Normalize all verified claims and update database
    for c in claims:
        facet_def = target_facets.get(c["facet"])
        exp_type = facet_def.expected_type if facet_def else "text"
        norm_result = normalize_claim_value(c["facet"], c["value_raw"], exp_type)
        norm_json = json.dumps(norm_result)
        c["value_normalized"] = norm_json
        c["norm_data"] = norm_result

        conn.execute(
            "UPDATE claims SET value_normalized = ? WHERE id = ?",
            (norm_json, c["id"])
        )

    conn.commit()
    conn.close()

    # 3. Derive Current Version / Period dynamically:
    today = datetime.now().date()

    all_vps = set()
    official_vps = set()
    for c in claims:
        vp = normalize_version_period(c.get("version_period") or c.get("cycle"))
        if vp:
            all_vps.add(vp)
            if c["source_authority"] == "official":
                official_vps.add(vp)

    user_vp = sess["target_version_period"] or (sess["target_cycle"] if "target_cycle" in sess.keys() else None)
    newest_source_vp = sorted(list(official_vps or all_vps), reverse=True)[0] if (official_vps or all_vps) else None
    version_period_warning = None

    if user_vp:
        current_version_period = normalize_version_period(user_vp)
        if not newest_source_vp or newest_source_vp < current_version_period:
            version_period_warning = f"No source covers the current version/period ({current_version_period}). The newest version/period found across sources is '{newest_source_vp or 'none'}'."
    else:
        if newest_source_vp:
            current_version_period = newest_source_vp
            version_period_warning = f"No source covers the current cycle or period later than '{newest_source_vp}'. No source confirms whether a later version or period has superseded '{newest_source_vp}'."
        else:
            current_version_period = None
            version_period_warning = "No version or period information found in any source. No source covers the current cycle."

    # Check if the version/period the user asked about is already over relative to today's date
    target_vp_to_check = user_vp or current_version_period
    if not target_vp_to_check and sess.get("goal"):
        goal_term = re.search(r'\b(Fall|Autumn|Spring|Summer|Winter)\s+(20\d\d)\b', sess["goal"], re.IGNORECASE)
        if goal_term:
            target_vp_to_check = f"{goal_term.group(1).capitalize()} {goal_term.group(2)}"
        else:
            goal_cyc = re.search(r'\b(20\d\d)[/-](\d{2,4})\b', sess["goal"])
            if goal_cyc:
                target_vp_to_check = normalize_version_period(goal_cyc.group(0))

    vp_end_date = get_version_period_end_date(target_vp_to_check)
    is_target_period_expired = bool(vp_end_date and vp_end_date < today)

    if is_target_period_expired:
        date_str = vp_end_date.strftime("%d %b %Y")
        # Remove leading zero if present, e.g. "01 Jan" -> "1 Jan"
        if date_str.startswith("0"):
            date_str = date_str[1:]
        expired_vp_warning = (
            f"The version or period you asked about ('{target_vp_to_check}') is assumed to have ended around {date_str} "
            f"relative to today's date ({today.strftime('%d %b %Y')}), because period end dates are inferred. You may be researching an expired academic term or closed period."
        )
        if version_period_warning:
            version_period_warning = f"{expired_vp_warning} {version_period_warning}"
        else:
            version_period_warning = expired_vp_warning

    # 4. Group claims by facet
    facet_groups: Dict[str, List[Dict[str, Any]]] = {fid: [] for fid in target_facets.keys()}
    for c in claims:
        if c["facet"] in facet_groups:
            facet_groups[c["facet"]].append(c)

    gaps = []
    checklist = []
    conflict_explanations = []
    confidence_summary = {}

    # Warning item if user asks about an already expired version or period
    if is_target_period_expired and target_vp_to_check and vp_end_date:
        date_str = vp_end_date.strftime("%d %b %Y")
        if date_str.startswith("0"):
            date_str = date_str[1:]
        expired_gap_item = {
            "id": f"gap_period_expired_{normalize_version_period(target_vp_to_check)}",
            "gap_type": "cycle_warning",
            "facet": "version_period",
            "facet_name": "Target Version / Period",
            "confidence": "Expired Period",
            "priority": "high",
            "title": f"Target Period Likely Ended: '{target_vp_to_check}' (assumed around {date_str})",
            "description": expired_vp_warning,
            "consequence": f"Researching an expired term ('{target_vp_to_check}') produces outdated application criteria, closed admission rounds, or void policies.",
            "action_needed": f"Verify active or upcoming periods on {official_domain}: Confirm whether newer guidelines have been published for current cycles.",
            "sources_involved": []
        }
        gaps.append(expired_gap_item)
        checklist.append(expired_gap_item)

    # Warning item if no source covers current version/period
    if version_period_warning and current_version_period and not is_target_period_expired:
        vp_gap_item = {
            "id": "gap_version_period_warning",
            "gap_type": "cycle_warning",
            "facet": "version_period",
            "facet_name": "Version / Period",
            "confidence": "Warning",
            "priority": "high",
            "title": f"Unconfirmed Version / Period: {current_version_period}",
            "description": version_period_warning,
            "consequence": "Relying on parameters from an outdated revision, cycle, or model generation risks using obsolete specifications, expired terms, or superseded rules.",
            "action_needed": f"Check {official_domain} to verify whether newer specifications or guidelines have been released for {current_version_period}.",
            "sources_involved": []
        }
        gaps.append(vp_gap_item)
        checklist.append(vp_gap_item)

    # 5. Evaluate each target facet
    for facet_id, facet_def in target_facets.items():
        f_claims = facet_groups.get(facet_id, [])
        facet_consequence = facet_def.consequence or f"Acting without verifying {facet_def.name} risks unforeseen costs, disqualification, or incorrect commitments."
        priority_weight = facet_def.importance if facet_def.importance in ("critical", "high", "medium") else "high"

        # Case A: MISSING FACET (Dark spot)
        if len(f_claims) == 0:
            confidence_summary[facet_id] = "Not found"
            action_text = f"Search {official_domain} for '{facet_def.name}': None of the provided sources mention this specification or requirement, creating an information blindspot."

            gap_item = {
                "id": f"gap_missing_{facet_id}",
                "gap_type": "missing",
                "facet": facet_id,
                "facet_name": facet_def.name,
                "confidence": "Not found",
                "priority": priority_weight,
                "title": f"Missing: {facet_def.name} not found in any source",
                "description": f"None of the provided sources mention '{facet_def.name}'. This represents an unaddressed information dark spot.",
                "consequence": facet_consequence,
                "action_needed": action_text,
                "sources_involved": []
            }
            gaps.append(gap_item)
            checklist.append(gap_item)
            continue

        # Case B: SINGLE-SOURCE CLAIM
        if len(f_claims) == 1:
            claim = f_claims[0]
            auth = claim["source_authority"]
            is_official = (auth == "official")

            confidence_label = "Single-source"
            confidence_summary[facet_id] = confidence_label

            if not is_official:
                action_text = f"Verify {facet_def.name} on {official_domain}: The value '{claim['value_raw']}' was only found on secondary portal '{claim['source_title']}'. Corroborate with primary documentation before deciding."
                gap_item = {
                    "id": f"gap_no_official_{facet_id}",
                    "gap_type": "no_official_source",
                    "facet": facet_id,
                    "facet_name": facet_def.name,
                    "confidence": confidence_label,
                    "priority": "high",
                    "title": f"No Official Source: {facet_def.name} only in {auth} source",
                    "description": f"The value '{claim['value_raw']}' was only found in a {auth}-authority source ({claim['source_title']}), with no official confirmation.",
                    "consequence": facet_consequence,
                    "action_needed": action_text,
                    "sources_involved": [{
                        "source_title": claim["source_title"],
                        "authority": auth,
                        "value": claim["value_raw"],
                        "quote": claim["exact_quote"]
                    }]
                }
                gaps.append(gap_item)
                checklist.append(gap_item)
            else:
                action_text = f"Corroborate {facet_def.name} on {official_domain}: Relies solely on '{claim['source_title']}'. Confirm no recent revisions or amendments have been posted."
                gap_item = {
                    "id": f"gap_single_{facet_id}",
                    "gap_type": "single_source",
                    "facet": facet_id,
                    "facet_name": facet_def.name,
                    "confidence": confidence_label,
                    "priority": "medium",
                    "title": f"Single Source: {facet_def.name} relies on one document",
                    "description": f"Verified only in '{claim['source_title']}'. No other source corroborated this claim.",
                    "consequence": "Single-source claims are vulnerable if the document is an initial draft or later amended.",
                    "action_needed": action_text,
                    "sources_involved": [{
                        "source_title": claim["source_title"],
                        "authority": auth,
                        "value": claim["value_raw"],
                        "quote": claim["exact_quote"]
                    }]
                }
                gaps.append(gap_item)
                checklist.append(gap_item)

        # Case C: MULTIPLE SOURCES -> RUN CONFLICT EXPLAINER
        if len(f_claims) > 1:
            real_conflicts = []
            partial_overlaps = []
            vp_diffs = []
            scope_diffs = []

            for i in range(len(f_claims)):
                for j in range(i + 1, len(f_claims)):
                    ca = f_claims[i]
                    cb = f_claims[j]
                    expl = classify_conflict_pair(ca, cb, facet_def, current_version_period)
                    conflict_explanations.append({
                        "facet": facet_id,
                        "facet_name": facet_def.name,
                        **expl
                    })

                    if expl["conflict_type"] == "real_conflict":
                        real_conflicts.append((ca, cb, expl))
                    elif expl["conflict_type"] == "partial_overlap":
                        partial_overlaps.append((ca, cb, expl))
                    elif expl["conflict_type"] == "version_period_difference":
                        vp_diffs.append((ca, cb, expl))
                    elif expl["conflict_type"] == "scope_difference":
                        scope_diffs.append((ca, cb, expl))

            # Only flag as CONFLICT if there is a REAL factual contradiction!
            if real_conflicts:
                confidence_summary[facet_id] = "Conflicting"
                ca, cb, expl = real_conflicts[0]

                off_claim = ca if ca["source_authority"] == "official" else cb if cb["source_authority"] == "official" else ca
                oth_claim = cb if off_claim == ca else ca

                action_text = (
                    f"Verify {facet_def.name} on {official_domain}: '{off_claim['source_title']}' ({off_claim['source_authority']}) states '{off_claim['value_raw']}', "
                    f"contradicting '{oth_claim['source_title']}' ({oth_claim['source_authority']}) which states '{oth_claim['value_raw']}'. "
                    f"Confirm the primary specifications before proceeding."
                )

                gap_item = {
                    "id": f"gap_conflict_{facet_id}",
                    "gap_type": "conflict",
                    "conflict_taxonomy": "real_conflict",
                    "facet": facet_id,
                    "facet_name": facet_def.name,
                    "confidence": "Conflicting",
                    "priority": "critical",
                    "title": f"Real Conflict: {facet_def.name}",
                    "description": expl["explanation"],
                    "consequence": facet_consequence,
                    "action_needed": action_text,
                    "sources_involved": [
                        {"source_title": ca["source_title"], "authority": ca["source_authority"], "value": ca["value_raw"], "quote": ca["exact_quote"]},
                        {"source_title": cb["source_title"], "authority": cb["source_authority"], "value": cb["value_raw"], "quote": cb["exact_quote"]}
                    ]
                }
                gaps.append(gap_item)
                checklist.append(gap_item)

            elif partial_overlaps:
                confidence_summary[facet_id] = "Partial Overlap"
                ca, cb, expl = partial_overlaps[0]
                extra_items = expl.get("extra_items", [])
                extra_str = ", ".join(extra_items)
                action_text = (
                    f"Confirm {facet_def.name} on {official_domain}: '{ca['source_title']}' and '{cb['source_title']}' "
                    f"have partial overlap. Verify whether additional item(s) [{extra_str}] are mandatory."
                )
                gap_item = {
                    "id": f"gap_overlap_{facet_id}",
                    "gap_type": "partial_overlap",
                    "conflict_taxonomy": "partial_overlap",
                    "facet": facet_id,
                    "facet_name": facet_def.name,
                    "confidence": "Partial Overlap",
                    "priority": "medium",
                    "title": f"Partial Overlap: {facet_def.name}",
                    "description": expl["explanation"],
                    "consequence": facet_consequence,
                    "action_needed": action_text,
                    "sources_involved": [
                        {"source_title": ca["source_title"], "authority": ca["source_authority"], "value": ca["value_raw"], "quote": ca["exact_quote"]},
                        {"source_title": cb["source_title"], "authority": cb["source_authority"], "value": cb["value_raw"], "quote": cb["exact_quote"]}
                    ]
                }
                gaps.append(gap_item)
                checklist.append(gap_item)

            elif vp_diffs:
                confidence_summary[facet_id] = "Corroborated"
                ca, cb, expl = vp_diffs[0]
                vp_a = normalize_version_period(ca.get("version_period") or ca.get("cycle"))
                vp_b = normalize_version_period(cb.get("version_period") or cb.get("cycle"))
                new_claim = ca if (vp_a and current_version_period and vp_a == current_version_period) else cb
                old_claim = cb if new_claim == ca else ca
                old_vp = vp_b if new_claim == ca else vp_a

                action_text = (
                    f"Confirm {facet_def.name} for current version/period {current_version_period} on {official_domain}: "
                    f"Ignore previous revision ({old_vp}) figure '{old_claim['value_raw']}' from '{old_claim['source_title']}' and verify latest specification '{new_claim['value_raw']}'."
                )

                gap_item = {
                    "id": f"gap_timediff_{facet_id}",
                    "gap_type": "time_difference",
                    "conflict_taxonomy": "version_period_difference",
                    "facet": facet_id,
                    "facet_name": facet_def.name,
                    "confidence": "Corroborated",
                    "priority": "medium",
                    "title": f"Version / Period Difference (Not a Conflict): {facet_def.name}",
                    "description": expl["explanation"],
                    "consequence": f"Parameters from previous revision {old_vp} have been superseded and may no longer apply to {current_version_period}.",
                    "action_needed": action_text,
                    "sources_involved": [
                        {"source_title": ca["source_title"], "authority": ca["source_authority"], "version_period": vp_a, "value": ca["value_raw"], "quote": ca["exact_quote"]},
                        {"source_title": cb["source_title"], "authority": cb["source_authority"], "version_period": vp_b, "value": cb["value_raw"], "quote": cb["exact_quote"]}
                    ]
                }
                gaps.append(gap_item)
                checklist.append(gap_item)

            elif scope_diffs:
                confidence_summary[facet_id] = "Corroborated"
                ca, cb, expl = scope_diffs[0]
                gap_item = {
                    "id": f"gap_scopediff_{facet_id}",
                    "gap_type": "scope_difference",
                    "conflict_taxonomy": "scope_difference",
                    "facet": facet_id,
                    "facet_name": facet_def.name,
                    "confidence": "Corroborated",
                    "priority": "medium",
                    "title": f"Scope Difference: {facet_def.name}",
                    "description": expl["explanation"],
                    "consequence": "Confusing general criteria with specific variant criteria leads to mistaken assumptions.",
                    "action_needed": f"Identify your specific target variant ({ca.get('scope')} vs {cb.get('scope')}) on {official_domain} before deciding.",
                    "sources_involved": [
                        {"source_title": ca["source_title"], "authority": ca["source_authority"], "scope": ca.get("scope"), "value": ca["value_raw"], "quote": ca["exact_quote"]},
                        {"source_title": cb["source_title"], "authority": cb["source_authority"], "scope": cb.get("scope"), "value": cb["value_raw"], "quote": cb["exact_quote"]}
                    ]
                }
                gaps.append(gap_item)
                checklist.append(gap_item)
            else:
                distinct_original_ids = {c.get("original_group_id") or c.get("source_id") for c in f_claims}
                if len(distinct_original_ids) == 1:
                    # COPIES COUNT AS A SINGLE SOURCE!
                    # All claims come from the same original source (or near-duplicate copies)
                    first_claim = f_claims[0]
                    auth = first_claim.get("source_authority", "official")
                    confidence_summary[facet_id] = f"Single-source ({auth}: 1 original, {len(f_claims)} copies)"

                    # Generate Single-Source Gap Item
                    action_text = f"Corroborate {facet_def.name} on {official_domain}: Appears across {len(f_claims)} sources, but text analysis detected they are copies of 1 original ('{first_claim['source_title']}'). Confirm independently."
                    gap_item = {
                        "id": f"gap_single_copies_{facet_id}",
                        "gap_type": "single_source",
                        "facet": facet_id,
                        "facet_name": facet_def.name,
                        "confidence": "Single-source (Copied Sources)",
                        "priority": "medium",
                        "title": f"Single Source: {facet_def.name} relies on 1 original source ({len(f_claims)} copies)",
                        "description": f"Verified across {len(f_claims)} documents, but these sources are near-duplicates/copies of '{first_claim['source_title']}'. No independent source corroborated this claim.",
                        "consequence": "Secondary portals and aggregators frequently echo official notices or one another verbatim. Without independent corroboration, amendments or retracted circulars will be missed.",
                        "action_needed": action_text,
                        "sources_involved": [{
                            "source_title": c["source_title"],
                            "authority": c.get("source_authority"),
                            "value": c["value_raw"],
                            "quote": c["exact_quote"]
                        } for c in f_claims]
                    }
                    gaps.append(gap_item)
                    checklist.append(gap_item)
                else:
                    confidence_summary[facet_id] = "Corroborated"

        # Check for OUTDATED version/period in any claim relative to current_version_period
        for c in f_claims:
            vp = normalize_version_period(c.get("version_period") or c.get("cycle"))
            if vp and current_version_period and vp < current_version_period:
                action_text = f"Discard archived {facet_def.name} value '{c['value_raw']}' from '{c['source_title']}': Document is from past revision {vp}. Check current {current_version_period} guidelines on {official_domain}."
                gap_item = {
                    "id": f"gap_outdated_{facet_id}_{c['id']}",
                    "gap_type": "outdated",
                    "facet": facet_id,
                    "facet_name": facet_def.name,
                    "confidence": "Single-source",
                    "priority": "high",
                    "title": f"Outdated Version / Period: {facet_def.name} from {vp}",
                    "description": f"Source '{c['source_title']}' references version/period {vp}, which has been superseded by current version/period {current_version_period}.",
                    "consequence": f"Information from past revisions ({vp}) is invalid or superseded for the current {current_version_period} release.",
                    "action_needed": action_text,
                    "sources_involved": [{
                        "source_title": c["source_title"],
                        "authority": c["source_authority"],
                        "version_period": vp,
                        "value": c["value_raw"],
                        "quote": c["exact_quote"]
                    }]
                }
                gaps.append(gap_item)
                checklist.append(gap_item)

        # Check for DEADLINE / EXPIRY ALREADY PASSED
        if is_deadline_or_expiry_facet(facet_def) or facet_def.expected_type == "date":
            passed_deadline_claims = []
            for c in f_claims:
                vp = normalize_version_period(c.get("version_period") or c.get("cycle"))
                if vp and current_version_period and vp < current_version_period:
                    continue  # Skip old-period deadlines already handled by outdated check

                val_raw = c.get("value_raw", "")
                if is_duration_expression(val_raw):
                    continue  # Durations like "30 days" or "return window" are not calendar deadlines

                norm_date = c.get("norm_data", {})
                if norm_date.get("type") == "date":
                    iso_str = norm_date.get("data", {}).get("iso")
                    if iso_str:
                        try:
                            deadline_date = datetime.strptime(iso_str, "%Y-%m-%d").date()
                            if deadline_date < today:
                                passed_deadline_claims.append((c, iso_str))
                        except Exception:
                            pass

            if passed_deadline_claims:
                date_summaries = []
                sources_inv = []
                for c, iso_str in passed_deadline_claims:
                    date_summaries.append(f"'{c['value_raw']}' ({iso_str}) from '{c['source_title']}'")
                    sources_inv.append({
                        "source_title": c["source_title"],
                        "authority": c["source_authority"],
                        "value": c["value_raw"],
                        "quote": c["exact_quote"]
                    })

                dates_str = "; ".join(date_summaries)
                action_text = f"Check {official_domain} for an extension, updated schedule, or next upcoming period for {facet_def.name}: Stated date(s) [{dates_str}] have closed relative to today ({today.isoformat()})."
                passed_originals = {c.get("original_group_id") or c.get("source_id") for c, _ in passed_deadline_claims}
                gap_item = {
                    "id": f"gap_passed_{facet_id}",
                    "gap_type": "deadline_passed",
                    "facet": facet_id,
                    "facet_name": facet_def.name,
                    "confidence": "Corroborated" if len(passed_originals) > 1 else "Single-source",
                    "priority": "critical",
                    "title": f"Deadline Expired: {facet_def.name} closed for {current_version_period or 'current period'}",
                    "description": f"All stated deadlines or expiration dates have passed in the past relative to today's date ({today.isoformat()}): {dates_str}.",
                    "consequence": facet_consequence,
                    "action_needed": action_text,
                    "sources_involved": sources_inv
                }
                gaps.append(gap_item)
                checklist.append(gap_item)

    # 6. Sort checklist by priority weight: critical (1) > high (2) > medium (3) > low (4)
    priority_order = {"critical": 1, "high": 2, "medium": 3, "low": 4}
    checklist.sort(key=lambda x: priority_order.get(x["priority"], 99))

    is_vp_assumed = bool(not user_vp and current_version_period)

    # Attach actionable email drafts for official inquiries
    try:
        from app.email_drafts import generate_email_draft, find_source_emails
        discovered_contacts = find_source_emails(session_id, conn)
        best_contact = discovered_contacts[0] if discovered_contacts else None
        for g in gaps:
            if "email_draft" not in g:
                g["email_draft"] = generate_email_draft(
                    g,
                    official_domain=official_domain,
                    target_period=current_version_period,
                    discovered_contact=best_contact
                )
    except Exception:
        pass

    return {
        "current_version_period": current_version_period,
        "current_cycle": current_version_period,  # Backward compatible alias
        "is_version_period_assumed": is_vp_assumed,
        "is_cycle_assumed": is_vp_assumed,  # Backward compatible alias
        "version_period_warning": version_period_warning,
        "cycle_warning": version_period_warning,  # Backward compatible alias
        "total_gaps": len(gaps),
        "confidence_summary": confidence_summary,
        "gaps": gaps,
        "checklist": checklist,
        "conflict_explanations": conflict_explanations,
        "independence": independence_data
    }


def build_coverage_matrix(session_id: str) -> Dict[str, Any]:
    """
    Coverage Matrix Generator (Universal across all topics):
    Builds a complete Facets x Sources grid with visual dark spot indicators.
    - Rows: Target Facets defined for the session (with importance pill).
    - Columns: Sources ingested in the session.
    - Cells: Verified claim data, version/period tags, conflict markers, or missing state.
    - Row Status: dark_spot (missing across ALL sources), conflict, version_period_difference, single_source, corroborated.
    """
    conn = get_db_connection()
    sess = conn.execute("SELECT * FROM research_sessions WHERE id = ?", (session_id,)).fetchone()
    if not sess:
        conn.close()
        raise ValueError(f"Session {session_id} not found")

    target_facets_data = json.loads(sess["facets_json"])
    target_facets = [FacetDefinition(**f) for f in target_facets_data]
    official_domain = sess["official_domain"] or "the official source"

    # Fetch sources
    src_rows = conn.execute("""
        SELECT id, title, url, authority, published_date, published_date_origin, content_hash, original_group_id
        FROM sources
        WHERE session_id = ?
        ORDER BY CASE WHEN authority = 'official' THEN 0 WHEN authority = 'secondary' THEN 1 ELSE 2 END, id ASC
    """, (session_id,)).fetchall()
    sources = [row_to_dict(r) for r in src_rows]

    # Fetch claims (verified)
    claim_rows = conn.execute("""
        SELECT c.*, s.title as source_title, s.authority as source_authority, s.original_group_id
        FROM claims c
        JOIN sources s ON c.source_id = s.id
        WHERE c.session_id = ? AND c.verified = 1
        ORDER BY c.facet ASC, c.id ASC
    """, (session_id,)).fetchall()
    conn.close()

    claims = [row_to_dict(r) for r in claim_rows]

    # Run detection
    det_results = run_gap_detection(session_id)
    current_version_period = det_results.get("current_version_period")
    is_vp_assumed = det_results.get("is_version_period_assumed", False)
    vp_warning = det_results.get("version_period_warning")
    gaps = det_results.get("gaps", [])
    independence_data = det_results.get("independence", {})
    source_details = independence_data.get("source_details_map", {})

    for s in sources:
        sid = s["id"]
        det = source_details.get(sid, {})
        s["original_group_id"] = det.get("original_group_id", s.get("original_group_id") or sid)
        s["is_original"] = det.get("is_original", (s["original_group_id"] == sid))
        s["copied_from_title"] = det.get("copied_from_title")

    # Map conflicting, partial overlap, & version-difference facets
    conflict_facet_ids = {g["facet"] for g in gaps if g.get("gap_type") == "conflict"}
    overlap_facet_ids = {g["facet"] for g in gaps if g.get("gap_type") == "partial_overlap"}
    vp_diff_facet_ids = {g["facet"] for g in gaps if g.get("gap_type") in ("version_period_difference", "time_difference")}

    # Build claim lookup: facet -> source_id -> claim
    facet_source_claims: Dict[str, Dict[str, Dict[str, Any]]] = {f.id: {} for f in target_facets}
    for c in claims:
        fid = c["facet"]
        sid = c["source_id"]
        if fid in facet_source_claims:
            facet_source_claims[fid][sid] = c

    # Build Facet Rows
    matrix_rows = []
    dark_spots_count = 0
    covered_facets_count = 0

    for fdef in target_facets:
        fid = fdef.id
        covered_sources = facet_source_claims.get(fid, {})
        num_covered = len(covered_sources)

        # Count independent originals covering this facet
        covered_original_ids = {
            c.get("original_group_id") or sid
            for sid, c in covered_sources.items()
        }
        num_independent_covered = len(covered_original_ids)

        # Determine Row Consensus Status
        if num_covered == 0:
            status = "dark_spot"
            status_label = "🌑 Dark Spot (Missing Across All Sources)"
            dark_spots_count += 1
        elif fid in conflict_facet_ids:
            status = "conflict"
            status_label = "⚡ Real Conflict"
            covered_facets_count += 1
        elif fid in overlap_facet_ids:
            status = "partial_overlap"
            status_label = "📋 Partial Overlap (Extra Items)"
            covered_facets_count += 1
        elif fid in vp_diff_facet_ids:
            status = "time_difference"
            status_label = "⏳ Version / Period Difference"
            covered_facets_count += 1
        elif num_independent_covered == 1:
            status = "single_source"
            auth = list(covered_sources.values())[0]["source_authority"]
            if len(covered_sources) > 1:
                status_label = f"🔍 Single-Source ({len(covered_sources)} copies of 1 original)"
            else:
                status_label = f"🔍 Single-Source ({auth})"
            covered_facets_count += 1
        else:
            status = "corroborated"
            status_label = "✓ Corroborated"
            covered_facets_count += 1

        # Populate cell for each source
        cells = {}
        for s in sources:
            sid = s["id"]
            if sid in covered_sources:
                c = covered_sources[sid]
                vp = normalize_version_period(c.get("version_period") or c.get("cycle"))
                is_outdated = bool(vp and current_version_period and vp < current_version_period)
                is_conflicting = bool(fid in conflict_facet_ids)

                norm_val = None
                if c.get("value_normalized"):
                    try:
                        norm_val = json.loads(c["value_normalized"])
                    except Exception:
                        norm_val = None

                cells[sid] = {
                    "has_claim": True,
                    "claim_id": c["id"],
                    "value_raw": c["value_raw"],
                    "value_normalized": norm_val,
                    "version_period": vp,
                    "cycle": vp,
                    "is_outdated": is_outdated,
                    "is_conflicting": is_conflicting,
                    "exact_quote": c["exact_quote"],
                    "quote_offset_start": c["quote_offset_start"],
                    "quote_offset_end": c["quote_offset_end"],
                    "source_id": sid,
                    "source_title": s["title"],
                    "source_authority": s["authority"]
                }
            else:
                cells[sid] = {
                    "has_claim": False,
                    "source_id": sid,
                    "source_title": s["title"],
                    "source_authority": s["authority"]
                }

        matrix_rows.append({
            "facet_id": fid,
            "facet_name": fdef.name,
            "description": fdef.description,
            "expected_type": fdef.expected_type,
            "importance": fdef.importance,
            "consequence": fdef.consequence,
            "is_deadline": fdef.is_deadline,
            "status": status,
            "status_label": status_label,
            "sources_covered": num_covered,
            "total_sources": len(sources),
            "cells": cells
        })

    total_facets = len(target_facets)
    coverage_score = round((covered_facets_count / total_facets) * 100, 1) if total_facets > 0 else 0.0

    return {
        "session_id": session_id,
        "official_domain": official_domain,
        "current_version_period": current_version_period,
        "current_cycle": current_version_period,  # Backward compatible alias
        "is_version_period_assumed": is_vp_assumed,
        "is_cycle_assumed": is_vp_assumed,  # Backward compatible alias
        "version_period_warning": vp_warning,
        "cycle_warning": vp_warning,  # Backward compatible alias
        "stats": {
            "total_facets": total_facets,
            "covered_facets": covered_facets_count,
            "dark_spots_count": dark_spots_count,
            "conflicts_count": len(conflict_facet_ids),
            "coverage_score": coverage_score
        },
        "sources": sources,
        "matrix": matrix_rows,
        "independence": independence_data
    }
