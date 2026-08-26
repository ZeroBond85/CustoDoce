from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_SELECTORS_DB: dict[str, Any] | None = None
_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _load_selectors_db() -> dict[str, Any]:
    global _SELECTORS_DB
    if _SELECTORS_DB is None:
        path = _CONFIG_DIR / "selectors.yaml"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                _SELECTORS_DB = yaml.safe_load(f) or {}
        else:
            _SELECTORS_DB = {}
    return _SELECTORS_DB


def resolve_selectors(store_config: dict[str, Any]) -> dict[str, list[str]]:
    """Resolve selectors for a store: store-specific > type variant > defaults.

    Returns a dict with keys: product_card, product_name, product_price,
    product_old_price, product_brand, product_validity.
    """
    db = _load_selectors_db()
    store_selectors = store_config.get("selectors") or {}
    store_type = store_config.get("type", "")
    variant = db.get(store_type) or {}
    defaults = db.get("defaults") or {}

    merged: dict[str, list[str]] = {}
    keys = ["product_card", "product_name", "product_price",
            "product_old_price", "product_brand", "product_validity"]
    for key in keys:
        merged[key] = (
            store_selectors.get(key)
            or variant.get(key)
            or defaults.get(key)
            or []
        )
    return merged


def get_available_variants() -> list[str]:
    """Return list of available selector variant names."""
    db = _load_selectors_db()
    return [k for k in db if k != "defaults"]


def reload() -> None:
    """Force reload of selectors.yaml on next call."""
    global _SELECTORS_DB
    _SELECTORS_DB = None
