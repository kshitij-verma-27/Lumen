import asyncio
import os
import sys
import json
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ["FORCE_MOCK"] = "false"

from dotenv import load_dotenv
load_dotenv(override=True)

from app.database import init_db
from app.ingest.connectors import fetch_html_document
from app.crawl.extract_entities import (
    chunk_document_text,
    extract_entities_from_chunk,
    ALLOWED_ENTITY_TYPES,
    ALLOWED_ATTRIBUTES,
    BANNED_STATUS_WORDS,
    extract_deterministic_links_and_contacts,
)
from app.trust import verify_claim_in_source


async def main():
    targets = [
        {"name": "National Scholarship Portal", "url": "https://scholarships.gov.in", "category": "education"},
        {"name": "National Testing Agency", "url": "https://nta.ac.in", "category": "education"},
        {"name": "Udyam Registration", "url": "https://udyamregistration.gov.in", "category": "business"},
        {"name": "University Grants Commission", "url": "https://www.ugc.gov.in", "category": "education"},
        {"name": "Smart India Hackathon", "url": "https://sih.gov.in", "category": "education"},
    ]

    all_raw_claims = []
    dropped_before_verification = []

    for t in targets:
        print(f"Fetching {t['name']} ({t['url']})...")
        doc = await fetch_html_document(t["url"], custom_title=t["name"])
        if doc.status != "ok" or not doc.text:
            print(f"  [ERROR] Failed to fetch {t['name']}")
            continue

        chunks = chunk_document_text(doc.text)
        print(f"  Document text: {len(doc.text)} chars across {len(chunks)} chunk(s). Calling Gemini...")

        for c_idx, chunk in enumerate(chunks):
            raw_ents = await extract_entities_from_chunk(chunk, doc.url, t["category"])
            for ent in raw_ents:
                if not isinstance(ent, dict):
                    dropped_before_verification.append({
                        "portal": t["name"],
                        "entity": "Unknown",
                        "raw_claim": str(ent),
                        "reason": "Entity is not a dictionary"
                    })
                    continue

                ent_name = ent.get("name", "Unknown Entity")
                raw_attrs = ent.get("attributes", [])
                if isinstance(raw_attrs, dict):
                    raw_attrs = [{"attribute_name": k, **v} if isinstance(v, dict) else {"attribute_name": k, "attribute_value": str(v)} for k, v in raw_attrs.items()]

                for a in raw_attrs:
                    if not isinstance(a, dict):
                        continue
                    attr_name = str(a.get("attribute_name", "")).lower().strip()
                    attr_val = str(a.get("attribute_value") or a.get("value") or "").strip()
                    quote = str(a.get("exact_quote") or a.get("quote") or a.get("text") or "").strip()

                    # Check drop conditions
                    drop_reason = None
                    if not attr_name:
                        drop_reason = "Missing attribute name"
                    elif attr_name not in ALLOWED_ATTRIBUTES:
                        drop_reason = f"Attribute '{attr_name}' not in ALLOWED_ATTRIBUTES"
                    elif attr_name in ("apply_link", "contact"):
                        drop_reason = f"Attribute '{attr_name}' handled deterministically from HTML anchors"
                    elif not attr_val:
                        drop_reason = "Empty attribute value"
                    elif not quote:
                        drop_reason = "Empty exact quote"
                    elif attr_val.lower() in BANNED_STATUS_WORDS:
                        drop_reason = f"Banned status word '{attr_val}' used as value"

                    if drop_reason:
                        dropped_before_verification.append({
                            "portal": t["name"],
                            "entity": ent_name,
                            "attribute": attr_name,
                            "value": attr_val,
                            "quote": quote,
                            "reason": drop_reason
                        })
                        all_raw_claims.append({
                            "portal": t["name"],
                            "entity": ent_name,
                            "attribute": attr_name,
                            "value": attr_val,
                            "quote": quote,
                            "verified": "DROPPED",
                            "score": 0.0,
                            "reason": drop_reason,
                            "dropped": True
                        })
                    else:
                        # Ran through verify_claim_in_source
                        v_res = verify_claim_in_source(doc.text, quote, attr_val)
                        is_v = v_res.get("verified", False)
                        score = v_res.get("verification_score", 0.0)
                        rej_reason = v_res.get("rejection_reason")

                        all_raw_claims.append({
                            "portal": t["name"],
                            "entity": ent_name,
                            "attribute": attr_name,
                            "value": attr_val,
                            "quote": quote,
                            "verified": "YES" if is_v else "NO",
                            "score": score,
                            "reason": rej_reason or ("Verified by exact quote containment" if is_v else "Verification failed"),
                            "dropped": False
                        })

    # Save to JSON for exact presentation
    out_path = Path("scratch/raw_claims_audit.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_raw_claims": len(all_raw_claims),
            "dropped_count": len(dropped_before_verification),
            "claims": all_raw_claims,
            "dropped": dropped_before_verification
        }, f, indent=2, ensure_ascii=False)

    print(f"\n[DONE] Captured {len(all_raw_claims)} total raw claims.")
    print(f"Dropped before verification: {len(dropped_before_verification)}")
    verified_count = sum(1 for c in all_raw_claims if c["verified"] == "YES")
    rejected_count = sum(1 for c in all_raw_claims if c["verified"] == "NO")
    print(f"Verified: {verified_count} | Rejected: {rejected_count}")


if __name__ == "__main__":
    asyncio.run(main())
