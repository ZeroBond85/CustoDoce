"""Regressão: extract_brand agora usa fallback global quando ingrediente
não tem marcas (root cause de 53% Desconhecido em prod)."""

from parsers.brand_extractor import extract_brand


ING_WITHOUT_BRANDS = {"canonical_name": "Leite Condensado", "brands": []}
ING_WITH_BRANDS = {"canonical_name": "Leite Condensado", "brands": ["Moça", "Piracanjuba"]}
ALL_INGS = [
    {"canonical_name": "Leite Condensado", "brands": ["Moça", "Piracanjuba"]},
    {"canonical_name": "Creme de Leite", "brands": ["Nestlé", "Piracanjuba"]},
    {"canonical_name": "Chocolate 50%", "brands": ["Harald", "Melken"]},
]


def test_fallback_global_quando_ingredient_sem_brands():
    # Ingrediente alvo sem marcas, mas lista global tem
    assert extract_brand("Leite Condensado Moça 395g", ING_WITHOUT_BRANDS) == "Desconhecido"
    assert extract_brand("Leite Condensado Moça 395g", ING_WITHOUT_BRANDS, all_ingredients=ALL_INGS) == "Moça"


def test_fallback_global_respeita_separadores():
    # Dr. Oetker no global; produto tem "Dr.Oetker" (sem espaço)
    global_ings = [{"canonical_name": "Fermento", "brands": ["Dr. Oetker"]}]
    assert extract_brand("Fermento Dr.Oetker 10g", {"brands": []}, all_ingredients=global_ings) == "Dr. Oetker"


def test_fallback_global_multipalavra_token_set():
    # Tres Coroas multiword via token_set_ratio
    global_ings = [{"canonical_name": "Leite em Pó", "brands": ["Tres Coroas"]}]
    assert extract_brand("Leite Tres Coroas 400g", {"brands": []}, all_ingredients=global_ings) == "Tres Coroas"


def test_fallback_sem_all_ingredients_mantem_desconhecido():
    # Sem all_ingredients → comportamento original (não lê texto)
    assert extract_brand("Leite Moça", ING_WITHOUT_BRANDS) == "Desconhecido"
    assert extract_brand("Leite Moça", ING_WITHOUT_BRANDS, all_ingredients=None) == "Desconhecido"


def test_fallback_global_prioriza_brand_do_ingredient_se_existir():
    # Se ingredient tem marcas, NÃO cai no global (mesmo que global tenha mais)
    # Texto tem "Moça" mas ingredient só tem "Piracanjuba" → não matcheia → Desconhecido
    ing = {"canonical_name": "Leite", "brands": ["Piracanjuba"]}
    global_ings = [{"canonical_name": "Leite", "brands": ["Moça"]}]
    assert extract_brand("Leite Moça 1kg", ing, all_ingredients=global_ings) == "Desconhecido"


def test_sem_falso_positivo_melkenzada():
    ing = {"canonical_name": "Chocolate", "brands": ["Melken"]}
    assert extract_brand("Cobertura Melkenzada 1kg", ing) == "Desconhecido"
    assert extract_brand("Cobertura Melkenzada 1kg", ing, all_ingredients=ALL_INGS) == "Desconhecido"
