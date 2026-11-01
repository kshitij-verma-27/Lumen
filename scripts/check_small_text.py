import sys
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BASE_URL = "http://127.0.0.1:8000"

PAGES = [
    ("Home", "#/"),
    ("Explore", "#/category/education"),
    ("Registry", "#/registry"),
    ("Source", "#/source/edu_nirf"),
    ("Entity", "#/entity/ent_pmuspcentral_07f721e8e0"),
    ("Investigate", "#/investigate")
]

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=CHROME_PATH, headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    
    # Run 1-click demo first to generate full results
    page.goto(f"{BASE_URL}/#/", wait_until="networkidle")
    page.click("#btn-home-1click-demo")
    page.wait_for_selector(".assistant-summary-box", timeout=30000)
    
    for name, route in PAGES:
        page.goto(f"{BASE_URL}/{route}", wait_until="networkidle")
        under16 = page.evaluate("""() => {
            const elements = Array.from(document.querySelectorAll('*'));
            const res = [];
            for (const el of elements) {
                if (el.children.length === 0 && el.innerText && el.innerText.trim().length > 0 && el.offsetWidth > 0 && el.offsetHeight > 0) {
                    const fs = parseFloat(window.getComputedStyle(el).fontSize);
                    if (fs < 15.9) {
                        res.push({
                            tag: el.tagName,
                            className: String(el.className),
                            id: el.id,
                            fontSize: fs,
                            text: el.innerText.trim().slice(0, 40)
                        });
                    }
                }
            }
            return res;
        }""")
        print(f"\n--- {name} ({route}) : {len(under16)} elements under 16px ---")
        seen = set()
        for item in under16:
            key = (item["tag"], item["className"], item["fontSize"])
            if key not in seen:
                seen.add(key)
                print(f"  {item['tag']:6} | class={item['className']:35} | id={item['id']:15} | {item['fontSize']:.1f}px | '{item['text']}'")
    
    browser.close()
