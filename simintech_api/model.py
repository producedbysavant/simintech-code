"""Модель данных COM API SimInTech.

TDataDescriptor — структура VT_RECORD, через которую идут поиск, чтение и
запись сигналов. comtypes поддерживает её корректно, pywin32 — нет.
"""

from dataclasses import dataclass
from typing import Optional

from .constants import DataType

try:  # pragma: no cover — comtypes есть только на Windows
    from comtypes import Structure, c_int64, c_long
except ImportError:  # pragma: no cover
    Structure = object
    c_int64 = c_long = "int"  # заглушки для unit-тестов вне Windows


class TDataDescriptor(Structure):
    """COM-структура TDataDescriptor из mmain.ridl.

    Поля (по mmain.ridl / mmain.hpp):
        DataId   (__int64) — уникальный id элемента данных; 0 = не найден.
        DataType (long)    — тип данных (см. DataType).
    """

    _fields_ = [
        ("DataId", c_int64),
        ("DataType", c_long),
    ]

    def __init__(self, data_id: int = 0, data_type: int = 0):
        super().__init__()
        self.DataId = data_id
        self.DataType = data_type

    @property
    def is_valid(self) -> bool:
        """Дескриптор указывает на реальный элемент данных."""
        return self.DataId != 0

    def __repr__(self) -> str:  # pragma: no cover
        try:
            dt = DataType(self.DataType).name
        except ValueError:
            dt = f"<unknown:{self.DataType}>"
        return f"TDataDescriptor(DataId={self.DataId}, DataType={dt})"


@dataclass
class SignalInfo:
    """Информация о сигнале проекта (из GetDataInfoFromList).

    Args:
        name: имя сигнала.
        caption: подпись.
        descriptor: COM-дескриптор; без него прочитать значение нельзя.
        source: откуда запись получена — ``"com"`` (список сигналов проекта)
            или ``"xml"`` (имена блоков из .xprt, **не** сигналы).
    """

    name: str
    caption: str
    descriptor: Optional[TDataDescriptor] = None
    source: str = "com"

    @property
    def readable(self) -> bool:
        """Можно ли прочитать значение этого сигнала.

        ``False`` для имён, извлечённых из XML: это имена блоков, а не
        элементы данных, и `Project.signal()` по ним не сработает.
        """
        return self.descriptor is not None


@dataclass
class RestartNames:
    """Имена файлов рестарта проекта (из `GetProjectRestartNames`).

    COM-метод отдаёт шесть [out]-значений одним кортежем; здесь они разложены
    по именам, чтобы вызывающий не считал позиции. Значения отдаются **как
    есть**: что означает каждый флаг, по одному имени не видно, а на живом
    SimInTech метод ещё не проверялся — ни порядок значений, ни их смысл не
    подтверждены. Пути — строки, флаги — целые, время — с плавающей точкой.

    Args:
        read_file: файл, из которого читается рестарт (`aReadRestartFile`).
        write_file: файл, в который пишется рестарт (`aWriteRestartFile`).
        read_flag: флаг чтения рестарта (`aReadRestartFlag`).
        write_flag: флаг записи рестарта (`aWriteRestartFlag`).
        new_restart_time: время новой точки рестарта (`aNewRestartTime`).
        set_new_time_flag: флаг установки нового времени (`aSetNewTimeFlag`).
    """

    read_file: str
    write_file: str
    read_flag: int
    write_flag: int
    new_restart_time: float
    set_new_time_flag: int


@dataclass
class PortInfo:
    """Информация о порте блока (из GetPortInfo)."""

    port_id: int
    name: str
    side: int       # PortSide
    mode: int       # PortMode
    type_id: int
    item_id: int
    is_inverse: int
    is_center: int
    is_invisible: int
    x: float        # локальные координаты
    y: float
    x_global: float  # глобальные координаты на странице
    y_global: float
