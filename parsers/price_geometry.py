"""Geometric price reconstruction for supermarket flyer OCR output.

Flyer prices are rendered as stylized graphics where the OCR engine emits the
integer ("reais") part and the fractional ("centavos") part as *separate*
regions (the centavos usually appear as a smaller superscript to the upper
right). Naive text parsing therefore scrambles prices. These helpers rebuild
the numeric value geometrically from the OCR region boxes.

The module is intentionally free of OCR/LLM dependencies: it operates purely on
region dicts of the shape::

    {"text": str, "box": [[x, y], [x, y], [x, y], [x, y]], "score": float}

so it can be unit-tested with hand-crafted fixtures and reused by any OCR
backend (RapidOCR, Tesseract, ...).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# --- geometry helpers --------------------------------------------------------

Box = list[list[float]]


def _cx(b: Box) -> float:
    return sum(p[0] for p in b) / 4


def _cy(b: Box) -> float:
    return sum(p[1] for p in b) / 4


def _height(b: Box) -> float:
    return max(p[1] for p in b) - min(p[1] for p in b)


# --- numeric parsing ---------------------------------------------------------

_NUM = re.compile(r"^[R$\s]*(\d[\d.,]*)\s*$")
_NON_DIGIT = re.compile(r"\D")

_BOILERPLATE = re.compile(
    r"(limite por cpf|desconto|cliente app|cll?ente|cart[aã]o tenda|"
    r"com o cart|pagando com|pre[cç]o(\s|$)|sai por|^tenda$|^atacado$|"
    r"fecha|na loja|no site|no app|unidades?\.?$|quilos?\.?$|packs?\.?$|"
    r"bandejas?\.?$|^cada$|^o kg$|^a unidade$|v[aá]lidas? para|ofertas?|"
    r"^pe[cç]a\b|^pacote\b|^lata\b|^garrafa\b|^sache\b|^sab?ores?\b|"
    r"^o bife|^o peda[cç]o|^o litro|^o pote|^a bandeja|^embalagem|desde)",
    re.IGNORECASE,
)


def _digit_str(text: str) -> str | None:
    """Return the raw digit sequence of a numeric region, else None."""
    m = _NUM.match(text.strip())
    if not m:
        return None
    return re.sub(r"[.,]", "", m.group(1))


def is_boilerplate(text: str) -> bool:
    """True for recurring promo / packaging phrases that are not product names."""
    return bool(_BOILERPLATE.search(text.strip()))


def is_product_name(text: str) -> bool:
    """Heuristic: enough letters and not boilerplate.

    We do NOT reject short all-uppercase words: real product tokens such as
    "LEITE", "ARROZ", "CAFE", "TRIGO" are frequently rendered in uppercase on
    flyers. Only genuine OCR garble (too few letters, or too low a letter
    ratio) is rejected.
    """
    t = text.strip()
    letters = sum(c.isalpha() for c in t)
    if letters < 4 or letters / max(1, len(t)) <= 0.5:
        return False
    return not is_boilerplate(t)


# --- price reconstruction ----------------------------------------------------


@dataclass(frozen=True)
class Price:
    value: float
    box: Box
    source: str  # debug tag describing how it was reconstructed


@dataclass
class _Num:
    """Internal working record for a numeric OCR region."""

    digits: str
    raw: str
    box: Box
    height: float
    cx: float
    cy: float
    used: bool = False


def reconstruct_prices(
    regions: list[dict],
    *,
    min_reais_height: float = 55.0,
) -> list[Price]:
    """Rebuild price values from OCR regions.

    Strategy (in priority order, tallest regions anchor first):
      * explicit separator ("19,90" / "19.90")   -> as-is
      * 4-digit tall blob   ("3590")              -> RR,CC
      * 3-digit tall blob   ("280")               -> R,CC
      * tall 1-2 digit reais + nearby small 2-digit cents to the upper-right
      * leftover tall 1-2 digit reais with no cents found
    """
    nums: list[_Num] = []
    for r in regions:
        d = _digit_str(r["text"])
        if d is None:
            continue
        box = r["box"]
        nums.append(
            _Num(
                digits=d,
                raw=r["text"].strip(),
                box=box,
                height=_height(box),
                cx=_cx(box),
                cy=_cy(box),
            )
        )
    nums.sort(key=lambda n: -n.height)  # big reais first
    # Pre-split cents candidates (2-digit regions) to avoid an O(n^2) scan.
    cents_pool = [n for n in nums if len(n.digits) == 2]
    prices: list[Price] = []

    for n in nums:
        if n.used:
            continue
        raw = n.digits
        # explicit decimal separator present
        if ("," in n.raw or "." in n.raw) and len(raw) >= 3:
            norm = n.raw.replace(".", ",")
            intpart, _, frac = norm.rpartition(",")
            intpart = _NON_DIGIT.sub("", intpart) or "0"
            frac = _NON_DIGIT.sub("", frac)
            try:
                val = int(intpart) + int(frac[:2].ljust(2, "0")) / 100
            except ValueError:
                continue
            n.used = True
            prices.append(Price(val, n.box, raw + " [sep]"))
            continue
        # single tall blob
        if n.height > 60 and len(raw) == 4:
            n.used = True
            prices.append(Price(int(raw[:2]) + int(raw[2:]) / 100, n.box, raw + " [blob4]"))
            continue
        if n.height > 60 and len(raw) == 3:
            n.used = True
            prices.append(Price(int(raw[0]) + int(raw[1:]) / 100, n.box, raw + " [blob3]"))
            continue
        # tall reais (1-2 digits) -> find superscript cents to the upper-right
        if n.height > min_reais_height and len(raw) <= 2:
            best: tuple[float, _Num] | None = None
            for m in cents_pool:
                if m.used or m is n:
                    continue
                dx = m.cx - n.cx
                dy = m.cy - n.cy
                if 0 < dx < n.height * 2.0 and abs(dy) < n.height * 0.9 and m.height < n.height:
                    dist = dx + abs(dy)
                    if best is None or dist < best[0]:
                        best = (dist, m)
            if best:
                cents = best[1]
                cents.used = True
                n.used = True
                prices.append(Price(int(raw) + int(cents.digits) / 100, n.box, f"{raw}+{cents.digits}"))
                continue
            n.used = True
            prices.append(Price(float(raw), n.box, raw + " [noCents]"))
    return prices


def deduplicate_dual_prices(
    prices: list[Price],
    *,
    max_dx: float = 70.0,
    max_dy: float = 170.0,
) -> list[Price]:
    """Merge the two prices most Tenda products show (Cliente APP vs Cartão).

    Prices in the same column and vertically close belong to one product; keep
    the lower (promotional) value.
    """
    remaining = sorted(prices, key=lambda p: (_cx(p.box), _cy(p.box)))
    used = [False] * len(remaining)
    out: list[Price] = []
    for i, p in enumerate(remaining):
        if used[i]:
            continue
        cluster = [p]
        used[i] = True
        for j in range(i + 1, len(remaining)):
            if used[j]:
                continue
            q = remaining[j]
            if abs(_cx(q.box) - _cx(p.box)) <= max_dx and abs(_cy(q.box) - _cy(p.box)) <= max_dy:
                cluster.append(q)
                used[j] = True
        promo = min(cluster, key=lambda x: x.value)
        out.append(promo)
    return out
