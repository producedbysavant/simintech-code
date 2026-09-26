"""Страница схемы SimInTech."""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, List, Optional, Tuple

from ..constants import (
    WIRE_TYPE_AUTOMATICS,
    standard_block_size,
)
from ..exceptions import BlockError, UnsupportedBlockError, WireError
from .com_client import _out_values

if TYPE_CHECKING:
    from .project import Project
    from .block import Block
    from .port import Port
    from .wire import Wire

#: Имя класса линии связи в этой сборке (свойство `ClassName`). Разные вызовы
#: возвращают его и целиком («Математическая связь»), и обрезанным
#: («Математическая») — проверено на живом SimInTech64, поэтому сверяется
#: начало строки, а не равенство.
WIRE_CLASS_PREFIX = "Математическая"

#: Имя объекта-линии (свойство `Name`) — запасной признак.
WIRE_NAME_PREFIX = "MBTYWire"


def _is_wire_object(class_name: str, name: str) -> bool:
    """Отличить линию связи от блока по имени класса или объекта."""
    cls = (class_name or "").strip()
    obj = (name or "").strip()
    return (cls.startswith(WIRE_CLASS_PREFIX)
            or obj.startswith(WIRE_NAME_PREFIX))


class Page:
    """Страница проекта. Создаётся через Project.get_main_page() и т.п."""

    def __init__(self, project: "Project", page_id: int):
        self._project = project
        self._id = page_id

    @property
    def id(self) -> int:
        """COM-идентификатор страницы."""
        return self._id

    @property
    def project(self) -> "Project":
        """Проект, которому принадлежит страница."""
        return self._project

    # ─── Активация страницы ─────────────────────────────────────────

    def activate(self) -> None:
        """Сделать страницу текущей (SetCurrentPage)."""
        self._project.client.call("SetCurrentPage", self._project.id, self._id)

    def parent(self) -> Optional["Page"]:
        """Родительская страница (COM `PageUp`); `None`, если её нет.

        Нужна, чтобы вернуться из страницы субмодели (`Project.submodel_page`)
        на страницу, которой она принадлежит. Нулевая страница трактуется как
        отсутствие родителя — так выглядит главная страница; **предположение**,
        на живом SimInTech не проверено, как и то, что `PageUp` возвращает
        именно родителя в этом смысле.

        Raises:
            ComCallError: метод не вернул [out]-значение (пустой результат или
                `None`) — это признак другой сигнатуры, а не отсутствия
                родителя.
        """
        values = _out_values(
            self._project.client.call("PageUp", self._id), "PageUp")
        page_id = _as_i64(values[0])
        if not page_id:
            return None
        return Page(self._project, page_id)

    # ─── Блоки ──────────────────────────────────────────────────────

    def create_block(
        self,
        class_name: str,
        x: float,
        y: float,
        *,
        width: Optional[float] = None,
        height: Optional[float] = None,
        layer_no: int = 0,
        parent_block: int = 0,
    ) -> "Block":
        """Создать блок на странице.

        Args:
            class_name: имя класса блока (русское, регистрозависимо),
                напр. "Константа", "Усилитель".
            x, y: координаты ЛЕВОГО ВЕРХНЕГО угла блока (не центра!):
                `SetBlockPosition` принимает левый верхний угол.
            width, height: размеры; по умолчанию — штатный размер класса
                (`standard_block_size`), а для неизмеренных классов — тот,
                что блок уже имеет.
            layer_no: номер слоя (0 — основной).
            parent_block: id родительского блока (для встраиваемых), 0 — нет.
        """
        from ..constants import UNSUPPORTED_COM_BLOCK_CLASSES
        if class_name in UNSUPPORTED_COM_BLOCK_CLASSES:
            raise UnsupportedBlockError(
                f"Класс '{class_name}' отвергает библиотека, а не COM: запись "
                f"блока через `CreateBlock` создаётся (измерено 2026-09-18), но "
                f"годность такого блока в расчёте не проверена "
                f"(см. константы.UNSUPPORTED_COM_BLOCK_CLASSES). Нужен этот "
                f"блок — используйте встроенный язык SimInTech или макрос."
            )
        self.activate()
        block_id = _as_i64(self._project.client.call(
            "CreateBlock",
            self._project.id, layer_no, parent_block, class_name,
        ))
        if block_id == 0:
            raise BlockError(f"CreateBlock не создал блок класса '{class_name}'")
        from .block import Block
        block = Block(self._project, block_id, class_name=class_name)
        # Штатный размер класса вместо того, что даёт CreateBlock: он создаёт
        # блок 60x40, а в моделях SimInTech для этих классов приняты 32x16 и
        # 32x32 (см. constants.STANDARD_BLOCK_SIZES). Для неизмеренных классов
        # размер не трогаем — set_position прочитает его у блока.
        if width is None or height is None:
            standard = standard_block_size(class_name)
            if standard is not None:
                width = standard[0] if width is None else width
                height = standard[1] if height is None else height
        block.set_position(x, y, width=width, height=height)
        return block

    def get_blocks(self) -> List["Block"]:
        """Получить блоки текущей страницы (`GetPageBlockId` по индексу).

        Перечисление отдаёт **все** объекты страницы, включая линии связи:
        на живой сборке счётчик вырастает на единицу после `CreateWire`, а
        `GetPageBlockId` возвращает идентификатор линии. Поэтому линии тут
        отсеиваются — иначе они попадали бы в список блоков (и в
        `list_blocks`), как раньше в список сигналов попадали провода.

        Линии отдельно — :meth:`get_wires`.
        """
        from .block import Block
        return [Block(self._project, block_id)
                for block_id, is_wire in self._objects() if not is_wire]

    def get_wires(self) -> List["Wire"]:
        """Линии связи текущей страницы.

        Перечисление то же, что у блоков, — `GetPageObjectCount` +
        `GetPageBlockId` (идентификатор **проекта**, а не страницы: с
        идентификатором страницы счётчик возвращает 0 — проверено на живом
        SimInTech64).

        **Концы линии этим путём не читаются.** Отдельных методов для портов
        связи в интерфейсе нет (`GetPortWireId` и подобные — функции встроенного
        языка, не COM), свойство `Points` у линии пусто даже после
        `NormalizeWire`, а у портов нет читаемых свойств. Поэтому линия
        возвращается без пары «откуда → куда»; сопоставить её с конкретными
        блоками можно только по тем, что создала эта сессия.
        """
        from .wire import Wire
        return [Wire(self._project, wire_id)
                for wire_id, is_wire in self._objects() if is_wire]

    def _objects(self) -> List[Tuple[int, bool]]:
        """Объекты страницы: (идентификатор, признак «это линия связи»)."""
        self.activate()
        count = _as_i64(self._project.client.call(
            "GetPageObjectCount", self._project.id))
        result: List[Tuple[int, bool]] = []
        for i in range(count):
            obj_id = _as_i64(self._project.client.call(
                "GetPageBlockId", self._project.id, i))
            if not obj_id:
                continue
            result.append((obj_id, self._is_wire(obj_id)))
        return result

    def _is_wire(self, obj_id: int) -> bool:
        """Линия ли это: по классу, при отказе чтения — по имени объекта."""
        from ..exceptions import ComCallError
        try:
            class_name = self._project.client.call(
                "GetBlockPropAsString", obj_id, "ClassName") or ""
        except ComCallError:
            class_name = ""
        if _is_wire_object(str(class_name), ""):
            return True
        try:
            name = self._project.client.call(
                "GetBlockPropAsString", obj_id, "Name") or ""
        except ComCallError:
            return False
        return _is_wire_object("", str(name))

    def find_block(self, name: str) -> Optional["Block"]:
        """Найти блок по свойству Name."""
        from ..exceptions import ComCallError
        for block in self.get_blocks():
            try:
                if block.get_property("Name") == name:
                    return block
            except ComCallError:
                continue
        return None

    # ─── Линии связи ────────────────────────────────────────────────

    def create_wire(
        self,
        start_port: "Port",
        end_port: "Port",
        points: Optional[List[Tuple[float, float]]] = None,
        *,
        wire_type: int = WIRE_TYPE_AUTOMATICS,
        layer_no: int = 0,
    ) -> "Wire":
        """Создать линию связи между двумя портами.

        **Маршрут линии задаёт SimInTech, а не вызывающий.** Нормализация
        (`NormalizeWire` после перерисовки редактора) ломает линию на
        ортогональные участки сама и препятствия не учитывает, а `points`
        геометрией не управляют: их уход в COM (`PointCount` +
        `SetWirePoint`) — единственное, что с ними происходит. Чистая схема
        получается расстановкой блоков (`LayeredPlacer`): источник с
        единственным приёмником — вплотную к нему, тогда середина маршрута
        попадает в свободный коридор.

        Args:
            start_port: порт-источник (выход).
            end_port: порт-приёмник (вход).
            points: опорные точки линии (промежуточные), опционально.
                Передаются в `CreateWire`/`SetWirePoint` ровно как прежде, но
                маршрутом не управляют, поэтому при их передаче выдаётся
                `UserWarning` — см. `wire.POINTS_DO_NOT_ROUTE`.
            wire_type: 0 — автоматика, 1 — гидравлика.
            layer_no: номер слоя.

        Raises:
            WireError: ``CreateWire`` вернул 0 — линия не создана. Нулевой
                возврат — это отказ, а не идентификатор: `Wire(0)` дальше не
                замечает никто (`NormalizeWire(0)` возвращает 0 и не
                отказывает), и агент счёл бы вход подключённым.

        Проверка на ноль — **договорная, а не измеренная**: на SimInTech64
        (2026-09-17) ``CreateWire`` не вернул 0 ни на одном входе. Ветка
        оставлена страховкой от «нулевого идентификатора», но настоящий отказ
        приходит иначе — исключением ``ComCallError``.

        Измеренное поведение при неверных входах (SimInTech64, 2026-09-17):

        * вырожденные, но ненулевые входы — тот же порт дважды, вход вместо
          выхода, несуществующий слой (7, −1), нулевой id **приёмника** —
          возвращают **ненулевой** id, и объект линии действительно
          появляется (`Page.get_wires()` растёт на единицу). Ноль здесь не
          приходит, и отличить такую линию от настоящей по возврату нельзя;
        * структурно неверные id портов (0, −1, 12345) и ``wire_type=99``
          дают **исключение**: COM отдаёт access violation
          (`[-0x7fff0001] ... Access violation ... in module 'mmain.exe'`),
          обёрнутое в ``ComCallError``. ``mmain.exe`` при этом выживает, и
          следующий вызов проходит.

        Практическое следствие: на пути `create_wire` с портами, добытыми
        `get_out_port`/`get_in_port`, отказа в виде нуля не бывает — оба
        метода сами бросают `PortError` на нулевом id, а валидная пара всегда
        даёт непустой id. Отказ среды здесь — исключение, и оно поднимается
        выше само.
        """
        from .wire import POINTS_DO_NOT_ROUTE, Wire
        if points:
            # Молчаливая передача точек выдавала бы управление маршрутом,
            # которого нет: вызывающий (и примеры) счёл бы геометрию заданной.
            warnings.warn(POINTS_DO_NOT_ROUTE, UserWarning, stacklevel=2)
        point_count = len(points) if points else 0
        wire_id = _as_i64(self._project.client.call(
            "CreateWire",
            self._project.id, layer_no, wire_type, 0, -1,
            start_port.id, end_port.id, point_count,
        ))
        if not wire_id:
            raise WireError(
                f"CreateWire не создал линию между портами "
                f"{start_port.id} → {end_port.id}: проверьте, что оба порта "
                f"принадлежат одной странице, и корректность слоя "
                f"(layer_no={layer_no})"
            )
        wire = Wire(self._project, wire_id)
        if points:
            for idx, (x, y) in enumerate(points):
                wire.set_point(idx, x, y)
        return wire


def _as_i64(value) -> int:
    if hasattr(value, "value"):
        return int(value.value)
    return int(value)
