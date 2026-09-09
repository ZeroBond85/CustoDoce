import re

from services.types import PriceNormalized


class NormalizedPrice:
    def __init__(
        self, qty: int, unit_kg: float, total_kg: float, price_per_kg: float, price_per_un: float
    ) -> None:
        self.qty = qty
        self.unit_kg = unit_kg
        self.total_kg = total_kg
        self.price_per_kg = price_per_kg
        self.price_per_un = price_per_un

    def to_dict(self) -> PriceNormalized:
        return {
            "qty": self.qty,
            "unit_kg": round(self.unit_kg, 4),
            "total_kg": round(self.total_kg, 4),
            "price_per_kg": round(self.price_per_kg, 2),
            "price_per_un": round(self.price_per_un, 2),
        }

    def __repr__(self) -> str:
        return (
            f"<Normalized: R${self.price_per_kg:.2f}/kg, "
            f"R${self.price_per_un:.2f}/un, "
            f"{self.qty} x {self.unit_kg * 1000:.0f}g>"
        )


_WEIGHT_PATTERNS = [
    re.compile(r"(\d+)\s*x\s*([\d,.]+)\s*(kg|g|ml|litro|litros)", re.I),
    re.compile(r"([\d,.]+)\s*(kg|g|ml|litro|litros)", re.I),
    re.compile(r"(\d+)\s*[xX]\s*([\d,.]+)(?:\s*(kg|g|ml|litro|litros))?", re.I),
]

_UNIT_PATTERNS = [
    re.compile(r"(\d+)\s*(uni|un|und|unidade|uns?)\b", re.I),
    re.compile(r"pacote\s*com\s*(\d+)", re.I),
    re.compile(r"cx\s*(?:com\s*)?(\d+)", re.I),
    re.compile(r"cx\w*\s*(?:com\s*)?(\d+)", re.I),
]


def parse_unit(raw_unit: str) -> NormalizedPrice | None:
    if not raw_unit or not isinstance(raw_unit, str):
        return None

    raw_unit = raw_unit.strip().replace(",", ".")

    qty = 1
    unit_kg = 0.0

    for pattern in _WEIGHT_PATTERNS:
        match = pattern.search(raw_unit)
        if match:
            groups = match.groups()
            if len(groups) == 3:
                qty = int(groups[0])
                weight_str = groups[1]
                weight_unit = groups[2] if groups[2] else "g"
            else:
                qty = 1
                weight_str = groups[0]
                weight_unit = groups[1] if len(groups) > 1 else "g"

            try:
                weight = float(weight_str)
            except ValueError:
                continue

            if weight_unit and weight_unit.lower() in ("kg", "kilo", "kilograma"):
                unit_kg = weight
            elif weight_unit and weight_unit.lower() in ("g", "gr", "grama") or (
                weight_unit and weight_unit.lower() in ("ml", "mililitro")
            ):
                unit_kg = weight / 1000
            elif weight_unit and weight_unit.lower() in ("litro", "litros"):
                unit_kg = weight  # 1 litro ~ 1kg for liquids
            else:
                unit_kg = weight / 1000

            # Check for explicit unit count
            for u_pattern in _UNIT_PATTERNS:
                u_match = u_pattern.search(raw_unit)
                if u_match:
                    qty = int(u_match.group(1))

            total_kg = qty * unit_kg
            normalized = NormalizedPrice(
                qty=qty,
                unit_kg=unit_kg,
                total_kg=total_kg,
                price_per_kg=0.0,
                price_per_un=0.0,
            )
            return normalized

    return None


def normalize_price(raw_price: float, raw_unit: str) -> NormalizedPrice | None:
    if raw_price <= 0:
        return None

    parsed = parse_unit(raw_unit)
    if parsed is None:
        return None

    # Use rounding to 4 decimals before final round to 2 to avoid float precision issues
    # 42.9 / 12 = 3.575.
    # We want to be consistent.
    parsed.price_per_kg = round(raw_price / parsed.total_kg, 4)
    parsed.price_per_un = round(raw_price / parsed.qty, 4)

    # The to_dict() method already rounds to 2.
    return parsed


# ─── Name Cleaning for Matcher ───────────────────────────────────────────────

# Unicode-aware word boundary: use (?<!\p{L})\p{L}|\p{L}(?!\p{L}) equivalent
# Python re doesn't support \p{}, so we use a custom approach:
# - \b matches between \w and \W, but \w is ASCII-only by default
# - We'll use explicit boundary checks with (?<!\w) and (?!\w) which do work
#   with most non-ASCII when the pattern itself contains those chars

