import json
import sys

d = json.load(sys.stdin)
# Update check_workflows to show more fields
for w in d["workflows"]:
    if "scrape" in w["path"] or "e2e" in w["path"]:
        print(f"{w['path']}: created={w['created_at']} updated={w['updated_at']}")
