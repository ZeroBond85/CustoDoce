import re
import sys
from datetime import UTC, datetime
from pathlib import Path

_TIMESTAMP_PAT = re.compile(r'> Última (atualização|revisão): (\d{4}-\d{2}-\d{2}) \d{2}:\d{2} UTC')
_SKIP_DIRS = {'.git', '.venv', '.venv314', 'node_modules', '__pycache__', 'lib64', '.pytest_cache', '.opencode', '.agent'}
_EXCLUDE_FILES = {'docs/changelog.md', 'docs/skills.md', 'AGENTS.md'}

root = Path('.')
issues = []

for md_file in root.rglob('*.md'):
    rel = md_file.relative_to(root)
    if any(skip in md_file.parts for skip in _SKIP_DIRS):
        continue
    if str(rel).replace('\\', '/') in _EXCLUDE_FILES:
        continue
    try:
        content = md_file.read_text(encoding='utf-8')
    except Exception:
        continue
    m = _TIMESTAMP_PAT.search(content)
    if not m:
        issues.append(f'{rel}: missing timestamp')
        continue
    label = m.group(1)
    date_str = m.group(2)
    try:
        ts_date = datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=UTC)
        delta = datetime.now(UTC) - ts_date
        if delta.days > 14:
            issues.append(f'{rel}: timestamp is {delta.days} days old (max 14) — label={label}, date={date_str}')
    except ValueError:
        issues.append(f'{rel}: invalid timestamp date: {date_str}')

print(f'Total issues: {len(issues)}')
for i in issues:
    print(f'  - {i}')
sys.exit(1 if issues else 0)