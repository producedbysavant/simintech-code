"""Тесты алгоритма размещения LayeredPlacer."""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from simintech_api.layout import LayeredPlacer


def test_linear_chain():
    placer = LayeredPlacer()
    pos = placer.place(['A', 'B', 'C'], [('A', 'B'), ('B', 'C')])
    # A на слое 0, B на слое 1, C на слое 2
    assert pos['A'][0] < pos['B'][0] < pos['C'][0]
    # Все по одной вертикали (y одинаковый)
    ys = {pos[k][1] for k in pos}
    assert len(ys) == 1


def test_no_overlap():
    placer = LayeredPlacer()
    blocks = [f'b{i}' for i in range(20)]
    conns = [(f'b{i}', f'b{i+1}') for i in range(19)]
    pos = placer.place(blocks, conns)
    placed = list(pos.values())
    for i, a in enumerate(placed):
        for b in placed[i + 1:]:
            assert abs(a[0] - b[0]) > 20 or abs(a[1] - b[1]) > 20, \
                f"Наложение: {a} и {b}"


def test_branching():
    placer = LayeredPlacer()
    pos = placer.place(['A', 'B', 'C'], [('A', 'B'), ('A', 'C')])
    # A на слое 0, B и C на слое 1 с разными y
    assert pos['A'][0] < pos['B'][0]
    assert pos['A'][0] < pos['C'][0]
    assert pos['B'][1] != pos['C'][1]


def test_feedback_loop():
    """Обратная связь (цикл) не должна ломать ранжирование."""
    placer = LayeredPlacer()
    # A -> B, B -> A (цикл) + внешний вход A
    pos = placer.place(['A', 'B'], [('A', 'B'), ('B', 'A')])
    assert set(pos.keys()) == {'A', 'B'}


def test_empty():
    placer = LayeredPlacer()
    assert placer.place([], []) == {}


def test_single_consumer_source_placed_next_to_consumer():
    """Источник с единственным приёмником ставится вплотную к нему.

    Иначе линия тянется через всю схему: SimInTech ведёт её через середину
    между портами, и она проходит сквозь промежуточные блоки. Проверено на
    SimInTech64 2026-09-15 на модели «Константа -> Интегратор -> Усилитель ->
    Сумматор» со второй константой на входе сумматора.
    """
    placer = LayeredPlacer()
    pos = placer.place(
        ["c1", "integ", "gain", "c2", "summ"],
        [("c1", "integ"), ("integ", "gain"), ("gain", "summ"),
         ("c2", "summ")])

    # c2 идёт на вход summ: её слой — непосредственно перед summ,
    # то есть тот же, где усилитель, но в другой строке
    assert pos["gain"][0] == pos["c2"][0] < pos["summ"][0]
    assert pos["c2"][1] != pos["gain"][1]
    # её линия стала короткой: раньше c2 стояла на слое 0
    assert pos["c2"][0] > pos["c1"][0]


def test_multi_consumer_source_stays_in_first_layer():
    """Блок, от которого зависят несколько, остаётся в первом слое.

    Сдвиг вправо развернул бы часть его связей назад.
    """
    placer = LayeredPlacer()
    pos = placer.place(
        ["src", "a", "b", "c"],
        [("src", "a"), ("a", "c"), ("b", "c"), ("src", "b")])

    assert pos["src"][0] < pos["a"][0]
    assert pos["src"][0] < pos["b"][0]


def test_chain_keeps_first_layer():
    """В обычной цепочке источник остаётся на первом слое."""
    placer = LayeredPlacer()
    pos = placer.place(["a", "b", "c", "d"],
                       [("a", "b"), ("b", "c"), ("c", "d")])

    assert pos["a"][0] < pos["b"][0] < pos["c"][0] < pos["d"][0]
    assert pos["a"][0] == 0.0


def test_pure_cycle_places():
    """Чистый цикл без внешних источников размещается (корень = min входов)."""
    placer = LayeredPlacer()
    pos = placer.place(['A', 'B'], [('A', 'B'), ('B', 'A')])
    assert set(pos.keys()) == {'A', 'B'}
    # Цикл разрывается: корень ('A' — первый по списку) встаёт на слой 0, 'B' —
    # на следующий. Прежняя проверка (`A == B or A < B or B < A`) истинна при
    # любых числах, то есть не падала бы ни при каком размещении.
    assert pos['A'][0] == 0.0
    assert pos['B'][0] > pos['A'][0]


