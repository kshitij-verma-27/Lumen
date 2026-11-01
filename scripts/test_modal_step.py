import sys
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BASE_URL = "http://127.0.0.1:8000"

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=CHROME_PATH, headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_init_script("localStorage.setItem('lumen_profile_dismissed', 'true'); localStorage.setItem('lumen_font_scale', '18');")
    page = ctx.new_page()
    page.goto(f"{BASE_URL}/#/", wait_until="networkidle")
    print("1. Page loaded")
    page.click("#btn-topbar-more")
    print("2. More menu display:", page.evaluate("() => document.getElementById('topbar-more-menu').style.display"))
    print("3. More a11y btn visible:", page.is_visible("#btn-more-accessibility"))
    page.click("#btn-more-accessibility")
    res = page.evaluate("""() => {
        const modal = document.getElementById('accessibility-modal');
        const box = modal.querySelector('.a11y-modal-box');
        const btn = document.getElementById('btn-a11y-font-increase');
        return {
            modalCS: { display: window.getComputedStyle(modal).display, position: window.getComputedStyle(modal).position, zIndex: window.getComputedStyle(modal).zIndex },
            boxCS: { display: window.getComputedStyle(box).display, width: box.offsetWidth, height: box.offsetHeight },
            btnCS: { display: window.getComputedStyle(btn).display, visibility: window.getComputedStyle(btn).visibility, offsetW: btn.offsetWidth, offsetH: btn.offsetHeight },
            modalHtml: modal.outerHTML.slice(0, 300)
        };
    }""")
    print("Computed styles:", res)
    browser.close()
