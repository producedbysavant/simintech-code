"""Сборка Model IR из нескольких источников и расхождения между ними.

`.xprt` первичен. Текст модели и протокол топологии не подменяют его поля
молча: найденное расхождение остаётся `Discrepancy` с обоими источниками,
а `strict` превращает структурные ошибки в отказ.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from . import ids
from .codes import (
    ContainerKind,
    Severity,
    SourceKind,
    SourceStatus,
    WireEndKind,
)
from .errors import ModelIRConflictError
from .ir import (
    Container,
    Discrepancy,
    ModelIR,
    ModelMeta,
    ModelObject,
)

_ORDER = (SourceKind.XPRT, SourceKind.MODEL_TEXT, SourceKind.TOPOLOGY)


def _objects_in(model: ModelIR, container: Container) -> list[ModelObject]:
    return [item for item in model.objects
            if item.container_id == container.id]


def _names(objects: Iterable[ModelObject]) -> set[str]:
    return {item.name for item in objects if item.name}


def _find_scope(base: ModelIR, names: set[str]) -> Container | None:
    if not names:
        return None
    candidates = [
        container for container in base.containers
        if names <= _names(_objects_in(base, container))
    ]
    return candidates[0] if len(candidates) == 1 else None


def _main_container(model: ModelIR) -> Container | None:
    return next((item for item in model.containers
                 if item.kind is ContainerKind.PROJECT), None)


def _text_port_index(objects: dict[str, ModelObject], name: str,
                     port_index: int) -> int:
    obj = objects.get(name)
    if obj is None:
        return port_index
    port = obj.port(port_index)
    if port is None:
        return port_index
    text = port.fields.get("text_index")
    return int(text) if text is not None else port_index


def _direct_edges(model: ModelIR, container: Container,
                  objects: dict[str, ModelObject],
                  text_index: bool) -> set[tuple[str, int, str, int]]:
    result: set[tuple[str, int, str, int]] = set()
    for wire in model.wires:
        if wire.container_id != container.id:
            continue
        if (wire.start.kind is not WireEndKind.PORT
                or wire.end.kind is not WireEndKind.PORT):
            continue
        start = wire.start.object_name
        end = wire.end.object_name
        start_index = (_text_port_index(objects, start, wire.start.port_index)
                       if text_index else wire.start.port_index)
        end_index = (_text_port_index(objects, end, wire.end.port_index)
                     if text_index else wire.end.port_index)
        result.add((start, start_index, end, end_index))
    return result


def _compare_text(base: ModelIR, text: ModelIR) -> list[Discrepancy]:
    added: list[Discrepancy] = []
    text_root = _main_container(text)
    if text_root is None:
        return [Discrepancy(
            code="source_scope_unmatched", severity=Severity.ERROR,
            subject="model_text", detail="в тексте нет главного контейнера",
            sources=("model_text",))]
    text_objects = _objects_in(text, text_root)
    scope = _find_scope(base, _names(text_objects))
    if scope is None:
        added.append(Discrepancy(
            code="source_scope_unmatched", severity=Severity.ERROR,
            subject="model_text",
            detail="набор имён текста не совпал ровно с одним контейнером",
            sources=("xprt", "model_text")))
        scope = _main_container(base)
    if scope is None:
        return added
    base_objects = _objects_in(base, scope)
    base_by_name = {item.name: item for item in base_objects if item.name}
    text_by_name = {item.name: item for item in text_objects if item.name}
    for name, obj in text_by_name.items():
        other = base_by_name.get(name)
        if other is None:
            added.append(Discrepancy(
                code="object_missing_in_source", severity=Severity.ERROR,
                subject=f"{scope.address}::{name}",
                detail="объект есть в тексте, но отсутствует в .xprt",
                sources=("model_text", "xprt")))
            continue
        if obj.class_name != other.class_name:
            added.append(Discrepancy(
                code="class_mismatch", severity=Severity.ERROR,
                subject=f"{scope.address}::{name}",
                detail=f"text={obj.class_name!r}, xprt={other.class_name!r}",
                sources=("model_text", "xprt")))
        for label in ("in", "out"):
            text_count = sum(1 for port in obj.ports
                             if port.direction.value == label)
            base_count = sum(1 for port in other.ports
                             if port.direction.value == label)
            if text_count != base_count:
                added.append(Discrepancy(
                    code=("port_missing_in_source" if text_count < base_count
                          else "port_extra_in_source"),
                    severity=Severity.WARNING,
                    subject=f"{scope.address}::{name}",
                    detail=f"портов {label}: text={text_count}, "
                           f"xprt={base_count}",
                    sources=("model_text", "xprt")))
    for name in sorted(set(base_by_name) - set(text_by_name)):
        added.append(Discrepancy(
            code="object_extra_in_source", severity=Severity.ERROR,
            subject=f"{scope.address}::{name}",
            detail="объект есть в .xprt, но отсутствует в тексте",
            sources=("xprt", "model_text")))
    base_edges = _direct_edges(base, scope, base_by_name, False)
    text_edges = _direct_edges(text, text_root, text_by_name, True)
    for edge in sorted(base_edges - text_edges):
        added.append(Discrepancy(
            code="wire_missing_in_source", severity=Severity.ERROR,
            subject=f"{scope.address}::{edge[0]}->{edge[2]}",
            detail=f"провод {edge[0]}:out:{edge[1]} -> "
                   f"{edge[2]}:in:{edge[3]} отсутствует в тексте",
            sources=("xprt", "model_text")))
    for edge in sorted(text_edges - base_edges):
        added.append(Discrepancy(
            code="wire_extra_in_source", severity=Severity.ERROR,
            subject=f"{scope.address}::{edge[0]}->{edge[2]}",
            detail=f"провод {edge[0]}:out:{edge[1]} -> "
                   f"{edge[2]}:in:{edge[3]} отсутствует в .xprt",
            sources=("model_text", "xprt")))
    base_branches = sum(1 for wire in base.wires
                        if wire.container_id == scope.id
                        and wire.start.kind is WireEndKind.BRANCH)
    text_branches = sum(1 for wire in text.wires
                        if wire.container_id == text_root.id
                        and wire.start.kind is WireEndKind.BRANCH)
    if base_branches != text_branches:
        added.append(Discrepancy(
            code="wire_end_conflict", severity=Severity.ERROR,
            subject=scope.address,
            detail=f"ветвей: xprt={base_branches}, text={text_branches}",
            sources=("xprt", "model_text")))
    return added


def _topology_edges(model: ModelIR,
                    container: Container) -> set[tuple[str, int, str, int]]:
    result: set[tuple[str, int, str, int]] = set()
    for wire in model.wires:
        if wire.container_id != container.id:
            continue
        if (wire.start.kind is not WireEndKind.PORT
                or wire.end.kind is not WireEndKind.PORT):
            continue
        first = (wire.start.object_name, wire.start.port_index)
        second = (wire.end.object_name, wire.end.port_index)
        result.add((first[0], first[1], second[0], second[1]))
    return result


def _compare_topology(base: ModelIR, topology: ModelIR) -> list[Discrepancy]:
    added: list[Discrepancy] = []
    root = _main_container(topology)
    if root is None:
        return added
    names = _names(_objects_in(topology, root))
    scope = _find_scope(base, names)
    if scope is None:
        added.append(Discrepancy(
            code="source_scope_unmatched", severity=Severity.WARNING,
            subject="topology",
            detail="набор имён топологии не совпал ровно с одним "
                   "контейнером",
            sources=("xprt", "topology")))
        scope = _main_container(base)
    if scope is None:
        return added
    added.append(Discrepancy(
        code="topology_scope_limited", severity=Severity.INFO,
        subject=scope.address,
        detail="топология даёт связность без формы линии и ветвей",
        sources=("topology",)))
    base_edges = _topology_edges(base, scope)
    topo_edges = _topology_edges(topology, root)
    normalized_base = {tuple(sorted(((a, b), (c, d))))
                       for a, b, c, d in base_edges}
    normalized_topo = {tuple(sorted(((a, b), (c, d))))
                       for a, b, c, d in topo_edges}
    for edge in normalized_base - normalized_topo:
        added.append(Discrepancy(
            code="wire_missing_in_source", severity=Severity.WARNING,
            subject=scope.address,
            detail=f"связь {edge} отсутствует в топологии",
            sources=("xprt", "topology")))
    for edge in normalized_topo - normalized_base:
        added.append(Discrepancy(
            code="wire_extra_in_source", severity=Severity.WARNING,
            subject=scope.address,
            detail=f"связь {edge} отсутствует в .xprt",
            sources=("topology", "xprt")))
    return added


def _merge_meta(base: ModelIR, sources: list[ModelIR]) -> ModelMeta:
    source_set: list[SourceKind] = []
    hashes: dict[str, str] = {}
    for source in sources:
        for kind in source.meta.source_set:
            if kind not in source_set:
                source_set.append(kind)
        hashes.update(source.meta.source_hashes)
    source_set.sort(key=_ORDER.index)
    return replace(base.meta, source_set=tuple(source_set),
                   source_hashes=hashes, structure_hash="",
                   content_hash="")


def build_model_ir(*, xprt: ModelIR | None = None,
                   text: ModelIR | None = None,
                   topology: ModelIR | None = None,
                   strict: bool = False) -> ModelIR:
    """Собрать IR из источников; `.xprt` первичен, остальные сверяются."""
    sources = [item for item in (xprt, text, topology) if item is not None]
    if not sources:
        raise ModelIRConflictError(
            "нет ни одного источника: нужен .xprt, текст модели или топология")
    base = xprt or text or topology
    assert base is not None
    added: list[Discrepancy] = []
    if xprt is not None and text is not None:
        added.extend(_compare_text(xprt, text))
    if xprt is not None and topology is not None:
        added.extend(_compare_topology(xprt, topology))
    if xprt is None and text is not None and topology is not None:
        added.extend(_compare_topology(text, topology))
    errors = [item for item in added if item.severity is Severity.ERROR]
    if strict and errors:
        codes = ", ".join(sorted({item.code for item in errors}))
        raise ModelIRConflictError(
            f"источники расходятся: {codes}")
    discrepancies = base.discrepancies + tuple(added)
    counts: dict[str, int] = {}
    for item in discrepancies:
        counts[item.code] = counts.get(item.code, 0) + 1
    coverage = replace(
        base.coverage, discrepancy_counts=counts,
        source_status=(SourceStatus.PARTIAL if added
                       else base.coverage.source_status))
    meta = _merge_meta(base, sources)
    model = replace(base, meta=meta, discrepancies=discrepancies,
                    coverage=coverage)
    meta = replace(meta, structure_hash=ids.structure_hash(model),
                   content_hash=ids.content_hash(model))
    return replace(model, meta=meta)
