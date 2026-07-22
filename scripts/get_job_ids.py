import subprocess
import json

result = subprocess.run([
    "gh", "api", "repos/ZeroBond85/CustoDoce/actions/runs/29953479044/jobs", 
    "--paginate"
], capture_output=True, text=True, cwd="/mnt/c/Zerobond/Code/CustoDoce")

data = json.loads(result.stdout)
for job in data["jobs"]:
    name = job["name"]
    if "scrape" in name.lower() and "setup" not in name.lower() and "enrich" not in name.lower() and "commit" not in name.lower() and "notify" not in name.lower() and "cleanup" not in name.lower():
        print(f"{job['name']}: {job['id']}")