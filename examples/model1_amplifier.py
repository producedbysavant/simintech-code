"""Модель 1: «Усилитель сигнала».

Схема: Синусоида (1 Гц, амплитуда 1) -> Усилитель (коэффициент 2.5).
Расчёт на 10 секунд с проверкой возврата run_to, сохранение схемы в
model1_amplifier.xprt.

Запуск (Windows, mmain.exe /regserver):
    python examples/model1_amplifier.py
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from simintech_api import COMClient, Project


def main() -> None:
    print("=== Модель 1: Усилитель сигнала ===")
    client = COMClient(silent_mode=True).connect()

    # 1. Проект и блоки
    # Проект — из шаблона: у `Project.new()` нет расчётного слоя, и модельное
    # время в нём не растёт, хотя вызовы сообщают об успехе.
    prj = Project.from_template(client)
    prj.set_calc_end_time(10.0)      # конечное время расчёта
    page = prj.get_main_page()

    src = page.create_block("Синусоида", 0, 0)
    src.set_property("Name", "SinSource")
    # Частота 1 Гц, амплитуда 1 (значения по умолчанию; при необходимости
    # задаются свойствами блока Синусоида)

    gain = page.create_block("Усилитель", 200, 0)
    gain.set_property("Name", "Gain")
    gain.set_property("a", 2.5)   # коэффициент усиления

    src.connect(gain)
    prj.save_xml(os.path.join(os.path.dirname(__file__), "model1_amplifier.xprt"))

    # 2. Расчёт на 10 секунд
    sim = prj.simulation()
    sim.start()
    # run_to не блокирующий: True вернётся только если время действительно
    # дошло до отметки (у `sim.run()` нет ни цели, ни остановки).
    reached = sim.run_to(10.0)
    print(f"Модельное время: {sim.get_time():.3f} с")
    if not reached:
        print("Расчёт не дошёл до 10 с. Проверьте конечное время расчёта "
              "(set_calc_end_time) и входы блоков: неподключённый вход молча "
              "останавливает расчёт всей модели.")
    sim.stop()

    # 3. Считываем сигналы по именам блоков
    #    Выход синусоиды — сигнал с именем блока SinSource (как сигнал блока);
    #    выход усилителя — сигнал Gain. Имена сигналов уточняются по списку.
    signals = {s.name: s for s in prj.list_signals()}
    print(f"Сигналов в модели: {len(signals)}")
    for name in list(signals)[:10]:
        print(f"  {name}")

    prj.close()
    client.shutdown()
    print("Модель 1 построена и сохранена: model1_amplifier.xprt")
    print("Примечание: для точного чтения сигналов используется список "
          "list_signals() и Project.signal(name) — см. model3_complex.py "
          "с полным конвейером чтения.")


if __name__ == "__main__":
    main()
