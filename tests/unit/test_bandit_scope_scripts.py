"""Unit tests para PR-02 — bandit cobre scripts/ e zero findings Medium/High.

O ci.yml excluía scripts/ do scan bandit (L98 legado) e scripts/ tinha
10 findings (3 High B602 shell=True, B113 sem timeout, B615 HF sem revision,
B608 SQL dinâmico, B310 urlopen). Estes testes travam a política.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"


class TestBanditScope:
    def test_ci_bandit_includes_scripts(self):
        content = CI_YML.read_text(encoding="utf-8")
        matches = [ln.strip() for ln in content.splitlines() if "bandit -r" in ln]
        assert matches, "steps bandit ausentes no ci.yml"
        # Passo legado estrito (low+) para os diretórios de produção.
        assert any("admin/" in ln and "-ll" not in ln for ln in matches), matches
        # scripts/ entra com gate calibrado medium+ (LOW de dev-tools não bloqueia).
        script_steps = [ln for ln in matches if "scripts/" in ln and "admin/" not in ln]
        assert script_steps and all("-ll" in ln for ln in script_steps), matches


class TestShellTrueEliminated:
    def test_no_shell_true_in_scripts(self):
        offenders = []
        for py in (REPO_ROOT / "scripts").rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            if re.search(r"shell\s*=\s*True", text):
                offenders.append(py.name)
        assert not offenders, f"shell=True proibido em scripts/: {offenders}"

    def test_subprocess_uses_token_lists(self):
        for name in ("ci_local.py", "validation_utils.py"):
            text = (REPO_ROOT / "scripts" / name).read_text(encoding="utf-8")
            assert "shlex.split" in text, f"{name} deve tokenizar comandos"


class TestDynamicSqlEliminated:
    def test_validate_migrations_no_insert_fstring(self):
        text = (REPO_ROOT / "scripts" / "validate_migrations.py").read_text(encoding="utf-8")
        assert "INSERT INTO" not in text
        assert "noqa: S608" not in text
        assert 'table("schema_migrations").upsert' in text

    def test_restore_from_json_no_dynamic_sql(self):
        text = (REPO_ROOT / "scripts" / "restore_from_json.py").read_text(encoding="utf-8")
        assert "SELECT COUNT" not in text
        assert 'select("*", count="exact")' in text


class TestNetworkHardening:
    def test_download_latest_release_has_timeouts(self):
        text = (REPO_ROOT / "scripts" / "download_latest_release.py").read_text(encoding="utf-8")
        gets = re.findall(r"requests\.get\([^)]*\)", text)
        assert len(gets) == 3, gets
        for g in gets:
            assert "timeout=" in g, g

    def test_export_onnx_pins_revision(self):
        text = (REPO_ROOT / "scripts" / "export_onnx.py").read_text(encoding="utf-8")
        assert re.search(r'MODEL_REVISION\s*=\s*"[0-9a-f]{40}"', text), "revision deve ser commit hash"
        assert text.count("revision=MODEL_REVISION") == 2

    def test_streamlit_check_uses_httpx(self):
        text = (REPO_ROOT / "scripts" / "validate_streamlit_cloud.py").read_text(encoding="utf-8")
        assert "urllib" not in text
        assert "import httpx" in text
