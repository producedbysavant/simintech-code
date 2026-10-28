"""Потоковый разбор `.xprt` в Model IR.

Источник - SaveProjectXML. Разбор не запускает расчёт и не трогает COM.
Страницы обрабатываются по мере закрытия, дочерние страницы отделяются от
иконок `blockimage`: иконка - оформление, а не модельный контейнер.
"""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, BinaryIO, Iterator, TextIO

from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

from ..catalog import clean_value, decode_xprt_value
from . import ids
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
from .errors import ModelIRLimitError, XprtParseError
from .ir import (
    IR_SCHEMA_VERSION,
    BoundaryPort,
    Container,
    Coverage,
    Decoration,
    Discrepancy,
    MemoryLink,
    ModelIR,
    ModelMeta,
    ModelObject,
    ModelPort,
    ModelWire,
    Property,
    Provenance,
    ScriptInfo,
    WireEnd,
)

#: Пределы разбора: байты, объекты, провода, глубина страниц.
DEFAULT_MAX_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_OBJECTS = 100_000
DEFAULT_MAX_WIRES = 200_000
DEFAULT_MAX_DEPTH = 64

#: Свойства-скрипты: в IR хранится хеш, а не полный текст.
SCRIPT_SLOTS = frozenset({
    "Script", "OnInitScript", "OnRunScript", "OnDestroyScript",
})

#: Оформление, которое не является модельным объектом.
DECORATION_TYPES = frozenset({"0", "1", "2", "5", "6", "20", "24", "27", "29", "39"})
ANNOTATION_TYPES = frozenset({"20", "108"})
DECORATION_CLASSES = frozenset({
    "Arc", "FillRect", "Line", "Point", "PolyLine", "Rectangle",
    "RotatedText", "TextLabel", "constLabel",
})
ANNOTATION_CLASSES = frozenset({
    "TextLabel", "constLabel", "RotatedText", "Комментарий",
})
MEMORY_CELLS = frozenset({"В память", "Из памяти"})
PORT_BLOCKS = frozenset({"Порт входа", "Порт выхода"})

#: Вендорские типы объектов 100..114; 101 - провод, остальные модельные.
BLOCK_TYPES = frozenset(str(value) for value in range(100, 115)) - {"101"}

#: Оформление, которое сохраняется рядом с моделью, но не в графе.
KEEP_VISUAL_PROPS = frozenset({
    "PortNames", "Text", "LabelText", "UID", "Width", "Height",
})

#: Свойства страницы, которые описывают вид, а не модель.
_PAGE_VIEW_PROPS = frozenset({
    "x", "y", "width", "height", "x_center", "y_center", "x_scale",
    "y_scale", "scalex", "scaley", "visible", "backcolor", "transparent",
    "snap", "snapstep", "grid", "imagemode", "angle", "printarea",
    "prngridon", "lmargin", "rmargin", "tmargin", "bmargin", "curentlayer",
    "layered", "opacity", "enabledls", "visiblels", "curentls", "uselsonrun",
})

_MAX_PROPERTY_CHARS = 4096
_POINT_RE = re.compile(r"\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)")
_NUMBERED_RE = re.compile(r"^(?P<base>[a-z_]+?)(?:_\d+)?$", re.I)


@dataclass(frozen=True, slots=True)
class Limits:
    """Пределы, при превышении которых разбор отказывает."""

    max_bytes: int = DEFAULT_MAX_BYTES
    max_objects: int = DEFAULT_MAX_OBJECTS
    max_wires: int = DEFAULT_MAX_WIRES
    max_depth: int = DEFAULT_MAX_DEPTH


@dataclass(slots=True)
class _RawPort:
    index: int
    fields: dict[str, str]
    name: str
    mode: str


@dataclass(slots=True)
class _RawDecor:
    order: int
    name: str
    class_name: str
    obj_type: str
    points: tuple[tuple[float, float], ...]
    text: str


@dataclass(slots=True)
class _RawObject:
    order: int
    fields: dict[str, str]
    points: tuple[tuple[float, float], ...]
    base_points: tuple[tuple[float, float], ...]
    props: dict[str, Property]
    visual_props: dict[str, Property]
    scripts: dict[str, ScriptInfo]
    ports: tuple[_RawPort, ...]
    skipped: dict[str, int]
    child_page: "_RawPage | None" = None
    block_image: tuple[_RawDecor, ...] = ()
    nested_objects: int = 0


@dataclass(slots=True)
class _RawPage:
    props: dict[str, Property]
    script: ScriptInfo
    objects: list[_RawObject]
    skipped: dict[str, int] = field(default_factory=dict)
    block_image_objects: int = 0
    block_image_pages: int = 0


@dataclass(slots=True)
class _Entity:
    order: int
    raw: _RawObject
    kind: str
    id: str
    address: str
    object: ModelObject | None = None
    wire: ModelWire | None = None
    decoration: Decoration | None = None


def _clean(value: str | None) -> str:
    return clean_value(value or "")


def _decode(value: str) -> str:
    try:
        return decode_xprt_value(value)
    except Exception:  # noqa: BLE001 - поврежденное значение не должно терять запись
        return _clean(value)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _text(elem: Any, tag: str) -> str:
    child = elem.find(tag)
    return _clean("".join(child.itertext())) if child is not None else ""


def _int(value: str, default: int = -1) -> int:
    try:
        return int(value.strip())
    except (TypeError, ValueError):
        return default


