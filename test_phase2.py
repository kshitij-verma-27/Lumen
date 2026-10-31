import asyncio
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

os.environ["FORCE_MOCK"] = "true"
os.environ["DARKSPOT_DB"] = "test_darkspot.db"
os.environ["LUMEN_ALLOW_TEST_DOMAINS"] = "true"

from app.database import init_db, get_db_connection
from app.ingest.models import Document
from app.crawl.crawler import run_crawl_job, get_crawl_job
from app.crawl.extract_entities import (
    extract_entities_from_document,
    merge_duplicate_entities,
    ALLOWED_ENTITY_TYPES,
    ALLOWED_ATTRIBUTES,
)
from app.crawl.store import (
    save_entity,
    get_entity_by_id,
    search_entities,
)
from app.crawl.detect_adapter import analyze_entity_gaps
from app.crawl.queue import start_crawl_job
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


async def run_phase2_tests():
    print("==================================================")
    print("  RUNNING PHASE 2 TEST SUITE (MOCK MODE)")
    print("==================================================")

    init_db()

    # ----------------------------------------------------
    # TEST 1: Categories API
    # ----------------------------------------------------
    print("\n[Test 1] GET /api/categories")
    resp = client.get("/api/categories")
    assert resp.status_code == 200
    cats = resp.json().get("categories", [])
    assert len(cats) == 5
    cat_ids = {c["id"] for c in cats}
    assert cat_ids == {"education", "career", "public_services", "research", "business"}
    print(f"  [OK] Categories API returned all 5 domains: {list(cat_ids)}")

    # ----------------------------------------------------
    # TEST 2: Registry API (List & Add)
    # ----------------------------------------------------
    print("\n[Test 2] GET & POST /api/registry")
    r_list = client.get("/api/registry?domain_category=education")
    assert r_list.status_code == 200
    edu_sources = r_list.json().get("sources", [])
    assert len(edu_sources) >= 5
    print(f"  [OK] Registry returned {len(edu_sources)} education sources")

    # Add custom source
    post_payload = {
        "name": "State Research Council",
        "base_url": "https://research.state.gov.in",
        "domain_category": "research",
        "subcategory": "funding_grants",
        "type": "official",
        "owner": "Department of S&T"
    }
    r_add = client.post("/api/registry", json=post_payload)
    assert r_add.status_code == 200
    added_src = r_add.json()["source"]
    assert added_src["name"] == "State Research Council"
    print(f"  [OK] Successfully added source {added_src['id']} with validation score {r_add.json()['validation']['score']}")

    # ----------------------------------------------------
    # TEST 3: Bounded Crawl Job (Queue & Crawler)
    # ----------------------------------------------------
    print("\n[Test 3] POST /api/crawl & GET /api/crawl/{id}")
    crawl_payload = {
        "start_url": "https://scholarships.gov.in",
        "domain_category": "education",
        "max_pages": 15
    }
    c_resp = client.post("/api/crawl", json=crawl_payload)
    assert c_resp.status_code == 200
    job_id = c_resp.json()["job_id"]
    assert job_id.startswith("job_")
    print(f"  [OK] Spawned crawl job {job_id}")

    # Wait for mock job completion
    await asyncio.sleep(0.5)
    s_resp = client.get(f"/api/crawl/{job_id}")
    assert s_resp.status_code == 200
    job_info = s_resp.json()
    assert job_info["id"] == job_id
    assert job_info["status"] in ("pending", "running", "completed")
    print(f"  [OK] Crawl job progress: status={job_info['status']}, progress={job_info['progress_pct']}%")

    # ----------------------------------------------------
    # TEST 4: Entity Extraction with Code Quote Verification
    # ----------------------------------------------------
    print("\n[Test 4] Entity Extraction & Code Quote Verification")
    sample_text = (
        "National Means-cum-Merit Scholarship Scheme (NMMSS). "
        "Eligibility: Students studying in Class IX whose parental annual income is not more than Rs. 3,50,000. "
        "Application deadline: Last date for online submission of applications is 30th November 2026. "
        "Application fee: No application fee is charged from applicants. "
        "Issuing authority: Department of School Education and Literacy, Ministry of Education."
    )
    test_doc = Document(
        url="https://scholarships.gov.in/nmmss",
        title="National Means-cum-Merit Scholarship Scheme",
        text=sample_text,
        published_date="2026-03-01",
        date_origin="meta",
        fetched_at="2026-03-01T12:00:00",
        content_hash="hash_test_123",
        status="ok",
    )

    entities = await extract_entities_from_document(test_doc, domain_category="education", source_id="src_edu_nsp")
    assert len(entities) >= 1
    ent = entities[0]
    assert ent["entity_type"] in ALLOWED_ENTITY_TYPES
    print(f"  [OK] Extracted Entity: '{ent['name']}' (type={ent['entity_type']})")

    # Verify attributes carry exact_quote and verified flags
    attr_names = {a["attribute_name"] for a in ent["attributes"]}
    for a in ent["attributes"]:
        assert a["attribute_name"] in ALLOWED_ATTRIBUTES
        assert a["exact_quote"] != ""
        assert a["exact_quote"] in sample_text, f"Quote '{a['exact_quote']}' must be in document text"
        assert a["verified"] in (0, 1)
        assert a["uncertain"] in (0, 1)
        print(f"    - Attribute: {a['attribute_name']} | Value: {a['attribute_value']} | Verified: {bool(a['verified'])}")

    # ----------------------------------------------------
    # TEST 5: Entity Deduplication & Merging Across Sources
    # ----------------------------------------------------
    print("\n[Test 5] Entity Deduplication & Cross-Source Merge")
    doc2_text = (
        "National Means cum Merit Scholarship Scheme 2026. "
        "Official portal apply link: Apply online at scholarships.gov.in. "
        "Parental income limit: Rs. 3,50,000 per annum."
    )
    doc2 = Document(
        url="https://education.gov.in/nmmss-notice",
        title="National Means cum Merit Scholarship Scheme 2026",
        text=doc2_text,
        content_hash="hash_doc2",
        status="ok",
    )
    entities2 = await extract_entities_from_document(doc2, domain_category="education", source_id="src_moe_portal")

    merged = merge_duplicate_entities(entities + entities2)
    assert len(merged) == 1, f"Expected 1 merged entity, got {len(merged)}"
    merged_ent = merged[0]
    assert "src_edu_nsp" in merged_ent["source_ids"]
    assert "src_moe_portal" in merged_ent["source_ids"]
    print(f"  [OK] Successfully merged near-duplicate entities across 2 sources: {merged_ent['source_ids']}")

    # ----------------------------------------------------
    # TEST 6: Entity Storage & FTS5 Full-Text Search
    # ----------------------------------------------------
    print("\n[Test 6] Entity Storage & FTS5 Search")
    saved_id = save_entity(merged_ent)
    assert saved_id.startswith("ent_")

    retrieved = get_entity_by_id(saved_id)
    assert retrieved is not None
    assert retrieved["name"] == merged_ent["name"]
    assert len(retrieved["attributes"]) >= len(merged_ent["attributes"])
    print(f"  [OK] Entity {saved_id} saved and retrieved with {len(retrieved['attributes'])} verified attributes")

    # Search with FTS5
    search_res = search_entities(query="Merit Scholarship", domain_category="education")
    assert len(search_res) >= 1
    assert any(e["id"] == saved_id for e in search_res)
    print(f"  [OK] FTS5 search found entity '{search_res[0]['name']}' with high relevance")

    # ----------------------------------------------------
    # TEST 7: Detect.py Engine Reuse (Gaps, Conflicts & Checklist)
    # ----------------------------------------------------
    print("\n[Test 7] Detect Engine Reuse per Entity (/api/entities/{id}/gaps)")
    gaps_res = analyze_entity_gaps(saved_id)
    assert "gaps" in gaps_res
    assert "checklist" in gaps_res
    assert "coverage_matrix" in gaps_res
    print(f"  [OK] Gap analysis executed: {len(gaps_res['gaps'])} gaps detected | {len(gaps_res['checklist'])} actions | coverage matrix generated")

    # Test API GET /api/entities/{id}
    api_e = client.get(f"/api/entities/{saved_id}")
    assert api_e.status_code == 200
    assert api_e.json()["id"] == saved_id

    # Test API GET /api/entities/{id}/gaps
    api_g = client.get(f"/api/entities/{saved_id}/gaps")
    assert api_g.status_code == 200
    assert "coverage_matrix" in api_g.json()

    print("\n==================================================")
    print("  ALL PHASE 2 UNIT & PIPELINE CHECKS PASSED!")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(run_phase2_tests())
