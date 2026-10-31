import asyncio
from datetime import datetime
import logging
import os
import socket
from typing import Any, Dict, List
from urllib.parse import urlparse
import httpx
import bs4

from app.ingest.politeness import USER_AGENT, global_robots_cache, global_rate_limiter
from app.registry import get_all_registry_sources, update_registry_source

logger = logging.getLogger(__name__)


def is_network_available() -> bool:
    """Verifies that an active external internet connection is present."""
    for host in ("1.1.1.1", "8.8.8.8"):
        try:
            s = socket.create_connection((host, 53), timeout=3.0)
            s.close()
            return True
        except OSError:
            continue
    return False


# Curated baseline for mock-mode testing
MOCK_SEED_STATUS = {
    # Education
    "edu_nirf": {"reachability": "reachable", "robots_status": "allowed", "needs_js": False, "status_code": 200, "final_url": "https://www.nirfindia.org"},
    "edu_nta": {"reachability": "reachable", "robots_status": "allowed", "needs_js": False, "status_code": 200, "final_url": "https://nta.ac.in"},
    "edu_swayam": {"reachability": "needs_js", "robots_status": "allowed", "needs_js": True, "status_code": 200, "final_url": "https://swayam.gov.in"},
    "edu_nptel": {"reachability": "needs_js", "robots_status": "allowed", "needs_js": True, "status_code": 200, "final_url": "https://nptel.ac.in"},
    "edu_ncert": {"reachability": "reachable", "robots_status": "allowed", "needs_js": False, "status_code": 200, "final_url": "https://ncert.nic.in"},
    "edu_aicte": {"reachability": "reachable", "robots_status": "allowed", "needs_js": False, "status_code": 200, "final_url": "https://www.aicte-india.org"},
    "edu_ugc": {"reachability": "reachable", "robots_status": "allowed", "needs_js": False, "status_code": 200, "final_url": "https://www.ugc.gov.in"},
    "edu_nsp": {"reachability": "reachable", "robots_status": "allowed", "needs_js": False, "status_code": 200, "final_url": "https://scholarships.gov.in"},
    "edu_sih": {"reachability": "reachable", "robots_status": "allowed", "needs_js": False, "status_code": 200, "final_url": "https://sih.gov.in"},
    "edu_diksha": {"reachability": "needs_js", "robots_status": "allowed", "needs_js": True, "status_code": 200, "final_url": "https://diksha.gov.in"},
    # Career
    "car_ncs": {"reachability": "reachable", "robots_status": "allowed", "needs_js": False, "status_code": 200, "final_url": "https://www.ncs.gov.in"},
    "car_skill_india": {"reachability": "needs_js", "robots_status": "allowed", "needs_js": True, "status_code": 200, "final_url": "https://www.skillindiadigital.gov.in"},
    "car_upsc": {"reachability": "reachable", "robots_status": "allowed", "needs_js": False, "status_code": 200, "final_url": "https://upsc.gov.in"},
    "car_ssc": {"reachability": "reachable", "robots_status": "allowed", "needs_js": False, "status_code": 200, "final_url": "https://ssc.gov.in"},
    # Public Services
    "pub_india_gov": {"reachability": "reachable", "robots_status": "allowed", "needs_js": False, "status_code": 200, "final_url": "https://www.india.gov.in"},
    "pub_mygov": {"reachability": "reachable", "robots_status": "allowed", "needs_js": False, "status_code": 200, "final_url": "https://www.mygov.in"},
    "pub_digilocker": {"reachability": "needs_js", "robots_status": "allowed", "needs_js": True, "status_code": 200, "final_url": "https://www.digilocker.gov.in"},
    "pub_umang": {"reachability": "needs_js", "robots_status": "allowed", "needs_js": True, "status_code": 200, "final_url": "https://web.umang.gov.in"},
    "pub_pmsuryaghar": {"reachability": "reachable", "robots_status": "allowed", "needs_js": False, "status_code": 200, "final_url": "https://pmsuryaghar.gov.in"},
    # Research
    "res_anrf": {"reachability": "reachable", "robots_status": "allowed", "needs_js": False, "status_code": 200, "final_url": "https://anrfonline.in"},
    "res_dst": {"reachability": "reachable", "robots_status": "allowed", "needs_js": False, "status_code": 200, "final_url": "https://dst.gov.in"},
    "res_csir_hrdg": {"reachability": "reachable", "robots_status": "allowed", "needs_js": False, "status_code": 200, "final_url": "https://csirhrdg.res.in"},
    "res_arxiv": {"reachability": "reachable", "robots_status": "allowed", "needs_js": False, "status_code": 200, "final_url": "https://arxiv.org"},
    "res_data_gov": {"reachability": "reachable", "robots_status": "allowed", "needs_js": False, "status_code": 200, "final_url": "https://data.gov.in"},
    # Business
    "biz_startup_india": {"reachability": "needs_js", "robots_status": "allowed", "needs_js": True, "status_code": 200, "final_url": "https://www.startupindia.gov.in"},
    "biz_udyam": {"reachability": "reachable", "robots_status": "allowed", "needs_js": False, "status_code": 200, "final_url": "https://udyamregistration.gov.in"},
    "biz_gst": {"reachability": "blocked", "robots_status": "disallowed", "needs_js": True, "status_code": 403, "final_url": "https://www.gst.gov.in"},
    "biz_mca": {"reachability": "blocked", "robots_status": "disallowed", "needs_js": True, "status_code": 403, "final_url": "https://www.mca.gov.in"},
    "biz_dpiit": {"reachability": "reachable", "robots_status": "allowed", "needs_js": False, "status_code": 200, "final_url": "https://dpiit.gov.in"},
}


