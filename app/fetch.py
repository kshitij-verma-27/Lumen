import hashlib
import re
import urllib.parse
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
import httpx
import trafilatura
from bs4 import BeautifulSoup
from app.database import get_db_connection


def compute_content_hash(text: str) -> str:
    """Compute SHA-256 hash of cleaned text."""
    clean = re.sub(r'\s+', ' ', text).strip()
    return hashlib.sha256(clean.encode('utf-8')).hexdigest()


def extract_published_date(html: str, url: Optional[str] = None, headers: Optional[Dict[str, str]] = None) -> Tuple[Optional[str], str]:
    """
    Extract published date and record its origin:
    - 'meta_tag': from schema.org, OpenGraph, or HTML meta tags
    - 'url_regex': from year/month patterns in the URL
    - 'http_header': from Last-Modified HTTP response header
    - 'none': if no date found
    """
    if not html:
        return None, "none"

    soup = BeautifulSoup(html, "html.parser")

    # 1. Meta tag inspection
    meta_date_attrs = [
        ("meta", {"property": "article:published_time"}),
        ("meta", {"property": "og:published_time"}),
        ("meta", {"name": "publication_date"}),
        ("meta", {"name": "date"}),
        ("meta", {"name": "DC.date.issued"}),
        ("meta", {"itemprop": "datePublished"}),
        ("time", {"datetime": True}),
    ]

    for tag, attrs in meta_date_attrs:
        el = soup.find(tag, attrs)
        if el:
            val = el.get("content") or el.get("datetime")
            if val and len(val.strip()) >= 4:
                return val.strip()[:10], "meta_tag"

    # 2. URL regex pattern (e.g. /2025/10/12/ or /2025-08/)
    if url:
        url_match = re.search(r'/(20\d\d)[/-](\d{1,2})(?:[/-](\d{1,2}))?', url)
        if url_match:
            year = url_match.group(1)
            month = url_match.group(2).zfill(2)
            day = url_match.group(3).zfill(2) if url_match.group(3) else "01"
            return f"{year}-{month}-{day}", "url_regex"

    # 3. HTTP Header Last-Modified
    if headers and "last-modified" in headers:
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(headers["last-modified"])
            return dt.strftime("%Y-%m-%d"), "http_header"
        except Exception:
            pass

    return None, "none"


