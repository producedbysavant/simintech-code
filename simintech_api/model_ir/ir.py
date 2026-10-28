"""Структуры Model IR: полное представление модели без COM и XML-зависимостей.

Все записи неизменяемы. Словари свойств принадлежат записи и не должны
изменяться после сборки IR; потребитель читает их, а не правит.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .codes import (
    ContainerKind,
    ObjectKind,
    PortDirection,
    ProvenanceStatus,
    Severity,
    SourceKind,
    SourceStatus,
    WireEndKind,
    WireKind,
)

#: Версия схемы IR. Несовпадение - отказ, а не попытка прочитать по-своему.
IR_SCHEMA_VERSION = "1.0"


def _unknown_provenance() -> "Provenance":
    return Provenance(SourceKind.DERIVED, ProvenanceStatus.UNKNOWN)


@dataclass(frozen=True, slots=True)
class Provenance:
    """Откуда и насколько достоверно взято значение."""

    source: SourceKind
    status: ProvenanceStatus
    ref: str = ""
    observed_at: str = ""
    product_version: str = ""
    note: str = ""


@dataclass(frozen=True, slots=True)
class Property:
    """Свойство объекта или страницы в том виде, в каком оно лежит в выгрузке."""

    name: str
    value: str
    section: str
    kind: str = "unknown"
    mode: str = ""
    caption: str = ""
    text_value: str = ""
    script_hash: str = ""
    truncated: bool = False
    raw_len: int = 0
    sha256: str = ""
    provenance: Provenance = field(default_factory=_unknown_provenance)


@dataclass(frozen=True, slots=True)
class ScriptInfo:
    """Скрипт как хеш и признак наличия: полный текст остаётся в выгрузке."""

    slot: str
    section: str
    present: bool
    sha256: str = ""
    length: int = 0
    provenance: Provenance = field(default_factory=_unknown_provenance)


@dataclass(frozen=True, slots=True)
class ModelPort:
    """Порт объекта. Адрес порта - (объект, индекс), не имя."""

    id: str
    object_id: str
    index: int
    name: str
    direction: PortDirection = PortDirection.UNKNOWN
    side: int = -1
    x: float = -1.0
    y: float = -1.0
    x_glob: float = -1.0
    y_glob: float = -1.0
    type_id: str = ""
    item_id: str = ""
    synthetic: bool = False
    fields: dict[str, str] = field(default_factory=dict)
    provenance: Provenance = field(default_factory=_unknown_provenance)


@dataclass(frozen=True, slots=True)
class ModelObject:
    """Объект страницы: блок, субмодель, порт-блок, ячейка памяти или unknown."""

    id: str
    address: str
    container_id: str
    name: str
    class_name: str
    obj_type: str
    order: int
    kind: ObjectKind
    points: tuple[tuple[float, float], ...] = ()
    props: dict[str, Property] = field(default_factory=dict)
    visual_props: dict[str, Property] = field(default_factory=dict)
    scripts: dict[str, ScriptInfo] = field(default_factory=dict)
    ports: tuple[ModelPort, ...] = ()
    uid: str = ""
    indexstr: str = ""
    width: float | None = None
    height: float | None = None
    angle: float | None = None
    filename: str = ""
    extra: dict[str, str] = field(default_factory=dict)
    provenance: Provenance = field(default_factory=_unknown_provenance)

    @property
    def is_model_object(self) -> bool:
        """Участвует ли объект в графе сигналов."""
        return self.kind not in (ObjectKind.ANNOTATION, ObjectKind.DECORATION)

    def port(self, index: int) -> ModelPort | None:
        for item in self.ports:
            if item.index == index:
                return item
        return None

    def property(self, name: str) -> str:
        item = self.props.get(name)
        return item.value if item is not None else ""

    def visual_property(self, name: str) -> str:
        item = self.visual_props.get(name)
        return item.value if item is not None else ""


@dataclass(frozen=True, slots=True)
class WireEnd:
    """Конец провода: порт, ветвь, обрыв или неразрешённый адрес."""

    kind: WireEndKind
    object_id: str = ""
    object_name: str = ""
    port_index: int = -1
    container_id: str = ""
    resolved: bool = False
    reason: str = ""
    provenance: Provenance = field(default_factory=_unknown_provenance)


@dataclass(frozen=True, slots=True)
class ModelWire:
    """Провод или ветвь. Форма маршрута хранится отдельно от связности."""

    id: str
    address: str
    container_id: str
    order: int
    name: str
    kind: WireKind
    start: WireEnd
    end: WireEnd
    points: tuple[tuple[float, float], ...] = ()
    node_points: tuple[tuple[float, float], ...] = ()
    start_xy: tuple[float, float] = (-1.0, -1.0)
    end_xy: tuple[float, float] = (-1.0, -1.0)
    branch_parent_id: str = ""
    branch_node: int = -1
    parent_status: ProvenanceStatus = ProvenanceStatus.UNKNOWN
    props: dict[str, Property] = field(default_factory=dict)
    provenance: Provenance = field(default_factory=_unknown_provenance)


@dataclass(frozen=True, slots=True)
class Container:
    """Страница проекта или субмодели."""

    id: str
    address: str
    kind: ContainerKind
    name: str
    order: int = 0
    parent_object_id: str = ""
    props: dict[str, Property] = field(default_factory=dict)
    script_hash: str = ""
    script_present: bool = False
    object_ids: tuple[str, ...] = ()
    wire_ids: tuple[str, ...] = ()
    child_container_ids: tuple[str, ...] = ()
    provenance: Provenance = field(default_factory=_unknown_provenance)


@dataclass(frozen=True, slots=True)
class BoundaryPort:
    """Связь внешнего порта субмодели с внутренним порт-блоком."""

    id: str
    submodel_object_id: str
    external_port_index: int
    external_port_name: str
    internal_object_id: str = ""
    internal_port_index: int = -1
    port_names: str = ""
    resolved: bool = False
    reason: str = ""
    provenance: Provenance = field(default_factory=_unknown_provenance)


@dataclass(frozen=True, slots=True)
class MemoryLink:
    """Ячейка памяти: переменная PortNames и её писатели/читатели."""

    id: str
    variable: str
    writers: tuple[str, ...] = ()
    readers: tuple[str, ...] = ()
    resolved: bool = False
    reason: str = ""
    provenance: Provenance = field(default_factory=_unknown_provenance)


@dataclass(frozen=True, slots=True)
class Decoration:
    """Оформление страницы: подпись, линия, заливка, иконка блока."""

    id: str
    container_id: str
    address: str
    name: str
    class_name: str
    obj_type: str
    order: int
    points: tuple[tuple[float, float], ...] = ()
    text: str = ""
    provenance: Provenance = field(default_factory=_unknown_provenance)


@dataclass(frozen=True, slots=True)
class Discrepancy:
    """Расхождение или потеря, которую нельзя скрыть."""

    code: str
    severity: Severity
    subject: str
    detail: str = ""
    sources: tuple[str, ...] = ()
    alternatives: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Coverage:
    """Что разобрано, что пропущено и что осталось неизвестным."""

    containers: int = 0
    objects: int = 0
    ports_real: int = 0
    ports_synthetic: int = 0
    wires: int = 0
    branches: int = 0
    decorations: int = 0
    block_image_pages: int = 0
    block_image_objects: int = 0
    unresolved_ends: int = 0
    unresolved_branches: int = 0
    unknown_object_types: int = 0
    source_status: SourceStatus = SourceStatus.OK
    port_order_status: ProvenanceStatus = ProvenanceStatus.HYPOTHESIS
    skipped: dict[str, int] = field(default_factory=dict)
    discrepancy_counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ModelMeta:
    """Паспортные данные сборки IR."""

    ir_schema: str
    primary_source: SourceKind
    source_set: tuple[SourceKind, ...]
    source_hashes: dict[str, str]
    structure_hash: str
    content_hash: str
    created_at: str = ""
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ModelIR:
    """Полное представление модели."""

    meta: ModelMeta
    containers: tuple[Container, ...]
    objects: tuple[ModelObject, ...]
    wires: tuple[ModelWire, ...] = ()
    boundaries: tuple[BoundaryPort, ...] = ()
    memory_links: tuple[MemoryLink, ...] = ()
    decorations: tuple[Decoration, ...] = ()
    block_image_objects: tuple[Decoration, ...] = ()
    discrepancies: tuple[Discrepancy, ...] = ()
    coverage: Coverage = field(default_factory=Coverage)

    def container(self, container_id: str) -> Container | None:
        for item in self.containers:
            if item.id == container_id:
                return item
        return None

    def object(self, object_id: str) -> ModelObject | None:
        for item in self.objects:
            if item.id == object_id:
                return item
        return None

    def wire(self, wire_id: str) -> ModelWire | None:
        for item in self.wires:
            if item.id == wire_id:
                return item
        return None

    def object_by_address(self, address: str) -> ModelObject | None:
        for item in self.objects:
            if item.address == address:
                return item
        return None

    def objects_in(self, container_id: str) -> tuple[ModelObject, ...]:
        return tuple(item for item in self.objects
                     if item.container_id == container_id)

    def wires_in(self, container_id: str) -> tuple[ModelWire, ...]:
        return tuple(item for item in self.wires
                     if item.container_id == container_id)
