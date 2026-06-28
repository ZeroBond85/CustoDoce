import json
import sys

d = json.load(sys.stdin)
print(f"id={d['id']} name={d['name']} path={d['path']} state={d['state']}")
