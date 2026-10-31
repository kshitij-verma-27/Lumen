import asyncio
from datetime import datetime
import logging
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from app.database import get_db_connection
from app.crawl.crawler import run_crawl_job, get_crawl_job, update_job_status
from app.crawl.extract_entities import extract_entities_from_document, merge_duplicate_entities
from app.crawl.store import save_entity
from app.registry import find_registry_match_by_url

logger = logging.getLogger(__name__)


async def _execute_crawl_pipeline(
    job_id: str,
    start_url: str,
    domain_category: str,
    allowed_paths: Optional[List[str]] = None,
    max_pages: int = 15,
):
    try:
        # 1. Crawl documents bounded by max_pages=15 and depth=2
        docs = await run_crawl_job(
            job_id=job_id,
            start_url=start_url,
            allowed_paths=allowed_paths,
            max_pages=max_pages,
            max_depth=2,
        )

        # 2. Extract entities with code quote verification
        all_entities = []
        reg_match = find_registry_match_by_url(start_url)
        source_id = reg_match["id"] if reg_match else f"src_{uuid.uuid4().hex[:8]}"

        for doc in docs:
            extracted = await extract_entities_from_document(
                doc=doc,
                domain_category=domain_category,
                source_id=source_id,
            )
            all_entities.extend(extracted)

        # 3. Merge duplicate entities
        merged = merge_duplicate_entities(all_entities)

        # 4. Save merged entities to database and FTS5 index
        saved_ids = []
        for ent in merged:
            ent_id = save_entity(ent)
            saved_ids.append(ent_id)

        update_job_status(
            job_id,
            status="completed",
            progress_pct=100.0,
            processed_count=len(docs),
            total_count=len(docs),
        )
        logger.info(f"Crawl job {job_id} completed: crawled {len(docs)} pages, extracted {len(saved_ids)} entities")

    except Exception as e:
        logger.error(f"Crawl pipeline failed for job {job_id}: {e}")
        update_job_status(job_id, status="failed", progress_pct=100.0, error=str(e))


def start_crawl_job(
    start_url: str,
    domain_category: str = "education",
    allowed_paths: Optional[List[str]] = None,
    max_pages: int = 15,
) -> str:
    """
    Spawns an on-demand crawl job in the background and returns job_id.
    """
    job_id = f"job_{uuid.uuid4().hex[:10]}"
    conn = get_db_connection()
    now_iso = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    domain = urlparse(start_url).netloc
    conn.execute(
        """
        INSERT INTO crawl_jobs (
            id, category, domain, status, progress_pct, processed_count, total_count, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (job_id, domain_category, domain, "pending", 0.0, 0, max_pages, now_iso, now_iso),
    )
    conn.commit()
    conn.close()

    # Launch background pipeline safely across both async event loop and worker thread
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(
            _execute_crawl_pipeline(
                job_id=job_id,
                start_url=start_url,
                domain_category=domain_category,
                allowed_paths=allowed_paths,
                max_pages=min(max_pages, 15),
            )
        )
    except RuntimeError:
        import threading
        t = threading.Thread(
            target=lambda: asyncio.run(
                _execute_crawl_pipeline(
                    job_id=job_id,
                    start_url=start_url,
                    domain_category=domain_category,
                    allowed_paths=allowed_paths,
                    max_pages=min(max_pages, 15),
                )
            ),
            daemon=True,
        )
        t.start()

    return job_id
