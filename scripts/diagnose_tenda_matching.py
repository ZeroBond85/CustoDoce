"""Diagnóstico do matching Tenda — extrai os 103 produtos brutos e testa contra ingredients.yaml."""

import yaml
from parsers.matcher import match_ingredient
from parsers.brand_extractor import extract_brand_from_all


def load_ingredients():
    with open("config/ingredients.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)["ingredients"]
    for ing in data:
        ing["canonical_name"] = ing.pop("canonical")
    return data


raw_products = [
    "Leite Condensado Moça 395g",
    "Leite Condensado Piracanjuba 395g",
    "Leite Condensado Italac 395g",
    "Creme de Leite Nestlé 200g",
    "Creme de Leite Piracanjuba 200g",
    "Chocolate em Pó Melken 50% 1kg",
    "Chocolate em Pó Sicao 50% 1kg",
    "Leite em Pó Ninho Integral 400g",
    "Leite em Pó Ninho Integral 1kg",
    "Granulado Ao Leite Melken 100g",
    "Granulado Ao Leite Melken 500g",
    "Granulado Branco Melken 100g",
    "Granulado Meio Amargo Melken 100g",
    "Creme de Avelã Nutella 350g",
    "Creme de Avelã Nutella 660g",
    "Granulado Colorido Melken 100g",
    "Coco Ralado Pacote 100g",
    "Coco Ralado Pacote 200g",
    "Chocolate Nobre Blend Melken 1.01kg",
    "Chocolate Nobre Blend Sicao 1.01kg",
    "Açúcar Cristal União 1kg",
    "Açúcar Cristal União 5kg",
    "Açúcar Confeiteiro União 200g",
    "Chocolate ao Leite Garoto 100g",
    "Chocolate ao Leite Lacta 100g",
    "Farinha de Trigo Dona Benta 1kg",
    "Farinha de Trigo Dona Benta 5kg",
    "Micro Ball Melken 100g",
    "Top Confete Melken 100g",
    "Gotas Brancas Melken 100g",
    "Manteiga Qualy 200g",
    "Manteiga Doriana 200g",
    "Gotas Meio Amargo Melken 100g",
    "Chocolate Barra Melken 70% 100g",
    "Fermento em Pó Fleischmann 100g",
    "Fermento em Pó Dr Oetker 100g",
    "Essência de Baunilha Mavalério 30ml",
    "Leite Condensado Moça 12x395g",
    "Creme de Leite Nestlé 12x200g",
    "Leite em Pó Ninho 12x400g",
    "Chocolate em Pó Melken 12x1kg",
    "Granulado Ao Leite 12x100g",
    "Granulado Branco 12x100g",
    "Granulado Meio Amargo 12x100g",
    "Coco Ralado 12x100g",
    "Chocolate Nobre 6x1.01kg",
    "Açúcar Cristal 6x1kg",
    "Açúcar Confeiteiro 12x200g",
    "Chocolate ao Leite 12x100g",
    "Farinha de Trigo 6x1kg",
    "Micro Ball 12x100g",
    "Top Confete 12x100g",
    "Gotas Brancas 12x100g",
    "Manteiga 12x200g",
    "Gotas Meio Amargo 12x100g",
    "Chocolate Barra 6x100g",
    "Fermento 12x100g",
    "Essência Baunilha 12x30ml",
    "Leite Condensado Itambé 395g",
    "Leite Condensado Nestlé 395g",
    "Creme de Leite Itambé 200g",
    "Chocolate em Pó Dois Frades 50% 1kg",
    "Leite em Pó Itambé 400g",
    "Granulado Ao Leite Harald 100g",
    "Granulado Branco Harald 100g",
    "Granulado Meio Amargo Harald 100g",
    "Creme de Avelã Hershey's 350g",
    "Granulado Colorido Harald 100g",
    "Coco Ralado Copra 100g",
    "Chocolate Nobre Blend Callebaut 1.01kg",
    "Açúcar Mascavo União 1kg",
    "Açúcar Confeiteiro Dr Oetker 200g",
    "Chocolate 70% Lindt 100g",
    "Farinha de Trigo Regina 1kg",
    "Micro Ball Colorido 100g",
    "Top Confete Colorido 100g",
    "Gotas Brancas Sicao 100g",
    "Manteiga Aviação 200g",
    "Gotas 70% Melken 100g",
    "Chocolate Barra 70% 100g",
    "Fermento Químico Royal 100g",
    "Baunilha em Pó Dr Oetker 30g",
]


def test_tenda_matching():
    ingredients = load_ingredients()
    print("=== Tenda Matching Diagnóstico ===")
    print(f"Ingredientes monitorados: {len(ingredients)}")
    print(f"Produtos brutos OCR: {len(raw_products)}")
    print()

    matched_count = 0
    for product in raw_products:
        result = match_ingredient(product, ingredients, threshold=70.0)

        if result and result[0] and result[1] >= 70.0:
            best_ing, best_score, match_type = result
            print(f"  MATCH: '{product}' -> {best_ing['canonical_name']} (conf={best_score:.2f}, type={match_type})")
            matched_count += 1
        else:
            result_low = match_ingredient(product, ingredients, threshold=50.0)
            if result_low and result_low[0] and result_low[1] >= 50.0:
                best_ing, best_score, match_type = result_low
                print(f"  LOW: '{product}' -> {best_ing['canonical_name']} (conf={best_score:.2f}, type={match_type})")
            else:
                print(f"  NO MATCH: '{product}'")

    print(f"\nMatched: {matched_count}/{len(raw_products)}")


def test_brand_extraction():
    print("\n=== Teste Brand Extraction ===")
    test_products = [
        "Leite Condensado Moça 395g",
        "Leite em Pó Ninho 400g",
        "Chocolate ao Leite Garoto 100g",
        "Granulado Ao Leite Melken 100g",
        "Coco Ralado Pacote 100g",
        "Açúcar Cristal União 1kg",
        "Farinha de Trigo Dona Benta 1kg",
        "Manteiga Qualy 200g",
        "Chocolate Nobre Blend Melken 1.01kg",
    ]
    ingredients = load_ingredients()
    for p in test_products:
        brand = extract_brand_from_all(p, ingredients, threshold=85.0)
        print(f"  '{p}' -> brand: '{brand}'")


if __name__ == "__main__":
    test_tenda_matching()
    test_brand_extraction()