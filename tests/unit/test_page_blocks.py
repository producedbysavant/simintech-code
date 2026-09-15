"""Создание блоков: штатные размеры классов (без COM).

`CreateBlock` создаёт блок 60x40, а в моделях SimInTech для этих классов
приняты другие размеры — «Константа» 32x16, блоки с одним входом 32x32
(замерено на 20+ эталонных моделях, 2026-09-15). Блок нестандартного размера
считается нарушением правил разработки, поэтому размер выставляется при
создании.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from simintech_api.constants import standard_block_size  # noqa: E402
from simintech_api.core.page import Page  # noqa: E402


class FakeClient:
    """Клиент, запоминающий вызовы; CreateBlock отдаёт фиксированный id."""

    def __init__(self, props=None, block_id=7):
        self.props = dict(props or {})
        self.block_id = block_id
        self.calls = []

    def call(self, method, *args):
        self.calls.append((method, args))
        if method == "CreateBlock":
            return self.block_id
        if method == "GetBlockPropAsString":
            return self.props.get(args[1], "")
        return 0


class FakeProject:
    id = 5

    def __init__(self, client):
        self.client = client


def _page(props=None, block_id=7):
    client = FakeClient(props=props, block_id=block_id)
    return Page(FakeProject(client), 11), client


def _positions(client):
    return [c for c in client.calls if c[0] == "SetBlockPosition"]


# ─── Таблица штатных размеров ─────────────────────────────────────

def test_standard_size_of_constant():
    assert standard_block_size("Константа") == (32.0, 16.0)


def test_standard_size_of_single_input_blocks():
    for class_name in ("Усилитель", "Интегратор", "Ступенька", "Синусоида"):
        assert standard_block_size(class_name) == (32.0, 32.0)


def test_standard_size_of_sum_oper_by_inputs():
    """У «Сумматора» размер зависит от числа входов: 32x32 / 32x48."""
    assert standard_block_size("Сумматор") == (32.0, 32.0)
    assert standard_block_size("Сумматор", 2) == (32.0, 32.0)
    assert standard_block_size("Сумматор", 3) == (32.0, 48.0)


def test_standard_size_of_unknown_class():
    assert standard_block_size("НетТакогоКласса") is None


# ─── Применение при создании блока ────────────────────────────────

def test_create_block_applies_standard_size():
    page, client = _page()

    page.create_block("Константа", 10.0, 20.0)

    assert ("SetBlockPosition", (7, 10.0, 20.0, 32.0, 16.0, 0.0)) in client.calls


def test_create_block_keeps_explicit_size():
    """Явно заданный размер применяется как есть."""
    page, client = _page()

    page.create_block("Константа", 10.0, 20.0, width=80.0, height=60.0)

    assert ("SetBlockPosition", (7, 10.0, 20.0, 80.0, 60.0, 0.0)) in client.calls


def test_create_block_leaves_size_of_unknown_class():
    """Неизмеренный класс не переразмеряем — берём размер, что дал блок."""
    page, client = _page(props={"Width": "60", "Height": "40"})

    page.create_block("Динамические", 0.0, 0.0)

    assert ("SetBlockPosition", (7, 0.0, 0.0, 60.0, 40.0, 0.0)) in client.calls


def test_create_block_activates_page():
    """Перед CreateBlock страница делается текущей (SetCurrentPage)."""
    page, client = _page()

    page.create_block("Усилитель", 0.0, 0.0)

    assert ("SetCurrentPage", (5, 11)) in client.calls
