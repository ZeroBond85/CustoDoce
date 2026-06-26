#!/usr/bin/env python3
"""
Gera relatório HTML consolidado da regressão full.
Lê output do pytest --json-report, screenshots, e gera HTML.
"""
import json
from datetime import datetime
from pathlib import Path

REPORT_DIR = Path("data")
SCREENSHOT_DIR = Path("data/regression_screenshots")
REPORT_FILE = REPORT_DIR / f"regression_report_{datetime.now().strftime('%Y-%m-%d')}.html"
HISTORY_FILE = REPORT_DIR / "regression_history.json"


def load_pytest_report():
    path = Path(".pytest_results.json")
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def get_screenshots():
    if not SCREENSHOT_DIR.exists():
        return []
    return sorted(SCREENSHOT_DIR.glob("*.png"))


def build_html(results: dict, screenshots: list, history: list) -> str:
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    summary = results.get("summary", {})
    total = summary.get("total", 0)
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    skipped = summary.get("skipped", 0)
    errors = summary.get("errors", 0)
    duration = results.get("duration", 0)

    # Build phase summary
    phases = [
        ("A - Corrigir Testes", "test_new_features.py"),
        ("B - AI Feature Flags", "code changes"),
        ("C - Optimize scrape.yml", "scrape.yml"),
        ("D1 - Playwright 16x3", "e2e_real.py"),
        ("D2 - DB Real", "TestDBReal"),
        ("D3 - Pipeline E2E", "TestPipelineReal"),
        ("D4 - Scrapers Reais", "TestScrapersReal"),
        ("D5 - Telegram Bot", "TestTelegramReal"),
        ("D7-D9 - Extra DB", "test_db_real.py"),
        ("E1 - Workflows", "GH Actions"),
        ("E2 - Alertas", "test_telegram_real.py"),
    ]

    # Determine pass/fail per phase from history
    phase_rows = ""
    for phase_name, phase_keyword in phases:
        is_ok = True
        count = 0
        for test in results.get("tests", []):
            nodeid = test.get("nodeid", "")
            if phase_keyword in nodeid:
                count += 1
                if test.get("outcome") not in ("passed", "skipped"):
                    is_ok = False
        if count == 0:
            # Check history
            for h in history:
                if h.get("phase") == phase_name:
                    is_ok = h.get("passed", 0) > 0 and h.get("failed", 0) == 0
                    count = 1
        badge = "badge-ok" if is_ok else "badge-err"
        label = "OK" if is_ok else "FALHA"
        phase_rows += f"""
        <tr>
            <td>{phase_name}</td>
            <td><span class="badge {badge}">{label}</span></td>
            <td>{count}</td>
        </tr>"""

    # Screenshots
    screenshot_html = ""
    for s in screenshots[:10]:
        rel = s.relative_to(Path.cwd())
        screenshot_html += f'<li><img src="../../{rel}" style="max-width:600px;border:1px solid #ddd;"></li>'
    if not screenshot_html:
        screenshot_html = "<li>Sem screenshots de erro</li>"

    # Compare with last run
    prev = history[-1] if history else {}
    prev_passed = prev.get("passed", 0)
    prev_failed = prev.get("failed", 0)
    delta_passed = passed - prev_passed
    delta_failed = failed - prev_failed

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Regressão Full CustoDoce</title>
<style>
body {{font-family:Arial,sans-serif;background:#fafafa;margin:0;padding:20px;color:#333}}
h1 {{color:#F59E42}} h2 {{color:#E91E8C}}
.card {{background:#fff;border-radius:8px;padding:20px;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,.1)}}
.badge {{display:inline-block;padding:4px 10px;border-radius:4px;font-size:12px;font-weight:bold}}
.badge-ok {{background:#16A34A;color:#fff}} .badge-err {{background:#DC2626;color:#fff}} .badge-warn {{background:#F59E42;color:#fff}}
table {{width:100%;border-collapse:collapse}}
th,td {{text-align:left;padding:8px;border-bottom:1px solid #ddd}}
th {{background:#f5f5f5}}
.delta-up {{color:#16A34A}} .delta-down {{color:#DC2626}}
img {{max-width:100%;border-radius:4px}}
pre {{background:#f5f5f5;padding:10px;border-radius:4px;overflow:auto}}
</style>
</head>
<body>
<div class="card">
    <h1>Regressão Full CustoDoce</h1>
    <p><strong>Data:</strong> {now}</p>
    <p><strong>Total:</strong> {total} | <strong>Passed:</strong> {passed} | <strong>Failed:</strong> {failed} | <strong>Skipped:</strong> {skipped} | <strong>Errors:</strong> {errors}</p>
    <p><strong>Duração:</strong> {duration:.1f}s</p>
    <p><strong>vs última execução:</strong> <span class="delta-up">+{delta_passed}</span> passed / <span class="delta-down">+{delta_failed}</span> failed</p>
</div>

<div class="card">
    <h2>Resumo por Fase</h2>
    <table>
        <tr><th>Fase</th><th>Status</th><th>Testes</th></tr>
        {phase_rows}
    </table>
</div>

<div class="card">
    <h2>Screenshots de Erro</h2>
    <ul>{screenshot_html}</ul>
</div>

<div class="card">
    <h2>Timing por Teste</h2>
    <pre>{json.dumps({(t.get("nodeid","").split("::")[-1] if "::" in t.get("nodeid","") else t.get("nodeid","")): f"{t.get('duration',0):.2f}s" for t in results.get("tests", []) if t.get("duration",0) > 0.5}, indent=2, ensure_ascii=False)[:2000]}</pre>
</div>

<hr>
<p style="text-align:center;color:#888;font-size:12px;">Gerado em {now} • CustoDoce</p>
</body>
</html>"""
    return html


def main():
    results = load_pytest_report()
    screenshots = get_screenshots()
    summary = results.get("summary", {})
    history = []
    if HISTORY_FILE.exists():
        try:
            history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            history = []
    if not isinstance(history, list):
        history = []
    history.append({
        "date": datetime.now().isoformat(),
        "passed": summary.get("passed", 0),
        "failed": summary.get("failed", 0),
        "total": summary.get("total", 0),
        "duration": results.get("duration", 0),
    })
    history = history[-20:]
    HISTORY_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")
    html = build_html(results, screenshots, history)
    REPORT_FILE.write_text(html, encoding="utf-8")
    print(f"Relatório gerado: {REPORT_FILE}")


if __name__ == "__main__":
    main()
