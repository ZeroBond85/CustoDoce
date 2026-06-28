import pytest
from parsers.brand_extractor import extract_brand


@pytest.fixture
def sample_ingredient():
    return {"canonical_name": "Leite Condensado", "brands": ["Moça", "Piracanjuba", "Italac", "Itambé"]}


@pytest.mark.parametrize(
    "product_text, expected_brand",
    [
        # Exact match (Level 1)
        ("Leite Condensado Moça 395g", "Moça"),
        ("Leite Condensado Piracanjuba", "Piracanjuba"),
        ("Leite Condensado Italac", "Italac"),
        ("Leite Condensado Itambé", "Itambé"),
        # Substring match (Level 2)
        ("Leite Condensado Moça", "Moça"),
        ("Leite Condensado Moça 395g", "Moça"),  # Boundaries’ check
        # Fuzzy match (Level 3)
        ("Leite Condensado Moca 395g", "Moça"),  # Accent difference
        ("Leite Condensado Piracanjuba", "Piracanjuba"),
        # No match
        ("Leite Condensado Genérico", "Desconhecido"),
        ("Leite Condensado marca X", "Desconhecido"),
        # Empty text
        ("", "Desconhecido"),
    ],
)
def test_extract_brand(sample_ingredient, product_text, expected_brand):
    assert extract_brand(product_text, sample_ingredient) == expected_brand
