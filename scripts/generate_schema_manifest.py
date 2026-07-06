"""
Generate a JSON manifest of the Supabase public schema
by parsing consolidated_migration.sql offline.
No Supabase dependency — runs in CI without credentials.

Schema (rich):
  manifest = {
    "_meta": {...},
    "<table_or_view>": {
      "columns": ["col1", "col2", ...],                # backward compat
      "types": {"col1": "uuid", "col2": "decimal(10,2)", ...},
      "not_null": ["col1", "col2", ...],               # NOT NULL (with or without DEFAULT)
      "not_null_no_default": ["col1", ...],            # NOT NULL w/o DEFAULT — required
      "defaults": {"col1": "gen_random_uuid()", ...},
      "generated": {"col1": "EXPRESSION", ...},        # GENERATED ALWAYS AS ... STORED
      "constraints": {
        "pk": ["id"],
        "unique": [["ingredient_id","store_id","collected_at"]],
        "fk": [{"columns":["price_id"],"references":{"table":"prices","column":"id"}}],
        "check": [{"expression":"event_type IN ('failure','success')"}],
      },
    },
    ...
  }
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SQL_PATH = REPO_ROOT / "supabase" / "consolidated_migration.sql"
MANIFEST_PATH = REPO_ROOT / "config" / "schema_manifest.json"


# ─── Generic helpers ───────────────────────────────────────────────────────


def _normalize_name(name: str) -> str:
    return name.lower().strip().strip('"')


def _strip_sql_comments(text: str) -> str:
    text = re.sub(r"--[^\n]*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return text


def _split_top_level(text: str) -> list[str]:
    """Split `text` by commas respecting parenthesis depth 0 (so array literals,
    function calls, CHECK clauses are kept together)."""
    depth = 0
    seg_start = 0
    out = []
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            out.append(text[seg_start:i].strip())
            seg_start = i + 1
    rest = text[seg_start:].strip()
    if rest:
        out.append(rest)
    return [s for s in out if s]


def _extract_block_body(sql: str, open_pos: int) -> tuple[str, int]:
    """Given sql and the position of an opening `(`, return the body inside
    the matching parens along with the position just past the closing `)`."""
    depth = 0
    i = open_pos
    while i < len(sql):
        ch = sql[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return sql[open_pos + 1 : i], i + 1
        i += 1
    return "", open_pos  # unmatched


# ─── Column parsing ────────────────────────────────────────────────────────


def _parse_column_definition(seg: str) -> dict | None:
    """Parse a single column definition segment like:
        `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
        `raw_price NUMERIC(10,2) NOT NULL`
        `price_per_kg NUMERIC GENERATED ALWAYS AS ((normalized->>'price_per_kg')::numeric) STORED`
    Returns:
        {name, type, not_null, default, generated, in_pk, unique_inline, check}
        or None if this is not a column definition (table-level constraint).
    """
    seg = seg.strip()
    if not seg:
        return None

    # Skip table-level constraints
    head = seg.split(None, 1)[0].upper() if seg else ""
    if head in {
        "PRIMARY", "UNIQUE", "FOREIGN", "CHECK", "CONSTRAINT",
        "INDEX", "EXCLUDE", "LIKE",
    }:
        return None

    parts = seg.split(None, 1)
    if len(parts) < 2:
        return None
    name = _normalize_name(parts[0])
    if not name or name == "constraint":
        return None

    rest = parts[1]

    # GENERATED ALWAYS AS <expr> STORED | VIRTUAL
    generated_match = re.match(
        r"(GENERATED\s+ALWAYS\s+AS\s+\((?P<expr>.*?)\)\s*STORED|GENERATED\s+ALWAYS\s+AS\s+(?P<raw>\S+))",
        rest,
        re.I | re.S,
    )
    if generated_match:
        generated_expr = generated_match.group("expr") or generated_match.group("raw") or ""
        after = rest[generated_match.end() :].upper()
        col_type = "GENERATED"
        return {
            "name": name,
            "type": col_type,
            "not_null": "NOT" in after and "NULL" in after,
            "default": None,
            "generated": generated_expr.strip(),
        }

    # Type — capture until we hit a modifier keyword
    type_match = re.match(
        r"(?P<type>[A-Za-z_][\w]*(?:\s*\([^)]*\))?(?:\s*\[[^\]]*\])?)",
        rest,
    )
    col_type = type_match.group("type").lower() if type_match else ""

    upper_rest = rest.upper()
    not_null = bool(re.search(r"\bNOT\s+NULL\b", upper_rest))
    is_pk = bool(re.search(r"\bPRIMARY\s+KEY\b", upper_rest))
    is_unique = bool(re.search(r"\bUNIQUE\b", upper_rest))

    # DEFAULT <expr> — could be a function call, string, number, array
    default_expr = None
    default_match = re.search(r"DEFAULT\s+(.+?)(?=\s*(?:NOT\s+NULL|PRIMARY|UNIQUE|GENERATED|CHECK|REFERENCES|,|$))",
                              rest, re.I | re.S)
    if default_match:
        default_expr = default_match.group(1).strip()

    # Inline REFERENCES (column-level FK)
    references = None
    ref_match = re.search(
        r"REFERENCES\s+(?P<tbl>[\w\.]+)\s*\((?P<col>[\w\"]+)\)"
        r"(?:\s*ON\s+DELETE\s+(?P<ondel>\w+(?:\s+\w+)?))?",
        rest, re.I,
    )
    if ref_match:
        references = {
            "table": _normalize_name(ref_match.group("tbl")),
            "column": _normalize_name(ref_match.group("col")),
            "on_delete": (ref_match.group("ondel") or "").strip().upper() or None,
        }

    # Inline CHECK constraint
    check_expr = None
    check_match = re.search(r"CHECK\s*\((.+)\)\s*$", rest, re.I)
    if check_match:
        check_expr = check_match.group(1).strip()

    return {
        "name": name,
        "type": col_type.strip() or "unknown",
        "not_null": not_null,
        "default": default_expr,
        "generated": None,
        "in_pk": is_pk,
        "in_unique": is_unique,
        "references": references,
        "check": check_expr,
    }


# ─── Table constraints (UNIQUE / PK / FK / CHECK) ──────────────────────────


def _parse_table_constraint(seg: str) -> dict | None:
    """Parse a table-level constraint segment (returned by _split_top_level).
    Returns dict with one of: pk, unique, fk, check — or None."""
    seg = seg.strip()
    upper = seg.upper()
    head = upper.split(None, 1)[0] if upper else ""

    if head == "PRIMARY":
        m = re.search(r"PRIMARY\s+KEY\s*\(([^)]+)\)", seg, re.I)
        if m:
            cols = [_normalize_name(c) for c in m.group(1).split(",")]
            return {"type": "pk", "columns": cols}
        return None

    if head == "UNIQUE":
        m = re.search(r"UNIQUE\s*\(([^)]+)\)", seg, re.I)
        if m:
            cols = [_normalize_name(c) for c in m.group(1).split(",")]
            return {"type": "unique", "columns": cols}
        return None

    if head == "FOREIGN":
        m = re.match(
            r"FOREIGN\s+KEY\s*\((?P<cols>[^)]+)\)\s*REFERENCES\s+(?P<tbl>[\w\.]+)\s*\((?P<col>[\w\"]+)\)"
            r"(?:\s*ON\s+DELETE\s+(?P<ondel>\w+(?:\s+\w+)?))?",
            seg,
            re.I,
        )
        if m:
            return {
                "type": "fk",
                "columns": [_normalize_name(c) for c in m.group("cols").split(",")],
                "references": {
                    "table": _normalize_name(m.group("tbl")),
                    "column": _normalize_name(m.group("col")),
                },
                "on_delete": (m.group("ondel") or "").strip().upper() or None,
            }
        return None

    if head == "CHECK":
        m = re.match(r"CHECK\s*\((?P<expr>.*)\)\s*$", seg, re.I | re.S)
        if m:
            return {"type": "check", "expression": m.group("expr").strip()}
        return None

    # FOREIGN KEY variants: "ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY"
    fk_match = re.match(
        r"(?:\w+\s+)?FOREIGN\s+KEY\s*\((?P<cols>[^)]+)\)\s*REFERENCES\s+(?P<tbl>[\w\.]+)"
        r"\s*\((?P<col>[\w\"]+)\)",
        seg,
        re.I,
    )
    if fk_match:
        return {
            "type": "fk",
            "columns": [_normalize_name(c) for c in fk_match.group("cols").split(",")],
            "references": {
                "table": _normalize_name(fk_match.group("tbl")),
                "column": _normalize_name(fk_match.group("col")),
            },
        }

    # ALTER TABLE ... ADD CONSTRAINT <name> UNIQUE (col)
    add_unique = re.match(
        r"(?:CONSTRAINT\s+\w+\s+)?UNIQUE\s*\((?P<cols>[^)]+)\)\s*$",
        seg,
        re.I,
    )
    if add_unique:
        return {
            "type": "unique",
            "columns": [_normalize_name(c) for c in add_unique.group("cols").split(",")],
        }

    return None


# ─── Whole table parse ─────────────────────────────────────────────────────


def _parse_create_table(sql: str, start_pos: int) -> tuple[str, dict]:
    """Parse a full CREATE TABLE statement starting at the opening paren.
    Returns (table_name, schema_dict).

    schema_dict = {
      "columns": [ordered list of column names],
      "types": dict,
      "not_null": [list of NOT NULL columns],
      "not_null_no_default": [list of NOT NULL columns without DEFAULT or GENERATED],
      "defaults": dict,
      "generated": dict,
      "constraints": {"pk"|"unique"|"fk"|"check": ...},
    }
    """
    body, end_pos = _extract_block_body(sql, start_pos)
    if not body:
        return "", {}

    segments = []
    for raw in _split_top_level(body):
        cleaned = _strip_sql_comments(raw).strip().rstrip(",").strip()
        if cleaned:
            segments.append(cleaned)

    columns: list[str] = []
    types: dict[str, str] = {}
    not_null: list[str] = []
    not_null_no_default: list[str] = []
    defaults: dict[str, str] = {}
    generated: dict[str, str] = {}
    pks: list[str] = []
    uniques: list[list[str]] = []
    fks: list[dict] = []
    checks: list[dict] = []

    for seg in segments:
        upper = seg.upper().lstrip()
        # Detect table-level constraint quickly
        if upper.startswith(("PRIMARY ", "UNIQUE ", "FOREIGN ", "CHECK ", "CONSTRAINT ", "INDEX ", "EXCLUDE ")):
            # CONSTRAINT <name> (UNIQUE/FK/CHECK/PK)
            tc = _parse_table_constraint(_strip_table_constraint_prefix(seg))
            if tc:
                if tc["type"] == "pk":
                    pks = tc["columns"]
                elif tc["type"] == "unique":
                    uniques.append(tc["columns"])
                elif tc["type"] == "fk":
                    fks.append({
                        "columns": tc["columns"],
                        "references": tc["references"],
                        "on_delete": tc.get("on_delete"),
                    })
                elif tc["type"] == "check":
                    checks.append({"expression": tc["expression"]})
            else:
                # Could be a "Constraint <name> UNIQUE (...)" without our normalizer.
                pass
            continue

        col = _parse_column_definition(seg)
        if not col:
            continue
        name = col["name"]
        columns.append(name)
        types[name] = col["type"]
        if col["not_null"]:
            not_null.append(name)
        if col["not_null"] and col["default"] is None and col["generated"] is None:
            not_null_no_default.append(name)
        if col["default"] is not None:
            defaults[name] = col["default"]
        if col["generated"] is not None:
            generated[name] = col["generated"]
        if col["in_pk"]:
            pks.append(name)
        if col.get("in_unique"):
            uniques.append([name])
        if col.get("references"):
            fks.append({
                "columns": [name],
                "references": col["references"],
            })
        if col.get("check"):
            checks.append({"expression": col["check"]})

    schema = {
        "columns": columns,
        "types": types,
        "not_null": not_null,
        "not_null_no_default": not_null_no_default,
        "defaults": defaults,
        "generated": generated,
        "constraints": {
            "pk": pks,
            "unique": uniques,
            "fk": fks,
            "check": checks,
        },
    }
    return "", schema


def _strip_table_constraint_prefix(seg: str) -> str:
    """Remove leading `CONSTRAINT <name>` from a CREATE TABLE constraint segment."""
    return re.sub(r"^CONSTRAINT\s+\w+\s+", "", seg, flags=re.I).strip()


# ─── ALTER TABLE parsing ───────────────────────────────────────────────────


def _apply_alter_table_add(sql: str, manifest: dict) -> None:
    """Apply `ALTER TABLE <t> ADD COLUMN [IF NOT EXISTS] <name> <type> [NOT NULL]
    [DEFAULT <expr>];` to existing tables in the manifest."""
    pattern = re.compile(
        r"\bALTER\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
        r"(?P<table>\"?[\w]+\"?)\s+"
        r"ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?"
        r"\"?(?P<col>[\w]+)\"?\s+"
        r"(?P<rest>.+?);",
        re.I | re.S,
    )
    for m in pattern.finditer(sql):
        table = _normalize_name(m.group("table"))
        col = _normalize_name(m.group("col"))
        rest = m.group("rest").strip()
        manifest.setdefault(table, _empty_schema())
        schema = manifest[table]
        if col in schema["columns"]:
            # Already declared in CREATE TABLE; merge.
            pass

        # Parse type from the head of `rest`.
        type_m = re.match(r"(?P<type>[A-Za-z_][\w]*(?:\s*\([^)]*\))?(?:\s*\[[^\]]*\])?)", rest)
        col_type = (type_m.group("type").lower() if type_m else "unknown").strip()
        upper_rest = rest.upper()

        not_null = bool(re.search(r"\bNOT\s+NULL\b", upper_rest))
        default_m = re.search(
            r"DEFAULT\s+(.+?)(?=\s*(?:NOT\s+NULL|;|$))", rest, re.I | re.S
        )
        default_expr = default_m.group(1).strip() if default_m else None

        if col not in schema["columns"]:
            schema["columns"].append(col)
        schema["types"][col] = col_type
        if not_null and col not in schema["not_null"]:
            schema["not_null"].append(col)
        if not_null and default_expr is None and col not in schema["not_null_no_default"]:
            schema["not_null_no_default"].append(col)
        if default_expr is not None and col not in schema["defaults"]:
            schema["defaults"][col] = default_expr


def _apply_alter_column_set_default(sql: str, manifest: dict) -> None:
    """Apply `ALTER TABLE <t> ALTER COLUMN <col> SET DEFAULT <expr>` and
    `ALTER TABLE <t> ALTER COLUMN <col> SET NOT NULL` to manifest."""
    pattern_set = re.compile(
        r"\bALTER\s+TABLE\s+(?P<table>\w+)\s+ALTER\s+COLUMN\s+(?P<col>\w+)\s+"
        r"SET\s+DEFAULT\s+(?P<expr>[^;]+);",
        re.I,
    )
    for m in pattern_set.finditer(sql):
        table = _normalize_name(m.group("table"))
        col = _normalize_name(m.group("col"))
        expr = m.group("expr").strip()
        schema = manifest.get(table)
        if not schema:
            continue
        schema["defaults"][col] = expr

    pattern_notnull = re.compile(
        r"\bALTER\s+TABLE\s+(?P<table>\w+)\s+ALTER\s+COLUMN\s+(?P<col>\w+)\s+SET\s+NOT\s+NULL\s*;",
        re.I,
    )
    for m in pattern_notnull.finditer(sql):
        table = _normalize_name(m.group("table"))
        col = _normalize_name(m.group("col"))
        schema = manifest.get(table)
        if not schema:
            continue
        if col not in schema["not_null"]:
            schema["not_null"].append(col)
        if col not in schema["not_null_no_default"]:
            # After SET DEFAULT, the column has a default — so move it out of the no-default bucket.
            if schema["defaults"].get(col) or schema["generated"].get(col):
                # No longer mandatory w/o default.
                pass
            else:
                schema["not_null_no_default"].append(col)


def _apply_alter_column_type(sql: str, manifest: dict) -> None:
    """Apply `ALTER TABLE ... ALTER COLUMN ... TYPE ...`."""
    pattern = re.compile(
        r"\bALTER\s+TABLE\s+(?P<table>\w+)\s+ALTER\s+COLUMN\s+(?P<col>\w+)\s+TYPE\s+(?P<type>[^;]+);",
        re.I,
    )
    for m in pattern.finditer(sql):
        table = _normalize_name(m.group("table"))
        col = _normalize_name(m.group("col"))
        new_type = m.group("type").strip().lower()
        schema = manifest.get(table)
        if not schema:
            continue
        schema["types"][col] = new_type


def _apply_alter_column_generated(sql: str, manifest: dict) -> None:
    """Apply `ALTER TABLE ... ADD COLUMN ... GENERATED ALWAYS AS (...) STORED`."""
    pattern = re.compile(
        r"\bALTER\s+TABLE\s+(?P<table>\w+)\s+ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?"
        r"(?P<col>\w+)\s+(?P<type>[\w( \)]+?)\s+GENERATED\s+ALWAYS\s+AS\s*\((?P<expr>[^)]+)\)\s+STORED\s*;",
        re.I,
    )
    for m in pattern.finditer(sql):
        table = _normalize_name(m.group("table"))
        col = _normalize_name(m.group("col"))
        typ = m.group("type").strip().lower()
        expr = m.group("expr").strip()
        schema = manifest.get(table)
        if not schema:
            continue
        if col not in schema["columns"]:
            schema["columns"].append(col)
        schema["types"][col] = typ
        schema["generated"][col] = expr


def _apply_alter_table_add_constraint_unique(sql: str, manifest: dict) -> None:
    """Apply `ALTER TABLE <t> ADD CONSTRAINT <name> UNIQUE (<col>, ...)`."""
    pattern = re.compile(
        r"\bALTER\s+TABLE\s+(?P<table>\w+)\s+ADD\s+CONSTRAINT\s+\w+\s+UNIQUE\s*\((?P<cols>[^)]+)\)\s*;",
        re.I,
    )
    for m in pattern.finditer(sql):
        table = _normalize_name(m.group("table"))
        cols = [_normalize_name(c) for c in m.group("cols").split(",")]
        schema = manifest.get(table)
        if not schema:
            continue
        # Avoid duplicates
        if cols not in schema["constraints"]["unique"]:
            schema["constraints"]["unique"].append(cols)


def _apply_alter_table_drop_constraint(sql: str, manifest: dict) -> None:
    """No-op at this level (informational only)."""
    return


def _empty_schema() -> dict:
    return {
        "columns": [],
        "types": {},
        "not_null": [],
        "not_null_no_default": [],
        "defaults": {},
        "generated": {},
        "constraints": {"pk": [], "unique": [], "fk": [], "check": []},
    }


# ─── Materialized view ─────────────────────────────────────────────────────


def _extract_mv_columns(body: str) -> list[str]:
    """Extract column references from a SELECT clause.

    Handles `SELECT DISTINCT ON (...)` as well as plain `SELECT`."""
    # Strip DISTINCT ON (...) clause upfront
    body = re.sub(r"\bDISTINCT\s+ON\s*\([^)]*\)\s+", "", body, flags=re.I)
    select_m = re.search(r"\bSELECT\s+", body, re.I)
    if not select_m:
        return []
    sel_start = select_m.end()
    from_m = re.search(r"\bFROM\b", body[sel_start:], re.I)
    if not from_m:
        return []
    select_block = body[sel_start : sel_start + from_m.start()]
    columns = []
    for part in _split_top_level(select_block):
        alias_m = re.search(r"\bAS\s+(\w+)", part, re.I)
        if alias_m:
            columns.append(_normalize_name(alias_m.group(1)))
        else:
            first = part.split()[0] if part.split() else part
            if first.upper() != "DISTINCT":
                columns.append(_normalize_name(first.strip('"')))
    return columns


# ─── Main ──────────────────────────────────────────────────────────────────


def generate_manifest() -> int:
    if not SQL_PATH.exists():
        print(f"ERRO: SQL file not found at {SQL_PATH}")
        return 1

    sql = _strip_sql_comments(SQL_PATH.read_text(encoding="utf-8"))
    manifest: dict[str, dict] = {}

    # 1. CREATE TABLE
    table_pattern = re.compile(
        r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\"?[\w]+\"?)\s*\(",
        re.I,
    )
    for m in table_pattern.finditer(sql):
        table = _normalize_name(m.group(1))
        if not table:
            continue
        open_pos = m.end() - 1
        _table_name, schema = _parse_create_table(sql, open_pos)
        if schema.get("columns"):
            manifest[table] = schema

    # 2. CREATE MATERIALIZED VIEW
    mv_pattern = re.compile(
        r"\bCREATE\s+MATERIALIZED\s+VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?(\"?[\w]+\"?)\s+AS",
        re.I,
    )
    for m in mv_pattern.finditer(sql):
        view = _normalize_name(m.group(1))
        body_start = m.end()
        # Scan from body_start to the next top-level semicolon
        rest = sql[body_start:]
        semicolon_depth = 0
        body_len = 0
        for ch in rest:
            if ch == '(':
                semicolon_depth += 1
            elif ch == ')':
                semicolon_depth -= 1
            elif ch == ';' and semicolon_depth == 0:
                break
            body_len += 1
        query_block = rest[:body_len]
        cols = _extract_mv_columns(query_block)
        if cols:
            manifest[view] = _empty_schema()
            manifest[view]["columns"] = cols

    # 3. Apply ALTER TABLE changes
    _apply_alter_table_add(sql, manifest)
    _apply_alter_column_set_default(sql, manifest)
    _apply_alter_column_generated(sql, manifest)
    _apply_alter_column_type(sql, manifest)
    _apply_alter_table_add_constraint_unique(sql, manifest)

    # 4. Backward compatibility: every entry must expose `columns` (already done)
    # and expose `_meta`. We also keep legacy `tables_count` marker.
    manifest["_meta"] = {
        "source": "consolidated_migration.sql",
        "generator": "scripts/generate_schema_manifest.py",
        "version": 2,
        "tables": len([k for k in manifest if not k.startswith("_")]),
    }

    # 5. Idempotent FALLBACK for tables/views where parsing didn't yield any
    # schema details (rare, but be defensive): synthesize a minimal schema.
    for k, v in list(manifest.items()):
        if k.startswith("_"):
            continue
        if not isinstance(v, dict) or not v.get("columns"):
            # If columns is the legacy list-style (back-compat), preserve it.
            if isinstance(v, list):
                cols = v
                manifest[k] = _empty_schema()
                manifest[k]["columns"] = cols
            else:
                manifest[k] = _empty_schema()
                # leave empty — will be flagged in validation if any mock targets it.

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)

    total = manifest["_meta"]["tables"]
    print(f"SUCCESS: Manifest generated at {MANIFEST_PATH}")
    print(f"Tables/Views parsed: {total}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(generate_manifest())
