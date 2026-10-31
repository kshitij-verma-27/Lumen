import asyncio
import os
import sys
from pathlib import Path

# Ensure UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))

# Ensure live mode (real Gemini API)
os.environ["FORCE_MOCK"] = "false"

from dotenv import load_dotenv
load_dotenv(override=True)

import json
from datetime import datetime
from app.database import init_db
from app.ingest.connectors import fetch_html_document
from app.crawl.extract_entities import extract_entities_from_document
from app.crawl.store import save_entity


async def run_live_gemini_test():
    init_db()

    print("==================================================")
    print("  LIVE GEMINI ENTITY EXTRACTION & VERIFICATION TEST")
    print("==================================================")

    # 5 Seeds: 3 original + UGC and SIH
    targets = [
        {
            "id": "edu_nsp",
            "name": "National Scholarship Portal",
            "url": "https://scholarships.gov.in",
            "category": "education"
        },
        {
            "id": "edu_nta",
            "name": "National Testing Agency",
            "url": "https://nta.ac.in",
            "category": "education"
        },
        {
            "id": "biz_udyam",
            "name": "Udyam Registration",
            "url": "https://udyamregistration.gov.in",
            "category": "business"
        },
        {
            "id": "edu_ugc",
            "name": "University Grants Commission",
            "url": "https://www.ugc.gov.in",
            "category": "education"
        },
        {
            "id": "edu_sih",
            "name": "Smart India Hackathon",
            "url": "https://sih.gov.in",
            "category": "education"
        }
    ]

    total_extracted_claims = 0
    total_verified_claims = 0
    total_rejected_claims = 0

    results_summary = []
    all_rejections = []
    all_saved_entities = []

    for target in targets:
        print(f"\n[Target: {target['name']}] Fetching {target['url']}...")
        doc = await fetch_html_document(target["url"], custom_title=target["name"])

        if doc.status != "ok" or not doc.text:
            print(f"  [WARN] Failed to fetch {target['url']}: {doc.error}")
            continue

        print(f"  Fetched {len(doc.text)} chars of text. Calling Gemini live model for entity extraction...")
        entities = await extract_entities_from_document(
            doc=doc,
            domain_category=target["category"],
            source_id=target["id"]
        )

        print(f"  Extracted {len(entities)} entity/entities.")
        
        target_extracted = 0
        target_verified = 0
        target_rejected = 0

        for ent in entities:
            print(f"\n  Entity: '{ent['name']}' (type: {ent['entity_type']})")
            saved_id = save_entity(ent)
            all_saved_entities.append(ent)

            for attr in ent.get("attributes", []):
                target_extracted += 1
                total_extracted_claims += 1

                is_v = bool(attr.get("verified"))
                val = str(attr.get("attribute_value", ""))
                quote = str(attr.get("exact_quote", ""))
                reason = attr.get("rejection_reason")

                if is_v:
                    target_verified += 1
                    total_verified_claims += 1
                    status_tag = "VERIFIED [OK]"
                else:
                    target_rejected += 1
                    total_rejected_claims += 1
                    status_tag = "REJECTED [UNCERTAIN]"
                    all_rejections.append({
                        "portal": target["name"],
                        "entity": ent["name"],
                        "attribute": attr["attribute_name"],
                        "value": val,
                        "quote": quote,
                        "reason": reason or "Quote/value verification criteria not satisfied"
                    })

                print(f"    - {attr['attribute_name']:15}: {val[:60]}")
                print(f"      Quote : \"{quote[:80]}...\"")
                print(f"      Status: {status_tag} {f'(Reason: {reason})' if reason else ''}")

        results_summary.append({
            "target": target["name"],
            "url": target["url"],
            "entities": len(entities),
            "claims_extracted": target_extracted,
            "claims_verified": target_verified,
            "claims_rejected": target_rejected
        })

    # Save demo snapshot
    snapshot_data = {
        "snapshot_date": datetime.utcnow().strftime("%Y-%m-%d"),
        "label": f"Demo snapshot taken {datetime.utcnow().strftime('%d %b %Y')}",
        "total_entities": len(all_saved_entities),
        "total_claims_extracted": total_extracted_claims,
        "total_claims_verified": total_verified_claims,
        "total_claims_rejected": total_rejected_claims,
        "portals": results_summary,
        "entities": all_saved_entities,
    }
    snapshot_path = Path("data/demo_snapshot.json")
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(snapshot_data, f, indent=2, ensure_ascii=False)
    print(f"\n[OK] Saved Demo Snapshot with {len(all_saved_entities)} entities to {snapshot_path}")

    print("\n==================================================")
    print("  LIVE GEMINI EXTRACTION & VERIFICATION SUMMARY")
    print("==================================================")
    print(f"Total Claims Extracted : {total_extracted_claims}")
    print(f"Total Claims Verified  : {total_verified_claims}")
    print(f"Total Claims Rejected  : {total_rejected_claims}")
    if total_extracted_claims > 0:
        pct_verified = (total_verified_claims / total_extracted_claims) * 100
        print(f"Verification Pass Rate : {pct_verified:.1f}%")

    print("\nPer-Portal Breakdown:")
    for r in results_summary:
        print(f"  * {r['target']} ({r['url']}): {r['entities']} entities | {r['claims_extracted']} claims ({r['claims_verified']} verified, {r['claims_rejected']} rejected)")

    if all_rejections:
        print("\n==================================================")
        print("  LIST OF REJECTED CLAIMS WITH REASONS")
        print("==================================================")
        for idx, rej in enumerate(all_rejections, 1):
            print(f"\n[{idx}] Portal: {rej['portal']} | Entity: {rej['entity']}")
            print(f"    Attribute: {rej['attribute']}")
            print(f"    Value    : {rej['value']}")
            print(f"    Quote    : \"{rej['quote']}\"")
            print(f"    Reason   : {rej['reason']}")


if __name__ == "__main__":
    asyncio.run(run_live_gemini_test())
