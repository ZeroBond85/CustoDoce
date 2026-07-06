"""Validate all static mock data against the offline schema manifest.

Checks:
  1. Column names exist in schema
  2. NOT NULL columns have explicit values
  3. NOT NULL NO DEFAULT columns are present
  4. Python type matches SQL type (boolean→bool, jsonb→dict, etc.)
  5. CHECK constraints are respected (e.g. event_type IN (...))
  6. FK references are resolvable
"""

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST_PATH = REPO_ROOT / "config" / "schema_manifest.json"

MOCK_TABLE_MAP: dict[str, str] = {
    "MOCK_INGREDIENTS": "ingredients",
    "MOCK_STORES": "stores",
    "MOCK_PRICES": "prices",
    "MOCK_LATEST_PRICES": "v_latest_prices",
    "MOCK_PRICE_HISTORY": "price_history",
    "MOCK_REVIEW_QUEUE": "review_queue",
    "MOCK_SCRAPING_LOGS": "scraping_logs",
    "MOCK_SCRAPER_HEALTH": "scraper_health_log",
    "MOCK_SCHEDULES": "schedules",
    "MOCK_FEATURE_FLAGS": "feature_flags",
    "MOCK_FLYERS": "flyers",
    "MOCK_RECIPES": "recipes",
    "MOCK_RECIPE_ITEMS": "recipe_items",
    "MOCK_SCRAPE_FREQUENCIES": "scrape_frequencies",
    "MOCK_ALERT_RULES": "alert_rules",
    "MOCK_ALERT_RECIPIENTS": "alert_recipients",
}

# SQL → Python type mapping (simplified)
TYPE_MAP: dict[str, type | tuple[type, ...]] = {
    "uuid": str,
    "text": str,
    "boolean": bool,
    "int": int,
    "integer": int,
    "jsonb": (dict, list),
}

DECIMAL_PATTERN = re.compile(r"^(decimal|numeric)(\(.*\))?$")

NORMALIZED_REQUIRED_KEYS = {"qty", "unit_kg", "total_kg", "price_per_kg", "price_per_un"}


def _get_manifest() -> dict:
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        return json.load(f)


def _load_mock(mock_name: str) -> list[dict]:
    mod = __import__("tests.unit.fixtures.mock_data", fromlist=[mock_name])
    return getattr(mod, mock_name)


def _check_enum(check_expr: str, value) -> list[str]:
    """Validate a single check expression against a value."""
    errs = []
    in_m = re.match(r"\s*(\w+)\s+IN\s*\((.+)\)\s*$", check_expr, re.I)
    if in_m:
        allowed = []
        for part in in_m.group(2).split(","):
            raw = part.strip().strip("'").strip('"')
            allowed.append(raw)
        if str(value).lower() not in [a.lower() for a in allowed]:
            errs.append(f"  value '{value}' not in allowed set {allowed}")
    return errs


@pytest.fixture(scope="session")
def manifest() -> dict:
    return _get_manifest()


# ─── Test 1: Manifest exists ────────────────────────────────────────────────


def test_manifest_exists():
    assert MANIFEST_PATH.exists(), (
        f"Schema manifest not found at {MANIFEST_PATH}. "
        f"Run: python scripts/generate_schema_manifest.py"
    )


# ─── Test 2: Column name validation (parametrized per mock) ─────────────────


@pytest.mark.parametrize("mock_name", sorted(MOCK_TABLE_MAP.keys()))
def test_mock_keys_exist_in_schema(mock_name: str, manifest: dict):
    table_name = MOCK_TABLE_MAP[mock_name]
    table_cols = set(manifest.get(table_name, {}).get("columns", []))

    assert table_cols, f"Table '{table_name}' not found in manifest"

    mock_data = _load_mock(mock_name)
    if not mock_data:
        return

    errors = []
    for i, item in enumerate(mock_data):
        for key in item:
            if key not in table_cols:
                errors.append(f"  [{mock_name}][{i}] key '{key}' not in table '{table_name}'")
    if errors:
        pytest.fail(
            f"{len(errors)} key(s) in {mock_name} don't match schema '{table_name}':\n"
            + "\n".join(errors)
            + f"\n  Valid cols: {sorted(table_cols)}"
        )


# ─── Test 3: NOT NULL + NOT NULL NO DEFAULT ─────────────────────────────────


@pytest.mark.parametrize("mock_name", sorted(MOCK_TABLE_MAP.keys()))
def test_not_null_columns_present(mock_name: str, manifest: dict):
    table_name = MOCK_TABLE_MAP[mock_name]
    schema = manifest.get(table_name, {})
    not_null = set(schema.get("not_null", []))
    not_null_no_default = set(schema.get("not_null_no_default", []))

    mock_data = _load_mock(mock_name)
    if not mock_data:
        return

    errors = []
    for i, item in enumerate(mock_data):
        for col in not_null:
            if col not in item:
                errors.append(f"  [{mock_name}][{i}] NOT NULL column '{col}' is missing")
        for col in not_null_no_default:
            if col not in item:
                errors.append(
                    f"  [{mock_name}][{i}] NOT NULL NO DEFAULT column '{col}' is missing"
                )
    if errors:
        pytest.fail("Missing columns:\n" + "\n".join(errors))


# ─── Test 4: Python type matches SQL type ───────────────────────────────────


