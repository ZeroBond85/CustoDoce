import re
from typing import Optional

from rapidfuzz import fuzz


def extract_brand(product_text: str, ingredient: dict) -> str:
    brands = ingredient.get("brands", [])
    if not brands:
        return "Desconhecido"

    text_upper = product_text.upper()

    # Level 1: exact word boundary match
    for brand in brands:
        brand_upper = brand.upper()
        if re.search(rf"\b{re.escape(brand_upper)}\b", text_upper):
            return brand

    # Level 2: substring match (brand not embedded inside another word)
    for brand in brands:
        brand_upper = brand.upper()
        if re.search(rf"(?<![A-Z]){re.escape(brand_upper)}(?![A-Z])", text_upper):
            return brand

    # Level 3: fuzzy match per word (RapidFuzz ratio >= 80 on each product word vs brand)
    product_words = re.sub(r"[^A-Z\s]", " ", product_text.upper()).split()
    best_brand = "Desconhecido"
    best_score = 0
    for brand in brands:
        brand_upper = brand.upper()
        for word in set(product_words):
            score = fuzz.ratio(word, brand_upper)
            if score > best_score:
                best_score = score
                best_brand = brand if score >= 80 else "Desconhecido"

    return best_brand


def extract_brand_from_all(product_text: str, ingredients: list[dict], threshold: float = 85.0) -> Optional[str]:
    if not ingredients:
        return None

    text_upper = product_text.upper()
    seen = set()
    best_brand = None
    best_score = 0

    for ing in ingredients:
        for brand in ing.get("brands", []):
            b_upper = brand.upper()
            if b_upper in seen:
                continue
            seen.add(b_upper)

            if re.search(rf"\b{re.escape(b_upper)}\b", text_upper):
                return brand

    for ing in ingredients:
        for brand in ing.get("brands", []):
            b_upper = brand.upper()
            if b_upper in seen:
                continue
            seen.add(b_upper)

            if re.search(rf"(?<![A-Z]){re.escape(b_upper)}(?![A-Z])", text_upper):
                return brand

    seen.clear()
    product_words = re.sub(r"[^A-Z\s]", " ", text_upper).split()
    for ing in ingredients:
        for brand in ing.get("brands", []):
            b_upper = brand.upper()
            if b_upper in seen:
                continue
            seen.add(b_upper)

            for word in set(product_words):
                score = fuzz.ratio(word, b_upper)
                if score > best_score:
                    best_score = score
                    best_brand = brand if score >= threshold else None

    return best_brand
