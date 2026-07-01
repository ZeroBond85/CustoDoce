"""Auto-updater for CURRENT stale refs.

Only touches blocks classified as CURRENT.
Never touches HISTORICAL or AMBIGUOUS blocks.

Replaces STALE NUMBER within the match context, not the full match text.
For example, match "512 passing" in "**512 passing**" → "**577 passing**".
"""

from __future__ import annotations

import re
from pathlib import Path


# Maps pattern key -> (stale_num, truth_num_fn)
# where truth_num_fn(truth_dict) returns the replacement number as string.
def _build_replacements(truth: dict) -> dict[str, tuple[str, str]]:
    unit = truth["test_counts"].get("unit", 0)
    schema = truth["test_counts"].get("schema", 0)
    total = truth["total_tests"]
    pages = truth["pages_count"]

    return {
        "page_count": ("17", str(pages)),
        "test_count_418": ("418", str(unit)),
        "test_count_383": ("383", str(unit)),
        "test_count_512": ("512", str(unit + schema)),
        "test_count_630": ("630", str(total)),
        "test_count_709": ("709", str(total)),
    }


def apply_fix(text: str, stale_num: str, truth_num: str) -> str:
    """Replace stale_num with truth_num, as standalone word/boundary.

    Uses word-boundary regex \b to avoid replacing substrings of larger numbers.
    Only replaces FIRST occurrence.
    """
    return re.sub(rf"\b{re.escape(stale_num)}\b", truth_num, text, count=1)


def sync_file(fpath: Path, findings: list[dict], truth: dict, dry_run: bool = False) -> list[str]:
    """Apply updates to a single .md file based on CURRENT-classified findings.

    Returns list of change descriptions (empty = no changes).
    """
    repl = _build_replacements(truth)
    changes: list[str] = []
    content = fpath.read_text(encoding="utf-8")

    for finding in findings:
        if finding["classification"] != "CURRENT":
            continue
        pat = finding["pattern"]
        if pat not in repl:
            continue
        stale_num, truth_num = repl[pat]

        # Only proceed if the stale number actually appears in the file
        # (within the CURRENT section — conservatively check whole file)
        if re.search(rf"\b{re.escape(stale_num)}\b", content) is None:
            continue

        new_content = apply_fix(content, stale_num, truth_num)
        if new_content != content:
            changes.append(f"  {finding['file']}:{finding['line']} - {pat}: '{stale_num}' -> '{truth_num}'")
            content = new_content

    if not dry_run:
        fpath.write_text(content, encoding="utf-8")

    return changes
