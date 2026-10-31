import asyncio
from datetime import datetime
import hashlib
import io
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import bs4
import dateparser
import httpx
import trafilatura

from app.ingest.models import Document
from app.ingest.politeness import (
    USER_AGENT,
    global_rate_limiter,
    global_robots_cache,
)
from app.ingest.ssrf import is_url_safe

logger = logging.getLogger(__name__)

MAX_BODY_BYTES = 2 * 1024 * 1024  # 2MB max download
MAX_TEXT_CHARS = 500 * 1024       # 500KB max text length


def compute_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_date_from_html(soup: bs4.BeautifulSoup, raw_html: str) -> tuple[Optional[str], str]:
    """Extracts published date from meta tags, schema.org JSON-LD, or body text."""
    # 1. Meta tags
    meta_keys = [
        "article:published_time", "article:modified_time", "og:updated_time",
        "date", "dc.date", "dc.date.issued", "pubdate", "publishdate"
    ]
    for key in meta_keys:
        meta = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
        if meta and meta.get("content"):
            content = meta.get("content").strip()
            parsed = dateparser.parse(content)
            if parsed:
                return parsed.strftime("%Y-%m-%d"), "meta"

    # 2. JSON-LD
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, dict):
                date_str = data.get("datePublished") or data.get("dateModified")
                if date_str:
                    parsed = dateparser.parse(str(date_str))
                    if parsed:
                        return parsed.strftime("%Y-%m-%d"), "meta"
        except Exception:
            continue

    # 3. Regex on body text
    date_pattern = re.search(
        r"(?:updated|published|last revised|dated|as on|effective)[:\s]+([A-Za-z0-9,\s\-\/]{6,25})",
        raw_html[:15000],
        re.IGNORECASE
    )
    if date_pattern:
        parsed = dateparser.parse(date_pattern.group(1).strip())
        if parsed and 2000 <= parsed.year <= 2035:
            return parsed.strftime("%Y-%m-%d"), "body"

    return None, "none"


async def fetch_html_document(url: str, custom_title: Optional[str] = None) -> Document:
    """Fetch and normalize an HTML webpage into a Document."""
    # 1. SSRF check
    safe, reason = is_url_safe(url)
    if not safe:
        return Document(
            url=url,
            title=custom_title,
            status="blocked",
            error=f"SSRF guard: {reason}",
            fetched_at=datetime.utcnow().isoformat(),
        )

    # 2. Robots check
    allowed, delay, r_status = await global_robots_cache.can_fetch(url)
    if not allowed:
        return Document(
            url=url,
            title=custom_title,
            status="disallowed",
            error=f"Robots.txt disallows crawling for {url}",
            fetched_at=datetime.utcnow().isoformat(),
        )

    # 3. Rate limiter throttle
    await global_rate_limiter.throttle(url, required_delay=delay)

    # 4. Fetch content
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=15.0), verify=False, follow_redirects=True) as client:
            resp = await client.get(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
            )

            if resp.status_code in (401, 403):
                return Document(
                    url=url,
                    title=custom_title,
                    status="blocked",
                    error=f"HTTP {resp.status_code} Forbidden/Blocked",
                    fetched_at=datetime.utcnow().isoformat(),
                )
            if resp.status_code != 200:
                return Document(
                    url=url,
                    title=custom_title,
                    status="unreachable",
                    error=f"HTTP status {resp.status_code}",
                    fetched_at=datetime.utcnow().isoformat(),
                )

            raw_html = resp.text
            from app.ingest.text_extractor import extract_clean_text
            extracted_text, auto_title = extract_clean_text(raw_html, max_chars=MAX_TEXT_CHARS)
            title = custom_title or auto_title or url
            clean_text = extracted_text
            soup = bs4.BeautifulSoup(raw_html[:50000], "html.parser")
            pub_date, date_origin = extract_date_from_html(soup, raw_html)

            # Collect HTML anchors for deterministic link & contact extraction
            anchors = []
            for a in soup.find_all("a", href=True):
                href = a.get("href", "").strip()
                a_text = a.get_text(separator=" ", strip=True)
                if href and (a_text or href.startswith("mailto:") or href.startswith("tel:")):
                    anchors.append({"text": a_text, "href": href})

            return Document(
                url=str(resp.url),
                title=title,
                text=clean_text,
                published_date=pub_date,
                date_origin=date_origin,
                fetched_at=datetime.utcnow().isoformat(),
                content_hash=compute_hash(clean_text),
                status="ok",
                content_type=resp.headers.get("content-type", "text/html"),
                size_bytes=len(clean_text.encode("utf-8")),
                metadata={"anchors": anchors[:250]},
            )

    except httpx.TimeoutException:
        return Document(url=url, status="unreachable", error="Connection timeout (15s)", fetched_at=datetime.utcnow().isoformat())
    except Exception as e:
        logger.error(f"Failed to fetch HTML for {url}: {e}")
        return Document(url=url, status="error", error=str(e), fetched_at=datetime.utcnow().isoformat())


