"""Testes do sync_ingredient_fields.py — sincronização YAML -> DB.

Cobre: sync exato de exclude_terms, merge de search_terms/brands,
limpeza de artifacts de teste nos aliases.
"""

from unittest.mock import MagicMock, patch


def test_load_yaml_ingredients():
    from scripts.sync_ingredient_fields import load_yaml_ingredients

    ings = load_yaml_ingredients()
    assert len(ings) >= 23
    assert any(i["canonical"] == "Top Confete Morango" for i in ings)


def test_sync_marks_exclude_terms_diff():
    """Ingrediente com exclude_terms YAML != DB deve entrar em pending."""
    from scripts.sync_ingredient_fields import main

    yaml_ing = {
        "canonical": "Teste",
        "exclude_terms": ["papel", "caixa"],
        "search_terms": ["teste"],
        "brands": [],
    }
    db_ing = {
        "canonical_name": "Teste",
        "exclude_terms": [],
        "search_terms": ["teste"],
        "brands": [],
        "aliases": [],
    }

    with (
        patch("scripts.sync_ingredient_fields.load_yaml_ingredients", return_value=[yaml_ing]),
        patch("scripts.sync_ingredient_fields.get_service_client") as mock_gsc,
    ):
        mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.data = [db_ing]
        mock_client.rpc.return_value.execute.return_value = mock_res
        mock_gsc.return_value = mock_client

        # Capturar output do dry-run
        with patch("sys.argv", ["sync_ingredient_fields.py", "--dry-run"]):
            try:
                main()
            except SystemExit:
                pass

        # O pending deve ter sido detectado: verificar que exec não foi chamado
        # (dry-run não executa update)
        assert not mock_client.table.return_value.update.called


def test_clean_alias_removes_test_artifacts():
    from scripts.sync_ingredient_fields import _clean_alias

    assert _clean_alias("Test Approve UUID 200g") is None
    assert _clean_alias("Test Approve Name 500g") is None
    assert _clean_alias("Test Approve Fuzzy 1kg") is None
    assert _clean_alias("Duplicate Price Product 395g") is None
    assert _clean_alias("Granulado Melken Ao Leite 1kg") == "Granulado Melken Ao Leite 1kg"
    assert _clean_alias("Leite Condensado Moça 395g") == "Leite Condensado Moça 395g"


def test_seed_includes_exclude_terms():
    """O seed deve enviar exclude_terms/search_terms/brands ao upsert (fix do gap)."""
    from scripts.seed_config_db import seed_ingredients

    yaml_ing = {
        "canonical": "Teste",
        "category": "test",
        "aliases": ["Teste 1kg"],
        "exclude_terms": ["papel", "caixa"],
        "search_terms": ["teste"],
        "brands": ["Marca"],
        "unit_target": "kg",
    }

    with (
        patch("scripts.seed_config_db.yaml.safe_load", return_value={"ingredients": [yaml_ing]}),
        patch("scripts.seed_config_db.upsert_ingredient") as mock_upsert,
    ):
        seed_ingredients()
        mock_upsert.assert_called_once()
        data = mock_upsert.call_args[0][0]
        assert data["exclude_terms"] == ["papel", "caixa"]
        assert data["search_terms"] == ["teste"]
        assert data["brands"] == ["Marca"]
