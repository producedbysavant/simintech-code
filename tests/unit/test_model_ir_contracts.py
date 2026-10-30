"""Model IR: реестр контрактов блоков и его валидатор."""

import copy
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from simintech_api.model_ir import (  # noqa: E402
    BlockContractRegistry,
    ModelQueryError,
    load_default_contracts,
    validate_contract_data,
)

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "simintech_api" / "data" / "block_catalog.json"
CONTRACTS = ROOT / "simintech_api" / "data" / "block_contracts.json"


def _catalog() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def _contracts() -> dict:
    return json.loads(CONTRACTS.read_text(encoding="utf-8"))


def test_registry_covers_all_catalog_classes():
    registry = load_default_contracts()
    assert len(registry.classes()) == 958
    assert set(registry.classes()) == set(_catalog()["classes"])
    coverage = registry.coverage()
    assert coverage.classes == 958
    assert sum(coverage.port_models.values()) == 958


def test_nport_and_portnames_contracts():
    registry = load_default_contracts()
    multiply = registry.require("Перемножитель")
    assert multiply.ports.model == "nport"
    assert multiply.ports.nport_property == "nport"
    assert any(item.code == "nport-input-count"
               for item in multiply.constraints)
    ports = registry.ports_for("Перемножитель", {"nport": 3})
    assert [item.index for item in ports.inputs] == [1, 2, 3]
    assert ports.outputs
    assert ports.inputs[0].name == "PORT1"
    assert ports.inputs[2].name == "PORT3"

    memory = registry.require("В память")
    assert memory.ports.model == "portnames"
    assert memory.ports.portnames_property == "PortNames"
    assert registry.require("Субмодель").ports.model == "submodel"


def test_blocked_creation_and_unknown_ports():
    registry = load_default_contracts()
    out_port = registry.require("Порт выхода")
    assert any(path.status == "blocked" for path in out_port.creation)
    unknown = registry.require("Arduino - I2C - Ведомый I2C")
    assert unknown.ports.model == "unknown"
    assert unknown.ports.reason


def test_ports_for_refuses_bad_nport_and_unknown_class():
    registry = load_default_contracts()
    with pytest.raises(ModelQueryError):
        registry.ports_for("Перемножитель", {"nport": 0})
    with pytest.raises(ModelQueryError):
        registry.ports_for("Перемножитель", {"nport": "много"})
    with pytest.raises(ModelQueryError):
        registry.ports_for("Нет такого класса")


def test_validator_accepts_registry_and_rejects_mutations():
    data = _contracts()
    catalog = _catalog()
    assert validate_contract_data(data, catalog) == []

    broken = copy.deepcopy(data)
    broken["classes"].pop(next(iter(broken["classes"])))
    assert validate_contract_data(broken, catalog)

    broken = copy.deepcopy(data)
    name = "Перемножитель"
    broken["classes"][name]["status"] = "wrong"
    assert validate_contract_data(broken, catalog)

    broken = copy.deepcopy(data)
    unknown = next(item for item in broken["classes"].values()
                   if item["ports"]["model"] == "unknown")
    unknown["ports"].pop("reason")
    assert validate_contract_data(broken, catalog)

    broken = copy.deepcopy(data)
    broken["classes"][name]["ports"]["nport_property"] = "other"
    assert validate_contract_data(broken, catalog)

    broken = copy.deepcopy(data)
    broken["classes"][name]["constraints"][0]["description"] += chr(0x2014)
    assert validate_contract_data(broken, catalog)


def test_registry_rejects_wrong_schema():
    data = _contracts()
    data["schema"] = "other"
    with pytest.raises(ModelQueryError):
        BlockContractRegistry(data)


def test_sum_ports_follow_weights():
    """Сумматор: число и имена входов задают веса (живой замер 30.10.2026).

    `a = [1 , -1]` даёт «+» и «−» (U+2212), `a = [2 , -3]` даёт «2» и
    «-3», три единицы дают три входа «+». Имя дробного веса не измерено и
    остаётся пустым: сверка такое имя не проверяет.
    """
    registry = load_default_contracts()
    contract = registry.require("Сумматор")
    assert contract.ports.model == "weights"
    assert contract.ports.weights_property == "a"

    pairs = registry.ports_for("Сумматор", {"a": "[1 , -1]"})
    assert [(item.index, item.name) for item in pairs.inputs] == [
        (1, "+"), (2, "−")]
    numbers = registry.ports_for("Сумматор", {"a": "[2 , -3]"})
    assert [item.name for item in numbers.inputs] == ["2", "-3"]
    three = registry.ports_for("Сумматор", {"a": "[1 , 1 , 1]"})
    assert [item.name for item in three.inputs] == ["+", "+", "+"]
    fractional = registry.ports_for("Сумматор", {"a": "[0.5 , 1]"})
    assert fractional.inputs[0].name == ""
    with pytest.raises(ModelQueryError):
        registry.ports_for("Сумматор", {"a": "много"})


def test_optional_port_follows_addport():
    """T1 у задержки есть только при включённом addport (замер 30.10.2026)."""
    registry = load_default_contracts()
    contract = registry.require("Задержка по включению")
    assert contract.ports.variants
    on = registry.ports_for("Задержка по включению", {"addport": "1"})
    assert [item.name for item in on.inputs] == ["inport", "T1"]
    off = registry.ports_for("Задержка по включению", {"addport": "0"})
    assert [item.name for item in off.inputs] == ["inport"]
    empty = registry.ports_for("Задержка по включению", {})
    assert [item.name for item in empty.inputs] == ["inport"]


def test_instance_defined_port_names_are_declared():
    """Классы с меняющимся от экземпляра именем помечены явно.

    Корпус дал `inport` и `inport_1`, живая приёмка 29.10.2026 показала `U`
    и `U1` у тех же классов: имя не инвариант, и сверка не должна объявлять
    из-за него отказ.
    """
    registry = load_default_contracts()
    for name in ("Оператор НЕ", "Операция БОЛЬШЕ", "Операция МЕНЬШЕ"):
        ports = registry.require(name).ports
        assert ports.model == "fixed"
        assert ports.name_status == "instance_defined"
