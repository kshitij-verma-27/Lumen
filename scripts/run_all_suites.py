import os
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Enforce isolated test database
os.environ["DARKSPOT_DB"] = "test_darkspot.db"
os.environ["FORCE_MOCK"] = "true"

test_files = [
    "test_phase1.py",
    "test_phase2.py",
    "test_l1.py",
    "test_l2.py",
    "test_l3_matrix.py",
    "test_all_topics.py",
    "test_source_independence.py",
    "test_new_batch.py",
    "test_documents_and_cycle_override.py",
    "test_phase4_phase5.py",
]

print("==================================================")
print(f"RUNNING ALL 10 TEST SUITES WITH ISOLATED TEST DBS (DARKSPOT_DB)")
print("==================================================\n")

results = {}

for tf in test_files:
    if not Path(tf).exists():
        print(f"[-] {tf}: SKIPPED (File not found)")
        continue
    
    suite_db = Path(f"scratch/test_{Path(tf).stem}.db")
    if suite_db.exists():
        try:
            suite_db.unlink()
        except Exception:
            pass

    test_env = os.environ.copy()
    test_env["DARKSPOT_DB"] = str(suite_db.resolve())
    test_env["FORCE_MOCK"] = "true"
    test_env["LUMEN_ALLOW_TEST_DOMAINS"] = "true"

    cmd = [sys.executable, tf]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=test_env)
    
    if res.returncode == 0:
        results[tf] = "PASS"
        print(f"[+] {tf:36s} -> PASS")
    else:
        results[tf] = "FAIL"
        print(f"[-] {tf:36s} -> FAIL (exit code {res.returncode})")
        if res.stderr:
            print("--- STDERR ---")
            print(res.stderr[:600])

print("\n==================================================")
print("TEST SUMMARY:")
for tf, status in results.items():
    print(f"  {tf:36s}: {status}")
all_passed = all(status == "PASS" for status in results.values())
print(f"\nOVERALL RESULT: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
print("==================================================")
