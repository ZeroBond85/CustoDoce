import re
import unicodedata
from typing import Any, cast

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


# Stopwords que não identificam ingrediente (não podem passar o keyword gate).
# "COM"/"SEM"/"PARA"/"TIPO"/"SACO"/"LATA"/"POTE"/"MIX"/"TOP" etc. aparecem em
# qualquer produto e deixariam feijão/arroz/sabonete passarem o gate.
_KEYWORD_STOPWORDS = {
    "DE", "DA", "DO", "EM", "COM", "SEM", "PARA", "TIPO", "TOP", "MIX",
    "FOOD", "SACO", "LATA", "POTE", "CAIXA", "PACOTE", "EMBALAGEM", "FORM",
    "FOLHA", "TIPOS", "SABORES", "TODOS", "VARIOS", "C", "UN", "CX", "PC",
    "PT", "GR", "G", "KG", "ML", "UNIDADE", "UNIDADES", "BARRA", "TABLETE",
}


def extract_all_keywords(ingredients: list[Ingredient]) -> set[str]:
    keywords: set[str] = set()
    for ing in ingredients:
        for text in [ing.get("canonical_name", "")] + cast(list[str], ing.get("aliases") or []) + cast(list[str], ing.get("search_terms") or []):
            for w in text.split():
                clean = re.sub(r"[^A-Z0-9]", "", w.upper())
                # Ignora tokens com dígitos ("1KG", "500G", "12X395G") — tamanho
                # não identifica ingrediente e deixaria qualquer produto passar.
                if clean and len(clean) > 2 and not any(ch.isdigit() for ch in clean) and clean not in _KEYWORD_STOPWORDS:
                    keywords.add(clean)
    return keywords


def has_ingredient_keyword(product_text: str, keywords: set[str]) -> bool:
    product_words = {re.sub(r"[^A-Z0-9]", "", w.upper()) for w in product_text.split() if len(w) > 2}
    return bool(product_words & keywords)


