"""
Testes para validar a configuração do workflow scrape.yml.

Objetivo: Garantir que o Checkout não usa token custom (GH_PAT) em scheduled workflows,
evitando falha "fatal: could not read Username for 'https://github.com': terminal prompts disabled".
"""

from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRAPE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "scrape.yml"


def load_scrape_workflow() -> dict:
    """Carrega o workflow scrape.yml a partir da raiz do repo."""
    assert SCRAPE_WORKFLOW.is_file(), f"scrape.yml não encontrado em {SCRAPE_WORKFLOW}"
    with SCRAPE_WORKFLOW.open(encoding="utf-8") as f:
        workflow = yaml.safe_load(f)
    assert workflow and "jobs" in workflow, "scrape.yml sem bloco 'jobs'"
    return workflow


def find_collect_job(workflow: dict) -> dict:
    """Seleciona o job 'collect' do scrape.yml (nome ou id 'collect')."""
    jobs = workflow.get("jobs", {}) or {}
    if "collect" in jobs:
        job = jobs["collect"]
        if isinstance(job, dict):
            return job
    for job in jobs.values():
        if isinstance(job, dict) and job.get("name") == "collect":
            return job
    pytest.fail("Job 'collect' não encontrado em scrape.yml")


def find_step(steps, name: str):
    found = next((s for s in steps if s.get("name") == name), None)
    if found is None:
        pytest.fail(f"Step '{name}' não encontrado em scrape.yml/jobs.collect")
    return found


def test_checkout_no_custom_token():
    """
    Valida que o step 'Checkout' do job 'collect' não usa 'with: token: ${{ secrets.GH_PAT }}'.
    Causa raiz: scheduled workflow falhava com 'terminal prompts disabled' por token custom.
    """
    workflow = load_scrape_workflow()
    job = find_collect_job(workflow)
    steps = job.get("steps", []) or []
    checkout = find_step(steps, "Checkout")
    with_section = checkout.get("with") or {}
    if with_section:
        assert "token" not in with_section or with_section.get("token") != "${{ secrets.GH_PAT }}", (
            "Checkout não deve usar 'with: token: ${{ secrets.GH_PAT }}' em scheduled workflows. "
            "Use checkout default (sem token) para evitar falha em scheduled runs."
        )


def test_alert_steps_use_curl_not_httpx():
    """
    Valida que os steps 'Alert on commit failure' e 'Alert on email failure' usam 'curl'
    (não 'python -c \"import httpx\"') para evitar cascata de falhas em ambientes restritos.
    """
    workflow = load_scrape_workflow()
    job = find_collect_job(workflow)
    steps = job.get("steps", []) or []

    alert_names = {"Alert on commit failure", "Alert on email failure"}
    found_names = {s.get("name") for s in steps if s.get("name") in alert_names}

    # Segue convenção CustoDoce: alertas usam `curl` (out-of-the-box) e não Python inline.
    assert "Alert on commit failure" in found_names
    assert "Alert on email failure" in found_names

    for step in steps:
        if step.get("name") not in alert_names:
            continue
        run_script = step.get("run", "") or ""
        assert "python -c \"import httpx\"" not in run_script, (
            f"Step '{step.get('name')}' ainda usa 'python -c \"import httpx\"'. "
            "Substituir por 'curl' para evitar dependência externa em caso de falha."
        )
        assert "curl" in run_script, (
            f"Step '{step.get('name')}' deve usar 'curl' para alertas Telegram."
        )


def test_gh_pat_used_only_in_commit_push_step():
    """
    Valida que o GH_PAT é referenciado apenas no step 'Commit Latest Pushing latest prices',
    e não em nenhum outro step do job 'collect'.
    """
    workflow = load_scrape_workflow()
    job = find_collect_job(workflow)
    steps = job.get("steps", []) or []

    commit_push_step = find_step(steps, "Commit Latest Pushing latest prices")
    commit_dumped = yaml.safe_dump(commit_push_step)
    assert "secrets.GH_PAT" in commit_dumped, (
        "Step 'Commit Latest Pushing latest prices' deve referenciar 'secrets.GH_PAT' "
        "(necessário para git push)."
    )

    for step in steps:
        if step is commit_push_step:
            continue
        dumped = yaml.safe_dump(step)
        assert "secrets.GH_PAT" not in dumped, (
            f"Step '{step.get('name', '?')}' referencia 'secrets.GH_PAT' "
            "mas apenas 'Commit Latest Pushing latest prices' deve fazê-lo."
        )
        # Defensivo: nenhum step exceto o git push deve definir token custom no checkout.
        with_block = step.get("with") or {}
        if "uses" in step and "checkout" in str(step.get("uses", "")):
            assert "token" not in with_block, (
                f"Step '{step.get('name')}' (checkout) NÃO deve usar 'with: token:' custom."
            )


if __name__ == "__main__":
    test_checkout_no_custom_token()
    test_alert_steps_use_curl_not_httpx()
    test_gh_pat_used_only_in_commit_push_step()
    print("All tests passed!")
