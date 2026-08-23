import re
import unicodedata

from rapidfuzz import fuzz

from services.types import Ingredient

# Separadores que podem aparecer entre partes da marca ("Dr.Oetker" == "Dr. Oetker")
_BRAND_SEP = r"[\s.\-_]?"
_WORD_SPLIT = re.compile(r"[\s.\-_]+")
_NON_ALPHA = re.compile(r"[^A-Z\s]")


def _normalize_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def _brand_pattern(brand_norm: str) -> str:
    r"""Regex tolerante a separadores: "Dr.Oetker", "Dr. Oetker" e "DROETKER"
    geram o MESMO padrão (DR[\s.\-_]?OETKER). Fronteiras por letra (não dígito)
    preservam "Ninho400g" → Ninho e bloqueiam "Melkenzada" → Melken."""
    parts = [p for p in _WORD_SPLIT.split(brand_norm) if p]
    body = _BRAND_SEP.join(re.escape(p) for p in parts)
    return rf"(?<![A-Z]){body}(?![A-Z])"


def _dedup_brands(brands: list[str], seen: set) -> list[str]:
    out = []
    for brand in brands or []:
        key = brand.upper()
        if not brand or key in seen:
            continue
        seen.add(key)
        out.append(brand)
    return out


def _fuzzy_score(text_norm: str, brand_norm: str, threshold: float = 80.0) -> float:
    """Melhor score fuzzy: token_set (multi-palavra: 'Tres Coroas' em texto
    bag-of-words) OU ratio palavra-a-palavra (typo único: 'Piracajuba')."""
    best = fuzz.token_set_ratio(text_norm, brand_norm)
    if best >= threshold:
        return best
    for word in set(_NON_ALPHA.sub(" ", text_norm).split()):
        s = fuzz.ratio(word, brand_norm)
        if s > best:
            best = s
    return best


def _match_brands(text_norm: str, brands: list[str], threshold: float = 80.0) -> str | None:
    """Pipeline 3 níveis sobre uma lista de marcas. Retorna o original (case
    do YAML) ou None."""
    brands = _dedup_brands(brands, set())

    # Level 1+2: padrão com fronteiras e separadores flexíveis
    for brand in brands:
        pattern = _brand_pattern(_normalize_accents(brand.upper()))
        m = re.search(pattern, text_norm)
        if m:
            return brand

    # Level 3: fuzzy (token_set para multiword + ratio por palavra)
    scored = sorted(
        ((brand, _fuzzy_score(text_norm, _normalize_accents(brand.upper()), threshold)) for brand in brands),
        key=lambda x: x[1],
        reverse=True,
    )
    for brand, score in scored:
        if score >= threshold:
            return brand
    return None


def extract_brand(
    product_text: str,
    ingredient: Ingredient,
    all_ingredients: list[Ingredient] | None = None,
) -> str:
    """Extrai marca do texto do produto.

    Root-cause fix (2026-08-21): quando o ingrediente NÃO tem marcas cadastradas,
    antes retornava "Desconhecido" sem nem ler o texto — hoje 53% dos preços em
    prod estão como Desconhecido por isso. Com `all_ingredients`, cai para a
    lista global dedup de todas as marcas conhecidas.
    """
    if not product_text:
        return "Desconhecido"

    text_norm = _normalize_accents(product_text.upper())
    brands = ingredient.get("brands") or []

    result = _match_brands(text_norm, brands)
    if result is None and not brands and all_ingredients:
        global_brands = [b for ing in all_ingredients for b in (ing.get("brands") or [])]
        result = _match_brands(text_norm, global_brands)

    return result if result is not None else "Desconhecido"


def extract_brand_from_all(product_text: str, ingredients: list[Ingredient], threshold: float = 85.0) -> str | None:
    if not ingredients or not product_text:
        return None

    text_norm = _normalize_accents(product_text.upper())
    seen: set = set()
    all_brands: list[str] = []
    for ing in ingredients:
        for brand in ing.get("brands") or []:
            if brand and brand.upper() not in seen:
                seen.add(brand.upper())
                all_brands.append(brand)
    return _match_brands(text_norm, all_brands, threshold=threshold)