def clean_text(text: str) -> str:
    text = text.upper()
    text = re.sub(r"[^A-Z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


_INGREDIENT_EXCLUDE_CACHE: dict[Any, dict[str, list[str]]] = {}


def _load_exclude_terms(ingredients: list[Ingredient]) -> dict[str, list[str]]:
    """Carrega exclude_terms do YAML e cacheia."""
    key = id(ingredients)
    if key not in _INGREDIENT_EXCLUDE_CACHE:
        _INGREDIENT_EXCLUDE_CACHE[key] = {ing["canonical_name"]: cast(list[str], ing.get("exclude_terms") or []) for ing in ingredients}
    return _INGREDIENT_EXCLUDE_CACHE[key]


def has_excluded_terms(product_text: str, ingredient: Ingredient) -> bool:
    """Retorna True se o produto contém termo da exclude_terms do ingrediente."""
    terms = cast(list[str], ingredient.get("exclude_terms") or [])
    if not terms:
        return False
    product_lower = product_text.lower()
    return any(t.lower() in product_lower for t in terms)


def build_alias_list(ingredients: list[Ingredient]) -> list[tuple[str, str, list[str]]]:
    alias_map: list[tuple[str, str, list[str]]] = []
    for ing in ingredients:
        canonical = ing["canonical_name"]
        aliases = cast(list[str], ing.get("aliases") or [])
        alias_map.append((canonical, canonical, aliases))
        for alias in aliases:
            alias_map.append((canonical, alias, aliases))
        for search_term in cast(list[str], ing.get("search_terms") or []):
            alias_map.append((canonical, search_term, aliases))
    return alias_map


def _is_short_term(term: str) -> bool:
    """Termo muito curto (< 2 palavras OU < 8 chars) não pode gerar 'exato' em
    qualquer posição — evita FPs como 'Amarelo Manteiga' (cor) → Manteiga
    ou 'Ovos de Páscoa' (chocolate) → Ovos. Termos de 2+ palavras ("Leite
    Condensado", "Granulado Branco") são substanciais e casam em qualquer posição."""
    words = list(term.split())
    return len(words) < 2 or len(term.strip()) < 8


def _deaccent(text: str) -> str:
    """Remove acentos e normaliza para ASCII ('AÇÚCAR' → 'ACUCAR'). Permite que
    aliases/search_terms sem acento casem com produtos acentuados e vice-versa
    ('acucar granulado' em 'Açúcar Granulado Uniao Docucar 1kg')."""
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


def _term_at_word_boundary(product_upper: str, term_upper: str) -> bool:
    """True se o termo aparece como PALAVRA inteira (não substring de palavra
    maior). Evita FPs como search_term 'cl' (Creme de Leite) casando
    'Chocolate CLassic' ou search_term 'baunilha' casando 'Baunilhado'.
    Preserva matches legítimos de marcas/termos curtos ('ninho' em
    'Leite em Pó Ninho 400g')."""
    pattern = r"(?<![A-Z0-9])" + re.escape(term_upper) + r"(?![A-Z0-9])"
    return re.search(pattern, product_upper) is not None


def _token_coverage(product_clean: str, term_clean: str) -> float:
    """Fração dos tokens do TERMO presentes no produto. Penaliza o flaw do
    `token_set_ratio`: interseção de poucos tokens genéricos ('chocolate po'
    vs produto que só contém 'chocolate') gera 86+ sem os tokens do termo
    estarem de fato no produto."""
    product_tokens = set(product_clean.split())
    term_tokens = set(term_clean.split())
    if not term_tokens:
        return 0.0
    return len(product_tokens & term_tokens) / len(term_tokens)


_FUZZY_COVERAGE_PENALTY = 0.25
# Termos de 1 palavra: token_set_ratio dá 100 se o token aparece em QUALQUER
# posição ('Ovos' em 'Macarrão com Ovos'). Para esses, a cobertura deve ser
# medida em relação ao PRODUTO: quantos tokens do produto o termo explica.
# 'Macarrão ... Ovos 500g' → 1/5 = 0.2 → forte penalidade; 'Ovos brancos 30un'
# → 1/3 = 0.33 → ainda penalizado, mas o match_exact (startswith) já resolve.
_SINGLE_WORD_PRODUCT_COVERAGE = True
# Só aplica a penalidade de cobertura do PRODUTO para termos de 1 palavra quando
# o produto tem >4 tokens. Produtos curtos ('Leite Condensado', 'Chocolate 50%')
# não devem ser derrubados pela fração de tokens explicada — a cobertura do termo
# (token_set) já é suficiente e penalidade extra mata matches legítimos.
_SINGLE_WORD_MIN_PRODUCT_TOKENS = 4


def _penalize_score(score: float, product_clean: str, term_clean: str) -> float:
    """Aplica penalidade de cobertura ao score fuzzy. coverage=1.0 → intacto;
    coverage=0.0 → score*(1-penalty). Matches onde o termo compartilha só uma
    fração dos tokens com o produto são rebaixados (vão para review_queue).

    Para termos de 1 palavra, usa cobertura do PRODUTO (tokens do termo /
    tokens do produto): 'Ovos' isolado dentro de 'Macarrão com Ovos' explica
    fração mínima do produto → penalidade forte. token_set_ratio de termo
    monopalavra é inútil (sempre 100 quando presente). Produtos curtos (<=4
    tokens) pulam essa penalidade para não matar matches legítimos."""
    coverage = _token_coverage(product_clean, term_clean)
    if _SINGLE_WORD_PRODUCT_COVERAGE and len(term_clean.split()) == 1:
        product_tokens = set(product_clean.split())
        if not product_tokens:
            return score
        if len(product_tokens) <= _SINGLE_WORD_MIN_PRODUCT_TOKENS:
            return score * (1.0 - _FUZZY_COVERAGE_PENALTY * (1.0 - coverage))
        term_tokens = set(term_clean.split())
        coverage = len(product_tokens & term_tokens) / len(product_tokens)
    return score * (1.0 - _FUZZY_COVERAGE_PENALTY * (1.0 - coverage))


def match_exact(product_text: str, ingredient: Ingredient) -> bool:
    product_upper = product_text.upper()
    canonical_upper = ingredient["canonical_name"].upper()
    # Versões sem acento para robustez a variações de acentuação no e-commerce
    # ("Açúcar Granulado Uniao" casa com search_term "acucar granulado").
    product_deac = _deaccent(product_upper)
    canonical_deac = _deaccent(canonical_upper)

    if canonical_upper in product_upper or canonical_deac in product_deac:
        # Canonical curto ("Manteiga", "Ovos") só gera "exato" se aparecer no
        # INÍCIO do nome do produto (padrão real de e-commerce) — evita FPs
        # onde o termo é só um adjetivo/cor ("Pap Manteiga", "Ovos de Páscoa").
        if _is_short_term(ingredient["canonical_name"]):
            return product_upper.startswith(canonical_upper) or product_upper.startswith(
                canonical_upper + " "
            ) or product_deac.startswith(canonical_deac) or product_deac.startswith(canonical_deac + " ")
        return True

    for alias in cast(list[str], ingredient.get("aliases") or []):
        alias_upper = alias.upper()
        alias_deac = _deaccent(alias_upper)
        if _is_short_term(alias):
            if _term_at_word_boundary(product_upper, alias_upper) or _term_at_word_boundary(
                product_deac, alias_deac
            ):
                return True
        elif alias_upper in product_upper or alias_deac in product_deac:
            return True

    for search_term in cast(list[str], ingredient.get("search_terms") or []):
        term_upper = search_term.upper()
        term_deac = _deaccent(term_upper)
        if _is_short_term(search_term):
            if _term_at_word_boundary(product_upper, term_upper) or _term_at_word_boundary(
                product_deac, term_deac
            ):
                return True
        elif term_upper in product_upper or term_deac in product_deac:
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

    best_ingredient: Ingredient | None = None
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
        score = _penalize_score(fuzz.token_set_ratio(product_clean, canonical_clean), product_clean, canonical_clean)
        if score > best_score:
            best_score = score
            best_ingredient = ing
            match_type = "proximo_nome"

        for alias in cast(list[str], ing.get("aliases") or []):
            alias_clean = clean_text(alias)
            score = _penalize_score(fuzz.token_set_ratio(product_clean, alias_clean), product_clean, alias_clean)
            if score > best_score:
                best_score = score
                best_ingredient = ing
                match_type = "proximo_apelido"

        for search_term in cast(list[str], ing.get("search_terms") or []):
            search_clean = clean_text(search_term)
            score = _penalize_score(fuzz.token_set_ratio(product_clean, search_clean), product_clean, search_clean)
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
    candidates: list[tuple[Ingredient, float, str, str]] = []

    for ing in ingredients:
        canonical_clean = clean_text(ing["canonical_name"])
        score = _penalize_score(fuzz.token_set_ratio(product_clean, canonical_clean), product_clean, canonical_clean)
        match_type = "proximo_nome"
        matched_term = ing["canonical_name"]

        for alias in cast(list[str], ing.get("aliases") or []):
            alias_clean = clean_text(alias)
            alias_score = _penalize_score(fuzz.token_set_ratio(product_clean, alias_clean), product_clean, alias_clean)
            if alias_score > score:
                score = alias_score
                match_type = "proximo_apelido"
                matched_term = alias

        for search_term in cast(list[str], ing.get("search_terms") or []):
            search_clean = clean_text(search_term)
            search_score = _penalize_score(
                fuzz.token_set_ratio(product_clean, search_clean), product_clean, search_clean
            )
            if search_score > score:
                score = search_score
                match_type = "proximo_apelido"
                matched_term = search_term

        candidates.append((ing, score, match_type, matched_term))

    candidates.sort(key=lambda x: x[1], reverse=True)
    return [(c[0], c[1], c[2], c[3]) for c in candidates[:top_n]]
