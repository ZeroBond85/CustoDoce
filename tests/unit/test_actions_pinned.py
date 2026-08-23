"""Unit tests para PR-05 — todas as Actions pinadas por SHA.

Regra AGENTS #10 (paridade) + hardening supply-chain: `uses:` externo
deve ser `owner/action@<40-hex>` (tag mutável permite troca silenciosa
do código executado). `uses:` locais (./.github/...) são permitidos.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

USES_RE = re.compile(r"uses:\s*(\S+)")

# SHAs canônicos (atualizar juntos com os yml ao bumpar versão).
EXPECTED_PINS = {
    "actions/checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/setup-python": "ece7cb06caefa5fff74198d8649806c4678c61a1",
    "actions/cache": "55cc8345863c7cc4c66a329aec7e433d2d1c52a9",
    "actions/upload-artifact": "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
}


def _iter_uses():
    for yml in sorted(WORKFLOWS.glob("*.yml")):
        for i, line in enumerate(yml.read_text(encoding="utf-8").splitlines(), 1):
            m = USES_RE.search(line)
            if m:
                yield yml.name, i, m.group(1)


def test_all_external_uses_sha_pinned():
    bad = []
    for wf, ln, ref in _iter_uses():
        if ref.startswith("./"):
            continue
        if not re.fullmatch(r"[^@]+@[0-9a-f]{40}", ref):
            bad.append(f"{wf}:{ln} {ref}")
    assert not bad, f"uses: sem pin SHA: {bad}"


def test_expected_pins_unchanged():
    found = {ref.split("@")[0]: ref.split("@")[1] for _, _, ref in _iter_uses() if "@" in ref and not ref.startswith("./")}
    for action, sha in EXPECTED_PINS.items():
        assert found.get(action) == sha, f"{action} mudou de SHA sem atualizar EXPECTED_PINS"
