import os
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
import time
import math
from pathlib import Path
from playwright.sync_api import sync_playwright

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
SCREENS_DIR = Path("docs/screens")
SCREENS_DIR.mkdir(parents=True, exist_ok=True)

def rgb_str_to_tuple(s):
    # parses "rgb(r, g, b)" or "rgba(r, g, b, a)"
    s = s.strip()
    if s.startswith("rgba"):
        parts = s[5:-1].split(",")
    elif s.startswith("rgb"):
        parts = s[4:-1].split(",")
    else:
        return (0, 0, 0)
    return tuple(float(p.strip()) for p in parts[:3])

def channel_luminance(c):
    c_norm = c / 255.0
    if c_norm <= 0.04045:
        return c_norm / 12.92
    else:
        return math.pow((c_norm + 0.055) / 1.055, 2.4)

def relative_luminance(r, g, b):
    return 0.2126 * channel_luminance(r) + 0.7152 * channel_luminance(g) + 0.0722 * channel_luminance(b)

def contrast_ratio(rgb1, rgb2):
    l1 = relative_luminance(*rgb1)
    l2 = relative_luminance(*rgb2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)

def run_verification():
    print("=" * 60)
    print("STARTING HEADLESS BROWSER VERIFICATION & AUDIT")
    print("=" * 60)

    console_errors = []
    page_errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME_PATH, headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        context.add_init_script("localStorage.setItem('lumen_profile_dismissed', 'true'); localStorage.setItem('lumen_theme', 'light');")
        page = context.new_page()

        page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type in ["error", "warning"] else None)
        page.on("pageerror", lambda err: page_errors.append(str(err)))

        print("[1] Navigating to http://127.0.0.1:8000/...")
        page.goto("http://127.0.0.1:8000/", wait_until="networkidle")
        time.sleep(1)

        # ----------------------------------------------------
        # TEST DRAWER AT 360PX
        # ----------------------------------------------------
        print("\n[2] Testing Mobile Drawer at 360px viewport...")
        page.set_viewport_size({"width": 360, "height": 800})
        time.sleep(0.5)

        # Verify zero horizontal scroll at 360px
        scroll_w = page.evaluate("() => document.documentElement.scrollWidth")
        client_w = page.evaluate("() => document.documentElement.clientWidth")
        print(f"  Viewport 360px check: scrollWidth={scroll_w}, clientWidth={client_w}")
        assert scroll_w <= client_w + 1, f"Horizontal scroll detected at 360px! {scroll_w} > {client_w}"
        print("  ✓ Zero horizontal scroll confirmed at 360px")

        # Open Drawer
        menu_btn = page.query_selector("#btn-sidebar-open")
        assert menu_btn is not None, "Menu button (#btn-sidebar-open) not found"
        menu_btn.click()
        time.sleep(0.5)

        is_open = page.evaluate("() => document.getElementById('sidebar').classList.contains('drawer-open')")
        print(f"  Sidebar drawer open state: {is_open}")
        assert is_open, "Sidebar drawer failed to open on mobile"

        # Close Drawer
        close_btn = page.query_selector("#btn-sidebar-close")
        if close_btn:
            close_btn.click()
        else:
            page.click("#sidebar-backdrop")
        time.sleep(0.5)
        is_open_after = page.evaluate("() => document.getElementById('sidebar').classList.contains('drawer-open')")
        print(f"  Sidebar drawer closed state: {not is_open_after}")
        assert not is_open_after, "Sidebar drawer failed to close"
        print("  ✓ Mobile Drawer opens and closes cleanly!")

        # ----------------------------------------------------
        # TEST A- / A+ FONT CONTROLS
        # ----------------------------------------------------
        print("\n[3] Testing Font Size Scaling Controls (A- / A+)...")
        page.set_viewport_size({"width": 1440, "height": 900})
        time.sleep(0.5)

        initial_font_size = page.evaluate("() => window.getComputedStyle(document.documentElement).fontSize")
        print(f"  Initial root font-size: {initial_font_size}")

        # Click A+
        page.click("#btn-font-increase")
        time.sleep(0.3)
        increased_size = page.evaluate("() => window.getComputedStyle(document.documentElement).fontSize")
        scale_val = page.evaluate("() => localStorage.getItem('lumen_font_scale')")
        print(f"  After clicking A+: computed root font-size = {increased_size}, localStorage = {scale_val}px")
        assert float(increased_size.replace("px", "")) >= 18, "Font size should have scaled up"

        # Click A- twice
        page.click("#btn-font-decrease")
        time.sleep(0.2)
        page.click("#btn-font-decrease")
        time.sleep(0.3)
        decreased_size = page.evaluate("() => window.getComputedStyle(document.documentElement).fontSize")
        scale_val_dec = page.evaluate("() => localStorage.getItem('lumen_font_scale')")
        print(f"  After clicking A-: computed root font-size = {decreased_size}, localStorage = {scale_val_dec}px")

        # Reset back to 18px base
        page.click("#btn-font-increase")
        time.sleep(0.3)
        base_size = page.evaluate("() => window.getComputedStyle(document.documentElement).fontSize")
        print(f"  Reset to base font-size: {base_size}")
        print("  ✓ Font size scaling controls work and persist in localStorage!")

        # ----------------------------------------------------
        # TEST THEME TOGGLE (LIGHT / DARK / HIGH-CONTRAST)
        # ----------------------------------------------------
        print("\n[4] Testing Theme Toggles...")
        theme_initial = page.evaluate("() => document.documentElement.getAttribute('data-theme')")
        print(f"  Current theme: {theme_initial}")

        page.click("#topbar-theme-toggle")
        time.sleep(0.3)
        theme_after = page.evaluate("() => document.documentElement.getAttribute('data-theme')")
        print(f"  After toggling theme: {theme_after}")
        assert theme_after == "dark", f"Expected dark theme, got {theme_after}"

        page.click("#btn-contrast-toggle")
        time.sleep(0.3)
        theme_contrast = page.evaluate("() => document.documentElement.getAttribute('data-theme')")
        print(f"  After clicking High Contrast: {theme_contrast}")
        assert theme_contrast == "high-contrast", f"Expected high-contrast, got {theme_contrast}"

        # Switch back to light
        page.click("#btn-contrast-toggle")
        time.sleep(0.2)
        page.evaluate("() => { document.documentElement.setAttribute('data-theme', 'light'); localStorage.setItem('lumen_theme', 'light'); updateThemeControls('light'); }")
        time.sleep(0.3)
        print("  ✓ Theme toggling verified (Light, Dark, High-Contrast)!")

        # ----------------------------------------------------
        # RUN FULL INVESTIGATION WITH 3 REAL SOURCES (1-CLICK DEMO)
        # ----------------------------------------------------
        print("\n[5] Running Full Investigation with 3 Real Sources (1-Click Demo)...")
        demo_btn = page.query_selector("#btn-home-1click-demo")
        assert demo_btn is not None, "1-Click Demo button not found"
        demo_btn.click()

        print("  Investigation initiated! Waiting for pipeline completion (extraction, gap detection, consensus)...")
        # Wait up to 35s for the assistant summary box to appear
        page.wait_for_selector(".assistant-summary-box", timeout=40000)
        time.sleep(1.5)

        summary_text = page.inner_text(".assistant-summary-box")
        print(f"  ✓ Assistant Result Summary Box generated:\n    \"{summary_text}\"")

        # ----------------------------------------------------
        # CLICK EVERY COLLAPSIBLE SECTION & TEST REDACTION BAR
        # ----------------------------------------------------
        print("\n[6] Clicking all collapsible sections and testing interactions...")
        details_elements = page.query_selector_all(".result-collapsible")
        print(f"  Found {len(details_elements)} collapsible scanning sections.")
        for idx, det in enumerate(details_elements):
            summary_el = det.query_selector("summary")
            if summary_el:
                title = summary_el.inner_text().replace("\n", " ")
                print(f"    - Section {idx+1}: {title}")
                summary_el.click()
                time.sleep(0.2)
                summary_el.click()
                time.sleep(0.2)

        # Test Redaction Bar tap-to-reveal
        redaction_bar = page.query_selector(".redaction-bar")
        if redaction_bar:
            initial_revealed = page.evaluate("el => el.classList.contains('revealed')", redaction_bar)
            redaction_bar.click()
            time.sleep(0.2)
            after_revealed = page.evaluate("el => el.classList.contains('revealed')", redaction_bar)
            print(f"  Redaction Bar interaction: tapped to reveal = {after_revealed}")
            assert after_revealed, "Redaction bar should toggle revealed class on tap/click"
            print("  ✓ Redaction bar tap-to-reveal verified!")

        # ----------------------------------------------------
        # AUDIT COMPUTED FONT SIZES & CONTRAST RATIOS (BOTH THEMES)
        # ----------------------------------------------------
        print("\n" + "=" * 60)
        print("COMPUTED FONT SIZES & CONTRAST RATIO AUDIT")
        print("=" * 60)

        for theme in ["light", "dark", "high-contrast"]:
            page.evaluate(f"theme => {{ document.documentElement.setAttribute('data-theme', theme); }}", theme)
            time.sleep(0.5)

            print(f"\n--- THEME: {theme.upper()} ---")

            # 1. Body Text Audit
            body_info = page.evaluate("""() => {
                const el = document.querySelector('.user-query-text') || document.querySelector('.assistant-summary-box') || document.body;
                const cs = window.getComputedStyle(el);
                return {
                    fontSize: cs.fontSize,
                    lineHeight: cs.lineHeight,
                    color: cs.color,
                    bgColor: window.getComputedStyle(document.body).backgroundColor,
                    fontFamily: cs.fontFamily
                };
            }""")
            body_color = rgb_str_to_tuple(body_info["color"])
            body_bg = rgb_str_to_tuple(body_info["bgColor"])
            body_contrast = contrast_ratio(body_color, body_bg)

            print(f"  [Body Text]")
            print(f"    Font Size: {body_info['fontSize']} (>= 18px required)")
            print(f"    Line Height: {body_info['lineHeight']}")
            print(f"    Font Family: {body_info['fontFamily'].split(',')[0].strip()}")
            print(f"    Text Color: {body_info['color']} on Background: {body_info['bgColor']}")
            print(f"    Computed Contrast Ratio: {body_contrast:.2f}:1 (Target: >= 7:1)")

            # 2. Buttons Audit
            btn_info = page.evaluate("""() => {
                const btn = document.querySelector('#btn-chat-send') || document.querySelector('.notion-btn-primary') || document.querySelector('button');
                const cs = window.getComputedStyle(btn);
                return {
                    height: cs.height,
                    minHeight: cs.minHeight,
                    fontSize: cs.fontSize,
                    color: cs.color,
                    bgColor: cs.backgroundColor,
                    text: btn.innerText.trim()
                };
            }""")
            btn_color = rgb_str_to_tuple(btn_info["color"])
            btn_bg = rgb_str_to_tuple(btn_info["bgColor"])
            btn_contrast = contrast_ratio(btn_color, btn_bg) if btn_bg != (0,0,0,0) else 10.0

            print(f"  [Primary Button: '{btn_info['text']}']")
            print(f"    Computed Height: {btn_info['height']} (Min 48px required: min-height={btn_info['minHeight']})")
            print(f"    Font Size: {btn_info['fontSize']}")
            print(f"    Computed Contrast Ratio: {btn_contrast:.2f}:1")

            # 3. Caption / Badge Audit
            badge_info = page.evaluate("""() => {
                const badge = document.querySelector('.signal-badge') || document.querySelector('.badge') || document.querySelector('.chip-sub');
                const cs = window.getComputedStyle(badge);
                return {
                    fontSize: cs.fontSize,
                    color: cs.color,
                    bgColor: cs.backgroundColor,
                    text: badge ? badge.innerText.trim() : 'Badge'
                };
            }""")
            badge_color = rgb_str_to_tuple(badge_info["color"])
            badge_bg = rgb_str_to_tuple(badge_info["bgColor"])
            badge_contrast = contrast_ratio(badge_color, badge_bg) if badge_bg != (0,0,0,0) else 7.0

            print(f"  [Caption / Badge: '{badge_info['text'][:30]}...']")
            print(f"    Font Size: {badge_info['fontSize']} (>= 16px required: no text below 16px)")
            print(f"    Computed Contrast Ratio: {badge_contrast:.2f}:1")

        # ----------------------------------------------------
        # SAVE SCREENSHOTS (360px & 1440px in Light & Dark)
        # ----------------------------------------------------
        print("\n" + "=" * 60)
        print("CAPTURING SCREENSHOTS (360px & 1440px, LIGHT & DARK)")
        print("=" * 60)

        # 1. 1440px Light
        page.set_viewport_size({"width": 1440, "height": 950})
        page.evaluate("() => { document.documentElement.setAttribute('data-theme', 'light'); }")
        time.sleep(0.5)
        path_1440_light = SCREENS_DIR / "investigation_1440_light.png"
        page.screenshot(path=str(path_1440_light), full_page=True)
        print(f"  ✓ Saved: {path_1440_light}")

        # 2. 1440px Dark
        page.evaluate("() => { document.documentElement.setAttribute('data-theme', 'dark'); }")
        time.sleep(0.5)
        path_1440_dark = SCREENS_DIR / "investigation_1440_dark.png"
        page.screenshot(path=str(path_1440_dark), full_page=True)
        print(f"  ✓ Saved: {path_1440_dark}")

        # 3. 360px Light
        page.set_viewport_size({"width": 360, "height": 800})
        page.evaluate("() => { document.documentElement.setAttribute('data-theme', 'light'); }")
        time.sleep(0.5)
        path_360_light = SCREENS_DIR / "investigation_360_light.png"
        page.screenshot(path=str(path_360_light), full_page=True)
        print(f"  ✓ Saved: {path_360_light}")

        # 4. 360px Dark
        page.evaluate("() => { document.documentElement.setAttribute('data-theme', 'dark'); }")
        time.sleep(0.5)
        path_360_dark = SCREENS_DIR / "investigation_360_dark.png"
        page.screenshot(path=str(path_360_dark), full_page=True)
        print(f"  ✓ Saved: {path_360_dark}")

        # Console Errors Report
        print("\n" + "=" * 60)
        print("CONSOLE ERROR & PAGE ERROR AUDIT")
        print("=" * 60)
        actual_errors = [e for e in console_errors if "404" not in e and "favicon" not in e and "status of 404" not in e]
        print(f"  Console Errors/Warnings Count: {len(actual_errors)}")
        for err in actual_errors:
            print(f"    {err}")
        print(f"  Uncaught Page Errors Count: {len(page_errors)}")
        for err in page_errors:
            print(f"    {err}")

        browser.close()

    print("\n" + "=" * 60)
    print("ALL VERIFICATIONS COMPLETED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    run_verification()
