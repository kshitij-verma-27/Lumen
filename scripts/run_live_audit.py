import asyncio
import os
import sys
from pathlib import Path

# Ensure UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import init_db
from app.registry import seed_registry_from_yaml
from app.seed_validator import audit_all_seeds


async def main():
    init_db()
    seed_registry_from_yaml()

    print(">>> Starting LIVE Seed Audit (force_mock=False) <<<")
    try:
        results = await audit_all_seeds(force_mock=False)
    except Exception as e:
        print(f"FATAL: Live audit failed with exception: {e}")
        return

    print(f"\nAudit completed. Total seeds inspected: {len(results)}\n")
    print(f"{'ID':18} | {'Category':15} | {'Status':6} | {'Robots':10} | {'Needs JS':8} | {'Mode':4} | {'Reachability':12} | {'Final URL':45}")
    print("-" * 135)
    for r in results:
        status_code = str(r.get("status_code") or "ERR")
        final = r.get("final_url") or r["url"]
        needs_js_str = "YES" if r.get("needs_js") else "NO"
        reach = r.get("reachability", "unknown")
        mode = r.get("audit_mode", "live")
        robots = r.get("robots_status", "unknown")
        print(f"{r['id']:18} | {r['category']:15} | {status_code:6} | {robots:10} | {needs_js_str:8} | {mode:4} | {reach:12} | {final:45}")

    reachable = [r for r in results if r["reachability"] == "reachable"]
    needs_js = [r for r in results if r["reachability"] == "needs_js"]
    blocked = [r for r in results if r["reachability"] == "blocked"]
    unreachable = [r for r in results if r["reachability"] == "unreachable"]

    print("\nSummary:")
    print(f"  Reachable (direct text): {len(reachable)}")
    print(f"  Needs JS (thin DOM/SPA): {len(needs_js)}")
    print(f"  Blocked (HTTP 403)     : {len(blocked)}")
    print(f"  Unreachable (timeout)  : {len(unreachable)}")


if __name__ == "__main__":
    asyncio.run(main())
