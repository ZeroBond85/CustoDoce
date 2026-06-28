import re

for f in [".github/workflows/scrape.yml", ".github/workflows/e2e.yml"]:
    with open(f) as fh:
        lines = fh.readlines()
    for i, line in enumerate(lines, 1):
        m = re.search(r"run:\s+([^>|].*)", line)
        if m and ": " in m.group(1):
            val = m.group(1).strip()
            print(f"{f}:{i}: WARN -- colon-space in run value")
            print(f"  {val[:120]}...")
    # Also check run: | blocks for lines with : following colon
    in_block = False
    block_indent = 0
    for _i, line in enumerate(lines, 1):
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if re.match(r"^\s+run:\s*\|\s*$", line):
            in_block = True
            block_indent = indent + 2
            continue
        if in_block:
            if indent < block_indent and stripped:
                in_block = False
            elif ": " in stripped and not stripped.startswith("#"):
                pass  # : in block content is fine
