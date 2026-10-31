"""Реестр контрактов блоков: свойства, порты, создание и ограничения.

Контракт не угадывает: неизмеренное поле остаётся `unknown` с причиной.
Реестр покрывает все классы каталога блоков; порты, не наблюдавшиеся в
корпусе выгрузок, честно помечены, а не достроены по имени.
"""

from __future__ import annotations

import json
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

from .codes import PortDirection
from .errors import ModelQueryError

SCHEMA = "block-contract/2"
VERSION = 2


@dataclass(frozen=True, slots=True)
class PortSpec:
    index: int
    name: str
    direction: PortDirection


@dataclass(frozen=True, slots=True)
class PortContract:
    model: str
    inputs: tuple[PortSpec, ...] = ()
    outputs: tuple[PortSpec, ...] = ()
    nport_property: str = ""
    portnames_property: str = ""
    #: Свойство весов: имена входов зависят от коэффициентов (`a` у
    #: «Сумматора»: 1 даёт «+», -1 даёт «−», прочее число даёт само число).
    weights_property: str = ""
    #: Что задают веса: `inputs` (по умолчанию) или `outputs` (у
    #: «Демультиплексора» выходов столько же, сколько весов).
    weights_role: str = "inputs"
    #: Условные порты: добавляются, когда свойство включено (`addport`).
    variants: tuple[Mapping[str, Any], ...] = ()
    name_status: str = "unknown"
    reason: str = ""
    provenance: str = ""

    @property
    def unknown(self) -> bool:
        return self.model == "unknown"


@dataclass(frozen=True, slots=True)
class PropertyContract:
    default: str
    readonly: bool
    kind: str = "unknown"
    provenance: str = ""


@dataclass(frozen=True, slots=True)
class CreationPath:
    path: str
    status: str
    ref: str = ""


@dataclass(frozen=True, slots=True)
class Constraint:
    code: str
    description: str
    params: Mapping[str, Any] = field(default_factory=dict)
    provenance: str = ""


@dataclass(frozen=True, slots=True)
class ProvenanceClaim:
    """Происхождение одного утверждения о поведении."""

    status: str = "unknown"
    ref: str = ""


@dataclass(frozen=True, slots=True)
class Review:
    """Инженерная проверка строки эталона."""

    status: str = "preliminary"
    reviewer: str = ""
    date: str = ""


@dataclass(frozen=True, slots=True)
class Behavior:
    """Машиночитаемое описание операции блока."""

    operation: str = "unknown"
    expression: str = ""
    parameters: tuple[str, ...] = ()
    provenance: ProvenanceClaim = field(default_factory=ProvenanceClaim)


@dataclass(frozen=True, slots=True)
class Dependency:
    """Зависимость выхода от входа, свойства или состояния."""

    output: int | str = 0
    source: Mapping[str, Any] = field(default_factory=dict)
    kind: str = "unknown"
    condition: Mapping[str, Any] | None = None
    state: Mapping[str, Any] | None = None
    reason: str = ""
    provenance: ProvenanceClaim = field(default_factory=ProvenanceClaim)


@dataclass(frozen=True, slots=True)
class KnownAbsence:
    """Проверенное отсутствие зависимости."""

    output: int | str = 0
    source: Mapping[str, Any] = field(default_factory=dict)
    provenance: ProvenanceClaim = field(default_factory=ProvenanceClaim)


@dataclass(frozen=True, slots=True)
class BlockContract:
    class_name: str
    status: str
    properties: Mapping[str, PropertyContract]
    ports: PortContract
    creation: tuple[CreationPath, ...]
    constraints: tuple[Constraint, ...]
    provenance: tuple[str, ...]
    claims: tuple[str, ...] = ()
    behavior: Behavior = field(default_factory=Behavior)
    dependencies: tuple[Dependency, ...] = ()
    signal_types: Mapping[str, Any] = field(default_factory=dict)
    review: Review = field(default_factory=Review)
    known_absences: tuple[KnownAbsence, ...] = ()
    pilot_scope: str = ""


@dataclass(frozen=True, slots=True)
class ContractCoverage:
    classes: int
    measured: int
    derived: int
    unknown: int
    port_models: Mapping[str, int]


def _direction(value: str) -> PortDirection:
    return {
        "in": PortDirection.IN,
        "out": PortDirection.OUT,
        "undirected": PortDirection.UNDIRECTED,
    }.get(value, PortDirection.UNKNOWN)


