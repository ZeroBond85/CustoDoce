import json
import sys

data = json.load(sys.stdin)
for r in data:
    conclusion = r.get("conclusion", "") or ""
    print(f"{r['name']}: {r['status']} {conclusion[:10]}")
