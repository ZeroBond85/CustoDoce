import re

_UNIT_PATTERNS = [
    re.compile(r"(\d+\s*x\s*[\d.,]+\s*(?:kg|g|ml|un|L|l))", re.I),
    re.compile(r"([\d.,]+\s*(?:kg|g|ml|un|L|l)\b)", re.I),
    re.compile(r"(cx\s*(?:com\s*)?\d+)", re.I),
    re.compile(r"(lata\s*\d+\s*(?:kg|g|ml))", re.I),
    re.compile(r"(pacote\s*(?:com\s*)?\d+)", re.I),
    re.compile(r"(balde\s*\d+\s*(?:kg|g|ml))", re.I),
]


def extract_unit(name: str) -> str:
    for pat in _UNIT_PATTERNS:
        m = pat.search(name)
        if m:
            return m.group(1).strip()
    return ""
