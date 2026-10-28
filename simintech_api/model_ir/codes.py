"""Стабильные коды Model IR: источники, статусы, виды сущностей, расхождения.

Строки этих перечислений попадают в паспорт, ответы запросов и отчёты
проверок. Менять их значения без смены версии схемы нельзя: потребитель
сравнивает коды, а не человеческий текст.
"""

from enum import Enum


class SourceKind(str, Enum):
    """Откуда пришли данные."""

    XPRT = "xprt"
    MODEL_TEXT = "model_text"
    TOPOLOGY = "topology"
    REGISTRY = "registry"
    DERIVED = "derived"


class ProvenanceStatus(str, Enum):
    """Насколько факт подтверждён."""

    MEASURED = "measured"
    DERIVED = "derived"
    HYPOTHESIS = "hypothesis"
    UNKNOWN = "unknown"
    CONTRADICTED = "contradicted"


class SourceStatus(str, Enum):
    """Состояние источника при сборке IR."""

    OK = "ok"
    ABSENT = "absent"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class ContainerKind(str, Enum):
    """Вид контейнера модели."""

    PROJECT = "project"
    SUBMODEL = "submodel"


class ObjectKind(str, Enum):
    """Вид объекта страницы."""

    BLOCK = "block"
    SUBMODEL = "submodel"
    PORT_BLOCK = "port_block"
    MEMORY_CELL = "memory_cell"
    ANNOTATION = "annotation"
    DECORATION = "decoration"
    UNKNOWN = "unknown"


class PortDirection(str, Enum):
    """Режим порта: 0 вход, 1 выход, 2 ненаправленный."""

    IN = "in"
    OUT = "out"
    UNDIRECTED = "undirected"
    UNKNOWN = "unknown"


class WireEndKind(str, Enum):
    """Чем кончается провод."""

    PORT = "port"
    BRANCH = "branch"
    UNCONNECTED = "unconnected"
    UNRESOLVED = "unresolved"


class WireKind(str, Enum):
    """Вид провода в IR."""

    WIRE = "wire"
    BRANCH = "branch"
    TOPOLOGY_EDGE = "topology_edge"


class Severity(str, Enum):
    """Важность расхождения."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


#: Коды расхождений. Значение - стабильная строка для JSON и тестов.
DISCREPANCY_CODES = frozenset({
    "boundary_unresolved",
    "branch_parent_unresolved",
    "duplicate_object_name",
    "duplicate_wire_name",
    "end_index_name_conflict",
    "legacy_containerblock",
    "memory_name_missing",
    "memory_port_missing",
    "memory_unpaired",
    "points_unparsed",
    "port_order_hypothesis",
    "unknown_object_type",
    "wire_direction_mismatch",
    "wire_end_unresolved",
    "wire_points_unparsed",
    "wire_port_out_of_range",
})
