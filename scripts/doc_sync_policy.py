"""
Doc Sync Policy — single source of truth for per-document update rules.

Defines 8 buckets, each with its own contract for how the doc is updated
over time. Every other sync tool (sync_docs.py, sync_md_v2.py,
sync_md_catchup.py, pre-push hooks) reads from here.

Usage:
    from scripts.doc_sync_policy import policy_for, DocPolicy

    p = policy_for("docs/archive/CUSTO_DOCE_RAIO_X.md")
    if p == DocPolicy.SNAPSHOT_REFERENCE_LIVE:
        ...
"""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

from scripts.doc_utils import read_frontmatter  # noqa: E402


class DocPolicy(str, Enum):
    """Update contract for a single .md document.

    A política é resolvida via:
      1. frontmatter (mais forte): doc_type=frozen + slug
      2. path-prefix fallback
    """
    LIVE = "live"                              # counters/sections tied to truth
    TIMESTAMP = "timestamp"                    # só freshness
    TIMESTAMP_PROTECTED = "timestamp_protected"  # timestamp + placeholder guard
    AUTO_GENERATED = "auto_generated"          # gerado por tooling (AST)
    IMMUTABLE = "immutable"                    # nunca tocado por sync
    SNAPSHOT_FROZEN = "snapshot_frozen"        # audit pontual com data fixada
    SNAPSHOT_REFERENCE_LIVE = "snapshot_reference_live"  # Raio-X (incremental)
    SNAPSHOT_DERIVED_LIVE = "snapshot_derived_live"      # Resumido (derivado)


# Slugs documentados no escopo atual
_REFERENCE_LIVE_SLUGS = {
    "custo_doce_raio_x",
}
_DERIVED_LIVE_SLUGS = {
    "raio-x_custo_doce_resumido",
}

# Patterns no corpo que indicam audit pontual com data congelada
_FROZEN_BODY_MARKPAT = re.compile(r"^\s*>\s*Gerado em: \d{2}/\d{2}/\d{4}", re.MULTILINE)


def _looks_frozen(fm: dict, body: str) -> bool:
    """Heurística que confirma doc como SNAPSHOT_FROZEN."""
    if fm.get("frozen") is True:
        return True
    if fm.get("doc_type") == "snapshot" and _FROZEN_BODY_MARKPAT.search(body):
        return True
    return False


def policy_for(file_path: str | Path) -> DocPolicy:
    """Resolve the policy for a given file path.

    Priority:
    1. frontmatter (for *.md in docs/archive/: snapshot + frozen markers OR slug match)
    2. path-prefix
    3. default: TIMESTAMP
    """
    rel = str(file_path)
    if isinstance(file_path, Path):
        try:
            rel = str(file_path.relative_to(_ROOT))
        except ValueError:
            rel = str(file_path)

    rel = rel.replace("\\", "/")

    # 1) frontmatter inspection (only archive docs have frontmatter today)
    if rel.startswith("docs/archive/"):
        abs_path = _ROOT / rel
        fm, body = read_frontmatter(abs_path)
        if fm:
            if _looks_frozen(fm, body):
                return DocPolicy.SNAPSHOT_FROZEN
            slug = fm.get("slug", "")
            if slug in _REFERENCE_LIVE_SLUGS:
                return DocPolicy.SNAPSHOT_REFERENCE_LIVE
            if slug in _DERIVED_LIVE_SLUGS:
                return DocPolicy.SNAPSHOT_DERIVED_LIVE

    # 2) path-prefix rules (more specific first)
    if rel.startswith("docs/adr/"):
        return DocPolicy.IMMUTABLE
    if rel.startswith("docs/api/"):
        return DocPolicy.AUTO_GENERATED
    if rel == "docs/skills.md":
        return DocPolicy.AUTO_GENERATED
    if rel == "docs/ROLLBACK_PROD.md":
        return DocPolicy.TIMESTAMP_PROTECTED
    if rel in {
        "AGENTS.md",
        "README.md",
        "REGRAS.md",
        "LESSONS.md",
        "docs/changelog.md",
    }:
        return DocPolicy.LIVE

    # 3) default
    return DocPolicy.TIMESTAMP


def is_inviting_original_dev(path: str | Path) -> bool:
    """Indica que arquivos dessa policy não devem ser tocados por sync."""
    p = policy_for(path)
    return p in (DocPolicy.IMMUTABLE, DocPolicy.SNAPSHOT_FROZEN)


__all__ = [
    "DocPolicy",
    "policy_for",
    "is_inviting_original_dev",
]
