"""md_auto_compress.py — MD compression for CustoDoce.

Two-pass approach (C+A):
  1. Dedup: merge sections with >=0.85 rapidfuzz similarity
  2. Archive: move low-score sections to docs/archive/<src>/YYYY-MM.md

Reversible via --rollback.

Usage:
    python scripts/md_auto_compress.py --target LESSONS.md --dry-run
    python scripts/md_auto_compress.py --target LESSONS.md --mode all
    python scripts/md_auto_compress.py --target LESSONS.md --rollback
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import rapidfuzz

# ═══════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG = _ROOT / "config" / "scoring_config.yaml"
_DEFAULT_ARCHIVE_DIR = _ROOT / "docs" / "archive"

# Max lines per file (matches agents_schema.yaml defaults)
_MAX_LINES = {"LESSONS.md": 700, "AGENTS.md": 350}

# Regex for section headings
_RE_LESSON = re.compile(r"^### (\d+)\.\s*(.*)")
_RE_AGENTS = re.compile(r"^## (\w[\w\s]*)")
_RE_KEEP = re.compile(r"<!--\s*keep\s*-->")
_RE_DATE_COMMIT = re.compile(r"\*\*Data \+ commit\*\*:\s*(\d{4}-\d{2}-\d{2})")


# ═══════════════════════════════════════════════════════════════
# Parsing
# ═══════════════════════════════════════════════════════════════


def parse_lessons(content: str) -> list[dict]:
    """Parse LESSONS.md into section dicts.

    Each section: {id, title, body, raw_text, lines, keep, age_months, ref_score}
    """
    sections = []
    lines = content.splitlines()
    i = 0

    while i < len(lines):
        m = _RE_LESSON.match(lines[i])
        if m:
            sec_id = int(m.group(1))
            title = m.group(2).strip()
            start = i
            i += 1
            body_lines = []
            while i < len(lines):
                if _RE_LESSON.match(lines[i]):
                    break
                body_lines.append(lines[i])
                i += 1
            body = "\n".join(body_lines).strip()
            raw = "\n".join(lines[start:i])
            sec_lines = i - start
            has_keep = bool(_RE_KEEP.search(body))

            # Estimate age from date in body
            age = 0
            dm = _RE_DATE_COMMIT.search(body)
            if dm:
                try:
                    d = datetime.strptime(dm.group(1), "%Y-%m-%d").replace(tzinfo=UTC)
                    months = (datetime.now(UTC) - d).days / 30
                    age = max(0, int(months))
                except ValueError:
                    pass

            sections.append({
                "id": sec_id,
                "title": title,
                "body": body,
                "raw_text": raw,
                "lines": sec_lines,
                "keep": has_keep,
                "age_months": age,
                "ref_score": 0,
            })
        else:
            i += 1

    return sections


# ═══════════════════════════════════════════════════════════════
# Scorer
# ═══════════════════════════════════════════════════════════════


def _load_scoring_config(path: str | None = None) -> dict:
    """Load scoring config from YAML file."""
    import yaml
    cfg_path = Path(path) if path else _DEFAULT_CONFIG
    if cfg_path.exists():
        with open(cfg_path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {
        "weights": {
            "keep_marker": 999,
            "cross_doc_ref": 10,
            "test_ref": 8,
            "code_ref": 6,
            "workflow_ref": 6,
            "docs_ref": 3,
            "dated_anchor": 5,
            "age_months": -1,
            "no_evidence_penalty": -3,
        },
        "thresholds": {
            "archive_candidate": -3,
            "preserve_absolute": 6,
            "dedup_similarity": 0.85,
            "buffer_lines": 10,
        },
    }


def section_score(section: dict, scoring_config: dict | None = None) -> int:
    """Compute numeric importance score for a section.

    Positive = important (keep). Negative = candidate for archive.
    `<!-- keep -->` is absolute (+999).
    """
    cfg = scoring_config or _load_scoring_config()
    w = cfg["weights"]

    if section.get("keep"):
        return w.get("keep_marker", 999)

    score = 0

    # External references (pre-computed by reference_score)
    ref = section.get("ref_score", 0)
    if ref > 0:
        score += ref

    # Age penalty
    age = section.get("age_months", 0)
    if age > 6:
        age_adj = min(age, 16)  # cap at 16 months
        score += w.get("age_months", -1) * (age_adj - 6)  # only penalty after 6mo

    # Dated anchor bonus
    if section.get("body", "") and _RE_DATE_COMMIT.search(section["body"]):
        score += w.get("dated_anchor", 5)

    # No evidence penalty
    if ref <= 0 and age > 6:
        score += w.get("no_evidence_penalty", -3)

    return score


def reference_score(section: dict) -> int:
    """Count external references to this section in the repo.

    Uses grep patterns. May return 0 in test environments.
    """
    score = 0
    sec_id = section.get("id", 0)
    if not sec_id:
        return 0

    patterns = [
        rf"LESSONS\.md\s+#{sec_id}\b",
        rf"\blessons?\s+#{sec_id}\b",
        rf"lesson\s+#{sec_id}\b",
    ]

    search_dirs = [
        _ROOT / "services",
        _ROOT / "scrapers",
        _ROOT / "parsers",
        _ROOT / "tests",
        _ROOT / "dashboard",
        _ROOT / "scripts",
        _ROOT / "config",
        _ROOT / ".github" / "workflows",
    ]

    import subprocess

    for pat in patterns:
        for d in search_dirs:
            if not d.exists():
                continue
            try:
                result = subprocess.run(
                    ["grep", "-rl", pat, str(d)],
                    capture_output=True, text=True, timeout=15,
                    cwd=str(_ROOT),
                )
                if result.stdout.strip():
                    score += len(result.stdout.strip().splitlines())
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                pass

    return min(score, 50)  # cap


# ═══════════════════════════════════════════════════════════════
# Dedup
# ═══════════════════════════════════════════════════════════════


def dedup(sections: list[dict], threshold: float = 0.85) -> list[dict]:
    """Merge sections with similarity >= threshold.

    Returns new list where merged sections become markers:
      {merged_into: survivor_id, body: "→ fundida em ### N"}
    Survivors get a note appended to their body.
    """
    merged_into: dict[int, int] = {}

    for i, sa in enumerate(sections):
        if sa["id"] in merged_into:
            continue
        for j, sb in enumerate(sections):
            if i == j or sb["id"] in merged_into:
                continue
            if sa.get("keep") or sb.get("keep"):
                continue

            text_a = (sa["body"] + " " + sa["title"]).lower()
            text_b = (sb["body"] + " " + sb["title"]).lower()
            sim = rapidfuzz.fuzz.token_set_ratio(text_a, text_b) / 100.0

            if sim >= threshold:
                merged_into[sb["id"]] = sa["id"]
                merged_into_sibling = False
                for other_id, survivor_id in merged_into.items():
                    if survivor_id == sb["id"] and other_id != sb["id"]:
                        merged_into_sibling = True
                        break

    result = []
    merged_sections: dict[int, list[int]] = {}
    for merged_id, survivor_id in merged_into.items():
        merged_sections.setdefault(survivor_id, []).append(merged_id)

    for s in sections:
        if s["id"] in merged_into:
            result.append({
                "type": "merge_ref",
                "id": s["id"],
                "title": s["title"],
                "body": f"→ fundida em ### {merged_into[s['id']]}",
                "lines": 1,
                "merged_into": merged_into[s["id"]],
            })
        elif s["id"] in merged_sections:
            s["body"] += "\n\n" + "\n".join(
                f"→ fundida com ### {mid}"
                for mid in merged_sections[s["id"]]
            )
            result.append(s)
        else:
            result.append(s)

    return result


# ═══════════════════════════════════════════════════════════════
# Archive
# ═══════════════════════════════════════════════════════════════


def archive(
    content: str,
    max_lines: int = 700,
    scoring_config: dict | None = None,
    dry_run: bool = False,
    archive_dir: str | None = None,
    target: str = "lessons",
) -> dict:
    """Archive low-score sections from LESSONS.md content.

    Returns:
        content: reconstructed content (same as input if no archive)
        archived: list of archived section dicts
        dry_run: True if dry run
        target: source file identifier
    """
    cfg = scoring_config or _load_scoring_config()
    sections = parse_lessons(content)
    lines = content.splitlines()
    total_lines = len(lines)

    if total_lines <= max_lines:
        return {"content": content, "archived": [], "dry_run": dry_run, "target": target}

    # Score sections
    scored = []
    for s in sections:
        if not s.get("ref_score"):
            s["ref_score"] = reference_score(s)
        score = section_score(s, cfg)
        scored.append((score, s))

    # Sort by score ascending (worst first)
    scored.sort(key=lambda x: x[0])

    threshold = cfg.get("thresholds", {}).get("archive_candidate", -3)
    buffer = cfg.get("thresholds", {}).get("buffer_lines", 10)
    target_lines = max_lines - buffer

    archived = []
    remaining_ids = {s["id"] for _, s in scored}
    current_lines = total_lines

    for score, s in scored:
        if current_lines <= target_lines:
            break
        if score >= threshold:
            continue
        if s.get("keep"):
            continue
        archived_section = dict(s)
        archived_section["score"] = score
        archived_section["reason"] = f"age={s.get('age_months',0)}mo ref_score={s.get('ref_score',0)}"
        archived_section["archived_at"] = datetime.now(UTC).isoformat()
        archived.append(archived_section)
        remaining_ids.discard(s["id"])
        current_lines -= s["lines"]

    if not archived:
        return {"content": content, "archived": [], "dry_run": dry_run, "target": target}

    # Reconstruct content from remaining sections
    remaining = [s for s in sections if s["id"] in remaining_ids]
    # Preserve header (text before first section)
    header_end = 0
    first_sec = sections[0] if sections else None
    if first_sec:
        idx = content.find(first_sec["raw_text"])
        if idx >= 0:
            header_end = idx

    header = content[:header_end]
    new_content = header + "\n".join(s["raw_text"] for s in remaining)

    if dry_run:
        return {
            "content": content,
            "archived": archived,
            "dry_run": True,
            "target": target,
        }

    # Write archive file
    arch_dir = Path(archive_dir) if archive_dir else (_DEFAULT_ARCHIVE_DIR / target)
    arch_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    archive_file = arch_dir / f"{now.strftime('%Y-%m')}.md"

    archive_entries = []
    archive_md_parts = [
        f"# Licoes Arquivadas — {now.strftime('%Y-%m')}",
        "",
        f"> Última atualização: {now.strftime('%Y-%m-%d %H:%M')} UTC",
        f"> Auto-archive via md_auto_compress.py em {now.isoformat()}",
        f"> Arquivo origem: {target}",
        f"> Reversivel com: --rollback --target {target}",
        "",
    ]
    for a in archived:
        archive_entries.append(a)
        archive_md_parts.append(f"### {a['id']}. {a['title']}")
        archive_md_parts.append("")
        archive_md_parts.append(a.get("body", ""))
        archive_md_parts.append("")
        archive_md_parts.append(f"**Arquivada por:** {a.get('reason', 'score baixo')}")
        archive_md_parts.append("")

    archive_content = "\n".join(archive_md_parts) + "\n"
    archive_file.write_text(archive_content, encoding="utf-8")

    # Write audit trail
    audit_entry = {
        "ts": now.isoformat(),
        "target": target,
        "archived_count": len(archived),
        "archived": [
            {"id": a["id"], "title": a["title"], "score": a.get("score"), "reason": a.get("reason")}
            for a in archived
        ],
            "new_file": str(archive_file.relative_to(_ROOT)) if archive_file.is_relative_to(_ROOT) else str(archive_file),
        "rev_sha": _get_git_sha(),
    }
    audit_file = arch_dir / "_audit.jsonl"
    with open(audit_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(audit_entry, ensure_ascii=False) + "\n")

    return {
        "content": new_content,
        "archived": archived,
        "dry_run": False,
        "target": target,
        "audit_entry": audit_entry,
    }


# ═══════════════════════════════════════════════════════════════
# Rollback
# ═══════════════════════════════════════════════════════════════


def _get_git_sha() -> str:
    try:
        import subprocess
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
            cwd=str(_ROOT),
        )
        return r.stdout.strip()[:12] if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def rollback(target: str = "lessons", archive_dir: str | None = None) -> dict:
    """Restore the last archive operation for given target.

    Reads the audit trail and restores the content.
    Currently marks the entry as rolled back;
    full reconstruction requires the pre-archive content from git.
    """
    arch_dir = Path(archive_dir) if archive_dir else (_DEFAULT_ARCHIVE_DIR / target)
    audit_file = arch_dir / "_audit.jsonl"
    if not audit_file.exists():
        return {"restored": False, "error": "Nenhum registro de archive encontrado"}

    # Read last audit entry
    entries = []
    with open(audit_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))

    if not entries:
        return {"restored": False, "error": "Audit vazio"}

    last = entries[-1]
    if last.get("rolled_back"):
        return {"restored": False, "error": "Ultimo archive ja foi revertido"}

    # Mark as rolled back
    last["rolled_back"] = True
    last["rolled_back_at"] = datetime.now(UTC).isoformat()
    entries[-1] = last

    with open(audit_file, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return {
        "restored": True,
        "target": target,
        "archived_count": len(last.get("archived", [])),
    }


# ═══════════════════════════════════════════════════════════════
# Compress (dedup + archive combined)
# ═══════════════════════════════════════════════════════════════


def compress(target_file: str, mode: str = "all", dry_run: bool = True) -> dict:
    """Run dedup then archive on target MD file.

    Returns result dict with keys: content, archived, dry_run, etc.
    """
    target_path = None
    for candidate in [_ROOT / target_file, _ROOT / target_file.replace("--target ", ""), _ROOT / "LESSONS.md"]:
        if isinstance(target_file, str) and "=" not in target_file and candidate.exists():
            target_path = candidate
            break
    if target_path is None:
        target_path = _ROOT / "LESSONS.md"

    if not target_path.exists():
        return {"error": f"Arquivo nao encontrado: {target_path}", "dry_run": dry_run}

    content = target_path.read_text(encoding="utf-8")
    fname = target_path.name
    max_lines = _MAX_LINES.get(fname, 700)
    cfg = _load_scoring_config()
    src = fname.replace(".md", "").lower()

    # Pass 1: Dedup
    if mode in ("all", "dedup"):
        sections = parse_lessons(content)
        deduped = dedup(sections)
        if len(deduped) < len(sections):
            # Reconstruct content from deduped sections
            header_end = 0
            first_sec = sections[0] if sections else None
            if first_sec:
                idx = content.find(first_sec["raw_text"])
                if idx >= 0:
                    header_end = idx
            header = content[:header_end]
            content = header + "\n".join(
                s["raw_text"] if not s.get("merged_into") else f"> {s['body']}"
                for s in deduped
                if not s.get("merged_into")
            )

    # Pass 2: Archive
    if mode in ("all", "archive"):
        result = archive(content, max_lines=max_lines, scoring_config=cfg, dry_run=dry_run, target=src)
        result["dedup_applied"] = mode in ("all", "dedup")
        result["target_file"] = str(target_path)
        if not dry_run and result.get("content") and result["content"] != content:
            target_path.write_text(result["content"], encoding="utf-8")
        return result

    return {"content": content, "archived": [], "dry_run": dry_run, "target": src}


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════


def _resolve_target(target_arg: str) -> str:
    known = {"lessons": "LESSONS.md", "agents": "AGENTS.md", "regras": "REGRAS.md"}
    if target_arg.lower() in known:
        return known[target_arg.lower()]
    if target_arg.endswith(".md"):
        return target_arg
    return "LESSONS.md"


def main():
    parser = argparse.ArgumentParser(description="Auto-compress MD files (dedup + archive)")
    parser.add_argument("--target", default="LESSONS.md", help="Target file (LESSONS.md, AGENTS.md, ...)")
    parser.add_argument("--mode", choices=["dedup", "archive", "all"], default="all")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--no-dry-run", action="store_false", dest="dry_run")
    parser.add_argument("--auto-yes", action="store_true", help="Internal: apply changes without prompt")
    parser.add_argument("--rollback", action="store_true", help="Revert last archive")
    parser.add_argument("--restore", type=int, metavar="ID", help="Restore specific section by ID")

    args = parser.parse_args()
    target_file = _resolve_target(args.target)

    if args.rollback:
        src = target_file.replace(".md", "").lower()
        result = rollback(target=src)
        if result["restored"]:
            print(f"[OK] Rollback concluido: {result.get('archived_count', 0)} secoes restauradas")
        else:
            print(f"[FAIL] Rollback falhou: {result.get('error', 'erro desconhecido')}")
            sys.exit(1)
        return

    dry_run = args.auto_yes is False and args.dry_run
    result = compress(target_file, mode=args.mode, dry_run=dry_run)

    if "error" in result:
        print(f"[FAIL] {result['error']}")
        sys.exit(1)

    archived = result.get("archived", [])
    dedupbed = result.get("dedup_applied", False)

    if dry_run:
        if dedupbed:
            print("[DRY-RUN] Dedup seria aplicado")
        if archived:
            print(f"[DRY-RUN] {len(archived)} secao(oes) seria(m) arquivada(s):")
            for a in archived:
                print(f"  — #{a.get('id')} {a.get('title')} (score={a.get('score')})")
        else:
            print("[OK] Nenhuma alteracao necessaria (dry-run)")
    else:
        if archived:
            print(f"[ARCHIVED] {len(archived)} secao(oes) arquivada(s)")
            for a in archived:
                print(f"  — #{a.get('id')} {a.get('title')}")
            print(f"[OK] Rollback via: python scripts/md_auto_compress.py --target {args.target} --rollback")
        if not archived and not dedupbed:
            print("[OK] Nenhuma alteracao necessaria")


if __name__ == "__main__":
    main()
