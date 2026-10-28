"""Разбор декларативного текста `savemodeltofile` в Model IR.

Текст описывает текущий контейнер на всю глубину `subsystem`. Портов как
контракта в нём нет: порты синтезируются из адресов концов проводов и
помечаются `synthetic`. Это честно видно в покрытии, а не выдаётся за
измеренный интерфейс блока.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

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
from .errors import ModelIRLimitError, ModelTextParseError
from .ir import (
    IR_SCHEMA_VERSION,
    Container,
    Coverage,
    Decoration,
    Discrepancy,
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
from .xprt_model import (
    ANNOTATION_CLASSES,
    DECORATION_CLASSES,
    MEMORY_CELLS,
    PORT_BLOCKS,
    Limits,
)

_RESERVED = frozenset({
    "type", "points", "subsystem", "src", "dst", "portnames", "Script",
    "OnInitScript", "OnRunScript", "OnDestroyScript", "uid",
})
_SCRIPT_KEYS = frozenset({
    "Script", "OnInitScript", "OnRunScript", "OnDestroyScript",
})
_ENDPOINT_RE = re.compile(r"^(.+):(out|in):(\d+)$")
_BRANCH_RE = re.compile(r"^(.+):(\d+)$")
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")
_EMBEDDED_QUOTE_RE = re.compile(r'"\s*\+\s*chr\(34\)\s*\+\s*"')
_IDENT_RE = re.compile(r"[^\s()\[\]=,:;]+")
_PUNCT = frozenset("()[]=,:;")


@dataclass(frozen=True, slots=True)
class _Token:
    kind: str
    value: str
    line: int
    column: int


@dataclass(slots=True)
class _Record:
    name: str
    values: dict[str, Any]
    subsystem: list["_Record"]
    order: int
    line: int


class _Stream:
    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0
        self.line = 1
        self.column = 1

    def _advance(self, count: int = 1) -> None:
        for _ in range(count):
            if self.pos >= len(self.text):
                return
            if self.text[self.pos] == "\n":
                self.line += 1
                self.column = 1
            else:
                self.column += 1
            self.pos += 1

    def _skip(self) -> None:
        while self.pos < len(self.text):
            char = self.text[self.pos]
            if char.isspace():
                self._advance()
                continue
            if self.text.startswith("//", self.pos):
                end = self.text.find("\n", self.pos)
                self._advance((end if end >= 0 else len(self.text)) - self.pos)
                continue
            break

    def next(self) -> _Token:
        self._skip()
        if self.pos >= len(self.text):
            return _Token("eof", "", self.line, self.column)
        line, column = self.line, self.column
        char = self.text[self.pos]
        if char in _PUNCT:
            self._advance()
            return _Token("punct", char, line, column)
        if char == '"':
            return _Token("string", self._string(), line, column)
        match = _NUMBER_RE.match(self.text, self.pos)
        if match is not None:
            value = match.group(0)
            self._advance(len(value))
            return _Token("number", value, line, column)
        match = _IDENT_RE.match(self.text, self.pos)
        if match is None:
            raise ModelTextParseError(
                f"неожиданный символ {char!r} в строке {line}, "
                f"столбец {column}")
        value = match.group(0)
        self._advance(len(value))
        return _Token("ident", value, line, column)

    def _string(self) -> str:
        self._advance()
        result: list[str] = []
        while self.pos < len(self.text):
            char = self.text[self.pos]
            if char == '"':
                embedded = _EMBEDDED_QUOTE_RE.match(self.text, self.pos)
                if embedded is not None:
                    result.append('"')
                    self._advance(embedded.end() - embedded.start())
                    continue
                self._advance()
                return "".join(result)
            if char == "\\" and self.pos + 1 < len(self.text):
                nxt = self.text[self.pos + 1]
                if nxt == '"':
                    result.append('"')
                    self._advance(2)
                    continue
            result.append(char)
            self._advance()
        raise ModelTextParseError(
            f"незакрытая строка в строке {self.line}, столбец {self.column}")


class _Parser:
    def __init__(self, stream: _Stream) -> None:
        self.stream = stream
        self.token = stream.next()

    def _take(self, kind: str, value: str | None = None) -> _Token:
        token = self.token
        if token.kind != kind or (value is not None and token.value != value):
            raise ModelTextParseError(
                f"ожидалось {value or kind!r}, получено {token.value!r} "
                f"в строке {token.line}, столбец {token.column}")
        self.token = self.stream.next()
        return token

    def _accept(self, kind: str, value: str | None = None) -> bool:
        if self.token.kind == kind and (
                value is None or self.token.value == value):
            self.token = self.stream.next()
            return True
        return False

    def document(self) -> tuple[dict[str, Any], list[_Record]]:
        self._take("punct", "(")
        page: dict[str, Any] = {}
        records: list[_Record] = []
        while not self._accept("punct", ")"):
            if self.token.kind == "eof":
                raise ModelTextParseError("текст модели оборван: нет ')'")
            name = self.token
            if name.kind != "ident":
                raise ModelTextParseError(
                    f"ожидалось имя записи, получено {name.value!r} "
                    f"в строке {name.line}")
            saved = self.stream.pos, self.stream.line, self.stream.column
            self.token = self.stream.next()
            if self.token.kind == "punct" and self.token.value == ":":
                self.token = self.stream.next()
                records.append(self._record(name.value, name.line, len(records)))
            else:
                self.stream.pos, self.stream.line, self.stream.column = saved
                self.token = _Token("ident", name.value, name.line, name.column)
                key = self._take("ident").value
                self._take("punct", "=")
                page[key] = self._value()
            self._accept("punct", ",")
            self._accept("punct", ";")
        return page, records

    def _record(self, name: str, line: int, order: int) -> _Record:
        self._take("punct", "(")
        values: dict[str, Any] = {}
        subsystem: list[_Record] = []
        while not self._accept("punct", ")"):
            if self.token.kind == "eof":
                raise ModelTextParseError(
                    f"запись {name!r} оборвана: нет ')'")
            key = self._take("ident").value
            if key == "subsystem":
                self._take("punct", ":")
                self._take("punct", "(")
                while not self._accept("punct", ")"):
                    if self.token.kind == "eof":
                        raise ModelTextParseError("subsystem оборван")
                    child_name = self._take("ident")
                    self._take("punct", ":")
                    subsystem.append(
                        self._record(child_name.value, child_name.line,
                                     len(subsystem)))
                    self._accept("punct", ",")
                continue
            self._take("punct", "=")
            values[key] = self._value()
            self._accept("punct", ",")
            self._accept("punct", ";")
        return _Record(name=name, values=values, subsystem=subsystem,
                       order=order, line=line)

    def _value(self) -> Any:
        token = self.token
        if token.kind == "string":
            self.token = self.stream.next()
            return token.value
        if token.kind == "number":
            self.token = self.stream.next()
            return float(token.value) if any(
                char in token.value for char in ".eE") else int(token.value)
        if token.kind == "ident":
            self.token = self.stream.next()
            return token.value
        if token.kind == "punct" and token.value == "[":
            self.token = self.stream.next()
            items: list[Any] = []
            while not self._accept("punct", "]"):
                items.append(self._value())
                if not self._accept("punct", ","):
                    self._accept("punct", "]")
                    break
            return items
        if token.kind == "punct" and token.value == "(":
            self.token = self.stream.next()
            tuple_items: list[Any] = []
            while not self._accept("punct", ")"):
                tuple_items.append(self._value())
                if not self._accept("punct", ","):
                    self._accept("punct", ")")
                    break
            return tuple(tuple_items)
        raise ModelTextParseError(
            f"ожидалось значение, получено {token.value!r} "
            f"в строке {token.line}, столбец {token.column}")


def _render(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _points(value: Any) -> tuple[tuple[float, float], ...]:
    if not isinstance(value, list):
        return ()
    result: list[tuple[float, float]] = []
    for item in value:
        if (isinstance(item, (list, tuple)) and len(item) >= 2
                and isinstance(item[0], (int, float))
                and isinstance(item[1], (int, float))):
            result.append((float(item[0]), float(item[1])))
    return tuple(result)


def _classify(record: _Record) -> ObjectKind:
    class_name = str(record.values.get("type", ""))
    if record.subsystem:
        return ObjectKind.SUBMODEL
    if class_name in PORT_BLOCKS:
        return ObjectKind.PORT_BLOCK
    if class_name in MEMORY_CELLS:
        return ObjectKind.MEMORY_CELL
    if class_name in ANNOTATION_CLASSES:
        return ObjectKind.ANNOTATION
    if class_name in DECORATION_CLASSES:
        return ObjectKind.DECORATION
    return ObjectKind.BLOCK


def _segment(name: str, order: int, duplicates: set[str]) -> str:
    base = name or "object"
    return base if base not in duplicates else f"{base}#{order}"


def _endpoint(value: Any) -> tuple[str, str, int] | None:
    if not isinstance(value, str):
        return None
    match = _ENDPOINT_RE.match(value)
    if match is not None:
        return match.group(1), match.group(2), int(match.group(3))
    return None


@dataclass(slots=True)
class _Page:
    containers: list[Container]
    objects: list[ModelObject]
    wires: list[ModelWire]
    decorations: list[Decoration]
    skipped: dict[str, int]
    unresolved_ends: int
    unconnected_ends: int
    unresolved_branches: int
    synthetic_ports: int


class _Builder:
    def __init__(self, source_hash: str, source_name: str,
                 limits: Limits) -> None:
        self.source_hash = source_hash
        self.source_name = source_name
        self.limits = limits
        self.containers: list[Container] = []
        self.objects: list[ModelObject] = []
        self.wires: list[ModelWire] = []
        self.decorations: list[Decoration] = []
        self.discrepancies: list[Discrepancy] = []
        self.skipped: dict[str, int] = {}

    def _discrepancy(self, code: str, severity: Severity, subject: str,
                     detail: str) -> None:
        self.discrepancies.append(Discrepancy(
            code=code, severity=severity, subject=subject, detail=detail,
            sources=("model_text",)))

    def build(self, page_props: dict[str, Any],
              records: list[_Record]) -> ModelIR:
        self._page(page_props, records, "main", ContainerKind.PROJECT, "", 0)
        counts: dict[str, int] = {}
        for item in self.discrepancies:
            counts[item.code] = counts.get(item.code, 0) + 1
        synthetic = sum(
            1 for item in self.objects for port in item.ports if port.synthetic)
        coverage = Coverage(
            containers=len(self.containers), objects=len(self.objects),
            ports_synthetic=synthetic, wires=len(self.wires),
            branches=sum(1 for item in self.wires
                         if item.kind is WireKind.BRANCH),
            decorations=len(self.decorations),
            unresolved_ends=sum(1 for item in self.wires
                                if item.start.kind is WireEndKind.UNRESOLVED)
            + sum(1 for item in self.wires
                  if item.end.kind is WireEndKind.UNRESOLVED),
            unconnected_ends=sum(1 for item in self.wires
                                 if item.start.kind is WireEndKind.UNCONNECTED)
            + sum(1 for item in self.wires
                  if item.end.kind is WireEndKind.UNCONNECTED),
            unresolved_branches=sum(
                1 for item in self.wires
                if item.start.kind is WireEndKind.UNRESOLVED
                and item.start.reason == "branch_parent_not_found"),
            source_status=SourceStatus.PARTIAL,
            port_order_status=ProvenanceStatus.HYPOTHESIS,
            skipped=dict(self.skipped), discrepancy_counts=counts)
        meta = ModelMeta(
            ir_schema=IR_SCHEMA_VERSION, primary_source=SourceKind.MODEL_TEXT,
            source_set=(SourceKind.MODEL_TEXT,),
            source_hashes={"model_text": self.source_hash},
            structure_hash="", content_hash="", source_name=self.source_name)
        model = ModelIR(
            meta=meta,
            containers=tuple(sorted(self.containers,
                                    key=lambda item: item.address)),
            objects=tuple(sorted(self.objects, key=lambda item: item.address)),
            wires=tuple(sorted(self.wires, key=lambda item: item.address)),
            decorations=tuple(sorted(self.decorations,
                                     key=lambda item: item.address)),
            discrepancies=tuple(self.discrepancies), coverage=coverage)
        meta = ModelMeta(
            ir_schema=meta.ir_schema, primary_source=meta.primary_source,
            source_set=meta.source_set, source_hashes=meta.source_hashes,
            structure_hash=ids.structure_hash(model),
            content_hash=ids.content_hash(model),
            source_name=meta.source_name)
        return ModelIR(
            meta=meta, containers=model.containers, objects=model.objects,
            wires=model.wires, decorations=model.decorations,
            discrepancies=model.discrepancies, coverage=model.coverage)

    def _page(self, page_props: dict[str, Any], records: list[_Record],
              address: str, kind: ContainerKind, parent_object_id: str,
              depth: int) -> str:
        if depth > self.limits.max_depth:
            raise ModelIRLimitError(
                f"глубина subsystem {depth} больше предела "
                f"{self.limits.max_depth}")
        container_id = ids.container_id(address)
        names = [record.name for record in records
                 if str(record.values.get("type", "")) != "wire"]
        duplicates = {name for name, count in Counter(names).items()
                      if count > 1 and name}
        wire_names = [record.name for record in records
                      if str(record.values.get("type", "")) == "wire"]
        for name, count in Counter(wire_names).items():
            if count > 1:
                self.skipped["duplicate_wire_name"] = (
                    self.skipped.get("duplicate_wire_name", 0) + 1)
        object_names: dict[str, list[str]] = {}
        for record in records:
            if str(record.values.get("type", "")) == "wire":
                continue
            object_id = ids.object_id(container_id, record.order)
            object_names.setdefault(record.name, []).append(object_id)
        raw_ports: dict[str, dict[PortDirection, set[int]]] = {}
        for record in records:
            if str(record.values.get("type", "")) != "wire":
                continue
            for side, direction in (("src", PortDirection.OUT),
                                    ("dst", PortDirection.IN)):
                parsed = _endpoint(record.values.get(side))
                if parsed is None:
                    continue
                name, end_kind, index = parsed
                if len(object_names.get(name, ())) != 1:
                    continue
                target = object_names[name][0]
                port_direction = (PortDirection.OUT if end_kind == "out"
                                  else PortDirection.IN)
                raw_ports.setdefault(target, {}).setdefault(
                    port_direction, set()).add(index)
        port_index_map: dict[tuple[str, PortDirection, int], int] = {}
        for target, by_direction in raw_ports.items():
            index = 0
            for direction in (PortDirection.IN, PortDirection.OUT):
                for text_index in sorted(by_direction.get(direction, ())):
                    port_index_map[(target, direction, text_index)] = index
                    index += 1
        object_by_name = {name: values[0] for name, values in object_names.items()
                          if len(values) == 1}
        objects: list[ModelObject] = []
        decorations: list[Decoration] = []
        segments: dict[int, str] = {}
        for record in records:
            class_name = str(record.values.get("type", ""))
            if class_name == "wire":
                continue
            kind_obj = _classify(record)
            segment = _segment(record.name, record.order, duplicates)
            segments[record.order] = segment
            obj_address = f"{address}::{segment}"
            obj_id = ids.object_id(container_id, record.order)
            if kind_obj in (ObjectKind.ANNOTATION, ObjectKind.DECORATION):
                text = record.values.get("Text", record.values.get("LabelText", ""))
                decorations.append(Decoration(
                    id=ids.decoration_id(container_id, record.order),
                    container_id=container_id, address=obj_address,
                    name=record.name, class_name=class_name,
                    obj_type="", order=record.order,
                    points=_points(record.values.get("points")),
                    text=str(text),
                    provenance=Provenance(SourceKind.MODEL_TEXT,
                                          ProvenanceStatus.HYPOTHESIS,
                                          obj_address)))
                continue
            props = {
                key: Property(
                    name=key, value=_render(value), section="model_text",
                    provenance=Provenance(SourceKind.MODEL_TEXT,
                                          ProvenanceStatus.HYPOTHESIS,
                                          obj_address))
                for key, value in record.values.items()
                if key not in _RESERVED
            }
            visual = {}
            portnames = record.values.get("portnames")
            if portnames is not None:
                visual["PortNames"] = Property(
                    name="PortNames", value=str(portnames),
                    section="visual_props",
                    provenance=Provenance(SourceKind.MODEL_TEXT,
                                          ProvenanceStatus.HYPOTHESIS,
                                          obj_address))
            scripts: dict[str, ScriptInfo] = {}
            for key in _SCRIPT_KEYS:
                if key not in record.values:
                    continue
                text = str(record.values[key])
                scripts[key] = ScriptInfo(
                    slot=key, section="model_text", present=bool(text),
                    sha256=hashlib.sha256(text.encode("utf-8")).hexdigest()
                    if text else "", length=len(text),
                    provenance=Provenance(SourceKind.MODEL_TEXT,
                                          ProvenanceStatus.HYPOTHESIS,
                                          obj_address))
            port_items: list[ModelPort] = []
            for (target, direction, text_index), index in sorted(
                    port_index_map.items(), key=lambda item: item[1]):
                if target != obj_id:
                    continue
                port_items.append(ModelPort(
                    id=ids.port_id(obj_id, index), object_id=obj_id,
                    index=index, name="", direction=direction,
                    synthetic=True,
                    fields={"text_index": str(text_index),
                            "text_direction": direction.value},
                    provenance=Provenance(SourceKind.MODEL_TEXT,
                                          ProvenanceStatus.HYPOTHESIS,
                                          obj_address)))
            objects.append(ModelObject(
                id=obj_id, address=obj_address, container_id=container_id,
                name=record.name, class_name=class_name, obj_type="",
                order=record.order, kind=kind_obj,
                points=_points(record.values.get("points")),
                props=props, visual_props=visual, scripts=scripts,
                ports=tuple(port_items),
                uid=str(record.values.get("uid", "")),
                filename=str(record.values.get("filename", "")),
                provenance=Provenance(SourceKind.MODEL_TEXT,
                                      ProvenanceStatus.HYPOTHESIS,
                                      obj_address)))
        wire_ids: dict[str, list[str]] = {}
        for record in records:
            if str(record.values.get("type", "")) == "wire":
                wire_ids.setdefault(record.name, []).append(
                    ids.wire_id(container_id, record.order))
        wires: list[ModelWire] = []
        for record in records:
            if str(record.values.get("type", "")) != "wire":
                continue
            wire_id = ids.wire_id(container_id, record.order)
            name = record.name
            start = self._end(record, "src", object_by_name, wire_ids,
                              port_index_map, container_id, True)
            end = self._end(record, "dst", object_by_name, wire_ids,
                            port_index_map, container_id, False)
            is_branch = start.kind is WireEndKind.BRANCH
            wires.append(ModelWire(
                id=wire_id,
                address=f"{address}::{(name or 'wire')}#{record.order}",
                container_id=container_id, order=record.order, name=name,
                kind=WireKind.BRANCH if is_branch else WireKind.WIRE,
                start=start, end=end,
                branch_parent_id=(start.object_id if is_branch else ""),
                branch_node=(start.port_index if is_branch else -1),
                parent_status=(ProvenanceStatus.HYPOTHESIS if is_branch
                               else ProvenanceStatus.UNKNOWN),
                points=_points(record.values.get("points")),
                provenance=Provenance(SourceKind.MODEL_TEXT,
                                      ProvenanceStatus.HYPOTHESIS,
                                      f"{address}::{name}")))
        child_ids: list[str] = []
        for record in records:
            if not record.subsystem:
                continue
            parent = object_by_name.get(record.name)
            if parent is None:
                continue
            child_address = f"{address}/{segments.get(record.order, record.name)}"
            child_ids.append(self._page(
                {}, record.subsystem, child_address, ContainerKind.SUBMODEL,
                parent, depth + 1))
        object_ids = tuple(item.id for item in objects)
        container = Container(
            id=container_id, address=address, kind=kind,
            name=str(page_props.get("name", "")) or (
                "main" if kind is ContainerKind.PROJECT
                else address.rsplit("/", 1)[-1]),
            order=depth, parent_object_id=parent_object_id,
            props={
                key: Property(
                    name=key, value=_render(value), section="page",
                    provenance=Provenance(SourceKind.MODEL_TEXT,
                                          ProvenanceStatus.HYPOTHESIS,
                                          address))
                for key, value in page_props.items()
                if key != "script"
            },
            script_present="script" in page_props,
            object_ids=object_ids,
            wire_ids=tuple(item.id for item in wires),
            child_container_ids=tuple(child_ids),
            provenance=Provenance(SourceKind.MODEL_TEXT,
                                  ProvenanceStatus.HYPOTHESIS, address))
        if "script" in page_props:
            self.skipped["page_script_temporary"] = (
                self.skipped.get("page_script_temporary", 0) + 1)
        self.containers.append(container)
        self.objects.extend(objects)
        self.wires.extend(wires)
        self.decorations.extend(decorations)
        if depth == 0:
            self.skipped["ports_not_in_text"] = sum(
                1 for item in objects if not item.ports)
        return container_id

    def _end(self, record: _Record, key: str,
             object_by_name: dict[str, str],
             wire_ids: dict[str, list[str]],
             port_index_map: dict[tuple[str, PortDirection, int], int],
             container_id: str, is_start: bool) -> WireEnd:
        raw = record.values.get(key)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            return WireEnd(
                kind=WireEndKind.UNCONNECTED, container_id=container_id,
                resolved=False, reason="unconnected",
                provenance=Provenance(SourceKind.MODEL_TEXT,
                                      ProvenanceStatus.HYPOTHESIS,
                                      f"{container_id}:{record.name}"))
        parsed = _endpoint(raw)
        if parsed is not None:
            name, kind, index = parsed
            expected = "out" if is_start else "in"
            if kind != expected:
                self._discrepancy("wire_direction_mismatch", Severity.WARNING,
                                  record.name,
                                  f"{key}: {kind}, ожидался {expected}")
            obj_id = object_by_name.get(name)
            if obj_id is None:
                self._discrepancy("wire_end_unresolved", Severity.ERROR,
                                  record.name, f"{key}: объект {name} не найден")
                return WireEnd(
                    kind=WireEndKind.UNRESOLVED, object_name=name,
                    port_index=index, container_id=container_id,
                    resolved=False, reason="object_not_found",
                    provenance=Provenance(SourceKind.MODEL_TEXT,
                                          ProvenanceStatus.UNKNOWN,
                                          record.name))
            direction = (PortDirection.OUT if kind == "out"
                         else PortDirection.IN)
            mapped = port_index_map.get((obj_id, direction, index))
            if mapped is None:
                self._discrepancy(
                    "wire_port_out_of_range", Severity.ERROR, record.name,
                    f"{key}: у {name} нет порта {kind}:{index}")
                return WireEnd(
                    kind=WireEndKind.UNRESOLVED, object_id=obj_id,
                    object_name=name, port_index=index,
                    container_id=container_id, resolved=False,
                    reason="port_not_found",
                    provenance=Provenance(SourceKind.MODEL_TEXT,
                                          ProvenanceStatus.UNKNOWN,
                                          record.name))
            return WireEnd(
                kind=WireEndKind.PORT, object_id=obj_id, object_name=name,
                port_index=mapped, container_id=container_id, resolved=True,
                provenance=Provenance(SourceKind.MODEL_TEXT,
                                      ProvenanceStatus.HYPOTHESIS,
                                      record.name))
        if is_start and isinstance(raw, str):
            branch = _BRANCH_RE.match(raw)
            if branch is not None:
                parent_name = branch.group(1)
                node = int(branch.group(2))
                parents = wire_ids.get(parent_name, [])
                if len(parents) == 1:
                    return WireEnd(
                        kind=WireEndKind.BRANCH, object_id=parents[0],
                        object_name=parent_name, port_index=node,
                        container_id=container_id, resolved=True,
                        provenance=Provenance(
                            SourceKind.MODEL_TEXT,
                            ProvenanceStatus.HYPOTHESIS, record.name))
                self._discrepancy(
                    "branch_parent_unresolved", Severity.ERROR, record.name,
                    f"родитель ветви {parent_name!r} не найден или неоднозначен")
                return WireEnd(
                    kind=WireEndKind.UNRESOLVED, object_name=parent_name,
                    port_index=node, container_id=container_id,
                    resolved=False, reason="branch_parent_not_found",
                    provenance=Provenance(SourceKind.MODEL_TEXT,
                                          ProvenanceStatus.UNKNOWN,
                                          record.name))
        self._discrepancy("wire_end_unresolved", Severity.ERROR, record.name,
                          f"{key}: адрес {raw!r} не разобран")
        return WireEnd(
            kind=WireEndKind.UNRESOLVED, object_name=str(raw),
            container_id=container_id, resolved=False, reason="bad_endpoint",
            provenance=Provenance(SourceKind.MODEL_TEXT,
                                  ProvenanceStatus.UNKNOWN, record.name))


def _count_records(records: list[_Record]) -> tuple[int, int]:
    objects = 0
    wires = 0
    for record in records:
        if str(record.values.get("type", "")) == "wire":
            wires += 1
        else:
            objects += 1
        child_objects, child_wires = _count_records(record.subsystem)
        objects += child_objects
        wires += child_wires
    return objects, wires


def parse_model_text(text: str, *, source_name: str = "",
                     limits: Limits | None = None) -> ModelIR:
    """Разобрать текст `savemodeltofile` в частичный Model IR."""
    limits = limits or Limits()
    raw = text.lstrip("﻿")
    encoded = raw.encode("utf-8")
    if len(encoded) > limits.max_bytes:
        raise ModelIRLimitError(
            f"размер текста {len(encoded)} больше предела {limits.max_bytes}")
    parser = _Parser(_Stream(raw))
    page_props, records = parser.document()
    objects, wires = _count_records(records)
    if objects > limits.max_objects:
        raise ModelIRLimitError("объектов в тексте больше предела")
    if wires > limits.max_wires:
        raise ModelIRLimitError("проводов в тексте больше предела")
    builder = _Builder(hashlib.sha256(encoded).hexdigest(), source_name,
                       limits)
    return builder.build(page_props, records)
