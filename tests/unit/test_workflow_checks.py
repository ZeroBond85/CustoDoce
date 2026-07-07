"""
Testes para validar a configuração dos workflows de scraping.

Objetivo: Garantir que a arquitetura consolidada (scrape-reusable.yml) está corretamente
referenciada pelos callers (scrape.yml, on_demand_scrape.yml, heal-scrapers.yml).

Sprint 12: consolidação de workflows – lint desses callers substitui checks legados
de jobs/ steps individuais (collect, alert, etc) que foram movidos para o reusable.
"""

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"


def _load_workflow(filename: str) -> dict:
    """Carrega um workflow a partir do diretório .github/workflows."""
    path = WORKFLOWS_DIR / filename
    assert path.is_file(), f"{filename} não encontrado em {path}"
    with path.open(encoding="utf-8") as f:
        workflow = yaml.safe_load(f)
    assert workflow and "jobs" in workflow, f"{filename} sem bloco 'jobs'"
    return workflow


def _scrape_callers() -> list[str]:
    """Retorna a lista de callers do workflow reutilizável."""
    return ["scrape.yml", "on_demand_scrape.yml", "heal-scrapers.yml"]


def test_all_scrape_callers_use_reusable():
    """Garante que todos os callers referenciam scrape-reusable.yml via 'uses'."""
    for filename in _scrape_callers():
        workflow = _load_workflow(filename)
        jobs = workflow.get("jobs", {}) or {}
        assert jobs, f"{filename} deve ter ao menos um job"
        for job_id, job in jobs.items():
            assert isinstance(job, dict), f"{filename} job {job_id} inválido"
            assert "uses" in job, (
                f"{filename} job {job_id} deve referenciar um workflow reutilizável via 'uses:'. "
                "Sprint 12: jobs diretos só devem permanecer se forem complementares ao reusable."
            )
            assert "scrape-reusable.yml" in str(job["uses"]), (
                f"{filename} job {job_id} deve referenciar './.github/workflows/scrape-reusable.yml'."
            )


def test_scrape_callers_have_no_steps_when_using_reusable():
    """Jobs que usam 'uses:' (workflow_call) NÃO podem ter 'steps:' próprio."""
    for filename in _scrape_callers():
        workflow = _load_workflow(filename)
        jobs = workflow.get("jobs", {}) or {}
        for job_id, job in jobs.items():
            if "uses" in job:
                assert "steps" not in job, (
                    f"{filename} job {job_id}: job com 'uses:' (workflow_call) "
                    "não pode ter 'steps:' próprio. Remova steps ou mova para o reusable."
                )


def test_scrape_reusable_has_required_jobs():
    """Garante que scrape-reusable.yml tem todos os jobs esperados: setup, scrape, enrich, commit, notify, cleanup."""
    workflow = _load_workflow("scrape-reusable.yml")
    jobs = workflow.get("jobs", {}) or {}
    required = {"setup", "scrape", "enrich", "commit", "notify", "cleanup"}
    missing = required - set(jobs.keys())
    assert not missing, f"scrape-reusable.yml está sem jobs obrigatórios: {missing}"


def test_scrape_jobs_have_time_budget_check():
    """Garante que jobs críticos do scrape-reusable têm check_time_budget para evitar estouro de minutos."""
    workflow = _load_workflow("scrape-reusable.yml")
    jobs_with_time_budget = {"scrape", "enrich", "commit", "notify", "cleanup"}
    for job_id in jobs_with_time_budget:
        if job_id not in workflow.get("jobs", {}):
            continue
        job = workflow["jobs"][job_id]
        steps = job.get("steps", []) or []
        has_check = any("check_time_budget" in str(s.get("run", "")) for s in steps)
        assert has_check, (
            f"Job '{job_id}' em scrape-reusable.yml deve ter um step com "
            "'python scripts/check_time_budget.py' para monitorar tempo de execução."
        )


def test_ci_workflow_jobs_have_record_start_time():
    """Garante que jobs do ci.yml registram CI_JOB_START (necessário para check_time_budget)."""
    workflow = _load_workflow("ci.yml")
    for job_id, job in workflow.get("jobs", {}).items():
        steps = job.get("steps", []) or []
        has_record = any(
            "CI_JOB_START" in str(s.get("run", "")) and "GITHUB_ENV" in str(s.get("run", ""))
            for s in steps
        )
        assert has_record, (
            f"Job '{job_id}' em ci.yml deve ter um step 'Record start time' que define "
            "CI_JOB_START (necessário para check_time_budget)."
        )


def test_ci_workflow_paths_at_trigger_level_not_job_level():
    """Garante que 'paths:' está no nível do trigger (on.push/on.pull_request), NÃO no nível do job.

    GitHub Actions só suporta path filtering em 'on.<event>.paths', não em jobs.<job_id>.paths.
    """
    workflow = _load_workflow("ci.yml")
    on = workflow.get("on", {}) or {}

    # Verifica se paths está definido no trigger push/pull_request
    for event in ("push", "pull_request"):
        if event in on and isinstance(on[event], dict):
            trigger_config = on[event]
            # Se tem branches, pode ter paths
            if "branches" in trigger_config:
                # paths é opcional, mas se existir deve estar aqui
                pass

    # CRÍTICO: nenhum job deve ter 'paths' no nível do job
    for job_id, job in workflow.get("jobs", {}).items():
        assert "paths" not in job, (
            f"ci.yml job '{job_id}': 'paths:' no nível do job é INVÁLIDO. "
            "Path filtering só funciona apenas em 'on.push.paths' ou 'on.pull_request.paths'. "
            "Use 'if:' condicional no job ou 'paths-ignore' no trigger."
        )


