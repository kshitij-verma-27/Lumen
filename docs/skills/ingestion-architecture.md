# Ingestion Architecture Rules

## Politeness & Web Citizenship
- Per-host rate limit: Strict maximum of 1 request per 2 seconds per host (`time.monotonic()`).
- Crawl-delay: Obey `Crawl-delay` directives declared in `robots.txt`.
- Robots cache: In-memory/SQLite cache of `robots.txt` with 24-hour TTL.
- Honest User-Agent: `LumenResearchBot/1.0 (+https://github.com/kshitij-verma-27/Lumen; research-notebook)`.
- Blocked handling: If blocked by 403, 401, or CAPTCHA, record status `blocked` and fallback to manual paste.

## Connectors & Document Model
Adapters return a normalized `Document`:
- `url`: Canonical fetched URL.
- `title`: Extracted title or fallback.
- `text`: Clean text extract (max 500KB per document).
- `published_date`: ISO date or null.
- `date_origin`: Source of date (`meta`, `header`, `url`, `body`).
- `fetched_at`: ISO timestamp.
- `content_hash`: SHA-256 hash of extracted text.
- `status`: `ok`, `blocked`, `unreachable`, `error`.
- `error`: Error string if failed.

## Background Crawl Jobs
- Async job queue (`asyncio.Queue` + SQLite table `crawl_jobs`).
- Crawl depth: Hard limit of 2 levels within `allowed_paths`.
- Progress tracking: Emits `stage`, `processed_count`, `total_count`, and `status`.
- Timeouts: 10s connection timeout, 15s read timeout per HTTP request.
