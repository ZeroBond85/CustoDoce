"""Unit tests for services/store_registry.py (discover + entry + dataclass)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services import store_registry


def test_store_registry_entry_dataclass_defaults():
    entry = store_registry.StoreRegistryEntry(name="Loja X")
    assert entry.name == "Loja X"
    assert entry.normalized_name == "LOJA X"
    assert entry.status == "pending_review"
    assert entry.config == {}


def test_discover_stores_from_flyers_filters_non_food():
    """Non-food stores like Magazine Luiza should be filtered out before registry."""
    mock_client = MagicMock()
    # flyers query returns 3 stores: 2 food, 1 non-food
    mock_client.table.return_value.select.return_value.execute.return_value = SimpleNamespace(
        data=[
            {"store_name": "Assaí Atacadista", "region": "Santos", "city": "Santos"},
            {"store_name": "Magazine Luiza", "region": "Santos", "city": "Santos"},
            {"store_name": "Carrefour", "region": "São Paulo", "city": "São Paulo"},
        ]
    )
    with patch.object(store_registry, "get_service_client", return_value=mock_client), \
         patch.object(store_registry, "upsert_registry_entry",
                      return_value=SimpleNamespace(id="new-1", matched_store_id=None, address="")):
        result = store_registry.discover_stores_from_flyers()
    # 2 food stores (Assaí, Carrefour), Magazine Luiza filtered out
    assert result == 2
    calls = mock_client.table.call_args_list
    tables_called = [c[0][0] for c in calls]
    assert "flyers" in tables_called  # queried flyers
    assert "stores" in tables_called  # queried existing stores for dedup


def test_discover_stores_from_flyers_no_client_returns_zero():
    with patch.object(store_registry, "get_service_client", side_effect=Exception("no client")):
        result = store_registry.discover_stores_from_flyers()
    assert result == 0


def test_is_food_store_name_filters_non_food():
    """T2.1: varejo não-alimentar visto nos pendentes é filtrado."""
    non_food = [
        "Lojas Havan", "Lojas Cem", "Lojas Quero-Quero", "Lojas Solar",
        "Eudora", "Jequiti", "Ferreira Costa", "TEMU", "Decathlon",
        "Tupperware", "Casa e Video", "Magazine Luiza", "Drogasil",
    ]
    for name in non_food:
        assert not store_registry._is_food_store_name(name), f"deveria ser não-food: {name}"


def test_is_food_store_name_keeps_food():
    """Lojas de comida reais (Shibata, Sam's Club) NÃO são filtradas."""
    food = [
        "Shibata", "Sam's Club", "Supermercado Dia", "Nagumo",
        "Assaí Atacadista", "Rede Krill", "Max Atacadista",
    ]
    for name in food:
        assert store_registry._is_food_store_name(name), f"deveria ser food: {name}"


def test_is_food_store_name_filters_flyer_titles():
    """T2.2: títulos de folheto agregador ('Catálogo ... em ...') são filtrados."""
    flyer_titles = [
        "Catálogo Lojas Havan em Guarujá | Dia Dos Pais | 2026-07-27",
        "Catálogo Nagumo em Itanhaém | FOLHETO | 2026-07-27",
        "Catálogo Supermercado Dia em Santos | Encarte Supermercado Dia | 2026-07-30",
        "Catalogo Lojas Havan em São Paulo | Dia Dos Pais",
    ]
    for name in flyer_titles:
        assert not store_registry._is_food_store_name(name), f"deveria filtrar flyer: {name}"


def test_discover_stores_from_flyers_filters_new_offenders():
    """T2.1/T2.2: Havan/Quero-Quero/flyer titles não entram no registry."""
    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.execute.return_value = SimpleNamespace(
        data=[
            {"store_name": "Lojas Havan", "region": "Santos", "city": "Santos"},
            {"store_name": "Catálogo Nagumo em Itanhaém | FOLHETO | 2026-07-27",
             "region": "Baixada", "city": "Itanhaém"},
            {"store_name": "Shibata", "region": "Santos", "city": "Santos"},
        ]
    )
    with patch.object(store_registry, "get_service_client", return_value=mock_client), \
         patch.object(store_registry, "upsert_registry_entry",
                      return_value=SimpleNamespace(id="new-1", matched_store_id=None, address="")):
        result = store_registry.discover_stores_from_flyers()
    # Só Shibata (food) entra; Havan + flyer title filtrados
    assert result == 1


def test_get_registry_entry_builds_dataclass():
    row = {
        "id": "reg-1",
        "name": "Nova Loja",
        "normalized_name": "NOVA LOJA",
        "tier": 3,
        "type": "manual",
        "logistics": "pickup_local",
        "city": "Santos",
        "zone": "Baixada",
        "coverage": "regional",
        "collection_method": "auto",
        "source": "auto",
        "status": "pending_review",
        "match_score": 0.5,
        "matched_store_id": None,
        "config": {},
    }
    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
        SimpleNamespace(data=row)
    )
    with patch.object(store_registry, "get_service_client", return_value=mock_client):
        entry = store_registry.get_registry_entry("reg-1")
    assert entry is not None
    assert entry.name == "Nova Loja"
    assert entry.tier == 3


