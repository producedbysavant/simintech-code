"""Собрать модель с нуля, посчитать и забрать результат в текстовый файл.

Что показывает:

1. проект создаётся **из шаблона** (`Project.from_template`) — только такой
   считает: у проекта из `Project.new()` нет расчётного слоя, и модельное
   время в нём не растёт ничем;
2. конечное время расчёта задаётся `set_calc_end_time` (свойство слоя
   `endtime`), иначе берётся значение шаблона — 10 с;
3. результат пишет блок «В файл»: по строке на момент времени в формате
   `<время> <значение 1> … <значение n>`. Это работает без базы сигналов —
   в отличие от `get_signal`.

Запуск (Windows, `mmain.exe /regserver`):

    python examples/run_to_file.py
"""

import os
import sys
import tempfile
import time

from simintech_api import COMClient, Project
from simintech_api.constants import find_model_template

#: Стандартный каталог результатов. Тот же подкаталог использует MCP-сервер
#: (`DEFAULT_OUTPUT_SUBDIR` в simintech-mcp) — он читает `read_output_file`
#: только оттуда, поэтому файл примера удаётся прочитать и через MCP.
OUT_DIR = os.path.join(tempfile.gettempdir(), "simintech-output")
OUT = os.path.join(OUT_DIR, "simintech_run_to_file.txt")

#: Шаг записи в файл, с
SAMPLE_STEP = 0.2


def main() -> int:
    template = find_model_template()
    print("шаблон:", template)
    if not template:
        print("Шаблон модели не найден. Задайте SIMINTECH_TEMPLATE "
              "или SIMINTECH_PATH.")
        return 1

    os.makedirs(OUT_DIR, exist_ok=True)
    if os.path.exists(OUT):
        os.remove(OUT)

    client = COMClient().connect()
    project = Project.from_template(client)
    project.set_calc_end_time(1.0)
    page = project.get_main_page()

    const = page.create_block("Константа", 100.0, 100.0)
    const.set_property("a", 2.0)
    const.init()

    gain = page.create_block("Усилитель", 300.0, 100.0)
    gain.set_property("a", 3.0)
    gain.init()

    sink = page.create_block("В файл", 500.0, 100.0)
    sink.set_property("filename", OUT)
    sink.set_property("count", 1)
    sink.set_property("step", f"[{SAMPLE_STEP}]")
    sink.init()

    const.connect(gain)
    gain.connect(sink)
    print(f"схема: {const.get_name()} -> {gain.get_name()} -> {sink.get_name()}")

    sim = project.simulation()
    sim.start()
    sim.run_to(1.0)

    # RunTo не блокирующий: дожидаемся выхода времени на отметку.
    deadline = time.monotonic() + 10
    while sim.get_time() < 0.999 and time.monotonic() < deadline:
        time.sleep(0.05)
    print("модельное время:", sim.get_time())
    if sim.get_time() < 0.999:
        print("Расчёт не дошёл до 1.0 с. Частая причина — у блока не соединён "
              "вход: это молча останавливает расчёт всей модели.")
    sim.stop()
    project.close()
    client.disconnect()

    if not os.path.exists(OUT):
        print("Файл результата не создан:", OUT)
        return 1

    with open(OUT, encoding="utf-8", errors="replace") as handle:
        lines = handle.read().splitlines()
    print(f"\n{OUT}: строк {len(lines)}")
    for line in lines:
        print("  ", line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
