"""
Validate that all static mock data dicts use column names
that exist in the real DB schema (parsed from SQL).
"""
import json
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST_PATH = REPO_ROOT / "config" / "schema_manifest.json"

# Mapping: mock variable name → table/view name in manifest
MOCK_TABLE_MAP: dict[str, str] = {
    "MOCK_PRICES": "v_latest_prices",
    "MOCK_LOGS": "scraping_logs",
}


def get_manifest() -> dict[str, set[str]]:
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return {k: set(v) for k, v in data.items() if not k.startswith("_")}


def get_mock_data(mock_name: str) -> tuple[str, list[dict]]:
    """Import a mock variable from the correct test module and return (table_name, mock_list)."""
    if mock_name == "MOCK_PRICES":
        from tests.unit.test_dashboard_contracts import MOCK_PRICES as data
        table = MOCK_TABLE_MAP[mock_name]
        return table, data
    if mock_name == "MOCK_LOGS":
        from tests.unit.test_dashboard_contracts import MOCK_LOGS as data
        table = MOCK_TABLE_MAP[mock_name]
        return table, data
    raise ValueError(f"Unknown mock: {mock_name}")


def test_manifest_exists():
    assert MANIFEST_PATH.exists(), (
        f"Schema manifest not found at {MANIFEST_PATH}. "
        "Run: python scripts/generate_schema_manifest.py"
    )


@pytest.mark.parametrize("mock_name", sorted(MOCK_TABLE_MAP.keys()))
def test_mock_keys_exist_in_schema(mock_name: str):
    manifest = get_manifest()
    table_name, mock_data = get_mock_data(mock_name)
    table_cols = manifest.get(table_name)

    assert table_cols is not None, (
        f"Table '{table_name}' not found in manifest. "
        f"Available: {sorted(manifest.keys())}"
    )

    if not mock_data:
        pytest.skip(f"{mock_name} is empty")

    errors = []
    for i, item in enumerate(mock_data):
        for key in item:
            if key not in table_cols:
                errors.append(
                    f"  [{mock_name}][{i}] key '{key}' not in table '{table_name}'"
                )

    if errors:
        pytest.fail(
            f"{len(errors)} key(s) in {mock_name} don't match schema '{table_name}':\n"
            + "\n".join(errors)
            + f"\n  Valid columns for '{table_name}': {sorted(table_cols)}"
        )


def test_mock_columns_cover_required_not_null():
    """Check that NOT NULL columns (without DEFAULT) are present in mocks."""
    manifest = get_manifest()
    # Minimal check: ensure key non-nullable fields are never missing
    essential_map: dict[str, set[str]] = {
        "v_latest_prices": {"ingredient_id", "store_id", "price_per_kg"},
        "scraping_logs": {"store_name", "status", "started_at"},
    }

    for mock_name in MOCK_TABLE_MAP:
        table_name = MOCK_TABLE_MAP[mock_name]
        essential = essential_map.get(table_name, set())
        if not essential:
            continue

        table_name, mock_data = get_mock_data(mock_name)
        if not mock_data:
            continue

        mock_keys = set(mock_data[0].keys())
        missing = essential - mock_keys
        if missing:
            pytest.fail(
                f"{mock_name} missing essential columns: {missing} "
                f"(table '{table_name}'). These are NOT NULL without DEFAULT."
            )
