import re
import os
from pathlib import Path
import httpx

FONTS_DIR = Path("frontend/fonts")
FONTS_DIR.mkdir(parents=True, exist_ok=True)

URL = "https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:ital,wght@0,400;0,700;1,400;1,700&family=Noto+Sans+Devanagari:wght@400;600&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,600&display=swap"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

resp = httpx.get(URL, headers=headers)
css_content = resp.text

# Extract all font URLs and download them
pattern = r"url\((https://fonts\.gstatic\.com/[^)]+)\)"
matches = re.findall(pattern, css_content)

url_to_local = {}
for i, font_url in enumerate(set(matches)):
    filename = f"font_{i}_{Path(font_url).name}"
    local_path = FONTS_DIR / filename
    if not local_path.exists():
        print(f"Downloading {filename}...")
        f_resp = httpx.get(font_url, headers=headers)
        with open(local_path, "wb") as f:
            f.write(f_resp.content)
    url_to_local[font_url] = f"/static/fonts/{filename}"

local_css = css_content
for remote_url, local_rel in url_to_local.items():
    local_css = local_css.replace(remote_url, local_rel)

with open(FONTS_DIR / "fonts.css", "w", encoding="utf-8") as f:
    f.write(local_css)

print(f"Successfully downloaded {len(url_to_local)} fonts and wrote frontend/fonts/fonts.css")
