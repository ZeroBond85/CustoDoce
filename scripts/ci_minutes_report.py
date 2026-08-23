#!/usr/bin/env python3
"""Relatório de minutos do GitHub Actions (free tier 2.000/mês).

Uso:
    python scripts/ci_minutes_report.py [--days 30]

Fonte: API de workflow runs (últimos N dias). Minutos por run =
ceil((updated_at - created_at) / 60), somado por workflow. Aproximação:
o GitHub cobra por JOB-minuto (jobs paralelos somam), então o número real
tende a ser MAIOR que o reportado aqui — usar como piso.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

REPORT_FILE = ".github/minutes_report.json"
FREE_TIER_LIMIT = 2000

# gh pode não estar no PATH do shell que invocou o Python (Windows) — mesmos
# caminhos canônicos de scripts/git_push.py::_CANDIDATE_BINS (LESSONS #80).
_CANDIDATE_BINS = [
    r"C:\Program Files\GitHub CLI",
    r"C:\Program Files (x86)\GitHub CLI",
    r"C:\Program Files\Git\cmd",
]


def _ensure_gh_path() -> None:
    env_path = os.environ.get("PATH", "")
    paths = env_path.split(os.pathsep) if env_path else []
    existing = {p.lower() for p in paths}
    added = False
    for cand in _CANDIDATE_BINS:
        if os.path.isdir(cand) and cand.lower() not in existing:
            paths.append(cand)
            existing.add(cand.lower())
            added = True
    if added:
        os.environ["PATH"] = os.pathsep.join(paths)


def _gh(*args: str) -> str:
    """Executa `gh` com o ambiente herdado (token vem de gh auth login)."""
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])}… falhou: {result.stderr.strip()[:200]}")
    return result.stdout


def get_repo() -> str:
    """owner/repo do remote origin (funciona fora do CI, sem GITHUB_REPOSITORY)."""
    out = _gh("repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner")
    return out.strip()


def get_workflow_runs(repo: str, days: int) -> list[dict]:
    """Runs dos últimos N dias com campos normalizados."""
    since = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
    runs: list[dict] = []
    page = 1
    while True:
        qs = urlencode({"created": f">{since}", "per_page": "100", "page": str(page)})
        out = _gh(
            "api",
            f"repos/{repo}/actions/runs?{qs}",
            "--jq", ".workflow_runs | map({wf: .name, created: .created_at, updated: .updated_at})",
        )
        batch = json.loads(out or "[]")
        if not batch:
            break
        runs.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return runs


def calculate_minutes(runs: list[dict]) -> dict[str, float]:
    """Minutos (piso) por workflow, somando ceil de cada run."""
    by_wf: dict[str, float] = {}
    for r in runs:
        try:
            created = datetime.fromisoformat(r["created"].replace("Z", "+00:00"))
            updated = datetime.fromisoformat(r["updated"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        minutes = max(1, round((updated - created).total_seconds() / 60))
        wf = r.get("wf") or "desconhecido"
        by_wf[wf] = by_wf.get(wf, 0) + minutes
    return dict(sorted(by_wf.items(), key=lambda kv: kv[1], reverse=True))


def generate_report(minutes_by_workflow: dict[str, float], days: int) -> dict:
    total = sum(minutes_by_workflow.values())
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "period_days": days,
        "total_minutes": total,
        "monthly_estimate": round(total * 30 / days) if days else total,
        "free_tier_limit": FREE_TIER_LIMIT,
        "workflows": minutes_by_workflow,
    }


def main() -> int:
    # Console Windows é cp1252 — emojis/acentos no output quebram com
    # UnicodeEncodeError. UTF-8 com replace evita crash de impressão.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30, help="Janela em dias (default 30)")
    args = parser.parse_args()

    _ensure_gh_path()
    try:
        repo = get_repo()
        print(f"Repo: {repo} · janela: {args.days} dias")
        runs = get_workflow_runs(repo, args.days)
        print(f"Runs encontrados: {len(runs)}")
    except RuntimeError as e:
        print(f"Erro: {e}", file=sys.stderr)
        return 1

    minutes_by_workflow = calculate_minutes(runs)
    report = generate_report(minutes_by_workflow, args.days)

    print(f"\n{'Workflow':<40} {'Minutos':>8}")
    print("-" * 50)
    for wf, m in minutes_by_workflow.items():
        print(f"{wf:<40} {m:>8.0f}")
    print("-" * 50)
    est = report["monthly_estimate"]
    pct = est / FREE_TIER_LIMIT * 100
    print(f"Total {args.days}d: {report['total_minutes']:.0f} min · projeção mensal: ~{est} min ({pct:.0f}% de {FREE_TIER_LIMIT})")
    if pct > 80:
        print("⚠️ Projeção acima de 80% do free tier!")

    with open(REPORT_FILE, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nRelatório salvo em {REPORT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