def _float(value: str, default: float = -1.0) -> float:
    try:
        return float(value.strip())
    except (TypeError, ValueError):
        return default


def _points(value: str) -> tuple[tuple[float, float], ...]:
    return tuple((float(x), float(y)) for x, y in _POINT_RE.findall(value))


def _points_of(elem: Any, tag: str) -> tuple[tuple[float, float], ...]:
    child = elem.find(tag)
    if child is None:
        return ()
    value = child.find("value")
    raw = "".join(value.itertext()) if value is not None else "".join(child.itertext())
    return _points(_clean(raw))


def _tag_base(tag: Any) -> str | None:
    if not isinstance(tag, str):
        return None
    match = _NUMBERED_RE.match(tag)
    return match.group("base").lower() if match else tag.lower()


def _numbered(elem: Any, base: str) -> Iterator[Any]:
    for child in elem:
        if _tag_base(child.tag) == base:
            yield child


def _value_and_kind(data: Any) -> tuple[str, str, str]:
    value = data.find("value")
    if value is None:
        return "", "unknown", ""
    items = value.find("items")
    index = value.find("index")
    if items is not None or index is not None:
        return _clean(index.text if index is not None else ""), "enum", _clean(
            "".join(items.itertext()) if items is not None else "")
    if len(value):
        return "", "structured", ""
    return _decode(value.text or ""), "scalar", ""


def _property_value(raw: str) -> tuple[str, bool, int, str]:
    if len(raw) <= _MAX_PROPERTY_CHARS:
        return raw, False, len(raw), ""
    return raw[:_MAX_PROPERTY_CHARS], True, len(raw), _sha(raw)


def _parse_props(elem: Any, section: str, ref: str,
                 skipped: dict[str, int]) -> tuple[
                     dict[str, Property], dict[str, Property],
                     dict[str, ScriptInfo]]:
    props: dict[str, Property] = {}
    visual: dict[str, Property] = {}
    scripts: dict[str, ScriptInfo] = {}
    for data in _numbered(elem, "data"):
        name = _text(data, "name")
        if not name:
            skipped[f"{section}_unnamed"] = skipped.get(f"{section}_unnamed", 0) + 1
            continue
        raw_value, kind, items = _value_and_kind(data)
        if items:
            raw_value = raw_value or items
        mode = _text(data, "mode")
        caption = _text(data, "caption")
        text_value = _text(data, "textvalue")
        script_elem = data.find("script")
        script_text = "".join(script_elem.itertext()) if script_elem is not None else ""
        if name in SCRIPT_SLOTS and not script_text:
            script_text = raw_value
        script_hash = _sha(script_text) if script_text else ""
        if name in SCRIPT_SLOTS:
            scripts[name] = ScriptInfo(
                slot=name, section=section, present=bool(script_text),
                sha256=script_hash, length=len(script_text),
                provenance=Provenance(SourceKind.XPRT,
                                      ProvenanceStatus.MEASURED, ref))
            continue
        if section == "custom_params":
            skipped["custom_params"] = skipped.get("custom_params", 0) + 1
            continue
        if section == "visual_props" and name not in KEEP_VISUAL_PROPS:
            skipped["visual_props"] = skipped.get("visual_props", 0) + 1
            continue
        value, truncated, raw_len, value_sha = _property_value(raw_value)
        prop = Property(
            name=name, value=value, section=section, kind=kind, mode=mode,
            caption=caption, text_value=text_value, script_hash=script_hash,
            truncated=truncated, raw_len=raw_len, sha256=value_sha,
            provenance=Provenance(SourceKind.XPRT,
                                  ProvenanceStatus.MEASURED, ref))
        if section == "visual_props":
            visual[name] = prop
        else:
            props[name] = prop
    return props, visual, scripts


def _parse_ports(elem: Any) -> tuple[_RawPort, ...]:
    ports = elem.find("ports")
    if ports is None:
        return ()
    result: list[_RawPort] = []
    for index, port in enumerate(_numbered(ports, "port")):
        fields = {
            child.tag: _clean("".join(child.itertext()))
            for child in port
            if isinstance(child.tag, str) and not len(child)
        }
        result.append(_RawPort(
            index=index, fields=fields,
            name=fields.get("name", ""), mode=fields.get("mode", "")))
    return tuple(result)


def _parse_object(elem: Any, order: int, ref: str) -> _RawObject:
    skipped: dict[str, int] = {}
    fields: dict[str, str] = {}
    props: dict[str, Property] = {}
    visual: dict[str, Property] = {}
    scripts: dict[str, ScriptInfo] = {}
    points: tuple[tuple[float, float], ...] = ()
    base_points: tuple[tuple[float, float], ...] = ()
    ports: tuple[_RawPort, ...] = ()
    nested = 0
    for child in elem:
        tag = _tag_base(child.tag)
        if tag is None:
            continue
        if tag == "points":
            points = _points_of(elem, "points")
            continue
        if tag == "base_points":
            base_points = _points_of(elem, "base_points")
            continue
        if tag == "ports":
            ports = _parse_ports(elem)
            continue
        if tag in ("custom_props", "custom_params", "visual_props"):
            p, v, s = _parse_props(child, tag, ref, skipped)
            props.update(p)
            visual.update(v)
            scripts.update(s)
            continue
        if tag == "script":
            text = _clean("".join(child.itertext()))
            scripts["script"] = ScriptInfo(
                slot="script", section="object", present=bool(text),
                sha256=_sha(text) if text else "", length=len(text),
                provenance=Provenance(SourceKind.XPRT,
                                      ProvenanceStatus.MEASURED, ref))
            continue
        if tag == "containerblock":
            nested += sum(1 for item in child.iter()
                          if _tag_base(item.tag) == "object")
            continue
        if tag in ("page", "blockimage"):
            continue
        if not len(child):
            fields[tag] = _clean("".join(child.itertext()))
    if nested:
        skipped["legacy_containerblock_objects"] = nested
    return _RawObject(
        order=order, fields=fields, points=points, base_points=base_points,
        props=props, visual_props=visual, scripts=scripts, ports=ports,
        skipped=skipped, nested_objects=nested)


