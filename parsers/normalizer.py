import re
from typing import Optional


class NormalizedPrice:
    def __init__(self, qty: int, unit_kg: float, total_kg: float,
                 price_per_kg: float, price_per_un: float):
        self.qty = qty
        self.unit_kg = unit_kg
        self.total_kg = total_kg
        self.price_per_kg = price_per_kg
        self.price_per_un = price_per_un

    def to_dict(self):
        return {
            "qty": self.qty,
            "unit_kg": round(self.unit_kg, 4),
            "total_kg": round(self.total_kg, 4),
            "price_per_kg": round(self.price_per_kg, 2),
            "price_per_un": round(self.price_per_un, 2),
        }

    def __repr__(self):
        return (f"<Normalized: R${self.price_per_kg:.2f}/kg, "
                f"R${self.price_per_un:.2f}/un, "
                f"{self.qty} x {self.unit_kg*1000:.0f}g>")


_WEIGHT_PATTERNS = [
    re.compile(r"(\d+)\s*x\s*([\d,.]+)\s*(kg|g|ml)", re.I),
    re.compile(r"([\d,.]+)\s*(kg|g|ml)", re.I),
    re.compile(r"(\d+)\s*[xX]\s*([\d,.]+)(?:\s*(kg|g|ml))?", re.I),
]

_UNIT_PATTERNS = [
    re.compile(r"(\d+)\s*(uni|un|und|unidade|uns?)\b", re.I),
    re.compile(r"pacote\s*com\s*(\d+)", re.I),
    re.compile(r"cx\s*(?:com\s*)?(\d+)", re.I),
    re.compile(r"cx\w*\s*(?:com\s*)?(\d+)", re.I),
]


def parse_unit(raw_unit: str) -> Optional[NormalizedPrice]:
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
            elif weight_unit and weight_unit.lower() in ("g", "gr", "grama") or weight_unit and weight_unit.lower() in ("ml", "mililitro"):
                unit_kg = weight / 1000
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


def normalize_price(raw_price: float, raw_unit: str) -> Optional[NormalizedPrice]:
    if raw_price <= 0:
        return None

    parsed = parse_unit(raw_unit)
    if parsed is None:
        return None

    parsed.price_per_kg = raw_price / parsed.total_kg
    parsed.price_per_un = raw_price / parsed.qty

    return parsed
