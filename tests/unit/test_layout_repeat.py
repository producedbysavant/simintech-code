"""Тесты выделения повторяющейся ячейки (ТЗ 4.4)."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from simintech_api.layout.repeat import (
    collapse_repeat,
    detect_repeat,
    place_repeat,
)


def _three_rows():
    classes = {'s': 'src', 't': 'sink'}
    for row, name in enumerate(('a', 'b', 'c')):
        classes[name + '0'] = 'amp'
        classes[name + '1'] = 'one'
        classes[name + '2'] = 'cmp'
    connections = [('s', 'a0'), ('s', 'b0'), ('s', 'c0'),
                   ('a0', 'a1'), ('a1', 'a2'),
                   ('b0', 'b1'), ('b1', 'b2'),
                   ('c0', 'c1'), ('c1', 'c2'),
                   ('a2', 't'), ('b2', 't'), ('c2', 't')]
    return classes, connections


def test_detect_repeat_finds_rows_of_one_cell():
    """Три одинаковые цепочки по строкам — повторяющаяся ячейка."""
    classes, connections = _three_rows()

    cell = detect_repeat(classes, connections)

    assert cell is not None
    assert cell.pattern == ['amp', 'one', 'cmp']
    assert len(cell.rows) == 3
    assert cell.rows[0] == ['a0', 'a1', 'a2']


def test_detect_repeat_silent_without_cell():
    """Разные цепочки ячейкой не считаются — схему не раздуваем."""
    classes = {'a': 'amp', 'b': 'one', 'c': 'cmp', 'd': 'gain'}
    connections = [('a', 'b'), ('b', 'c'), ('c', 'd')]

    assert detect_repeat(classes, connections) is None


def test_detect_repeat_requires_equal_degree():
    """Разная степень по позициям — не ячейка, остаётся канальная раскладка."""
    classes = {'s': 'src', 'a0': 'amp', 'a1': 'one',
               'b0': 'amp', 'b1': 'one'}
    connections = [('s', 'a0'), ('s', 'b0'),
                   ('a0', 'a1'), ('b0', 'b1'), ('a1', 'b0')]

    assert detect_repeat(classes, connections) is None


def test_place_repeat_puts_instances_in_rows():
    """Экземпляр — строка, позиция паттерна — колонка: получается шина."""
    classes, connections = _three_rows()
    cell = detect_repeat(classes, connections)
    sizes = {item: (60.0, 40.0) for item in classes}

    pos = place_repeat(cell, sizes)

    assert pos['a0'][0] == pos['b0'][0] == pos['c0'][0]
    assert pos['a0'][1] == pos['a1'][1] == pos['a2'][1]
    assert pos['a0'][1] < pos['b0'][1] < pos['c0'][1]
    # Шаг колонки: по полуширине с каждой стороны (30 + 30) плюс канал
    # STUB + WIRE_PITCH * 3 — выровненность по центрам не вычитается.
    assert pos['a0'][0] == 0.0
    assert pos['a1'][0] == 104.0
    assert pos['a2'][0] == 208.0


def test_collapse_repeat_places_cell_by_flow():
    """Дорожка сводится к супер-узлам: позиция — узел, строки — на его месте."""
    classes, connections = _three_rows()
    cell = detect_repeat(classes, connections)

    nodes, edges, rows_of = collapse_repeat(cell, classes, connections)

    assert ('cell', 0) in nodes and 's' in nodes and 't' in nodes
    assert ('s', ('cell', 0)) in edges
    assert (('cell', 0), ('cell', 1)) in edges
    assert (('cell', 2), 't') in edges
    assert rows_of[('cell', 0)] == ['a0', 'b0', 'c0']
    assert ('a0', ('cell', 1)) not in edges
