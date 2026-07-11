"""Unit tests for services/import_service.py (import manual de preços via CSV/XLSX)."""

from __future__ import annotations

from unittest.mock import patch

from services import import_service

_CSV = "ingredient,store,price,unit,collected_at,brand\nLeite Condensado,Assaí Atacadista,10.50,395g,2026-06-28,Moça\n"


def _patch_deps(captured):
    patchers = [
        patch.object(
            import_service,
            "get_all_ingredients",
            return_value=[{"canonical_name": "Leite Condensado", "id": "ing-001"}],
        ),
        patch.object(
            import_service,
            "get_all_stores",
            return_value=[{"name": "Assaí Atacadista", "id": "store-001"}],
        ),
        patch.object(import_service, "upsert_price", side_effect=captured.append),
    ]
    for p in patchers:
        p.start()
    return patchers


def test_import_manual_prices_csv_imports_row():
    captured = []
    patchers = _patch_deps(captured)
    import os
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write(_CSV)
        path = f.name
    try:
        result = import_service.import_manual_prices(path)
    finally:
        for p in patchers:
            p.stop()
        os.unlink(path)
    assert result["imported"] == 1
    assert result["errors"] == []
    assert captured, "upsert_price deveria ter sido chamado"
    assert captured[0]["ingredient_id"] == "ing-001"
    assert captured[0]["store_id"] == "store-001"
    assert captured[0]["normalized"] is not None


def test_import_manual_prices_unknown_ingredient_errors():
    captured = []
    patchers = _patch_deps(captured)
    csv = "ingredient,store,price,unit,collected_at,brand\nXYZZZ,Assaí Atacadista,10.50,395g,2026-06-28,Moça\n"
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write(csv)
        path = f.name
    try:
        result = import_service.import_manual_prices(path)
    finally:
        for p in patchers:
            p.stop()
        os.unlink(path)
    assert result["imported"] == 0
    assert any("XYZZZ" in e for e in result["errors"])
    assert captured == []
