import re
from typing import Optional

from rapidfuzz import fuzz


def clean_text(text: str) -> str:
    text = text.upper()
    text = re.sub(r"[^A-Z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def build_alias_list(ingredients: list[dict]) -> list[tuple[str, str, list[str]]]:
    alias_map = []
    for ing in ingredients:
        canonical = ing["canonical"]
        aliases = ing.get("aliases", [])
        alias_map.append((canonical, canonical, aliases))
        for alias in aliases:
            alias_map.append((canonical, alias, aliases))
    return alias_map


def match_exact(product_text: str, ingredient: dict) -> bool:
    product_upper = product_text.upper()
    canonical_upper = ingredient["canonical"].upper()

    if canonical_upper in product_upper:
        return True

    for alias in ingredient.get("aliases", []):
        if alias.upper() in product_upper:
            return True

    # Check all words from canonical in product text
    canonical_words = set(canonical_upper.split())
    product_words = set(product_upper.split())
    if len(canonical_words) > 1 and canonical_words.issubset(product_words):
        return True

    return False


def match_ingredient(
    product_text: str,
    ingredients: list[dict],
    threshold: float = 80.0,
) -> tuple[Optional[dict], float, str]:
    product_clean = clean_text(product_text)

    best_ingredient = None
    best_score = 0.0
    match_type = "none"

    for ing in ingredients:
        # exact match first
        if match_exact(product_text, ing):
            return ing, 100.0, "exact"

        # fuzzy match on canonical
        canonical_clean = clean_text(ing["canonical"])
        score = fuzz.ratio(product_clean, canonical_clean)
        if score > best_score:
            best_score = score
            best_ingredient = ing
            match_type = "fuzzy_canonical"

        for alias in ing.get("aliases", []):
            alias_clean = clean_text(alias)
            score = fuzz.ratio(product_clean, alias_clean)
            if score > best_score:
                best_score = score
                best_ingredient = ing
                match_type = "fuzzy_alias"

    if best_score >= threshold:
        return best_ingredient, best_score, match_type

    return None, best_score, match_type


def rank_ingredients(
    product_text: str,
    ingredients: list[dict],
    top_n: int = 3,
) -> list[tuple[dict, float, str]]:
    product_clean = clean_text(product_text)
    candidates = []

    for ing in ingredients:
        canonical_clean = clean_text(ing["canonical"])
        score = fuzz.ratio(product_clean, canonical_clean)

        for alias in ing.get("aliases", []):
            alias_clean = clean_text(alias)
            alias_score = fuzz.ratio(product_clean, alias_clean)
            score = max(score, alias_score)

        candidates.append((ing, score))

    candidates.sort(key=lambda x: x[1], reverse=True)
    return [(c[0], c[1], "fuzzy") for c in candidates[:top_n]]
