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
        # Search term exact matches (via match_exact search_terms)
        ("Moça Leite 395g", "Leite Condensado", "exato"),
        ("Itambé Leite 395g", "Leite Condensado", "exato"),
        ("Melken Chocolate 1kg", "Chocolate em Pó 50%", "exato"),
        ("Sicao Cacau 50%", "Chocolate em Pó 50%", "exato"),
        # Alias matches
        ("Condensado Integral Piracanjuba", "Leite Condensado", "exato"),
        ("Chocolate Pó Melken 500g", "Chocolate em Pó 50%", "exato"),
        # Fuzzy matches (above threshold 80)
        ("Leite Condensado Intgral", "Leite Condensado", "exato"),
        ("Creme de Leite 20% Gord", "Creme de Leite", "exato"),
        # "Choco Pó 50% Cacau" is now penalized below threshold (abbreviation) -> None
        ("Choco Pó 50% Cacau", None, "none"),
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


# ====================================================================
# Regressão: FPs de variante corrigidos via dados (ingredients.yaml)
# ====================================================================


@pytest.fixture(scope="module")
def real_ingredients():
    from scripts.evaluate_matcher import load_ingredients

    return load_ingredients()


def test_granulado_colorido_nao_casa_ao_leite(real_ingredients):
    """'Granulado Colorido' não pode casar 'Granulado Ao Leite'.

    Antes, o search_term genérico 'granulado' em 'Ao Leite' capturava qualquer
    granulado via match exato. Corrigido especializando para 'granulado ao leite'.
    """
    result, _score, _mt = match_ingredient("Granulado Colorido", real_ingredients)
    assert result is not None
    assert result["canonical_name"] == "Granulado Colorido"


def test_creme_de_leite_nestle_casa_variante_correta(real_ingredients):
    """'Creme de Leite Nestlé' casa 'Creme de Leite 20% Gordura' (Nestlé é marca dele)."""
    result, _score, _mt = match_ingredient("Creme de Leite Nestlé", real_ingredients)
    assert result is not None
    assert result["canonical_name"] == "Creme de Leite 20% Gordura"


def test_chocolate_cremoso_rejeitado_por_exclude_terms(real_ingredients):
    """'Chocolate Leite Cremoso' (barra) não é chocolate em pó → deve ser rejeitado.

    Regressão do exclude_terms aplicado em match_ingredient: 'cremoso' está na
    exclude_terms de 'Chocolate em Pó 50% Cacau'.
    """
    result, _score, _mt = match_ingredient("Chocolate Leite Cremoso 500g", real_ingredients)
    assert result is None


# ====================================================================
# RPR (Regra #11): FPs reais coletados do scrape (RIZZO/casa_santa_luzia)
# devem ser bloqueados; TNs legítimos não podem ser perdidos.
# ====================================================================


@pytest.mark.parametrize(
    "product_text",
    [
        "Haste de Chenille de Pelúcia 101cm - Amarelo Manteiga",
        "Papel Trufa 14,5x15,5cm - Granulado Branco - 100 unidades",
        "Caixa Surpresa para Doces Lembrancinha Granulado Colorido - Rosa",
        "Folha para Ovos de Páscoa - Barra de Chocolate - 35 cm",
        "Chocolate Granulado Dori - 300g",
        "Creme de Leite de Coco Fredão - 200ml",
        "Forminha para Doces Finos - Cheri - 3 Tons Pap Manteiga",
        "Caixa Cartinha para Barra de Chocolate de 80g",
    ],
)
def test_real_fps_rejeitados(real_ingredients, product_text):
    """FPs reais (embalagem/decoração/cor) não devem casar nenhum ingrediente."""
    result, _score, _mt = match_ingredient(product_text, real_ingredients)
    assert result is None, f"FP não bloqueado: {product_text} -> {result}"


@pytest.mark.parametrize(
    "product_text, expected",
    [
        ("Manteiga Aviação 200g", "Manteiga"),
        ("Manteiga com Sal 500g", "Manteiga"),
        ("Granulado Branco Melken 500g", "Granulado Branco"),
        ("Chocolate em Pó Melken 1kg 50%", "Chocolate em Pó 50% Cacau"),
        ("Creme de Leite Nestlé 200g", "Creme de Leite 20% Gordura"),
        ("Ovos Brancos 30 unidades", "Ovos"),
        ("Leite em Pó Ninho 400g", "Leite em Pó Integral"),
        ("Chocolate Chunks Harald 1kg", "Chocolate Chunks"),
    ],
)
def test_tns_legitimos_casam(real_ingredients, product_text, expected):
    """TNs legítimos devem continuar casando (sem perda de recall)."""
    result, _score, _mt = match_ingredient(product_text, real_ingredients)
    assert result is not None, f"TN perdido: {product_text}"
    assert result["canonical_name"] == expected, (
        f"{product_text} casou {result['canonical_name']}, esperado {expected}"
    )


# ====================================================================
# Phase 2: word-boundary guard, coverage penalty, deaccent, gate fixes
# ====================================================================


