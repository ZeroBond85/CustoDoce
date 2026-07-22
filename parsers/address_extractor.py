import re
from typing import NamedTuple


class AddressResult(NamedTuple):
    address: str
    confidence: float
    source_field: str  # 'rua', 'bairro', 'cep', 'phone', 'cidade_estado'


ADDRESS_PATTERNS: list[tuple[str, str, float]] = [
    (r"(?:R\.|Rua|Av\.|Avenida|Al\.|Alameda|Travessa|Trav\.|Praça|Pça\.|Estrada|Rodovia)\s+[^,;\n]+,\s*\d+\s*,?\s*[^,;\n]*", "rua_com_numero", 10.0),
    (r"(?:R\.|Rua|Av\.|Avenida)\s+[^,;\n]+", "rua_sem_numero", 7.0),
    (r"(?:CEP|Cep)\s*:?\s*\d{5}-?\d{3}", "cep", 8.0),
    (r"(?:Fone|Tel|Telefone|WhatsApp|Whats|Zap|Contato)\s*:?\s*\(?\d{2}\)?\s*\d{4,5}-?\d{4}", "telefone", 5.0),
    (r"(?:Bairro|Centro|Jardim|Vila\s+\w+|Parque\s+\w+|Residencial\s+\w+|Conjunto\s+\w+)", "bairro", 6.0),
    (r"(?:Centro|Zona\s+(?:Sul|Norte|Leste|Oeste))\s*[-,]?\s*(?:Santos|São\s*Vicente|Praia\s*Grande|Mongaguá|Itanhaém|Peruíbe|Guarujá|São\s*Paulo)", "cidade_estado", 8.0),
]


def extract_address(text: str) -> list[AddressResult]:
    if not text:
        return []

    results: list[AddressResult] = []
    seen: set[str] = set()

    for pattern, field, confidence in ADDRESS_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE):
            match_text = m.group(0).strip()
            # Dedup: skip if very similar to an existing match
            norm = re.sub(r"\s+", " ", match_text.lower())
            if norm in seen:
                continue
            seen.add(norm)
            results.append(AddressResult(address=match_text, confidence=confidence, source_field=field))

    results.sort(key=lambda r: r.confidence, reverse=True)
    return results


def best_address(text: str) -> AddressResult | None:
    extracts = extract_address(text)
    if not extracts:
        return None
    best = extracts[0]
    if best.confidence >= 7.0:
        return best
    # If no high-confidence match but we have multiple clues, combine them
    if len(extracts) >= 2:
        combined = "; ".join(e.address for e in extracts[:3])
        avg_conf = sum(e.confidence for e in extracts[:3]) / min(3, len(extracts))
        return AddressResult(address=combined, confidence=round(avg_conf, 2), source_field="combinado")

    return None