def _port_spec(item: Mapping[str, Any]) -> PortSpec:
    return PortSpec(index=int(item.get("index", -1)),
                    name=str(item.get("name", "")),
                    direction=_direction(str(item.get("direction", ""))))


def _ports(data: Mapping[str, Any]) -> PortContract:
    return PortContract(
        model=str(data.get("model", "unknown")),
        inputs=tuple(_port_spec(item) for item in data.get("inputs", ())),
        outputs=tuple(_port_spec(item) for item in data.get("outputs", ())),
        nport_property=str(data.get("nport_property", "")),
        portnames_property=str(data.get("portnames_property", "")),
        weights_property=str(data.get("weights_property", "")),
        weights_role=str(data.get("weights_role", "inputs")),
        variants=tuple(dict(item) for item in data.get("variants", ())),
        name_status=str(data.get("name_status", "unknown")),
        reason=str(data.get("reason", "")),
        provenance=str(data.get("provenance", "")))


def _provenance(data: Mapping[str, Any]) -> ProvenanceClaim:
    return ProvenanceClaim(
        status=str(data.get("status", "unknown")),
        ref=str(data.get("ref", "")))


def _behavior(data: Mapping[str, Any]) -> Behavior:
    return Behavior(
        operation=str(data.get("operation", "unknown")),
        expression=str(data.get("expression", "")),
        parameters=tuple(str(item) for item in data.get("parameters", ())),
        provenance=_provenance(data.get("provenance", {})))


def _review(data: Mapping[str, Any]) -> Review:
    return Review(
        status=str(data.get("status", "preliminary")),
        reviewer=str(data.get("reviewer", "")),
        date=str(data.get("date", "")))


def _dependency(data: Mapping[str, Any]) -> Dependency:
    condition = data.get("condition")
    state = data.get("state")
    return Dependency(
        output=data.get("output", 0),
        source=dict(data.get("source", {})),
        kind=str(data.get("kind", "unknown")),
        condition=dict(condition) if isinstance(condition, MappingABC) else None,
        state=dict(state) if isinstance(state, MappingABC) else None,
        reason=str(data.get("reason", "")),
        provenance=_provenance(data.get("provenance", {})))


def _known_absence(data: Mapping[str, Any]) -> KnownAbsence:
    return KnownAbsence(
        output=data.get("output", 0),
        source=dict(data.get("source", {})),
        provenance=_provenance(data.get("provenance", {})))


def _contract(name: str, data: Mapping[str, Any]) -> BlockContract:
    return BlockContract(
        class_name=str(data.get("class", name)),
        status=str(data.get("status", "unknown")),
        properties={
            key: PropertyContract(
                default=str(value.get("default", "")),
                readonly=bool(value.get("readonly", False)),
                kind=str(value.get("kind", "unknown")),
                provenance=str(value.get("provenance", "")))
            for key, value in data.get("properties", {}).items()
        },
        ports=_ports(data.get("ports", {})),
        creation=tuple(
            CreationPath(path=str(item.get("path", "")),
                         status=str(item.get("status", "unknown")),
                         ref=str(item.get("ref", "")))
            for item in data.get("creation", {}).get("paths", ())),
        constraints=tuple(
            Constraint(code=str(item.get("code", "")),
                       description=str(item.get("description", "")),
                       params=dict(item.get("params", {})),
                       provenance=str(item.get("provenance", "")))
            for item in data.get("constraints", ())),
        provenance=tuple(str(item) for item in data.get("provenance", ())),
        claims=tuple(str(item) for item in data.get("claims", ())),
        behavior=_behavior(data.get("behavior", {})),
        dependencies=tuple(_dependency(item)
                           for item in data.get("dependencies", ())),
        signal_types=dict(data.get("signal_types", {})),
        review=_review(data.get("review", {})),
        known_absences=tuple(_known_absence(item)
                             for item in data.get("known_absences", ())),
        pilot_scope=str(data.get("pilot_scope", "")))


