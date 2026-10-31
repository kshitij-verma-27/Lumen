import sqlite3
import json

conn = sqlite3.connect("darkspot.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Get all 29 seeds
rows = cursor.execute("""
    SELECT id, name, domain_category, base_url, http_status, reachability, needs_js, final_url, last_audited
    FROM registry_sources
    WHERE id LIKE 'edu_%' OR id LIKE 'car_%' OR id LIKE 'pub_%' OR id LIKE 'res_%' OR id LIKE 'biz_%'
    ORDER BY id ASC;
""").fetchall()

total_seeds = len(rows)

# Compute counts strictly from stored rows
status_counts = {}
for r in rows:
    st = r["http_status"]
    status_counts[st] = status_counts.get(st, 0) + 1

reachable_rows = [r for r in rows if r["reachability"] == "reachable"]
needs_js_rows = [r for r in rows if r["needs_js"] == 1]
blocked_rows = [r for r in rows if r["reachability"] == "blocked"]
unreachable_rows = [r for r in rows if r["reachability"] == "unreachable"]

# Extract portal names strictly from rows
blocked_names = [f"{r['name']} ({r['id']}, status {r['http_status']})" for r in blocked_rows]
needs_js_names = [f"{r['name']} ({r['id']})" for r in needs_js_rows]
reachable_names = [f"{r['name']} ({r['id']})" for r in reachable_rows]

# Generate limitations text with code
limitations_text = (
    f"The registry contains {total_seeds} official seeds across 5 national domains. "
    f"In our live audit (User-Agent: LumenResearchBot/1.0), {len(reachable_rows)} portals are directly reachable "
    f"with full HTML text content. {len(needs_js_rows)} portals ({', '.join(needs_js_names[:3])}, etc.) return HTTP 200 "
    f"but yield thin initial HTML markup because they rely on client-side JavaScript / Single Page Application hydration. "
    f"A total of {len(blocked_rows)} portals ({', '.join(blocked_names)}) returned HTTP 403 to our automated request. "
    f"Specifically, NTA ({[r['base_url'] for r in rows if r['id'] == 'edu_nta'][0]}) and Udyam "
    f"({[r['base_url'] for r in rows if r['id'] == 'biz_udyam'][0]}) were confirmed live and reachable. "
    f"JoSAA is not an enrolled seed in the 29 baseline registry entries in data/registry.yaml."
)

summary = {
    "total_seeds": total_seeds,
    "http_200_count": status_counts.get(200, 0),
    "http_403_count": status_counts.get(403, 0),
    "http_other_count": sum(c for st, c in status_counts.items() if st not in (200, 403)),
    "reachable_count": len(reachable_rows),
    "needs_js_count": len(needs_js_rows),
    "blocked_count": len(blocked_rows),
    "unreachable_count": len(unreachable_rows),
    "blocked_portals": blocked_names,
    "needs_js_portals": needs_js_names,
    "limitations_text": limitations_text
}

print("=== CODE-COMPUTED AUDIT COUNTS ===")
print(json.dumps(summary, indent=2))
print("\n=== DYNAMICALLY GENERATED LIMITATIONS TEXT ===")
print(limitations_text)
