import os
import sqlite3
import hashlib
from fastapi.testclient import TestClient

# Ensure isolated test database
os.environ["DARKSPOT_DB"] = "scratch/test_phase4_phase5.db"
os.environ["FORCE_MOCK"] = "true"

from app.database import init_db, get_db_connection
from app.main import app

client = TestClient(app)


def setup_db():
    if os.path.exists("scratch/test_phase4_phase5.db"):
        try:
            os.remove("scratch/test_phase4_phase5.db")
        except Exception:
            pass
    init_db()

    conn = get_db_connection()
    # Seed a registry source
    conn.execute("""
        INSERT INTO registry_sources (
            id, name, domain_category, subcategory, base_url, type, crawl_method,
            robots_status, reachability, trust_score, trust_reasons, notes, http_status, audit_mode
        ) VALUES (
            'test_seed_nta', 'National Testing Agency Test', 'education', 'entrance_exams',
            'https://nta.ac.in', 'official', 'html', 'allowed', 'reachable', 95.0,
            '["Statutory testing body under Ministry of Education", "Official entrance examination conduct authority", "Academic domain (.ac.in)"]',
            'Conducts JEE and NEET national entrance examinations.', 200, 'live'
        )
    """)

    # Seed an entity and entity_source
    conn.execute("""
        INSERT INTO entities (id, name, normalized_name, entity_type, domain_category, issuing_body)
        VALUES ('ent_jee_main', 'Joint Entrance Examination (Main)', 'jee main', 'exam', 'education', 'National Testing Agency')
    """)
    conn.execute("""
        INSERT INTO entity_sources (id, entity_id, source_id)
        VALUES ('link_jee_nta', 'ent_jee_main', 'test_seed_nta')
    """)

    conn.commit()
    conn.close()
    yield


def test_get_source_details_registry():
    """Verify GET /api/sources/{source_id} returns all required audit attributes."""
    res = client.get("/api/sources/test_seed_nta")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "test_seed_nta"
    assert data["name"] == "National Testing Agency Test"
    assert data["url"] == "https://nta.ac.in"
    assert data["authority"] == "official"
    assert data["trust_score"] == 95.0
    assert len(data["trust_reasons"]) <= 3
    assert "Statutory testing body under Ministry of Education" in data["trust_reasons"][0]
    assert data["reachability"] == "reachable"
    assert data["robots_status"] == "allowed"
    assert "content_hash" in data
    assert len(data["entities"]) == 1
    assert data["entities"][0]["name"] == "Joint Entrance Examination (Main)"


def test_recheck_source_registry_note():
    """Verify POST /api/sources/{source_id}/recheck includes mandatory note."""
    res = client.post("/api/sources/test_seed_nta/recheck")
    assert res.status_code == 200
    data = res.json()
    assert data["source_id"] == "test_seed_nta"
    assert "any text change counts, including small page edits" in data["note"]
    assert "any text change counts, including small page edits" in data["summary"]


def test_registry_ssrf_protection():
    """Verify SSRF attacks to loopback, private ranges, and cloud metadata are blocked."""
    # Loopback
    res = client.post("/api/registry", json={
        "name": "Loopback Attack",
        "base_url": "http://127.0.0.1:8000",
        "domain_category": "education",
        "type": "official"
    })
    assert res.status_code == 400
    assert "SSRF" in res.json()["detail"]

    # Cloud metadata
    res = client.post("/api/registry", json={
        "name": "Metadata Attack",
        "base_url": "http://169.254.169.254/latest/meta-data",
        "domain_category": "education",
        "type": "official"
    })
    assert res.status_code == 400
    assert "SSRF" in res.json()["detail"]

    # Private network
    res = client.post("/api/registry", json={
        "name": "Private Net Attack",
        "base_url": "http://192.168.1.1/admin",
        "domain_category": "education",
        "type": "official"
    })
    assert res.status_code == 400
    assert "SSRF" in res.json()["detail"]


def test_registry_add_valid_source():
    """Verify valid public source is validated on add and stored in registry."""
    res = client.post("/api/registry", json={
        "name": "Union Public Service Commission",
        "base_url": "https://upsc.gov.in",
        "domain_category": "career",
        "type": "official"
    })
    assert res.status_code == 200
    data = res.json()
    assert "source" in data
    assert "validation" in data
    assert data["source"]["name"] == "Union Public Service Commission"
    assert data["validation"]["score"] >= 50
    assert len(data["validation"]["reasons"]) > 0


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print("==================================================")
    print("  RUNNING PHASE 4 & PHASE 5 TEST SUITE (MOCK MODE)")
    print("==================================================")

    # Run fixture
    gen = setup_db()
    next(gen, None)

    print("\n[Test 1] GET /api/sources/{id}")
    test_get_source_details_registry()
    print("  [OK] Source details, trust badge (3 reasons), hash, and extracted entities verified")

    print("\n[Test 2] POST /api/sources/{id}/recheck")
    test_recheck_source_registry_note()
    print("  [OK] Re-check succeeded with note 'any text change counts, including small page edits'")

    print("\n[Test 3] SSRF Protection on Registry Addition")
    test_registry_ssrf_protection()
    print("  [OK] Blocked loopback (127.0.0.1), private network (192.168.1.1), and cloud metadata (169.254.169.254)")

    print("\n[Test 4] Registry Ingestion with Validation")
    test_registry_add_valid_source()
    print("  [OK] Successfully validated and added public source to registry")

    print("\n==================================================")
    print("  ALL PHASE 4 & PHASE 5 TESTS PASSED!")
    print("==================================================")
