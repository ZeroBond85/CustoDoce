with open(".github/workflows/e2e.yml", "rb") as f:
    b = f.read()
crlf = b"\r\n" in b
print(f"Size: {len(b)}")
print(f"Has CRLF: {crlf}")
print(f"Has TAB: {9 in b}")
bad = [i for i, c in enumerate(b) if c < 32 and c not in (10, 13)]
print(f"Control chars (not LF/CR): {bad}")
lines = b.split(b"\n")
for i, line in enumerate(lines):
    if b"workflow_dispatch" in line:
        indent = len(line) - len(line.lstrip())
        print(f"Line {i}: {line.decode()}  (indent={indent})")
