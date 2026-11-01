import os
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
import time
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BASE_URL = "http://127.0.0.1:8000"

VIEWPORTS = [1440, 1280, 1024, 768, 360]
THEMES = ["light", "dark", "high-contrast"]

PAGES = [
    ("Home", "#/"),
    ("Explore", "#/category/education"),
    ("Registry", "#/registry"),
    ("Source", "#/source/edu_nirf"),
    ("Entity", "#/entity/ent_pmuspcentral_07f721e8e0"),
    ("Investigate", "#/investigate")
]

def run_audit():
    print("=" * 80)
    print("LUMEN EXHAUSTIVE UI AUDIT & VERIFICATION SUITE")
    print("=" * 80)

    audit_results = []
    failed_items = []

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME_PATH, headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        context.add_init_script("localStorage.setItem('lumen_profile_dismissed', 'true'); localStorage.setItem('lumen_theme', 'light');")
        page = context.new_page()

        # Step 1: Run 1-click investigation first so Investigate view has real data
        print("\n[Setup] Running 1-Click Investigation on Home View...")
        page.goto(f"{BASE_URL}/", wait_until="networkidle")
        time.sleep(1)

        # Trigger 1-click demo
        page.click("#btn-home-1click-demo")
        print("  Clicked #btn-home-1click-demo, waiting for results...")
        page.wait_for_selector(".assistant-summary-box", timeout=30000)
        time.sleep(1)
        print("  ✓ 1-Click demo investigation completed!")

        # Verify 1-click demo results: conflicts count and coverage
        summary_text = page.evaluate("() => document.querySelector('.assistant-summary-box')?.innerText || ''")
        print(f"  Summary Text: {summary_text}")
        conflicts_text = page.evaluate("() => document.querySelector('.result-collapsible:nth-of-type(2) summary')?.innerText || ''")
        print(f"  Disagreements Summary: {conflicts_text}")
        assert "disagreement" in summary_text.lower() or "disagreement" in conflicts_text.lower(), "Expected disagreements to be reported in 1-click demo!"

        # Step 2: Check Fonts & Plain Digits
        print("\n[Check 1] Font Stack & Digit Rendering...")
        font_info = page.evaluate("""() => {
            const bodyCS = window.getComputedStyle(document.body);
            const headingCS = window.getComputedStyle(document.querySelector('h1') || document.body);
            return {
                bodyFont: bodyCS.fontFamily,
                headingFont: headingCS.fontFamily,
                fontSize: bodyCS.fontSize
            };
        }""")
        print(f"  Body Font Stack: {font_info['bodyFont']}")
        print(f"  Heading Font: {font_info['headingFont']}")
        assert "Noto Sans" in font_info["bodyFont"], "Noto Sans must be first in body font stack"
        assert "Atkinson" not in font_info["bodyFont"], "Atkinson must be removed from body font stack"
        print("  ✓ Plain zero font stack verified (Noto Sans first, no Atkinson)")

        # Step 3: Check Mobile Controls at Desktop (>= 768px) and Mobile (< 768px)
        print("\n[Check 2] Mobile Drawer Controls Visibility Threshold...")
        for w in [1440, 1280, 1024, 768]:
            page.set_viewport_size({"width": w, "height": 900})
            time.sleep(0.2)
            controls_vis = page.evaluate("""() => {
                const openBtn = document.getElementById('btn-sidebar-open');
                const closeBtn = document.getElementById('btn-sidebar-close');
                const openCS = openBtn ? window.getComputedStyle(openBtn) : null;
                const closeCS = closeBtn ? window.getComputedStyle(closeBtn) : null;
                return {
                    openDisplay: openCS ? openCS.display : 'none',
                    closeDisplay: closeCS ? closeCS.display : 'none'
                };
            }""")
            print(f"  Width {w}px: Menu button={controls_vis['openDisplay']}, Close button={controls_vis['closeDisplay']}")
            assert controls_vis["openDisplay"] == "none", f"Menu button visible at {w}px!"
            assert controls_vis["closeDisplay"] == "none", f"Close button visible at {w}px!"
        print("  ✓ Desktop >= 768px: Mobile controls strictly hidden")

        # Mobile check at 360px
        page.set_viewport_size({"width": 360, "height": 800})
        time.sleep(0.2)
        m_vis = page.evaluate("""() => {
            const openBtn = document.getElementById('btn-sidebar-open');
            return window.getComputedStyle(openBtn).display;
        }""")
        print(f"  Width 360px: Menu button={m_vis}")
        assert m_vis != "none", "Menu button should be visible on mobile (360px)"
        print("  ✓ Mobile 360px: Menu button visible")

        # Step 4: Sidebar Nav & History Audit
        print("\n[Check 3] Sidebar Nav & History Audit...")
        page.set_viewport_size({"width": 1440, "height": 900})
        time.sleep(0.2)
        nav_info = page.evaluate("""() => {
            const exploreBtn = document.getElementById('btn-sidebar-domains');
            const items = Array.from(document.querySelectorAll('.sidebar-link-btn, .sidebar-action-btn'));
            const aligns = items.map(el => window.getComputedStyle(el).justifyContent);
            const text = exploreBtn ? exploreBtn.innerText.trim() : '';
            return {
                exploreText: text,
                alignments: aligns
            };
        }""")
        print(f"  Explore button label: '{nav_info['exploreText']}'")
        assert "Explore" in nav_info["exploreText"] and "domains" not in nav_info["exploreText"].lower(), "Explore button should be renamed to 'Explore'"
        for a in nav_info["alignments"]:
            assert a in ["flex-start", "start", "left"], f"Sidebar button not left-aligned: {a}"
        print("  ✓ Sidebar items left-aligned and 'Explore' renamed")

        # Step 5: Check Topbar & More Menu Dropdown
        print("\n[Check 4] Topbar More Menu Dropdown...")
        topbar_info = page.evaluate("""() => {
            const topbar = document.querySelector('.notion-topbar');
            const tbCS = window.getComputedStyle(topbar);
            const moreBtn = document.getElementById('btn-topbar-more');
            const menu = document.getElementById('topbar-more-menu');
            return {
                height: tbCS.height,
                flexWrap: tbCS.flexWrap,
                hasMoreBtn: moreBtn !== null,
                hasMenu: menu !== null
            };
        }""")
        print(f"  Topbar height={topbar_info['height']}, flexWrap={topbar_info['flexWrap']}")
        assert topbar_info["flexWrap"] == "nowrap", "Topbar must be a single non-wrapping flex row"
        assert topbar_info["hasMoreBtn"] and topbar_info["hasMenu"], "Topbar More menu dropdown must exist"
        print("  ✓ Topbar single non-wrapping row with More menu dropdown verified")

        # Step 6: Exhaustive Bounding Box & Overlap Audit across 5 viewports x 3 themes x 6 pages
        print("\n" + "=" * 80)
        print("EXHAUSTIVE OVERLAP & BOUNDING BOX AUDIT MATRIX")
        print("=" * 80)

        for page_name, hash_route in PAGES:
            print(f"\n>>> PAGE: {page_name} ({hash_route}) <<<")
            page.goto(f"{BASE_URL}/{hash_route}", wait_until="networkidle")
            time.sleep(0.5)

            for w in VIEWPORTS:
                page.set_viewport_size({"width": w, "height": 900 if w >= 768 else 800})
                time.sleep(0.2)

                for theme in THEMES:
                    page.evaluate(f"theme => document.documentElement.setAttribute('data-theme', theme)", theme)
                    time.sleep(0.1)

                    # Bounding box & overlap audit in browser DOM
                    audit_res = page.evaluate("""(args) => {
                        const { width, theme, pageName } = args;
                        const errors = [];

                        // 1. Horizontal scroll check
                        const scrollW = document.documentElement.scrollWidth;
                        const clientW = document.documentElement.clientWidth;
                        if (scrollW > clientW + 1) {
                            errors.push(`Horizontal scroll detected: scrollWidth ${scrollW}px > clientWidth ${clientW}px`);
                        }

                        // 2. Topbar clipping & overlap check
                        const topbar = document.querySelector('.notion-topbar');
                        if (topbar && window.getComputedStyle(topbar).display !== 'none') {
                            const tbRect = topbar.getBoundingClientRect();
                            if (tbRect.top < 0) {
                                errors.push(`Topbar clipped at top of viewport: top=${tbRect.top}`);
                            }
                            if (tbRect.right > width + 1) {
                                errors.push(`Topbar extends past right viewport edge: right=${tbRect.right} > width=${width}`);
                            }

                            // Sibling button overlap check inside topbar
                            const tbButtons = Array.from(topbar.querySelectorAll('button:not([style*="display: none"])'));
                            const visibleBtns = tbButtons.filter(b => b.offsetWidth > 0 && b.offsetHeight > 0);
                            for (let i = 0; i < visibleBtns.length; i++) {
                                const rA = visibleBtns[i].getBoundingClientRect();
                                for (let j = i + 1; j < visibleBtns.length; j++) {
                                    const rB = visibleBtns[j].getBoundingClientRect();
                                    const overlaps = !(rA.right <= rB.left + 1 || rA.left >= rB.right - 1 || rA.bottom <= rB.top + 1 || rA.top >= rB.bottom - 1);
                                    if (overlaps) {
                                        errors.push(`Topbar buttons overlap: '${visibleBtns[i].innerText.trim()}' and '${visibleBtns[j].innerText.trim()}'`);
                                    }
                                }
                            }
                        }

                        // 3. Sidebar header clipping check
                        const sbHeader = document.querySelector('.sidebar-header');
                        if (sbHeader && window.getComputedStyle(sbHeader).display !== 'none' && width >= 768) {
                            const sbRect = sbHeader.getBoundingClientRect();
                            const brand = sbHeader.querySelector('.brand-name');
                            if (brand) {
                                const brandRect = brand.getBoundingClientRect();
                                if (brandRect.bottom > sbRect.bottom) {
                                    errors.push(`Sidebar brand 'Lumen' clipped by header bottom`);
                                }
                            }
                        }

                        // 4. Contrast check in high-contrast mode
                        let hcContrast = null;
                        if (theme === 'high-contrast') {
                            const bodyColor = window.getComputedStyle(document.body).color;
                            const bodyBg = window.getComputedStyle(document.body).backgroundColor;
                            if (bodyBg !== 'rgb(0, 0, 0)' && bodyBg !== '#000000') {
                                errors.push(`High-contrast body background is not pure black: ${bodyBg}`);
                            }
                        }

                        // 5. Small text audit: check for text elements under 16px
                        const allTextNodes = Array.from(document.querySelectorAll('p, span, div, a, button, label, td, th, small, code, kbd, samp'));
                        let minFontSize = 999;
                        for (const el of allTextNodes) {
                            if (el.children.length === 0 && el.innerText && el.innerText.trim().length > 0 && el.offsetWidth > 0 && el.offsetHeight > 0) {
                                const fs = parseFloat(window.getComputedStyle(el).fontSize);
                                if (fs < minFontSize) minFontSize = fs;
                                if (fs < 15.9) {
                                    errors.push(`Small text detected under 16px on <${el.tagName.toLowerCase()} class="${el.className}">: ${fs}px ('${el.innerText.trim().slice(0, 30)}')`);
                                }
                            }
                        }

                        return {
                            pageName,
                            width,
                            theme,
                            scrollWidth: scrollW,
                            clientWidth: clientW,
                            minFontSize,
                            errors
                        };
                    }""", {"width": w, "theme": theme, "pageName": page_name})

                    status = "PASS" if len(audit_res["errors"]) == 0 else "FAIL"
                    print(f"  [{status}] Page={page_name:11} | Width={w:4}px | Theme={theme:13} | MinFont={audit_res['minFontSize']:.1f}px | Scroll={audit_res['scrollWidth']}/{audit_res['clientWidth']}")
                    if audit_res["errors"]:
                        for err in audit_res["errors"]:
                            print(f"       ERROR: {err}")
                            failed_items.append((page_name, w, theme, err))

                    audit_results.append(audit_res)

        # Print Summary
        print("\n" + "=" * 80)
        print(f"AUDIT COMPLETE: Total Runs = {len(audit_results)}, Failures = {len(failed_items)}")
        print("=" * 80)
        if failed_items:
            print(f"Failed Items ({len(failed_items)}):")
            for f in failed_items:
                print(f" - {f[0]} at {f[1]}px ({f[2]}): {f[3]}")
        else:
            print("ALL 90 COMBINATIONS PASSED PERFECTLY WITH ZERO OVERLAPS, ZERO CLIPPING, AND ZERO HORIZONTAL SCROLL!")

        browser.close()

    assert len(failed_items) == 0, f"Audit failed on {len(failed_items)} items"

if __name__ == "__main__":
    run_audit()