def _mock_auto_promote(pending, prices_by_name=None, prices_by_id=None):
    """Monta mock de client com dados de pending + prices para auto_promote."""
    mock_client = MagicMock()

    def table(name):
        if name == "store_registry":
            tbl = MagicMock()
            tbl.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(data=pending)
            tbl.update.return_value.eq.return_value.execute.return_value = SimpleNamespace(data=[{}])
            return tbl
        if name == "prices":
            tbl = MagicMock()

            def select(cols):
                sel = MagicMock()

                def eq(col, val):
                    data = []
                    if col == "store_name":
                        data = prices_by_name.get(val, [])
                    elif col == "store_id":
                        data = prices_by_id.get(val, [])
                    sel.execute.return_value = SimpleNamespace(data=data)
                    return sel

                sel.eq.side_effect = eq
                return sel

            tbl.select.side_effect = select
            return tbl
        raise AssertionError(f"unexpected table: {name}")

    mock_client.table.side_effect = table
    return mock_client


def test_auto_promote_aggregator_sem_match_conta_por_store_name():
    """Fix 4.4: agregadora (source=auto) SEM matched_store_id com >=2 ingredientes
    em prices por store_name é promovida."""
    pending = [
        {"id": "r1", "name": "Loja Flyer X", "matched_store_id": None,
         "source": "auto", "discovery_source": "flyer", "tier": 3}
    ]
    prices = {
        "Loja Flyer X": [
            {"ingredient_id": "ing-1"}, {"ingredient_id": "ing-2"},
        ]
    }
    mock_client = _mock_auto_promote(pending, prices_by_name=prices)
    with patch.object(store_registry, "get_service_client", return_value=mock_client):
        promoted = store_registry.auto_promote_discovered_stores(min_matched_products=2)
    assert promoted == 1


def test_auto_promote_aggregator_sem_match_nao_promove_sem_precos():
    """Agregadora sem preços suficientes NÃO é promovida (continua pendente)."""
    pending = [
        {"id": "r1", "name": "Loja Flyer X", "matched_store_id": None,
         "source": "auto", "discovery_source": "flyer", "tier": 3}
    ]
    mock_client = _mock_auto_promote(pending, prices_by_name={"Loja Flyer X": []})
    with patch.object(store_registry, "get_service_client", return_value=mock_client):
        promoted = store_registry.auto_promote_discovered_stores(min_matched_products=2)
    assert promoted == 0


def test_auto_promote_com_match_conta_por_store_id():
    """Fix 4.5: com matched_store_id, conta ingredientes por store_id (não por
    store_name que quase nunca bate com o nome do scraper config)."""
    pending = [
        {"id": "r1", "name": "Assaí Flyer", "matched_store_id": "store-42",
         "source": "auto", "discovery_source": "flyer", "tier": 3}
    ]
    prices = {
        "store-42": [
            {"ingredient_id": "ing-1"}, {"ingredient_id": "ing-2"},
            {"ingredient_id": "ing-3"},
        ]
    }
    mock_client = _mock_auto_promote(pending, prices_by_id=prices)
    with patch.object(store_registry, "get_service_client", return_value=mock_client):
        promoted = store_registry.auto_promote_discovered_stores(min_matched_products=2)
    assert promoted == 1
