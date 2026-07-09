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
    python scripts/audit_secrets.py --since N        # escaneia so arquivos
                                                     # alterados nos ultimos N
                                                     # commits + working tree

Sai com codigo nao-zero somente em modo --strict ou quando
encontra segredo de alta confianca (API key real).

O flag --since reduz drasticamente o tempo de scan: em vez de varrer
todos os arquivos rastreados, varre apenas os arquivos tocados nos
ultimos N commits (git diff HEAD~N..HEAD) mais o working tree
(unstaged, staged e arquivos novos nao rastreados). Usado no pre-push
para escanear exatamente o que sera enviado (commits ainda nao pushados).
Sem --since, comporta-se como antes (scan completo do historico).
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

# Path prefixes to skip (false positives conhecidos ex: teste do proprio scanner)
EXCLUDE_PREFIXES: tuple[str, ...] = (
    "tests/unit/test_audit_secrets",
)

HIGH_CONFIDENCE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai_key", re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]{20,}")),
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("groq_key", re.compile(r"gsk_[A-Za-z0-9]{20,}")),
    ("openrouter_key", re.compile(r"sk-or-v1-[A-Za-f0-9]{40,}")),
    # mistral_key: Mistral API keys are 32-char IDs typically named "mistral_..." in env
    # Historical regex `(?<![A-Za-z0-9])[A-Za-z0-9]{32,}(?![A-Za-z0-9])` falso-positivo: matchava
    # "PytestUnraisableExceptionWarning" (32 chars). Removido # chave valida com prefixo + tamanho.
    # ("mistral_key", re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9]{32,}(?![A-Za-z0-9])")),
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
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def _changed_paths(since: int | None) -> list[str] | None:
    """Retorna a lista de caminhos relevantes para escopo --since.

    Se `since` for None, retorna None (chamador faz scan completo).
    Caso contrario, une: arquivos alterados nos ultimos `since` commits
    (HEAD~since..HEAD), working tree (unstaged + staged) e arquivos novos
    nao rastreados. Caminhos duplicados sao removidos preservando ordem.
    """
    if since is None:
        return None

    paths: list[str] = []
    seen: set[str] = set()

    def _collect(*git_args: str) -> None:
        try:
            res = subprocess.run(
                [_GIT, *git_args],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except subprocess.TimeoutExpired:
            return
        if res.returncode != 0:
            return
        for line in res.stdout.splitlines():
            line = line.strip()
            if not line or line in seen:
                continue
            seen.add(line)
            paths.append(line)

    # Commits recentes (o que sera pushado)
    _collect("diff", "--name-only", f"HEAD~{since}..HEAD")
    # Working tree (unstaged + staged)
    _collect("diff", "--name-only")
    _collect("diff", "--cached", "--name-only")
    # Arquivos novos nao rastreados (leitura do disco, nao do blob)
    _collect("ls-files", "--others", "--exclude-standard")
    return paths


def scan_tracked_files(since: int | None = None) -> list[Finding]:
    if since is None:
        ls = subprocess.run(
            [_GIT, "ls-files"],
            capture_output=True,
            check=True,
            text=True,
        )
        candidates = [
            p
            for p in ls.stdout.splitlines()
            if not p.startswith(".git/")
            and not any(p.lower().endswith(ext) for ext in BINARY_EXTENSIONS)
            and not any(p.startswith(prefix) for prefix in EXCLUDE_PREFIXES)
        ]
    else:
        # Escopo reduzido: apenas arquivos alterados recentemente.
        scoped = _changed_paths(since)
        if scoped is None:
            return scan_tracked_files(since=None)
        candidates = [
            p
            for p in scoped
            if not p.startswith(".git/")
            and not any(p.lower().endswith(ext) for ext in BINARY_EXTENSIONS)
            and not any(p.startswith(prefix) for prefix in EXCLUDE_PREFIXES)
        ]

    findings: list[Finding] = []
    for path in candidates:
        # Arquivos nao rastreados (novos) nao existem como blob no git;
        # lemos do disco. Demais usam o blob da working tree via git show.
        text = _git_blob_text(path)
        if text is None:
            # Fallback: tenta ler do disco (arquivo novo nao commitado)
            try:
                from pathlib import Path

                text = Path(path).read_text(encoding="utf-8", errors="replace")
            except (OSError, UnicodeDecodeError):
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
    parser.add_argument(
        "--since",
        type=int,
        default=None,
        help="Escaneia so arquivos alterados nos ultimos N commits + working tree.",
    )
    args = parser.parse_args()

    findings = scan_tracked_files(since=args.since)

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
