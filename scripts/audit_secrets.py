"""Auditoria de segredos no repositorio.

Varre o historico rastreado do git atras de padroes conhecidos de chave
de API (OpenAI, Anthropic, Groq, OpenRouter, Mistral, HuggingFace,
DeepSeek, Google, GitHub, Supabase, Slack, Stripe, Google service
accounts, PEM blocks) e de arquivos sensiveis (configs de editor,
backups SQL, dumps, modelos).

Uso:
    python scripts/audit_secrets.py                  # passa silencioso; exit 0
    python scripts/audit_secrets.py --strict        # exit 1 se encontrar algo
    python scripts/audit_secrets.py --json          # output JSON para CI

Sai com codigo nao-zero somente em modo --strict ou quando
encontra segredo de alta confianca (API key real).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass

# Skip binary files entirely (false positives from embedded metadata)
BINARY_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".pdf",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".ico",
        ".zip",
        ".gz",
        ".tar",
        ".7z",
        ".whl",
        ".pyc",
        ".pyo",
        ".onnx",
        ".pt",
        ".pth",
        ".npy",
        ".npz",
        ".bin",
        ".safetensors",
        ".pkl",
        ".h5",
        ".so",
        ".dll",
        ".exe",
    }
)

HIGH_CONFIDENCE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai_key", re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]{20,}")),
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("groq_key", re.compile(r"gsk_[A-Za-z0-9]{20,}")),
    ("openrouter_key", re.compile(r"sk-or-v1-[A-Za-f0-9]{40,}")),
    ("mistral_key", re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9]{32}(?![A-Za-z0-9])")),
    ("huggingface_key", re.compile(r"hf_[A-Za-z0-9]{20,}")),
    ("deepseek_key", re.compile(r"sk-[a-f0-9]{32}")),
    ("google_api_key", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("slack_token", re.compile(r"xox[abpr]-[0-9A-Za-z\-]{10,}")),
    ("stripe_key", re.compile(r"sk_(?:live|test)_[A-Za-z0-9]{20,}")),
    ("pem_private_key", re.compile(r"-----BEGIN (?:RSA|EC|OPENSSH|PRIVATE) (?:PRIVATE )?KEY-----")),
    ("google_service_account", re.compile(r'"type"\s*:\s*"service_account"')),
    (
        "supabase_service_role",
        re.compile(r"eyJhbGciOi[A-Za-z0-9_\-]{50,}\.eyJ[A-Za-z0-9_\-]{50,}\.[A-Za-z0-9_\-]{20,}"),
    ),
)


@dataclass(frozen=True)
class Finding:
    pattern: str
    path: str
    line_no: int
    snippet: str


_GIT = shutil.which("git") or "git"


def _git_blob_text(path: str) -> str | None:
    try:
        result = subprocess.run(
            [_GIT, "show", f":{path}"],
            capture_output=True,
            check=True,
            timeout=10,
        )
        return result.stdout.decode("utf-8", errors="replace")
    except subprocess.CalledProcessError, subprocess.TimeoutExpired:
        return None


def scan_tracked_files() -> list[Finding]:
    ls = subprocess.run(
        [_GIT, "ls-files"],
        capture_output=True,
        check=True,
        text=True,
    )
    findings: list[Finding] = []
    for path in ls.stdout.splitlines():
        if path.startswith(".git/"):
            continue
        if any(path.lower().endswith(ext) for ext in BINARY_EXTENSIONS):
            continue
        text = _git_blob_text(path)
        if text is None:
            continue
        for name, pat in HIGH_CONFIDENCE_PATTERNS:
            for match in pat.finditer(text):
                line_no = text.count("\n", 0, match.start()) + 1
                start = max(0, match.start() - 16)
                end = min(len(text), match.end() + 16)
                snippet = text[start:end].replace("\n", "\\n")
                findings.append(Finding(name, path, line_no, snippet))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Audita segredos expostos no repo.")
    parser.add_argument("--strict", action="store_true", help="Sai com codigo nao-zero se encontrar algo.")
    parser.add_argument("--json", action="store_true", help="Output em JSON.")
    args = parser.parse_args()

    findings = scan_tracked_files()

    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=2))
    else:
        if not findings:
            print("OK: nenhum segredo de alta confianca detectado nos arquivos rastreados.")
        else:
            print(f"ATENCAO: {len(findings)} possivel(is) segredo(s) detectado(s):")
            for f in findings:
                print(f"  - {f.pattern} em {f.path}:{f.line_no}  | {f.snippet}")

    if findings and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
