# Digital Dark Spot

> **AI-assisted information-gap detection web platform.**
> Reveals what is **missing**, **conflicting**, and **outdated** across sources with verifiable proof.

---

## Core Principle: Deterministic Verification

The LLM is strictly restricted to narrow text extraction. **All verification, quote matching, number cross-referencing, and authority classification are performed by deterministic Python code.**

1. **Quote Verification**: The LLM returns an `exact_quote`. Code searches for the quote in raw source text using exact substring matching first, falling back to `rapidfuzz` partial ratio alignment (>= 88% threshold). If not found, the claim is dropped.
2. **Value-in-Span Enforcement**: All digits, dates, and amounts in `value_raw` must literally appear inside the matched text span in the original document.
3. **Minimum Quote Length**: Requires >= 15 characters to prevent vague 1-word proofs.
4. **Authority Rules**: Domains ending in `.gov.in`, `.nic.in`, `.ac.in`, `.edu`, or matching the user-confirmed official domain receive `official` authority. News and educational publishers receive `secondary`. Aggregator blogs, forums, and unverified sites receive `low`.
5. **Rejected Claims Audit**: Every hallucinated or dropped claim is stored in SQLite with `verified = 0` and an explicit `rejection_reason`.
6. **Zero-Cost Offline Fixture Mode**: Automatically runs with bundled sample sources even without a Gemini API key.

---

## Quick Start

### 1. Install Dependencies
```bash
python -m pip install -r requirements.txt
```

### 2. Configure Environment (Optional)
If you have a Gemini API key:
```bash
copy .env.example .env
# Edit .env and set:
# GEMINI_API_KEY=your_key_here
```
*Note: If no API key is provided, the platform automatically runs in deterministic offline fixture mode using synthetic sample data.*

### 3. Run Automated Tests
```bash
# Run L1 Core + Adversarial Verification Suite
python test_l1.py

# Run L2 Normalizers, Gap Detection & Prioritized Checklist Suite
python test_l2.py
```

### 4. Start the Application
```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** in your browser.

---

## 1-Click Demo Walkthrough (L1 & L2)

1. Open **`http://127.0.0.1:8000`**.
2. Notice the top mode badge showing whether Live Gemini or Offline Fixture mode is active.
3. Click the **"🚀 1-Click Demo (Load 3 Synthetic Sample Sources)"** button on the setup card.
4. The system will:
   - Ingest 3 synthetic sample documents:
     - `[Synthetic Sample Data] Official Guidelines 2025-26` (Official authority)
     - `[Synthetic Sample Data] Sarkari Help Blog Alert 2025` (Low authority aggregator with conflicting numbers)
     - `[Synthetic Sample Data] Ministry Circular 2023-24` (Archived past academic cycle)
   - Extract and verify all claims in deterministic code with exact character offset tracking.
   - Run **L2 Gap Detection**:
     - ⚡ **Conflicts Caught**: Flags the conflict between Official (Rs. 3,50,000) and Aggregator (Rs. 1,50,000).
     - ⏳ **Outdated Cycles Caught**: Flags 3 claims from the 2023-24 circular as outdated compared to the 2025-26 cycle.
     - 🌑 **Dark Spots Caught**: Identifies unmentioned facets (`Selection Process`, `Renewal Conditions`) as critical missing information.
     - 📋 **Prioritized Checklist**: Generates a consequence-ranked checklist (Critical $\rightarrow$ High $\rightarrow$ Medium) with concrete next actions and interactive checkboxes.

