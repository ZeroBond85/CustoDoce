"""Poll CI or Scrape status until completion."""
import subprocess
import time
import sys
import json

TARGET = sys.argv[1] if len(sys.argv) > 1 else "scrape"

if TARGET == "ci":
    arg = ["--branch", "feature/chefon-curl-cffi-fixes", "--limit", "2"]
    label = "CI"
    runners = ["CI - Testes e Qualidade", "Dependency Audit"]
else:
    arg = ["--workflow", "scrape.yml", "--limit", "1"]
    label = "Scrape"
    runners = None

for i in range(120):
    time.sleep(30)
    try:
        out = subprocess.run(
            ["gh", "run", "list"] + arg + ["--json", "status,conclusion,databaseId,workflowName"],
            capture_output=True, text=True, timeout=30
        )
        data = json.loads(out.stdout.strip() or "[]")
        if not data:
            print(f"[{i+1}] No runs found")
            continue
        if label == "Scrape":
            r = data[0]
            status, conclusion, rid = r["status"], r.get("conclusion",""), r.get("databaseId","?")
            print(f"[{i+1}] Scrape #{rid}: {status} -> {conclusion or '...'}")
            if status == "completed":
                print("ALL GREEN!" if conclusion == "success" else f"FAILED: {conclusion}")
                sys.exit(0 if conclusion == "success" else 1)
        else:
            for r in data:
                wf = r.get("workflowName","?")
                status, conclusion = r["status"], r.get("conclusion","")
                print(f"[{i+1}] {wf}: {status} -> {conclusion or '...'}")
            all_done = all(r["status"] == "completed" for r in data)
            if all_done:
                failures = [r for r in data if r.get("conclusion") != "success"]
                print("ALL GREEN!" if not failures else f"FAILED: {[f['workflowName'] for f in failures]}")
                sys.exit(0 if not failures else 1)
    except Exception as e:
        print(f"[{i+1}] Error: {e}")

print("TIMEOUT")
sys.exit(2)
