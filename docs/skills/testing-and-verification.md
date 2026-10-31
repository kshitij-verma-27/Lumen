# Testing and Verification Rules

## Mock Mode Guarantee
- All test suites must execute deterministically without network calls or external API keys using `FORCE_MOCK=true`.
- LLM calls must have zero-network mock fallbacks in `app/llm.py`.
- Network fetchers must accept local fixtures or mock responses during testing.

## Non-Negotiable Test Discipline
- **Never weaken existing assertions**: If an existing test fails, fix the underlying bug or reconciliation logic. Never lower thresholds, remove asserts, or comment out checks.
- When modifying any existing test file, display explicit before/after diffs in reports.
- Keep baseline suites (`test_l1.py`, `test_l2.py`, `test_l3_matrix.py`, `test_all_topics.py`, `test_source_independence.py`, `test_new_batch.py`) 100% green.

## Adversarial Verification Cases
Every new feature must include adversarial test scenarios:
1. **Lookalike Domains**: Typosquats, hyphenated homoglyphs (e.g. `scholarships-gov.in`).
2. **Fee-for-Free Scams**: Asking for fees on free government portals.
3. **Copied Blogs**: Verifying duplicate text clustering and original source attribution.
4. **Outdated Period**: Proving that expired periods (e.g. 2024 deadlines in 2026) trigger warnings.
5. **Exact Quote Hallucinations**: Catching slight alterations in figures, percentages, and dates.
