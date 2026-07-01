"""Markdown-it section span parser.

Parses all .md files, computes heading-based section spans,
and returns structured data for classifier consumption.

Each .md → list of headings with extended span [start, end)
where end = next same/higher-level heading start (or EOF).
"""

from __future__ import annotations

import os as _os
import re
from pathlib import Path

from markdown_it import MarkdownIt

_ROOT = Path(__file__).resolve().parent.parent.parent
_SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "lib64"}

_md = MarkdownIt()

PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b17\b.*(páginas?|telas?|módulos?|pages?|aba)"), "page_count"),
    (re.compile(r"\b418\b"), "test_count_418"),
    (re.compile(r"\b383\b"), "test_count_383"),
    (re.compile(r"\b512\b.*(testes|passing|passando)"), "test_count_512"),
    (re.compile(r"\b630\b.*total"), "test_count_630"),
    (re.compile(r"\b709\b.*total"), "test_count_709"),
]


def _compute_section_spans(text: str) -> dict[int, str]:
    """Return dict: line_num -> heading_path for the entire section span."""
    tokens = _md.parse(text)
    headings: list[dict] = []
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open":
            level = int(tok.tag[1])
            start = tok.map[0] if tok.map else 0
            content = ""
            for j in range(i + 1, len(tokens)):
                if tokens[j].type == "inline":
                    content = tokens[j].content
                    break
                elif tokens[j].type == "heading_close":
                    break
            headings.append({"level": level, "content": content, "start": start})

    headings.sort(key=lambda h: h["start"])

    # Extend each heading to next same/higher-level heading (or EOF)
    for i, h in enumerate(headings):
        end = len(text.split("\n"))
        for j in range(i + 1, len(headings)):
            if headings[j]["level"] <= h["level"]:
                end = headings[j]["start"]
                break
        h["end"] = end

    lines = text.split("\n")
    line_to_heading: dict[int, str] = {}
    for line_num in range(len(lines)):
        path: list[tuple[int, str]] = []
        for h in headings:
            if h["start"] <= line_num < h["end"]:
                path = [p for p in path if p[0] < h["level"]]
                path.append((h["level"], h["content"]))
        line_to_heading[line_num] = " > ".join(t for _, t in path)

    return line_to_heading


def scan_all_md() -> list[dict]:
    """Scan all .md files and return structured findings.

    Each finding: {file, line, match, pattern, heading, classification}
    """
    findings: list[dict] = []

    for dirpath, dirnames, filenames in _os.walk(str(_ROOT), topdown=True):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fname in filenames:
            if not fname.endswith(".md"):
                continue
            fpath = Path(dirpath) / fname
            rel = str(fpath.relative_to(_ROOT))
            try:
                text = fpath.read_text(encoding="utf-8")
            except Exception:
                continue

            line_to_heading = _compute_section_spans(text)

            for pat, pat_name in PATTERNS:
                for m in pat.finditer(text):
                    line_num = text[: m.start()].count("\n")
                    heading = line_to_heading.get(line_num, "")
                    findings.append({
                        "file": rel,
                        "line": line_num + 1,
                        "heading": heading,
                        "pattern": pat_name,
                        "match": m.group().strip()[:80],
                    })

    return findings
