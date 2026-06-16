import re

PRICE_RE = re.compile(
    r"(?:R\$\s*)?([1-9]\d{0,2}(?:\.\d{3})*,\d{2})\b"
)
UNIT_RE = re.compile(
    r"(\d+\s*x\s*[\d.,]+\s*(?:kg|g|ml|un)\b"
    r"|[\d.,]+\s*(?:kg|g|ml|un)\b"
    r"|cx\s*(?:com\s*)?\d+\s*(?:uni)?\b"
    r"|lata\s*[\d.,]+\s*(?:kg|g)?\b"
    r"|pacote\s*[\d.,]+\s*(?:kg|g)?\b)",
    re.I,
)

STOP_WORDS = {
    "válido", "valido", "válida", "valida", "válidas", "validas",
    "válidos", "validos", "até", "ate", "somente", "sexta", "sábado",
    "sabado", "domingo", "estoque", "limitado", "limite", "unidade",
    "unidades", "cliente", "clientes", "cada", "preço", "preco",
    "promoção", "promocao", "confira", "apenas", "www", "http",
    "facebook", "instagram", "whatsapp", "telefone", "celular",
    "sac", "não", "nao", "nº", "numero", "número", "página", "pagina",
    "encarte", "folheto", "ofertas", "ofertas", "válidas", "parcele",
    "cartão", "cartao", "crédito", "credito", "débito", "debito",
    "dinheiro", "total", "subtotal", "desconto", "economize",
    "condições", "condicoes", "geral",
}


def clean_line(line: str) -> str:
    line = line.strip().strip("|").strip()
    line = re.sub(r"\s+", " ", line)
    return line


def is_stop_line(line: str) -> bool:
    words = set(line.lower().split())
    return bool(words & STOP_WORDS) or len(line) < 3 or line.isdigit()


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
    m = UNIT_RE.search(text)
    return m.group(1).strip() if m else ""


def parse_flyer_lines(lines: list[str]) -> list[dict]:
    products = []
    buffer = []

    for raw_line in lines:
        line = clean_line(raw_line)
        if not line or is_stop_line(line):
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
                products.append({
                    "product": name,
                    "price": price,
                    "unit": unit,
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
