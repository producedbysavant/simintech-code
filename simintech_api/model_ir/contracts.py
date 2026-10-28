"""Реестр контрактов блоков: свойства, порты, создание и ограничения.

Контракт не угадывает: неизмеренное поле остаётся `unknown` с причиной.
Реестр покрывает все классы каталога блоков; порты, не наблюдавшиеся в
корпусе выгрузок, честно помечены, а не достроены по имени.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .codes import PortDirection
from .errors import ModelQueryError

SCHEMA = "block-contract/1"
VERSION = 1


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
class BlockContract:
    class_name: str
    status: str
    properties: Mapping[str, PropertyContract]
    ports: PortContract
    creation: tuple[CreationPath, ...]
    constraints: tuple[Constraint, ...]
    provenance: tuple[str, ...]
    claims: tuple[str, ...] = ()


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
        name_status=str(data.get("name_status", "unknown")),
        reason=str(data.get("reason", "")),
        provenance=str(data.get("provenance", "")))


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
        claims=tuple(str(item) for item in data.get("claims", ())))


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
        """Порты класса с учётом nport/PortNames.

        Неизмеренный контракт возвращается как `unknown` с причиной: пустой
        список без статуса выглядел бы как «портов нет».
        """
        contract = self.require(class_name)
        props = properties or {}
        ports = contract.ports
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
            return PortContract(
                model="nport",
                inputs=tuple(_nport_input(ports, index)
                             for index in range(1, count + 1)),
                outputs=ports.outputs or (PortSpec(0, "y", PortDirection.OUT),),
                nport_property=ports.nport_property or "nport",
                name_status=ports.name_status,
                provenance=ports.provenance)
        return ports


def _default(contract: BlockContract, name: str) -> str:
    prop = contract.properties.get(name)
    return prop.default if prop is not None else ""


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
_ALLOWED_PORT_MODELS = {"fixed", "nport", "portnames", "submodel", "unknown"}
_ALLOWED_CREATION = {"derived", "blocked", "unknown"}


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
        if model == "nport" and ports.get("nport_property") != "nport":
            problems.append(f"{name}: nport без nport_property")
        if model != "nport" and ports.get("nport_property"):
            problems.append(f"{name}: nport_property вне nport")
        if model == "portnames" and ports.get(
                "portnames_property") != "PortNames":
            problems.append(f"{name}: portnames без PortNames")
        if model != "portnames" and ports.get("portnames_property"):
            problems.append(f"{name}: PortNames вне portnames")
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
