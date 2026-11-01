import sys
sys.stdout.reconfigure(encoding="utf-8")
import os
import time
from playwright.sync_api import sync_playwright

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BASE_URL = "http://127.0.0.1:8000"
OUT_DIR = "docs/screens"
os.makedirs(OUT_DIR, exist_ok=True)

VIEWS = [
    ("home", "#/"),
    ("investigate", "#/"), # with demo run
    ("explore", "#/category/education"),
    ("registry", "#/registry"),
    ("source", "#/source/edu_nirf"),
    ("entity", "#/entity/ent_pmuspcentral_07f721e8e0"),
]

WIDTHS = [(1440, 900), (360, 800)]
THEMES = ["light", "dark", "high-contrast"]

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=CHROME_PATH, headless=True)
    
    for theme in THEMES:
        for w, h in WIDTHS:
            context = browser.new_context(viewport={"width": w, "height": h})
            context.add_init_script(f"localStorage.setItem('lumen_profile_dismissed', 'true'); localStorage.setItem('lumen_theme', '{theme}');")
            page = context.new_page()
            
            # Setup demo run
            page.goto(f"{BASE_URL}/#/", wait_until="networkidle")
            page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
            page.click("#btn-home-1click-demo")
            try:
                page.wait_for_selector(".assistant-summary-box", timeout=20000)
            except Exception:
                pass
            time.sleep(0.5)
            
            # 1. Investigate screen
            page.screenshot(path=f"{OUT_DIR}/investigate_{w}px_{theme}.png", full_page=False)
            print(f"Captured: investigate_{w}px_{theme}.png")
            
            # 2. Explore screen
            page.goto(f"{BASE_URL}/#/category/education", wait_until="networkidle")
            page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
            time.sleep(0.3)
            page.screenshot(path=f"{OUT_DIR}/explore_{w}px_{theme}.png", full_page=False)
            print(f"Captured: explore_{w}px_{theme}.png")
            
            # 3. Registry screen
            page.goto(f"{BASE_URL}/#/registry", wait_until="networkidle")
            page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
            time.sleep(0.3)
            page.screenshot(path=f"{OUT_DIR}/registry_{w}px_{theme}.png", full_page=False)
            print(f"Captured: registry_{w}px_{theme}.png")
            
            # 4. Source screen
            page.goto(f"{BASE_URL}/#/source/edu_nirf", wait_until="networkidle")
            page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
            time.sleep(0.3)
            page.screenshot(path=f"{OUT_DIR}/source_{w}px_{theme}.png", full_page=False)
            print(f"Captured: source_{w}px_{theme}.png")
            
            # 5. Entity screen
            page.goto(f"{BASE_URL}/#/entity/ent_pmuspcentral_07f721e8e0", wait_until="networkidle")
            page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
            time.sleep(0.3)
            page.screenshot(path=f"{OUT_DIR}/entity_{w}px_{theme}.png", full_page=False)
            print(f"Captured: entity_{w}px_{theme}.png")
            
            context.close()
            
    browser.close()
print("All screenshots successfully captured!")
