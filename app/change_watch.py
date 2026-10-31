import os
import hashlib
import difflib
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from app.database import get_db_connection, row_to_dict
from app.fetch import fetch_url


def calculate_content_hash(text: str) -> str:
    """Calculates deterministic SHA-256 hash of text content."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


async def recheck_source(source_id: str, simulated_new_text: Optional[str] = None) -> Dict[str, Any]:
    """
    Re-checks a source against live URL or updated content.
    Compares content hashes and generates a unified diff if changes are detected.
    Updates the database with the new content, hash, and timestamp.
    """
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
    is_registry = False
    if not row:
        row = conn.execute("SELECT * FROM registry_sources WHERE id = ?", (source_id,)).fetchone()
        if not row:
            conn.close()
            raise ValueError(f"Source with id '{source_id}' not found.")
        is_registry = True

    src = row_to_dict(row)
    if is_registry:
        old_text = src.get("notes") or src.get("name") or ""
        old_hash = calculate_content_hash(old_text)
        url = src.get("base_url") or ""
        src["title"] = src.get("name")
        src["url"] = url
    else:
        old_text = src.get("text") or ""
        old_hash = src.get("content_hash") or calculate_content_hash(old_text)
        url = src.get("url") or ""

    now_iso = datetime.now(timezone.utc).isoformat()

    if simulated_new_text is not None:
        fresh_text = simulated_new_text
    elif (url.startswith("http://") or url.startswith("https://")) and os.environ.get("FORCE_MOCK") != "true":
        try:
            fetch_res = await fetch_url(url)
            if fetch_res.get("fetch_status") == "success":
                fresh_text = fetch_res.get("text") or ""
            else:
                conn.close()
                return {
                    "source_id": source_id,
                    "title": src.get("title"),
                    "url": url,
                    "changed": False,
                    "error": f"Failed to fetch: {fetch_res.get('error_message')}",
                    "old_hash": old_hash,
                    "new_hash": old_hash,
                    "last_checked_at": now_iso,
                    "note": "any text change counts, including small page edits",
                    "summary": f"Re-fetch failed: {fetch_res.get('error_message')} (any text change counts, including small page edits)"
                }
        except Exception as e:
            conn.close()
            return {
                "source_id": source_id,
                "title": src.get("title"),
                "url": url,
                "changed": False,
                "error": str(e),
                "old_hash": old_hash,
                "new_hash": old_hash,
                "last_checked_at": now_iso,
                "note": "any text change counts, including small page edits",
                "summary": f"Re-fetch error: {e} (any text change counts, including small page edits)"
            }
    else:
        # Sample, pasted, or mock test source without external live network call
        fresh_text = old_text

    new_hash = calculate_content_hash(fresh_text)
    changed = (new_hash != old_hash)

    diff_lines = []
    added_count = 0
    removed_count = 0

    if changed:
        old_lines = old_text.splitlines()
        new_lines = fresh_text.splitlines()
        diff = list(difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"previous ({old_hash[:8]})",
            tofile=f"current ({new_hash[:8]})",
            lineterm=""
        ))
        diff_lines = diff
        for line in diff:
            if line.startswith("+") and not line.startswith("+++"):
                added_count += 1
            elif line.startswith("-") and not line.startswith("---"):
                removed_count += 1

        summary = f"⚠️ Content modified: +{added_count} lines, -{removed_count} lines. (any text change counts, including small page edits)"

        # Update source in SQLite
        if is_registry:
            conn.execute("""
                UPDATE registry_sources
                SET last_checked = ?
                WHERE id = ?
            """, (now_iso, source_id))
        else:
            conn.execute("""
                UPDATE sources
                SET text = ?, content_hash = ?, last_checked_at = ?
                WHERE id = ?
            """, (fresh_text, new_hash, now_iso, source_id))
    else:
        summary = "✓ Content unchanged. Hash verified. (any text change counts, including small page edits)"
        if is_registry:
            conn.execute("""
                UPDATE registry_sources
                SET last_checked = ?
                WHERE id = ?
            """, (now_iso, source_id))
        else:
            conn.execute("""
                UPDATE sources
                SET last_checked_at = ?
                WHERE id = ?
            """, (now_iso, source_id))

    conn.commit()
    conn.close()

    return {
        "source_id": source_id,
        "title": src.get("title"),
        "url": url,
        "changed": changed,
        "old_hash": old_hash,
        "new_hash": new_hash,
        "last_checked_at": now_iso,
        "summary": summary,
        "note": "any text change counts, including small page edits",
        "diff": "\n".join(diff_lines) if diff_lines else None,
        "added_lines_count": added_count,
        "removed_lines_count": removed_count
    }


async def recheck_session_sources(session_id: str) -> Dict[str, Any]:
    """Re-checks all sources belonging to a session."""
    conn = get_db_connection()
    rows = conn.execute("SELECT id FROM sources WHERE session_id = ?", (session_id,)).fetchall()
    conn.close()

    results = []
    any_changed = False
    for r in rows:
        res = await recheck_source(r["id"])
        if res.get("changed"):
            any_changed = True
        results.append(res)

    return {
        "session_id": session_id,
        "total_sources_checked": len(results),
        "any_changed": any_changed,
        "results": results
    }
