import re
from typing import Optional


def extract_brand(product_text: str, ingredient: dict) -> str:
    brands = ingredient.get("brands", [])
    if not brands:
        return "Desconhecido"

    text_upper = product_text.upper()

    for brand in brands:
        brand_upper = brand.upper()
        if re.search(rf"\b{re.escape(brand_upper)}\b", text_upper):
            return brand

    return "Desconhecido"


def extract_brand_from_all(product_text: str, ingredients: list[dict]) -> Optional[str]:
    text_upper = product_text.upper()
    seen = set()
    for ing in ingredients:
        for brand in ing.get("brands", []):
            b_upper = brand.upper()
            if b_upper in seen:
                continue
            seen.add(b_upper)
            if re.search(rf"\b{re.escape(b_upper)}\b", text_upper):
                return brand
    return None
