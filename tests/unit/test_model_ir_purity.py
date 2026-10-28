"""Чистота Model IR: ядро не тянет COM и внутренности core."""

import ast
import os
import pathlib
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

ROOT = pathlib.Path(__file__).resolve().parents[2] / "simintech_api" / "model_ir"


def _imports(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.add("." * node.level + (node.module or ""))
    return found


def test_model_ir_does_not_import_com_or_core():
    for path in ROOT.rglob("*.py"):
        found = _imports(path)
        forbidden = {name for name in found
                     if name == "comtypes"
                     or name == "simintech_api.core"
                     or name.startswith("simintech_api.core.")
                     or name.endswith(".core")
                     or ".core." in name}
        assert not forbidden, f"{path}: {sorted(forbidden)}"


def test_model_ir_init_does_not_import_live():
    found = _imports(ROOT / "__init__.py")
    assert not any("live" in name for name in found), sorted(found)