def _parse_decor_page(elem: Any) -> tuple[_RawDecor, ...]:
    result: list[_RawDecor] = []
    for order, obj in enumerate(_numbered(elem, "object")):
        raw = _parse_object(obj, order, "")
        text = raw.visual_props.get("Text")
        text_value = raw.visual_props.get("LabelText")
        result.append(_RawDecor(
            order=order,
            name=raw.fields.get("name", ""),
            class_name=raw.fields.get("class_name", ""),
            obj_type=raw.fields.get("obj_type", ""),
            points=raw.points,
            text=(text.value if text is not None
                  else (text_value.value if text_value is not None else "")),
        ))
    return tuple(result)


def _parse_page(elem: Any) -> _RawPage:
    props: dict[str, Property] = {}
    script = ScriptInfo(slot="page_script", section="page", present=False)
    skipped: dict[str, int] = {}
    objects: list[_RawObject] = []
    for child in elem:
        tag = _tag_base(child.tag)
        if tag is None:
            continue
        if tag == "object":
            continue
        if tag == "script":
            text = _clean("".join(child.itertext()))
            script = ScriptInfo(
                slot="page_script", section="page", present=bool(text),
                sha256=_sha(text) if text else "", length=len(text),
                provenance=Provenance(SourceKind.XPRT,
                                      ProvenanceStatus.MEASURED, "page"))
            continue
        if tag in ("signal_list", "connect_list"):
            skipped[tag] = skipped.get(tag, 0) + 1
            continue
        if not len(child):
            props[tag] = Property(
                name=tag, value=_clean("".join(child.itertext())),
                section="page",
                provenance=Provenance(SourceKind.XPRT,
                                      ProvenanceStatus.MEASURED, "page"))
    return _RawPage(props=props, script=script, objects=objects,
                    skipped=skipped)


def _classify(raw: _RawObject, has_page: bool) -> ObjectKind:
    class_name = raw.fields.get("class_name", "")
    obj_type = raw.fields.get("obj_type", "")
    if has_page:
        return ObjectKind.SUBMODEL
    if obj_type == "103" or class_name in PORT_BLOCKS:
        return ObjectKind.PORT_BLOCK
    if class_name in MEMORY_CELLS or obj_type in ("104", "105"):
        return ObjectKind.MEMORY_CELL
    if obj_type in ANNOTATION_TYPES or class_name in ANNOTATION_CLASSES:
        return ObjectKind.ANNOTATION
    if obj_type in DECORATION_TYPES or class_name in DECORATION_CLASSES:
        return ObjectKind.DECORATION
    if obj_type in BLOCK_TYPES or (not obj_type and class_name):
        return ObjectKind.BLOCK
    return ObjectKind.UNKNOWN


def _segment(name: str, order: int, duplicates: set[str]) -> str:
    base = name or "object"
    return base if base not in duplicates else f"{base}#{order}"


def _direction(mode: str) -> PortDirection:
    if mode == "0":
        return PortDirection.IN
    if mode == "1":
        return PortDirection.OUT
    if mode == "2":
        return PortDirection.UNDIRECTED
    return PortDirection.UNKNOWN


def _build_port(raw: _RawPort, object_id: str, ref: str) -> ModelPort:
    fields = raw.fields
    return ModelPort(
        id=ids.port_id(object_id, raw.index),
        object_id=object_id,
        index=raw.index,
        name=raw.name,
        direction=_direction(raw.mode),
        side=_int(fields.get("side", ""), -1),
        x=_float(fields.get("x", "")),
        y=_float(fields.get("y", "")),
        x_glob=_float(fields.get("x_glob", "")),
        y_glob=_float(fields.get("y_glob", "")),
        type_id=fields.get("type", ""),
        item_id=fields.get("itemid", ""),
        fields=dict(fields),
        provenance=Provenance(SourceKind.XPRT, ProvenanceStatus.MEASURED,
                              ref))


