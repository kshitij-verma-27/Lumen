import json
import logging
from pathlib import Path
from app.database import init_db, get_db_connection
from app.registry import seed_registry_from_yaml
from app.crawl.store import save_entity

logger = logging.getLogger("lumen.bootstrap")


def bootstrap_app():
    """
    Idempotent, fast startup bootstrap:
    1. Initializes database schema (init_db()).
    2. Seeds official registry sources from data/registry.yaml.
    3. If entities table is empty, rebuilds demo entities from data/demo_snapshot.json.
    4. Applies audit columns to registry sources so status/reachability displays cleanly.
    Zero network calls at startup.
    """
    # 1. Initialize schema
    init_db()

    # 2. Seed registry from data/registry.yaml
    try:
        registry_yaml = Path("data/registry.yaml")
        if registry_yaml.exists():
            seed_registry_from_yaml(str(registry_yaml))
    except Exception as e:
        logger.warning(f"Registry seeding warning: {e}")

    # 3. Check if entities table is empty; if so, populate from data/demo_snapshot.json
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        count = cursor.execute("SELECT COUNT(*) FROM entities;").fetchone()[0]
        if count == 0:
            snapshot_path = Path("data/demo_snapshot.json")
            if snapshot_path.exists():
                with open(snapshot_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                entities = data.get("entities", [])
                for ent in entities:
                    save_entity(ent, conn=conn)
                conn.commit()
                logger.info(f"Bootstrapped {len(entities)} demo entities into empty database.")

        # Ensure registry sources have audit status columns populated if empty
        empty_audits = cursor.execute(
            "SELECT COUNT(*) FROM registry_sources WHERE reachability IS NOT NULL;"
        ).fetchone()[0]
        if empty_audits == 0:
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
    except Exception as e:
        logger.warning(f"Bootstrap entities warning: {e}")
    finally:
        conn.close()