def test_layer_step_follows_canon_not_constant():
    """Шаг слоя — канон ТЗ 4.2 (col_width + channel_w), а не фиксированные 160.

    Тест держит величину шага: подмена формулы (например, возврат к LAYER_GAP)
    краснит его. Звено цепочки выровнено по Y, поэтому разрез пуст и канал равен
    STUB + WIRE_PITCH; у ветвления два невыровненных луча — канал шире на шаг
    трека.
    """
    placer = LayeredPlacer()

    chain = placer.place(['A', 'B', 'C'], [('A', 'B'), ('B', 'C')])
    assert chain['B'][0] == 88.0

    branch = placer.place(['A', 'B', 'C'], [('A', 'B'), ('A', 'C')])
    assert branch['B'][0] == 96.0


def test_explicit_layer_gap_is_only_a_floor():
    """Явный layer_gap — пол, а не шаг: канон может его перекрыть."""
    chain = [('A', 'B'), ('B', 'C')]

    wide = LayeredPlacer(layer_gap=200).place(['A', 'B', 'C'], chain)
    assert wide['B'][0] == 200.0

    narrow = LayeredPlacer(layer_gap=10).place(['A', 'B', 'C'], chain)
    assert narrow['B'][0] == 88.0


def test_vertical_gap_widens_with_pins_between():
    """Линии, пересекающие полосу зазора, расширяют её (канон ТЗ 4.x).

    Один пин в полосе канон не теснит — BLOCK_GAP = 16 уже равен
    WIRE_PITCH * (1 + 1); два расширяют зазор до 24, иначе вылеты соседних
    пинов делят один трек.
    """
    placer = LayeredPlacer()
    main = {1: ['b1', 'b2']}
    sizes = {'b1': (60.0, 40.0), 'b2': (60.0, 40.0)}
    ys = {'b1': 20.0, 'b2': 76.0, 's1': 0.0, 's2': 0.0,
          'r1': 50.0, 'r2': 50.0}
    layer_of = {'s1': 0, 's2': 0, 'r1': 2, 'r2': 2}

    one = placer._vertical_gaps(main, sizes, ys, layer_of,
                                [('s1', 'r1')], {})
    assert one[(1, 0)] == 16.0

    two = placer._vertical_gaps(main, sizes, ys, layer_of,
                                [('s1', 'r1'), ('s2', 'r2')], {})
    assert two[(1, 0)] == 24.0


def test_back_edge_channel_is_reserved_below_columns():
    """Обратные связи — не слой: под колонками резервируется канал (ТЗ 4.3)."""
    chain = LayeredPlacer()
    chain.place(['A', 'B', 'C'], [('A', 'B'), ('B', 'C')])
    assert chain.back_channel == 0.0

    loop = LayeredPlacer()
    loop.place(['A', 'B'], [('A', 'B'), ('B', 'A')])
    assert loop.back_channel == 8.0


def test_layer_step_accounts_for_neighbour_half_width():
    """Широкий сосед не съедает канал: считаются полуширины обеих колонок."""
    placer = LayeredPlacer()
    sizes = {'port': (260.0, 40.0), 'logic': (32.0, 40.0)}

    pos = placer.place(['port', 'logic'], [('port', 'logic')], sizes=sizes)

    assert pos['port'][0] == 0.0
    assert pos['logic'][0] == 176.0


def test_layers_normalized_no_forward_link_inside_column():
    """Прямая связь не остаётся внутри колонки: слои нормализуются.

    «Ромб»: b и c зависят от a, а c ещё и от b. Ранжирование ставило b и c в
    один слой, и связь b→c оказывалась внутриколоночной — аудит называл её
    «внутриколоночной».
    """
    placer = LayeredPlacer()

    pos = placer.place(['a', 'b', 'c'], [('a', 'b'), ('a', 'c'), ('b', 'c')])

    x = {name: pos[name][0] for name in pos}
    assert x['a'] < x['b'] < x['c']


def test_feedback_does_not_lift_its_target():
    """Обратная связь не поднимает слой приёмника: петля остаётся петлёй."""
    placer = LayeredPlacer()

    pos = placer.place(['a', 'b'], [('a', 'b'), ('b', 'a')])

    x = {name: pos[name][0] for name in pos}
    assert x['a'] < x['b']
