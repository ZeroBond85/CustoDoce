"""
Testes para validar a configuração do workflow scrape.yml.
"""

import yaml
import os

def load_workflow_file(file_path):
    with open(file_path, encoding="utf-8") as f:
        return yaml.safe_load(f)

def test_checkout_no_custom_token():
    """Testa que o checkout não usa token custom."""
    workflow = load_workflow_file("C:\Zerobond\Code\CustoDoce\.github\workflows\scrape.yml")
    collect_job = workflow.get('jobs', {}).get('collect', {})
    steps = collect_job.get('steps', [])
    print("Steps names:", [step.get('name') for step in steps])
    
    # Debug: print all steps
    print("Jobs keys:", workflow.get('jobs', {}).keys())
    
    # Find the checkout step
    checkout_step = next((step for step in steps if step.get("name") == "Checkout"), None)
    assert checkout_step is not None, "Step 'Checkout' não encontrado"
    
    # Check if the checkout step has a 'with' section and it does not contain a custom token
    with_section = checkout_step.get("with", {})
    if with_section:
        assert "token" not in with_section or with_section.get("token") != "${{ secrets.GH_PAT }}", (
            "Checkout deve usar checkout default (sem token) para evitar falha em scheduled runs."
        )
    else:
        print("Checkout step has no 'with' section")

def test_alert_steps_use_curl():
    """Testa que os alertas usam curl."""
    workflow = load_workflow_file("C:\Zerobond\Code\CustoDoce\.github\workflows\scrape.yml")
    jobs = workflow.get("jobs", {})
    collect_job = next((job for job in jobs.values() if job.get("name") == "collect"), {})
    steps = collect_job.get("steps", [])
    
    alert_steps = [
        s for s in steps
        if s.get("name") in ["Alert on commit failure", "Alert on email failure"]
    ]
    
    for step in alert_steps:
        run_script = step.get("run", "")
        assert "curl" in run_script, f"Step '{step.get('name')}' deve usar 'curl'"

if __name__ == "__main__":
    test_checkout_no_custom_token()
    test_alert_steps_use_curl()