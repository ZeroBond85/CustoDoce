import re

PRICE_RE = re.compile(
    r"(?:R\$\s*)?([1-9]\d{0,2}(?:\.\d{3})*\s*,\d{2})\b"
)
STOP_WORDS = {
    "somente", "sexta", "sábado",
    "sabado", "domingo", "estoque", "limitado", "limite", "unidade",
    "unidades", "cliente", "clientes", "cada", "preço", "preco",
    "promoção", "promocao", "confira", "apenas", "www", "http",
    "facebook", "instagram", "whatsapp", "telefone", "celular",
    "sac", "não", "nao", "nº", "numero", "número", "página", "pagina",
    "encarte", "folheto", "ofertas", "parcele",
    "cartão", "cartao", "crédito", "credito", "débito", "debito",
    "dinheiro", "total", "subtotal", "desconto", "economize",
    "condições", "condicoes", "geral",
}

VALIDITY_RE = re.compile(
    r"(?:válido|valido|válida|valida)\s*(?:até|ate)\s*:?\s*\d{2}/\d{2}(?:/\d{2,4})?",
    re.I,
)
DATE_RE = re.compile(
    r"(?:até|ate)\s*:?\s*\d{2}/\d{2}(?:/\d{2,4})?",
    re.I,
)


def clean_line(line: str) -> str:
    line = line.strip().strip("|").strip()
    line = re.sub(r"\s+", " ", line)
    return line


def is_stop_line(line: str) -> bool:
    words = set(line.lower().split())
    return bool(words & STOP_WORDS) or len(line) < 3 or line.isdigit()


def is_validity_line(line: str) -> bool:
    return bool(VALIDITY_RE.search(line) or DATE_RE.search(line))


def extract_validity_text(line: str) -> str:
    m = VALIDITY_RE.search(line)
    if m:
        return m.group(0)
    m = DATE_RE.search(line)
    if m:
        return m.group(0)
    return ""


def extract_price(line: str) -> float | None:
    m = PRICE_RE.search(line)
    if m:
        raw = m.group(1)
        raw = raw.replace(".", "")
        raw = raw.replace(",", ".")
        try:
            return float(raw)
        except ValueError:
            pass
    return None


def extract_unit(text: str) -> str:
    from parsers.unit_extractor import extract_unit as _extract_unit
    return _extract_unit(text)


def parse_flyer_lines(lines: list[str]) -> list[dict]:
    products = []
    buffer = []
    last_validity = ""

    for raw_line in lines:
        line = clean_line(raw_line)
        if not line:
            continue

        if is_validity_line(line):
            last_validity = extract_validity_text(line)
            continue

        if is_stop_line(line):
            continue

        price = extract_price(line)

        if price is not None:
            remaining = PRICE_RE.sub("", line).strip()
            if remaining:
                buffer.append(remaining)
            name = " ".join(buffer).strip() if buffer else remaining
            name = re.sub(r"\s+", " ", name).strip()

            if name and len(name) > 3:
                unit = extract_unit(name)
                validity = last_validity
                last_validity = ""
                products.append({
                    "product": name,
                    "price": price,
                    "unit": unit,
                    "validity_raw": validity,
                    "brand": "",
                })
            buffer = []
        else:
            buffer.append(line)

    return products


def extract_lines_from_text(text: str) -> list[str]:
    lines = text.split("\n")
    seen = set()
    deduped = []
    for line in lines:
        key = clean_line(line).lower()
        if key and key not in seen:
            seen.add(key)
            deduped.append(line)
    return deduped
