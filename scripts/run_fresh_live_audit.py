import asyncio
from datetime import datetime
import json
import logging
import os
import sys
from pathlib import Path
from urllib.parse import urlparse
import yaml
import httpx
import bs4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingest.politeness import USER_AGENT, global_robots_cache, global_rate_limiter
from app.database import get_db_connection

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("live_audit")


async def run_audit():
    yaml_path = Path("data/registry.yaml")
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    seeds = data.get("sources", [])
    print(f"Loaded {len(seeds)} seeds from {yaml_path}")
    print(f"Fetcher User-Agent: {USER_AGENT}")

    results = []

    conn = get_db_connection()
    cursor = conn.cursor()

    for idx, s in enumerate(seeds, 1):
        s_id = s["id"]
        base_url = s["base_url"].rstrip("/")
        name = s["name"]
        cat = s["domain_category"]

        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        # 1. Robots.txt check
        try:
            allowed, delay, r_status = await global_robots_cache.can_fetch(base_url)
            robots_status = r_status if allowed else "disallowed"
        except Exception:
            robots_status = "unknown"
            delay = 2.0

        # 2. Rate limit
        await global_rate_limiter.throttle(base_url, required_delay=delay)

        # 3. Live HTTP request with HONEST User-Agent and NO browser spoofing
        final_url = base_url
        status_code = None
        reachability = "unknown"
        needs_js = False
        text_length = 0
        error = None

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml"
        }

        try:
            async with httpx.AsyncClient(timeout=12.0, verify=False, follow_redirects=True) as client:
                resp = await client.get(base_url, headers=headers)
                status_code = resp.status_code
                final_url = str(resp.url)

                if resp.status_code in (401, 403):
                    reachability = "blocked"
                    error = f"HTTP {resp.status_code} Forbidden (WAF/Anti-bot challenge)"
                    needs_js = False
                    text_length = len(resp.text)
                elif resp.status_code == 200:
                    raw_html = resp.text.lower()
                    soup = bs4.BeautifulSoup(resp.text[:50000], "html.parser")
                    text_content = soup.get_text(separator=" ", strip=True)
                    text_length = len(text_content)

                    # JS rendering detector: thin text (< 200 chars) or SPA mount markers
                    is_spa = any(marker in raw_html for marker in (
                        '<div id="root">', '<div id="app">', '<app-root>', 'react-root',
                        'ng-version', 'window.__initial_state__'
                    ))
                    if is_spa or text_length < 200:
                        reachability = "needs_js"
                        needs_js = True
                    else:
                        reachability = "reachable"
                        needs_js = False
                else:
                    reachability = "unreachable"
                    error = f"HTTP {resp.status_code}"
                    needs_js = False
                    text_length = len(resp.text)

        except httpx.TimeoutException:
            reachability = "unreachable"
            status_code = 0
            error = "Connection timeout (12s)"
        except Exception as e:
            reachability = "unreachable"
            status_code = 0
            error = str(e)

        res_item = {
            "id": s_id,
            "name": name,
            "category": cat,
            "timestamp": timestamp,
            "url": base_url,
            "status_code": status_code,
            "final_url": final_url,
            "text_length": text_length,
            "reachability": reachability,
            "needs_js": needs_js,
            "robots_status": robots_status,
            "error": error
        }
        results.append(res_item)

        # Update DB row
        cursor.execute("""
            UPDATE registry_sources
            SET reachability = ?,
                robots_status = ?,
                needs_js = ?,
                http_status = ?,
                final_url = ?,
                audit_mode = 'live',
                last_audited = ?,
                last_checked = ?
            WHERE id = ?;
        """, (
            reachability,
            robots_status,
            1 if needs_js else 0,
            status_code or 0,
            final_url,
            timestamp,
            timestamp,
            s_id
        ))
        conn.commit()

        print(f"[{idx:2d}/29] {s_id:15s} | status={status_code} | reach={reachability:11s} | needs_js={str(needs_js):5s} | len={text_length:6d} | final={final_url}")

    conn.close()

    # Save raw audit output to scratch/live_audit_raw.json
    out_path = Path("scratch/live_audit_raw.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"\nLive audit complete. Saved {len(results)} raw results to {out_path.resolve()}")


if __name__ == "__main__":
    asyncio.run(run_audit())
