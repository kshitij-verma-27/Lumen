import asyncio
import json
import base64
import os
import sys
import subprocess
import time
import urllib.request
from pathlib import Path
import websockets

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BASE_URL = "http://127.0.0.1:8000"
SCREENS_DIR = Path("docs/screens")
SCREENS_DIR.mkdir(parents=True, exist_ok=True)


class CDPBrowserSession:
    def __init__(self, page_ws_url):
        self.page_ws_url = page_ws_url
        self.ws = None
        self.futures = {}
        self.id_counter = 0
        self.console_logs = []
        self.console_errors = []
        self.listen_task = None

    async def connect(self):
        self.ws = await websockets.connect(self.page_ws_url, max_size=50 * 1024 * 1024)
        self.listen_task = asyncio.create_task(self._listen_loop())
        await self.send("Page.enable")
        await self.send("Runtime.enable")
        await self.send("DOM.enable")

    async def close(self):
        if self.listen_task:
            self.listen_task.cancel()
        if self.ws:
            await self.ws.close()

    async def _listen_loop(self):
        try:
            async for raw in self.ws:
                msg = json.loads(raw)
                if "id" in msg and msg["id"] in self.futures:
                    fut = self.futures.pop(msg["id"])
                    if not fut.done():
                        if "error" in msg:
                            fut.set_exception(Exception(msg["error"]))
                        else:
                            fut.set_result(msg.get("result", {}))
                elif "method" in msg:
                    m = msg["method"]
                    p = msg.get("params", {})
                    if m == "Runtime.consoleAPICalled":
                        ltype = p.get("type")
                        args = [str(a.get("value") or a.get("description") or "") for a in p.get("args", [])]
                        entry = f"[{ltype}] " + " ".join(args)
                        self.console_logs.append(entry)
                        if ltype in ("error", "assert"):
                            self.console_errors.append(entry)
                    elif m == "Runtime.exceptionThrown":
                        det = p.get("exceptionDetails", {})
                        err_text = det.get("text", "")
                        desc = det.get("exception", {}).get("description", "")
                        err = f"[EXCEPTION] {err_text}: {desc}"
                        self.console_errors.append(err)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            pass

    async def send(self, method, params=None):
        self.id_counter += 1
        mid = self.id_counter
        fut = asyncio.get_event_loop().create_future()
        self.futures[mid] = fut
        await self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        return await asyncio.wait_for(fut, timeout=15.0)

    async def set_viewport(self, width, height, mobile=False):
        await self.send("Emulation.setDeviceMetricsOverride", {
            "width": width,
            "height": height,
            "deviceScaleFactor": 2 if mobile else 1,
            "mobile": mobile
        })
        await asyncio.sleep(0.3)

    async def navigate(self, url):
        await self.send("Page.navigate", {"url": url})
        # Wait for page load and initial rendering
        await asyncio.sleep(1.5)

    async def eval_js(self, expr):
        res = await self.send("Runtime.evaluate", {
            "expression": expr,
            "returnByValue": True,
            "awaitPromise": True
        })
        return res.get("result", {}).get("value")

    async def capture_screenshot(self, filename: str):
        res = await self.send("Page.captureScreenshot", {"format": "png"})
        data = base64.b64decode(res.get("data", ""))
        target_path = SCREENS_DIR / filename
        target_path.write_bytes(data)
        return str(target_path)

    async def check_layout(self, page_name: str, width: int):
        scroll_w = await self.eval_js("document.documentElement.scrollWidth")
        inner_w = await self.eval_js("window.innerWidth")
        has_overflow = (scroll_w is not None and inner_w is not None and scroll_w > inner_w + 2)
        return {
            "page": page_name,
            "width": width,
            "innerWidth": inner_w,
            "scrollWidth": scroll_w,
            "has_overflow": has_overflow
        }