_NAME_CLEAN_PATTERNS = [
    # Remove pack sizes like "cx 12x395g", "12x395g", "12x 395g", "cx 12x 395g"
    re.compile(r"\b\d+\s*[xX]\s*\d+\s*(kg|g|ml|l|lt|un|unids?)\b", re.I),
    re.compile(r"\b\d+\s*[xX]\s*\d+\b", re.I),
    re.compile(r"\bcx\s+\d+[xX]\s*\d+", re.I),
    re.compile(r"\bcx\s+\d+", re.I),
    # Remove standalone weights like "395g", "1kg", "500ml"
    re.compile(r"\b\d+[.,]\d+\s*(kg|g|ml|l|lt|un|unids?)\b", re.I),
    re.compile(r"\b\d+\s*(kg|g|ml|l|lt|un|unids?)\b", re.I),
    # Remove parenthetical content
    re.compile(r"\([^)]*\)", re.I),
    # Remove suffixes after slash
    re.compile(r"\/[^\/]*$", re.I),
    # Remove common promotional prefixes and suffixes
    re.compile(r"^(promo|oferta|promocao|promoção|desconto|super|mega|ultra)\s+", re.I),
    re.compile(r"\s+(promo|oferta|promocao|promoção|desconto|super|mega|ultra)$", re.I),
    re.compile(r"\s+promo$", re.I),  # "promo" at end
    # Remove multiple spaces
    re.compile(r"\s{2,}"),
]

# Canonical name replacements for common abbreviations
# Using (?<!\w) and (?!\w) which work better with non-ASCII when the
# pattern chars are present in the text
_NAME_REPLACEMENTS = {
    # Word boundary assertions for better non-ASCII handling
    r"(?<!\w)choc(?!\w)": "chocolate",
    r"(?<!\w)chocol(?!\w)": "chocolate",
    r"(?<!\w)leite condens(?!\w)": "leite condensado",
    r"(?<!\w)leite cond(?!\w)": "leite condensado",
    r"(?<!\w)creme leite(?!\w)": "creme de leite",
    r"(?<!\w)creme de avel(?!\w)": "creme de avelã",
    r"(?<!\w)creme avela(?!\w)": "creme de avelã",
    r"(?<!\w)granulado(?!\w)": "granulado",
    r"(?<!\w)acucar(?!\w)": "açúcar",
    r"(?<!\w)acucar masc(?!\w)": "açúcar mascavo",
    r"(?<!\w)acucar conf(?!\w)": "açúcar confeiteiro",
    r"(?<!\w)far trigo(?!\w)": "farinha de trigo",
    r"(?<!\w)fermento bio(?!\w)": "fermento biologico",
    r"(?<!\w)ess baunilha(?!\w)": "essencia de baunilha",
    r"(?<!\w)ess vainilla(?!\w)": "essencia de vainilla",
    r"(?<!\w)cx(?!\w)": "",
    r"(?<!\w)promo(?!\w)": "",
    r"(?<!\w)oferta(?!\w)": "",
    r"(?<!\w)promocao(?!\w)": "",
    r"(?<!\w)promocão(?!\w)": "",
    r"(?<!\w)desconto(?!\w)": "",
    r"(?<!\w)super(?!\w)": "",
    r"(?<!\w)mega(?!\w)": "",
    r"(?<!\w)ultra(?!\w)": "",
}


def clean_name(name: str) -> str:
    """
    Limpa nome de produto para matching, removendo ruído de embalagem,
    medidas, parênteses, sufixos promocionais e normalizando abreviações.

    Exemplo:
        "Chocolate ao Leite 50% cx 12x395g (promo)" → "chocolate ao leite 50%"
    """
    if not name or not isinstance(name, str):
        return ""

    name = name.strip().lower()

    # Apply removal patterns
    for pattern in _NAME_CLEAN_PATTERNS:
        name = pattern.sub(" ", name)

    # Apply canonical replacements with word boundaries (longest patterns first to avoid partial matches)
    for old, new in sorted(_NAME_REPLACEMENTS.items(), key=lambda x: len(x[0]), reverse=True):
        name = re.sub(old, new, name)

    # Normalize whitespace
    name = " ".join(name.split())

    return name.strip()
