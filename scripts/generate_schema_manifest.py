"""
Generate a JSON manifest of the Supabase public schema
by parsing consolidated_migration.sql offline.
No Supabase dependency — runs in CI without credentials.
"""
import json
import re
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parent.parent
SQL_PATH = REPO_ROOT / "supabase" / "consolidated_migration.sql"
MANIFEST_PATH = REPO_ROOT / "config" / "schema_manifest.json"


def _normalize_name(name: str) -> str:
    return name.lower().strip()


def _strip_sql_comments(text: str) -> str:
    text = re.sub(r"--[^\n]*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return text


def _extract_table_columns(
    text: str, table_name: str, start_pos: int
) -> list[str]:
    """Extract column names from parenthesized table definition starting at start_pos.

    Splits column definitions by commas at parenthesis depth 0 (not commas
    inside CHECK constraints or function calls).
    """
    depth = 0
    i = start_pos
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
    if depth != 0:
        return []
    block = text[start_pos + 1 : i]

    # Split by commas at depth 0
    columns = []
    depth = 0
    seg_start = 0
    for j, ch in enumerate(block):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            seg = block[seg_start:j].strip()
            seg_start = j + 1
            seg = _strip_sql_comments(seg).strip()
            if not seg:
                continue
            # Skip table constraints
            if re.match(
                r"^(PRIMARY\s+KEY|UNIQUE|FOREIGN\s+KEY|CHECK|INDEX|EXCLUDE|CONSTRAINT|FULLTEXT|SPATIAL)\b",
                seg,
                re.I,
            ):
                continue
            parts = seg.split()
            if parts:
                col = _normalize_name(parts[0])
                if col and col not in ("constraint",):
                    columns.append(col)
    # Last segment (after final comma)
    if seg_start < len(block):
        seg = block[seg_start:].strip()
        seg = _strip_sql_comments(seg).strip()
        if seg:
            if re.match(
                r"^(PRIMARY\s+KEY|UNIQUE|FOREIGN\s+KEY|CHECK|INDEX|EXCLUDE|CONSTRAINT|FULLTEXT|SPATIAL)\b",
                seg,
                re.I,
            ):
                return columns
            parts = seg.split()
            if parts:
                col = _normalize_name(parts[0])
                if col and col not in ("constraint",):
                    columns.append(col)
    return columns


def _parse_materialized_view_columns(text: str, start_pos: int) -> list[str]:
    """Extract column names from CREATE MATERIALIZED VIEW ... AS SELECT ..."""
    # Find SELECT clause after AS
    select_match = re.search(
        r"\bSELECT\s+(?:DISTINCT\s+ON\s*\([^)]*\)\s*)?", text[start_pos:], re.I
    )
    if not select_match:
        return []
    sel_start = start_pos + select_match.end()
    # Find FROM that ends the select list
    from_match = re.search(r"\bFROM\b", text[sel_start:], re.I)
    if not from_match:
        return []
    select_block = text[sel_start : sel_start + from_match.start()]
    columns = []
    for part in select_block.split(","):
        part = part.strip()
        if not part:
            continue
        # Handle "col AS alias" or just "col"
        alias_match = re.search(r"\bAS\s+(\w+)", part, re.I)
        if alias_match:
            columns.append(_normalize_name(alias_match.group(1)))
        else:
            word = part.split()[0] if part.split() else part
            if word != "DISTINCT":
                columns.append(_normalize_name(word.strip('"')))
    return columns


def generate_manifest():
    if not SQL_PATH.exists():
        print(f"ERRO: SQL file not found at {SQL_PATH}")
        print("  Run from project root or check path.")
        return 1

    sql_text = SQL_PATH.read_text(encoding="utf-8")
    sql_text = _strip_sql_comments(sql_text)

    manifest: dict[str, list[str]] = defaultdict(list)

    # Pattern: CREATE TABLE [IF NOT EXISTS] name ( ... ) ;
    # or inline: CREATE TABLE name ( col1 type, col2 type, ... ) ;
    table_pattern = re.compile(
        r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\(",
        re.I,
    )
    for m in table_pattern.finditer(sql_text):
        table_name = _normalize_name(m.group(1))
        start = m.end() - 1  # position of the opening '('
        columns = _extract_table_columns(sql_text, table_name, start)
        if columns:
            manifest[table_name] = sorted(set(columns))

    # Pattern: CREATE MATERIALIZED VIEW [IF NOT EXISTS] name AS SELECT ...
    mv_pattern = re.compile(
        r"\bCREATE\s+MATERIALIZED\s+VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+AS",
        re.I,
    )
    for m in mv_pattern.finditer(sql_text):
        view_name = _normalize_name(m.group(1))
        columns = _parse_materialized_view_columns(sql_text, m.start())
        if columns:
            manifest[view_name] = sorted(set(columns))

    # Write manifest
    manifest["_meta"] = {
        "source": "consolidated_migration.sql",
        "generator": "scripts/generate_schema_manifest.py",
        "tables": len(manifest) - 1,
    }

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(dict(manifest), f, indent=2, sort_keys=True)

    table_count = len([k for k in manifest if not k.startswith("_")])
    print(f"SUCCESS: Manifest generated at {MANIFEST_PATH}")
    print(f"Tables/Views parsed: {table_count}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(generate_manifest())
