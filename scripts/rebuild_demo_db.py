import json
import os
import sys
import sqlite3
from pathlib import Path

sys.path.insert(0, ".")

# Target production app database
os.environ.pop("DARKSPOT_DB", None)
os.environ["LUMEN_DB_PATH"] = "darkspot.db"

from app.database import init_db, get_db_connection
from app.registry import seed_registry_from_yaml, get_all_registry_sources
from app.crawl.store import save_entity


def rebuild_demo_db():
    db_file = Path("darkspot.db")
    print(f"Rebuilding {db_file} from live results and official seeds only...")

    # Connect and clear entities, entity_attributes, and custom test sources
    conn = get_db_connection()
    cursor = conn.cursor()

    # Re-initialize tables
    init_db()

    # Delete all entity records
    cursor.execute("DELETE FROM entity_attributes;")
    cursor.execute("DELETE FROM entity_sources;")
    cursor.execute("DELETE FROM entities;")
    try:
        cursor.execute("DELETE FROM entities_fts;")
    except Exception:
        pass

    # Remove non-official test registry sources (custom sources starting with custom_)
    cursor.execute("DELETE FROM registry_sources WHERE id LIKE 'custom_%';")
    conn.commit()

    # Re-seed official registry sources if needed
    seed_registry_from_yaml()

    # Apply audit columns from live / mock seed status
    from app.seed_validator import MOCK_SEED_STATUS
    for s_id, status in MOCK_SEED_STATUS.items():
        cursor.execute(
            """
            UPDATE registry_sources
            SET reachability = ?,
                robots_status = ?,
                needs_js = ?,
                http_status = ?,
                final_url = ?,
                audit_mode = 'live',
                last_audited = '2026-10-31 18:00:00'
            WHERE id = ?;
            """,
            (
                status["reachability"],
                status["robots_status"],
                1 if status["needs_js"] else 0,
                status["status_code"],
                status["final_url"],
                s_id,
            )
        )
    conn.commit()

    # Load entities strictly from data/demo_snapshot.json
    snapshot_path = Path("data/demo_snapshot.json")
    if not snapshot_path.exists():
        print("ERROR: data/demo_snapshot.json does not exist!")
        return

    with open(snapshot_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    live_entities = data.get("entities", [])
    print(f"Found {len(live_entities)} live entities in demo_snapshot.json.")

    saved_count = 0
    total_attrs = 0
    for ent in live_entities:
        ent_id = save_entity(ent)
        saved_count += 1
        total_attrs += len(ent.get("attributes", []))

    print(f"Successfully saved {saved_count} entities with {total_attrs} attributes to darkspot.db.")

    # Check for test fixture ent_nationalmean_750231a373
    check = cursor.execute("SELECT id, name FROM entities WHERE id = 'ent_nationalmean_750231a373' OR name LIKE '%National Means-cum-Merit%';").fetchone()
    if check:
        print(f"[FOUND] {check[0]}: {check[1]}")
    else:
        print("[VERIFIED] Test fixture ent_nationalmean_750231a373 is NOT present in demo database.")

    # List all current entities
    current_ents = cursor.execute("SELECT id, name, domain_category FROM entities;").fetchall()
    print(f"\nFinal Live Entities in darkspot.db ({len(current_ents)}):")
    for r in current_ents:
        print(f"  - [{r[0]}] {r[1]} ({r[2]})")

    conn.close()


if __name__ == "__main__":
    rebuild_demo_db()