async def fetch_url(url: str, client: Optional[httpx.AsyncClient] = None) -> Dict[str, Any]:
    """
    Fetch URL using httpx and clean with Trafilatura.
    Checks SQLite cache table first.
    """
    conn = get_db_connection()
    cached = conn.execute(
        "SELECT payload FROM cache WHERE cache_key = ? AND cache_type = 'fetch'",
        (url,)
    ).fetchone()

    if cached:
        conn.close()
        import json
        payload = json.loads(cached["payload"])
        payload["fetch_status"] = "cached"
        return payload

    # 1. Validate URL scheme and format
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme or parsed.scheme not in ("http", "https") or not parsed.netloc:
        conn.close()
        return {
            "url": url,
            "title": None,
            "text": "",
            "content_hash": "",
            "published_date": None,
            "published_date_origin": "none",
            "fetch_status": "failed",
            "error_message": f"Invalid URL: '{url}' is not a valid HTTP or HTTPS address. Please check the URL syntax."
        }

    # 2. SSRF check against private/loopback/cloud-metadata IPs
    from app.ingest.ssrf import is_url_safe
    is_safe, ssrf_err = is_url_safe(url)
    if not is_safe:
        conn.close()
        return {
            "url": url,
            "title": None,
            "text": "",
            "content_hash": "",
            "published_date": None,
            "published_date_origin": "none",
            "fetch_status": "failed",
            "error_message": f"Security restriction: Access to private, local, or loopback network addresses is blocked ({ssrf_err})."
        }

    from app.ingest.politeness import USER_AGENT
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }

    try:
        close_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=15.0, follow_redirects=True)
            close_client = True

        response = await client.get(url, headers=headers)
        if close_client:
            await client.aclose()

        if response.status_code == 403:
            conn.close()
            return {
                "url": url,
                "title": None,
                "text": "",
                "content_hash": "",
                "published_date": None,
                "published_date_origin": "none",
                "fetch_status": "failed",
                "error_message": "Access forbidden: The remote server returned HTTP 403 to our automated request. Please use Paste Text to ingest this document directly."
            }
        elif response.status_code >= 400:
            conn.close()
            return {
                "url": url,
                "title": None,
                "text": "",
                "content_hash": "",
                "published_date": None,
                "published_date_origin": "none",
                "fetch_status": "failed",
                "error_message": f"HTTP error {response.status_code}: The remote server returned status {response.status_code}."
            }

        html_content = response.text
        from app.ingest.text_extractor import extract_clean_text, check_thin_page
        cleaned_text, title = extract_clean_text(html_content)

        # Check for JavaScript-only / thin page
        is_thin, thin_reason = check_thin_page(html_content, cleaned_text)
        if is_thin:
            header_dict = {k.lower(): v for k, v in response.headers.items()}
            pub_date, date_origin = extract_published_date(html_content, url, header_dict)
            content_hash = compute_content_hash(cleaned_text)
            conn.close()
            return {
                "url": url,
                "title": title or "JavaScript-Only Page",
                "text": cleaned_text,
                "content_hash": content_hash,
                "published_date": pub_date,
                "published_date_origin": date_origin,
                "fetch_status": "failed",
                "error_message": "JavaScript-only page: This page requires client-side JavaScript execution to render its full contents. Use the Paste Text action to ingest text directly."
            }

        # Published date and origin
        header_dict = {k.lower(): v for k, v in response.headers.items()}
        pub_date, date_origin = extract_published_date(html_content, url, header_dict)

        content_hash = compute_content_hash(cleaned_text)

        result = {
            "url": url,
            "title": title,
            "text": cleaned_text,
            "content_hash": content_hash,
            "published_date": pub_date,
            "published_date_origin": date_origin,
            "fetch_status": "success",
            "error_message": None
        }

        # Save to cache
        import json
        conn.execute(
            "INSERT OR REPLACE INTO cache (cache_key, cache_type, payload) VALUES (?, 'fetch', ?)",
            (url, json.dumps(result))
        )
        conn.commit()
        conn.close()

        return result

    except httpx.TimeoutException:
        conn.close()
        return {
            "url": url,
            "title": None,
            "text": "",
            "content_hash": "",
            "published_date": None,
            "published_date_origin": "none",
            "fetch_status": "failed",
            "error_message": "Request timed out: The remote server took longer than 15 seconds to respond. Please verify the URL or try again later."
        }
    except httpx.ConnectError:
        conn.close()
        return {
            "url": url,
            "title": None,
            "text": "",
            "content_hash": "",
            "published_date": None,
            "published_date_origin": "none",
            "fetch_status": "failed",
            "error_message": "Connection error: Could not connect to the remote host. The server may be offline or the domain may not exist."
        }
    except Exception as e:
        conn.close()
        return {
            "url": url,
            "title": None,
            "text": "",
            "content_hash": "",
            "published_date": None,
            "published_date_origin": "none",
            "fetch_status": "failed",
            "error_message": f"Unable to fetch page: {e}"
        }


def process_pasted_text(pasted_text: str, title: Optional[str] = None) -> Dict[str, Any]:
    """Process user-pasted text as a first-class source."""
    cleaned = re.sub(r'\r\n', '\n', pasted_text).strip()
    content_hash = compute_content_hash(cleaned)

    # Check for dates in pasted text (e.g. Date: 15-08-2025)
    date_match = re.search(r'(?:Date|Dated|Published|Circular No.*dated)\s*[:\-]?\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})', cleaned, re.IGNORECASE)
    pub_date = date_match.group(1) if date_match else None
    origin = "meta_tag" if pub_date else "none"

    if not title:
        first_line = cleaned.split("\n")[0][:80]
        title = first_line if first_line else "Pasted Source Document"

    pseudo_url = f"pasted://{content_hash[:10]}"

    return {
        "url": pseudo_url,
        "title": title,
        "text": cleaned,
        "content_hash": content_hash,
        "published_date": pub_date,
        "published_date_origin": origin,
        "fetch_status": "pasted",
        "error_message": None
    }