class BlockContractRegistry:
    """Загрузчик и запросы к реестру контрактов."""

    def __init__(self, data: Mapping[str, Any]) -> None:
        if int(data.get("version", 0)) != VERSION:
            raise ModelQueryError(
                f"версия реестра {data.get('version')!r} не поддерживается")
        if str(data.get("schema")) != SCHEMA:
            raise ModelQueryError(
                f"схема реестра {data.get('schema')!r} не поддерживается")
        self.meta: Mapping[str, Any] = data.get("meta", {})
        self._contracts = {
            str(name): _contract(str(name), value)
            for name, value in data.get("classes", {}).items()
        }

    @classmethod
    def load(cls, path: str | Path | None = None) -> "BlockContractRegistry":
        target = (Path(path) if path is not None
                  else Path(__file__).resolve().parents[1]
                  / "data" / "block_contracts.json")
        try:
            raw = target.read_text(encoding="utf-8")
        except OSError as exc:
            raise ModelQueryError(
                f"реестр контрактов не прочитан: {exc}") from exc
        return cls(json.loads(raw))

    def classes(self) -> tuple[str, ...]:
        return tuple(sorted(self._contracts))

    def get(self, class_name: str) -> BlockContract | None:
        return self._contracts.get(class_name)

    def require(self, class_name: str) -> BlockContract:
        found = self.get(class_name)
        if found is None:
            raise ModelQueryError(
                f"класс {class_name!r} отсутствует в реестре контрактов")
        return found

    def coverage(self) -> ContractCoverage:
        models: dict[str, int] = {}
        for item in self._contracts.values():
            models[item.ports.model] = models.get(item.ports.model, 0) + 1
        return ContractCoverage(
            classes=len(self._contracts),
            measured=sum(1 for item in self._contracts.values()
                         if item.status == "measured"),
            derived=sum(1 for item in self._contracts.values()
                        if item.status == "derived"),
            unknown=sum(1 for item in self._contracts.values()
                        if item.status == "unknown"),
            port_models=models)

    def ports_for(self, class_name: str,
                  properties: Mapping[str, Any] | None = None) -> PortContract:
        """Порты класса с учётом nport, весов и условных портов.

        Неизмеренный контракт возвращается как `unknown` с причиной: пустой
        список без статуса выглядел бы как «портов нет».
        """
        contract = self.require(class_name)
        props = properties or {}
        ports = contract.ports
        result = ports
        if ports.model == "nport":
            raw = props.get(ports.nport_property or "nport",
                            _default(contract, ports.nport_property or "nport"))
            try:
                count = int(raw)
            except (TypeError, ValueError) as exc:
                raise ModelQueryError(
                    f"{class_name}: {ports.nport_property or 'nport'}="
                    f"{raw!r} не целое число") from exc
            if count < 1:
                raise ModelQueryError(
                    f"{class_name}: число входов {count} меньше единицы")
            result = PortContract(
                model="nport",
                inputs=tuple(_nport_input(ports, index)
                             for index in range(1, count + 1)),
                # Синтетический выход не подставляется: у «Временного
                # графика» его нет вовсе, и «портов 0 против 1» было ложным
                # отказом (живой прогон 30.10.2026).
                outputs=ports.outputs,
                nport_property=ports.nport_property or "nport",
                name_status=ports.name_status,
                provenance=ports.provenance)
        elif ports.model == "weights":
            result = _weights_ports(contract, props)
        return _with_variants(contract, result, props)


def _default(contract: BlockContract, name: str) -> str:
    prop = contract.properties.get(name)
    return prop.default if prop is not None else ""


def _weights_ports(contract: BlockContract,
                   props: Mapping[str, Any]) -> PortContract:
    """Порты по весам: число и имена входов задаёт `a`.

    Живой замер 30.10.2026 (SimInTech64): `Сумматор` с `a = [1 , -1]` даёт
    входы «+» и «−» (U+2212), с `a = [2 , -3]` даёт «2» и «-3» (минус ASCII),
    с `a = [1 , 1 , 1]` три входа «+». Имена дробных весов не измерены:
    такой вход остаётся без имени, и сверка имена для него не проверяет
    (пустое ожидаемое имя сверка пропускает).
    """
    ports = contract.ports
    name = ports.weights_property or "a"
    raw = props.get(name, _default(contract, name))
    values = _weights(raw)
    if values is None:
        raise ModelQueryError(
            f"{contract.class_name}: {name}={raw!r} не список весов")
    if ports.weights_role == "outputs":
        # Имена выходов «Демультиплексора» зависят от экземпляра: наблюдались
        # и `outport_1…`, и `output_0…`, поэтому имена пустые (сверка их не
        # проверяет), а счётчик по весам остаётся точным.
        return PortContract(
            model="weights",
            inputs=ports.inputs,
            outputs=tuple(PortSpec(index, "", PortDirection.OUT)
                          for index in range(1, len(values) + 1)),
            weights_property=name,
            weights_role="outputs",
            name_status="instance_defined",
            provenance=ports.provenance)
    return PortContract(
        model="weights",
        inputs=tuple(PortSpec(index, _weight_name(value), PortDirection.IN)
                     for index, value in enumerate(values, start=1)),
        outputs=ports.outputs,
        weights_property=name,
        name_status=ports.name_status,
        provenance=ports.provenance)