@pytest.mark.parametrize(
    "product_text, expected",
    [
        # word-boundary guard: short terms don't match mid-word
        ("Chocolate CLassic 100g", None),  # "cl" in "Classic" blocked
        ("Amarelo Manteiga 200g", None),  # "manteiga" as color blocked
        ("Ovos de Páscoa 300g", None),  # "ovos" in pascoa blocked
        # legitimate short-term start matches
        ("Manteiga Aviação 200g", "Manteiga"),
        ("Ovos Brancos 30 unidades", "Ovos"),
        ("Ninho Leite em Pó 400g", "Leite em Pó Integral"),
    ],
)
def test_word_boundary_guard(real_ingredients, product_text, expected):
    """Short canonical/search_terms only match at word boundary or start."""
    result, _score, _mt = match_ingredient(product_text, real_ingredients)
    if expected is None:
        assert result is None, f"FP: {product_text} -> {result}"
    else:
        assert result is not None
        assert result["canonical_name"] == expected


@pytest.mark.parametrize(
    "product_text, expected",
    [
        # single-word term coverage penalty: term appears but explains little of product
        ("Macarrão De Sêmola Adria Ovos 500g", None),  # "Ovos" 1/5 tokens
        ("Salame Italiano Seara 100g", None),  # no match
        # legitimate single-word at start -> exact via startswith
        ("Ovos Brancos 30un", "Ovos"),
        ("Manteiga com Sal 200g", "Manteiga"),
    ],
)
def test_single_word_coverage_penalty(real_ingredients, product_text, expected):
    """Single-word canonicals penalized when they explain < fraction of product tokens."""
    result, _score, _mt = match_ingredient(product_text, real_ingredients)
    if expected is None:
        assert result is None, f"FP: {product_text} -> {result}"
    else:
        assert result is not None
        assert result["canonical_name"] == expected


def test_deaccent_matches_accent_variants(real_ingredients):
    """Deaccent normalization: 'Açúcar Granulado Uniao' matches 'acucar granulado' search_term."""
    result, _score, _mt = match_ingredient("Açúcar Granulado União 1kg", real_ingredients)
    assert result is not None
    assert result["canonical_name"] == "Açúcar Cristal / Refinado"

    result, _score, _mt = match_ingredient("Açúcar Refinado União 1kg", real_ingredients)
    assert result is not None
    assert result["canonical_name"] == "Açúcar Cristal / Refinado"


def test_gate_stopwords_and_digits_filtered(real_ingredients):
    """Gate keywords: numeric tokens (1KG, 500G) and stopwords (COM, SEM, PARA) filtered."""
    from parsers.matcher import extract_all_keywords

    kw = extract_all_keywords(real_ingredients)
    # numeric tokens removed
    assert "1KG" not in kw
    assert "500G" not in kw
    assert "395G" not in kw
    assert "12X395G" not in kw
    # stopwords removed
    assert "COM" not in kw
    assert "SEM" not in kw
    assert "PARA" not in kw
    assert "TIPO" not in kw
    assert "TOP" not in kw
    # legitimate ingredient tokens remain
    assert "CONDENSADO" in kw
    assert "CHOCOLATE" in kw
    assert "MANTEIGA" in kw


@pytest.mark.parametrize(
    "product_text, expected",
    [
        # new config: "mil cores" -> Granulado Colorido
        ("Granulado Crocante Mil Cores 2,1kg", "Granulado Colorido"),
        ("Confeito Mil Cores Chocolate Mavalério 500g", "Granulado Colorido"),
        # new config: "acucar granulado" -> Açúcar Cristal
        ("Açúcar Granulado União 1kg", "Açúcar Cristal / Refinado"),
        ("Açúcar Granulado União 5kg", "Açúcar Cristal / Refinado"),
        # new config: "choco power ball" -> Micro Ball
        ("Choco Power Ball Mavalerio 300g", "Micro Ball"),
        # exclude: "ovo po" / "pó" -> Ovos rejected
        ("OVO PÓ 1Kg", None),
        # exclude: essencia para outros sabores -> Baunilha rejected
        ("Essência Cookie Leite Condensado com Chocolate Concentrada", "Leite Condensado Integral"),
        # exclude: "chocolate" no Creme de Leite
        ("Creme de Leite Chocolate 200g", None),
        # exclude: "festa" removed from Granulado Colorido -> Faça A Festa matches
        ("Chocolate Granulado Faça A Festa Colorido 130g", "Granulado Colorido"),
    ],
)
def test_phase2_config_cases(real_ingredients, product_text, expected):
    """End-to-end cases covering Phase 2 YAML config changes."""
    result, _score, _mt = match_ingredient(product_text, real_ingredients)
    if expected is None:
        assert result is None, f"FP: {product_text} -> {result}"
    else:
        assert result is not None, f"Missed: {product_text}"
        assert result["canonical_name"] == expected, (
            f"{product_text} -> {result['canonical_name']} (expected {expected})"
        )


def test_fuzzy_coverage_penalty_reduces_thief_scores(real_ingredients):
    """Thief term 'chocolate po' should be penalized when only 'chocolate' present."""
    from parsers.matcher import _penalize_score, clean_text
    from rapidfuzz import fuzz

    product = clean_text("Chocolate Granulado Dori 300g")
    term = clean_text("Chocolate em Pó 50% Cacau")
    raw = fuzz.token_set_ratio(product, term)  # ~86
    penalized = _penalize_score(raw, product, term)
    assert penalized < 80, f"Penalty failed: raw={raw}, penalized={penalized}"

    # legitimate match retains high score
    product2 = clean_text("Chocolate em Pó 50% Cacau Melken 1kg")
    raw2 = fuzz.token_set_ratio(product2, term)
    penalized2 = _penalize_score(raw2, product2, term)
    assert penalized2 >= 80, f"Over-penalized legitimate: {penalized2}"
