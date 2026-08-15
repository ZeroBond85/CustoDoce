import re

from rapidfuzz import fuzz

from services.types import Ingredient

# Tokens de contexto NÃO-alimentar (embalagem, decoração, artesanato).
# Usado como guard-rail extra: se o produto tem um destes tokens E o match é
# por substring curta, rebaixa/bloqueia. Lista hardcoded (heurística fixa de
# domínio — não é config de negócio).
_PACKAGING_TOKENS = frozenset({
    "papel", "caixa", "embalagem", "forma", "forminha", "folha", "chenille",
    "pelúcia", "lembrancinha", "decorativo", "artesanato", "pincel",
    "brinquedo", "festa", "saco", "cartinha", "blister", "haste",
    "adereço", "enfeite", "topper", "marca texto", "caneca", "vela",
})


def has_packaging_tokens(product_text: str) -> bool:
    """Retorna True se o produto contém tokens de contexto não-alimentar.

    Heurística de domínio para FPs onde o ingrediente aparece como
    descrição de cor/decoração ("Amarelo Manteiga", "Papel Granulado Branco").
    """
    product_lower = product_text.lower()
    return any(t in product_lower for t in _PACKAGING_TOKENS)


def extract_all_keywords(ingredients: list[Ingredient]) -> set:
    keywords = set()
    for ing in ingredients:
        for text in [ing.get("canonical_name", "")] + ing.get("aliases", []) + ing.get("search_terms", []):
            for w in text.split():
                clean = re.sub(r"[^A-Z0-9]", "", w.upper())
                if clean and len(clean) > 2:
                    keywords.add(clean)
    return keywords


def has_ingredient_keyword(product_text: str, keywords: set) -> bool:
    product_words = {re.sub(r"[^A-Z0-9]", "", w.upper()) for w in product_text.split() if len(w) > 2}
    return bool(product_words & keywords)