class _Converter:
    def __init__(self, source_hash: str) -> None:
        self.source_hash = source_hash
        self.containers: list[Container] = []
        self.objects: list[ModelObject] = []
        self.wires: list[ModelWire] = []
        self.decorations: list[Decoration] = []
        self.block_image_objects: list[Decoration] = []
        self.discrepancies: list[Discrepancy] = []
        self.containers_by_id: dict[str, Container] = {}
        self.objects_by_id: dict[str, ModelObject] = {}
        self.unknown_types = 0
        self.block_image_pages = 0
        self.unresolved_ends = 0
        self.unresolved_branches = 0

    def _discrepancy(self, code: str, severity: Severity, subject: str,
                     detail: str) -> None:
        self.discrepancies.append(
            Discrepancy(code=code, severity=severity, subject=subject,
                        detail=detail, sources=("xprt",)))

    def convert(self, page: _RawPage) -> str:
        root_id = self._visit(page, "main", ContainerKind.PROJECT, "", 0)
        return root_id

    def _visit(self, page: _RawPage, address: str, kind: ContainerKind,
               parent_object_id: str, order: int) -> str:
        container_id = ids.container_id(address)
        names = [item.fields.get("name", "") for item in page.objects
                 if item.fields.get("obj_type", "") != "101"]
        duplicates = {name for name in names if names.count(name) > 1 and name}
        wire_names = [item.fields.get("name", "") for item in page.objects
                      if item.fields.get("obj_type", "") == "101"]
        wire_duplicates = {name for name in wire_names
                           if wire_names.count(name) > 1 and name}
        for name in sorted(duplicates):
            self._discrepancy("duplicate_object_name", Severity.INFO,
                              address, f"имя объекта повторяется: {name}")
        for name in sorted(wire_duplicates):
            self._discrepancy("duplicate_wire_name", Severity.INFO,
                              address, f"имя провода повторяется: {name}")

        entities: dict[int, _Entity] = {}
        for raw in page.objects:
            name = raw.fields.get("name", "")
            ref = f"{address}/{name or raw.order}"
            obj_type = raw.fields.get("obj_type", "")
            if obj_type == "101":
                wire_segment = _segment(name or "wire", raw.order, set())
                wire_address = f"{address}::{wire_segment}#{raw.order}"
                entity = _Entity(order=raw.order, raw=raw, kind="wire",
                                 id=ids.wire_id(container_id, raw.order),
                                 address=wire_address)
            else:
                has_page = raw.child_page is not None
                kind_obj = _classify(raw, has_page)
                segment = _segment(name, raw.order, duplicates)
                obj_address = f"{address}::{segment}"
                obj_id = ids.object_id(container_id, raw.order)
                if kind_obj in (ObjectKind.ANNOTATION, ObjectKind.DECORATION):
                    text = ""
                    label = raw.visual_props.get("Text")
                    if label is not None:
                        text = label.value
                    else:
                        label = raw.visual_props.get("LabelText")
                        text = label.value if label is not None else ""
                    decoration = Decoration(
                        id=ids.decoration_id(container_id, raw.order),
                        container_id=container_id, address=obj_address,
                        name=name, class_name=raw.fields.get("class_name", ""),
                        obj_type=obj_type, order=raw.order,
                        points=raw.points, text=text,
                        provenance=Provenance(SourceKind.XPRT,
                                              ProvenanceStatus.MEASURED, ref))
                    self.decorations.append(decoration)
                    entity = _Entity(order=raw.order, raw=raw, kind="decoration",
                                     id=decoration.id, address=obj_address,
                                     decoration=decoration)
                else:
                    if kind_obj is ObjectKind.UNKNOWN:
                        self.unknown_types += 1
                        self._discrepancy("unknown_object_type", Severity.WARNING,
                                          obj_address,
                                          f"тип {obj_type or '?'} не отнесён к модели")
                    ports = tuple(_build_port(item, obj_id, ref)
                                  for item in raw.ports)
                    visual_uid = raw.visual_props.get("UID")
                    uid = (raw.fields.get("uid", "")
                           or (visual_uid.value if visual_uid else ""))
                    obj = ModelObject(
                        id=obj_id, address=obj_address,
                        container_id=container_id, name=name,
                        class_name=raw.fields.get("class_name", ""),
                        obj_type=obj_type, order=raw.order, kind=kind_obj,
                        points=raw.points, props=raw.props,
                        visual_props=raw.visual_props, scripts=raw.scripts,
                        ports=ports,
                        uid=uid,
                        indexstr=raw.fields.get("indexstr", ""),
                        width=(_float(raw.fields.get("width", ""))
                               if raw.fields.get("width") else None),
                        height=(_float(raw.fields.get("height", ""))
                                if raw.fields.get("height") else None),
                        angle=(_float(raw.fields.get("angle", ""))
                               if raw.fields.get("angle") else None),
                        filename=raw.fields.get("filename", ""),
                        extra={k: v for k, v in raw.fields.items()
                               if k not in ("name", "class_name", "obj_type")},
                        provenance=Provenance(SourceKind.XPRT,
                                              ProvenanceStatus.MEASURED, ref))
                    self.objects.append(obj)
                    self.objects_by_id[obj.id] = obj
                    entity = _Entity(order=raw.order, raw=raw, kind="object",
                                     id=obj.id, address=obj_address, object=obj)
                if raw.block_image:
                    self.block_image_pages += 1
                    for decor in raw.block_image:
                        icon_address = (f"{obj_address}::icon/"
                                        f"{decor.name or decor.order}")
                        self.block_image_objects.append(Decoration(
                            id=ids.decoration_id(
                                f"{container_id}|icon|{raw.order}", decor.order),
                            container_id=container_id, address=icon_address,
                            name=decor.name, class_name=decor.class_name,
                            obj_type=decor.obj_type, order=decor.order,
                            points=decor.points, text=decor.text,
                            provenance=Provenance(
                                SourceKind.XPRT, ProvenanceStatus.MEASURED,
                                icon_address)))
            entities[raw.order] = entity

        # Провода разрешаются после того, как известны все объекты страницы.
        for wire_entity in entities.values():
            if wire_entity.kind != "wire":
                continue
            self._convert_wire(wire_entity, entities, container_id, address)

        object_ids = tuple(item.id for item in entities.values()
                           if item.kind == "object")
        wire_ids = tuple(item.id for item in entities.values()
                         if item.kind == "wire")
        child_ids: list[str] = []
        for raw in page.objects:
            child_entity = entities.get(raw.order)
            if (child_entity is None or child_entity.object is None
                    or raw.child_page is None):
                continue
            child_segment = _segment(raw.fields.get("name", ""),
                                     raw.order, duplicates)
            child_address = f"{address}/{child_segment}"
            child_id = self._visit(raw.child_page, child_address,
                                   ContainerKind.SUBMODEL,
                                   child_entity.object.id, raw.order)
            child_ids.append(child_id)
        script_present = page.script.present
        page_name = page.props.get("name")
        default_name = ("main" if kind is ContainerKind.PROJECT
                        else address.rsplit("/", 1)[-1])
        container = Container(
            id=container_id, address=address, kind=kind,
            name=(page_name.value if page_name is not None else "") or default_name,
            order=order, parent_object_id=parent_object_id,
            props=page.props, script_hash=page.script.sha256,
            script_present=script_present, object_ids=object_ids,
            wire_ids=wire_ids, child_container_ids=tuple(child_ids),
            provenance=Provenance(SourceKind.XPRT, ProvenanceStatus.MEASURED,
                                  address))
        self.containers.append(container)
        self.containers_by_id[container.id] = container
        return container.id

    def _convert_wire(self, entity: _Entity, entities: dict[int, _Entity],
                      container_id: str, container_address: str) -> None:
        raw = entity.raw
        fields = raw.fields
        start_index = _int(fields.get("start_bl_index", ""))
        end_index = _int(fields.get("end_bl_index", ""))
        start = self._wire_end(entities, start_index, fields, "start",
                               container_id, entity.address)
        end = self._wire_end(entities, end_index, fields, "end",
                             container_id, entity.address)
        parent_name = fields.get("parent_wire_name", "")
        parent_index = _int(fields.get("parent_wire_index", ""))
        parent_id = ""
        parent_node = _int(fields.get("parentwirenode", ""))
        parent_status = ProvenanceStatus.UNKNOWN
        kind = WireKind.WIRE
        if start_index == -1:
            parent_entity: _Entity | None = None
            ambiguous = False
            if parent_name:
                matches = [
                    candidate for candidate in entities.values()
                    if candidate.kind == "wire"
                    and candidate.raw.fields.get("name", "") == parent_name
                ]
                if len(matches) == 1:
                    parent_entity = matches[0]
                elif len(matches) > 1:
                    index_candidate = entities.get(parent_index)
                    if index_candidate in matches:
                        parent_entity = index_candidate
                    else:
                        ambiguous = True
            if (parent_entity is None and not ambiguous
                    and 0 <= parent_index < len(entities)):
                index_candidate = entities.get(parent_index)
                if index_candidate is not None and index_candidate.kind == "wire":
                    parent_entity = index_candidate
            if parent_entity is not None:
                parent_id = parent_entity.id
                parent_status = ProvenanceStatus.HYPOTHESIS
                kind = WireKind.BRANCH
                start = WireEnd(
                    kind=WireEndKind.BRANCH, object_id=parent_id,
                    object_name=parent_name or parent_entity.raw.fields.get("name", ""),
                    port_index=parent_node, container_id=container_id,
                    resolved=True,
                    provenance=Provenance(SourceKind.XPRT,
                                          ProvenanceStatus.HYPOTHESIS,
                                          entity.address))
            else:
                self.unresolved_branches += 1
                parent_label = parent_name or parent_index
                reason = ("родитель ветви неоднозначен" if ambiguous
                          else f"родитель ветви не найден: {parent_label}")
                self._discrepancy("branch_parent_unresolved", Severity.ERROR,
                                  entity.address, reason)
                start = WireEnd(
                    kind=WireEndKind.UNRESOLVED,
                    object_name=parent_name, port_index=parent_node,
                    container_id=container_id, resolved=False,
                    reason="branch_parent_not_found",
                    provenance=Provenance(SourceKind.XPRT,
                                          ProvenanceStatus.UNKNOWN,
                                          entity.address))
        if start.kind is WireEndKind.UNRESOLVED:
            self.unresolved_ends += 1
        if end.kind is WireEndKind.UNRESOLVED:
            self.unresolved_ends += 1
        wire = ModelWire(
            id=entity.id, address=entity.address, container_id=container_id,
            order=raw.order, name=fields.get("name", ""), kind=kind,
            start=start, end=end, points=raw.base_points,
            node_points=raw.points,
            start_xy=(_float(fields.get("start_x", "")),
                      _float(fields.get("start_y", ""))),
            end_xy=(_float(fields.get("end_x", "")),
                    _float(fields.get("end_y", ""))),
            branch_parent_id=parent_id, branch_node=parent_node,
            parent_status=parent_status, props=raw.props,
            provenance=Provenance(SourceKind.XPRT,
                                  ProvenanceStatus.MEASURED, entity.address))
        self.wires.append(wire)
        entity.wire = wire

    def _wire_end(self, entities: dict[int, _Entity], index: int,
                  fields: dict[str, str], side: str, container_id: str,
                  ref: str) -> WireEnd:
        name = fields.get(f"{side}_bl_name", "")
        port_index = _int(fields.get(f"{side}_port_index", ""))
        if index == -1:
            return WireEnd(
                kind=WireEndKind.UNCONNECTED, object_name=name,
                port_index=port_index, container_id=container_id,
                resolved=False, reason="unconnected",
                provenance=Provenance(SourceKind.XPRT,
                                      ProvenanceStatus.MEASURED, ref))
        entity = entities.get(index)
        if entity is None or entity.object is None:
            self._discrepancy("wire_end_unresolved", Severity.ERROR, ref,
                              f"{side}: объект {index} ({name}) не найден")
            return WireEnd(
                kind=WireEndKind.UNRESOLVED, object_name=name,
                port_index=port_index, container_id=container_id,
                resolved=False, reason="object_not_found",
                provenance=Provenance(SourceKind.XPRT,
                                      ProvenanceStatus.UNKNOWN, ref))
        obj = entity.object
        if name and obj.name and name != obj.name:
            self._discrepancy("end_index_name_conflict", Severity.ERROR, ref,
                              f"{side}: индекс {index} даёт {obj.name}, "
                              f"а имя {name}")
        port = obj.port(port_index)
        if port is None:
            self._discrepancy("wire_port_out_of_range", Severity.ERROR, ref,
                              f"{side}: у {obj.name} нет порта {port_index}")
            return WireEnd(
                kind=WireEndKind.UNRESOLVED, object_id=obj.id,
                object_name=obj.name, port_index=port_index,
                container_id=container_id, resolved=False,
                reason="port_not_found",
                provenance=Provenance(SourceKind.XPRT,
                                      ProvenanceStatus.UNKNOWN, ref))
        expected = ((PortDirection.OUT, PortDirection.UNDIRECTED)
                    if side == "start"
                    else (PortDirection.IN, PortDirection.UNDIRECTED))
        direction_unknown = port.direction is PortDirection.UNKNOWN
        if port.direction not in expected and not direction_unknown:
            self._discrepancy("wire_direction_mismatch", Severity.WARNING, ref,
                              f"{side}: порт {obj.name}:{port_index} имеет "
                              f"режим {port.direction.value}")
        return WireEnd(
            kind=WireEndKind.PORT, object_id=obj.id, object_name=obj.name,
            port_index=port_index, container_id=container_id, resolved=True,
            provenance=Provenance(SourceKind.XPRT,
                                  ProvenanceStatus.MEASURED, ref))

    def finish(self, root_page: _RawPage) -> ModelIR:
        self.convert(root_page)
        self._boundaries()
        self._memory_links()
        discrepancies = tuple(self.discrepancies)
        counts: dict[str, int] = {}
        for item in discrepancies:
            counts[item.code] = counts.get(item.code, 0) + 1
        ports_real = sum(len(item.ports) for item in self.objects)
        branches = sum(1 for item in self.wires
                       if item.kind is WireKind.BRANCH)
        coverage = Coverage(
            containers=len(self.containers), objects=len(self.objects),
            ports_real=ports_real, wires=len(self.wires), branches=branches,
            decorations=len(self.decorations),
            block_image_pages=self.block_image_pages,
            block_image_objects=len(self.block_image_objects),
            unresolved_ends=self.unresolved_ends,
            unresolved_branches=self.unresolved_branches,
            unknown_object_types=self.unknown_types,
            source_status=SourceStatus.OK,
            port_order_status=ProvenanceStatus.HYPOTHESIS,
            skipped=_merge_skipped(root_page),
            discrepancy_counts=counts)
        meta = ModelMeta(
            ir_schema=IR_SCHEMA_VERSION, primary_source=SourceKind.XPRT,
            source_set=(SourceKind.XPRT,),
            source_hashes={"xprt": self.source_hash},
            structure_hash="", content_hash="")
        model = ModelIR(
            meta=meta, containers=tuple(sorted(self.containers,
                                               key=lambda item: item.address)),
            objects=tuple(sorted(self.objects, key=lambda item: item.address)),
            wires=tuple(sorted(self.wires, key=lambda item: item.address)),
            boundaries=tuple(self._boundaries_cache),
            memory_links=tuple(self._memory_cache),
            decorations=tuple(sorted(self.decorations,
                                     key=lambda item: item.address)),
            block_image_objects=tuple(self.block_image_objects),
            discrepancies=discrepancies, coverage=coverage)
        meta = replace(meta, structure_hash=ids.structure_hash(model),
                       content_hash=ids.content_hash(model))
        return replace(model, meta=meta)

    _boundaries_cache: list[BoundaryPort] = []
    _memory_cache: list[MemoryLink] = []

    def _boundaries(self) -> None:
        self._boundaries_cache = []
        for obj in self.objects:
            if obj.kind is not ObjectKind.SUBMODEL:
                continue
            container = next((item for item in self.containers
                              if item.parent_object_id == obj.id), None)
            if container is None:
                continue
            internal = [item for item in self.objects
                        if item.container_id == container.id
                        and item.kind is ObjectKind.PORT_BLOCK]
            for port in obj.ports:
                if port.direction is PortDirection.OUT:
                    wanted = {"Порт выхода"}
                elif port.direction is PortDirection.IN:
                    wanted = {"Порт входа"}
                else:
                    wanted = {"Порт входа", "Порт выхода"}
                candidates = [item for item in internal
                              if item.class_name in wanted
                              and item.ports
                              and item.ports[0].name == port.name]
                chosen = candidates[0] if len(candidates) == 1 else None
                chosen_names = (chosen.visual_props.get("PortNames")
                                if chosen else None)
                boundary = BoundaryPort(
                    id=ids.boundary_id(obj.id, port.index),
                    submodel_object_id=obj.id,
                    external_port_index=port.index,
                    external_port_name=port.name,
                    internal_object_id=(chosen.id if chosen else ""),
                    internal_port_index=(chosen.ports[0].index if chosen else -1),
                    port_names=(chosen_names.value if chosen_names else ""),
                    resolved=chosen is not None,
                    reason=("" if chosen else
                            ("ambiguous" if len(candidates) > 1 else "not_found")),
                    provenance=Provenance(SourceKind.DERIVED,
                                          ProvenanceStatus.DERIVED, obj.address))
                if not boundary.resolved:
                    self._discrepancy("boundary_unresolved", Severity.WARNING,
                                      obj.address,
                                      f"порт {port.name}: {boundary.reason}")
                self._boundaries_cache.append(boundary)

    def _memory_links(self) -> None:
        self._memory_cache = []
        groups: dict[str, tuple[list[str], list[str]]] = {}
        unnamed = 0
        for obj in self.objects:
            if obj.kind is not ObjectKind.MEMORY_CELL:
                continue
            prop = obj.visual_props.get("PortNames") or obj.props.get("PortNames")
            variable = " ".join((prop.value if prop is not None else "").split())
            port = obj.ports[0] if obj.ports else None
            address = f"{obj.address}:{port.index if port is not None else -1}"
            if not variable:
                unnamed += 1
                self._discrepancy("memory_name_missing", Severity.WARNING,
                                  obj.address, "у ячейки памяти нет PortNames")
                self._memory_cache.append(MemoryLink(
                    id=ids.memory_id(obj.address), variable="",
                    writers=((address,) if obj.class_name == "В память" else ()),
                    readers=((address,) if obj.class_name == "Из памяти" else ()),
                    resolved=False, reason="memory_name_missing",
                    provenance=Provenance(SourceKind.DERIVED,
                                          ProvenanceStatus.DERIVED, obj.address)))
                continue
            if port is None:
                self._discrepancy("memory_port_missing", Severity.WARNING,
                                  obj.address,
                                  "у ячейки памяти нет порта")
                self._memory_cache.append(MemoryLink(
                    id=ids.memory_id(obj.address), variable=variable,
                    writers=((obj.address,) if obj.class_name == "В память"
                             else ()),
                    readers=((obj.address,) if obj.class_name == "Из памяти"
                             else ()),
                    resolved=False, reason="port_missing",
                    provenance=Provenance(SourceKind.DERIVED,
                                          ProvenanceStatus.DERIVED, obj.address)))
                continue
            writers, readers = groups.setdefault(variable, ([], []))
            if obj.class_name == "В память":
                writers.append(address)
            elif obj.class_name == "Из памяти":
                readers.append(address)
        for variable, (writers, readers) in sorted(groups.items()):
            resolved = bool(writers and readers)
            if not resolved:
                self._discrepancy("memory_unpaired", Severity.WARNING,
                                  variable, "у переменной нет пары")
            self._memory_cache.append(MemoryLink(
                id=ids.memory_id(variable), variable=variable,
                writers=tuple(writers), readers=tuple(readers),
                resolved=resolved,
                reason="" if resolved else "unpaired",
                provenance=Provenance(SourceKind.DERIVED,
                                      ProvenanceStatus.DERIVED, variable)))


