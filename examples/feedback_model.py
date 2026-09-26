"""Пример 3: модель с обратной связью + авто-размещение.

Демонстрирует полный конвейер:
1. Спецификация модели (блоки + связи) декларативно.
2. Автоматическая расстановка (LayeredPlacer).
3. Создание блоков в позициях placer'а.
4. Создание линий между портами.
5. Запуск расчёта.

Линии трассирует SimInTech: маршрут выбирает `NormalizeWire` (после
перерисовки редактора), а опорные точки на него не влияют, поэтому в
`create_wire` они не передаются — чистая схема получается расстановкой.

Обратная связь: y = u + 0.5*y (усилитель с замыканием на вход).
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from simintech_api import COMClient, Project
from simintech_api.layout import LayeredPlacer

# Спецификация модели: {id: (класс, свойства)}, связи: [(src, dst)]
SPEC = {
    "source": ("Ступенька", {"t": 0.0, "y0": 0.0, "yk": 1.0}),
    "sum": ("Сумматор", {"a": [1.0, 1.0]}),
    "gain": ("Усилитель", {"a": 1.5}),
    "fb": ("Усилитель", {"a": 0.5}),
}
LINKS = [
    ("source", "sum"),   # вход задания
    ("sum", "gain"),     # сумма -> усилитель
    ("gain", "fb"),      # выход -> обратная связь
    ("fb", "sum"),       # обратная связь -> на вход сумматора (петля)
]

# Дефолтные размеры блоков
SIZES = {k: (60.0, 40.0) for k in SPEC}


def main() -> None:
    client = COMClient(silent_mode=True).connect()
    # Проект — из шаблона: у `Project.new()` нет расчётного слоя, и модельное
    # время в нём не растёт, хотя run_to сообщает об успехе.
    prj = Project.from_template(client)
    prj.set_calc_end_time(5.0)       # конечное время расчёта
    page = prj.get_main_page()

    # 1. Расстановка (обратная связь поддерживается placer'ом)
    placer = LayeredPlacer()
    positions = placer.place(list(SPEC.keys()), LINKS, sizes=SIZES)
    print("Позиции блоков:", positions)

    # 2. Создание блоков в вычисленных позициях
    blocks = {}
    for bid, (cls, props) in SPEC.items():
        cx, cy = positions[bid]
        b = page.create_block(cls, cx, cy)
        for k, v in props.items():
            b.set_property(k, v)
        b.set_name(bid)
        blocks[bid] = b

    # 3. Линии между портами. Маршрут задаёт SimInTech, поэтому опорные точки
    #    не передаются: `create_wire(points=…)` маршрутом не управляет и
    #    предупреждает об этом.
    for src, dst in LINKS:
        out_p = blocks[src].get_out_port(0)
        in_p = blocks[dst].get_in_port(0)
        page.create_wire(out_p, in_p)

    # 4. Сохранение и расчёт
    out = os.path.join(os.path.dirname(__file__), "feedback_model.xprt")
    prj.save_xml(out)
    print(f"Модель с обратной связью сохранена: {out}")

    sim = prj.simulation()
    sim.start()
    # run_to не блокирующий: True вернётся только если время действительно
    # дошло до отметки.
    reached = sim.run_to(5.0)
    print(f"Модельное время: {sim.get_time():.3f} с")
    sim.stop()

    prj.close()
    client.disconnect()
    if not reached:
        print("Расчёт не дошёл до 5 с. Проверьте конечное время расчёта "
              "(set_calc_end_time) и входы блоков: неподключённый вход молча "
              "останавливает расчёт всей модели.")
    else:
        print("Готово. Установившееся значение выхода: u * a / (1 - a*fb) "
              "с учётом топологии сумматора.")


if __name__ == "__main__":
    main()