def _weights(raw: Any) -> "list[float] | None":
    """Веса из значения свойства: `[1 , -1]` или `1 -1`; `None` значит не разобрать."""
    text = str(raw).strip().strip("[]")
    if not text.strip():
        return None
    parts = [item for item in text.replace(",", " ").split() if item]
    try:
        return [float(item) for item in parts]
    except ValueError:
        return None


def _weight_name(value: float) -> str:
    """Имя входа по весу: «+», «−» (U+2212) или само число."""
    if value == 1:
        return "+"
    if value == -1:
        return "−"
    if float(value).is_integer():
        return str(int(value))
    return ""


def _truthy(raw: Any) -> bool:
    """Включено ли свойство: пусто, «0» и «false» значат нет."""
    return str(raw).strip().lower() not in ("", "0", "false")


def _with_variants(contract: BlockContract, ports: PortContract,
                   props: Mapping[str, Any]) -> PortContract:
    """Добавить условные порты, свойства которых включены.

    Живой замер 30.10.2026: у `Задержки по включению` порт `T1` есть при
    `addport = 1` и отсутствует при `addport = 0` или пустом значении.
    """
    if not contract.ports.variants:
        return ports
    inputs = list(ports.inputs)
    outputs = list(ports.outputs)
    for variant in contract.ports.variants:
        prop = str(variant.get("property", ""))
        if not prop:
            continue
        raw = props.get(prop, _default(contract, prop))
        if not _truthy(raw):
            continue
        inputs.extend(_port_spec(item) for item in variant.get("add_inputs", ()))
        outputs.extend(_port_spec(item)
                       for item in variant.get("add_outputs", ()))
    inputs.sort(key=lambda item: item.index)
    outputs.sort(key=lambda item: item.index)
    return replace(ports, inputs=tuple(inputs), outputs=tuple(outputs))


def _nport_input(ports: PortContract, number: int) -> PortSpec:
    observed = [item for item in ports.inputs
                if item.direction is PortDirection.IN]
    if number <= len(observed) and observed[number - 1].name:
        return PortSpec(number, observed[number - 1].name, PortDirection.IN)
    prefix = "u"
    if observed:
        name = observed[0].name
        for pos, char in enumerate(name):
            if char.isdigit():
                prefix = name[:pos] or "u"
                break
    return PortSpec(number, f"{prefix}{number}", PortDirection.IN)


_ALLOWED_STATUS = {"measured", "derived", "unknown"}
_ALLOWED_PORT_MODELS = {"fixed", "nport", "portnames", "submodel",
                        "weights", "unknown"}
_ALLOWED_NAME_STATUS = {"measured", "missing", "unknown",
                        "instance_defined", "weights"}
_ALLOWED_CREATION = {"derived", "blocked", "unknown"}
_ALLOWED_PILOT_SCOPE = {"", "live_acceptance", "synthetic_only", "auxiliary"}
_ALLOWED_REVIEW = {"preliminary", "approved"}
_ALLOWED_BEHAVIOR = {
    "identity", "constant", "gain", "sum", "product", "integrate",
    "select", "vector", "split", "script", "unknown",
}
_ALLOWED_DEPENDENCY = {
    "unconditional", "conditional", "control", "stateful", "script",
    "unknown",
}
_ALLOWED_PROVENANCE = {
    "measured", "derived", "claim", "experiment", "unknown",
}
_ALLOWED_CONDITION = {"equals", "in", "threshold", "select"}
_ALLOWED_STATE = {"initial", "history", "memory"}
_ALLOWED_SOURCE = {"port", "property", "state", "memory", "boundary"}
_ALLOWED_ROLE = {"all_inputs", "selected_input", "control"}
_ALLOWED_SIGNAL_TYPE = {"real", "integer", "boolean", "vector", "unknown"}


