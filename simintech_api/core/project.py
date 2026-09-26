"""Управление проектом SimInTech."""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from ..exceptions import PageError, ProjectError, SignalError
from ..constants import CALC_LAYER, find_model_template
from ..model import RestartNames, SignalInfo, TDataDescriptor
from .com_client import _out_values

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

    # ─── Настройки расчёта (свойства слоя) ──────────────────────────

    def calc_settings(self) -> dict:
        """Параметры расчётного слоя проекта: имена и значения.

        Читаются **из выгрузки** `.xprt`, а не через COM: метода чтения свойств
        слоя в интерфейсе нет, есть только запись (`SetLayerProp`). Выгрузка
        даёт заодно ответ на вопрос «какие имена в этом проекте вообще есть» —
        без него проверять имя при записи было бы нечем, а `SetLayerProp`
        неизвестное имя, по аналогии с `SetBlockProp`, может принять молча.

        Секция слоя шире настроек расчёта: на живом проекте в ней, кроме
        `starttime`/`endtime`/`hmin`/`hmax`/`intmet`, лежат, например,
        `comp_names` и строки загрузки/компиляции — по этому словарь и
        называется «параметры слоя», а не «настройки расчёта».

        У проекта без расчётного слоя (созданного через `Project.new()`) секции
        параметров нет — возвращается пустой словарь, и это не ошибка.

        Требует COM: чтобы получить выгрузку, проект должен быть в среде.
        """
        from ..catalog import export_xprt_text, parse_xprt_layer_params

        return parse_xprt_layer_params(export_xprt_text(self))

    def set_calc_setting(self, name: str, value: str) -> "Project":
        """Записать параметр расчёта (`SetLayerProp`), проверив имя.

        Имя сверяется с теми, что уже есть в проекте (`calc_settings`):
        неизвестное отвергается. Это не перестраховка — у `SetBlockProp` запись
        в несуществующее имя молча ничего не делает, и `SetLayerProp`
        проверять на это отдельно не приходилось.

        Raises:
            ProjectError: имени нет в настройках проекта, либо `SetLayerProp`
                не принял значение (нет расчётного слоя).
        """
        known = self.calc_settings()
        if known and name not in known:
            raise ProjectError(
                f"параметра «{name}» нет в настройках расчёта проекта. "
                f"Известные: {', '.join(sorted(known))}"
            )
        handle = self._client.set_layer_prop(self._id, CALC_LAYER, name,
                                             str(value))
        if not handle:
            raise ProjectError(
                f"SetLayerProp не принял «{name}»: в проекте нет расчётного "
                f"слоя. Создайте проект через Project.from_template()."
            )
        return self

    # ─── Точки рестарта ─────────────────────────────────────────────
    #
    # Рестарт (checkpoint/restore) — это снимок состояния модели, который
    # можно записать в файл и загрузить обратно, чтобы продолжить расчёт не
    # с начала. Все методы группы адресуются идентификатором проекта, поэтому
    # живут здесь. **Ни один из них не проверен на живом SimInTech**: смысл
    # кодов возврата и флагов взят из имён параметров RIDL и не подтверждён
    # практикой. Проверять их стоит на копии модели — что именно делает
    # запись/чтение рестарта с уже посчитанным проектом, неизвестно.

    def write_restart(self, path: str) -> None:
        """Записать рестарт проекта в файл (COM `WriteProjectRestart`).

        На живом SimInTech не проверено: ни формат файла, ни то, требуется ли
        предварительный `write_restart_point`.
        """
        self._client.call("WriteProjectRestart", self._id, path)

    def read_restart(self, path: str) -> None:
        """Загрузить рестарт проекта из файла (COM `ReadProjectRestart`).

        На живом SimInTech не проверено: не подтверждено ни то, что состояние
        модели действительно меняется, ни как это отражается на времени
        расчёта.
        """
        self._client.call("ReadProjectRestart", self._id, path)

    def write_restart_point(self) -> int:
        """Записать точку рестарта (COM `WriteRestartPoint`).

        Возвращается результат COM-вызова как есть, приведённый к int: что
        означает код, по RIDL не видно. И код, и поведение на живом SimInTech
        не подтверждены.
        """
        return _as_int(self._client.call("WriteRestartPoint", self._id))

    def read_restart_point(self) -> float:
        """Вернуть точку рестарта (COM `ReadRestartPoint`).

        Результат приводится к float в предположении, что точка рестарта —
        момент модельного времени (рядом, в `GetProjectRestartNames`, есть
        поле `aNewRestartTime`). Это предположение: ни тип, ни значение на
        живом SimInTech не подтверждены. Если метод ничего не вернул (None),
        результатом будет 0.0 — отличить «нет точки» от «точка в нуле» по
        этому ответу нельзя.
        """
        return _as_float(self._client.call("ReadRestartPoint", self._id))

    def set_restart_preserve_flag(self, preserve: int) -> None:
        """Установить флаг сохранения рестарта (`SetRestartPreserveFlag`).

        Args:
            preserve: значение флага `fRestartPreserve` — целое, как в COM.
                Смысл значений (0/1 — выключено/включено или наоборот) на
                живом SimInTech не подтверждён.

        На живом SimInTech не проверено.
        """
        self._client.call("SetRestartPreserveFlag", self._id, int(preserve))

    def restart_names(self) -> RestartNames:
        """Имена файлов рестарта и связанные с ними флаги.

        Разбор `GetProjectRestartNames`: по RIDL метод отдаёт шесть
        [out]-значений (два имени файла, два флага, время и флаг времени);
        они раскладываются по полям `RestartNames`. Если метод вернул не
        шесть значений, это отказ (`ComCallError`), а не молчаливо сдвинутый
        разбор. На живом SimInTech не проверено — ни порядок значений, ни их
        смысл.
        """
        values = _out_values(
            self._client.call("GetProjectRestartNames", self._id),
            "GetProjectRestartNames", 6)
        return RestartNames(
            read_file=_as_str(values[0]),
            write_file=_as_str(values[1]),
            read_flag=_as_int(values[2]),
            write_flag=_as_int(values[3]),
            new_restart_time=_as_float(values[4]),
            set_new_time_flag=_as_int(values[5]),
        )

    def set_read_restart_file(self, path: str, load: int) -> None:
        """Задать файл, из которого читается рестарт.

        COM `SetProjectReadRestartFile`; это настройка проекта, а не сама
        загрузка (загрузка — `read_restart`).

        Args:
            path: имя файла рестарта.
            load: значение флага `fLoadRst` — целое, как в COM; что именно оно
                включает, на живом SimInTech не подтверждено.

        На живом SimInTech не проверено.
        """
        self._client.call("SetProjectReadRestartFile", self._id, path, int(load))

    def set_write_restart_file(self, path: str, save: int) -> None:
        """Задать файл, в который пишется рестарт.

        COM `SetProjectWriteRestartFile`; это настройка проекта, а не сама
        запись (запись — `write_restart`).

        Args:
            path: имя файла рестарта.
            save: значение флага `fSaveRst` — целое, как в COM; что именно оно
                включает, на живом SimInTech не подтверждено.

        На живом SimInTech не проверено.
        """
        self._client.call("SetProjectWriteRestartFile", self._id, path, int(save))

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

    # ─── Субмодели ──────────────────────────────────────────────────
    #
    # Субмодель — это модель внутри блока: у блока со субмоделью есть своя
    # страница (`submodel_page`), а сама субмодель берётся из файла
    # (`load_submodel`/`assign_submodel`). Методы живут на `Project`, потому
    # что команды адресуются проектом и блоком; идентификатор блока при этом
    # передаётся явно — угадывать его из проекта было бы нечем.
    # **На живом SimInTech группа не проверена**: не подтверждено ни то, что
    # `LoadSubmodel` и `AssignSubmodel` — разные операции, ни то, чем они
    # отличаются. Проверять на копии модели.

    def submodel_page(self, block_id: int) -> "Page":
        """Страница субмодели блока (COM `GetSubmodelPage`).

        Args:
            block_id: идентификатор блока (`Block.id`), а не страницы.

        Returns:
            Страница субмодели — её можно активировать (`Page.activate`) и
            создавать на ней блоки.

        Raises:
            PageError: COM вернул нулевую страницу. Это значит, что субмодели
                у блока нет либо блок не найден — различить эти случаи по
                ответу нечем.

        Проверено живьём **на успешном пути**: на демо вендора этот вызов вместе
        с `Page.activate()` делал текущей страницу блока `acrms_Circuit1`, и
        топологическая проба прочитала с неё 35 объектов (измерено 2026-09-22,
        `tests/integration/test_topology_live.py`). Ветка отказа (`PageError`) на
        живом SimInTech не измерялась.

        Оговорка для того, кто делает страницу текущей ради пробы: на неглавной
        странице `ScriptBridge` возвращает прежний скрипт с главной, поэтому
        скрипт внутренней страницы **теряется** — см. раздел `read_topology` в
        `docs/api.md`.
        """
        from .page import Page
        values = _out_values(
            self._client.call("GetSubmodelPage", int(block_id)),
            "GetSubmodelPage")
        page_id = _as_i64(values[0])
        if not page_id:
            raise PageError(
                f"GetSubmodelPage вернул нулевую страницу для блока "
                f"{block_id}: субмодели у блока нет либо блок не найден "
                f"(на живом SimInTech не подтверждено)."
            )
        return Page(self, page_id)

    def load_submodel(self, block_id: int, path: str) -> None:
        """Загрузить субмодель из файла в блок (COM `LoadSubmodel`).

        Args:
            block_id: идентификатор блока (`Block.id`).
            path: путь к файлу субмодели (.prt).

        На живом SimInTech не проверено: чем `load_submodel` отличается от
        `assign_submodel`, по RIDL не видно, а практикой это не проверялось.
        """
        self._client.call("LoadSubmodel", int(block_id), path)

    def assign_submodel(self, block_id: int, path: str) -> None:
        """Назначить блоку субмодель из файла (COM `AssignSubmodel`).

        Args:
            block_id: идентификатор блока (`Block.id`).
            path: путь к файлу субмодели (.prt).

        На живом SimInTech не проверено: чем `assign_submodel` отличается от
        `load_submodel`, по RIDL не видно, а практикой это не проверялось.
        """
        self._client.call("AssignSubmodel", self._id, int(block_id), path)

    # ─── Сигналы ────────────────────────────────────────────────────

    def find_signal(self, name: str) -> TDataDescriptor:
        """Найти сигнал по имени записи; вернуть TDataDescriptor (или SignalError).

        Работает через FindSignalData — сигнал ищется по имени записи
        независимо от GetProjectSignalList. Читается только у проекта с
        подключённой базой сигналов: без неё обмен пуст, и имя блока сигналом
        не является, поэтому `SignalError` — а не «сигнал доступен сразу после
        открытия».
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


def _as_int(value) -> int:
    """Целое из результата COM-вызова: код возврата или флаг.

    От `_as_i64` отличается отношением к `None`: COM ничего не вернул — это 0.
    У флага 0 осмыслен (выключено), и отличить «выключено» от «не пришло» по
    ответу нечем, а падать на `None` незачем.
    """
    if value is None:
        return 0
    if hasattr(value, "value"):
        return int(value.value)
    return int(value)


def _as_str(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _as_float(value) -> float:
    if value is None:
        return 0.0
    if hasattr(value, "value"):
        return float(value.value)
    return float(value)
