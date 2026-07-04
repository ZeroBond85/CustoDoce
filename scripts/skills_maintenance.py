#!/usr/bin/env python3
"""
Skills Maintenance Script for CustoDoce

Check, update, backup, and validate OpenCode skills.
"""

import argparse
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SKILLS_DIR = PROJECT_ROOT / ".opencode" / "skills"
GLOBAL_SKILLS_DIR = Path.home() / ".config" / "opencode" / "skills"
BACKUP_DIR = PROJECT_ROOT / "data" / "skills_backup"

APPROVED_SKILLS = [
    # Vibe coding
    "project-context-primer",
    "code-review",
    "github",
    "dependency-audit",
    "knowledge-base-update",
    "brainstorming",
    "writing-plans",
    "architecture-review",
    "test-driven-execution",
    "prompt-enhancer",
    "documentation-sync",
    "incident-response",
    # CustoDoce core
    "web-scraper",
    "price-normalizer",
    "llm-integration",
    "self-healing",
    "brand-extractor",
    # Streamlit UI
    "streamlit-theming",
    "streamlit-components",
    "streamlit-responsive",
    "streamlit",
    # Global overlays
    "api-design",
    "docs-writer",
    "github-actions",
    "project-doc-sync",
    "sql-optimizer",
    "telegram-bot",
    "test-total-runner",
    # External (installed)
    "frontend-design",
    "theme-factory",
    "accessibility",
    "design-md",
    # Maintenance
    "skills-maintenance",
]

SKILL_CATEGORIES: dict[str, list[str]] = {
    "Vibe Coding": [
        "project-context-primer", "code-review", "github", "dependency-audit",
        "knowledge-base-update", "brainstorming", "writing-plans",
        "architecture-review", "test-driven-execution", "prompt-enhancer",
        "documentation-sync", "incident-response",
    ],
    "CustoDoce Core": [
        "web-scraper", "price-normalizer", "llm-integration",
        "self-healing", "brand-extractor",
    ],
    "Streamlit UI": [
        "streamlit", "streamlit-theming", "streamlit-components",
        "streamlit-responsive", "accessibility", "design-md",
    ],
    "Overlay Global": [
        "api-design", "docs-writer", "github-actions",
        "project-doc-sync", "sql-optimizer", "telegram-bot", "test-total-runner",
    ],
    "Externas (não adotadas)": [
        "frontend-design", "theme-factory",
    ],
    "Ops": [
        "skills-maintenance",
    ],
}


def skill_to_category(skill_name: str) -> str:
    """Auto-deriva categoria de uma skill."""
    for cat, skills in SKILL_CATEGORIES.items():
        if skill_name in skills:
            return cat
    return "Sem categoria"


def check_skills():
    """Check status of all installed skills."""
    print("=== Skills Status ===")
    print(f"SKILLS_DIR: {SKILLS_DIR}")
    print()

    if not SKILLS_DIR.exists():
        print(f"[ERROR] Skills directory not found: {SKILLS_DIR}")
        return 1

    skills = [d for d in SKILLS_DIR.iterdir() if d.is_dir()]
    print(f"TOTAL: {len(skills)} skills\n")

    warnings = 0
    now = datetime.now()
    stale_threshold = timedelta(days=30)

    for skill in sorted(skills):
        skill_name = skill.name
        skill_file = skill / "SKILL.md"

        if not skill_file.exists():
            print(f"[ERROR] {skill_name}: SKILL.md not found")
            continue

        last_modified = datetime.fromtimestamp(skill_file.stat().st_mtime)
        age = now - last_modified

        if age > stale_threshold:
            print(f"[WARN] {skill_name} ({last_modified.strftime('%d/%m/%Y')}) - {age.days} days old")
            warnings += 1
        else:
            print(f"[OK] {skill_name} ({last_modified.strftime('%d/%m/%Y')})")

        if skill_name not in APPROVED_SKILLS:
            print(f"      [INFO] Not in approved list")

    print()
    if warnings > 0:
        print(f"[WARN] {warnings} skills outdated (>30 days)")
        return 1
    return 0


def backup_skills():
    """Backup skills before update."""
    print("=== Skills Backup ===")

    if not SKILLS_DIR.exists():
        print(f"[ERROR] Skills directory not found")
        return 1

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"skills_{timestamp}"

    print(f"Backing up to: {backup_path}")
    shutil.copytree(SKILLS_DIR, backup_path)

    print(f"[OK] Backup created")

    # Keep last 5 backups
    backups = sorted(BACKUP_DIR.glob("skills_*"))
    while len(backups) > 5:
        oldest = backups.pop(0)
        print(f"[CLEAN] Removing old backup: {oldest.name}")
        shutil.rmtree(oldest)

    return 0


def validate_skills():
    """Validate SKILL.md frontmatter."""
    print("=== Skills Validation ===")

    errors = 0

    for skill_dir in SKILLS_DIR.iterdir():
        if not skill_dir.is_dir():
            continue

        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            print(f"[ERROR] {skill_dir.name}: SKILL.md not found")
            errors += 1
            continue

        content = skill_file.read_text(encoding="utf-8")

        # Check frontmatter
        if not content.startswith("---"):
            print(f"[ERROR] {skill_dir.name}: Missing frontmatter")
            errors += 1
            continue

        # Parse frontmatter
        try:
            lines = content.split("---")[1].strip().split("\n")
            has_name = any("name:" in line for line in lines)
            has_desc = any("description:" in line for line in lines)

            if not has_name:
                print(f"[ERROR] {skill_dir.name}: Missing 'name' in frontmatter")
                errors += 1
            if not has_desc:
                print(f"[ERROR] {skill_dir.name}: Missing 'description' in frontmatter")
                errors += 1
        except Exception as e:
            print(f"[ERROR] {skill_dir.name}: Parse error - {e}")
            errors += 1

    if errors == 0:
        print(f"[OK] All {len(list(SKILLS_DIR.iterdir()))} skills valid")
    else:
        print(f"[ERROR] {errors} validation errors")

    return 1 if errors > 0 else 0


def list_skills():
    """List all installed skills."""
    print("=== Installed Skills ===\n")

    skills = sorted(SKILLS_DIR.iterdir())
    for skill in skills:
        if not skill.is_dir():
            continue
        skill_file = skill / "SKILL.md"
        if skill_file.exists():
            print(f"  - {skill.name}")
        else:
            print(f"  - {skill.name} [NO SKILL.md]")

    print(f"\nTotal: {len([s for s in skills if s.is_dir()])} skills")


def main():
    parser = argparse.ArgumentParser(description="Skills Maintenance for CustoDoce")
    parser.add_argument("--check", action="store_true", help="Check skills status")
    parser.add_argument("--backup", action="store_true", help="Backup skills")
    parser.add_argument("--validate", action="store_true", help="Validate skills")
    parser.add_argument("--list", action="store_true", help="List installed skills")
    parser.add_argument("--full", action="store_true", help="Full maintenance (backup + check + validate)")

    args = parser.parse_args()

    if args.list:
        return list_skills()

    if args.full:
        print("=== Full Skills Maintenance ===\n")
        backup_skills()
        check_skills()
        return validate_skills()

    if args.check:
        return check_skills()

    if args.backup:
        return backup_skills()

    if args.validate:
        return validate_skills()

    parser.print_help()
    return 0


if __name__ == "__main__":
    exit(main())