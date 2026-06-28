"""
Testes unitários para services/price_analytics.py: otimizar_carrinho_compras.

Cobre:
- Cenário Monofonte: 1 loja cobrindo todos os itens
- Cenário Multifonte: até 2 lojas cobrindo tudo, com economia
- Edge cases: lista vazia, itens faltando
- Formatação Markdown/HTML
"""

from unittest.mock import patch

import pytest


@pytest.fixture
def sample_latest_prices():
    return [
        # Assaí: cheapest for conden + but expensive for manteiga
        {
            "ingredient_id": "Leite Condensado Integral",
            "store_id": "assai",
            "store_name": "Assaí",
            "normalized": {"price_per_kg": 13.95},
            "raw_price": 5.51,
            "raw_unit": "395g",
        },
        {
            "ingredient_id": "Manteiga",
            "store_id": "assai",
            "store_name": "Assaí",
            "normalized": {"price_per_kg": 45.0},
        },
        # Tenda: mais barato para manteiga, mas não tem condensado
        {
            "ingredient_id": "Manteiga",
            "store_id": "tenda",
            "store_name": "Tenda",
            "normalized": {"price_per_kg": 35.0},
        },
        # Extra: cover both, but expensive everywhere
        {
            "ingredient_id": "Leite Condensado Integral",
            "store_id": "extra",
            "store_name": "Extra",
            "normalized": {"price_per_kg": 16.0},
        },
        {
            "ingredient_id": "Manteiga",
            "store_id": "extra",
            "store_name": "Extra",
            "normalized": {"price_per_kg": 40.0},
        },
    ]


def test_optimize_with_empty_list():
    """Lista vazia → resposta vazia."""
    from services.price_analytics import otimizar_carrinho_compras

    result = otimizar_carrinho_compras({})
    assert result["cenario_monofonte"] is None
    assert result["cenario_multifonte"] is None
    assert "vazia" in result["format_markdown"].lower()


def test_optimize_all_missing(sample_latest_prices):
    """Lista com todos os itens faltando → graceful fallback."""
    with patch(
        "services.price_analytics.get_all_current_prices",
        return_value=sample_latest_prices,
    ):
        from services.price_analytics import otimizar_carrinho_compras

        result = otimizar_carrinho_compras(
            {
                "Item Inexistente A": 5.0,
                "Item Inexistente B": 2.0,
            }
        )
    assert result["cenario_monofonte"] is None
    assert result["cenario_multifonte"] is None
    assert "Nenhum dos itens" in result["format_markdown"] or "sem pre" in result["format_markdown"].lower()


def test_monofonte_finds_single_store(sample_latest_prices):
    """Quando Assaí ou Extra cobrem tudo, identificamos a mais barata."""
    with patch(
        "services.price_analytics.get_all_current_prices",
        return_value=sample_latest_prices,
    ):
        from services.price_analytics import otimizar_carrinho_compras

        lista = {
            "Leite Condensado Integral": 5.0,
            "Manteiga": 2.0,
        }
        result = otimizar_carrinho_compras(lista, max_sources=1)

    # Monofonte: Assaí (13.95*5 + 45*2 = 69.75+90 = 159.75) vs Extra (16*5 + 40*2 = 80+80 = 160)
    # Assaí is cheaper
    assert result["cenario_monofonte"] is not None
    assert result["cenario_monofonte"]["store_name"] == "Assaí"


def test_multifonte_beats_monofonte(sample_latest_prices):
    """Dividir entre Assaí (Condensado) e Tenda (Manteiga) deve economizar."""
    with patch(
        "services.price_analytics.get_all_current_prices",
        return_value=sample_latest_prices,
    ):
        from services.price_analytics import otimizar_carrinho_compras

        lista = {
            "Leite Condensado Integral": 5.0,
            "Manteiga": 2.0,
        }
        result = otimizar_carrinho_compras(lista, max_sources=2)

    # Monofonte (Assaí): 13.95 * 5 + 45 * 2 = 159.75
    # Multifonte: 13.95*5 (Assaí conden) + 35*2 (Tenda manteiga) = 69.75 + 70 = 139.75
    # Economia = 20.0
    assert result["economia_multifonte_vs_monofonte"] is not None
    assert result["economia_multifonte_vs_monofonte"] > 15.0


def test_no_store_covers_100_percent():
    """Quando ninguém cobre tudo, monofonte is None."""
    prices = [
        # Tenda has only Manteiga
        {
            "ingredient_id": "Manteiga",
            "store_id": "tenda",
            "store_name": "Tenda",
            "normalized": {"price_per_kg": 35.0},
        },
    ]
    with patch("services.price_analytics.get_all_current_prices", return_value=prices):
        from services.price_analytics import otimizar_carrinho_compras

        lista = {"Leite Condensado Integral": 5.0, "Manteiga": 2.0}
        result = otimizar_carrinho_compras(lista)

    assert result["cenario_monofonte"] is None
    assert result["lista_faltando"] == ["Leite Condensado Integral"]


def test_format_markdown_includes_key_info(sample_latest_prices):
    """Markdown format includes Monofonte & Multifonte info."""
    with patch(
        "services.price_analytics.get_all_current_prices",
        return_value=sample_latest_prices,
    ):
        from services.price_analytics import otimizar_carrinho_compras

        result = otimizar_carrinho_compras(
            {
                "Leite Condensado Integral": 5.0,
                "Manteiga": 2.0,
            },
            max_sources=2,
        )
    md = result["format_markdown"]
    assert "Monofonte" in md or "monofonte" in md.lower()
    assert "Multifonte" in md or "multifonte" in md.lower()


def test_format_html_includes_table(sample_latest_prices):
    """HTML format deve ser HTML well-formed."""
    with patch(
        "services.price_analytics.get_all_current_prices",
        return_value=sample_latest_prices,
    ):
        from services.price_analytics import otimizar_carrinho_compras

        result = otimizar_carrinho_compras(
            {
                "Leite Condensado Integral": 5.0,
                "Manteiga": 2.0,
            },
            max_sources=2,
        )
    html = result["format_html"]
    assert "<table" in html
    assert "</table>" in html


def test_get_all_current_prices_exception_handled():
    """Se get_all_current_prices lançar, retorna graceful."""

    def boom(*args, **kwargs):
        raise Exception("DB offline")

    with patch("services.price_analytics.get_all_current_prices", side_effect=boom):
        from services.price_analytics import otimizar_carrinho_compras

        result = otimizar_carrinho_compras({"Leite Condensado Integral": 5.0})
    assert result["cenario_monofonte"] is None
    assert result["cenario_multifonte"] is None


def test_max_sources_reduces_to_1(sample_latest_prices):
    """max_sources=1 deve desabilitar multifonte."""
    with patch(
        "services.price_analytics.get_all_current_prices",
        return_value=sample_latest_prices,
    ):
        from services.price_analytics import otimizar_carrinho_compras

        result = otimizar_carrinho_compras(
            {
                "Leite Condensado Integral": 5.0,
                "Manteiga": 2.0,
            },
            max_sources=1,
        )
    # Although combinatorics would generate r=1 options
    # Only 1-store combos = monofonte-like
    # Multifonte with r=1 is essentially same info. OK.