def _check_provenance(where: str, data: Any,
                      problems: list[str]) -> None:
    if not isinstance(data, MappingABC):
        problems.append(f"{where}: provenance не объект")
        return
    if data.get("status") not in _ALLOWED_PROVENANCE:
        problems.append(
            f"{where}: недопустимый provenance.status "
            f"{data.get('status')!r}")


def _check_source(where: str, source: Any, problems: list[str]) -> None:
    if not isinstance(source, MappingABC):
        problems.append(f"{where}: source не объект")
        return
    kind = source.get("kind")
    if kind not in _ALLOWED_SOURCE:
        problems.append(f"{where}: недопустимый source.kind {kind!r}")
        return
    if kind == "port":
        role = source.get("role")
        if role is not None and role not in _ALLOWED_ROLE:
            problems.append(f"{where}: недопустимая role {role!r}")
        if role is None and not isinstance(source.get("index"), int):
            problems.append(f"{where}: port без index или role")
        if role == "selected_input":
            if not isinstance(source.get("selector"), MappingABC):
                problems.append(f"{where}: selected_input без selector")
            mapping = source.get("mapping")
            if mapping is not None:
                if not isinstance(mapping, list):
                    problems.append(f"{where}: mapping не список")
                else:
                    for case in mapping:
                        if not isinstance(case, MappingABC) or \
                                "value" not in case or \
                                not isinstance(case.get("input"), int):
                            problems.append(
                                f"{where}: mapping без value/input")
    elif kind == "property" and not source.get("name"):
        problems.append(f"{where}: property без name")
    elif kind == "state" and not source.get("name"):
        problems.append(f"{where}: state без name")


def _check_condition(where: str, condition: Any, source: Any,
                     problems: list[str]) -> None:
    if not isinstance(condition, MappingABC):
        problems.append(f"{where}: condition не объект")
        return
    op = condition.get("op")
    if op not in _ALLOWED_CONDITION:
        problems.append(f"{where}: недопустимый condition.op {op!r}")
        return
    if not isinstance(condition.get("source"), MappingABC):
        problems.append(f"{where}: condition без source")
    if op == "equals" and "value" not in condition:
        problems.append(f"{where}: equals без value")
    if op == "in" and not isinstance(condition.get("values"), list):
        problems.append(f"{where}: in без values")
    if op == "threshold" and not isinstance(
            condition.get("above"), (int, float)):
        problems.append(f"{where}: threshold без above")
    if op == "select":
        cases = condition.get("cases")
        role = source.get("role") if isinstance(source, MappingABC) else None
        if cases is None:
            if role != "selected_input":
                problems.append(f"{where}: select без cases")
        elif not isinstance(cases, list):
            problems.append(f"{where}: cases не список")
        else:
            for case in cases:
                if not isinstance(case, MappingABC) or \
                        "value" not in case or \
                        not isinstance(case.get("input"), int):
                    problems.append(f"{where}: case без value/input")


def _check_state(where: str, state: Any, problems: list[str]) -> None:
    if not isinstance(state, MappingABC):
        problems.append(f"{where}: state не объект")
        return
    kind = state.get("kind")
    if kind not in _ALLOWED_STATE:
        problems.append(f"{where}: недопустимый state.kind {kind!r}")
        return
    if kind == "initial" and not state.get("property"):
        problems.append(f"{where}: initial без property")
    if kind == "history" and not state.get("window"):
        problems.append(f"{where}: history без window")
    if kind == "memory" and not state.get("cell"):
        problems.append(f"{where}: memory без cell")


def _check_behavior(where: str, data: Any, problems: list[str]) -> None:
    if not isinstance(data, MappingABC):
        problems.append(f"{where}: behavior не объект")
        return
    if data.get("operation") not in _ALLOWED_BEHAVIOR:
        problems.append(
            f"{where}: недопустимый behavior.operation "
            f"{data.get('operation')!r}")
    _check_provenance(f"{where}.behavior",
                      data.get("provenance", {}), problems)