def clean_text(text: str) -> str:
    text = text.upper()
    text = re.sub(r"[^A-Z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


_INGREDIENT_EXCLUDE_CACHE: dict = {}


def _load_exclude_terms(ingredients: list[Ingredient]) -> dict[str, list[str]]:
    """Carrega exclude_terms do YAML e cacheia."""
    key = id(ingredients)
    if key not in _INGREDIENT_EXCLUDE_CACHE:
        _INGREDIENT_EXCLUDE_CACHE[key] = {ing["canonical_name"]: ing.get("exclude_terms", []) for ing in ingredients}
    return _INGREDIENT_EXCLUDE_CACHE[key]


def has_excluded_terms(product_text: str, ingredient: Ingredient) -> bool:
    """Retorna True se o produto contém termo da exclude_terms do ingrediente."""
    terms = ingredient.get("exclude_terms", [])
    if not terms:
        return False
    product_lower = product_text.lower()
    return any(t.lower() in product_lower for t in terms)


def build_alias_list(ingredients: list[Ingredient]) -> list[tuple[str, str, list[str]]]:
    alias_map = []
    for ing in ingredients:
        canonical = ing["canonical_name"]
        aliases = ing.get("aliases", [])
        alias_map.append((canonical, canonical, aliases))
        for alias in aliases:
            alias_map.append((canonical, alias, aliases))
        for search_term in ing.get("search_terms", []):
            alias_map.append((canonical, search_term, aliases))
    return alias_map


def _is_short_term(term: str) -> bool:
    """Termo muito curto (< 2 palavras OU < 8 chars) não pode gerar 'exato' em
    qualquer posição — evita FPs como 'Amarelo Manteiga' (cor) → Manteiga
    ou 'Ovos de Páscoa' (chocolate) → Ovos. Termos de 2+ palavras ("Leite
    Condensado", "Granulado Branco") são substanciais e casam em qualquer posição."""
    words = [w for w in term.split()]
    return len(words) < 2 or len(term.strip()) < 8


def match_exact(product_text: str, ingredient: Ingredient) -> bool:
    product_upper = product_text.upper()
    canonical_upper = ingredient["canonical_name"].upper()

    if canonical_upper in product_upper:
        # Canonical curto ("Manteiga", "Ovos") só gera "exato" se aparecer no
        # INÍCIO do nome do produto (padrão real de e-commerce) — evita FPs
        # onde o termo é só um adjetivo/cor ("Pap Manteiga", "Ovos de Páscoa").
        if _is_short_term(ingredient["canonical_name"]):
            if product_upper.startswith(canonical_upper) or product_upper.startswith(canonical_upper + " "):
                return True
            return False
        return True

    for alias in ingredient.get("aliases", []):
        if alias.upper() in product_upper:
            return True

    for search_term in ingredient.get("search_terms", []):
        if search_term.upper() in product_upper:
            return True

    # Check all words from canonical in product text
    canonical_words = set(canonical_upper.split())
    product_words = set(product_upper.split())
    return len(canonical_words) > 1 and canonical_words.issubset(product_words)


def match_ingredient(
    product_text: str,
    ingredients: list[Ingredient],
    threshold: float = 80.0,
) -> tuple[Ingredient | None, float, str]:
    product_clean = clean_text(product_text)

    best_ingredient = None
    best_score = 0.0
    match_type = "none"

    for ing in ingredients:
        # Respeita exclude_terms: se o produto contém um termo excluído deste
        # ingrediente, ele não pode casar (alinha o matcher com o comportamento
        # do collector, evitando FPs como "Chocolate Cremoso" -> "Chocolate em Pó").
        if has_excluded_terms(product_text, ing):
            continue

        # exact match first
        if match_exact(product_text, ing):
            return ing, 100.0, "exato"

        # fuzzy match on canonical
        canonical_clean = clean_text(ing["canonical_name"])
        score = fuzz.token_set_ratio(product_clean, canonical_clean)
        if score > best_score:
            best_score = score
            best_ingredient = ing
            match_type = "proximo_nome"

        for alias in ing.get("aliases", []):
            alias_clean = clean_text(alias)
            score = fuzz.token_set_ratio(product_clean, alias_clean)
            if score > best_score:
                best_score = score
                best_ingredient = ing
                match_type = "proximo_apelido"

        for search_term in ing.get("search_terms", []):
            search_clean = clean_text(search_term)
            score = fuzz.token_set_ratio(product_clean, search_clean)
            if score > best_score:
                best_score = score
                best_ingredient = ing
                match_type = "proximo_apelido"

    if best_score >= threshold:
        return best_ingredient, best_score, match_type

    return None, best_score, match_type


def rank_ingredients(
    product_text: str,
    ingredients: list[Ingredient],
    top_n: int = 3,
) -> list[tuple[Ingredient, float, str, str]]:
    """Returns list of (ingredient, score, match_type, matched_term)"""
    product_clean = clean_text(product_text)
    candidates = []

    for ing in ingredients:
        canonical_clean = clean_text(ing["canonical_name"])
        score = fuzz.token_set_ratio(product_clean, canonical_clean)
        match_type = "proximo_nome"
        matched_term = ing["canonical_name"]

        for alias in ing.get("aliases", []):
            alias_clean = clean_text(alias)
            alias_score = fuzz.token_set_ratio(product_clean, alias_clean)
            if alias_score > score:
                score = alias_score
                match_type = "proximo_apelido"
                matched_term = alias

        for search_term in ing.get("search_terms", []):
            search_clean = clean_text(search_term)
            search_score = fuzz.token_set_ratio(product_clean, search_clean)
            if search_score > score:
                score = search_score
                match_type = "proximo_apelido"
                matched_term = search_term

        candidates.append((ing, score, match_type, matched_term))

    candidates.sort(key=lambda x: x[1], reverse=True)
    return [(c[0], c[1], c[2], c[3]) for c in candidates[:top_n]]
