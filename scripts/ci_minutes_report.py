#!/usr/bin/env python3
"""
Script para gerar relatório de minutos consumidos por workflows no GitHub Actions.

Uso:
  python ci_minutes_report.py

Este script coleta dados de cada workflow e gera um JSON com o consumo de minutos.
"""

import json
import os
import subprocess
import sys
from datetime import datetime

# Configuração
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPORT_FILE = ".github/minutes_report.json"


def get_workflow_runs() -> list[dict]:
    """Retorna uma lista de runs de workflows dos últimos 30 dias."""
    if not GITHUB_TOKEN:
        raise ValueError("GITHUB_TOKEN não está definido.")

    # Obter todos os workflows ativos
    workflows = subprocess.check_output(
        ["gh", "api", "repos/{owner}/{repo}/actions/workflows"],
        env={"GITHUB_TOKEN": GITHUB_TOKEN},
        text=True,
    )
    workflows = json.loads(workflows)

    workflow_names = [w["name"] for w in workflows]

    # Obter runs de cada workflow
    runs = []
    for workflow_name in workflow_names:
        try:
            runs_response = subprocess.check_output(
                [
                    "gh", "api",
                    f"repos/{os.getenv('GITHUB_REPOSITORY')}/actions/runs",
                    "--workflow", workflow_name,
                    "--limit", "100",
                    "--json", "conclusion,workflow_name,duration,created_at"
                ],
                env={"GITHUB_TOKEN": GITHUB_TOKEN},
                text=True,
            )
            runs_response = json.loads(runs_response)
            for run in runs_response:
                runs.append({
                    "workflow_name": workflow_name,
                    "conclusion": run["conclusion"],
                    "duration": run["duration"],
                    "created_at": run["created_at"],
                })
        except subprocess.CalledProcessError:
            continue

    return runs


def calculate_minutes_consumed(runs: list[dict]) -> dict[str, int]:
    """Calcula o total de minutos consumidos por workflow."""
    minutes_by_workflow = {}

    for run in runs:
        if run["conclusion"] != "success":
            continue

        duration_seconds = run["duration"] / 1000  # Convertendo de ms para segundos
        minutes = duration_seconds / 60

        workflow_name = run["workflow_name"]
        minutes_by_workflow[workflow_name] = minutes_by_workflow.get(workflow_name, 0) + minutes

    return minutes_by_workflow


def generate_report(minutes_by_workflow: dict[str, int]) -> dict:
    """Gera um relatório completo com os minutos consumidos."""
    report = {
        "timestamp": datetime.now().isoformat(),
        "total_minutes": sum(minutes_by_workflow.values()),
        "workflows": minutes_by_workflow,
        "free_tier_limit": 2000,
        "remaining_minutes": 2000 - sum(minutes_by_workflow.values()),
    }

    return report


def save_report(report: dict) -> None:
    """Salva o relatório em um arquivo JSON."""
    with open(REPORT_FILE, "w") as f:
        json.dump(report, f, indent=2)

    print(f"Relatório salvo em {REPORT_FILE}")


if __name__ == "__main__":
    try:
        runs = get_workflow_runs()
        minutes_by_workflow = calculate_minutes_consumed(runs)
        report = generate_report(minutes_by_workflow)
        save_report(report)
    except Exception as e:
        print(f"Erro ao gerar relatório: {e}", file=sys.stderr)
        sys.exit(1)