"""Model IR: реестр контрактов блоков и его валидатор."""

import copy
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from simintech_api.model_ir import (  # noqa: E402
    SCHEMA,
    VERSION,
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
    и `U1` у тех же классов; у «Интегратора» корпус дал `Port_0` и `Port_1`,
    а живой COM и импорт 30.10.2026 дают `inport` и `outport`. Имя не
    инвариант, и сверка не должна объявлять из-за него отказ.
    """
    registry = load_default_contracts()
    for name in ("Оператор НЕ", "Операция БОЛЬШЕ", "Операция МЕНЬШЕ",
                 "Интегратор"):
        ports = registry.require(name).ports
        assert ports.model == "fixed"
        assert ports.name_status == "instance_defined"


GRAPH = """<Header><project><page>
  <object>
    <name>`G`</name>
    <class_name>`Временной график`</class_name><obj_type>`100`</obj_type>
    <ports>
      <port><name>`inport_1`</name><mode>`0`</mode></port>
      <port><name>`inport_2`</name><mode>`0`</mode></port>
      <port><name>`inport_3`</name><mode>`0`</mode></port>
    </ports>
  </object>
</page></project></Header>"""


def _generator():
    """Модуль генератора реестра: логика слияния живёт в скрипте."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import generate_block_contracts

    return generate_block_contracts


def test_demultiplexer_outputs_follow_weights():
    """У «Демультиплексора» выходов столько, сколько весов (замер 30.10.2026)."""
    registry = load_default_contracts()
    contract = registry.require("Демультиплексор")
    assert contract.ports.model == "weights"
    assert contract.ports.weights_role == "outputs"
    ports = registry.ports_for("Демультиплексор", {"a": "[1, 1, 1]"})
    assert len(ports.inputs) == 1
    assert len(ports.outputs) == 3
    six = registry.ports_for("Демультиплексор", {"a": "[1, 1, 1, 1, 1, 1]"})
    assert len(six.outputs) == 6


def test_graph_inputs_follow_inportcount():
    """У «Временного графика» входов столько, сколько в InPortCount."""
    registry = load_default_contracts()
    contract = registry.require("Временной график")
    assert contract.ports.model == "nport"
    assert contract.ports.nport_property == "InPortCount"
    ports = registry.ports_for("Временной график", {"InPortCount": "3"})
    assert [item.name for item in ports.inputs] == [
        "inport_1", "inport_2", "inport_3"]
    assert ports.outputs == ()


def test_script_ports_are_not_guessed():
    """Пины «Языка программирования» задаёт скрипт: класс не измерен."""
    registry = load_default_contracts()
    ports = registry.require("Язык программирования").ports
    assert ports.model == "unknown"
    assert ports.reason == "script_defined_ports"


def test_ports_names_only_variety_is_instance_defined():
    """Подписи, различающиеся только именами, дают fixed + instance_defined."""
    generator = _generator()
    observed = [((0, "outport", "out"), (1, "inport", "in")),
                ((0, "Port_0", "out"), (1, "PORT1", "in"))]
    ports = generator._ports("Усилитель", observed, set())
    assert ports["model"] == "fixed"
    assert ports["name_status"] == "instance_defined"
    assert ports["outputs"][0]["name"] == "outport", (
        "образцом выбран набор с автоименами")


def test_merge_replaces_unknown_with_live_observation(tmp_path):
    """Слияние заменяет неизмеренную запись наблюдением, а не пересобирает всё."""
    generator = _generator()
    corpus = tmp_path / "corpus.xprt"
    corpus.write_text(GRAPH, encoding="utf-8")
    existing = {
        "version": VERSION, "schema": SCHEMA,
        "meta": {"port_model_counts": {"unknown": 1},
                 "unknown_classes": ["Временной график"]},
        "classes": {"Временной график": {
            "class": "Временной график", "status": "derived",
            "properties": {}, "ports": {"model": "unknown",
                                        "reason": "varied_signatures"},
            "creation": {"paths": []}, "constraints": [], "provenance": [],
        }},
    }
    merged = generator.merge(existing, CATALOG, [corpus], "2026-10-30")

    ports = merged["classes"]["Временной график"]["ports"]
    assert ports["model"] == "nport"
    assert ports["nport_property"] == "InPortCount"
    assert merged["meta"]["port_model_counts"] == {"nport": 1}
    assert merged["meta"]["unknown_classes"] == []


def test_contract_v2_parses_pilot_fields():
    data = {
        "schema": "block-contract/2",
        "version": 2,
        "classes": {
            "Тестовый блок": {
                "class": "Тестовый блок",
                "status": "derived",
                "pilot_scope": "live_acceptance",
                "ports": {"model": "fixed", "inputs": [], "outputs": []},
                "behavior": {
                    "operation": "gain",
                    "expression": "y = a * u",
                    "parameters": ["a"],
                    "provenance": {"status": "derived", "ref": "test"},
                },
                "dependencies": [{
                    "output": 0,
                    "source": {"kind": "port", "index": 1},
                    "kind": "unconditional",
                    "condition": None,
                    "state": None,
                    "provenance": {"status": "derived", "ref": "test"},
                }],
                "review": {
                    "status": "preliminary", "reviewer": "", "date": "",
                },
                "known_absences": [{
                    "output": 0,
                    "source": {"kind": "port", "index": 2},
                    "provenance": {"status": "claim", "ref": "test"},
                }],
            },
        },
        "meta": {"catalog_classes": 0},
    }
    registry = BlockContractRegistry(data)
    contract = registry.require("Тестовый блок")
    assert contract.behavior.operation == "gain"
    assert contract.dependencies[0].kind == "unconditional"
    assert contract.review.status == "preliminary"
    assert contract.known_absences[0].source["index"] == 2
    assert contract.pilot_scope == "live_acceptance"


def test_contract_v2_rejects_bad_dependency_kind():
    data = _contracts()
    data["classes"]["Усилитель"]["dependencies"] = [{
        "output": 0, "source": {"kind": "port", "index": 1},
        "kind": "maybe", "provenance": {"status": "derived", "ref": "x"},
    }]
    assert validate_contract_data(data, _catalog())


def test_contract_v2_rejects_stateful_without_state():
    data = _contracts()
    data["classes"]["Интегратор"]["dependencies"] = [{
        "output": 0, "source": {"kind": "port", "index": 1},
        "kind": "stateful", "state": None,
        "provenance": {"status": "derived", "ref": "x"},
    }]
    assert validate_contract_data(data, _catalog())


def test_contract_v2_accepts_conditional_with_unknown_condition():
    data = _contracts()
    data["classes"]["Усилитель"]["dependencies"] = [{
        "output": 1, "source": {"kind": "port", "index": 1},
        "kind": "conditional", "condition": None,
        "reason": "condition_unknown",
        "provenance": {"status": "derived", "ref": "x"},
    }]
    assert validate_contract_data(data, _catalog()) == []


def test_contract_v2_rejects_unknown_condition_op():
    data = _contracts()
    data["classes"]["Усилитель"]["dependencies"] = [{
        "output": 1, "source": {"kind": "port", "index": 1},
        "kind": "conditional",
        "condition": {"op": "matches", "source": {"kind": "port", "index": 1}},
        "provenance": {"status": "derived", "ref": "x"},
    }]
    assert validate_contract_data(data, _catalog())


def test_contract_v2_rejects_select_without_cases():
    data = _contracts()
    data["classes"]["Усилитель"]["dependencies"] = [{
        "output": 1, "source": {"kind": "port", "index": 1},
        "kind": "conditional",
        "condition": {"op": "select", "source": {"kind": "port", "index": 1}},
        "provenance": {"status": "derived", "ref": "x"},
    }]
    assert validate_contract_data(data, _catalog())


def test_contract_v2_rejects_unknown_state_kind():
    data = _contracts()
    data["classes"]["Интегратор"]["dependencies"] = [{
        "output": 0, "source": {"kind": "port", "index": 1},
        "kind": "stateful", "state": {"kind": "eternal"},
        "provenance": {"status": "derived", "ref": "x"},
    }]
    assert validate_contract_data(data, _catalog())


def test_contract_v2_rejects_bad_signal_types():
    data = _contracts()
    data["classes"]["Усилитель"]["signal_types"] = {
        "inputs": [{"index": 1, "type": "complex", "unit": "V"}],
        "outputs": [],
        "provenance": {"status": "unknown", "ref": ""},
    }
    assert validate_contract_data(data, _catalog())


def test_contract_v2_rejects_bad_behavior_provenance():
    data = _contracts()
    data["classes"]["Усилитель"]["behavior"] = {
        "operation": "gain",
        "provenance": {"status": "guess", "ref": "x"},
    }
    assert validate_contract_data(data, _catalog())


def test_contract_v2_accepts_selected_input_select_without_cases():
    data = _contracts()
    data["classes"]["Усилитель"]["dependencies"] = [{
        "output": 1,
        "source": {"kind": "port", "role": "selected_input",
                   "selector": {"kind": "port", "role": "control"},
                   "mapping": [{"value": 0, "input": 1}]},
        "kind": "conditional",
        "condition": {"op": "select",
                      "source": {"kind": "port", "role": "control"}},
        "provenance": {"status": "derived", "ref": "x"},
    }]
    assert validate_contract_data(data, _catalog()) == []
