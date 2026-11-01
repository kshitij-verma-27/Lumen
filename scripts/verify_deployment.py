import os
import sys
import time
import subprocess
import json
import urllib.request
import urllib.error
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

def run_tests():
    print("=" * 80)
    print("DEPLOYMENT VERIFICATION SUITE: RENDER + VERCEL SPLIT")
    print("=" * 80)

    # -------------------------------------------------------------
    # TEST 1: Render Local Run (PORT=10000, empty isolated DB)
    # -------------------------------------------------------------
    print("\n--- TEST 1: RENDER DEPLOYMENT (PORT=10000, ISOLATED DB) ---")
    db_test_render = Path("test_render_port10000.db")
    if db_test_render.exists():
        try: os.remove(db_test_render)
        except: pass

    env_render = os.environ.copy()
    env_render["PORT"] = "10000"
    env_render["DARKSPOT_DB"] = "test_render_port10000.db"
    env_render["FORCE_MOCK"] = "true"
    env_render["TESTING"] = "true"

    proc_render = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10000"],
        env=env_render,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    time.sleep(3)

    try:
        # Check /api/health
        req = urllib.request.urlopen("http://127.0.0.1:10000/api/health")
        health = json.loads(req.read().decode())
        print(f"  [OK] /api/health responded: status={health.get('status')}, mode={health.get('mode')}")

        # Check bootstrap seeded entities in isolated DB
        req = urllib.request.urlopen("http://127.0.0.1:10000/api/entities?limit=6")
        ents = json.loads(req.read().decode())
        print(f"  [OK] Bootstrap populated {len(ents.get('entities', []))} entities on initial empty DB startup")

        # Check home HTML loads
        req = urllib.request.urlopen("http://127.0.0.1:10000/")
        html = req.read().decode()
        print(f"  [OK] Full app served at Render root URL (length: {len(html)} bytes)")

        # Check registry loads
        req = urllib.request.urlopen("http://127.0.0.1:10000/api/registry")
        reg = json.loads(req.read().decode())
        print(f"  [OK] Registry loaded {len(reg.get('sources', []))} sources")

        print("  [OK] Render single-service deployment verified!")
    finally:
        proc_render.terminate()
        proc_render.wait()
        if db_test_render.exists():
            try: os.remove(db_test_render)
            except: pass

    # -------------------------------------------------------------
    # TEST 2: Split Deployment (Backend :8001, Frontend static :5173)
    # -------------------------------------------------------------
    print("\n--- TEST 2: SPLIT DEPLOYMENT (BACKEND: 8001, VERCEL STATIC: 5173) ---")
    db_split = Path("test_split_backend.db")
    if db_split.exists():
        try: os.remove(db_split)
        except: pass

    # Set frontend config to point to backend 8001
    with open("frontend/config.js", "w", encoding="utf-8") as f:
        f.write('window.APP_CONFIG = { API_BASE: "http://127.0.0.1:8001" };\n')

    env_backend = os.environ.copy()
    env_backend["PORT"] = "8001"
    env_backend["DARKSPOT_DB"] = "test_split_backend.db"
    env_backend["ALLOWED_ORIGINS"] = "http://127.0.0.1:5173,http://localhost:5173"
    env_backend["FORCE_MOCK"] = "true"
    env_backend["TESTING"] = "true"

    proc_backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"],
        env=env_backend,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    proc_frontend = subprocess.Popen(
        [sys.executable, "-m", "http.server", "5173", "--directory", "frontend"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    time.sleep(3)

    from playwright.sync_api import sync_playwright

    console_errors = []
    failed_requests = []

    try:
        # Check CORS rejection from unauthorized origin
        print("  Checking CORS policy on backend port 8001...")
        req = urllib.request.Request(
            "http://127.0.0.1:8001/api/entities?limit=6",
            headers={"Origin": "http://unauthorized-evil-domain.com"}
        )
        try:
            resp = urllib.request.urlopen(req)
            allow_header = resp.headers.get("Access-Control-Allow-Origin")
            print(f"    CORS Response Header for unauthorized-evil-domain.com: '{allow_header}'")
            assert allow_header != "http://unauthorized-evil-domain.com" and allow_header != "*", "Unauthorized origin was NOT blocked by CORS!"
            print("    [OK] Unauthorized origin correctly blocked by CORS")
        except urllib.error.HTTPError as e:
            print(f"    [OK] Unauthorized origin rejected: {e.code}")

        # Check CORS acceptance from authorized origin
        req_auth = urllib.request.Request(
            "http://127.0.0.1:8001/api/entities?limit=6",
            headers={"Origin": "http://127.0.0.1:5173"}
        )
        resp_auth = urllib.request.urlopen(req_auth)
        allow_auth = resp_auth.headers.get("Access-Control-Allow-Origin")
        print(f"    CORS Response Header for authorized origin: '{allow_auth}'")
        assert allow_auth == "http://127.0.0.1:5173", "Authorized origin was not granted CORS!"
        print("    [OK] Authorized frontend origin correctly granted CORS")

        # Headless Browser Verification on Frontend Port 5173
        print("\n  Launching Headless Chrome on static frontend http://127.0.0.1:5173/#/ ...")
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=CHROME_PATH, headless=True)
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            ctx.add_init_script("localStorage.setItem('lumen_profile_dismissed', 'true'); localStorage.setItem('lumen_theme', 'light');")
            page = ctx.new_page()

            page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type == "error" and "favicon" not in msg.text.lower() else None)
            page.on("requestfailed", lambda req: failed_requests.append(f"Failed: {req.url} ({req.failure})") if "favicon" not in req.url else None)

            # 1. Home View
            page.goto("http://127.0.0.1:5173/#/", wait_until="networkidle")
            time.sleep(0.5)
            print("    [OK] Home page loaded from static Vercel-style server")

            # 2. 1-Click Demo
            print("    Running 1-click investigation on split deployment...")
            page.click("#btn-home-1click-demo")
            page.wait_for_selector(".assistant-summary-box", timeout=30000)
            time.sleep(1)
            print("    [OK] 1-Click investigation executed and results displayed")

            # 3. Registry View
            page.goto("http://127.0.0.1:5173/#/registry", wait_until="networkidle")
            time.sleep(0.5)
            reg_count = page.evaluate("() => document.querySelectorAll('#registry-table-body tr').length")
            print(f"    [OK] Registry view rendered with {reg_count} rows from backend API")

            # 4. Entity View
            page.goto("http://127.0.0.1:5173/#/entity/ent_pmuspcentral_07f721e8e0", wait_until="networkidle")
            time.sleep(0.5)
            ent_title = page.evaluate("() => document.getElementById('entity-name-text')?.innerText || ''")
            print(f"    [OK] Entity view loaded: '{ent_title}'")

            # 5. Accessibility Modal
            page.click("#btn-topbar-more")
            time.sleep(0.2)
            page.click("#btn-more-accessibility")
            time.sleep(0.2)
            a11y_vis = page.is_visible("#accessibility-modal")
            print(f"    [OK] Accessibility modal open={a11y_vis}")
            page.keyboard.press("Escape")

            # 6. Check Exports URLs
            export_urls = page.evaluate("""() => ({
                jsonUrl: apiUrl('/api/sessions/test/export/json'),
                htmlUrl: apiUrl('/api/sessions/test/export/html')
            })""")
            print(f"    [OK] Export JSON URL routes to backend: {export_urls['jsonUrl']}")
            print(f"    [OK] Export HTML URL routes to backend: {export_urls['htmlUrl']}")
            assert "http://127.0.0.1:8001" in export_urls["jsonUrl"], "Export JSON must use apiUrl!"
            assert "http://127.0.0.1:8001" in export_urls["htmlUrl"], "Export HTML must use apiUrl!"

            browser.close()

        print(f"\n  Split Deployment Frontend Results: Console Errors = {len(console_errors)}, Failed Requests = {len(failed_requests)}")
        if console_errors:
            print("    Console errors:", console_errors)
        if failed_requests:
            print("    Failed requests:", failed_requests)
        assert len(console_errors) == 0, f"Console errors: {console_errors}"
        assert len(failed_requests) == 0, f"Failed requests: {failed_requests}"
        print("  [OK] Split deployment (Vercel static + Render backend) verified successfully!")

    finally:
        proc_backend.terminate()
        proc_backend.wait()
        proc_frontend.terminate()
        proc_frontend.wait()
        # Reset config.js to default
        with open("frontend/config.js", "w", encoding="utf-8") as f:
            f.write('window.APP_CONFIG = {\n  API_BASE: ""\n};\n')
        if db_split.exists():
            try: os.remove(db_split)
            except: pass

    # -------------------------------------------------------------
    # TEST 3: All Test Suites on Isolated DBs
    # -------------------------------------------------------------
    print("\n--- TEST 3: RUN ALL TEST SUITES ON ISOLATED DATABASES ---")
    test_files = [
        "test_phase1.py",
        "test_phase2.py",
        "test_phase4_phase5.py",
        "test_l1.py",
        "test_l2.py",
        "test_l3_matrix.py",
        "test_documents_and_cycle_override.py",
        "test_new_batch.py",
        "test_all_topics.py",
        "test_source_independence.py"
    ]

    suite_results = {}
    for t_file in test_files:
        if not Path(t_file).exists():
            continue
        env_suite = os.environ.copy()
        env_suite["DARKSPOT_DB"] = f"test_{Path(t_file).stem}_isolated.db"
        env_suite["LUMEN_DISABLE_RATE_LIMIT"] = "true"
        env_suite["TESTING"] = "true"
        env_suite["FORCE_MOCK"] = "true"

        res = subprocess.run(
            [sys.executable, t_file],
            env=env_suite,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace"
        )
        status = "PASS" if res.returncode == 0 else "FAIL"
        print(f"  [{status}] {t_file:32} (exit={res.returncode})")
        if res.returncode != 0:
            lines = res.stdout.strip().splitlines()[-15:]
            for l in lines:
                print(f"      {l}")
        suite_results[t_file] = status
        # Clean up isolated DB
        iso_db = Path(f"test_{Path(t_file).stem}_isolated.db")
        if iso_db.exists():
            try: os.remove(iso_db)
            except: pass

    failed = [k for k, v in suite_results.items() if v != "PASS"]
    print("\n" + "=" * 80)
    print(f"DEPLOYMENT VERIFICATION SUMMARY: All Suites Passed = {len(failed) == 0}")
    print("=" * 80)
    assert len(failed) == 0, f"Failed suites: {failed}"


if __name__ == "__main__":
    run_tests()
