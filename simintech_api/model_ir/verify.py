"""Сверка фактической модели с SystemSpec и инженерные проверки.

Вердикт не маскирует частичный успех: `failed` при любом расхождении,
`partial` при неизвестных или непроверенных пунктах, `passed` только когда
все запрошенные проверки прошли.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .codes import PortDirection, WireEndKind
from .graph import ModelIndex
from .ir import Container, ModelIR, ModelObject
from .system_spec import CompiledSpec, ExpectedLevel, ExpectedObject

_MAX_ITEMS = 200
_STATUS_ORDER = {"failed": 0, "not_evaluated": 1, "unknown": 2, "passed": 3}


def _limited(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        enumerate(items),
        key=lambda pair: (_STATUS_ORDER.get(str(pair[1].get("status")), 9),
                          pair[0]))
    return [item for _pos, item in ordered[:_MAX_ITEMS]]


@dataclass(frozen=True, slots=True)
class VerificationReport:
    verdict: str
    spec_name: str
    model_hash: str
    items: tuple[dict[str, Any], ...]
    counts: dict[str, int]
    scope: str = "full_model"
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "spec_name": self.spec_name,
            "model_hash": self.model_hash,
            "scope": self.scope,
            "items": list(self.items),
            "counts": dict(self.counts),
            "truncated": self.truncated,
        }


def _item(ident: str, kind: str, status: str, detail: str,
          **evidence: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": ident, "kind": kind, "status": status, "detail": detail}
    if evidence:
        item["evidence"] = evidence
    return item


def _container(model: ModelIR, address: str) -> Container | None:
    for container in model.containers:
        if container.address == address:
            return container
    return None


def _objects(model: ModelIR, container: Container) -> dict[str, ModelObject]:
    return {item.name.lower(): item for item in model.objects
            if item.container_id == container.id}


def _edges(model: ModelIR, container: Container,
           objects: dict[str, ModelObject]) -> set[
               tuple[str, int, str, int]]:
    result: set[tuple[str, int, str, int]] = set()
    by_id = {item.id: key for key, item in objects.items()}
    for wire in model.wires:
        if wire.container_id != container.id:
            continue
        if (wire.start.kind is not WireEndKind.PORT
                or wire.end.kind is not WireEndKind.PORT):
            continue
        src = by_id.get(wire.start.object_id)
        dst = by_id.get(wire.end.object_id)
        if src is None or dst is None:
            continue
        result.add((src, wire.start.port_index, dst, wire.end.port_index))
    return result


def _expected_edges(level: ExpectedLevel) -> set[tuple[str, int, str, int]]:
    return {(item.src.lower(), item.src_index,
             item.dst.lower(), item.dst_index)
            for item in level.wires}


def _compare_ports(expected: ExpectedObject, actual: ModelObject) -> str:
    expected_in = sum(1 for item in expected.ports
                      if item.direction is PortDirection.IN)
    expected_out = sum(1 for item in expected.ports
                       if item.direction is PortDirection.OUT)
    actual_in = [item for item in actual.ports
                 if item.direction is PortDirection.IN]
    actual_out = [item for item in actual.ports
                  if item.direction is PortDirection.OUT]
    if len(actual_in) != expected_in or len(actual_out) != expected_out:
        return (f"входов {len(actual_in)} против {expected_in}, "
                f"выходов {len(actual_out)} против {expected_out}")
    expected_names = {item.name.lower() for item in expected.ports if item.name}
    if expected_names:
        actual_names = {item.name.lower() for item in actual.ports if item.name}
        missing = expected_names - actual_names
        if missing:
            return f"нет портов {sorted(missing)}"
    return ""


def _compare_level(model: ModelIR, expected: ExpectedLevel,
                   address: str, items: list[dict[str, Any]]) -> None:
    container = _container(model, address)
    if container is None:
        items.append(_item(f"container:{address}", "container_missing",
                           "failed", f"контейнера {address} нет"))
        return
    actual_objects = _objects(model, container)
    expected_names = {item.name.lower() for item in expected.objects}
    for obj in expected.objects:
        actual = actual_objects.get(obj.name.lower())
        if actual is None:
            items.append(_item(f"object:{obj.name}", "object_missing",
                               "failed", f"блока {obj.name} нет"))
            continue
        if actual.class_name != obj.class_name:
            items.append(_item(
                f"object:{obj.name}", "class_mismatch", "failed",
                f"text={obj.class_name!r}, actual={actual.class_name!r}"))
        if obj.ports_known:
            mismatch = _compare_ports(obj, actual)
            if mismatch:
                items.append(_item(
                    f"object:{obj.name}", "port_mismatch", "failed", mismatch))
        else:
            items.append(_item(
                f"object:{obj.name}", "port_unknown", "not_evaluated",
                "портовая схема класса не измерена"))
        for child in obj.children:
            child_container = next(
                (item for item in model.containers
                 if item.parent_object_id == actual.id), None)
            if child_container is None:
                items.append(_item(
                    f"container:{child.address}", "container_missing",
                    "failed", f"страницы субмодели {child.address} нет"))
            else:
                _compare_level(model, child, child.address, items)
    for name in sorted(set(actual_objects) - expected_names):
        items.append(_item(f"object:{name}", "object_extra", "failed",
                           f"лишний блок {name}"))
    expected_edges = _expected_edges(expected)
    actual_edges = _edges(model, container, actual_objects)
    for edge in sorted(expected_edges - actual_edges):
        items.append(_item(
            f"wire:{edge[0]}->{edge[2]}", "wire_missing", "failed",
            f"нет провода {edge}"))
    for edge in sorted(actual_edges - expected_edges):
        items.append(_item(
            f"wire:{edge[0]}->{edge[2]}", "wire_extra", "failed",
            f"лишний провод {edge}"))


def _requirements(model: ModelIR, index: ModelIndex,
                  requirements: tuple[dict[str, Any], ...]
                  ) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    objects = {item.name.lower(): item for item in model.objects}
    for pos, requirement in enumerate(requirements):
        ident = str(requirement.get("id", f"requirement[{pos}]"))
        check = requirement.get("check")
        if not isinstance(check, dict):
            items.append(_item(ident, "requirement", "not_evaluated",
                               "у требования нет машинной проверки"))
            continue
        kind = str(check.get("kind", ""))
        target = str(check.get("target", ""))
        if kind == "object_present":
            found = target.lower() in objects
            items.append(_item(
                ident, "requirement", "passed" if found else "failed",
                f"блок {target}: {'есть' if found else 'нет'}"))
        elif kind == "wire_present":
            parts = target.split("->")
            found = False
            if len(parts) == 2:
                src = parts[0].strip().split(":")
                dst = parts[1].strip().split(":")
                main = _container(model, "main")
                if main is not None and len(src) >= 3 and len(dst) >= 3:
                    try:
                        wanted = (src[0].lower(), int(src[2]),
                                  dst[0].lower(), int(dst[2]))
                    except ValueError:
                        wanted = None
                    if wanted is not None:
                        found = wanted in _edges(
                            model, main, _objects(model, main))
            items.append(_item(
                ident, "requirement", "passed" if found else "failed",
                f"провод {target}: {'есть' if found else 'нет'}"))
        elif kind == "ports_connected":
            obj = objects.get(target.lower())
            if obj is None:
                items.append(_item(ident, "requirement", "failed",
                                   f"блока {target} нет"))
            else:
                missing = [port.index for port in obj.ports
                           if port.direction is PortDirection.IN
                           and not index.reverse.get(port.id)]
                items.append(_item(
                    ident, "requirement", "passed" if not missing else "failed",
                    f"входов без источника: {len(missing)}"))
        elif kind == "no_cycles":
            cycles = index.find_cycles()
            items.append(_item(
                ident, "requirement", "passed" if not cycles.items else "failed",
                f"циклов: {len(cycles.items)}"))
        else:
            items.append(_item(ident, "requirement", "not_evaluated",
                               f"неизвестная проверка {kind!r}"))
    return items


def verify_model(actual: ModelIR, compiled: CompiledSpec) -> VerificationReport:
    """Сверить фактическую модель с скомпилированной спецификацией."""
    items: list[dict[str, Any]] = []
    _compare_level(actual, compiled.expected.level, "main", items)
    index = ModelIndex(actual)
    for item in index.validate_invariants(
            compiled.invariants, query_limit=None).items:
        items.append(_item(str(item.get("id")), "invariant",
                           str(item.get("status")),
                           str(item.get("detail", ""))))
    items.extend(_requirements(actual, index, compiled.requirements))
    for pos, assertion in enumerate(compiled.assertions):
        ident = str(assertion.get("id", f"assertion[{pos}]"))
        items.append(_item(ident, "assertion", "not_evaluated",
                           "расчётное испытание не выполнялось"))
    if compiled.profile.get("check_geometry"):
        items.append(_item("geometry", "geometry", "not_evaluated",
                           "геометрия спецификации не задана"))
    counts = {"passed": 0, "failed": 0, "not_evaluated": 0, "unknown": 0}
    for item in items:
        status = str(item.get("status"))
        if status in counts:
            counts[status] += 1
    if counts["failed"]:
        verdict = "failed"
    elif counts["not_evaluated"] or counts["unknown"]:
        verdict = "partial"
    else:
        verdict = "passed"
    return VerificationReport(
        verdict=verdict, spec_name=compiled.name,
        model_hash=actual.meta.structure_hash,
        items=tuple(_limited(items)),
        counts=counts, truncated=len(items) > _MAX_ITEMS)
