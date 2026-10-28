"""Model IR на реальных выгрузках поставки.

Тесты запускаются только явно: `pytest -m distribution`. Пути берутся из
`SIMINTECH_IR_DEMO` и `SIMINTECH_XPRT_DIRS`; в репозиторий выгрузки не
попадают.
"""

import os
import pathlib
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from simintech_api.model_ir import WireKind, parse_xprt_file  # noqa: E402

pytestmark = pytest.mark.distribution


def _demo() -> pathlib.Path | None:
    raw = os.environ.get("SIMINTECH_IR_DEMO", "").strip()
    return pathlib.Path(raw) if raw else None


def _xprt_files() -> list[pathlib.Path]:
    raw = os.environ.get("SIMINTECH_XPRT_DIRS", "").strip()
    result: list[pathlib.Path] = []
    for part in raw.split(os.pathsep):
        if not part:
            continue
        root = pathlib.Path(part)
        if root.is_file() and root.suffix.lower() == ".xprt":
            result.append(root)
        elif root.is_dir():
            result.extend(sorted(root.glob("*.xprt")))
    return result


def test_demo_is_complete_and_stable():
    path = _demo()
    if path is None:
        pytest.skip("SIMINTECH_IR_DEMO не задан")
    ir = parse_xprt_file(path)
    assert ir.containers, "в выгрузке нет контейнеров"
    assert ir.objects, "в выгрузке нет объектов"
    assert ir.wires, "в выгрузке нет проводов"
    assert ir.coverage.unresolved_ends == 0
    assert ir.coverage.unresolved_branches == 0
    assert ir.coverage.objects == len(ir.objects)
    assert ir.coverage.wires == len(ir.wires)
    assert ir.coverage.branches == sum(
        1 for item in ir.wires if item.kind is WireKind.BRANCH)
    assert ir.coverage.ports_real == sum(len(item.ports) for item in ir.objects)
    again = parse_xprt_file(path)
    assert again.meta.structure_hash == ir.meta.structure_hash
    assert again.meta.content_hash == ir.meta.content_hash


def test_configured_files_parse_with_consistent_coverage():
    files = _xprt_files()
    if not files:
        pytest.skip("SIMINTECH_XPRT_DIRS не задан")
    for path in files:
        ir = parse_xprt_file(path)
        assert ir.coverage.objects == len(ir.objects), path
        assert ir.coverage.wires == len(ir.wires), path
        assert ir.meta.structure_hash, path
