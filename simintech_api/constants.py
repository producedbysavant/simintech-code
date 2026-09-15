"""Константы COM API SimInTech.

Значения DataType восстановлены из практики (см. SIT_SimInTech_Vneshnij_API.pdf,
mmain.hpp и docs/reference/com_api_inventory.md) — официально enum не
задокументирован.
"""

import os
from enum import IntEnum
from typing import List, Optional


class DataType(IntEnum):
    """Типы данных сигналов SimInTech (поле TDataDescriptor.DataType)."""
    DOUBLE = 0        # double
    INTEGER = 1       # integer (int64)
    BOOL = 2          # boolean (читается/пишется как int)
    STRING = 4        # string
    ARRAY = 5         # array (double[])
    INT_ARRAY = 12    # intarray (int64[])


# Имя метода чтения по DataType
READ_METHODS = {
    DataType.DOUBLE: "ReadAsFloat",
    DataType.INTEGER: "ReadAsInteger",
    DataType.BOOL: "ReadAsInteger",
    DataType.STRING: "ReadAsString",
}

# Имя метода записи по DataType
WRITE_METHODS = {
    DataType.DOUBLE: "WriteAsFloat",
    DataType.INTEGER: "WriteAsInteger",
    DataType.BOOL: "WriteAsInteger",
    DataType.STRING: "WriteAsString",
}


class PortSide(IntEnum):
    """Сторона порта (поле GetPortInfo Side)."""
    LEFT = 0
    RIGHT = 1
    TOP = 2
    BOTTOM = 3


class PortMode(IntEnum):
    """Режим порта."""
    INPUT = 0
    OUTPUT = 1
    # прочие режимы (универсальный, параметр и т.п.) не задокументированы
    UNKNOWN = -1


# Пространственные константы layout (в пикселях схемы SimInTech)
GRID_SIZE = 20          # шаг сетки трассировки
LAYER_GAP = 160         # расстояние между слоями (X)
BLOCK_GAP = 80          # расстояние между блоками в слое (Y)
DEFAULT_BLOCK_W = 60    # ширина блока по умолчанию
DEFAULT_BLOCK_H = 40    # высота блока по умолчанию
PORT_STUB = 20          # длина короткого участка линии от порта до канала

# WireType для CreateWire: 0 — автоматика, 1 — гидравлика
WIRE_TYPE_AUTOMATICS = 0
WIRE_TYPE_HYDRAULICS = 1

# Классы блоков, НЕ создаваемые через COM CreateBlock (из практики; обходить
# через встроенный язык SimInTech / макросы)
UNSUPPORTED_COM_BLOCK_CLASSES = {
    "Из памяти",
    "Порт выхода",                # регистрация порта состояния
    "Флаг входа в состояние",     # вызывает AV
    # CreateBlock возвращает 0, создавая вместо блока заглушку-«табличку»
    # (класс в списке, но объект не тот). Проверено на SimInTech64 (2026-09-10).
    "Выход данных состояния",
    "Состояние автомата",
}

# Классы блоков, проверенно создаваемые через COM CreateBlock
SUPPORTED_COM_BLOCK_CLASSES = {
    "Константа",
    "Усилитель",
    "Сумматор",
    "Интегратор",
    "Производная",
    "Ступенька",
    "Синусоида",
    "Временной график",
    "Сравнивающее устройство",
    "Порт входа",
    "Задержка на шаг интегрирования",
    "RS-триггер с приоритетом по установке",
    # Вывод результатов в текстовый файл: строки «<время> <значения...>»
    "В файл",
}

# ─── Шаблон проекта ────────────────────────────────────────────────

#: Имя шаблона «пустой модели» в поставке SimInTech (меню «Файл → Создать»).
MODEL_TEMPLATE_NAME = "Схема модели общего вида.prt"

#: Номер расчётного слоя («Автоматика», плагин `mbtylib.dll@layer`).
#: Свойства слоя (в т.ч. `endtime`) меняются только у проекта с этим слоем.
CALC_LAYER = 0

#: Путь по умолчанию на Windows.
DEFAULT_MODEL_TEMPLATE = "C:\\SimInTech64\\bin\\Template\\" + MODEL_TEMPLATE_NAME

#: Путь по умолчанию из WSL (там же лежит установка).
DEFAULT_MODEL_TEMPLATE_WSL = "/mnt/c/SimInTech64/bin/Template/" + MODEL_TEMPLATE_NAME


def find_model_template() -> Optional[str]:
    """Найти шаблон пустой модели SimInTech.

    Порядок поиска:

    1. ``SIMINTECH_TEMPLATE`` — полный путь к файлу шаблона. Если переменная
       задана, она **авторитетна**: при несуществующем файле возвращается
       ``None``, а не откат на путь по умолчанию (иначе опечатка в настройке
       молча подменялась бы другим шаблоном).
    2. ``SIMINTECH_PATH`` — корень установки, ожидается
       ``<корень>/bin/Template/<имя шаблона>``.
    3. Пути по умолчанию: Windows (``C:\\SimInTech64\\...``) и WSL
       (``/mnt/c/SimInTech64/...``). Оба перебираются независимо от платформы —
       так один и тот же код находит установку и из Windows, и из WSL.

    COM же работает **только на Windows** (см. `COMClient.connect`), поэтому
    найденный из-под WSL путь годится лишь для справки — расчёт по нему не
    пойдёт.

    Зачем шаблон: ``NewProject`` создаёт **пустой** проект — без моделирующего
    слоя и без настроек расчёта. Такой проект не считает: модельное время не
    растёт ни через `ProjectRun`, ни через `RunTo`, ни через `ProjectStep`,
    хотя все вызовы возвращают успех (проверено на SimInTech64, 2026-09-15).
    """
    explicit = os.environ.get("SIMINTECH_TEMPLATE")
    if explicit:
        return explicit if os.path.isfile(explicit) else None

    candidates: List[str] = []

    root = os.environ.get("SIMINTECH_PATH")
    if root:
        candidates.append(os.path.join(root, "bin", "Template", MODEL_TEMPLATE_NAME))

    candidates.append(DEFAULT_MODEL_TEMPLATE)
    candidates.append(DEFAULT_MODEL_TEMPLATE_WSL)

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


# ─── Каталог результатов ───────────────────────────────────────────

#: Подкаталог стандартного каталога результатов внутри временного каталога.
#: Соглашение общее для библиотеки и MCP-сервера (`simintech-mcp`): блок
#: «В файл» должен писать внутрь него, иначе `read_output_file` не прочитает
#: файл — сервер читает только этот каталог.
DEFAULT_OUTPUT_SUBDIR = "simintech-output"


def default_output_dir() -> str:
    """Стандартный каталог результатов: ``<временный каталог>/simintech-output``."""
    import tempfile
    return os.path.join(tempfile.gettempdir(), DEFAULT_OUTPUT_SUBDIR)
