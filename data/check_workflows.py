import json
import sys

d = json.load(sys.stdin)
names = ["scrape", "e2e", "ci"]
for w in d["workflows"]:
    if any(n in w["path"] for n in names):
        print(f"{w['name']}: id={w['id']} state={w['state']}")
