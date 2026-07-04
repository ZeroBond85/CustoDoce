"""Heading-based stale-ref classifier.

Determines if a stale numeric reference is:
- CURRENT: should be auto-updated to truth value
- HISTORICAL: intentionally preserved (milestone, changelog, lesson)
- AMBIGUOUS: cannot determine automatically

Rules are based on heading path and match text context.
"""

from __future__ import annotations

# Heading fragments that mark a section as historical snapshot
_HISTORICAL_HEADING_MARKERS = {
    "histórico",
    "histórico de versões",
    "versão",
    "changelog",
    "roadmap",
    "próximos",
    "lição",
    "lições",
    "lessons",
    "entregas confirmadas",
    "entregas",
    "milestone",
}

# Heading fragments that mark a section as current status
_CURRENT_HEADING_MARKERS = {
    "status atual",
    "avaliação",
    "avaliação de riscos",
    "riscos",
    "métricas finais",
    "métricas de sucesso",
}

# Match text patterns that indicate a historical reference
_HISTORICAL_MATCH_MARKERS = [
    "era ",
    "em 29/06",
    "em 30/06",
    "resolvido",
    "mitigado",
    "passou de ",
    "subiu de",
    "anteriormente",
]


def classify(heading: str, match_text: str, file_path: str) -> str:
    """Return 'HISTORICAL', 'CURRENT', or 'AMBIGUOUS'.

    Checks (in order):
    1. File-level: changelog.md is always HISTORICAL
    2. Heading path markers
    3. Match text markers
    4. Default: AMBIGUOUS
    """
    h_lower = heading.lower()
    m_lower = match_text.lower()
    fp_lower = file_path.lower()

    # File-level rules
    if "changelog" in fp_lower:
        return "HISTORICAL"

    # Section-level: heading path (HISTORICAL markers first)
    for marker in _HISTORICAL_HEADING_MARKERS:
        if marker in h_lower:
            return "HISTORICAL"

    # Match text context — checked BEFORE heading CURRENT markers so that
    # a match like "512 em 29/06; Sprint 7-9" within a CURRENT heading
    # still gets classified as HISTORICAL.
    for marker in _HISTORICAL_MATCH_MARKERS:
        if marker in m_lower:
            return "HISTORICAL"

    # Section-level: CURRENT heading markers
    for marker in _CURRENT_HEADING_MARKERS:
        if marker in h_lower:
            return "CURRENT"

    # README roadmap is historical
    if "readme" in fp_lower and "roadmap" in h_lower:
        return "HISTORICAL"

    return "AMBIGUOUS"
