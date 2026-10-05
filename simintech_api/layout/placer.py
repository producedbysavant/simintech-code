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

from ..constants import BLOCK_GAP

from .canon import WIRE_PITCH, channel_width, round_step

# Ключ блока — любой хешируемый: алгоритм раскладывает граф по ключам и не
# заглядывает внутрь. Идентификатор не обязан быть int: примеры и тесты
# библиотеки адресуют блоки именами (`'A'`, `'k_0'`), и потребитель
# (simintech-mcp) — тоже. Аннотация `int` отвергала такую передачу.
_BlockId = TypeVar("_BlockId", bound=Hashable)


class LayeredPlacer:
    """Размещение блоков слоями по направлению сигнала.

    Args:
        layer_gap: ЯВНЫЙ пол шага слоёв по X. По канону (ТЗ 4.2) шаг
            считается формулой col_width + channel_w, а не задаётся
            константой; параметр нужен только чтобы задать пол
            осознанно (по умолчанию пола нет).
        block_gap: расстояние между блоками в слое по Y.
    """

    def __init__(self, layer_gap: Optional[float] = None,
                 block_gap: float = BLOCK_GAP):
        self.layer_gap = layer_gap
        self.block_gap = block_gap
        #: Высота нижнего канала обратных связей по последней раскладке
        #: (ТЗ 4.3). Заполняется `place`, читается аудитом.
        self.back_channel = 0.0

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
        connections = list(connections)
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
        # 1b) Нормализация слоёв: слой приёмника строго правее слоя источника.
        #     Ранжирование этого не обещало — обратные рёбра из него выкинуты, —
        #     и связанные блоки могли встать в одну колонку; аудит называет
        #     такие связи «внутриколоночными». Граф без обратных рёбер
        #     ациклический, поэтому подъём слоёв сходится.
        back = _back_edges(block_ids, outgoing)
        for _pass in range(len(block_ids) + 1):
            lifted = False
            for src_id, dst_id in connections:
                if (src_id, dst_id) in back:
                    continue
                if src_id not in layer_of or dst_id not in layer_of:
                    continue
                if layer_of[dst_id] <= layer_of[src_id]:
                    layer_of[dst_id] = layer_of[src_id] + 1
                    lifted = True
            if not lifted:
                break
        levels = max(layer_of.values(), default=-1) + 1
        rebuilt: List[List[_BlockId]] = [[] for _ in range(levels)]
        for bid in block_ids:
            if bid in layer_of:
                rebuilt[layer_of[bid]].append(bid)
        layers[:] = [layer for layer in rebuilt if layer]
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

        cx0, cy0 = origin

        # 3) Вертикальные координаты (Y): стопкой, зазор по канону.
        main = {li: [b for b in layer if b not in helpers]
                for li, layer in enumerate(layers)}
        gaps: Dict[Tuple[int, int], float] = {}
        ys, _heights = self._stack(layers, main, sizes, gaps, cy0)
        # Два прохода: полосы зазоров зависят от Y, а Y — от зазоров.
        for _pass in range(2):
            gaps = self._vertical_gaps(
                main, sizes, ys, layer_of, connections, gaps)
            ys, _heights = self._stack(layers, main, sizes, gaps, cy0)

        # 4) Шаг слоя по канону ТЗ 4.2 («канал шире разреза»):
        #    layer_x[i+1] = layer_x[i] + col_width(i) + channel_w(i),
        #    channel_w = STUB + WIRE_PITCH * max(1, cut_size).
        #    cut_size(i) — связи через зазор i минус выровненные в одну
        #    горизонталь: Y уже посчитан, выровненность берётся фактически.
        col_width = [
            max((sizes.get(b, (60.0, 40.0))[0] for b in layer), default=0.0)
            for layer in layers]
        edges = [
            (layer_of[src], layer_of[dst], src, dst)
            for src, dst in connections
            if src in layer_of and dst in layer_of
            and layer_of[src] < layer_of[dst]]
        xs = [cx0]
        for li in range(len(layers) - 1):
            # Разрез — ВСЕ связи через зазор: выравненность по центрам не
            # равна выравненности по пинам (у многопортового блока пин in:0
            # стоит на центр − 8), поэтому до ТЗ 4.1 выровненные не
            # вычитаем — иначе канал систематически занижен на 8 за связь.
            cut = sum(1 for ls, ld, _src, _dst in edges if ls <= li < ld)
            # Полуширины обеих колонок: иначе широкий сосед съедает канал
            # (порт 260 против логики 32 — зазор 14 px вместо 136).
            step = (col_width[li] / 2.0 + channel_width(cut)
                    + col_width[li + 1] / 2.0)
            if self.layer_gap is not None:
                step = max(self.layer_gap, step)
            xs.append(xs[li] + round_step(step))
        result: Dict[_BlockId, Tuple[float, float]] = {
            bid: (xs[li], ys[bid])
            for li, layer in enumerate(layers) for bid in layer}

        # 5) Обратные связи — не слой, а отдельный канал НИЖЕ всех
        #    колонок высотой WIRE_PITCH за связь (ТЗ 4.3). Раскладчик
        #    канал не рисует — он не трассирует, — но контракт держит:
        #    ниже колонок ничего не ставится, и маршруты обратных связей
        #    аудит вправе ждать именно здесь.
        self.back_channel = WIRE_PITCH * sum(
            1 for src, dst in connections
            if src in layer_of and dst in layer_of
            and layer_of[dst] <= layer_of[src])

        return result

    def _stack(
        self,
        layers: List[List[_BlockId]],
        main: Dict[int, List[_BlockId]],
        sizes: Dict[_BlockId, Tuple[float, float]],
        gaps: Dict[Tuple[int, int], float],
        origin_y: float,
    ) -> "Tuple[Dict[_BlockId, float], List[float]]":
        """Y-координаты стопкой в слое; зазор пары берётся из `gaps`.

        Возвращает (центры по Y, высоты слоёв). Вспомогательный ряд встаёт под
        основным с базовым зазором — как и было до канона: он не влияет на
        выравнивание слоёв, иначе цепочка разъезжается.
        """
        heights: List[float] = []
        for li, layer in enumerate(layers):
            total = 0.0
            for index, bid in enumerate(main[li]):
                total += sizes.get(bid, (60.0, 40.0))[1]
                if index:
                    total += gaps.get((li, index - 1), self.block_gap)
            heights.append(total)
        max_height = max(heights, default=0.0)
        ys: Dict[_BlockId, float] = {}
        for li, layer in enumerate(layers):
            start = origin_y + (max_height - heights[li]) / 2.0
            y = start
            for index, bid in enumerate(main[li]):
                h = sizes.get(bid, (60.0, 40.0))[1]
                ys[bid] = y + h / 2.0
                y += h + gaps.get((li, index), self.block_gap)
            y = start + heights[li]
            for bid in layer:
                if bid in main[li]:
                    continue
                h = sizes.get(bid, (60.0, 40.0))[1]
                y += self.block_gap
                ys[bid] = y + h / 2.0
                y += h
        return ys, heights

    def _vertical_gaps(
        self,
        main: Dict[int, List[_BlockId]],
        sizes: Dict[_BlockId, Tuple[float, float]],
        ys: Dict[_BlockId, float],
        layer_of: Dict[_BlockId, int],
        connections: Sequence[Tuple[_BlockId, _BlockId]],
        gaps: Dict[Tuple[int, int], float],
    ) -> Dict[Tuple[int, int], float]:
        """Зазор между соседними блоками колонки — по канону ТЗ 4.x.

        `pins_between` — число линий, пересекающих горизонтальную полосу зазора.
        Линия, прыгающая через колонку (источник левее, приёмник правее),
        проходит её на Y приёмника — там идёт её дальняя горизонталь; связь,
        оканчивающаяся в колонке или выходящая из неё, полосу не пересекает
        (её горизонталь лежит в канале, а не в теле колонки).

        Зазор = `max(BLOCK_GAP, WIRE_PITCH * (pins_between + 1))`: при
        BLOCK_GAP = 16 формула начинает влиять со второй такой линии (n = 2
        даёт 24), иначе вылеты соседних пинов сразу делят один трек.
        """
        result = dict(gaps)
        for li, items in main.items():
            for index in range(len(items) - 1):
                lower, upper = items[index], items[index + 1]
                top = ys[upper] - sizes.get(upper, (60.0, 40.0))[1] / 2.0
                bottom = ys[lower] + sizes.get(lower, (60.0, 40.0))[1] / 2.0
                pins = 0
                for src, dst in connections:
                    if src not in layer_of or dst not in layer_of:
                        continue
                    if layer_of[src] < li < layer_of[dst] and bottom < ys[dst] < top:
                        pins += 1
                result[(li, index)] = max(
                    self.block_gap, WIRE_PITCH * (pins + 1))
        return result


def _back_edges(
    block_ids: "List[_BlockId]",
    outgoing: "Dict[_BlockId, Set[_BlockId]]",
) -> "Set[Tuple[_BlockId, _BlockId]]":
    """Рёбра, замыкающие цикл (обратные связи) — их нормализация не трогает.

    Обход в глубину: ребро на вершину, которая ещё в стеке, — обратное. Именно
    эти рёбра ранжирование и выбрасывает; поднимать по ним слой приёмника
    значило бы выпрямить обратную связь и развернуть часть схемы назад.
    """
    state: "Dict[_BlockId, int]" = {bid: 0 for bid in block_ids}
    back: "Set[Tuple[_BlockId, _BlockId]]" = set()

    def visit(node: _BlockId) -> None:
        state[node] = 1
        for nxt in outgoing.get(node, set()):
            if state.get(nxt, 2) == 1:
                back.add((node, nxt))
            elif state.get(nxt, 2) == 0:
                visit(nxt)
        state[node] = 2

    for bid in block_ids:
        if state.get(bid, 0) == 0:
            visit(bid)
    return back


def _median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return float(s[n // 2])
    return (s[n // 2 - 1] + s[n // 2]) / 2.0
