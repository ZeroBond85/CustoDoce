"""
Tests for scripts/validate_md_timestamps.py — CI gate de timestamps.

Verifica que o validador:
1. Flagga timestamps velhos / ausentes em docs vivos (policy TIMESTAMP).
2. Respeita doc_sync_policy: IMMUTABLE (ADRs), SNAPSHOT_FROZEN e
   SNAPSHOT_DERIVED_LIVE (snapshots com data congelada) são pulados —
   o sync nunca os mantém, exigir freshness quebraria o CI a cada N dias.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from scripts.validate_md_timestamps import validate


def _write_md(root: Path, rel: str, timestamp: str | None, body: str = "conteudo") -> Path:
    """Cria .md sob root. Se timestamp é None, não escreve a linha de data."""
    content = body
    if timestamp is not None:
        content = f"> Última atualização: {timestamp} 12:00 UTC\n\n{body}"
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _ts(days_ago: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days_ago)).strftime("%Y-%m-%d")


class TestLiveDocs:
    def test_fresh_timestamp_ok(self, tmp_path):
        _write_md(tmp_path, "docs/contributing.md", _ts(1))
        assert validate(tmp_path) == []

    def test_old_timestamp_flagged(self, tmp_path):
        _write_md(tmp_path, "docs/contributing.md", _ts(40))
        issues = validate(tmp_path)
        assert len(issues) == 1
        assert "40 days old" in issues[0]

    def test_old_but_within_custom_limit_ok(self, tmp_path):
        _write_md(tmp_path, "docs/contributing.md", _ts(20))
        assert validate(tmp_path, max_age_days=30) == []

    def test_old_breaks_custom_limit(self, tmp_path):
        _write_md(tmp_path, "docs/contributing.md", _ts(20))
        issues = validate(tmp_path, max_age_days=10)
        assert len(issues) == 1

    def test_missing_timestamp_flagged(self, tmp_path):
        _write_md(tmp_path, "docs/contributing.md", None)
        issues = validate(tmp_path)
        assert len(issues) == 1
        assert "missing timestamp" in issues[0]


class TestPolicySkip:
    def test_adr_immutable_skipped(self, tmp_path):
        # ADR é IMMUTABLE — sync nunca toca, freshness não se aplica.
        _write_md(tmp_path, "docs/adr/001-architecture.md", _ts(400))
        assert validate(tmp_path) == []

    def test_snapshot_frozen_skipped(self, tmp_path, monkeypatch):
        from scripts.doc_sync_policy import DocPolicy
        from scripts.validate_md_timestamps import policy_for as _real_policy_for

        p = tmp_path / "docs/archive/foo.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            "---\ndoc_type: snapshot\nfrozen: true\n---\n\n"
            f"> Gerado em: {datetime.now(UTC).strftime('%d/%m/%Y')}\n\ndoc snapshot",
            encoding="utf-8",
        )
        # policy_for resolve _ROOT global; snapshot real do repo não existe no
        # tmp_path. Simula o resultado da policy para o rel usado pelo validador.
        monkeypatch.setattr(
            "scripts.validate_md_timestamps.policy_for",
            lambda rel: DocPolicy.SNAPSHOT_FROZEN
            if str(rel).replace("\\", "/") == "docs/archive/foo.md"
            else _real_policy_for(rel),
        )
        assert validate(tmp_path) == []

    def test_snapshot_derived_skipped(self, tmp_path, monkeypatch):
        from scripts.doc_sync_policy import DocPolicy
        from scripts.validate_md_timestamps import policy_for as _real_policy_for

        p = tmp_path / "docs/archive/resumido.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            "---\ndoc_type: snapshot\nslug: raio-x_custo_doce_resumido\n---\n\nderived",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "scripts.validate_md_timestamps.policy_for",
            lambda rel: DocPolicy.SNAPSHOT_DERIVED_LIVE
            if str(rel).replace("\\", "/") == "docs/archive/resumido.md"
            else _real_policy_for(rel),
        )
        assert validate(tmp_path) == []

    def test_archived_live_doc_still_flagged(self, tmp_path):
        # archive sem frontmatter vira TIMESTAMP default → ainda validado.
        _write_md(tmp_path, "docs/archive/outro.md", _ts(400))
        issues = validate(tmp_path)
        assert len(issues) == 1