async def run_audit():
    print("==================================================")
    print("STARTING HEADLESS BROWSER AUDIT (STABILIZATION SPRINT ITEM C)")
    print("==================================================")

    # Launch Chrome headless
    proc = subprocess.Popen([
        CHROME_PATH,
        "--headless=new",
        "--remote-debugging-port=9222",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage"
    ])
    await asyncio.sleep(2)

    all_layout_results = []
    all_console_errors = []
    all_screenshots = []

    try:
        v = json.loads(urllib.request.urlopen("http://127.0.0.1:9222/json/version").read())
        browser_ws_url = v["webSocketDebuggerUrl"]

        async with websockets.connect(browser_ws_url, max_size=50 * 1024 * 1024) as b_ws:
            # Create a target page
            create_msg = {"id": 1, "method": "Target.createTarget", "params": {"url": "about:blank"}}
            await b_ws.send(json.dumps(create_msg))
            resp = json.loads(await b_ws.recv())
            target_id = resp["result"]["targetId"]

            tabs = json.loads(urllib.request.urlopen("http://127.0.0.1:9222/json").read())
            page_tab = [t for t in tabs if t["id"] == target_id][0]
            page_ws_url = page_tab["webSocketDebuggerUrl"]

            session = CDPBrowserSession(page_ws_url)
            await session.connect()

            viewports = [
                {"name": "360px", "width": 360, "height": 800, "mobile": True},
                {"name": "1440px", "width": 1440, "height": 900, "mobile": False}
            ]

            # Find valid entity ID and source ID from database
            conn_test = urllib.request.urlopen(f"{BASE_URL}/api/entities")
            ents_data = json.loads(conn_test.read().decode("utf-8"))
            first_entity = ents_data.get("entities", [{}])[0]
            entity_id = first_entity.get("id") or "ent_pmuspcentral_07f721e8e0"

            sources_test = urllib.request.urlopen(f"{BASE_URL}/api/registry")
            srcs_data = json.loads(sources_test.read().decode("utf-8"))
            first_src = srcs_data.get("seeds", [{}])[0]
            source_id = first_src.get("id") or "edu_nta"

            print(f"Target Entity for Audit: {entity_id}")
            print(f"Target Source for Audit: {source_id}\n")

            for vp in viewports:
                vp_name = vp["name"]
                w = vp["width"]
                h = vp["height"]
                mobile = vp["mobile"]
                print(f"\n--- AUDITING VIEWPORT: {vp_name} ({w}x{h}, mobile={mobile}) ---")

                await session.set_viewport(w, h, mobile=mobile)

                # 1. HOME SCREEN (Light & Dark Theme)
                print(f"[+] Navigating to Home ({vp_name})...")
                await session.navigate(f"{BASE_URL}/#/")
                await asyncio.sleep(1.0)
                
                # Check light theme
                await session.eval_js("setTheme('light')")
                await asyncio.sleep(0.4)
                sc_light = await session.capture_screenshot(f"home_{vp_name}_light.png")
                all_screenshots.append(sc_light)
                
                # Check dark theme
                await session.eval_js("setTheme('dark')")
                await asyncio.sleep(0.4)
                sc_dark = await session.capture_screenshot(f"home_{vp_name}_dark.png")
                all_screenshots.append(sc_dark)
                
                l_res = await session.check_layout(f"Home ({vp_name})", w)
                all_layout_results.append(l_res)

                # 2. PROFILE POPUP
                print(f"[+] Testing Profile Modal Popup ({vp_name})...")
                await session.eval_js("openProfileModal()")
                await asyncio.sleep(0.5)
                sc_profile = await session.capture_screenshot(f"profile_{vp_name}_dark.png")
                all_screenshots.append(sc_profile)
                l_res = await session.check_layout(f"Profile Modal ({vp_name})", w)
                all_layout_results.append(l_res)
                await session.eval_js("closeProfileModal()")
                await asyncio.sleep(0.3)

                # 3. CATEGORY VIEW
                print(f"[+] Navigating to Category View: education ({vp_name})...")
                await session.navigate(f"{BASE_URL}/#/category/education")
                await asyncio.sleep(1.0)
                sc_cat = await session.capture_screenshot(f"category_{vp_name}_dark.png")
                all_screenshots.append(sc_cat)
                l_res = await session.check_layout(f"Category ({vp_name})", w)
                all_layout_results.append(l_res)

                # 4. SEARCH VIEW
                print(f"[+] Testing Search View ({vp_name})...")
                await session.navigate(f"{BASE_URL}/#/search?q=scholarship")
                await asyncio.sleep(1.0)
                sc_search = await session.capture_screenshot(f"search_{vp_name}_dark.png")
                all_screenshots.append(sc_search)
                l_res = await session.check_layout(f"Search ({vp_name})", w)
                all_layout_results.append(l_res)

                # 5. ENTITY VIEW (Click every tab + redaction bar)
                print(f"[+] Navigating to Entity View: {entity_id} ({vp_name})...")
                await session.navigate(f"{BASE_URL}/#/entity/{entity_id}")
                await asyncio.sleep(1.2)
                
                # Click through tabs
                tabs_to_click = ["tab-btn-claims", "tab-btn-gaps", "tab-btn-matrix", "tab-btn-sources"]
                for t in tabs_to_click:
                    await session.eval_js(f"const el = document.getElementById('{t}'); if (el) el.click();")
                    await asyncio.sleep(0.3)

                # Click redaction bars to reveal
                await session.eval_js("""
                    const bars = document.querySelectorAll('.redaction-bar');
                    bars.forEach(b => b.classList.add('revealed'));
                """)
                await asyncio.sleep(0.4)
                sc_ent = await session.capture_screenshot(f"entity_{vp_name}_dark.png")
                all_screenshots.append(sc_ent)
                l_res = await session.check_layout(f"Entity ({vp_name})", w)
                all_layout_results.append(l_res)

                # 6. SOURCE VIEW
                print(f"[+] Navigating to Source View: {source_id} ({vp_name})...")
                await session.navigate(f"{BASE_URL}/#/source/{source_id}")
                await asyncio.sleep(1.2)
                sc_src = await session.capture_screenshot(f"source_{vp_name}_dark.png")
                all_screenshots.append(sc_src)
                l_res = await session.check_layout(f"Source ({vp_name})", w)
                all_layout_results.append(l_res)

                # 7. REGISTRY MANAGER (Add source & Paste text interactions)
                print(f"[+] Navigating to Registry Manager ({vp_name})...")
                await session.navigate(f"{BASE_URL}/#/registry")
                await asyncio.sleep(1.2)

                # Filter registry
                await session.eval_js("filterRegistryTable('reachable')")
                await asyncio.sleep(0.3)

                # Open Paste Modal
                await session.eval_js("openPasteModal()")
                await asyncio.sleep(0.4)
                sc_reg_paste = await session.capture_screenshot(f"registry_paste_modal_{vp_name}.png")
                all_screenshots.append(sc_reg_paste)
                await session.eval_js("closePasteModal()")
                await asyncio.sleep(0.3)

                sc_reg = await session.capture_screenshot(f"registry_{vp_name}_dark.png")
                all_screenshots.append(sc_reg)
                l_res = await session.check_layout(f"Registry ({vp_name})", w)
                all_layout_results.append(l_res)

                # 8. INVESTIGATE VIEW (Full Flow)
                print(f"[+] Navigating to Investigate ({vp_name})...")
                await session.navigate(f"{BASE_URL}/#/investigate")
                await asyncio.sleep(1.2)
                
                # Check one-click demo card click
                await session.eval_js("""
                    const sampleBtn = document.querySelector('.sample-pack-btn, #btn-run-sample-demo, [onclick*=\"runSamplePack\"]');
                    if (sampleBtn) sampleBtn.click();
                """)
                await asyncio.sleep(0.6)
                sc_inv = await session.capture_screenshot(f"investigation_{vp_name}_dark.png")
                all_screenshots.append(sc_inv)
                l_res = await session.check_layout(f"Investigate ({vp_name})", w)
                all_layout_results.append(l_res)

            # Collect errors
            all_console_errors = session.console_errors

            await session.close()

    finally:
        proc.terminate()

    # PRINT AUDIT REPORT
    print("\n" + "="*80)
    print("HEADLESS BROWSER AUDIT REPORT")
    print("="*80)

    print("\n1. LAYOUT BREAK / HORIZONTAL OVERFLOW ANALYSIS:")
    breaks_found = 0
    for lr in all_layout_results:
        status = "OK (No overflow)" if not lr["has_overflow"] else f"LAYOUT BREAK! (scrollWidth={lr['scrollWidth']} > innerWidth={lr['innerWidth']})"
        print(f"  {lr['page']:28s} -> {status}")
        if lr["has_overflow"]:
            breaks_found += 1

    print(f"\nTotal Layout Breaks Found: {breaks_found}")

    print("\n2. CONSOLE ERRORS & JAVASCRIPT EXCEPTIONS:")
    if not all_console_errors:
        print("  None! (Zero console errors or uncaught exceptions detected across all views)")
    else:
        for err in all_console_errors:
            print(f"  - {err}")
    print(f"Total Console Errors: {len(all_console_errors)}")

    print(f"\n3. SCREENSHOTS GENERATED ({len(all_screenshots)} files):")
    for s in all_screenshots:
        print(f"  - {s}")
    print("="*80)

    return {
        "layout_breaks": breaks_found,
        "console_errors": len(all_console_errors),
        "screenshots_count": len(all_screenshots)
    }

if __name__ == "__main__":
    asyncio.run(run_audit())
