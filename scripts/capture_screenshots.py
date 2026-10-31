import subprocess
import os
import sys
import time
from pathlib import Path

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BASE_URL = "http://127.0.0.1:8000"

OUT_DIR = Path("docs/screens")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 12 Screenshots: (View, Viewport, Theme, URL, Output File)
TASKS = [
    # 1. Home Screen
    {
        "name": "Home 1440px Light",
        "url": f"{BASE_URL}/?view=home&theme=light",
        "size": (1440, 900),
        "out": OUT_DIR / "home_1440px_light.png"
    },
    {
        "name": "Home 1440px Dark",
        "url": f"{BASE_URL}/?view=home&theme=dark",
        "size": (1440, 900),
        "out": OUT_DIR / "home_1440px_dark.png"
    },
    {
        "name": "Home 360px Light",
        "url": f"{BASE_URL}/?view=home&theme=light",
        "size": (360, 800),
        "out": OUT_DIR / "home_360px_light.png"
    },
    {
        "name": "Home 360px Dark",
        "url": f"{BASE_URL}/?view=home&theme=dark",
        "size": (360, 800),
        "out": OUT_DIR / "home_360px_dark.png"
    },

    # 2. Entity Page with Redaction Bars (PM-USP Scholarship has redactions for missing attributes)
    {
        "name": "Entity 1440px Light",
        "url": f"{BASE_URL}/?view=entity&id=ent_pmuspcentral_07f721e8e0&theme=light",
        "size": (1440, 900),
        "out": OUT_DIR / "entity_1440px_light.png"
    },
    {
        "name": "Entity 1440px Dark",
        "url": f"{BASE_URL}/?view=entity&id=ent_pmuspcentral_07f721e8e0&theme=dark",
        "size": (1440, 900),
        "out": OUT_DIR / "entity_1440px_dark.png"
    },
    {
        "name": "Entity 360px Light",
        "url": f"{BASE_URL}/?view=entity&id=ent_pmuspcentral_07f721e8e0&theme=light",
        "size": (360, 800),
        "out": OUT_DIR / "entity_360px_light.png"
    },
    {
        "name": "Entity 360px Dark",
        "url": f"{BASE_URL}/?view=entity&id=ent_pmuspcentral_07f721e8e0&theme=dark",
        "size": (360, 800),
        "out": OUT_DIR / "entity_360px_dark.png"
    },

    # 3. Investigation Results Page
    {
        "name": "Investigation 1440px Light",
        "url": f"{BASE_URL}/?view=investigate&theme=light",
        "size": (1440, 900),
        "out": OUT_DIR / "investigation_1440px_light.png"
    },
    {
        "name": "Investigation 1440px Dark",
        "url": f"{BASE_URL}/?view=investigate&theme=dark",
        "size": (1440, 900),
        "out": OUT_DIR / "investigation_1440px_dark.png"
    },
    {
        "name": "Investigation 360px Light",
        "url": f"{BASE_URL}/?view=investigate&theme=light",
        "size": (360, 800),
        "out": OUT_DIR / "investigation_360px_light.png"
    },
    {
        "name": "Investigation 360px Dark",
        "url": f"{BASE_URL}/?view=investigate&theme=dark",
        "size": (360, 800),
        "out": OUT_DIR / "investigation_360px_dark.png"
    },
    # 4. Registry Manager View
    {
        "name": "Registry 1440px Light",
        "url": f"{BASE_URL}/?view=registry&theme=light",
        "size": (1440, 900),
        "out": OUT_DIR / "registry_1440px_light.png"
    },
    {
        "name": "Registry 1440px Dark",
        "url": f"{BASE_URL}/?view=registry&theme=dark",
        "size": (1440, 900),
        "out": OUT_DIR / "registry_1440px_dark.png"
    },
    {
        "name": "Registry 360px Light",
        "url": f"{BASE_URL}/?view=registry&theme=light",
        "size": (360, 800),
        "out": OUT_DIR / "registry_360px_light.png"
    },
    {
        "name": "Registry 360px Dark",
        "url": f"{BASE_URL}/?view=registry&theme=dark",
        "size": (360, 800),
        "out": OUT_DIR / "registry_360px_dark.png"
    },

    # 5. Source Page View (Technical Audit & Extracted Claims)
    {
        "name": "Source 1440px Light",
        "url": f"{BASE_URL}/?view=source&id=edu_nta&theme=light",
        "size": (1440, 900),
        "out": OUT_DIR / "source_1440px_light.png"
    },
    {
        "name": "Source 1440px Dark",
        "url": f"{BASE_URL}/?view=source&id=edu_nta&theme=dark",
        "size": (1440, 900),
        "out": OUT_DIR / "source_1440px_dark.png"
    },
    {
        "name": "Source 360px Light",
        "url": f"{BASE_URL}/?view=source&id=edu_nta&theme=light",
        "size": (360, 800),
        "out": OUT_DIR / "source_360px_light.png"
    },
    {
        "name": "Source 360px Dark",
        "url": f"{BASE_URL}/?view=source&id=edu_nta&theme=dark",
        "size": (360, 800),
        "out": OUT_DIR / "source_360px_dark.png"
    },

    # 6. Profile Popup Modal (Local Only, Plain Language Note)
    {
        "name": "Profile 1440px Light",
        "url": f"{BASE_URL}/?view=home&theme=light&profile=open",
        "size": (1440, 900),
        "out": OUT_DIR / "profile_1440px_light.png"
    },
    {
        "name": "Profile 1440px Dark",
        "url": f"{BASE_URL}/?view=home&theme=dark&profile=open",
        "size": (1440, 900),
        "out": OUT_DIR / "profile_1440px_dark.png"
    },
    {
        "name": "Profile 360px Light",
        "url": f"{BASE_URL}/?view=home&theme=light&profile=open",
        "size": (360, 800),
        "out": OUT_DIR / "profile_360px_light.png"
    },
    {
        "name": "Profile 360px Dark",
        "url": f"{BASE_URL}/?view=home&theme=dark&profile=open",
        "size": (360, 800),
        "out": OUT_DIR / "profile_360px_dark.png"
    },
]


def capture():
    print(f"Capturing {len(TASKS)} screenshots to {OUT_DIR.resolve()}...")
    for idx, t in enumerate(TASKS, 1):
        w, h = t["size"]
        out_file = t["out"].resolve()
        args = [
            CHROME_PATH,
            "--headless=new",
            "--virtual-time-budget=2000",
            f"--window-size={w},{h}",
            f"--screenshot={out_file}",
            t["url"]
        ]
        print(f"[{idx}/{len(TASKS)}] Capturing {t['name']} ({w}x{h}) -> {t['out'].name}...")
        res = subprocess.run(args, capture_output=True, text=True)
        if out_file.exists() and out_file.stat().st_size > 0:
            print(f"  [OK] Saved {out_file.name} ({out_file.stat().st_size} bytes)")
        else:
            print(f"  [WARN] Failed or empty output for {t['name']}: {res.stderr}")


if __name__ == "__main__":
    capture()