def _merge_skipped(page: _RawPage) -> dict[str, int]:
    result = dict(page.skipped)
    for item in page.objects:
        for key, value in item.skipped.items():
            result[key] = result.get(key, 0) + value
        if item.child_page is not None:
            for key, value in _merge_skipped(item.child_page).items():
                result[key] = result.get(key, 0) + value
    return result


def _strip_declaration(text: str) -> str:
    text = text.lstrip("﻿")
    if text.startswith("<?xml"):
        end = text.find("?>")
        if end >= 0:
            text = text[end + 2:]
    return text


def _parse_stream(stream: BinaryIO | TextIO, *, source_name: str,
                  limits: Limits, source_hash: str) -> ModelIR:
    raw_objects: dict[int, _RawObject] = {}
    object_orders: dict[int, int] = {}
    page_orders: dict[int, int] = {}
    page_containers: dict[int, _RawPage] = {}
    block_images: dict[int, tuple[_RawDecor, ...]] = {}
    root_page: _RawPage | None = None
    stack: list[str] = []
    elems: list[Any] = []
    objects_seen = 0
    wires_seen = 0
    pages_seen = 0

    try:
        for event, elem in ET.iterparse(stream, events=("start", "end")):
            if event == "start":
                stack.append(elem.tag)
                elems.append(elem)
                if elem.tag == "page":
                    pages_seen += 1
                    depth = sum(1 for tag in stack if tag == "page")
                    if depth > limits.max_depth:
                        raise ModelIRLimitError(
                            f"глубина страниц {depth} больше предела "
                            f"{limits.max_depth}")
                    page_orders[id(elem)] = 0
                elif elem.tag == "object":
                    order = 0
                    for parent in reversed(elems[:-1]):
                        if parent.tag == "page":
                            order = page_orders.get(id(parent), 0)
                            page_orders[id(parent)] = order + 1
                            break
                    object_orders[id(elem)] = order
                continue

            tag = elem.tag
            if tag == "object":
                order = object_orders.pop(id(elem), 0)
                parent_tag = elems[-2].tag if len(elems) >= 2 else ""
                objects_seen += 1
                if parent_tag != "containerblock":
                    # Старая вложенность: объект не является прямым объектом
                    # страницы. Родитель уже учёл его в покрытии.
                    raw = _parse_object(elem, order, "")
                    raw_objects[id(elem)] = raw
                    if raw.fields.get("obj_type") == "101":
                        wires_seen += 1
                if objects_seen > limits.max_objects:
                    raise ModelIRLimitError(
                        f"объектов больше предела {limits.max_objects}")
                if wires_seen > limits.max_wires:
                    raise ModelIRLimitError(
                        f"проводов больше предела {limits.max_wires}")
            elif tag == "page":
                parent = elems[-2] if len(elems) >= 2 else None
                if parent is not None and parent.tag == "blockimage":
                    owner = next((item for item in reversed(elems[:-2])
                                  if item.tag == "object"), None)
                    if owner is not None:
                        block_images[id(owner)] = _parse_decor_page(elem)
                    for obj in _numbered(elem, "object"):
                        raw_objects.pop(id(obj), None)
                        object_orders.pop(id(obj), None)
                        obj.clear()
                    elem.clear()
                elif parent is not None and parent.tag == "object":
                    page = _parse_page(elem)
                    for obj in _numbered(elem, "object"):
                        raw_obj = raw_objects.get(id(obj))
                        if raw_obj is None:
                            raw_obj = _parse_object(
                                obj, object_orders.pop(id(obj), 0), "")
                        else:
                            raw_objects.pop(id(obj))
                        raw_obj.order = object_orders.pop(id(obj), raw_obj.order)
                        raw_obj.child_page = (
                            page_containers.pop(id(obj))
                            if id(obj) in page_containers else None)
                        raw_obj.block_image = block_images.pop(id(obj), ())
                        page.objects.append(raw_obj)
                        obj.clear()
                    page_containers[id(parent)] = page
                    elem.clear()
                elif parent is not None and parent.tag == "project":
                    root_page = _parse_page(elem)
                    for obj in _numbered(elem, "object"):
                        raw_obj = raw_objects.get(id(obj))
                        if raw_obj is None:
                            raw_obj = _parse_object(
                                obj, object_orders.pop(id(obj), 0), "")
                        else:
                            raw_objects.pop(id(obj))
                        raw_obj.order = object_orders.pop(id(obj), raw_obj.order)
                        raw_obj.child_page = (
                            page_containers.pop(id(obj))
                            if id(obj) in page_containers else None)
                        raw_obj.block_image = block_images.pop(id(obj), ())
                        root_page.objects.append(raw_obj)
                        obj.clear()
                    elem.clear()
                else:
                    # Страница в неожиданном контейнере: сохраняем как
                    # субмодель, чтобы не потерять объекты молча.
                    page = _parse_page(elem)
                    for obj in _numbered(elem, "object"):
                        raw_obj = raw_objects.get(id(obj))
                        if raw_obj is None:
                            raw_obj = _parse_object(
                                obj, object_orders.pop(id(obj), 0), "")
                        else:
                            raw_objects.pop(id(obj))
                        raw_obj.order = object_orders.pop(id(obj), raw_obj.order)
                        raw_obj.child_page = (
                            page_containers.pop(id(obj))
                            if id(obj) in page_containers else None)
                        raw_obj.block_image = block_images.pop(id(obj), ())
                        page.objects.append(raw_obj)
                        obj.clear()
                    owner = parent if parent is not None else elem
                    page_containers[id(owner)] = page
                    elem.clear()
                page_orders.pop(id(elem), None)
            elif tag == "blockimage":
                pass
            elems.pop()
            stack.pop()
    except (ET.ParseError, DefusedXmlException) as exc:
        raise XprtParseError(
            f"выгрузка не разобрана как корректный XML ({type(exc).__name__}: "
            f"{exc})") from exc

    if root_page is None:
        root_page = _RawPage(props={}, script=ScriptInfo(
            slot="page_script", section="page", present=False),
            objects=[])
    converter = _Converter(source_hash)
    return converter.finish(root_page)


