"""Повторяющаяся ячейка — дорожка, а не плоский граф (ТЗ 4.4).

Столбцы «& / 1 / >» на схеме — одна и та же ячейка, повторённая по строкам.
Плоская укладка ставит экземпляры в одну колонку и сваливает их связи в один
разрез; параллельные непересекающиеся горизонтали — то, что человек читает как
шину, — получаются только тогда, когда экземпляр идёт строкой, а позиция внутри
ячейки — колонкой: `row = index`, `col = позиция в паттерне`.

Ячейка выделяется до раскладки: одинаковая цепочка классов, одинаковая степень
по позициям и связи внутри группы только к соседу по индексу. Если ячейка не
выделяется — схему не раздуваем, остаётся канальная раскладка (в ответе
инструмента это `repeated_cell: no`).
"""

from __future__ import annotations

from ..constants import BLOCK_GAP

from .canon import channel_width, cut_sizes, round_step
from typing import (
    Dict,
    Hashable,
    List,
    NamedTuple,
    Optional,
    Sequence,
    Set,
    Tuple,
    TypeVar,
)

_Item = TypeVar("_Item", bound=Hashable)


class RepeatedCell(NamedTuple):
    """Выделенная повторяющаяся ячейка (ТЗ 4.4).

    `pattern` — классы позиций ячейки; `rows` — экземпляры по строкам, в
    строке блоки в порядке позиций. Укладка: строка — экземпляр, колонка —
    позиция паттерна.
    """

    pattern: List[str]
    rows: List[List[_Item]]


def _chains(
    items: "List[_Item]",
    outgoing: "Dict[_Item, Set[_Item]]",
    incoming: "Dict[_Item, Set[_Item]]",
) -> "List[List[_Item]]":
    """Максимальные цепочки: звено продолжается, пока вход у следующего один.

    Голова — блок, чей источник не единственный его приёмник (шина или
    внешний вход): иначе цепочка втянула бы в себя соседние строки.
    """
    chains: "List[List[_Item]]" = []
    for head in items:
        sources = incoming[head]
        if len(sources) == 1 and len(outgoing[next(iter(sources))]) == 1:
            continue
        chain = [head]
        seen = {head}
        current = head
        while True:
            outs = outgoing[current]
            if len(outs) != 1:
                break
            (nxt,) = tuple(outs)
            if nxt in seen or incoming[nxt] != {current}:
                break
            chain.append(nxt)
            seen.add(nxt)
            current = nxt
        if len(chain) >= 2:
            chains.append(chain)
    return chains


def detect_repeat(
    classes: "Dict[_Item, str]",
    connections: "Sequence[Tuple[_Item, _Item]]",
) -> "Optional[RepeatedCell]":
    """Выделить повторяющийся подграф (ТЗ 4.4) или `None`, если его нет.

    Группа считается ячейкой, когда в ней не меньше двух строк с одинаковым
    класс-паттерном, одинаковая длина и одинаковая степень по позициям, а рёбра
    внутри группы не соединяют строки между собой — только позиции внутри
    строки.
    """
    items = list(classes)
    outgoing: "Dict[_Item, Set[_Item]]" = {item: set() for item in items}
    incoming: "Dict[_Item, Set[_Item]]" = {item: set() for item in items}
    for src, dst in connections:
        if src in outgoing and dst in incoming:
            outgoing[src].add(dst)
            incoming[dst].add(src)

    groups: "Dict[Tuple[str, ...], List[List[_Item]]]" = {}
    for chain in _chains(items, outgoing, incoming):
        groups.setdefault(tuple(classes[item] for item in chain), []).append(chain)

    for pattern, rows in groups.items():
        if len(rows) < 2 or len(pattern) < 2:
            continue
        degrees = {
            tuple((len(outgoing[item]), len(incoming[item]))
                  for item in row)
            for row in rows}
        if len(degrees) != 1:
            continue
        in_group = {item for row in rows for item in row}
        if any(dst in in_group and dst not in row
               for row in rows
               for src in row
               for dst in outgoing[src]):
            continue
        return RepeatedCell(list(pattern), rows)
    return None


def place_repeat(
    cell: "RepeatedCell",
    sizes: "Dict[_Item, Tuple[float, float]]",
    origin: "Tuple[float, float]" = (0.0, 0.0),
) -> "Dict[_Item, Tuple[float, float]]":
    """Координаты дорожки: строка — экземпляр, колонка — позиция (ТЗ 4.4).

    Шаг колонки — канон 4.2: через каждый зазор позиции идут горизонтали всех
    строк, поэтому мощность разреза равна числу строк. Строки разводятся
    базовым зазором: между ними проходят только собственные горизонтали строк,
    и каждая уже лежит на своём треке.
    """
    if not cell.pattern or not cell.rows:
        return {}
    columns = len(cell.pattern)
    widths = [
        max(sizes.get(row[col], (60.0, 40.0))[0] for row in cell.rows)
        for col in range(columns)]
    heights = [
        max(sizes.get(item, (60.0, 40.0))[1] for item in row)
        for row in cell.rows]
    # Разрез — все связи строки, без вычитания выровненных: по центрам
    # строки стоят на одном Y, но пины смещены (in:0 — на центр − 8),
    # поэтому до ТЗ 4.1 выравненность по центрам не считается.
    nets = [(col, col + 1, False)
            for _row in cell.rows for col in range(columns - 1)]
    cuts = cut_sizes(nets, columns - 1)
    xs: "List[float]" = [origin[0]]
    for col in range(columns - 1):
        xs.append(xs[col] + round_step(
            widths[col] / 2.0 + channel_width(cuts[col])
            + widths[col + 1] / 2.0))
    result: "Dict[_Item, Tuple[float, float]]" = {}
    y = origin[1]
    for index, row in enumerate(cell.rows):
        if index:
            y += heights[index - 1] / 2.0 + BLOCK_GAP + heights[index] / 2.0
        for col, item in enumerate(row):
            result[item] = (xs[col], y)
    return result


def collapse_repeat(
    cell: "RepeatedCell",
    block_ids: "Sequence[_Item]",
    connections: "Sequence[Tuple[_Item, _Item]]",
) -> "Tuple[List[object], List[Tuple[object, object]], Dict[object, List[_Item]]]":
    """Свести дорожку к супер-узлам, чтобы она встала по потоку (ТЗ 4.4).

    Позиция паттерна становится одним узлом; строки разворачиваются на его
    месте. Раскладка считается по супер-узлам, поэтому ячейка садится после
    своих внешних предшественников и до внешних потребителей — жёсткое «слева»
    оказалось бы частным случаем, когда предшественников у группы нет вовсе.

    Возвращает (узлы, рёбра, разворот): разворот — что за строки стоят на месте
    каждого супер-узла, в порядке строк.
    """
    columns = len(cell.pattern)
    rows_of: "Dict[object, List[_Item]]" = {
        ("cell", col): [row[col] for row in cell.rows]
        for col in range(columns)}
    owner: "Dict[_Item, object]" = {
        item: node for node, items in rows_of.items() for item in items}
    nodes: "List[object]" = list(rows_of)
    for item in block_ids:
        if item not in owner:
            nodes.append(item)
    edges: "List[Tuple[object, object]]" = []
    for src, dst in connections:
        from_node = owner.get(src, src)
        to_node = owner.get(dst, dst)
        if from_node == to_node:
            continue
        if from_node not in nodes or to_node not in nodes:
            continue
        if (from_node, to_node) not in edges:
            edges.append((from_node, to_node))
    return nodes, edges, rows_of
