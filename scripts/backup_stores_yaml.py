#!/usr/bin/env python3
"""
Backup stores.yaml before sync operations.
Creates timestamped backup in data/store_backups/
"""

import shutil
from datetime import UTC, datetime
from pathlib import Path

STORES_YAML = Path("config/stores.yaml")
BACKUP_DIR = Path("data/store_backups")


def backup_stores_yaml() -> Path | None:
    """Create timestamped backup of stores.yaml. Returns backup path or None."""
    if not STORES_YAML.exists():
        print(f"[WARN] {STORES_YAML} not found")
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    suffix = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = BACKUP_DIR / f"stores.{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.yaml"

    shutil.copy2(STORES_YAML, backup_path)
    print(f"[OK] Backup created: {backup_path}")
    return backup_path


if __name__ == "__main__":
    backup_stores_yaml()