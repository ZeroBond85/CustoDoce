import pytest
from parsers.unit_extractor import extract_unit


@pytest.mark.parametrize(
    "product_name, expected_unit",
    [
        ("Leite Condensado Moça 395g", "395g"),
        ("Leite Condensado 12x395g", "12x395g"),
        ("Creme de Leite 200ml", "200ml"),
        ("Chocolate em Pó 1kg", "1kg"),
        ("Açúcar Refinado 5kg", "5kg"),
        ("Farinha de Trigo cx com 12", "cx com 12"),
        ("Leite em Pó lata 400g", "lata 400g"),
        ("Granulado 500 g", "500 g"),
        ("Manteiga 200 g", "200 g"),
        ("Produto sem unidade", ""),
    ],
)
def test_extract_unit(product_name, expected_unit):
    assert extract_unit(product_name) == expected_unit
