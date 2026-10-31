# Source Validation Agent Rules

## Verification Tiers & Rubric
1. **Tier 1 - Deterministic Rule Check**:
   - HTTPS validation: mandatory for secure classification.
   - Domain class: `.gov.in`, `.nic.in`, `.ac.in`, `.edu`, or registered owner domain.
   - Known registry match: instant positive score signal.
   - Lookalike check: homoglyph and Levenshtein distance check against official domains.
   - Scam heuristics: fee for free government schemes, false urgency, guaranteed results, shortened URLs (`bit.ly`, `tinyurl`), sensitive credential harvesting.
2. **Tier 2 - LLM Explanation & Signal**:
   - LLM reviews text signals to propose classification and draft human explanation.
   - LLM cannot override code rules; decision is rule-enforced.
3. **Tier 3 - Red-Team Refutation**:
   - System attempts to argue why the source might be misleading, copied, or outdated before confirming an "official" label.

## Output Schema
Returns `{trust_level, score, reasons, checks, validated_at}`:
- `trust_level`: `official` (85-100), `secondary` (65-84), `community` (45-64), `low` (20-44), `suspicious` (0-19), `blocked` (error).
- `reasons`: Array of human-readable explanation strings. Top 3 displayed on badge.
- `checks`: Dict of individual pass/fail metrics.
- `manual_override`: Optional admin/user flag with reason note.
