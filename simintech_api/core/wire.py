"""Линия связи между портами SimInTech."""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, List, Optional, Tuple

from ..exceptions import WireError

if TYPE_CHECKING:
    from .project import Project
    from .port import Port

#: Опорные точки маршрутом линии **не управляют** — его выбирает SimInTech.
#: Проверено на SimInTech64 (2026-09-15, `docs/reference/com_api_inventory.md`
#: §6): свежесозданная линия идёт по прямой, `NormalizeWire` (после
#: `RepaintEditor`) ломает её на ортогональные участки сама и препятствия не
#: учитывает; `SetWirePoint` на линии без размеченных точек игнорируется, а на
#: размеченной вставляет точку в ломаную — линия идёт назад (зигзаг). Способа
#: задать свои изломы в API нет. Поэтому передача точек не обставляется
#: молчанием: вызывающий счёл бы, что задал геометрию (см. `docs/api.md`,
#: `docs/algorithms.md`).
POINTS_DO_NOT_ROUTE = (
    "Опорные точки не управляют геометрией линии: маршрут задаёт SimInTech "
    "(NormalizeWire после RepaintEditor). SetWirePoint на линии без "
    "размеченных точек игнорируется, а на размеченной даёт зигзаг — способа "
    "задать свои изломы в API нет. Геометрию задавайте расстановкой блоков "
    "(LayeredPlacer): источник с единственным приёмником — вплотную к нему."
)


class Wire:
    """Линия связи. Создаётся через Page.create_wire().

    Args:
        project: проект.
        wire_id: COM-идентификатор линии (__int64).
        start_port / end_port: (опционально) порты для удобства.
    """

    def __init__(self, project: "Project", wire_id: int,
                 start_port: Optional["Port"] = None,
                 end_port: Optional["Port"] = None):
        self._project = project
        self._id = wire_id
        self._start_port = start_port
        self._end_port = end_port

    @property
    def id(self) -> int:
        """COM-идентификатор линии."""
        return self._id

    @property
    def project(self) -> "Project":
        """Проект линии."""
        return self._project

    @property
    def client(self):
        """COM-клиент проекта."""
        return self._project.client

    @property
    def start_port(self) -> Optional["Port"]:
        """Порт-источник (если задан)."""
        return self._start_port

    @property
    def end_port(self) -> Optional["Port"]:
        """Порт-приёмник (если задан)."""
        return self._end_port

    # ─── Опорные точки ──────────────────────────────────────────────

    def set_point(self, index: int, x: float, y: float) -> "Wire":
        """Установить опорную точку линии (SetWirePoint).

        Маршрутом не управляет: нормализация такие точки либо игнорирует,
        либо превращает линию в зигзаг — см. `POINTS_DO_NOT_ROUTE`.
        """
        self.client.call("SetWirePoint", self._id, index, x, y)
        return self

    def set_points(self, points: List[Tuple[float, float]]) -> "Wire":
        """Установить все опорные точки линии.

        Маршрут задаёт SimInTech, а не эти точки (см. `POINTS_DO_NOT_ROUTE`),
        поэтому о вызове выдаётся предупреждение: без него вызывающий счёл бы,
        что задал геометрию линии.
        """
        warnings.warn(POINTS_DO_NOT_ROUTE, UserWarning, stacklevel=2)
        for idx, (x, y) in enumerate(points):
            self.set_point(idx, x, y)
        return self

    # ─── Выравнивание ───────────────────────────────────────────────

    def normalize(self) -> "Wire":
        """Автоматически выровнять линию (NormalizeWire)."""
        try:
            self.client.call("NormalizeWire", self._id)
        except Exception:
            # NormalizeWire может молча не сработать — не критично
            pass
        return self

    # ─── Ветвление ──────────────────────────────────────────────────

    def branch_to(self, port: "Port", point_index: int = 0) -> "Wire":
        """Создать ветвление от этой линии к порту.

        Args:
            port: порт-приёмник.
            point_index: номер точки ветвления на родительской линии (с 0).

        Raises:
            WireError: ``CreateWire`` вернул 0 — ветвление не создано.
                Нулевой возврат — отказ, а не идентификатор (`Wire(0)`).
                Проверка договорная: на SimInTech64 (2026-09-17) ноль от
                ``CreateWire`` получить не удалось ни на одном входе —
                настоящий отказ приходит ``ComCallError`` (см.
                `Page.create_wire`). У метода нет вызовов в коде, так что
                поведение этой ветки на живом COM не проверялось.
        """
        wire_id = _as_i64(self.client.call(
            "CreateWire",
            self._project.id, 0, 0, self._id, point_index,
            0, port.id, 0,   # StartPort=0: ветвление от линии, а не от порта
        ))
        if not wire_id:
            raise WireError(
                f"CreateWire не создал ветвление от линии {self._id} "
                f"к порту {port.id}: проверьте, что точка {point_index} "
                f"лежит на линии, и что порт принадлежит её странице"
            )
        return Wire(self._project, wire_id)

    def __repr__(self) -> str:  # pragma: no cover
        return f"Wire({self._id})"


def _as_i64(value) -> int:
    if hasattr(value, "value"):
        return int(value.value)
    return int(value)
