import pytest

from parsers.matcher import match_ingredient


@pytest.fixture
def sample_ingredients():
    return [
        {
            "canonical_name": "Leite Condensado",
            "aliases": ["Leite Condensado Integral", "Condensado"],
            "search_terms": ["moça", "itambé"],
        },
        {
            "canonical_name": "Chocolate em Pó 50%",
            "aliases": ["Chocolate Cacau 50%", "Chocolate Pó"],
            "search_terms": ["melken", "sicao"],
        },
        {
            "canonical_name": "Creme de Leite",
            "aliases": ["Creme de Leite 20%"],
            "search_terms": ["nestlé", "piracanjuba"],
        },
    ]


@pytest.mark.parametrize(
    "product_text, expected_match, expected_type",
    [
        # Exact matches
        ("Leite Condensado Moça 395g", "Leite Condensado", "exato"),
        ("Creme de Leite Nestlé 200g", "Creme de Leite", "exato"),
        ("Chocolate em Pó 50% Sicao 1kg", "Chocolate em Pó 50%", "exato"),
        # Alias matches
        ("Condensado Integral Piracanjuba", "Leite Condensado", "exato"),
        ("Chocolate Pó Melken 500g", "Chocolate em Pó 50%", "exato"),
        # Fuzzy matches (above threshold 80)
        ("Leite Condensado Intgral", "Leite Condensado", "exato"),
        ("Creme de Leite 20% Gord", "Creme de Leite", "exato"),
        ("Choco Pó 50% Cacau", "Chocolate em Pó 50%", "proximo_apelido"),
        # Subtle differences
        ("Leite Condensado Moça", "Leite Condensado", "exato"),
        ("Leite Condensado Int", "Leite Condensado", "exato"),
        # No match (below threshold)
        ("Açúcar Refinado", None, "none"),
        ("Farinha de Trigo", None, "none"),
        ("Manteiga com sal", None, "none"),
        # Edge cases
        ("", None, "none"),
        ("   ", None, "none"),
    ],
)
def test_match_ingredient(sample_ingredients, product_text, expected_match, expected_type):
    ing, score, match_type = match_ingredient(product_text, sample_ingredients)
    if expected_match is None:
        assert ing is None
    else:
        assert ing is not None
        assert ing["canonical_name"] == expected_match

    # For 'exato', the type is always 'exato'. For others, it depends on the path.
    # If expected_match is None, the type returned is whatever was best but < threshold.
    if expected_match is not None:
        assert match_type == expected_type


def test_clean_text():
    from parsers.matcher import clean_text

    assert clean_text("Leite Condensado 12un") == "LEITE CONDENSADO 12UN"
    assert clean_text("Creme de Leite - Nestle") == "CREME DE LEITE NESTLE"
    assert clean_text("") == ""


@pytest.mark.parametrize(
    "product_text, ingredient_idx, expected",
    [
        ("Leite Condensado Moça 395g", 0, True),
        ("Creme de Leite", 0, False),  # wrong ingredient
        ("Leite Cond Molico 395g", 0, False),  # 'Cond' ≠ 'Condensado' (prefix, not exact)
        ("Leite Condensado Integral Moça", 0, True),  # word_subset
    ],
)
def test_match_exact(sample_ingredients, product_text, ingredient_idx, expected):
    from parsers.matcher import match_exact

    assert match_exact(product_text, sample_ingredients[ingredient_idx]) == expected


def test_rank_ingredients(sample_ingredients):
    from parsers.matcher import rank_ingredients

    result = rank_ingredients("Chocolate em Pó 50% Cacau 200g", sample_ingredients, top_n=2)
    assert len(result) == 2
    assert result[0][0]["canonical_name"] == "Chocolate em Pó 50%"


def test_build_alias_list(sample_ingredients):
    from parsers.matcher import build_alias_list

    result = build_alias_list(sample_ingredients)
    assert len(result) >= 3
    pairs = [(c, a) for c, a, _ in result]
    assert ("Leite Condensado", "Leite Condensado") in pairs
    assert ("Leite Condensado", "Leite Condensado Integral") in pairs


@pytest.mark.parametrize(
    "text, expected_len",
    [
        ("Leite Condensado Moça", True),
        ("Arroz Branco 5kg", False),
    ],
)
def test_has_ingredient_keyword(sample_ingredients, text, expected_len):
    from parsers.matcher import extract_all_keywords, has_ingredient_keyword

    kw = extract_all_keywords(sample_ingredients)
    assert has_ingredient_keyword(text, kw) == expected_len


def test_extract_all_keywords_empty():
    from parsers.matcher import extract_all_keywords

    assert extract_all_keywords([]) == set()
