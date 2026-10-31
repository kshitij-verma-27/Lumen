import bs4
import trafilatura
from typing import Optional, Tuple

# Single canonical thin page threshold:
# A page is thin if it has < 40 words or < 200 characters of readable text,
# or contains modern SPA root markers with < 300 characters of initial text.
MIN_TEXT_CHARS = 200
MIN_WORD_COUNT = 40
SPA_MARKERS = (
    '<div id="root">',
    '<div id="app">',
    '<app-root>',
    'react-root',
    'ng-version',
    'window.__initial_state__',
    'window.__NEXT_DATA__'
)


def extract_clean_text(html_content: str, max_chars: int = 500 * 1024) -> Tuple[str, Optional[str]]:
    """
    Single shared text extractor used by fetch, audit, crawler, and validation.
    Extracts readable article / document text using Trafilatura with recall favor,
    falling back gracefully to BeautifulSoup semantic text extraction.
    Returns (cleaned_text, title).
    """
    if not html_content:
        return "", None

    # 1. Title extraction
    soup = bs4.BeautifulSoup(html_content[:50000], "html.parser")
    title_el = soup.find("title") or soup.find("h1")
    title = title_el.get_text(strip=True) if title_el else None

    # 2. Trafilatura extraction
    cleaned_text = trafilatura.extract(
        html_content,
        include_comments=False,
        include_tables=True,
        include_links=True,
        favor_recall=True
    )

    # 3. Fallback to BeautifulSoup if Trafilatura extracted nothing or minimal text
    if not cleaned_text or len(cleaned_text.strip()) < 50:
        fallback_soup = bs4.BeautifulSoup(html_content, "html.parser")
        for s in fallback_soup(["script", "style", "nav", "footer", "header", "noscript"]):
            s.decompose()
        cleaned_text = fallback_soup.get_text(separator="\n", strip=True)

    cleaned_text = (cleaned_text or "").strip()[:max_chars]
    return cleaned_text, title


def check_thin_page(html_content: str, cleaned_text: str) -> Tuple[bool, Optional[str]]:
    """
    Single shared 'thin page' rule across audit, crawler, and validation.
    Returns (is_thin, reason).
    """
    text_clean = (cleaned_text or "").strip()
    char_count = len(text_clean)
    words = text_clean.split()
    word_count = len(words)

    if char_count < MIN_TEXT_CHARS or word_count < MIN_WORD_COUNT:
        return True, f"Thin content: document contains only {word_count} words ({char_count} chars < {MIN_TEXT_CHARS} chars minimum)"

    html_lower = html_content.lower()
    is_spa = any(marker.lower() in html_lower for marker in SPA_MARKERS)
    if is_spa and char_count < 300:
        return True, f"Thin SPA shell: initial HTML markup contains client-side application mount points and only {char_count} chars of text"

    return False, None
