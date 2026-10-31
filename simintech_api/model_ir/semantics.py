"""Функциональная семантика Model IR: влияние входов на выход.

Модуль отвечает на вопрос «какие источники действительно влияют на выход»,
а не «какие объекты достижимы по проводам». Структурные рёбра ведут к
блоку, функциональные зависимости внутри блока берутся из контракта.
Неизвестность остаётся неизвестностью: структурный путь не повышает
статус цепочки до `contract`.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .codes import ObjectKind, PortDirection
from .contracts import BlockContract, BlockContractRegistry, Dependency
from .errors import ModelQueryError
from .graph import ModelIndex, QueryResult
from .ir import ModelObject

_STRUCTURAL_KINDS = frozenset({"wire", "branch", "boundary"})
_CALC_SCRIPT_SLOTS = ("script", "Script", "OnInitScript", "OnRunScript")
_INCLUDE = frozenset({"contract", "not_established"})
_MAX_UNKNOWN = 200


def influence(
        index: ModelIndex, registry: BlockContractRegistry, target: str,
        max_depth: int = 64,
        include: Iterable[str] = ("contract", "not_established"),
        max_items: int = 200) -> QueryResult:
    """Цепочки влияния на выход `target`.

    `target` - порт (`объект:индекс`) или объект с одним выходом. Элемент
    ответа - цепочка от цели к терминальному источнику; `hops` хранят
    функциональные переходы, `path` - адреса пройденных узлов.
    """
    allowed = _include_filter(include)
    items: list[dict[str, Any]] = []
    unknown: list[str] = []
    absences: list[dict[str, Any]] = []
    walker = _Walker(index, registry, items, unknown, absences, max_depth)
    for port_id in _target_ports(index, target):
        walker.walk(port_id, [], [], 0, frozenset())
    filtered = [item for item in items
                if item["evidence"]["status"] in allowed]
    total = len(filtered)
    unique_unknown = tuple(dict.fromkeys(unknown))
    return QueryResult(
        query="influence",
        scope="influence",
        model_hash=index.model.meta.structure_hash,
        items=tuple(filtered[:max_items]),
        unknown=unique_unknown[:_MAX_UNKNOWN],
        truncated=(total > max_items
                   or len(unique_unknown) > _MAX_UNKNOWN),
        evidence={"known_absences": absences, "items_total": total},
    )


def _include_filter(include: Iterable[str]) -> frozenset[str]:
    if isinstance(include, str):
        include = (include,)
    values = frozenset(include)
    if not values or values - _INCLUDE:
        raise ModelQueryError(
            f"include={sorted(values)}: допустимы contract и "
            f"not_established")
    return values


def _target_ports(index: ModelIndex, target: str) -> list[str]:
    try:
        return [index.port(target).id]
    except ModelQueryError:
        pass
    obj = index.object(target)
    outputs = [port.id for port in obj.ports
               if port.direction in (PortDirection.OUT,
                                     PortDirection.UNDIRECTED)]
    if not outputs:
        raise ModelQueryError(
            f"{target}: у объекта нет выхода для influence")
    return outputs


def _props(obj: ModelObject) -> dict[str, str]:
    return {name: prop.value for name, prop in obj.props.items()}


def _object_script(obj: ModelObject) -> str:
    for slot in _CALC_SCRIPT_SLOTS:
        info = obj.scripts.get(slot)
        if info is not None and info.present:
            return slot
    return ""


class _Walker:
    def __init__(self, index: ModelIndex, registry: BlockContractRegistry,
                 items: list[dict[str, Any]], unknown: list[str],
                 absences: list[dict[str, Any]], max_depth: int) -> None:
        self.index = index
        self.registry = registry
        self.items = items
        self.unknown = unknown
        self.absences = absences
        self.max_depth = max_depth

    def walk(self, port_id: str, hops: list[dict[str, Any]],
             path: list[str], depth: int,
             visited: frozenset[str]) -> None:
        name = self.index.node_name(port_id)
        if depth > self.max_depth:
            self.unknown.append(f"{name}: depth_limit")
            return
        if port_id in visited:
            self.unknown.append(f"{name}: cycle")
            return
        visited = visited | {port_id}
        path = path + [name]
        port = self.index.ports.get(port_id)
        obj = self.index.node_object(port_id)
        if port is None or obj is None:
            self.unknown.append(f"{name}: unresolved_port")
            return
        if port.direction in (PortDirection.IN, PortDirection.UNDIRECTED):
            self._walk_input(port_id, hops, path, depth, visited)
            return
        self._walk_output(port, obj, name, hops, path, depth, visited)

    def _walk_input(self, port_id: str, hops: list[dict[str, Any]],
                    path: list[str], depth: int,
                    visited: frozenset[str]) -> None:
        incoming = self.index.reverse.get(port_id, ())
        memory = [edge for edge in incoming if edge.kind == "memory"]
        for edge in memory:
            hop = {
                "from": self.index.node_name(port_id),
                "to": self.index.node_name(edge.src),
                "kind": "stateful",
                "condition": None,
                "state": {"kind": "memory"},
                "evidence": {"status": "contract", "ref": edge.wire_id},
            }
            self.walk(edge.src, hops + [hop], path, depth + 1, visited)
        structural = [edge for edge in incoming
                      if edge.kind in _STRUCTURAL_KINDS]
        if structural:
            for edge in structural:
                self.walk(edge.src, hops, path, depth + 1, visited)
            return
        if not memory:
            self._emit({"kind": "port",
                        "address": self.index.node_name(port_id)},
                       hops, path)

    def _walk_output(self, port: Any, obj: ModelObject, name: str,
                     hops: list[dict[str, Any]], path: list[str],
                     depth: int, visited: frozenset[str]) -> None:
        self._collect_absences(obj, port.index, name)
        memory = [edge for edge in self.index.reverse.get(port.id, ())
                  if edge.kind == "memory"]
        if memory:
            for edge in memory:
                hop = {
                    "from": name,
                    "to": self.index.node_name(edge.src),
                    "kind": "stateful",
                    "condition": None,
                    "state": {"kind": "memory"},
                    "evidence": {"status": "contract", "ref": edge.wire_id},
                }
                self.walk(edge.src, hops + [hop], path, depth + 1, visited)
            return
        contract = self.registry.get(obj.class_name)
        if contract is None:
            self.unknown.append(f"{name}: class_unknown")
            return
        start = len(self.items)
        dependencies = [dependency for dependency in
                        self.registry.dependencies_for(
                            obj.class_name, _props(obj))
                        if dependency.output == port.index]
        if not dependencies:
            reason = ("script_defined_ports" if _object_script(obj)
                      else "behavior_unknown")
            self.unknown.append(f"{name}: {reason}")
            self._detail_and_downgrade(port, start)
            return
        for dependency in dependencies:
            self._walk_dependency(
                dependency, contract, obj, name, port, hops, path, depth,
                visited)
        self._detail_and_downgrade(port, start)

    def _detail_and_downgrade(self, port: Any, start: int) -> None:
        """Детализировать субмодель внутри страницы, не поднимая статус.

        Внешний контракт даёт функциональные хопы; переход по boundary
        показывает внутреннюю цепочку. Если внутри есть неизвестный блок,
        условные ветви понижаются, а управляющая зависимость остаётся
        отдельной.
        """
        details = self._detail_unknown(port)
        if not details:
            return
        self.unknown.extend(details)
        reason = details[0]
        for item in self.items[start:]:
            if not any(hop["kind"] == "conditional"
                       for hop in item["hops"]):
                continue
            item["evidence"]["status"] = "not_established"
            item["evidence"]["reason"] = reason
            for hop in item["hops"]:
                if hop["kind"] == "conditional":
                    hop["evidence"]["status"] = "not_established"
                    hop["evidence"]["reason"] = reason

    def _detail_unknown(self, port: Any) -> list[str]:
        obj = self.index.node_object(port.id)
        if obj is None or obj.kind is not ObjectKind.SUBMODEL:
            return []
        details: list[str] = []
        for edge in self.index.reverse.get(port.id, ()):
            if edge.kind != "boundary":
                continue
            walker = _Walker(self.index, self.registry, [], details, [],
                             self.max_depth)
            walker.walk(edge.src, [], [], 0, frozenset())
        return details

    def _walk_dependency(
            self, dependency: Dependency, contract: BlockContract,
            obj: ModelObject, name: str, port: Any,
            hops: list[dict[str, Any]], path: list[str], depth: int,
            visited: frozenset[str]) -> None:
        status, ref, reason = _dependency_evidence(
            contract, dependency, obj)
        object_script = _object_script(obj)
        hop_kind = "script" if object_script else dependency.kind
        source = dependency.source
        source_port = None
        if source.get("kind") == "port":
            raw_index = source.get("index")
            if isinstance(raw_index, int):
                source_port = obj.port(raw_index)
        if source_port is not None:
            to_address = self.index.node_name(source_port.id)
        else:
            to_address = _source_address(obj, source)
        hop = {
            "from": name,
            "to": to_address,
            "kind": hop_kind,
            "condition": (dict(dependency.condition)
                          if dependency.condition is not None else None),
            "state": (dict(dependency.state)
                      if dependency.state is not None else None),
            "evidence": _evidence(status, ref, reason),
        }
        if source.get("kind") in ("property", "state"):
            self._emit(
                {"kind": str(source.get("kind")),
                 "address": _source_address(obj, source)},
                hops + [hop], path)
            return
        if source.get("kind") == "port":
            if source_port is None:
                self.unknown.append(f"{name}: source_port_missing")
                return
            self.walk(source_port.id, hops + [hop], path, depth + 1,
                      visited)
            return
        self.unknown.append(
            f"{name}: unsupported_source_{source.get('kind')}")

    def _collect_absences(self, obj: ModelObject, output: int,
                          target: str) -> None:
        contract = self.registry.get(obj.class_name)
        if contract is None:
            return
        for absence in contract.known_absences:
            if absence.output != output:
                continue
            self.absences.append({
                "target": target,
                "source": dict(absence.source),
                "provenance": _evidence(
                    absence.provenance.status, absence.provenance.ref, ""),
            })

    def _emit(self, source: Mapping[str, Any],
              hops: list[dict[str, Any]], path: list[str]) -> None:
        status, reason = _chain_status(hops)
        self.items.append({
            "target": path[0] if path else "",
            "source": dict(source),
            "path": list(path),
            "hops": list(hops),
            "evidence": _evidence(status, "chain", reason),
            "unknown": None,
        })


def _source_address(obj: ModelObject, source: Mapping[str, Any]) -> str:
    kind = str(source.get("kind", "source"))
    if kind in ("property", "state"):
        return f"{obj.address}@{kind}:{source.get('name', '')}"
    return (f"{obj.address}@{kind}:"
            f"{source.get('name', source.get('index', ''))}")


def _dependency_evidence(
        contract: BlockContract, dependency: Dependency,
        obj: ModelObject) -> tuple[str, str, str]:
    if _object_script(obj):
        return "not_established", dependency.provenance.ref, "object_script"
    if dependency.kind == "script":
        return ("not_established", dependency.provenance.ref,
                dependency.reason or "script")
    if dependency.kind == "unknown":
        return ("not_established", dependency.provenance.ref,
                dependency.reason or "unknown")
    if dependency.kind == "conditional" and dependency.condition is None:
        return ("not_established", dependency.provenance.ref,
                dependency.reason or "condition_unknown")
    status = dependency.provenance.status
    if status == "measured":
        return "contract", dependency.provenance.ref, ""
    if status in ("claim", "derived") and \
            contract.review.status == "approved":
        return "contract", dependency.provenance.ref, ""
    return "not_established", dependency.provenance.ref, "unapproved"


def _chain_status(hops: list[dict[str, Any]]) -> tuple[str, str]:
    if not hops:
        return "not_established", "no_hops"
    for hop in hops:
        evidence = hop["evidence"]
        if evidence["status"] != "contract":
            return "not_established", str(evidence.get("reason", ""))
    return "contract", ""


def _evidence(status: str, ref: str, reason: str) -> dict[str, str]:
    result = {"status": status}
    if ref:
        result["ref"] = ref
    if reason:
        result["reason"] = reason
    return result
