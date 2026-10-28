"""Чистота Model IR: ядро не тянет COM и внутренности core."""

import ast
import os
import pathlib
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

ROOT = pathlib.Path(__file__).resolve().parents[2] / "simintech_api" / "model_ir"


def _imports_from_source(source: str) -> set[str]:
    """Все импорты, включая канонические формы ``from .. import core``."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            if node.module:
                found.add(module)
                found.update(f"{module}.{alias.name}" for alias in node.names)
            else:
                found.update("." * node.level + alias.name
                             for alias in node.names)
    return found


def _forbidden(found: set[str]) -> set[str]:
    return {
        name for name in found
        if name == "comtypes"
        or name.startswith("comtypes.")
        or name == "simintech_api.core"
        or name.startswith("simintech_api.core.")
        or name.endswith(".core")
        or name.startswith("..core")
    }


@pytest.mark.parametrize("source", [
    "import comtypes",
    "import comtypes.client",
    "from .. import core",
    "from simintech_api import core",
    "from simintech_api.core import project",
])
def test_purity_gate_detects_canonical_forms(source):
    assert _forbidden(_imports_from_source(source)), source


def test_model_ir_does_not_import_com_or_core():
    for path in ROOT.rglob("*.py"):
        found = _imports_from_source(path.read_text(encoding="utf-8"))
        assert not _forbidden(found), f"{path}: {sorted(_forbidden(found))}"


def test_model_ir_init_does_not_import_live():
    found = _imports_from_source((ROOT / "__init__.py").read_text(
        encoding="utf-8"))
    assert not any("live" in name for name in found), sorted(found)
