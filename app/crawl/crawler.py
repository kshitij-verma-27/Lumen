import asyncio
from datetime import datetime
import json
import logging
import os
import re
from typing import Any, Callable, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse
import bs4
import httpx

from app.database import get_db_connection
from app.ingest.connectors import fetch_html_document, compute_hash
from app.ingest.models import Document
from app.ingest.politeness import global_rate_limiter, global_robots_cache
from app.ingest.ssrf import is_url_safe

logger = logging.getLogger(__name__)

MAX_PAGES_PER_JOB = 15
MAX_DEPTH = 2


def update_job_status(
    job_id: str,
    status: str,
    progress_pct: float = 0.0,
    processed_count: int = 0,
    total_count: int = 0,
    error: Optional[str] = None,
):
    conn = get_db_connection()
    now_iso = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        UPDATE crawl_jobs SET
            status = ?,
            progress_pct = ?,
            processed_count = ?,
            total_count = ?,
            error = ?,
            updated_at = ?
        WHERE id = ?;
        """,
        (status, progress_pct, processed_count, total_count, error, now_iso, job_id),
    )
    conn.commit()
    conn.close()


def get_crawl_job(job_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM crawl_jobs WHERE id = ?;", (job_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return dict(row)


def is_path_allowed(path: str, allowed_paths: List[str]) -> bool:
    if not allowed_paths or "/" in allowed_paths:
        return True
    return any(path.startswith(prefix) for prefix in allowed_paths)


def extract_internal_links(base_url: str, html: str, allowed_paths: List[str]) -> List[str]:
    """Extracts same-origin links matching allowed paths up to max depth."""
    try:
        base_parsed = urlparse(base_url)
        base_netloc = base_parsed.netloc.lower()
        soup = bs4.BeautifulSoup(html[:100000], "html.parser")
        links: Set[str] = set()

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue
            abs_url = urljoin(base_url, href)
            p = urlparse(abs_url)

            # Same host check
            if p.netloc.lower() == base_netloc and p.scheme.lower() in ("http", "https"):
                clean_url = f"{p.scheme}://{p.netloc}{p.path}".rstrip("/")
                if clean_url and is_path_allowed(p.path or "/", allowed_paths):
                    links.add(clean_url)
        return list(links)
    except Exception as e:
        logger.warning(f"Error extracting links from {base_url}: {e}")
        return []


async def run_crawl_job(
    job_id: str,
    start_url: str,
    allowed_paths: Optional[List[str]] = None,
    max_pages: int = MAX_PAGES_PER_JOB,
    max_depth: int = MAX_DEPTH,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
) -> List[Document]:
    """
    Executes an on-demand, rate-limited crawl starting from start_url.
    Respects max 15 pages per job, max depth 2, and emits progress.
    """
    allowed_paths = allowed_paths or ["/"]
    update_job_status(job_id, status="running", progress_pct=5.0, processed_count=0, total_count=max_pages)

    visited: Set[str] = set()
    queue: List[tuple[str, int]] = [(start_url, 0)]
    documents: List[Document] = []

    # Mock mode fast path
    if os.environ.get("FORCE_MOCK", "").lower() == "true":
        doc = Document(
            url=start_url,
            title=f"Mock Crawled Page for {urlparse(start_url).netloc}",
            text=f"Official notification from {start_url}. Eligibility: Any graduate. Application deadline is 30th November 2026. Fee is Rs. 100. Apply online.",
            published_date="2026-03-01",
            date_origin="meta",
            fetched_at=datetime.utcnow().isoformat(),
            content_hash=compute_hash("Mock Crawled Page content"),
            status="ok",
            size_bytes=150,
        )
        documents.append(doc)
        update_job_status(job_id, status="completed", progress_pct=100.0, processed_count=1, total_count=1)
        return documents

    try:
        while queue and len(documents) < max_pages:
            current_url, depth = queue.pop(0)
            if current_url in visited:
                continue
            visited.add(current_url)

            # SSRF check
            safe, ssrf_err = is_url_safe(current_url)
            if not safe:
                logger.warning(f"Skipping unsafe URL {current_url}: {ssrf_err}")
                continue

            # Progress notification
            processed = len(documents) + 1
            pct = min(95.0, round((processed / max_pages) * 100, 1))
            update_job_status(job_id, status="running", progress_pct=pct, processed_count=processed, total_count=max_pages)
            if progress_callback:
                progress_callback(f"Reading source {processed} of {max_pages}", processed, max_pages)

            # Fetch normalized document
            doc = await fetch_html_document(current_url)
            if doc.status == "ok" and len(doc.text) > 100:
                documents.append(doc)

                # Extract child links if depth allows
                if depth < max_depth and len(documents) < max_pages:
                    child_links = extract_internal_links(current_url, doc.text, allowed_paths)
                    for cl in child_links:
                        if cl not in visited and len(queue) < (max_pages * 2):
                            queue.append((cl, depth + 1))

        update_job_status(
            job_id,
            status="completed",
            progress_pct=100.0,
            processed_count=len(documents),
            total_count=len(documents),
        )
        return documents

    except Exception as e:
        logger.error(f"Crawl job {job_id} failed: {e}")
        update_job_status(job_id, status="failed", progress_pct=100.0, error=str(e))
        return documents
