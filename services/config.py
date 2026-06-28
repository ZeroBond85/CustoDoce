import os
import yaml
from functools import lru_cache

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "features.yaml")


@lru_cache(maxsize=1)
def _load_config():
    if os.path.exists(_CONFIG_PATH):
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def get(key: str, default=None):
    data = _load_config()
    parts = key.split(".")
    for part in parts:
        if isinstance(data, dict):
            data = data.get(part)
        else:
            return default
    if data is None:
        return default
    if isinstance(data, bool):
        return data
    if isinstance(data, (int, float)):
        return data
    return data


def get_feature(path: str, ingredient: str = None, default=None):
    """
    Gets a feature flag. If an ingredient is provided, it checks for a
    per-ingredient override in 'features.overrides[ingredient]'.
    """
    # 1. Try ingredient override first
    if ingredient:
        override_path = f"features.overrides.{ingredient}.{path.replace('features.', '')}"
        val = get(override_path)
        if val is not None:
            return val

    # 2. Fallback to global feature flag
    return get(path, default)


def reload():
    _load_config.cache_clear()
