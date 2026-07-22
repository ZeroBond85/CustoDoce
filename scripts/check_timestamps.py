import re
import sys
from datetime import UTC, datetime
from pathlib import Path

root = Path(".")
pattern = re.compile(r"> Última (atualização|revisão): (\d{4}-\d{2}-\d{2}) \d{2}:\d{2} UTC")
skip_dirs = {".git", ".venv", ".venv314", "node_modules", "__pycache__", "lib64", ".pytest_cache", ".opencode", ".agent"}
exclude_files = {"docs/changelog.md", "docs/skills.md", "AGENTS.md"}

issues = []
files_checked = 0

for md_file in root.rglob("*.md"):
    files_checked += 1
    parts = md_file.parts
    if any(skip in parts for skip in skip_dirs):
        continue
    rel = md_file.relative_to(root)
    rel_str = str(rel).replace("\\", "/")
    if rel_str in exclude_files:
        continue
    try:
        content = md_file.read_text(encoding="utf-8")
    except Exception:
        continue
    m = pattern.search(content)
    if not m:
        issues.append(f"{rel_str}: missing timestamp")
        continue
    label = m.group(1)
    date_str = m.group(2)
    try:
        ts_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
        delta = datetime.now(UTC) - ts_date
        if delta.days > 14:
            issues.append(f"{rel_str}: timestamp is {delta.days} days old (max 14)")
    except ValueError:
        issues.append(f"{rel_str}: invalid timestamp date: {date_str}")

print(f"Files checked: {files_checked}")
print(f"Issues found: {len(issues)}")
for i in issues:
    print(f"  - {i}")
sys.exit(1 if issues else 0)