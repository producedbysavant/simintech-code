"""Управление проектом SimInTech."""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from ..exceptions import ProjectError, SignalError
from ..constants import CALC_LAYER, find_model_template
from ..model import SignalInfo, TDataDescriptor

if TYPE_CHECKING:
    from .com_client import COMClient
    from .page import Page
    from .simulation import Simulation


class Project:
    """Проект SimInTech (обёртка над ProjectId).

    Создаётся через Project.from_template(), Project.open() или Project.new() —
    не напрямую. Расчёт идёт только в проекте из шаблона (`from_template`).
    """

    def __init__(self, client: "COMClient", project_id: int):
        self._client = client
        self._id = project_id

    # ─── Фабричные методы ───────────────────────────────────────────

    @classmethod
    def new(cls, client: "COMClient") -> "Project":
        """Создать новый **пустой** проект.

        В проекте нет моделирующего слоя и настроек расчёта, поэтому расчёт в
        нём не идёт: модельное время не растёт, хотя вызовы сообщают об успехе.
        Предупреждение стоит здесь, а не только у `from_template()`: тот, кто
        вызывает `new()`, читает docstring `new()`, а не соседнего метода.

        Для проекта, в котором можно считать, используйте `from_template()`.
        """
        project_id = client.new_project()
        if project_id == 0:
            raise ProjectError("NewProject вернул нулевой ProjectId")
        return cls(client, project_id)

    @classmethod
    def open(cls, client: "COMClient", path: str) -> "Project":
        """Открыть проект (.prt/.xprt) по пути."""
        project_id = client.open_project(path)
        if project_id == 0:
            raise ProjectError(f"OpenProject не удалось открыть '{path}'")
        return cls(client, project_id)

    @classmethod
    def from_template(cls, client: "COMClient",
                      template: "str | None" = None) -> "Project":
        """Создать проект из шаблона пустой модели SimInTech.

        Это рабочий способ «создать проект с нуля»: `Project.new()` даёт пустой
        проект, в котором нет моделирующего слоя и настроек расчёта, поэтому
        расчёт в нём не идёт (модельное время не растёт, хотя вызовы сообщают
        об успехе). Шаблон из поставки — «Схема модели общего вида.prt» — даёт
        полноценный проект с расчётным слоем «Автоматика» и настройками.

        Args:
            template: путь к шаблону; по умолчанию — из `find_model_template()`
                (учитывает переменные окружения `SIMINTECH_TEMPLATE`,
                `SIMINTECH_PATH`).
        """
        path = template or find_model_template()
        if not path:
            raise ProjectError(
                "Не найден шаблон модели SimInTech. Укажите путь явно или "
                "задайте SIMINTECH_TEMPLATE / SIMINTECH_PATH."
            )
        project_id = client.open_template(path)
        if project_id == 0:
            raise ProjectError(f"OpenTemplate не открыл шаблон '{path}'")
        return cls(client, project_id)

    def set_calc_end_time(self, seconds: float) -> "Project":
        """Задать конечное время расчёта (`endtime` расчётного слоя).

        Без этого проект считается до значения из шаблона (10 с). Требует
        проекта с расчётным слоем — созданного из шаблона, а не через
        `Project.new()`.
        """
        if seconds <= 0:
            raise ValueError("Конечное время расчёта должно быть положительным")
        handle = self._client.set_layer_prop(
            self._id, CALC_LAYER, "endtime", float(seconds))
        if not handle:
            raise ProjectError(
                "SetLayerProp не принял endtime: в проекте нет расчётного слоя. "
                "Создайте проект через Project.from_template()."
            )
        return self

    # ─── Редактор ───────────────────────────────────────────────────

    def repaint(self) -> "Project":
        """Перерисовать редактор проекта (COM `RepaintEditor`).

        Нужна между перемещением блоков и трассировкой линий. `Block.set_center`
        переносит блок и его порты, но внутренние прямоугольники, по которым
        SimInTech прокладывает провода, обновляются только при перерисовке: без
        неё `Wire.normalize()` строит маршрут в обход блоков, стоящих на
        прежних местах, и оставляет в геометрии точки вроде ``(-160,-1056)`` —
        они потом не пересчитываются, и линия остаётся кривой. Проверено на
        SimInTech64 2026-09-15: с `RepaintEditor` линии ортогональны, без него —
        диагональны и уходят за пределы схемы. `BlockAfterEdit` для каждого
        блока этого не заменяет.
        """
        self._client.call("RepaintEditor", self._id)
        return self

    # ─── Форма проекта ──────────────────────────────────────────────

    def show_form(self) -> "Project":
        """Показать форму проекта (COM `FormShow`).

        Вызывать **перед сохранением**, если файл потом должен открываться в
        GUI SimInTech. Состояние окна — часть проекта: у сессии без видимой
        формы (обычной при работе через COM) в файл уходит
        ``<visible>0</visible>``. Такой проект загружается — COM его открывает
        и считает, — но GUI восстанавливает сохранённое состояние окна и
        оставляет окно модели скрытым: видна пустая рамка SimInTech, и это
        выглядит как «проект не открылся». `FormShow` выставляет флаг в 1, и
        сохранённый файл открывается обычным образом. Касается обоих форматов
        (`.prt` и `.xprt`) — проверено на SimInTech64.

        Побочный эффект: окно SimInTech действительно показывается на машине,
        где запущен COM-сервер. Для полностью безоконного сохранения вызов
        можно не делать — ценой того, что файл не покажется в GUI.
        """
        self._client.call("FormShow", self._id)
        return self

    # ─── Свойства ───────────────────────────────────────────────────

    @property
    def id(self) -> int:
        return self._id

    @property
    def client(self) -> "COMClient":
        return self._client

    # ─── Жизненный цикл ─────────────────────────────────────────────

    def close(self) -> None:
        """Закрыть проект."""
        self._client.call("CloseProject", self._id)

    def save_xml(self, path: str) -> None:
        """Сохранить проект в XML-формат (.xprt)."""
        self._client.call("SaveProjectXML", self._id, path)

    def save_binary(self, path: str) -> None:
        """Сохранить проект в бинарный формат (.prt)."""
        self._client.call("SaveProjectBinary", self._id, path)

    def export_db_to_xml(self, path: str) -> None:
        """Выгрузить базу сигналов проекта в XML.

        COM-путь выгрузки базы: не нужны ни командная строка, ни макрос
        `dbexporttoxml` — база отдаётся одним вызовом. Файл пишет сам
        SimInTech; читает его `simintech_api.sdb.SignalDatabase.from_xml`.

        Проверено на поставке: проект с базой отдаёт файл, который наш разбор
        читает целиком (5 категорий, 99 групп, 5805 сигналов).
        """
        self._client.call("ExportDBToXML", self._id, path)

    # ─── Страницы ───────────────────────────────────────────────────

    def get_main_page(self) -> "Page":
        """Получить главную страницу проекта."""
        from .page import Page
        page_id = self._client.call("GetMainPage", self._id)
        return Page(self, _as_i64(page_id))

    def get_current_page(self) -> "Page":
        """Получить текущую страницу проекта."""
        from .page import Page
        page_id = self._client.call("GetCurentPage", self._id)
        return Page(self, _as_i64(page_id))

    # ─── Сигналы ────────────────────────────────────────────────────

    def find_signal(self, name: str) -> TDataDescriptor:
        """Найти сигнал по имени блока; вернуть TDataDescriptor (или SignalError).

        Работает через FindSignalData — сигнал ищется по имени блока
        независимо от GetProjectSignalList. Как правило доступен сразу после
        открытия проекта; при необходимости инициализации вызывайте
        sim.start() перед поиском.
        """
        from ..utils.converters import descriptor_is_valid

        desc = self._client.find_signal(name, self._id)
        if not descriptor_is_valid(desc):
            raise SignalError(
                f"Сигнал '{name}' не найден в проекте. Обмен данными идёт "
                f"через список сигналов проекта и подключённую базу сигналов; "
                f"у проекта без базы их нет, и имя блока сигналом не является. "
                f"Проверьте GetProjectDB и список сигналов "
                f"(list_signals): записи с source='xml' — это имена блоков, "
                f"они не читаются."
            )
        return desc

    def signal(self, name: str) -> "Signal":  # noqa: F821 — Signal импортируется ниже
        """Вернуть объект Signal по имени сигнала."""
        from .signal import Signal
        return Signal(self, self.find_signal(name), name)

    def list_signals(self) -> List[SignalInfo]:
        """Получить список сигналов проекта.

        Два источника, различимых по `SignalInfo.source`:

        1. ``"com"`` — `GetProjectSignalList` → `GetListCount` →
           `GetDataInfoFromList`. Это настоящие сигналы, у них есть
           дескриптор, и `Signal.read()` по ним работает.
        2. ``"xml"`` — если COM-список пуст, имена извлекаются из .xprt.
           Это **имена блоков, а не сигналы**: `readable` у них ``False``,
           прочитать значение нельзя. Возвращаются как подсказка о том, что
           есть на схеме, а не как пригодные к чтению сигналы.

        У проекта, созданного `Project.new()`, список обычно пуст: обмен
        идёт через базу сигналов, а её к такому проекту не подключают
        (`GetProjectDB` → `(None, None)`). Проверено на SimInTech64.
        """
        from ..utils.converters import _to_descriptor
        result: List[SignalInfo] = []
        list_id = _as_i64(self._client.call("GetProjectSignalList", self._id))
        count = _as_i64(self._client.call("GetListCount", list_id))
        for i in range(count):
            # comtypes возвращает [out] (Name, Caption, DataDesc) в порядке объявления
            name, caption, desc = self._client.call("GetDataInfoFromList", list_id, i)
            result.append(SignalInfo(
                name=_as_str(name),
                caption=_as_str(caption),
                descriptor=_to_descriptor(desc),
            ))
        if result:
            return result
        # Запасной путь: имена блоков из XML. Это НЕ сигналы — помечаем
        # источником "xml", чтобы вызывающий код не принял их за читаемые.
        try:
            from ..utils.xprt_signals import extract_signal_names_from_project
            names = extract_signal_names_from_project(self)
            result = [
                SignalInfo(name=nm, caption="", descriptor=None, source="xml")
                for nm in names
            ]
        except Exception:
            pass
        return result

    def get_signal_names_from_xml(self) -> List[str]:
        """Извлечь имена сигналов из XML-представления проекта (.xprt).

        Экспортирует проект во временный файл и парсит имена блоков
        (кандидатов в сигналы). Полезно, когда GetProjectSignalList пуст
        (модель без блоков «Вход/Выход алгоритма»).
        """
        from ..utils.xprt_signals import extract_signal_names_from_project
        return extract_signal_names_from_project(self)

    # ─── Расчёт ─────────────────────────────────────────────────────

    def simulation(self) -> "Simulation":
        """Получить объект управления расчётом проекта."""
        from .simulation import Simulation
        return Simulation(self._client, self._id)

    def run(self) -> None:
        """Запустить расчёт (удобная обёртка)."""
        self.simulation().start().run()

    def stop(self) -> None:
        """Остановить расчёт."""
        self.simulation().stop()


def _as_i64(value) -> int:
    if hasattr(value, "value"):
        return int(value.value)
    return int(value)


def _as_str(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)
