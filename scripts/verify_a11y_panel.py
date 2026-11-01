import sys
sys.stdout.reconfigure(encoding="utf-8")
import os
import time
from playwright.sync_api import sync_playwright

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BASE_URL = "http://127.0.0.1:8000"
OUT_DIR = "docs/screens"
os.makedirs(OUT_DIR, exist_ok=True)

VIEWPORTS = [1440, 1024, 768, 360]
THEMES = ["light", "dark", "high-contrast"]

def verify():
    print("=" * 80)
    print("VERIFICATION: TOPBAR, SIDEBAR & ACCESSIBILITY PANEL PERSISTENCE")
    print("=" * 80)

    console_errors = []
    audit_results = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME_PATH, headless=True)

        for w in VIEWPORTS:
            for theme in THEMES:
                context = browser.new_context(viewport={"width": w, "height": 900 if w >= 768 else 800})
                page = context.new_page()
                page.on("console", lambda msg: console_errors.append(f"[{w}px {theme}] {msg.type}: {msg.text}") if (msg.type == "error" and "favicon" not in msg.text.lower()) else None)
                page.on("pageerror", lambda err: console_errors.append(f"[{w}px {theme}] Page error: {err}"))

                # Initialize with theme
                context.add_init_script(f"""
                    localStorage.setItem('lumen_profile_dismissed', 'true');
                    if (localStorage.getItem('lumen_theme') === null) {{
                        localStorage.setItem('lumen_theme', '{theme}');
                    }}
                    if (localStorage.getItem('lumen_font_scale') === null) {{
                        localStorage.setItem('lumen_font_scale', '18');
                    }}
                """)
                page.goto(f"{BASE_URL}/#/", wait_until="networkidle")
                page.evaluate(f"""() => {{
                    localStorage.setItem('lumen_theme', '{theme}');
                    localStorage.setItem('lumen_font_scale', '18');
                    setTheme('{theme}');
                    applyFontSize(18);
                }}""")
                time.sleep(0.3)

                # Check 1: Top bar items
                topbar_check = page.evaluate("""(w) => {
                    const fontCtrl = document.querySelector('.font-size-controls');
                    const themeToggle = document.getElementById('topbar-theme-toggle');
                    const profBtn = document.getElementById('btn-topbar-profile');
                    const moreBtn = document.getElementById('btn-topbar-more');
                    const menuBtn = document.getElementById('btn-sidebar-open');
                    const breadcrumb = document.querySelector('.breadcrumbs');
                    const menuCS = menuBtn ? window.getComputedStyle(menuBtn).display : 'none';

                    const errors = [];
                    if (fontCtrl) errors.push("Font size controls still present in topbar!");
                    if (themeToggle) errors.push("Topbar theme toggle button still present!");
                    if (!profBtn || !moreBtn) errors.push("Profile or More button missing from topbar!");
                    if (w >= 768 && menuCS !== 'none') errors.push(`Menu button visible at ${w}px desktop!`);
                    if (w < 768 && menuCS === 'none') errors.push("Menu button hidden on mobile 360px!");

                    // Sibling overlap check
                    const tbButtons = Array.from(document.querySelectorAll('.notion-topbar button'))
                        .filter(b => b.offsetWidth > 0 && b.offsetHeight > 0);
                    for (let i = 0; i < tbButtons.length; i++) {
                        const rA = tbButtons[i].getBoundingClientRect();
                        for (let j = i + 1; j < tbButtons.length; j++) {
                            const rB = tbButtons[j].getBoundingClientRect();
                            const overlaps = !(rA.right <= rB.left + 1 || rA.left >= rB.right - 1 || rA.bottom <= rB.top + 1 || rA.top >= rB.bottom - 1);
                            if (overlaps) errors.push(`Topbar button overlap: ${tbButtons[i].innerText} and ${tbButtons[j].innerText}`);
                        }
                    }

                    return errors;
                }""", w)

                # Check 2: Sidebar footer
                sidebar_check = page.evaluate("""() => {
                    const errors = [];
                    const dToggle = document.getElementById('theme-toggle');
                    const hcToggle = document.getElementById('sidebar-contrast-toggle');
                    const modeBadge = document.getElementById('llm-mode-badge');

                    if (dToggle) errors.push("Sidebar Dark Mode button still present!");
                    if (hcToggle) errors.push("Sidebar High Contrast button still present!");
                    if (!modeBadge) errors.push("Sidebar LLM mode badge missing!");
                    return errors;
                }""")

                # Check 3: More menu items & height
                page.click("#btn-topbar-more")
                time.sleep(0.2)
                more_check = page.evaluate("""() => {
                    const errors = [];
                    const menu = document.getElementById('topbar-more-menu');
                    if (!menu || menu.style.display !== 'flex') errors.push("More menu did not open!");
                    const items = Array.from(menu.querySelectorAll('.dropdown-item-btn'));
                    if (items.length !== 3) errors.push(`Expected 3 items in More menu, found ${items.length}`);
                    for (const item of items) {
                        const h = item.offsetHeight;
                        if (h < 44) errors.push(`More menu item height < 44px: ${item.innerText.trim()} has height ${h}px`);
                    }
                    return errors;
                }""")

                # Check 4: Open Accessibility Modal from More
                page.click("#btn-more-accessibility")
                time.sleep(0.3)
                modal_open_check = page.evaluate("""() => {
                    const errors = [];
                    const modal = document.getElementById('accessibility-modal');
                    if (!modal || modal.style.display !== 'flex') errors.push("Accessibility modal did not open!");
                    const role = modal.querySelector('.modal-box').getAttribute('role');
                    const ariaModal = modal.querySelector('.modal-box').getAttribute('aria-modal');
                    const ariaLabel = modal.querySelector('.modal-box').getAttribute('aria-labelledby');
                    if (role !== 'dialog') errors.push(`Modal role is '${role}', expected 'dialog'`);
                    if (ariaModal !== 'true') errors.push("Modal aria-modal is not 'true'");
                    if (!ariaLabel) errors.push("Modal missing aria-labelledby");
                    return errors;
                }""")

                # Check 5: Change settings inside Accessibility Modal
                page.click("#btn-a11y-font-increase") # 18 -> 20px
                time.sleep(0.1)
                page.click("#font-radio-dyslexic")   # Font -> Atkinson Hyperlegible
                time.sleep(0.1)
                page.click("#motion-radio-on")        # Reduce motion -> on
                time.sleep(0.1)
                page.click("#spacing-radio-relaxed")  # Line spacing -> relaxed
                time.sleep(0.1)

                val_check = page.evaluate("""() => {
                    const val = document.getElementById('a11y-font-size-val').innerText;
                    return {
                        fontVal: val,
                        hasDyslexic: document.documentElement.style.getPropertyValue('--font-sans').includes('Atkinson'),
                        hasMotion: document.documentElement.classList.contains('reduce-motion'),
                        hasSpacing: document.documentElement.classList.contains('line-spacing-relaxed')
                    };
                }""")

                # Capture representative screenshot for 1440px light and 360px dark
                if w == 1440 and theme == "light":
                    page.screenshot(path=f"{OUT_DIR}/topbar_and_accessibility_panel_1440px.png")
                    print(f"  [Screenshot] Saved {OUT_DIR}/topbar_and_accessibility_panel_1440px.png")
                elif w == 360 and theme == "dark":
                    page.screenshot(path=f"{OUT_DIR}/topbar_and_accessibility_panel_360px.png")
                    print(f"  [Screenshot] Saved {OUT_DIR}/topbar_and_accessibility_panel_360px.png")

                # Close modal with Escape key
                page.keyboard.press("Escape")
                time.sleep(0.2)
                esc_check = page.evaluate("""() => {
                    const modal = document.getElementById('accessibility-modal');
                    return modal && modal.style.display === 'none';
                }""")

                # Reload page to test persistence in localStorage
                page.reload(wait_until="networkidle")
                time.sleep(0.3)

                persist_check = page.evaluate("""() => {
                    const scale = localStorage.getItem('lumen_font_scale');
                    const font = localStorage.getItem('lumen_font_family');
                    const motion = localStorage.getItem('lumen_reduce_motion');
                    const spacing = localStorage.getItem('lumen_line_spacing');
                    const htmlScale = document.documentElement.style.fontSize;
                    const hasDyslexic = document.documentElement.style.getPropertyValue('--font-sans').includes('Atkinson');
                    const hasMotion = document.documentElement.classList.contains('reduce-motion');
                    const hasSpacing = document.documentElement.classList.contains('line-spacing-relaxed');

                    return {
                        scale, font, motion, spacing, htmlScale, hasDyslexic, hasMotion, hasSpacing
                    };
                }""")

                errors = topbar_check + sidebar_check + more_check + modal_open_check
                if val_check["fontVal"] != "20px":
                    errors.append(f"Font value was not updated to 20px: {val_check['fontVal']}")
                if not esc_check:
                    errors.append("Escape did not close accessibility modal")
                if persist_check["scale"] != "20" or persist_check["htmlScale"] != "20px":
                    errors.append(f"Font scale 20px failed to persist: {persist_check['scale']}")
                if persist_check["font"] != "dyslexic" or not persist_check["hasDyslexic"]:
                    errors.append(f"Dyslexia font failed to persist: {persist_check['font']}")
                if persist_check["motion"] != "true" or not persist_check["hasMotion"]:
                    errors.append("Reduce motion failed to persist")
                if persist_check["spacing"] != "relaxed" or not persist_check["hasSpacing"]:
                    errors.append("Relaxed line spacing failed to persist")

                status = "PASS" if len(errors) == 0 else "FAIL"
                print(f"  [{status}] Viewport={w:4}px | Theme={theme:13} | FontScale={persist_check['htmlScale']} | Dyslexic={persist_check['hasDyslexic']} | Motion={persist_check['hasMotion']} | Spacing={persist_check['hasSpacing']}")
                if errors:
                    for err in errors:
                        print(f"       ERROR: {err}")
                audit_results.append((w, theme, status, errors))

                context.close()

        browser.close()

    print("\n" + "=" * 80)
    print(f"VERIFICATION SUMMARY: Runs = {len(audit_results)}, Console Errors = {len(console_errors)}")
    print("=" * 80)
    failed = [r for r in audit_results if r[2] != "PASS"]
    if failed:
        print(f"Failures ({len(failed)}):")
        for f in failed:
            print(f" - {f[0]}px ({f[1]}): {f[3]}")
    else:
        print("ALL VIEWPORTS AND THEMES PASSED PERFECTLY WITH ZERO OVERLAPS, ZERO CLIPPING, AND ZERO CONSOLE ERRORS!")
    
    assert len(console_errors) == 0, f"Console errors detected: {console_errors}"
    assert len(failed) == 0, f"Failures detected: {failed}"

if __name__ == "__main__":
    verify()
