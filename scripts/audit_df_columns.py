"""
Audit tool to check if columns used in DataFrame accesses (df['col'])
exist in the Supabase schema manifest.
"""
import ast
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "config/schema_manifest.json"

def load_manifest() -> set[str]:
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        all_cols = set()
        for cols in data.values():
            all_cols.update(cols)
        # Add common aliases used in dashboard
        all_cols.update({"ppk", "cost", "Ingrediente", "Qtd (g)", "name", "price_per_kg"})
        return all_cols

def audit_df_access(filepath: Path, valid_cols: set[str]) -> list[str]:
    text = filepath.read_text(encoding="utf-8")
    errors = []
    try:
        tree = ast.parse(text)
        for node in ast.walk(tree):
            # Detect df['col'] or df["col"]
            if (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Name)
                and node.value.id.startswith('df')
                and isinstance(node.slice, (ast.Constant, ast.Str))
            ):
                col = node.slice.value if isinstance(node.slice, ast.Constant) else node.slice.s
                if col not in valid_cols:
                    errors.append(f"{filepath.relative_to(REPO_ROOT)}:{node.lineno} - Column '{col}' not in schema manifest")
    except SyntaxError:
        pass
    return errors

def main():
    valid_cols = load_manifest()
    dashboard_dir = REPO_ROOT / "dashboard"
    errors = []
    for pyfile in dashboard_dir.rglob("*.py"):
        errors.extend(audit_df_access(pyfile, valid_cols))

    if errors:
        print("Mismatches found in DataFrame accesses:")
        for e in errors:
            print(e)
    else:
        print("All DataFrame column accesses valid.")

if __name__ == "__main__":
    main()
