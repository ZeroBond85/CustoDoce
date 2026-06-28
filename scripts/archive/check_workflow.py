import base64
import subprocess

result = subprocess.run(
    ["gh", "api", "repos/ZeroBond85/CustoDoce/contents/.github/workflows/scrape.yml", "--jq", ".content"],
    capture_output=True,
    text=True,
)  # noqa: S607
content = result.stdout.strip().strip('"')
decoded = base64.b64decode(content).decode("utf-8")
print("workflow_dispatch in decoded:", "workflow_dispatch" in decoded)

# Find the workflow_dispatch section
idx = decoded.find("workflow_dispatch")
if idx >= 0:
    print("---")
    print(decoded[max(0, idx - 200) : idx + 500])