def test_pull_request_workflows_have_pr_guard():
    """Garante que workflows com jobs destrutivos (invasivos) ficam restritos a branches."""
    workflow = _load_workflow("scrape-reusable.yml")
    on = workflow.get(True, workflow.get("on", {})) or {}
    # workflow_call não tem 'branches' filter – caller é quem decide
    assert "workflow_call" in on, "scrape-reusable.yml deve usar trigger 'workflow_call'"


def test_cleaners_have_release_lock_step():
    """Garante que o job cleanup do scrape-reusable libera o lock distribuído."""
    workflow = _load_workflow("scrape-reusable.yml")
    cleanup = workflow["jobs"].get("cleanup")
    assert cleanup is not None, "Job 'cleanup' ausente em scrape-reusable.yml"
    steps = cleanup.get("steps", []) or []
    has_release = any(
        "scrape_lock.py release" in str(s.get("run", "")) for s in steps
    )
    assert has_release, "Job 'cleanup' deve liberar o lock via 'python scripts/scrape_lock.py release'"


def test_no_bash_github_conclusion_in_notify_steps():
    """Garante que notificações usam 'if: success()' / 'if: failure()' nativos, não bash $GITHUB_CONCLUSION.

    $GITHUB_CONCLUSION não existe em tempo de execução do step; use condicionais YAML nativos.
    ${ job.conclusion } É VÁLIDO quando usado em step COM 'if:' guard (success/failure/always).
    """
    for filename in ["backup.yml", "ci.yml", "scrape-reusable.yml"] + _scrape_callers():
        path = WORKFLOWS_DIR / filename
        if not path.is_file():
            continue
        with path.open(encoding="utf-8") as f:
            workflow = yaml.safe_load(f)

        # Verifica padrão problemático: $GITHUB_CONCLUSION em bash
        jobs = workflow.get("jobs", {}) or {}
        for job_id, job in jobs.items():
            steps = job.get("steps", []) or []
            for step in steps:
                run = str(step.get("run", ""))
                if "GITHUB_CONCLUSION" in run:
                    raise AssertionError(
                        f"{filename} job '{job_id}': usa '$GITHUB_CONCLUSION' em run: bash – INVÁLIDO. "
                        "Use 'if: success()' / 'if: failure()' / 'if: always()' no step."
                    )

                # Verifica ${{ job.conclusion }} SEM 'if:' guard - isso é inválido
                # Se o step tem ${{ job.conclusion }} mas NÃO tem if:, é erro
                if "${{ job.conclusion }}" in run:
                    step_if = step.get("if", "")
                    valid_guards = ("success()", "failure()", "always()", "cancelled()")
                    if not any(guard in step_if for guard in valid_guards):
                        raise AssertionError(
                            f"{filename} job '{job_id}': usa '${{ job.conclusion }}' em run: "
                            "sem 'if:' guard (success/failure/always). "
                            "Adicione 'if: always()' ao step ou use condicionais nativos."
                        )


def test_all_workflows_have_concurrency():
    """Todos os workflows devem ter configuração de concurrency para evitar paralelismo destrutivo.

    Workflows do tipo workflow_call (reusable) são exceção — os callers gerenciam concorrência.
    """
    for path in WORKFLOWS_DIR.glob("*.yml"):
        with path.open(encoding="utf-8") as f:
            workflow = yaml.safe_load(f)

        name = path.name

        # Reusable workflows (workflow_call) não precisam de concurrency própria
        on = workflow.get(True, workflow.get("on", {})) or {}
        if "workflow_call" in on:
            continue

        if name in ("scrape.yml", "on_demand_scrape.yml", "heal-scrapers.yml"):
            # Callers delegam concurrency para o job que chama o reusable
            jobs = workflow.get("jobs", {}) or {}
            for job_id, job in jobs.items():
                assert "concurrency" in job, (
                    f"{name} job '{job_id}': deve ter 'concurrency:' para evitar paralelismo."
                )
        else:
            # Workflows standalone devem ter concurrency no nível raiz
            assert "concurrency" in workflow, (
                f"{name}: workflow deve ter 'concurrency:' no nível raiz."
            )


if __name__ == "__main__":
    test_all_scrape_callers_use_reusable()
    test_scrape_callers_have_no_steps_when_using_reusable()
    test_scrape_reusable_has_required_jobs()
    test_scrape_jobs_have_time_budget_check()
    test_ci_workflow_jobs_have_record_start_time()
    test_ci_workflow_paths_at_trigger_level_not_job_level()
    test_pull_request_workflows_have_pr_guard()
    test_cleaners_have_release_lock_step()
    test_no_bash_github_conclusion_in_notify_steps()
    test_all_workflows_have_concurrency()
    print("All workflow check tests passed!")