def parse_xprt(source: str | bytes, *, source_name: str = "",
               limits: Limits | None = None) -> ModelIR:
    """Разобрать текст или байты `.xprt` в Model IR."""
    limits = limits or Limits()
    if isinstance(source, str):
        raw = source.encode("utf-8")
        if len(raw) > limits.max_bytes:
            raise ModelIRLimitError(
                f"размер выгрузки {len(raw)} больше предела {limits.max_bytes}")
        text = _strip_declaration(source)
        stream: BinaryIO | TextIO = io.StringIO(text)
    else:
        raw = source
        if len(raw) > limits.max_bytes:
            raise ModelIRLimitError(
                f"размер выгрузки {len(raw)} больше предела {limits.max_bytes}")
        stream = io.BytesIO(raw)
    return _parse_stream(stream, source_name=source_name, limits=limits,
                         source_hash=hashlib.sha256(raw).hexdigest())


def parse_xprt_file(path: str | Path, *, limits: Limits | None = None) -> ModelIR:
    """Разобрать `.xprt` из файла потоково, без чтения всего текста в строку."""
    limits = limits or Limits()
    file_path = Path(path)
    try:
        size = file_path.stat().st_size
    except OSError as exc:
        raise XprtParseError(f"файл выгрузки не открыт: {exc}") from exc
    if size > limits.max_bytes:
        raise ModelIRLimitError(
            f"размер выгрузки {size} больше предела {limits.max_bytes}")
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    with file_path.open("rb") as handle:
        return _parse_stream(handle, source_name=file_path.name, limits=limits,
                             source_hash=digest.hexdigest())
