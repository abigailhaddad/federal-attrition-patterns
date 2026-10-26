# Fails if a digit is typed into text that build.py writes to facts.md or onto a chart: every number there must come
# from the data, a source document, or config.py.  python3 check_literals.py
import ast, re, sys

ALLOWED = [r"^\d+\. ",          # section numbers that match chart numbers ("3. Who left each year")
           r"SHA-256", r"\bsha256\b", r"(?i)chart \d", r"charts \d and \d", r"= 100\b", r"source_\w+\.png", r"[\w.]+\.(png|pdf|html|json|parquet|csv)"]
TEXT_CALLS = {"b", "h", "append", "text", "set_title", "annotate", "set_xlabel", "set_ylabel"}   # facts.md writers and chart text; finish() is checked from its 3rd argument on (title, subtitle, notes)


def literal_parts(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        yield node.value
    elif isinstance(node, ast.JoinedStr):
        for v in node.values:
            if isinstance(v, ast.Constant):
                yield v.value
    elif isinstance(node, ast.BinOp):
        yield from literal_parts(node.left)
        yield from literal_parts(node.right)
    elif isinstance(node, (ast.List, ast.Tuple)):
        for e in node.elts:
            yield from literal_parts(e)
    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "join":
        for a in node.args:
            yield from literal_parts(a)


bad = []
for n in ast.walk(ast.parse(open("build.py").read())):
    if not isinstance(n, ast.Call):
        continue
    name = n.func.id if isinstance(n.func, ast.Name) else n.func.attr if isinstance(n.func, ast.Attribute) else ""
    args = n.args if name in TEXT_CALLS else n.args[2:] if name == "finish" else []
    for a in args:
        for p in literal_parts(a):
            text = p
            for pat in ALLOWED:
                text = re.sub(pat, "", text)
            if re.search(r"\d", text):
                bad.append((n.lineno, p.strip()[:120]))
for line, p in sorted(set(bad)):
    print(f"build.py:{line}: digit typed into text: {p!r}")
sys.exit(1 if bad else 0)
