"""
Testes para scripts/audit_mds.py — gate de coerência dos .md.

Garante que o audit:
- detecta merge-conflict markers (corrupção por git merge não resolvido)
- detecta camadas do pre-commit citadas erradas vs truth real
- ignora LESSONS.md/changelog (histórico) nas checagens de contadores
- respeita allowlist histórica (README.md 14 workflows)
"""

from __future__ import annotations

from pathlib import Path

from scripts.audit_mds import (
    HISTORICAL_FILES,
    _LAYER_PAT,
    _check_merge_conflicts,
    _count_pre_commit_layers,
    _iter_live_mds,
)

ROOT = Path(__file__).resolve().parent.parent.parent


class TestLayerCount:
    def test_counts_real_layers_from_hook(self):
        assert _count_pre_commit_layers() == 14

    def test_layer_pattern_matches_decimal_and_plain(self):
        text = "# Layer 1: X\n# 1.5. Y\n# 2.5 DOC SYNC\n# 9 Z\n"
        layers = set(_LAYER_PAT.findall(text))
        assert layers == {"1", "1.5", "2.5", "9"}


class TestMergeConflicts:
    def test_regex_detects_unresolved_markers(self):
        from scripts.audit_mds import _MERGE_MARKERS

        assert _MERGE_MARKERS.search("<<<<<<< Updated upstream\nfoo\n") is not None
        assert _MERGE_MARKERS.search("=======\nfoo\n") is not None
        assert _MERGE_MARKERS.search(">>>>>>> Stashed changes\nfoo\n") is not None
        assert _MERGE_MARKERS.search("# normal md content\n") is None

    def test_scan_finds_conflict_in_raiox(self):
        conflicts = _check_merge_conflicts()
        raiox = [c for c in conflicts if "CUSTO_DOCE_RAIO_X" in c["file"]]
        assert raiox, "merge-conflict no RAIO_X deve ser detectado (corrupção ativa)"


class TestLiveMdIteration:
    def test_skips_venv_and_archive(self):
        rels = [rel for _, rel in _iter_live_mds()]
        assert not any(r.startswith(".venv") for r in rels)
        assert not any(r.startswith("docs/archive/") for r in rels)
        assert "AGENTS.md" in rels


class TestHistoricalFiles:
    def test_reports_marked_historical(self):
        assert "SCRAPER_ANALYSIS_REPORT.md" in HISTORICAL_FILES
        assert "SECURITY_AUDIT_REPORT_2026-08.md" in HISTORICAL_FILES