def _check_signal_types(where: str, data: Any, problems: list[str]) -> None:
    if not isinstance(data, MappingABC):
        problems.append(f"{where}: signal_types не объект")
        return
    for key in ("inputs", "outputs"):
        items = data.get(key, [])
        if not isinstance(items, list):
            problems.append(f"{where}.{key}: не список")
            continue
        for pos, item in enumerate(items):
            if not isinstance(item, MappingABC):
                problems.append(f"{where}.{key}[{pos}]: не объект")
                continue
            if not isinstance(item.get("index"), int):
                problems.append(f"{where}.{key}[{pos}]: без index")
            if item.get("type") not in _ALLOWED_SIGNAL_TYPE:
                problems.append(
                    f"{where}.{key}[{pos}]: недопустимый type "
                    f"{item.get('type')!r}")
            if not isinstance(item.get("unit", ""), str):
                problems.append(f"{where}.{key}[{pos}]: unit не строка")
    _check_provenance(f"{where}.signal_types",
                      data.get("provenance", {}), problems)


def _check_dependency(where: str, data: Any,
                      problems: list[str]) -> None:
    if not isinstance(data, MappingABC):
        problems.append(f"{where}: зависимость не объект")
        return
    output = data.get("output")
    if not (isinstance(output, int) or output == "all_outputs"):
        problems.append(f"{where}: недопустимый output {output!r}")
    kind = data.get("kind")
    if kind not in _ALLOWED_DEPENDENCY:
        problems.append(f"{where}: недопустимый kind {kind!r}")
    source = data.get("source", {})
    _check_source(f"{where}.source", source, problems)
    _check_provenance(where, data.get("provenance", {}), problems)
    state = data.get("state")
    if kind == "stateful" and state is None:
        problems.append(f"{where}: stateful без state")
    elif state is not None:
        _check_state(f"{where}.state", state, problems)
    condition = data.get("condition")
    if kind == "conditional" and condition is None:
        if not data.get("reason"):
            problems.append(f"{where}: conditional без condition")
    elif condition is not None:
        _check_condition(f"{where}.condition", condition, source, problems)
    if kind == "script" and not data.get("reason"):
        problems.append(f"{where}: script без reason")


