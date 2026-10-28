"""Компиляция SystemSpec в ожидаемую модель без исполнения кода.

Спецификация проверяется до SimInTech: классы, свойства, ссылки на блоки,
концы проводов, инварианты и профиль проверки. Ошибки собираются все, чтобы
агент исправил спецификацию за один проход.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from .codes import PortDirection
from .contracts import BlockContractRegistry, load_default_contracts
from .errors import ModelQueryError, SystemSpecError

SCHEMA = "system-spec/1"
_ENDPOINT_RE = re.compile(r"^(.+):(out|in):(\d+)$")
_INVARIANTS = frozenset({
    "required_inputs_connected", "no_self_loops", "unique_object_names",
    "memory_pair_complete", "no_dangling_wires", "max_fanout",
    "container_depth", "contract_ports_match",
})
_CHECKS = frozenset({"object_present", "wire_present", "ports_connected",
                     "no_cycles"})
_OPS = frozenset({"==", "!=", ">", ">=", "<", "<="})


@dataclass(frozen=True, slots=True)
class ExpectedPort:
    index: int
    name: str
    direction: PortDirection


@dataclass(frozen=True, slots=True)
class ExpectedObject:
    name: str
    class_name: str
    ports: tuple[ExpectedPort, ...]
    ports_known: bool
    children: tuple["ExpectedLevel", ...] = ()


@dataclass(frozen=True, slots=True)
class ExpectedWire:
    src: str
    src_index: int
    dst: str
    dst_index: int


@dataclass(frozen=True, slots=True)
class ExpectedLevel:
    address: str
    objects: tuple[ExpectedObject, ...]
    wires: tuple[ExpectedWire, ...]


@dataclass(frozen=True, slots=True)
class ExpectedModel:
    level: ExpectedLevel


@dataclass(frozen=True, slots=True)
class CompiledSpec:
    name: str
    expected: ExpectedModel
    invariants: tuple[dict[str, Any], ...]
    requirements: tuple[dict[str, Any], ...]
    assertions: tuple[dict[str, Any], ...]
    profile: Mapping[str, Any]
    provenance: Mapping[str, Any] = field(default_factory=dict)


def _problem(problems: list[dict[str, str]], path: str, code: str,
             message: str) -> None:
    problems.append({"path": path, "code": code, "message": message})


def _ports_from_hints(data: Any) -> tuple[ExpectedPort, ...]:
    if not isinstance(data, Mapping):
        return ()
    result: list[ExpectedPort] = []
    index = 0
    for key, direction in (("inputs", PortDirection.IN),
                           ("outputs", PortDirection.OUT)):
        values = data.get(key, ())
        if not isinstance(values, (list, tuple)):
            continue
        for name in values:
            if isinstance(name, str) and name:
                result.append(ExpectedPort(index, name, direction))
                index += 1
    return tuple(result)


def _ports_from_contract(class_name: str, props: Mapping[str, Any],
                         registry: BlockContractRegistry) -> tuple[
                             tuple[ExpectedPort, ...], bool, str]:
    try:
        contract = registry.ports_for(class_name, props)
    except ModelQueryError as exc:
        return (), False, str(exc)
    if contract.model in ("unknown", "submodel"):
        return (), False, contract.reason or contract.model
    result = tuple(
        ExpectedPort(item.index, item.name, item.direction)
        for item in contract.inputs + contract.outputs)
    return result, True, ""


def _endpoint(value: Any, expected: str, path: str,
              names: set[str], problems: list[dict[str, str]]
              ) -> tuple[str, int] | None:
    if not isinstance(value, str):
        _problem(problems, path, "bad_endpoint", "конец провода не строка")
        return None
    match = _ENDPOINT_RE.match(value)
    if match is None:
        _problem(problems, path, "bad_endpoint",
                 f"{value!r}: ожидается имя:{expected}:индекс")
        return None
    name, kind, raw_index = match.groups()
    if kind != expected:
        _problem(problems, path, "bad_endpoint",
                 f"{value!r}: для этого конца нужен {expected}")
    if name.lower() not in names:
        _problem(problems, path, "unknown_block",
                 f"{value!r}: блока {name!r} нет на уровне")
    try:
        index = int(raw_index)
    except ValueError:
        _problem(problems, path, "bad_endpoint", f"{value!r}: индекс не число")
        return None
    return name, index


def _compile_level(blocks: Any, wires: Any, address: str, path: str,
                   registry: BlockContractRegistry,
                   problems: list[dict[str, str]]) -> ExpectedLevel:
    if not isinstance(blocks, list):
        _problem(problems, path + ".blocks", "bad_shape",
                 "blocks должен быть списком")
        blocks = []
    names: set[str] = set()
    objects: list[ExpectedObject] = []
    for pos, block in enumerate(blocks):
        block_path = f"{path}.blocks[{pos}]"
        if not isinstance(block, Mapping):
            _problem(problems, block_path, "bad_shape", "блок не объект")
            continue
        name = str(block.get("name", ""))
        class_name = str(block.get("class", ""))
        if not name:
            _problem(problems, block_path + ".name", "missing_name",
                     "у блока нет имени")
            continue
        if name.lower() in names:
            _problem(problems, block_path + ".name", "duplicate_name",
                     f"имя {name!r} повторяется")
        names.add(name.lower())
        props = block.get("props", {})
        if not isinstance(props, Mapping):
            props = {}
        hints = _ports_from_hints(block.get("ports"))
        ports = hints
        ports_known = bool(hints)
        contract = registry.get(class_name)
        if contract is None:
            _problem(problems, block_path + ".class", "unknown_class",
                     f"класса {class_name!r} нет в каталоге")
        else:
            for prop in props:
                if prop not in contract.properties:
                    _problem(problems, block_path + ".props", "unknown_prop",
                             f"свойства {prop!r} нет у класса {class_name!r}")
            if not hints:
                ports, ports_known, _reason = _ports_from_contract(
                    class_name, props, registry)
        children: list[ExpectedLevel] = []
        if "subsystem" in block:
            subsystem = block.get("subsystem")
            if not isinstance(subsystem, Mapping):
                _problem(problems, block_path + ".subsystem", "bad_shape",
                         "subsystem должен быть объектом")
            else:
                children.append(_compile_level(
                    subsystem.get("blocks", []), subsystem.get("wires", []),
                    f"{address}/{name}", block_path + ".subsystem",
                    registry, problems))
        objects.append(ExpectedObject(
            name=name, class_name=class_name, ports=ports,
            ports_known=ports_known, children=tuple(children)))
    if not isinstance(wires, list):
        _problem(problems, path + ".wires", "bad_shape",
                 "wires должен быть списком")
        wires = []
    result_wires: list[ExpectedWire] = []
    for pos, wire in enumerate(wires):
        wire_path = f"{path}.wires[{pos}]"
        if not isinstance(wire, Mapping):
            _problem(problems, wire_path, "bad_shape", "провод не объект")
            continue
        src = _endpoint(wire.get("src"), "out", wire_path + ".src",
                        names, problems)
        dst = _endpoint(wire.get("dst"), "in", wire_path + ".dst",
                        names, problems)
        if src is None or dst is None:
            continue
        if src[0].lower() == dst[0].lower() and src[1] == dst[1]:
            _problem(problems, wire_path, "self_loop",
                     "провод из выхода в тот же вход")
            continue
        result_wires.append(ExpectedWire(src[0], src[1], dst[0], dst[1]))
    return ExpectedLevel(address=address, objects=tuple(objects),
                         wires=tuple(result_wires))


def compile_system_spec(
        spec: Mapping[str, Any],
        registry: Optional[BlockContractRegistry] = None
) -> CompiledSpec:
    """Проверить и нормализовать SystemSpec; ошибки собраны все."""
    problems: list[dict[str, str]] = []
    if not isinstance(spec, Mapping):
        raise SystemSpecError([{"path": "$", "code": "bad_shape",
                                "message": "спецификация не объект"}])
    schema = str(spec.get("schema", SCHEMA))
    if schema != SCHEMA:
        _problem(problems, "schema", "bad_schema",
                 f"схема {schema!r}, ожидается {SCHEMA}")
    registry = registry or load_default_contracts()
    level = _compile_level(
        spec.get("blocks", []), spec.get("wires", []), "main", "$",
        registry, problems)
    invariants = spec.get("invariants", [])
    if not isinstance(invariants, list):
        _problem(problems, "invariants", "bad_shape",
                 "invariants должен быть списком")
        invariants = []
    for pos, invariant in enumerate(invariants):
        if not isinstance(invariant, Mapping):
            _problem(problems, f"invariants[{pos}]", "bad_shape",
                     "инвариант не объект")
        elif invariant.get("kind") not in _INVARIANTS:
            _problem(problems, f"invariants[{pos}].kind", "unknown_kind",
                     f"неизвестный инвариант {invariant.get('kind')!r}")
    requirements = spec.get("requirements", [])
    if not isinstance(requirements, list):
        _problem(problems, "requirements", "bad_shape",
                 "requirements должен быть списком")
        requirements = []
    for pos, requirement in enumerate(requirements):
        if not isinstance(requirement, Mapping):
            _problem(problems, f"requirements[{pos}]", "bad_shape",
                     "требование не объект")
            continue
        if not requirement.get("id"):
            _problem(problems, f"requirements[{pos}].id", "missing_id",
                     "у требования нет id")
        check = requirement.get("check")
        if check is not None:
            if not isinstance(check, Mapping):
                _problem(problems, f"requirements[{pos}].check", "bad_shape",
                         "check не объект")
            elif check.get("kind") not in _CHECKS:
                _problem(problems, f"requirements[{pos}].check.kind",
                         "unknown_check",
                         f"неизвестная проверка {check.get('kind')!r}")
    assertions = spec.get("assertions", [])
    if not isinstance(assertions, list):
        _problem(problems, "assertions", "bad_shape",
                 "assertions должен быть списком")
        assertions = []
    for pos, assertion in enumerate(assertions):
        if not isinstance(assertion, Mapping):
            _problem(problems, f"assertions[{pos}]", "bad_shape",
                     "утверждение не объект")
        elif assertion.get("op") not in _OPS:
            _problem(problems, f"assertions[{pos}].op", "unknown_op",
                     f"неизвестная операция {assertion.get('op')!r}")
    profile = dict(spec.get("verification_profile", {}))
    profile.setdefault("readback", ["xprt"])
    profile.setdefault("simulate", False)
    profile.setdefault("tolerance", 1e-9)
    profile.setdefault("check_geometry", False)
    profile.setdefault("build_strategy", "auto")
    if problems:
        raise SystemSpecError(problems)
    return CompiledSpec(
        name=str(spec.get("name", "") or "model"),
        expected=ExpectedModel(level=level),
        invariants=tuple(dict(item) for item in invariants),
        requirements=tuple(dict(item) for item in requirements),
        assertions=tuple(dict(item) for item in assertions),
        profile=profile,
        provenance=dict(spec.get("provenance", {}) or {}))
