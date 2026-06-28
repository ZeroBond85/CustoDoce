"""
Migration runner with smart SQL splitting that respects PL/pgSQL dollar-quoting ($$ ... $$).
Used by deploy_database.py and standalone migrations.
"""

import re


def split_sql_statements(sql: str) -> list[str]:
    """
    Splits SQL into individual statements, respecting dollar-quoted strings.
    Tracks whether we're inside a $$ ... $$ block (function body).
    """
    statements = []
    buf: list[str] = []
    in_dollar_quote = False
    in_single_quote = False

    i = 0
    while i < len(sql):
        # Handle line comments
        if not in_dollar_quote and not in_single_quote and sql[i : i + 2] == "--":
            # Skip to end of line
            while i < len(sql) and sql[i] != "\n":
                buf.append(sql[i])
                i += 1
            continue

        # Handle block comments
        if not in_dollar_quote and not in_single_quote and sql[i : i + 2] == "/*":
            i += 2
            while i < len(sql) and sql[i : i + 2] != "*/":
                if i + 1 >= len(sql):
                    break
                buf.append(sql[i])
                i += 1
            if i + 1 < len(sql):
                i += 2  # skip */
            continue

        char = sql[i]

        # Detect dollar-quoting
        if not in_single_quote and char == "$":
            # Check if it's $$ (PL/pgSQL anonymous block)
            if i + 1 < len(sql) and sql[i + 1] == "$":
                buf.append("$$")
                in_dollar_quote = not in_dollar_quote
                i += 2
                continue
            # Check for named dollar quote $tag$ ... $tag$
            m = re.match(r"^\$(?P<tag>[a-zA-Z_][a-zA-Z0-9_]*)\$", sql[i:])
            if m:
                tag = m.group("tag")
                buf.append(f"${tag}$")
                in_dollar_quote = True
                self_tag = f"${tag}$"
                # Track tagged quote state with a different approach
                i += len(m.group(0))
                # We need to find the matching closing tag
                # Simple state machine: keep reading until we find self_tag
                close_idx = sql.find(self_tag, i)
                if close_idx == -1:
                    # Unterminated
                    raise ValueError(f"Unterminated dollar quote ${tag}$")
                buf.append(sql[i:close_idx] + self_tag)
                i = close_idx + len(self_tag)
                in_dollar_quote = False
                continue

        # Detect single quotes (string literals)
        if not in_dollar_quote and char == "'":
            in_single_quote = not in_single_quote
            buf.append(char)
            i += 1
            continue

        # Handle statement terminator (semicolon outside any quoting/comment)
        if not in_dollar_quote and not in_single_quote and char == ";":
            statement = "".join(buf).strip()
            if statement:
                statements.append(statement)
            buf = []
            i += 1
            continue

        buf.append(char)
        i += 1

    # Flush remaining
    rest = "".join(buf).strip()
    if rest:
        statements.append(rest)

    return statements