@pytest.mark.parametrize("mock_name", sorted(MOCK_TABLE_MAP.keys()))
def test_column_types_match(mock_name: str, manifest: dict):
    table_name = MOCK_TABLE_MAP[mock_name]
    types = manifest.get(table_name, {}).get("types", {})
    not_null_set = set(manifest.get(table_name, {}).get("not_null", []))

    mock_data = _load_mock(mock_name)
    if not mock_data:
        return

    errors = []
    for i, item in enumerate(mock_data):
        for key, value in item.items():
            sql_type = types.get(key, "")
            if not sql_type:
                continue
            # Allow None for nullable columns
            if value is None and _is_nullable(key, not_null_set):
                continue
            expected = _resolve_expected_type(sql_type)
            if expected is None:
                continue
            if not isinstance(value, expected):
                errors.append(
                    f"  [{mock_name}][{i}].{key}: expected {expected.__name__}, "
                    f"got {type(value).__name__} (value={value!r})"
                )
    if errors:
        pytest.fail("Type mismatches:\n" + "\n".join(errors))


def _resolve_expected_type(sql_type: str) -> type | tuple[type, ...] | None:
    base = sql_type.lower().strip()
    if base in TYPE_MAP:
        return TYPE_MAP[base]
    if DECIMAL_PATTERN.match(base):
        return (int, float, str)
    if base in ("timestamptz", "date"):
        return str
    if base.endswith("[]"):
        return list
    return None


def _is_nullable(col: str, not_null_set: set[str]) -> bool:
    """Return True if column is nullable (not in NOT NULL set)."""
    return col not in not_null_set


# ─── Test 5: CHECK constraints ──────────────────────────────────────────────


@pytest.mark.parametrize("mock_name", sorted(MOCK_TABLE_MAP.keys()))
def test_check_constraints_respected(mock_name: str, manifest: dict):
    table_name = MOCK_TABLE_MAP[mock_name]
    checks = manifest.get(table_name, {}).get("constraints", {}).get("check", [])

    if not checks:
        return

    mock_data = _load_mock(mock_name)
    if not mock_data:
        return

    errors = []
    for i, item in enumerate(mock_data):
        for check in checks:
            expr = check.get("expression", "")
            # Determine column from expression
            col_m = re.match(r"\s*(\w+)\s+IN\s*\(", expr, re.I)
            if col_m:
                col = col_m.group(1).lower()
                if col in item:
                    errs = _check_enum(expr, item[col])
                    errors.extend(
                        f"  [{mock_name}][{i}] CHECK {expr}: {e}" for e in errs
                    )
    if errors:
        pytest.fail("CHECK violations:\n" + "\n".join(errors))


# ─── Test 6: FK references resolvable ───────────────────────────────────────


def _collect_ids_by_table(manifest: dict) -> dict[str, set[str]]:
    """Build a {table_name -> {id1, id2, ...}} lookup from all mocks."""
    ids: dict[str, set[str]] = {}
    for mock_name, table_name in MOCK_TABLE_MAP.items():
        data = _load_mock(mock_name)
        for item in data:
            pk = item.get("id")
            if pk is not None:
                ids.setdefault(table_name, set()).add(str(pk))
    return ids


@pytest.mark.parametrize("mock_name", sorted(MOCK_TABLE_MAP.keys()))
def test_fk_references_resolvable(mock_name: str, manifest: dict):
    table_name = MOCK_TABLE_MAP[mock_name]
    fks = manifest.get(table_name, {}).get("constraints", {}).get("fk", [])

    if not fks:
        return

    ids_by_table = _collect_ids_by_table(manifest)
    mock_data = _load_mock(mock_name)
    if not mock_data:
        return

    errors = []
    for i, item in enumerate(mock_data):
        for fk in fks:
            fk_cols = fk.get("columns", [])
            ref = fk.get("references", {})
            ref_table = ref.get("table", "")
            ref_col = ref.get("column", "id")
            ref_ids = ids_by_table.get(ref_table, set())

            for col in fk_cols:
                val = item.get(col)
                if val is not None and str(val) not in ref_ids:
                    errors.append(
                        f"  [{mock_name}][{i}].{col}={val!r} → FK to {ref_table}.{ref_col} "
                        f"not found in mock data (available: {sorted(ref_ids)[:10]})"
                    )
    if errors:
        pytest.fail("Unresolvable FK references:\n" + "\n".join(errors))


# ─── Test 7: JSONB normalized has required keys ─────────────────────────────


@pytest.mark.parametrize("mock_name", sorted(MOCK_TABLE_MAP.keys()))
def test_normalized_jsonb_has_required_keys(mock_name: str, manifest: dict):
    table_name = MOCK_TABLE_MAP[mock_name]
    types = manifest.get(table_name, {}).get("types", {})

    if types.get("normalized") != "jsonb":
        return

    mock_data = _load_mock(mock_name)
    if not mock_data:
        return

    errors = []
    for i, item in enumerate(mock_data):
        normalized = item.get("normalized")
        if not isinstance(normalized, dict):
            errors.append(f"  [{mock_name}][{i}].normalized is not a dict: {normalized!r}")
            continue
        missing = NORMALIZED_REQUIRED_KEYS - set(normalized.keys())
        if missing:
            errors.append(
                f"  [{mock_name}][{i}].normalized missing keys: {missing}. "
                f"Has: {sorted(normalized.keys())}"
            )
    if errors:
        pytest.fail("JSONB normalized missing required keys:\n" + "\n".join(errors))