async def fetch_rss_atom_document(url: str, custom_title: Optional[str] = None) -> Document:
    """Fetch and parse an RSS or Atom feed into a normalized Document."""
    safe, reason = is_url_safe(url)
    if not safe:
        return Document(url=url, status="blocked", error=f"SSRF guard: {reason}")

    allowed, delay, _ = await global_robots_cache.can_fetch(url)
    if not allowed:
        return Document(url=url, status="disallowed", error="Robots.txt disallowed")

    await global_rate_limiter.throttle(url, required_delay=delay)

    try:
        async with httpx.AsyncClient(timeout=15.0, verify=False, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": USER_AGENT})
            if resp.status_code != 200:
                return Document(url=url, status="unreachable", error=f"HTTP {resp.status_code}")

            xml_content = resp.text
            root = ET.fromstring(xml_content)

            feed_title = custom_title or (root.findtext(".//title") or url)
            items = []
            latest_date = None

            # Handle both RSS <item> and Atom <entry>
            xml_items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry") or root.findall(".//entry")
            for item in xml_items[:50]:
                it_title = item.findtext("title") or item.findtext("{http://www.w3.org/2005/Atom}title") or ""
                it_desc = item.findtext("description") or item.findtext("{http://www.w3.org/2005/Atom}summary") or item.findtext("{http://www.w3.org/2005/Atom}content") or ""
                it_link = item.findtext("link") or ""
                it_date = item.findtext("pubDate") or item.findtext("{http://www.w3.org/2005/Atom}updated") or ""

                if it_date and not latest_date:
                    p = dateparser.parse(it_date)
                    if p:
                        latest_date = p.strftime("%Y-%m-%d")

                # Strip HTML from description if any
                clean_desc = bs4.BeautifulSoup(it_desc, "html.parser").get_text(separator=" ", strip=True)
                items.append(f"Title: {it_title.strip()}\nLink: {it_link.strip()}\nSummary: {clean_desc.strip()}")

            combined_text = f"Feed: {feed_title}\n\n" + "\n\n---\n\n".join(items)
            clean_text = combined_text[:MAX_TEXT_CHARS]

            return Document(
                url=str(resp.url),
                title=feed_title,
                text=clean_text,
                published_date=latest_date,
                date_origin="meta" if latest_date else "none",
                fetched_at=datetime.utcnow().isoformat(),
                content_hash=compute_hash(clean_text),
                status="ok",
                content_type="application/rss+xml",
                size_bytes=len(clean_text.encode("utf-8")),
                metadata={"item_count": len(items)},
            )
    except Exception as e:
        return Document(url=url, status="error", error=f"RSS parse failed: {e}", fetched_at=datetime.utcnow().isoformat())


async def fetch_sitemap_document(url: str, custom_title: Optional[str] = None) -> Document:
    """Fetch and parse a sitemap.xml into a Document."""
    safe, reason = is_url_safe(url)
    if not safe:
        return Document(url=url, status="blocked", error=f"SSRF guard: {reason}")

    allowed, delay, _ = await global_robots_cache.can_fetch(url)
    if not allowed:
        return Document(url=url, status="disallowed", error="Robots.txt disallowed")

    await global_rate_limiter.throttle(url, required_delay=delay)

    try:
        async with httpx.AsyncClient(timeout=15.0, verify=False, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": USER_AGENT})
            if resp.status_code != 200:
                return Document(url=url, status="unreachable", error=f"HTTP {resp.status_code}")

            root = ET.fromstring(resp.text)
            urls = []
            latest_date = None

            # Handle sitemap url elements
            for elem in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}url") or root.findall(".//url"):
                loc = elem.findtext("{http://www.sitemaps.org/schemas/sitemap/0.9}loc") or elem.findtext("loc") or ""
                lastmod = elem.findtext("{http://www.sitemaps.org/schemas/sitemap/0.9}lastmod") or elem.findtext("lastmod") or ""
                if lastmod and not latest_date:
                    p = dateparser.parse(lastmod)
                    if p:
                        latest_date = p.strftime("%Y-%m-%d")
                urls.append(f"URL: {loc.strip()} (lastmod: {lastmod.strip()})")

            combined_text = f"Sitemap: {url}\n\n" + "\n".join(urls[:200])
            clean_text = combined_text[:MAX_TEXT_CHARS]

            return Document(
                url=str(resp.url),
                title=custom_title or f"Sitemap for {urlparse(url).netloc}",
                text=clean_text,
                published_date=latest_date,
                date_origin="meta" if latest_date else "none",
                fetched_at=datetime.utcnow().isoformat(),
                content_hash=compute_hash(clean_text),
                status="ok",
                content_type="application/xml",
                size_bytes=len(clean_text.encode("utf-8")),
                metadata={"url_count": len(urls)},
            )
    except Exception as e:
        return Document(url=url, status="error", error=f"Sitemap parse failed: {e}", fetched_at=datetime.utcnow().isoformat())


async def fetch_pdf_document(url_or_path: str, raw_bytes: Optional[bytes] = None, custom_title: Optional[str] = None) -> Document:
    """Fetch and parse PDF text using pypdf into a Document."""
    pdf_bytes = raw_bytes
    if pdf_bytes is None:
        safe, reason = is_url_safe(url_or_path)
        if not safe:
            return Document(url=url_or_path, status="blocked", error=f"SSRF guard: {reason}")

        allowed, delay, _ = await global_robots_cache.can_fetch(url_or_path)
        if not allowed:
            return Document(url=url_or_path, status="disallowed", error="Robots.txt disallowed")

        await global_rate_limiter.throttle(url_or_path, required_delay=delay)

        try:
            async with httpx.AsyncClient(timeout=20.0, verify=False, follow_redirects=True) as client:
                resp = await client.get(url_or_path, headers={"User-Agent": USER_AGENT})
                if resp.status_code != 200:
                    return Document(url=url_or_path, status="unreachable", error=f"HTTP {resp.status_code}")
                pdf_bytes = resp.content
        except Exception as e:
            return Document(url=url_or_path, status="error", error=f"PDF fetch failed: {e}")

    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages_text = []
        for i, page in enumerate(reader.pages[:50]):
            txt = page.extract_text() or ""
            if txt.strip():
                pages_text.append(f"[Page {i+1}]\n{txt.strip()}")

        extracted = "\n\n".join(pages_text)[:MAX_TEXT_CHARS]
        title = custom_title or (reader.metadata.title if reader.metadata and reader.metadata.title else url_or_path)

        return Document(
            url=url_or_path,
            title=title or "PDF Document",
            text=extracted,
            published_date=None,
            date_origin="none",
            fetched_at=datetime.utcnow().isoformat(),
            content_hash=compute_hash(extracted),
            status="ok",
            content_type="application/pdf",
            size_bytes=len(extracted.encode("utf-8")),
            metadata={"total_pages": len(reader.pages)},
        )
    except Exception as e:
        return Document(url=url_or_path, status="error", error=f"PDF extract failed: {e}", fetched_at=datetime.utcnow().isoformat())


async def fetch_json_api_document(url: str, custom_title: Optional[str] = None) -> Document:
    """Fetch and flatten a JSON API response into a readable Document."""
    safe, reason = is_url_safe(url)
    if not safe:
        return Document(url=url, status="blocked", error=f"SSRF guard: {reason}")

    allowed, delay, _ = await global_robots_cache.can_fetch(url)
    if not allowed:
        return Document(url=url, status="disallowed", error="Robots.txt disallowed")

    await global_rate_limiter.throttle(url, required_delay=delay)

    try:
        async with httpx.AsyncClient(timeout=15.0, verify=False, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            if resp.status_code != 200:
                return Document(url=url, status="unreachable", error=f"HTTP {resp.status_code}")

            data = resp.json()
            formatted_text = json.dumps(data, indent=2, ensure_ascii=False)[:MAX_TEXT_CHARS]

            return Document(
                url=str(resp.url),
                title=custom_title or f"API Response from {urlparse(url).netloc}",
                text=formatted_text,
                published_date=datetime.utcnow().strftime("%Y-%m-%d"),
                date_origin="header",
                fetched_at=datetime.utcnow().isoformat(),
                content_hash=compute_hash(formatted_text),
                status="ok",
                content_type="application/json",
                size_bytes=len(formatted_text.encode("utf-8")),
            )
    except Exception as e:
        return Document(url=url, status="error", error=f"JSON API fetch failed: {e}", fetched_at=datetime.utcnow().isoformat())


def process_pasted_text(text: str, custom_url: str = "pasted://user", custom_title: str = "User Supplied Text") -> Document:
    """Creates a normalized Document from user-pasted text."""
    clean_text = (text or "").strip()[:MAX_TEXT_CHARS]
    # Check for date pattern in pasted text (supporting ordinal days e.g. 25th November 2025)
    date_match = re.search(r"\b(\d{1,2}(?:st|nd|rd|th)?[\s\-\/]+[A-Za-z0-9]{3,9}[\s\-\/]+\d{2,4})\b", clean_text)
    pub_date = None
    if date_match:
        p = dateparser.parse(date_match.group(1))
        if p and 2000 <= p.year <= 2035:
            pub_date = p.strftime("%Y-%m-%d")

    return Document(
        url=custom_url,
        title=custom_title,
        text=clean_text,
        published_date=pub_date,
        date_origin="body" if pub_date else "none",
        fetched_at=datetime.utcnow().isoformat(),
        content_hash=compute_hash(clean_text),
        status="ok",
        content_type="text/plain",
        size_bytes=len(clean_text.encode("utf-8")),
    )
