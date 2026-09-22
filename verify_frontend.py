"""Headless verification for frontend/app.py.

Checks:
  1. every theme defines the same CSS variables (no half-themed palette possible)
  2. the app renders with zero exceptions
  3. every theme can be selected and still renders with zero exceptions

Run from the repo root with the venv active.
"""
import ast
import os

from streamlit.testing.v1 import AppTest

APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "frontend", "app.py"))

# --- 1. structural check ---------------------------------------------------
src = open(APP, encoding="utf-8").read()
tree = ast.parse(src)
themes = None
for node in tree.body:
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(getattr(t, "id", "") == "THEMES" for t in targets):
            themes = ast.literal_eval(node.value)

assert themes, "THEMES table not found in app.py"
ref = set(themes["Midnight Moss"])
for name, values in themes.items():
    assert set(values) == ref, f"{name} is missing/extras {set(values) ^ ref}"
print(f"[ok] {len(themes)} themes, {len(ref)} variables each, structurally identical")

# --- 2. first render -------------------------------------------------------
at = AppTest.from_file(APP, default_timeout=40)
at.run()
assert not at.exception, [e.value for e in at.exception]
print("[ok] default render, 0 exceptions")

# --- 3. every theme renders ------------------------------------------------
labels = [s.label for s in at.selectbox]
theme_idx = labels.index("Background theme")
for option in at.selectbox[theme_idx].options:
    at.selectbox[theme_idx].set_value(option).run()
    assert not at.exception, (option, [e.value for e in at.exception])
    print(f"[ok] theme renders: {option}")

print("[done] all themes verified")