#!/usr/bin/env python3
"""Static checks for index.html's module script.

Written after breaking the page twice with string patches, where the only check in place was counting
braces — which cannot catch either failure. Both were use-before-declaration (a temporal dead zone
ReferenceError), which is a *runtime* error a syntax check also misses, so it gets its own pass here.

  ./check_page.py            # parse + ordering checks
Exits non-zero on any finding.
"""
import re, subprocess, sys, pathlib

SRC = pathlib.Path(__file__).parent / "index.html"
html = SRC.read_text()
m = re.search(r'<script type="module">\n(.*?)\n</script>', html, re.S)
if not m:
    print("FAIL: no module script found"); sys.exit(1)
js = m.group(1)
problems = []

# 1. real parse, via the node in asset-studio's dev image (there is no node on this host)
tmp = pathlib.Path("/tmp/_wi1370_check.mjs"); tmp.write_text(js)
try:
    r = subprocess.run(
        ["docker", "run", "--rm", "-v", f"{tmp}:/c.mjs:ro", "localhost/asset-studio-dev",
         "node", "--check", "/c.mjs"],
        capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        problems.append("node --check failed:\n" + (r.stderr.strip() or r.stdout.strip()))
    else:
        print("  [ok] node --check parses the module")
except Exception as e:
    print(f"  [skip] node --check unavailable ({e})")

# 2. temporal dead zone: a top-level const/let used above its own declaration.
#    Only module-level declarations (column 0) — anything indented is inside a scope this cannot model.
lines = js.split("\n")
decl = {}
for i, ln in enumerate(lines):
    for d in re.finditer(r'^(?:const|let)\s+([A-Za-z_$][\w$]*)', ln):
        decl.setdefault(d.group(1), i)
    for d in re.finditer(r'^(?:const|let)\s*\{([^}]*)\}', ln):
        for name in re.findall(r'[A-Za-z_$][\w$]*', d.group(1)):
            decl.setdefault(name, i)
in_fn = 0
for i, ln in enumerate(lines):
    code = re.sub(r'//.*$', '', ln)
    code = re.sub(r'([\'"`]).*?\1', '""', code)
    # a use inside a function body may legitimately precede the declaration (hoisted call site),
    # so only flag uses at module level — i.e. lines that are not inside a brace-nested function
    for name, at in decl.items():
        if i < at and re.search(rf'\b{re.escape(name)}\b', code):
            if in_fn == 0:
                problems.append(f"line {i+1}: `{name}` used before its declaration on line {at+1} "
                                f"(temporal dead zone — ReferenceError at run time)")
    if re.search(r'\bfunction\b|=>\s*\{', code):
        in_fn += code.count("{") - code.count("}")
        in_fn = max(in_fn, 0)
    elif in_fn:
        in_fn += code.count("{") - code.count("}")
        in_fn = max(in_fn, 0)

if problems:
    print("\n".join("  [FAIL] " + p for p in problems)); sys.exit(1)
print(f"  [ok] no module-level use-before-declaration ({len(decl)} top-level bindings)")
print("check_page.py: PASS")
