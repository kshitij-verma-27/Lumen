import asyncio
import logging
import os
import time
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
import httpx

logger = logging.getLogger(__name__)

contact_url = os.environ.get("CONTACT_URL", "").strip()
if contact_url:
    USER_AGENT = f"LumenResearchBot/1.0 (+{contact_url}; research-notebook)"
else:
    USER_AGENT = "LumenResearchBot/1.0 (research-notebook)"

DEFAULT_MIN_DELAY = 2.0  # Max 1 request per 2 seconds per host
ROBOTS_CACHE_TTL = 86400  # 24 hours


class HostRateLimiter:
    """Enforces per-host rate limiting (min 2.0s delay between requests to same host)."""

    def __init__(self, min_delay: float = DEFAULT_MIN_DELAY):
        self.min_delay = min_delay
        self._last_request: Dict[str, float] = {}
        self._locks: Dict[str, asyncio.Lock] = {}

    def _get_lock(self, host: str) -> asyncio.Lock:
        if host not in self._locks:
            self._locks[host] = asyncio.Lock()
        return self._locks[host]

    async def throttle(self, url: str, required_delay: Optional[float] = None) -> float:
        """Asynchronously delays if needed to respect rate limit for this host."""
        if os.environ.get("FORCE_MOCK", "").lower() == "true":
            return 0.0

        try:
            parsed = urlparse(url)
            host = (parsed.netloc or "unknown").lower().split(":")[0]
        except Exception:
            host = "unknown"

        delay_to_use = max(self.min_delay, required_delay or 0.0)
        lock = self._get_lock(host)

        async with lock:
            now = time.monotonic()
            last = self._last_request.get(host, 0.0)
            elapsed = now - last
            wait_time = delay_to_use - elapsed
            if wait_time > 0:
                logger.debug(f"Throttling request to {host} for {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
            self._last_request[host] = time.monotonic()
            return max(0.0, wait_time)


class RobotsCache:
    """Caches and evaluates robots.txt rules per host with TTL."""

    def __init__(self, user_agent: str = USER_AGENT, ttl: float = ROBOTS_CACHE_TTL):
        self.user_agent = user_agent
        self.ttl = ttl
        # host -> (parser, fetch_timestamp, crawl_delay)
        self._cache: Dict[str, Tuple[RobotFileParser, float, float]] = {}

    async def get_robots(self, url: str, client: Optional[httpx.AsyncClient] = None) -> Tuple[RobotFileParser, float]:
        """Retrieves or fetches RobotFileParser and crawl_delay for URL's host."""
        try:
            parsed = urlparse(url)
            scheme = parsed.scheme or "https"
            host = (parsed.netloc or "").lower()
            base_origin = f"{scheme}://{host}"
        except Exception:
            rf = RobotFileParser()
            rf.allow_all = True
            return rf, DEFAULT_MIN_DELAY

        now = time.time()
        if host in self._cache:
            rf, timestamp, delay = self._cache[host]
            if now - timestamp < self.ttl:
                return rf, delay

        # Mock mode fallback
        if os.environ.get("FORCE_MOCK", "").lower() == "true":
            rf = RobotFileParser()
            rf.allow_all = True
            self._cache[host] = (rf, now, DEFAULT_MIN_DELAY)
            return rf, DEFAULT_MIN_DELAY

        robots_url = f"{base_origin}/robots.txt"
        rf = RobotFileParser()
        delay = DEFAULT_MIN_DELAY

        try:
            close_client = False
            if client is None:
                client = httpx.AsyncClient(timeout=10.0, verify=False, follow_redirects=True)
                close_client = True

            try:
                resp = await client.get(robots_url, headers={"User-Agent": self.user_agent})
                if resp.status_code == 200:
                    rf.parse(resp.text.splitlines())
                    crawl_delay = rf.crawl_delay(self.user_agent) or rf.crawl_delay("*")
                    if crawl_delay:
                        delay = max(float(crawl_delay), DEFAULT_MIN_DELAY)
                elif resp.status_code in (401, 403):
                    # Host explicitly refuses crawling robots.txt
                    rf.disallow_all = True
                else:
                    rf.allow_all = True
            finally:
                if close_client:
                    await client.aclose()
        except Exception as e:
            logger.debug(f"Could not fetch robots.txt for {host}: {e}")
            rf.allow_all = True

        self._cache[host] = (rf, now, delay)
        return rf, delay

    async def can_fetch(self, url: str, client: Optional[httpx.AsyncClient] = None) -> Tuple[bool, float, str]:
        """
        Checks if the URL is allowed by robots.txt.
        Returns (is_allowed, crawl_delay, status_string).
        """
        if os.environ.get("FORCE_MOCK", "").lower() == "true":
            return True, DEFAULT_MIN_DELAY, "allowed"

        rf, delay = await self.get_robots(url, client=client)
        if getattr(rf, "disallow_all", False):
            return False, delay, "disallowed"
        if getattr(rf, "allow_all", False):
            return True, delay, "allowed"

        allowed = rf.can_fetch(self.user_agent, url) or rf.can_fetch("*", url)
        status = "allowed" if allowed else "disallowed"
        return allowed, delay, status


# Global singleton instances
global_rate_limiter = HostRateLimiter(min_delay=DEFAULT_MIN_DELAY)
global_robots_cache = RobotsCache(user_agent=USER_AGENT)
