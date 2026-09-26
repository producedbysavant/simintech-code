"""Модель 3: «Многокомпонентная система» — проверка layout.

Создаёт 12 блоков со сложной структурой (несколько параллельных ветвей и
перекрёстные связи), использует LayeredPlacer для автоматической расстановки,
соединяет порты и выводит координаты блоков; проверяет отсутствие наложений.

Линии трассирует SimInTech: маршрут выбирает `NormalizeWire` (после
перерисовки редактора), а опорные точки на него не влияют, поэтому в
`create_wire` они не передаются.

Расчёт не запускается: проект создаётся через `Project.new()` — проверяется
только layout, а расчётный слой такому проекту не нужен.

Запуск (Windows): python examples/model3_complex.py
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from simintech_api import COMClient, Project
from simintech_api.layout import LayeredPlacer

# Спецификация модели: id -> (класс, свойства)
SPEC = {
    "src1": ("Синусоида", {}),
    "src2": ("Ступенька", {"t": 0.0, "y0": 0.0, "yk": 1.0}),
    "sum1": ("Сумматор", {"a": [1.0, 1.0]}),
    "g1": ("Усилитель", {"a": 1.5}),
    "g2": ("Усилитель", {"a": 0.8}),
    "int1": ("Интегратор", {"k": 1.0, "x0": 0.0}),
    "sum2": ("Сумматор", {"a": [1.0, 1.0, 1.0]}),
    "g3": ("Усилитель", {"a": 2.0}),
    "g4": ("Усилитель", {"a": 0.5}),
    "int2": ("Интегратор", {"k": 1.0, "x0": 0.0}),
    "sum3": ("Сумматор", {"a": [1.0, -1.0]}),
    "plot": ("Временной график", {}),
}

# Связи (src, dst, in_index): перекрёстные и параллельные ветви
LINKS = [
    ("src1", "sum1", 0),
    ("src2", "sum1", 1),
    ("sum1", "g1", 0),
    ("sum1", "g2", 0),
    ("g1", "int1", 0),
    ("g2", "sum2", 0),
    ("int1", "sum2", 1),
    ("g1", "sum2", 2),
    ("sum2", "g3", 0),
    ("sum2", "g4", 0),
    ("g3", "int2", 0),
    ("int2", "sum3", 0),
    ("g4", "sum3", 1),
    ("sum3", "plot", 0),
]

SIZES = {k: (60.0, 40.0) for k in SPEC}


def main() -> None:
    print("=== Модель 3: многокомпонентная система (layout) ===")
    client = COMClient(silent_mode=True).connect()
    prj = Project.new(client)
    page = prj.get_main_page()

    # 1. Автоматическая расстановка (LayeredPlacer)
    placer = LayeredPlacer()
    positions = placer.place(list(SPEC.keys()),
                             [(s, d) for s, d, _ in LINKS],
                             sizes=SIZES)
    print("\nРасстановка блоков (LayeredPlacer):")
    for bid, (cx, cy) in positions.items():
        print(f"  {bid:5s} -> ({cx:7.1f}, {cy:7.1f})")

    # Проверка: блоки не накладываются
    placed = list(positions.values())
    overlaps = 0
    for i, a in enumerate(placed):
        for b in placed[i + 1:]:
            if abs(a[0] - b[0]) < 40 and abs(a[1] - b[1]) < 40:
                overlaps += 1
    print(f"  Наложений блоков: {overlaps}")
    assert overlaps == 0

    # 2. Создание блоков в вычисленных позициях
    blocks = {}
    for bid, (cls, props) in SPEC.items():
        cx, cy = positions[bid]
        b = page.create_block(cls, cx, cy)
        b.set_name(bid)
        for k, v in props.items():
            b.set_property(k, v)
        blocks[bid] = b

    # 3. Создание линий между портами. Маршрут задаёт SimInTech, поэтому
    #    опорные точки не передаются: `create_wire(points=…)` маршрутом не
    #    управляет и предупреждает об этом.
    print("\nСоздание линий:")
    wires = []
    for src, dst, in_idx in LINKS:
        out_p = blocks[src].get_out_port(0)
        in_p = blocks[dst].get_in_port(in_idx)
        w = page.create_wire(out_p, in_p)
        wires.append(w)
        print(f"  {src}->{dst}: линия {w.id}")

    # 4. Сохранение и проверка
    out = os.path.join(os.path.dirname(__file__), "model3_complex.xprt")
    prj.save_xml(out)
    print(f"\nМодель сохранена: {out}")
    print(f"Блоков: {len(blocks)}, линий: {len(wires)}")

    prj.close()
    client.shutdown()
    print("Модель 3 готова. Блоки не накладываются; маршрут линий — "
          "за SimInTech (NormalizeWire).")


if __name__ == "__main__":
    main()
