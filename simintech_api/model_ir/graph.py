"""Графовые запросы к полному Model IR.

Индексы строятся один раз на модель. Запросы возвращают результат с
доказательством: область, хеш модели, покрытие, неизвестные и признак
усечения. Пустой ответ и неизвестность не смешиваются.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from . import ids
from .codes import (
    ObjectKind,
    PortDirection,
    SourceStatus,
    WireEndKind,
    WireKind,
)
from .errors import ModelQueryError
from .ir import (
    Container,
    Coverage,
    Discrepancy,
    ModelIR,
    ModelObject,
    ModelPort,
    ModelWire,
)

_MAX_ITEMS = 200


@dataclass(frozen=True, slots=True)
class SignalEdge:
    src: str
    dst: str
    wire_id: str
    kind: str


@dataclass(frozen=True, slots=True)
class QueryResult:
    query: str
    scope: str
    model_hash: str
    items: tuple[dict[str, Any], ...] = ()
    unknown: tuple[str, ...] = ()
    truncated: bool = False
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "scope": self.scope,
            "model_hash": self.model_hash,
            "items": list(self.items),
            "unknown": list(self.unknown),
            "truncated": self.truncated,
            "evidence": dict(self.evidence),
        }


def coverage_dict(coverage: Coverage) -> dict[str, Any]:
    return {
        "containers": coverage.containers,
        "objects": coverage.objects,
        "ports_real": coverage.ports_real,
        "ports_synthetic": coverage.ports_synthetic,
        "wires": coverage.wires,
        "branches": coverage.branches,
        "decorations": coverage.decorations,
        "block_image_pages": coverage.block_image_pages,
        "block_image_objects": coverage.block_image_objects,
        "unresolved_ends": coverage.unresolved_ends,
        "unconnected_ends": coverage.unconnected_ends,
        "unresolved_branches": coverage.unresolved_branches,
        "unknown_object_types": coverage.unknown_object_types,
        "external_submodels": coverage.external_submodels,
        "source_status": coverage.source_status.value,
        "skipped": dict(coverage.skipped),
        "discrepancy_counts": dict(coverage.discrepancy_counts),
    }


def discrepancy_dict(item: Discrepancy) -> dict[str, Any]:
    return {
        "code": item.code,
        "severity": item.severity.value,
        "subject": item.subject,
        "detail": item.detail,
        "sources": list(item.sources),
        "alternatives": list(item.alternatives),
    }


def _port_id(obj: ModelObject, index: int) -> str | None:
    port = obj.port(index)
    return port.id if port is not None else None


class ModelIndex:
    """Индексы и граф сигналов полной модели."""

    def __init__(self, model: ModelIR) -> None:
        self.model = model
        self.containers: dict[str, Container] = {
            item.id: item for item in model.containers}
        self.objects: dict[str, ModelObject] = {
            item.id: item for item in model.objects}
        self.by_address: dict[str, ModelObject] = {
            item.address: item for item in model.objects}
        self.by_name: dict[str, list[ModelObject]] = {}
        for obj in model.objects:
            self.by_name.setdefault(obj.name, []).append(obj)
        self.ports: dict[str, ModelPort] = {
            port.id: port for obj in model.objects for port in obj.ports}
        self.wires: dict[str, ModelWire] = {
            wire.id: wire for wire in model.wires}
        self.wires_by_name: dict[str, list[ModelWire]] = {}
        for wire in model.wires:
            self.wires_by_name.setdefault(wire.name, []).append(wire)
        grouped_objects: dict[str, list[ModelObject]] = {}
        for obj in model.objects:
            grouped_objects.setdefault(obj.container_id, []).append(obj)
        self.objects_in: dict[str, tuple[ModelObject, ...]] = {
            key: tuple(value) for key, value in grouped_objects.items()}
        grouped_wires: dict[str, list[ModelWire]] = {}
        for wire in model.wires:
            grouped_wires.setdefault(wire.container_id, []).append(wire)
        self.wires_in: dict[str, tuple[ModelWire, ...]] = {
            key: tuple(value) for key, value in grouped_wires.items()}
        self.signal: dict[str, list[SignalEdge]] = {}
        self.reverse: dict[str, list[SignalEdge]] = {}
        self.unknown: list[str] = []
        self._build_edges()

    # ─── Поиск адресатов ───────────────────────────────────────────

    def object(self, ref: str) -> ModelObject:
        if ref in self.objects:
            return self.objects[ref]
        if ref in self.by_address:
            return self.by_address[ref]
        found = self.by_name.get(ref) or []
        if len(found) == 1:
            return found[0]
        if len(found) > 1:
            candidates = ", ".join(item.address for item in found)
            raise ModelQueryError(
                f"имя {ref!r} неоднозначно: {candidates}")
        raise ModelQueryError(f"объект {ref!r} не найден")

    def port(self, ref: str) -> ModelPort:
        if ref in self.ports:
            return self.ports[ref]
        if ":" not in ref:
            raise ModelQueryError(
                f"порт {ref!r}: ожидается объект:индекс")
        name, raw_index = ref.rsplit(":", 1)
        try:
            index = int(raw_index)
        except ValueError as exc:
            raise ModelQueryError(
                f"порт {ref!r}: индекс не число") from exc
        obj = self.object(name)
        port = obj.port(index)
        if port is None:
            raise ModelQueryError(
                f"у {obj.address} нет порта {index}")
        return port

    def wire(self, ref: str) -> ModelWire:
        if ref in self.wires:
            return self.wires[ref]
        found = [item for item in self.wires.values()
                 if item.address == ref]
        if len(found) == 1:
            return found[0]
        named = self.wires_by_name.get(ref) or []
        if len(named) == 1:
            return named[0]
        if len(named) > 1:
            candidates = ", ".join(item.address for item in named)
            raise ModelQueryError(
                f"имя провода {ref!r} неоднозначно: {candidates}")
        raise ModelQueryError(f"провод {ref!r} не найден")

    # ─── Построение графа ─────────────────────────────────────────

    def _source_port(self, wire: ModelWire,
                     seen: set[str] | None = None) -> str | None:
        seen = seen or set()
        if wire.id in seen:
            return None
        seen.add(wire.id)
        if wire.start.kind is WireEndKind.PORT:
            obj = self.objects.get(wire.start.object_id)
            if obj is None:
                return None
            return _port_id(obj, wire.start.port_index)
        if wire.start.kind is WireEndKind.BRANCH and wire.branch_parent_id:
            parent = self.wires.get(wire.branch_parent_id)
            return self._source_port(parent, seen) if parent else None
        return None

    def _sink_port(self, wire: ModelWire) -> str | None:
        if wire.end.kind is not WireEndKind.PORT:
            return None
        obj = self.objects.get(wire.end.object_id)
        if obj is None:
            return None
        return _port_id(obj, wire.end.port_index)

    def _add_edge(self, edge: SignalEdge) -> None:
        self.signal.setdefault(edge.src, []).append(edge)
        self.reverse.setdefault(edge.dst, []).append(edge)

    def _build_edges(self) -> None:
        for wire in self.model.wires:
            source = self._source_port(wire)
            sink = self._sink_port(wire)
            if source is not None and sink is not None:
                self._add_edge(SignalEdge(
                    source, sink, wire.id,
                    "branch" if wire.kind is WireKind.BRANCH else "wire"))
            elif wire.start.kind is WireEndKind.UNRESOLVED:
                self.unknown.append(
                    f"{wire.address}: начало не разрешено")
            elif wire.end.kind is WireEndKind.UNRESOLVED:
                self.unknown.append(
                    f"{wire.address}: конец не разрешён")
        for boundary in self.model.boundaries:
            if not boundary.resolved:
                self.unknown.append(
                    f"{boundary.id}: граница субмодели не разрешена")
                continue
            submodel = self.objects.get(boundary.submodel_object_id)
            external = (next(
                (port for port in submodel.ports
                 if port.index == boundary.external_port_index), None)
                if submodel is not None else None)
            internal = self.ports.get(ids.port_id(
                boundary.internal_object_id, boundary.internal_port_index))
            if external is None or internal is None:
                self.unknown.append(
                    f"{boundary.id}: порт границы не найден")
                continue
            if external.direction in (PortDirection.IN,
                                      PortDirection.UNDIRECTED):
                self._add_edge(SignalEdge(
                    external.id, internal.id, boundary.id, "boundary"))
            if external.direction in (PortDirection.OUT,
                                      PortDirection.UNDIRECTED):
                self._add_edge(SignalEdge(
                    internal.id, external.id, boundary.id, "boundary"))
        for link in self.model.memory_links:
            if not link.resolved:
                self.unknown.append(
                    f"{link.id}: ячейка памяти не разрешена")
            for writer in link.writers:
                for reader in link.readers:
                    src = self._memory_port(writer)
                    dst = self._memory_port(reader)
                    if src is not None and dst is not None:
                        self._add_edge(SignalEdge(
                            src, dst, link.id, "memory"))
        # Внутри обычного блока сигнал идёт от входов к выходам. Граница
        # субмодели уже описана отдельными рёбрами и здесь не дублируется.
        for obj in self.model.objects:
            if obj.kind not in (ObjectKind.BLOCK, ObjectKind.UNKNOWN):
                continue
            inputs = [port.id for port in obj.ports
                      if port.direction in (PortDirection.IN,
                                            PortDirection.UNDIRECTED)]
            outputs = [port.id for port in obj.ports
                       if port.direction in (PortDirection.OUT,
                                             PortDirection.UNDIRECTED)]
            for source in inputs:
                for sink in outputs:
                    if source != sink:
                        self._add_edge(SignalEdge(
                            source, sink, f"block:{obj.id}", "block"))

    def _memory_port(self, address: str) -> str | None:
        name, _, raw_index = address.rpartition(":")
        try:
            index = int(raw_index)
        except ValueError:
            return None
        obj = self.by_address.get(name)
        if obj is None:
            return None
        return _port_id(obj, index)

    # ─── Общие помощники ──────────────────────────────────────────

    def node_name(self, port_id: str) -> str:
        port = self.ports.get(port_id)
        if port is None:
            return port_id
        obj = self.objects.get(port.object_id)
        return f"{obj.address}:{port.index}" if obj else port_id

    def node_object(self, port_id: str) -> ModelObject | None:
        port = self.ports.get(port_id)
        return self.objects.get(port.object_id) if port else None

    def _result(self, query: str, items: Iterable[dict[str, Any]],
                unknown: Iterable[str] = (), truncated: bool = False,
                scope: str = "full_model") -> QueryResult:
        item_list = list(items)
        unknown_list = list(unknown)
        truncated = (truncated or len(item_list) > _MAX_ITEMS
                     or len(unknown_list) > _MAX_ITEMS)
        return QueryResult(
            query=query, scope=scope, model_hash=self.model.meta.structure_hash,
            items=tuple(item_list[:_MAX_ITEMS]),
            unknown=tuple(unknown_list[:_MAX_ITEMS]),
            truncated=truncated,
            evidence={"coverage": coverage_dict(self.model.coverage),
                      "sources": [kind.value for kind in
                                  self.model.meta.source_set]})

    def _walk(self, starts: list[str], forward: bool, max_depth: int,
              query: str) -> QueryResult:
        items: list[dict[str, Any]] = []
        unknown: list[str] = list(self.unknown)
        truncated = False
        queue = [(node, 0) for node in starts]
        visited = set(starts)
        while queue:
            node, depth = queue.pop(0)
            if depth > max_depth:
                continue
            edges = ((self.signal.get(node, ())
                      if forward else self.reverse.get(node, ())))
            obj = self.node_object(node)
            items.append({
                "node": self.node_name(node),
                "object": obj.name if obj else "",
                "address": obj.address if obj else "",
                "port": self.ports[node].index if node in self.ports else -1,
                "depth": depth,
            })
            if len(items) >= _MAX_ITEMS:
                truncated = True
                break
            for edge in edges:
                peer = edge.dst if forward else edge.src
                if peer in visited:
                    continue
                visited.add(peer)
                queue.append((peer, depth + 1))
        return self._result(query, items, unknown, truncated)

    def _start_nodes(self, ref: str, forward: bool) -> list[str]:
        matches = [item for item in self.model.memory_links
                   if item.variable == ref]
        if matches:
            result: list[str] = []
            for link in matches:
                addresses = link.writers if forward else link.readers
                for address in addresses:
                    port = self._memory_port(address)
                    if port is not None:
                        result.append(port)
            return result
        try:
            wire = self.wire(ref)
        except ModelQueryError:
            wire = None
        if wire is not None:
            result = []
            source = self._source_port(wire)
            sink = self._sink_port(wire)
            if source is not None:
                result.append(source)
            if sink is not None:
                result.append(sink)
            return result
        try:
            port_obj = self.port(ref)
        except ModelQueryError:
            port_obj = None
        if port_obj is not None:
            return [port_obj.id]
        obj = self.object(ref)
        return [item.id for item in obj.ports]

    # ─── Запросы ─────────────────────────────────────────────────

    def inspect_node(self, node: str) -> QueryResult:
        obj = self.by_address.get(node)
        if obj is None:
            try:
                obj = self.object(node)
            except ModelQueryError:
                port = self.port(node)
                obj = self.objects[port.object_id]
        wires = [item for item in self.model.wires
                 if item.start.object_id == obj.id
                 or item.end.object_id == obj.id]
        ports = [
            {"index": port.index, "name": port.name,
             "direction": port.direction.value}
            for port in obj.ports]
        truncated = (len(ports) > _MAX_ITEMS or len(wires) > _MAX_ITEMS)
        return self._result("inspect_node", [{
            "address": obj.address,
            "name": obj.name,
            "class_name": obj.class_name,
            "obj_type": obj.obj_type,
            "kind": obj.kind.value,
            "container": self.containers[obj.container_id].address
            if obj.container_id in self.containers else "",
            "ports": ports[:_MAX_ITEMS],
            "ports_total": len(ports),
            "wires": [item.address for item in wires[:_MAX_ITEMS]],
            "wires_total": len(wires),
            "uid": obj.uid,
            "filename": obj.filename,
        }], truncated=truncated)

    def find_objects(self, query: str = "", class_name: str = "",
                     kind: str = "", limit: int = 50) -> QueryResult:
        needle = query.lower()
        found = [
            item for item in self.model.objects
            if (not needle
                or needle in item.name.lower()
                or needle in item.address.lower()
                or needle in item.class_name.lower())
            and (not class_name or item.class_name == class_name)
            and (not kind or item.kind.value == kind)
        ]
        found.sort(key=lambda item: item.address)
        truncated = len(found) > limit
        items = [{"address": item.address, "name": item.name,
                  "class_name": item.class_name, "kind": item.kind.value,
                  "container": self.containers[item.container_id].address
                  if item.container_id in self.containers else ""}
                 for item in found[:limit]]
        return self._result("find_objects", items, truncated=truncated)

    def trace_signal(self, signal: str, direction: str = "forward",
                     max_depth: int = 64) -> QueryResult:
        if direction not in ("forward", "backward", "both"):
            raise ModelQueryError(
                f"direction={direction!r}: ожидается forward, backward или both")
        starts = self._start_nodes(signal, direction != "backward")
        items: list[dict[str, Any]] = []
        unknown: list[str] = []
        truncated = False
        if direction in ("forward", "both"):
            forward = self._walk(starts, True, max_depth, "trace_signal")
            items.extend(forward.items)
            unknown.extend(forward.unknown)
            truncated = truncated or forward.truncated
        if direction in ("backward", "both"):
            backward = self._walk(starts, False, max_depth, "trace_signal")
            items.extend(backward.items)
            unknown.extend(backward.unknown)
            truncated = truncated or backward.truncated
        return self._result("trace_signal", items, unknown, truncated)

    def _object_walk(self, ref: str, forward: bool,
                     max_depth: int) -> list[dict[str, Any]]:
        obj = self.object(ref)
        queue = [(obj, 0)]
        visited = {obj.id}
        result: list[dict[str, Any]] = []
        while queue:
            current, depth = queue.pop(0)
            if depth > max_depth:
                continue
            result.append({"address": current.address, "name": current.name,
                           "depth": depth})
            for port in current.ports:
                edges = (self.signal.get(port.id, ()) if forward
                         else self.reverse.get(port.id, ()))
                for edge in edges:
                    peer_id = edge.dst if forward else edge.src
                    peer = self.node_object(peer_id)
                    if peer is None or peer.id in visited:
                        continue
                    visited.add(peer.id)
                    queue.append((peer, depth + 1))
        return result

    def ancestors(self, ref: str, max_depth: int = 64) -> QueryResult:
        return self._result(
            "ancestors", self._object_walk(ref, False, max_depth))

    def descendants(self, ref: str, max_depth: int = 64) -> QueryResult:
        return self._result(
            "descendants", self._object_walk(ref, True, max_depth))

    def find_path(self, src: str, dst: str,
                  max_length: int = 32) -> QueryResult:
        start = self.object(src)
        target = self.object(dst)
        queue = [(start, [start.address])]
        visited = {start.id}
        while queue:
            current, path = queue.pop(0)
            if current.id == target.id:
                return self._result(
                    "find_path", [{"path": path, "length": len(path) - 1}])
            if len(path) - 1 >= max_length:
                continue
            for port in current.ports:
                for edge in self.signal.get(port.id, ()):
                    peer = self.node_object(edge.dst)
                    if peer is None or peer.id in visited:
                        continue
                    visited.add(peer.id)
                    queue.append((peer, path + [peer.address]))
        return self._result(
            "find_path", (),
            unknown=(f"путь {start.address} -> {target.address} не найден",))

    def find_cycles(self, max_cycles: int = 20) -> QueryResult:
        graph: dict[str, set[str]] = {}
        for edge in (item for edges in self.signal.values() for item in edges):
            src = self.node_object(edge.src)
            dst = self.node_object(edge.dst)
            if src is None or dst is None:
                continue
            # Внутреннее ребро блока вход -> выход не является обратной
            # связью: на уровне объектов это петля того же блока. Настоящая
            # петля провода остаётся в графе и будет найдена.
            if src.id == dst.id and edge.kind == "block":
                continue
            graph.setdefault(src.id, set()).add(dst.id)
        index = 0
        stack: list[str] = []
        on_stack: set[str] = set()
        indices: dict[str, int] = {}
        low: dict[str, int] = {}
        cycles: list[list[str]] = []

        # Итеративный Tarjan: рекурсивный падал RecursionError на цепочке
        # из 1200 объектов, то есть отказ уходил мимо ModelQueryError.
        for start in sorted(graph):
            if start in indices:
                continue
            work: list[tuple[str, int]] = [(start, 0)]
            while work:
                node, position = work[-1]
                if position == 0:
                    indices[node] = index
                    low[node] = index
                    index += 1
                    stack.append(node)
                    on_stack.add(node)
                peers = sorted(graph.get(node, ()))
                if position < len(peers):
                    peer = peers[position]
                    work[-1] = (node, position + 1)
                    if peer not in indices:
                        work.append((peer, 0))
                    elif peer in on_stack:
                        low[node] = min(low[node], indices[peer])
                    continue
                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[node])
                if low[node] != indices[node]:
                    continue
                component: list[str] = []
                while True:
                    item = stack.pop()
                    on_stack.discard(item)
                    component.append(item)
                    if item == node:
                        break
                component.sort()
                if len(component) > 1 or node in graph.get(node, ()):
                    cycles.append(component)
        cycles.sort(key=lambda item: (-len(item), item))
        items = [
            {"objects": [self.objects[item].address for item in cycle]}
            for cycle in cycles[:max_cycles]
        ]
        return self._result("find_cycles", items,
                            truncated=len(cycles) > max_cycles)

    def check_connections(self) -> QueryResult:
        violations: list[dict[str, Any]] = []
        for obj in self.model.objects:
            for port in obj.ports:
                incoming = len(self.reverse.get(port.id, ()))
                outgoing = len(self.signal.get(port.id, ()))
                if port.direction is PortDirection.IN and incoming == 0:
                    violations.append({
                        "code": "unconnected_input",
                        "severity": "warning",
                        "subject": f"{obj.address}:{port.index}",
                        "detail": "вход без источника",
                    })
                if port.direction is PortDirection.OUT and outgoing == 0:
                    violations.append({
                        "code": "unconnected_output",
                        "severity": "info",
                        "subject": f"{obj.address}:{port.index}",
                        "detail": "выход без потребителя",
                    })
                if incoming > 1:
                    violations.append({
                        "code": "multiple_drivers",
                        "severity": "warning",
                        "subject": f"{obj.address}:{port.index}",
                        "detail": f"вход принимает {incoming} источников",
                    })
        for wire in self.model.wires:
            if wire.start.kind is WireEndKind.UNRESOLVED:
                violations.append({
                    "code": "wire_end_unresolved", "severity": "error",
                    "subject": wire.address, "detail": "начало не разрешено"})
            if wire.end.kind is WireEndKind.UNRESOLVED:
                violations.append({
                    "code": "wire_end_unresolved", "severity": "error",
                    "subject": wire.address, "detail": "конец не разрешён"})
        for disc in self.model.discrepancies:
            violations.append(discrepancy_dict(disc))
        seen: set[tuple[str, str, str]] = set()
        unique: list[dict[str, Any]] = []
        for violation in violations:
            key = (str(violation.get("code")),
                   str(violation.get("subject")),
                   str(violation.get("detail")))
            if key in seen:
                continue
            seen.add(key)
            unique.append(violation)
        errors = [item for item in unique
                  if item.get("severity") == "error"]
        partial = self.model.coverage.source_status is not SourceStatus.OK
        status = "fail" if errors else ("partial" if partial else "pass")
        evidence = {
            "status": status,
            "checked_objects": len(self.model.objects),
            "checked_ports": len(self.ports),
            "checked_connections": len(self.model.wires),
            "violations_total": len(unique),
            "unconnected_inputs": sum(
                1 for item in unique
                if item.get("code") == "unconnected_input"),
            "coverage": coverage_dict(self.model.coverage),
        }
        return QueryResult(
            query="check_connections", scope="full_model",
            model_hash=self.model.meta.structure_hash,
            items=tuple(unique[:_MAX_ITEMS]),
            truncated=len(unique) > _MAX_ITEMS,
            evidence=evidence)

    def validate_invariants(
            self, invariants: Iterable[dict[str, Any]]) -> QueryResult:
        results: list[dict[str, Any]] = []
        for invariant in invariants:
            kind = str(invariant.get("kind", ""))
            ident = str(invariant.get("id", kind))
            if kind == "required_inputs_connected":
                check = self.check_connections()
                failed = int(check.evidence.get(
                    "unconnected_inputs",
                    sum(1 for item in check.items
                        if item.get("code") == "unconnected_input")))
                results.append({
                    "id": ident, "kind": kind,
                    "status": "failed" if failed else "passed",
                    "detail": f"входов без источника: {failed}"})
            elif kind == "no_self_loops":
                loops = [wire.address for wire in self.model.wires
                         if wire.start.object_id
                         and wire.start.object_id == wire.end.object_id
                         and wire.start.port_index == wire.end.port_index]
                results.append({
                    "id": ident, "kind": kind,
                    "status": "failed" if loops else "passed",
                    "detail": f"самопетель: {len(loops)}"})
            elif kind == "unique_object_names":
                duplicates = [
                    name for name, items in self.by_name.items()
                    if len(items) > 1]
                results.append({
                    "id": ident, "kind": kind,
                    "status": "failed" if duplicates else "passed",
                    "detail": f"повторов имён: {len(duplicates)}"})
            elif kind == "memory_pair_complete":
                broken = [link.variable for link in self.model.memory_links
                          if not link.resolved]
                results.append({
                    "id": ident, "kind": kind,
                    "status": "failed" if broken else "passed",
                    "detail": f"непарных ячеек: {len(broken)}"})
            elif kind == "no_dangling_wires":
                dangling = [wire.address for wire in self.model.wires
                            if wire.start.kind in (WireEndKind.UNRESOLVED,
                                                   WireEndKind.UNCONNECTED)
                            or wire.end.kind in (WireEndKind.UNRESOLVED,
                                                 WireEndKind.UNCONNECTED)]
                results.append({
                    "id": ident, "kind": kind,
                    "status": "failed" if dangling else "passed",
                    "detail": f"оборванных проводов: {len(dangling)}"})
            elif kind == "max_fanout":
                limit = int(invariant.get("max", 1))
                fans = {
                    f"{obj.address}:{port.index}": len(
                        self.signal.get(port.id, ()))
                    for obj in self.model.objects for port in obj.ports
                    if len(self.signal.get(port.id, ())) > limit
                }
                results.append({
                    "id": ident, "kind": kind,
                    "status": "failed" if fans else "passed",
                    "detail": f"превышений: {len(fans)}"})
            elif kind == "container_depth":
                limit = int(invariant.get("max", 8))
                depth = max((self._depth(item) for item in self.model.containers),
                            default=0)
                results.append({
                    "id": ident, "kind": kind,
                    "status": "passed" if depth <= limit else "failed",
                    "detail": f"глубина: {depth}"})
            elif kind == "contract_ports_match":
                results.append({
                    "id": ident, "kind": kind, "status": "not_evaluated",
                    "detail": "реестр контрактов появится в C4"})
            else:
                results.append({
                    "id": ident, "kind": kind, "status": "not_evaluated",
                    "detail": f"неизвестный инвариант {kind!r}"})
        return self._result("validate_invariants", results)

    def _depth(self, container: Container) -> int:
        depth = 0
        current = container
        seen: set[str] = set()
        while current.parent_object_id and current.id not in seen:
            seen.add(current.id)
            obj = self.objects.get(current.parent_object_id)
            if obj is None:
                break
            parent = self.containers.get(obj.container_id)
            if parent is None:
                break
            current = parent
            depth += 1
        return depth

    def compare_models(self, other: ModelIR,
                       include_geometry: bool = False) -> QueryResult:
        other_index = ModelIndex(other)
        left = {item.address: item for item in self.model.objects}
        right = {item.address: item for item in other_index.model.objects}
        items: list[dict[str, Any]] = []
        for address in sorted(set(left) - set(right)):
            items.append({"kind": "object_removed", "address": address})
        for address in sorted(set(right) - set(left)):
            items.append({"kind": "object_added", "address": address})
        for address in sorted(set(left) & set(right)):
            first, second = left[address], right[address]
            if first.class_name != second.class_name:
                items.append({"kind": "class_changed", "address": address,
                              "left": first.class_name,
                              "right": second.class_name})
            if include_geometry and first.points != second.points:
                items.append({"kind": "geometry_changed",
                              "address": address})
        left_edges = {(wire.address): wire for wire in self.model.wires}
        right_edges = {(wire.address): wire for wire in other.wires}
        for address in sorted(set(left_edges) - set(right_edges)):
            items.append({"kind": "wire_removed", "address": address})
        for address in sorted(set(right_edges) - set(left_edges)):
            items.append({"kind": "wire_added", "address": address})
        return self._result("compare_models", items)

    def list_discrepancies(self, severity: str = "", code: str = "",
                           limit: int = 50) -> QueryResult:
        found = [
            item for item in self.model.discrepancies
            if (not severity or item.severity.value == severity)
            and (not code or item.code == code)
        ]
        truncated = len(found) > limit
        return self._result(
            "list_discrepancies",
            [discrepancy_dict(item) for item in found[:limit]],
            truncated=truncated)

    def coverage(self) -> QueryResult:
        return self._result("coverage", [coverage_dict(self.model.coverage)])

    def query(self, name: str, arguments: dict[str, Any] | None = None
              ) -> QueryResult:
        args = dict(arguments or {})
        handlers = {
            "inspect_node": lambda: self.inspect_node(str(args["node"])),
            "find_objects": lambda: self.find_objects(
                str(args.get("query", "")), str(args.get("class_name", "")),
                str(args.get("kind", "")), int(args.get("limit", 50))),
            "trace_signal": lambda: self.trace_signal(
                str(args["signal"]), str(args.get("direction", "forward")),
                int(args.get("max_depth", 64))),
            "ancestors": lambda: self.ancestors(
                str(args["node"]), int(args.get("max_depth", 64))),
            "descendants": lambda: self.descendants(
                str(args["node"]), int(args.get("max_depth", 64))),
            "find_path": lambda: self.find_path(
                str(args["src"]), str(args["dst"]),
                int(args.get("max_length", 32))),
            "find_cycles": lambda: self.find_cycles(
                int(args.get("max_cycles", 20))),
            "check_connections": self.check_connections,
            "compare_models": lambda: self.compare_models(
                args["other"], bool(args.get("include_geometry", False))),
            "validate_invariants": lambda: self.validate_invariants(
                args.get("invariants", ())),
            "list_discrepancies": lambda: self.list_discrepancies(
                str(args.get("severity", "")), str(args.get("code", "")),
                int(args.get("limit", 50))),
            "coverage": self.coverage,
        }
        handler = handlers.get(name)
        if handler is None:
            raise ModelQueryError(f"неизвестный запрос {name!r}")
        return handler()
