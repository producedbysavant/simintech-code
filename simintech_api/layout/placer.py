"""Алгоритм размещения блоков (Sugiyama-подобный layered layout).

Вход: граф связей «блок -> список блоков-приёмников» + размеры блоков.
Выход: словарь {block_id: (cx, cy)} — координаты центров без наложений.

Схема расположения — горизонтальная (слева направо): слой по X,
внутри слоя блоки по Y.
"""

from __future__ import annotations

from typing import (
    Dict,
    Hashable,
    Iterable,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    TypeVar,
)

from ..constants import BLOCK_GAP, LAYER_GAP

# Ключ блока — любой хешируемый: алгоритм раскладывает граф по ключам и не
# заглядывает внутрь. Идентификатор не обязан быть int: примеры и тесты
# библиотеки адресуют блоки именами (`'A'`, `'k_0'`), и потребитель
# (simintech-mcp) — тоже. Аннотация `int` отвергала такую передачу.
_BlockId = TypeVar("_BlockId", bound=Hashable)


class LayeredPlacer:
    """Размещение блоков слоями по направлению сигнала.

    Args:
        layer_gap: расстояние между слоями по X.
        block_gap: расстояние между блоками в слое по Y.
    """

    def __init__(self, layer_gap: float = LAYER_GAP,
                 block_gap: float = BLOCK_GAP):
        self.layer_gap = layer_gap
        self.block_gap = block_gap

    def place(
        self,
        block_ids: Iterable[_BlockId],
        connections: Iterable[Tuple[_BlockId, _BlockId]],
        sizes: Optional[Dict[_BlockId, Tuple[float, float]]] = None,
        origin: Tuple[float, float] = (0.0, 0.0),
    ) -> Dict[_BlockId, Tuple[float, float]]:
        """Вычислить координаты центров блоков.

        Args:
            block_ids: идентификаторы блоков — id или имена (ключ хешируемый,
                алгоритм его не разбирает).
            connections: пары (источник, приёмник) — направление сигнала.
            sizes: {block_id: (width, height)}; по умолчанию (60, 40).
            origin: координата центра первого блока (cx0, cy0).

        Returns:
            {block_id: (cx, cy)}.

        Raises:
            LayoutError: если граф содержит цикл без внешних источников
                (обратные связи разрешены — они просто не образуют новый слой).
        """
        block_ids = list(block_ids)
        if not block_ids:
            return {}

        sizes = sizes or {}
        # Индексы блоков
        idx = {bid: i for i, bid in enumerate(block_ids)}

        # Строим граф: для каждого блока множество источников (от кого зависит)
        incoming: Dict[_BlockId, Set[_BlockId]] = {bid: set() for bid in block_ids}
        outgoing: Dict[_BlockId, Set[_BlockId]] = {bid: set() for bid in block_ids}
        for src, dst in connections:
            if src in idx and dst in idx:
                incoming[dst].add(src)
                outgoing[src].add(dst)

        # 1) Ранжирование (слои по X)
        layers: List[List[_BlockId]] = []          # layer -> [block_id]
        layer_of: Dict[_BlockId, int] = {}
        placed: Set[_BlockId] = set()

        # Первый слой — блоки без входов. Если таких нет (чистый цикл /
        # обратная связь без внешнего источника), назначаем корнем блок
        # с минимальным числом входов и считаем его источником.
        frontier = [b for b in block_ids if not incoming[b]]
        if not frontier and block_ids:
            root = min(block_ids, key=lambda b: len(incoming[b]))
            frontier = [root]
            # Исключаем root из зависимостей остальных — обратная связь
            # от root сама по себе (root не входит в свой слой)
            for bid in block_ids:
                incoming[bid].discard(root)

        while frontier:
            layer: List[_BlockId] = []
            next_frontier: List[_BlockId] = []
            for bid in frontier:
                if bid in placed:
                    continue
                # Проверяем, что все источники уже размещены в более ранних слоях
                if not incoming[bid] or all(s in placed for s in incoming[bid]):
                    layer.append(bid)
                    placed.add(bid)
                    next_frontier.extend(outgoing[bid])
            if not layer:
                # Остались только блоки в циклах — разместим их в новый слой
                layer = [b for b in frontier if b not in placed]
                placed.update(layer)
            if not layer:
                break
            layers.append(layer)
            for bid in layer:
                layer_of[bid] = len(layers) - 1
            frontier = [
                b for b in next_frontier
                if b not in placed
                and b not in (item for sub in layers for item in sub)
            ]

        # Если что-то не разместилось (например, изолированные в цикле) — довесок
        remaining = [b for b in block_ids if b not in placed]
        if remaining:
            layers.append(remaining)
            for bid in remaining:
                layer_of[bid] = len(layers) - 1

        # 1a) Источник с единственным приёмником — вплотную к приёмнику.
        # Иначе линия тянется через всю схему, а SimInTech ведёт её через
        # середину между портами: длинная линия проходит сквозь промежуточные
        # блоки (проверено на SimInTech64 2026-09-15). Переносить можно только
        # источники с одним приёмником: у блока с несколькими приёмниками
        # смещение вправо развернуло бы часть связей назад. Такой блок встаёт
        # во «вспомогательный ряд» — ниже основного, иначе цепочка разъезжается
        # по вертикали.
        helpers: Set[_BlockId] = set()
        for bid in block_ids:
            if incoming[bid] or len(outgoing[bid]) != 1:
                continue
            (dst,) = tuple(outgoing[bid])
            target = layer_of.get(dst, 0) - 1
            if target <= layer_of[bid] or target >= len(layers):
                continue
            layers[layer_of[bid]].remove(bid)
            layers[target].append(bid)
            layer_of[bid] = target
            helpers.add(bid)

        # Опустевшие слои убираем — иначе схема начнётся с пропуска по X.
        if any(not layer for layer in layers):
            layers[:] = [layer for layer in layers if layer]
            for index, layer in enumerate(layers):
                for bid in layer:
                    layer_of[bid] = index

        # 2) Упорядочивание внутри слоя (медианная эвристика)
        for li, layer in enumerate(layers):
            if li == 0:
                continue
            # Для каждого блока слоя — медиана позиций источников в предыдущем слое
            medians: Dict[_BlockId, float] = {}
            prev_positions = {bid: pos for pos, bid in enumerate(layers[li - 1])}
            for bid in layer:
                srcs = [prev_positions[s] for s in incoming[bid] if s in prev_positions]
                medians[bid] = _median(srcs) if srcs else float(len(prev_positions))
            layers[li] = sorted(layer, key=lambda b: medians[b])

        # 3) Координаты центров
        result: Dict[_BlockId, Tuple[float, float]] = {}
        cx0, cy0 = origin

        def height(items: List[_BlockId]) -> float:
            return (sum(sizes.get(b, (60.0, 40.0))[1] for b in items)
                    + self.block_gap * max(0, len(items) - 1))

        # Высоту считаем по основному ряду: вспомогательные блоки стоят ниже и
        # на выравнивание слоёв влиять не должны, иначе цепочка разъезжается.
        main = {li: [b for b in layer if b not in helpers]
                for li, layer in enumerate(layers)}
        max_layer_height = max(
            (height(items) for items in main.values()), default=0.0)

        for li, layer in enumerate(layers):
            # Вертикальное центрирование слоя относительно самой высокой колонки
            y_start = cy0 + (max_layer_height - height(main[li])) / 2.0
            y = y_start
            for bid in main[li]:
                w, h = sizes.get(bid, (60.0, 40.0))
                result[bid] = (cx0 + li * self.layer_gap, y + h / 2.0)
                y += h + self.block_gap
            # Вспомогательный ряд — под основным, с тем же шагом
            y = y_start + height(main[li]) + (
                self.block_gap if main[li] else 0.0)
            for bid in layer:
                if bid not in helpers:
                    continue
                w, h = sizes.get(bid, (60.0, 40.0))
                result[bid] = (cx0 + li * self.layer_gap, y + h / 2.0)
                y += h + self.block_gap
            cx0 += 0  # X каждого слоя фиксирован: cx0 + li*layer_gap

        return result


def _median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return float(s[n // 2])
    return (s[n // 2 - 1] + s[n // 2]) / 2.0
