import sys
import re
from pathlib import Path
sys.path.insert(0, '.')
from scripts.doc_utils import read_frontmatter

root = Path('.')
categories = {
    'Snapshots (Archive)': ['docs/archive/'],
    'Core Config (Live)': ['AGENTS.md', 'README.md', 'REGRAS.md', 'LESSONS.md', 'docs/changelog.md', 'docs/skills.md'],
    'Reference/Docs (Timestamp)': ['docs/architecture.md', 'docs/troubleshooting.md', 'docs/security.md', 'docs/deployment.md', 'docs/deployment-staging.md', 'docs/contributing.md', 'docs/migration-guide.md', 'docs/ROLLBACK_PROD.md', 'tests/README.md'],
    'ADRs (Immutable)': ['docs/adr/'],
    'API (Auto-Generated)': ['docs/api/']
}

print('='*80)
print('ANALISE DE COERENCIA DOS .MD - BASELINE POS-ATUALIZACAO')
print('='*80)

for cat, patterns in categories.items():
    print(f'\n--- {cat} ---')
    for pattern in patterns:
        p = Path(pattern)
        files = [p] if p.is_file() else sorted(p.glob('*.md'))
        for f in files:
            if not f.exists():
                continue
            fm, body = read_frontmatter(f)
            has_fm = bool(fm)
            fm_keys = list(fm.keys()) if fm else []
            ts_match = re.search(r'> Ultima (atualizacao|revisao|snapshot): (\S+ \S+)', body)
            ts = ts_match.group(2) if ts_match else 'N/A'
            truth = fm.get('truth_at') if fm else None
            print(f'  {f.relative_to(root)}')
            print(f'    Frontmatter: {"SIM" if has_fm else "NAO"} ({", ".join(fm_keys) if fm_keys else "vazio"})')
            print(f'    Timestamp: {ts}')
            if truth:
                print(f'    truth_at: {truth}')