def validate_contract_data(data: Mapping[str, Any],
                           catalog: Mapping[str, Any]) -> list[str]:
    """Проверить реестр против каталога; пустой список: реестр цел."""
    problems: list[str] = []
    if int(data.get("version", 0)) != VERSION:
        problems.append(f"version={data.get('version')!r}, ожидается {VERSION}")
    if str(data.get("schema")) != SCHEMA:
        problems.append(f"schema={data.get('schema')!r}, ожидается {SCHEMA}")
    classes = data.get("classes", {})
    catalog_classes = catalog.get("classes", {})
    expected = set(catalog_classes)
    actual = set(classes)
    if actual != expected:
        problems.append(
            f"классы не совпадают: нет {sorted(expected - actual)[:5]}, "
            f"лишние {sorted(actual - expected)[:5]}")
    meta = data.get("meta", {})
    if int(meta.get("catalog_classes", 0)) != len(catalog_classes):
        problems.append("meta.catalog_classes не равен каталогу")
    counts: dict[str, int] = {}
    unknown: list[str] = []
    for name, item in classes.items():
        if item.get("class") != name:
            problems.append(f"{name}: class не совпадает с ключом")
        status = item.get("status")
        if status not in _ALLOWED_STATUS:
            problems.append(f"{name}: недопустимый status {status!r}")
        properties = item.get("properties", {})
        if set(properties) - set(catalog_classes.get(name, {})):
            problems.append(f"{name}: свойства вне каталога")
        readonly = set(catalog.get("readonly", {}).get(name, ()))
        for prop_name, prop in properties.items():
            if bool(prop.get("readonly")) != (prop_name in readonly):
                problems.append(f"{name}.{prop_name}: readonly расходится")
        ports = item.get("ports", {})
        model = ports.get("model")
        if model not in _ALLOWED_PORT_MODELS:
            problems.append(f"{name}: недопустимая ports.model {model!r}")
        counts[model] = counts.get(model, 0) + 1
        if model == "unknown":
            unknown.append(name)
            if not ports.get("reason"):
                problems.append(f"{name}: unknown без reason")
        nport_prop = str(ports.get("nport_property", ""))
        if model == "nport" and not nport_prop:
            problems.append(f"{name}: nport без nport_property")
        if model == "nport" and nport_prop and catalog_classes and \
                nport_prop not in catalog_classes.get(name, {}):
            problems.append(
                f"{name}: nport_property {nport_prop!r} не свойство класса")
        if model != "nport" and ports.get("nport_property"):
            problems.append(f"{name}: nport_property вне nport")
        if model == "portnames" and ports.get(
                "portnames_property") != "PortNames":
            problems.append(f"{name}: portnames без PortNames")
        if model != "portnames" and ports.get("portnames_property"):
            problems.append(f"{name}: PortNames вне portnames")
        if ports.get("name_status") not in _ALLOWED_NAME_STATUS:
            problems.append(
                f"{name}: недопустимый name_status "
                f"{ports.get('name_status')!r}")
        if model == "weights" and not ports.get("weights_property"):
            problems.append(f"{name}: weights без weights_property")
        if model != "weights" and ports.get("weights_property"):
            problems.append(f"{name}: weights_property вне weights")
        if ports.get("weights_role", "inputs") not in ("inputs", "outputs"):
            problems.append(
                f"{name}: недопустимый weights_role "
                f"{ports.get('weights_role')!r}")
        if model != "weights" and ports.get("weights_role", "inputs") != "inputs":
            problems.append(f"{name}: weights_role вне weights")
        for variant in ports.get("variants", ()):
            if not str(variant.get("property", "")):
                problems.append(f"{name}: вариант без property")
            for key in ("add_inputs", "add_outputs"):
                for spec in variant.get(key, ()):
                    if not isinstance(spec.get("index"), int):
                        problems.append(f"{name}: {key} без index")
                    if spec.get("direction") not in ("in", "out", "undirected"):
                        problems.append(f"{name}: {key} с дурным direction")
        scope = item.get("pilot_scope", "")
        if scope not in _ALLOWED_PILOT_SCOPE:
            problems.append(f"{name}: недопустимый pilot_scope {scope!r}")
        if "behavior" in item:
            _check_behavior(f"{name}", item.get("behavior"), problems)
        if "review" in item:
            review = item.get("review")
            if not isinstance(review, MappingABC):
                problems.append(f"{name}: review не объект")
            elif review.get("status") not in _ALLOWED_REVIEW:
                problems.append(
                    f"{name}: недопустимый review.status "
                    f"{review.get('status')!r}")
        if "dependencies" in item:
            dependencies = item.get("dependencies")
            if not isinstance(dependencies, list):
                problems.append(f"{name}: dependencies не список")
            else:
                for pos, dependency in enumerate(dependencies):
                    _check_dependency(
                        f"{name}.dependencies[{pos}]", dependency, problems)
        if "signal_types" in item:
            _check_signal_types(
                f"{name}", item.get("signal_types"), problems)
        if "known_absences" in item:
            absences = item.get("known_absences")
            if not isinstance(absences, list):
                problems.append(f"{name}: known_absences не список")
            else:
                for pos, absence in enumerate(absences):
                    where = f"{name}.known_absences[{pos}]"
                    if not isinstance(absence, MappingABC):
                        problems.append(f"{where}: не объект")
                        continue
                    output = absence.get("output")
                    if not (isinstance(output, int)
                            or output == "all_outputs"):
                        problems.append(
                            f"{where}: недопустимый output {output!r}")
                    _check_source(f"{where}.source",
                                  absence.get("source", {}), problems)
                    _check_provenance(
                        where, absence.get("provenance", {}), problems)
        for path in item.get("creation", {}).get("paths", ()):
            if path.get("status") not in _ALLOWED_CREATION:
                problems.append(f"{name}: недопустимый creation.status")
        for constraint in item.get("constraints", ()):
            if chr(0x2014) in str(constraint.get("description", "")):
                problems.append(f"{name}: em dash в описании ограничения")
    if dict(sorted(counts.items())) != meta.get("port_model_counts"):
        problems.append("meta.port_model_counts не совпадает с контрактами")
    if sorted(unknown) != sorted(meta.get("unknown_classes", ())):
        problems.append("meta.unknown_classes не совпадает")
    return problems


_default_registry: BlockContractRegistry | None = None


def load_default_contracts(reload: bool = False) -> BlockContractRegistry:
    global _default_registry
    if _default_registry is None or reload:
        _default_registry = BlockContractRegistry.load()
    return _default_registry