async def audit_single_seed(source: Dict[str, Any], force_mock: bool = False) -> Dict[str, Any]:
    source_id = source["id"]
    base_url = source["base_url"]
    now_iso = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    # MOCK MODE BRANCH
    if force_mock:
        mock_data = MOCK_SEED_STATUS.get(source_id, {
            "reachability": "reachable",
            "robots_status": "allowed",
            "needs_js": False,
            "status_code": 200,
            "final_url": base_url,
        })
        reach = mock_data["reachability"]
        robots = mock_data["robots_status"]
        needs_js = mock_data["needs_js"]
        status_code = mock_data.get("status_code", 200)
        final_url = mock_data.get("final_url", base_url)

        update_registry_source(source_id, {
            "reachability": reach,
            "robots_status": robots,
            "needs_js": 1 if needs_js else 0,
            "http_status": status_code,
            "final_url": final_url,
            "audit_mode": "mock",
            "last_audited": now_iso,
            "last_checked": now_iso,
        })

        return {
            "id": source_id,
            "name": source["name"],
            "category": source.get("domain_category"),
            "url": base_url,
            "final_url": final_url,
            "status_code": status_code,
            "robots_status": robots,
            "reachability": reach,
            "needs_js": needs_js,
            "audit_mode": "mock",
            "error": "returned HTTP 403 to our automated request" if reach == "blocked" else None,
        }

    # LIVE MODE BRANCH: Check network availability first
    if not is_network_available():
        raise RuntimeError("Network is unavailable: no internet connectivity detected. Cannot run live seed audit.")

    # 1. Robots.txt check
    try:
        allowed, delay, r_status = await global_robots_cache.can_fetch(base_url)
        robots_status = r_status if allowed else "disallowed"
    except Exception:
        robots_status = "unknown"
        delay = 2.0

    # 2. Politeness rate limiting
    await global_rate_limiter.throttle(base_url, required_delay=delay)

    # 3. HTTP GET Request
    final_url = base_url
    status_code = None
    error = None
    needs_js = False

    try:
        async with httpx.AsyncClient(timeout=10.0, verify=False, follow_redirects=True) as client:
            resp = await client.get(base_url, headers={"User-Agent": USER_AGENT})
            status_code = resp.status_code
            final_url = str(resp.url)

            if resp.status_code in (401, 403):
                reachability = "blocked"
                error = f"HTTP {resp.status_code} (returned HTTP 403 to our automated request)"
                needs_js = False
            elif resp.status_code == 200:
                from app.ingest.text_extractor import extract_clean_text, check_thin_page
                cleaned_text, _ = extract_clean_text(resp.text)
                is_thin, thin_reason = check_thin_page(resp.text, cleaned_text)

                if is_thin:
                    reachability = "needs_js"
                    needs_js = True
                    error = thin_reason
                else:
                    reachability = "reachable"
                    needs_js = False
            else:
                reachability = "unreachable"
                error = f"HTTP {resp.status_code}"
                needs_js = False

    except httpx.TimeoutException:
        reachability = "unreachable"
        error = "Connection timed out (10s)"
    except Exception as e:
        reachability = "unreachable"
        error = str(e)

    update_registry_source(source_id, {
        "reachability": reachability,
        "robots_status": robots_status,
        "needs_js": 1 if needs_js else 0,
        "http_status": status_code or 0,
        "final_url": final_url,
        "audit_mode": "live",
        "last_audited": now_iso,
        "last_checked": now_iso,
    })

    return {
        "id": source_id,
        "name": source["name"],
        "category": source.get("domain_category"),
        "url": base_url,
        "final_url": final_url,
        "status_code": status_code,
        "robots_status": robots_status,
        "reachability": reachability,
        "needs_js": needs_js,
        "audit_mode": "live",
        "error": error,
    }


async def audit_all_seeds(force_mock: bool = False) -> List[Dict[str, Any]]:
    sources = get_all_registry_sources()
    # Filter to only the 29 seed sources
    seed_sources = [s for s in sources if s["id"].startswith(("edu_", "car_", "pub_", "res_", "biz_"))]
    results = []
    for s in seed_sources:
        res = await audit_single_seed(s, force_mock=force_mock)
        results.append(res)
    return results
