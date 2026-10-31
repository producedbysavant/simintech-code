# Functional Semantics Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Научить `simintech_api.model_ir` отвечать на вопрос о функциональном влиянии входов на выход, не выдавая структурную достижимость за причинность, и дать проверяемое покрытие семантики.

**Architecture:** Один Model IR, без второго представления. `BlockContract` расширяется полями `behavior`, `dependencies`, `signal_types`, `review`, `known_absences`. Граф сохраняет типы рёбер; запросы получают фильтр `edge_kinds`. Новый модуль `semantics.py` реализует `influence` и `semantic_coverage` поверх существующих `ModelIndex` и реестра контрактов.

**Tech Stack:** Python 3.11, dataclasses, pytest, PyYAML (тестовые зависимости), defusedxml. Проект: `simintech-code`.

**Spec:** `docs/superpowers/specs/2026-10-30-functional-semantics-pilot.md`

## Global Constraints

- Схема контрактов: `block-contract/2`, версия `2`. Старые поля сохраняются; отсутствие нового поля означает `unknown`.
- `evidence.status = contract` только если каждый функциональный хоп проходит правило: `measured` именно отношения источник-выход, `claim` из утверждённой строки, `derived` только при `review.status = approved`. `preliminary` всегда даёт `not_established`.
- Структурный `measured` (порты, число входов) не подтверждает функциональную зависимость.
- `selected_input` раскрывается по явному `mapping`; подставлять `port.index` вместо значения управляющего сигнала запрещено.
- Переход по `boundary` не подтверждает причинность; внутренний `unknown` понижает цепочку до `not_established`, даже если внешний контракт дал `contract`.
- `pilot_scope` (`live_acceptance`, `synthetic_only`, `auxiliary`) сохраняется в контракте; `auxiliary` не входит в живую приёмку.
- `script` не сворачивается в `unknown`: сохраняются `kind: script`, `reason: object_script`, `evidence.status: not_established`.
- `known_absences` не входят в `items` и не являются терминальными узлами влияния.
- По худшему звену агрегируется только `evidence.status`. `hops` сохраняют `kind`, `condition`, `state` и provenance каждого перехода.
- 958-классовый реестр не расширяется. Коммутатор по номеру порта живёт в тестовом контракте; `nport_named` не добавляется в production-данные.
- Никакого длинного тире (U+2014) и никакой атрибуции Claude в коммитах, комментариях и документах.
- Публичные фикстуры не содержат реальных путей, адресов и имён модели привода.

## Review Focus

1. Предварительная или derived-строка не должна давать `contract`. Тест: `test_influence_preliminary_row_is_not_contract` в Task 5.
2. Скрипт объекта не должен исчезать за общим `unknown`. Тест: `test_influence_script_preserves_kind_and_reason` в Task 5.
3. `known_absences` не должны появляться как источник влияния. Тест: `test_influence_known_absence_is_separate` в Task 5.
4. Цепочка с разными типами хопов не должна терять типы при агрегации. Тест: `test_influence_keeps_each_hop_kind` в Task 4.
5. Переход через границу субмодели не должен превращать структурную достижимость в `contract` без функционального контракта. Тест: `test_influence_boundary_without_contract_is_not_established` в Task 6.

---

### Task 0: Ветка и базовый прогон

**Files:** нет изменений.

- [ ] **Step 1: Создать ветку от main**

Run:
```bash
cd /mnt/c/git/simintech-code
git switch -c feat/functional-semantics-core main
```

- [ ] **Step 2: Зафиксировать базовый прогон**

Run:
```bash
python3 -m pytest -q
```
Expected: известный результат репозитория. Записать число passed и список падений. Новые тесты обязаны проходить; чужие падения не исправлять в этой работе.

---

### Task 1: Схема контрактов v2

**Files:**
- Modify: `simintech_api/model_ir/contracts.py`
- Modify: `simintech_api/data/block_contracts.json` (только `schema` и `version`)
- Test: `tests/unit/test_model_ir_contracts.py`

**Interfaces:**
- Consumes: существующие `PortContract`, `PropertyContract`, `Constraint`, `BlockContractRegistry`.
- Produces:
  - `ProvenanceClaim(status: str, ref: str)`
  - `Review(status: str, reviewer: str, date: str)`
  - `Behavior(operation: str, expression: str, parameters: tuple[str, ...], provenance: ProvenanceClaim)`
  - `Dependency(output: int | str, source: Mapping[str, Any], kind: str, condition: Mapping[str, Any] | None, state: Mapping[str, Any] | None, reason: str, provenance: ProvenanceClaim)`
  - `KnownAbsence(output: int | str, source: Mapping[str, Any], provenance: ProvenanceClaim)`
  - `BlockContract.behavior`, `.dependencies`, `.signal_types`, `.review`, `.known_absences`, `.pilot_scope`
  - `SCHEMA = "block-contract/2"`, `VERSION = 2`

- [ ] **Step 1: Написать падающий тест разбора**

Добавить в `tests/unit/test_model_ir_contracts.py`:
```python
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
```

- [ ] **Step 2: Убедиться, что тест падает**

Run:
```bash
python3 -m pytest tests/unit/test_model_ir_contracts.py::test_contract_v2_parses_pilot_fields -v
```
Expected: FAIL, `TypeError` или отсутствующие атрибуты.

- [ ] **Step 3: Реализовать dataclasses и разбор**

В `contracts.py`:
- поднять `SCHEMA` и `VERSION`;
- добавить dataclasses из Interfaces;
- расширить `BlockContract` полями с default;
- в `_contract()` разобрать новые поля;
- в `validate_contract_data()` добавить проверки:
  - `review.status` из `{"preliminary", "approved"}`;
  - `pilot_scope` из `{"", "live_acceptance", "synthetic_only", "auxiliary"}`;
  - `behavior.operation` из `{"identity", "constant", "gain", "sum", "product", "integrate", "select", "vector", "split", "script", "unknown"}`;
  - `behavior.provenance.status` из `{"measured", "derived", "claim", "experiment", "unknown"}`;
  - `dependencies[].kind` из `{"unconditional", "conditional", "control", "stateful", "script", "unknown"}`;
  - `dependencies[].provenance.status` из `{"measured", "derived", "claim", "experiment", "unknown"}`;
  - `stateful` без `state` отвергается;
  - `conditional` без `condition` отвергается только при пустом `reason`;
  - `known_absences[].source.kind` из `{"port", "property", "state"}`;
  - `condition.op` из `{"equals", "in", "threshold", "select"}`; обязательные поля: `equals` - `source` и `value`; `in` - `source` и `values`; `threshold` - `source` и `above`; `select` - `source` и `cases`;
  - `select` требует `cases`, кроме зависимости с `role: selected_input`, где cases строятся из `mapping`;
  - `state.kind` из `{"initial", "history", "memory"}`; обязательные поля: `initial` - `property`; `history` - `window`; `memory` - `cell`;
  - `source.kind` из `{"port", "property", "state", "memory", "boundary"}`;
  - роли портов из `{"all_inputs", "selected_input", "control"}`; `selected_input` требует `selector`, `mapping` необязателен, элементы `mapping` имеют `value` и `input`;
  - `signal_types` имеет `inputs`, `outputs`, `provenance`, а элементы портов имеют `index`, `type`, `unit`; `type` из `{"real", "integer", "boolean", "vector", "unknown"}`.
- в `simintech_api/data/block_contracts.json` заменить `"schema": "block-contract/1"` на `2` и `"version": 1` на `2`.

- [ ] **Step 4: Прогнать тест и весь файл**

Run:
```bash
python3 -m pytest tests/unit/test_model_ir_contracts.py -q
```
Expected: PASS. Если старые тесты ждут `block-contract/1`, обновить ожидания на константу `SCHEMA`.

- [ ] **Step 5: Добавить отказы валидатора**

Добавить тесты:
```python
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
```
Run:
```bash
python3 -m pytest tests/unit/test_model_ir_contracts.py -q
```
Expected: FAIL до реализации проверок, PASS после.

- [ ] **Step 6: Коммит**

```bash
git add simintech_api/model_ir/contracts.py simintech_api/data/block_contracts.json tests/unit/test_model_ir_contracts.py
git commit -m "feat(model-ir): схема контрактов v2 с поведением и зависимостями"
```

---

### Task 2: Раскрытие зависимостей по экземпляру

**Files:**
- Modify: `simintech_api/model_ir/contracts.py`
- Test: `tests/unit/test_model_ir_contracts.py`

**Interfaces:**
- Consumes: `BlockContractRegistry.ports_for`, `Dependency`.
- Produces: `BlockContractRegistry.dependencies_for(class_name: str, properties: Mapping[str, Any] | None = None) -> tuple[Dependency, ...]`.

- [ ] **Step 1: Написать падающие тесты раскрытия**

Добавить:
```python
def _test_registry(classes):
    return BlockContractRegistry({
        "schema": "block-contract/2", "version": 2,
        "classes": classes, "meta": {},
    })


def test_dependencies_all_inputs_expand_by_nport():
    registry = _test_registry({
        "Тестовый nport": {
            "class": "Тестовый nport", "status": "derived",
            "ports": {
                "model": "nport", "nport_property": "nport",
                "inputs": [{"index": 1, "name": "PORT1", "direction": "in"}],
                "outputs": [{"index": 0, "name": "out", "direction": "out"}],
            },
            "dependencies": [{
                "output": 0,
                "source": {"kind": "port", "role": "all_inputs"},
                "kind": "unconditional",
                "provenance": {"status": "claim", "ref": "test"},
            }],
        },
    })
    deps = registry.dependencies_for("Тестовый nport", {"nport": "3"})
    assert [item.source["index"] for item in deps] == [1, 2, 3]


def test_selected_input_expands_without_control():
    registry = _test_registry({
        "Тестовый выбор": {
            "class": "Тестовый выбор", "status": "derived",
            "ports": {
                "model": "fixed",
                "inputs": [
                    {"index": 0, "name": "number", "direction": "in"},
                    {"index": 1, "name": "data_1", "direction": "in"},
                    {"index": 2, "name": "data_2", "direction": "in"},
                ],
                "outputs": [{"index": 0, "name": "out", "direction": "out"}],
            },
            "dependencies": [
                {"output": 0, "source": {"kind": "port", "index": 0},
                 "kind": "control",
                 "provenance": {"status": "claim", "ref": "test"}},
                {"output": 0,
                 "source": {"kind": "port", "role": "selected_input",
                            "selector": {"kind": "port", "role": "control"},
                            "mapping": [{"value": 0, "input": 1},
                                        {"value": 1, "input": 2}]},
                 "kind": "conditional",
                 "condition": {"op": "select",
                               "source": {"kind": "port", "role": "control"}},
                 "provenance": {"status": "claim", "ref": "test"}},
            ],
        },
    })
    deps = registry.dependencies_for("Тестовый выбор")
    selected = [item for item in deps if item.kind == "conditional"]
    assert [item.source["index"] for item in selected] == [1, 2]
    assert [item.condition["cases"][0]["value"] for item in selected] == [0, 1]
    assert [item.condition["cases"][0]["input"] for item in selected] == [1, 2]
    assert all(item.source["index"] != 0 for item in selected)


def test_selected_input_without_mapping_is_condition_unknown():
    registry = _test_registry({
        "Тестовый выбор": {
            "class": "Тестовый выбор", "status": "derived",
            "ports": {
                "model": "fixed",
                "inputs": [
                    {"index": 0, "name": "number", "direction": "in"},
                    {"index": 1, "name": "data_1", "direction": "in"},
                    {"index": 2, "name": "data_2", "direction": "in"},
                ],
                "outputs": [{"index": 0, "name": "out", "direction": "out"}],
            },
            "dependencies": [
                {"output": 0, "source": {"kind": "port", "index": 0},
                 "kind": "control",
                 "provenance": {"status": "claim", "ref": "test"}},
                {"output": 0,
                 "source": {"kind": "port", "role": "selected_input",
                            "selector": {"kind": "port", "role": "control"}},
                 "kind": "conditional",
                 "provenance": {"status": "claim", "ref": "test"}},
            ],
        },
    })
    selected = [item for item in registry.dependencies_for("Тестовый выбор")
                if item.kind == "conditional"]
    assert [item.source["index"] for item in selected] == [1, 2]
    assert all(item.condition is None for item in selected)
    assert all(item.reason == "condition_unknown" for item in selected)


def test_all_outputs_expand_by_ports():
    registry = _test_registry({
        "Тестовый разветвитель": {
            "class": "Тестовый разветвитель", "status": "derived",
            "ports": {
                "model": "fixed",
                "inputs": [{"index": 0, "name": "inport", "direction": "in"}],
                "outputs": [
                    {"index": 1, "name": "out_1", "direction": "out"},
                    {"index": 2, "name": "out_2", "direction": "out"},
                ],
            },
            "dependencies": [{
                "output": "all_outputs",
                "source": {"kind": "port", "index": 0},
                "kind": "unconditional",
                "provenance": {"status": "claim", "ref": "test"},
            }],
        },
    })
    deps = registry.dependencies_for("Тестовый разветвитель")
    assert [item.output for item in deps] == [1, 2]
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run:
```bash
python3 -m pytest tests/unit/test_model_ir_contracts.py -q -k "dependencies or selected or outputs"
```
Expected: FAIL, метода нет.

- [ ] **Step 3: Реализовать `dependencies_for`**

Правила:
- `ports = self.ports_for(class_name, properties)`;
- `control_index` берётся из зависимости `kind == "control"` с конкретным `source.index`;
- `output == "all_outputs"` разворачивается по `ports.outputs`;
- `source.role == "all_inputs"` разворачивается по `ports.inputs`;
- `source.role == "selected_input"` разворачивается по всем входам, кроме `control_index`;
- если задан `mapping`, условие получает один case `{"value": v, "input": i}` из таблицы; подставлять `port.index` вместо значения запрещено;
- если `mapping` нет, зависимость остаётся `conditional`, `condition` равен `null`, `reason` равен `condition_unknown`;
- конкретные `output`/`source.index` возвращаются как есть;
- неразрешимая роль даёт `ModelQueryError`.

- [ ] **Step 4: Прогнать тесты**

Run:
```bash
python3 -m pytest tests/unit/test_model_ir_contracts.py -q
```
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add simintech_api/model_ir/contracts.py tests/unit/test_model_ir_contracts.py
git commit -m "feat(model-ir): раскрытие зависимостей по nport и весам"
```

---

### Task 3: Фильтр `edge_kinds` в графовых запросах

**Files:**
- Modify: `simintech_api/model_ir/graph.py`
- Test: `tests/unit/test_model_ir_graph.py`

**Interfaces:**
- Consumes: `SignalEdge.kind`, `ModelIndex.signal`, `ModelIndex.reverse`.
- Produces:
  - `ModelIndex.trace_signal(..., edge_kinds: tuple[str, ...] | None = None)`
  - `ModelIndex.ancestors(..., edge_kinds=...)`
  - `ModelIndex.descendants(..., edge_kinds=...)`
  - `ModelIndex.find_path(..., edge_kinds=...)`
  - `ModelIndex.query("trace_signal", {"edge_kinds": [...]})` и те же для остальных запросов.

- [ ] **Step 1: Написать падающие тесты**

Добавить:
```python
def test_trace_signal_edge_kinds_filter():
    model = parse_xprt(flat_model(3).text)
    index = ModelIndex(model)
    structural = index.trace_signal(
        "main::B1:1", direction="forward",
        edge_kinds=("wire", "branch", "boundary", "memory"))
    block_only = index.trace_signal(
        "main::B1:0", direction="forward", edge_kinds=("block",))
    assert any(item["address"] == "main::B2" for item in structural.items)
    assert all(item["address"] != "main::B1" for item in structural.items)
    assert any(item["address"] == "main::B1" for item in block_only.items)
    assert all(item["address"] != "main::B2" for item in block_only.items)


def test_trace_signal_rejects_unknown_edge_kind():
    index = ModelIndex(parse_xprt(flat_model(2).text))
    with pytest.raises(ModelQueryError):
        index.trace_signal("main::B0:1", edge_kinds=("teleport",))


def test_query_passes_edge_kinds():
    index = ModelIndex(parse_xprt(flat_model(3).text))
    result = index.query("trace_signal", {
        "signal": "main::B1:1", "direction": "forward",
        "edge_kinds": ["block"],
    })
    assert result.query == "trace_signal"
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run:
```bash
python3 -m pytest tests/unit/test_model_ir_graph.py -q -k "edge_kinds"
```
Expected: FAIL, неожиданный аргумент.

- [ ] **Step 3: Реализовать фильтр**

Добавить helper:
```python
_EDGE_KINDS = frozenset({"wire", "branch", "boundary", "memory", "block"})

def _edge_filter(edge_kinds):
    if edge_kinds is None:
        return None
    unknown = set(edge_kinds) - _EDGE_KINDS
    if unknown or not edge_kinds:
        raise ModelQueryError(
            f"edge_kinds={edge_kinds!r}: допустимы непустые значения "
            f"из {sorted(_EDGE_KINDS)}")
    return frozenset(edge_kinds)
```
Провести фильтр через `_walk_depths`, `_walk`, `_object_walk`, `find_path`; в `query()` прочитать `args.get("edge_kinds")`.

- [ ] **Step 4: Прогнать тесты**

Run:
```bash
python3 -m pytest tests/unit/test_model_ir_graph.py -q
```
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add simintech_api/model_ir/graph.py tests/unit/test_model_ir_graph.py
git commit -m "feat(model-ir): фильтр edge_kinds в графовых запросах"
```

---

### Task 4: Базовый запрос `influence`

**Files:**
- Create: `simintech_api/model_ir/semantics.py`
- Modify: `simintech_api/model_ir/__init__.py`
- Test: `tests/unit/test_model_ir_semantics.py`

**Interfaces:**
- Consumes: `ModelIndex`, `BlockContractRegistry`, `Dependency`, `QueryResult`.
- Produces:
  - `influence(index: ModelIndex, registry: BlockContractRegistry, target: str, max_depth: int = 64, include: tuple[str, ...] = ("contract", "not_established"), max_items: int = 200) -> QueryResult`
  - `QueryResult.items` содержит цепочки; `QueryResult.evidence["known_absences"]` содержит отдельный список; `QueryResult.unknown` содержит причины обрыва.

- [ ] **Step 1: Написать падающий тест цепочки**

Собрать тестовую модель:
```python
MODEL = """<Header><project><page>
  <object><name>`K`</name><class_name>`Константа`</class_name>
    <obj_type>`100`</obj_type>
    <ports><port><name>`y`</name><mode>`1`</mode></port></ports>
  </object>
  <object><name>`G`</name><class_name>`Усилитель`</class_name>
    <obj_type>`100`</obj_type>
    <ports>
      <port><name>`u`</name><mode>`0`</mode></port>
      <port><name>`y`</name><mode>`1`</mode></port>
    </ports>
  </object>
  <object><name>`S`</name><class_name>`Временной график`</class_name>
    <obj_type>`106`</obj_type>
    <ports><port><name>`u`</name><mode>`0`</mode></port></ports>
  </object>
  <object><name>`W1`</name><class_name>`Математическая связь`</class_name>
    <obj_type>`101`</obj_type>
    <start_bl_index>`0`</start_bl_index><start_port_index>`0`</start_port_index>
    <end_bl_index>`1`</end_bl_index><end_port_index>`0`</end_port_index>
  </object>
  <object><name>`W2`</name><class_name>`Математическая связь`</class_name>
    <obj_type>`101`</obj_type>
    <start_bl_index>`1`</start_bl_index><start_port_index>`1`</start_port_index>
    <end_bl_index>`2`</end_bl_index><end_port_index>`0`</end_port_index>
  </object>
</page></project></Header>"""
```

Тест:
```python
def _semantic_registry():
    return BlockContractRegistry({
        "schema": "block-contract/2", "version": 2, "meta": {},
        "classes": {
            "Константа": {
                "class": "Константа", "status": "derived",
                "ports": {"model": "fixed", "inputs": [],
                          "outputs": [{"index": 0, "name": "y", "direction": "out"}]},
                "behavior": {"operation": "constant", "expression": "y = a",
                             "parameters": ["a"],
                             "provenance": {"status": "claim", "ref": "test"}},
                "dependencies": [{
                    "output": 0, "source": {"kind": "property", "name": "a"},
                    "kind": "unconditional",
                    "provenance": {"status": "claim", "ref": "test"},
                }],
                "review": {"status": "approved", "reviewer": "test", "date": "2026-10-30"},
            },
            "Усилитель": {
                "class": "Усилитель", "status": "derived",
                "ports": {"model": "fixed",
                          "inputs": [{"index": 0, "name": "u", "direction": "in"}],
                          "outputs": [{"index": 1, "name": "y", "direction": "out"}]},
                "behavior": {"operation": "gain", "expression": "y = a * u",
                             "parameters": ["a"],
                             "provenance": {"status": "claim", "ref": "test"}},
                "dependencies": [
                    {"output": 1, "source": {"kind": "port", "index": 0},
                     "kind": "unconditional",
                     "provenance": {"status": "claim", "ref": "test"}},
                    {"output": 1, "source": {"kind": "property", "name": "a"},
                     "kind": "unconditional",
                     "provenance": {"status": "claim", "ref": "test"}},
                ],
                "review": {"status": "approved", "reviewer": "test", "date": "2026-10-30"},
            },
        },
    })


def test_influence_returns_chain_with_functional_hops():
    index = ModelIndex(parse_xprt(MODEL))
    result = influence(index, _semantic_registry(), "main::S:0")
    chains = [item for item in result.items
              if item["source"]["address"].startswith("main::K@property:a")]
    assert chains
    chain = chains[0]
    assert chain["source"]["kind"] == "property"
    assert [hop["kind"] for hop in chain["hops"]] == ["unconditional", "unconditional"]
    assert chain["evidence"]["status"] == "contract"
```

Вынесите словарь классов из `_semantic_registry()` в `_semantic_data()`:
Task 5 копирует его и меняет `review`/`provenance`, не мутируя исходный.

- [ ] **Step 2: Убедиться, что тест падает**

Run:
```bash
python3 -m pytest tests/unit/test_model_ir_semantics.py::test_influence_returns_chain_with_functional_hops -v
```
Expected: FAIL, модуль или функция отсутствует.

- [ ] **Step 3: Реализовать минимальный `influence`**

Алгоритм:
- нормализовать target в один выходной порт (`объект:индекс` или объект с одним выходом);
- идти назад: на входном порту брать обратные структурные рёбра; на выходе блока брать `dependencies_for` и фильтровать по `output`;
- каждый функциональный переход добавлять в `hops` с `kind`, `condition`, `state`, `evidence`;
- свойство или состояние добавлять как терминальный источник;
- `path` собирать из адресов объектов, включая границы;
- `evidence.status` цепочки: `contract`, если все функциональные хопы `contract`, иначе `not_established`;
- `known_absences` собирать отдельно;
- неизвестный контракт добавлять в `unknown` и не продолжать.

- [ ] **Step 4: Прогнать тест**

Run:
```bash
python3 -m pytest tests/unit/test_model_ir_semantics.py::test_influence_returns_chain_with_functional_hops -v
```
Expected: PASS.

- [ ] **Step 5: Добавить тест сохранения типов хопов**

```python
def test_influence_keeps_each_hop_kind():
    # Цепочка: свойство a -> усилитель -> сумматор -> выход.
    # Первый хоп unconditional, второй conditional.
    ...
```
Собрать модель с сумматором; контракт сумматора имеет `conditional` зависимость. Проверить:
```python
assert [hop["kind"] for hop in chain["hops"]] == ["conditional", "unconditional"]
```
Run:
```bash
python3 -m pytest tests/unit/test_model_ir_semantics.py -q
```
Expected: PASS.

- [ ] **Step 6: Коммит**

```bash
git add simintech_api/model_ir/semantics.py simintech_api/model_ir/__init__.py tests/unit/test_model_ir_semantics.py
git commit -m "feat(model-ir): запрос influence с цепочками и провенансом"
```

---

### Task 5: Статусы, скрипты, условия и отсутствия

**Files:**
- Modify: `simintech_api/model_ir/semantics.py`
- Test: `tests/unit/test_model_ir_semantics.py`

**Interfaces:**
- Consumes: `Dependency.kind`, `Dependency.condition`, `Dependency.state`, `Dependency.reason`, `Dependency.provenance`, `BlockContract.review`, `ModelObject.scripts`.
- Produces: те же `influence` и `QueryResult`, но с правилами статусов.

- [ ] **Step 1: Написать падающие тесты**

Добавить:
```python
def _with_review(registry, class_name, status):
    """Копия реестра с другим review.status."""
    data = copy.deepcopy(_semantic_data())
    data[class_name]["review"]["status"] = status
    return BlockContractRegistry({
        "schema": "block-contract/2", "version": 2,
        "classes": data, "meta": {},
    })


def _with_dependency_provenance(registry, class_name, status):
    """Копия реестра с другим provenance первой зависимости."""
    data = copy.deepcopy(_semantic_data())
    data[class_name]["dependencies"][0]["provenance"]["status"] = status
    return BlockContractRegistry({
        "schema": "block-contract/2", "version": 2,
        "classes": data, "meta": {},
    })


def test_influence_preliminary_row_is_not_contract():
    registry = _semantic_registry()
    registry = _with_review(registry, "Усилитель", "preliminary")
    result = influence(ModelIndex(parse_xprt(MODEL)), registry, "main::S:0")
    assert result.items[0]["evidence"]["status"] == "not_established"
    assert result.items[0]["evidence"]["reason"] == "unapproved"


def test_influence_structural_measured_does_not_upgrade_functional():
    # status: measured, но provenance зависимости: derived без approved
    registry = _with_dependency_provenance(
        _semantic_registry(), "Усилитель", "derived")
    result = influence(ModelIndex(parse_xprt(MODEL)), registry, "main::S:0")
    assert result.items[0]["evidence"]["status"] == "not_established"


def test_influence_script_preserves_kind_and_reason():
    # Блок с непустым Script в объекте.
    ...
    assert result.items[0]["hops"][-1]["kind"] == "script"
    assert result.items[0]["hops"][-1]["evidence"]["reason"] == "object_script"
    assert result.items[0]["evidence"]["status"] == "not_established"


def test_influence_conditional_keeps_condition():
    ...
    assert result.items[0]["hops"][0]["condition"]["op"] == "select"


def test_influence_unknown_condition_is_not_established():
    # Контракт: conditional, condition=None, reason=condition_unknown.
    ...
    assert result.items[0]["hops"][0]["kind"] == "conditional"
    assert result.items[0]["hops"][0]["condition"] is None
    assert result.items[0]["hops"][0]["evidence"]["reason"] == "condition_unknown"
    assert result.items[0]["evidence"]["status"] == "not_established"


def test_influence_stateful_keeps_state():
    ...
    assert result.items[0]["hops"][0]["kind"] == "stateful"
    assert result.items[0]["hops"][0]["state"]["kind"] == "history"


def test_influence_known_absence_is_separate():
    ...
    assert result.items == ()
    assert result.evidence["known_absences"][0]["source"]["index"] == 2
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run:
```bash
python3 -m pytest tests/unit/test_model_ir_semantics.py -q -k "preliminary or script or conditional or stateful or absence"
```
Expected: FAIL.

- [ ] **Step 3: Реализовать правила статусов**

- `measured` учитывается только в `Dependency.provenance`; `contract.status` и `ports.provenance` не участвуют;
- `claim` требует `review.status == approved`;
- `derived` требует `review.status == approved`;
- `preliminary` всегда `not_established`;
- `script` сохраняет `kind: script`, `reason: object_script`;
- `known_absences` не попадают в `items`;
- `stateful` без `state` уже отвергнут валидатором.

- [ ] **Step 4: Прогнать тесты**

Run:
```bash
python3 -m pytest tests/unit/test_model_ir_semantics.py -q
```
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add simintech_api/model_ir/semantics.py tests/unit/test_model_ir_semantics.py
git commit -m "feat(model-ir): статусы contract/not_established и отдельные отсутствия"
```

---

### Task 6: Границы субмоделей, память и циклы

**Files:**
- Modify: `simintech_api/model_ir/semantics.py`
- Test: `tests/unit/test_model_ir_semantics.py`

**Interfaces:**
- Consumes: `SignalEdge.kind == "boundary"`, `SignalEdge.kind == "memory"`, `ModelIndex.model.memory_links`.
- Produces: `influence` проходит границу, добавляет `stateful` для памяти и терминальный `unknown` для цикла.

- [ ] **Step 1: Написать падающие тесты**

```python
from test_model_ir_graph import CYCLE, MEMORY


def test_influence_boundary_without_contract_is_not_established():
    # SUB_MODEL: субмодель Sub (класс Субмодель) с внешними u/y,
    # внутри порт-блоки и блок K класса Неизвестный.
    index = ModelIndex(parse_xprt(SUB_MODEL))
    result = influence(index, _submodel_registry(), "main::Sub:1")
    assert all(item["evidence"]["status"] != "contract" for item in result.items)
    assert any("class_unknown" in item for item in result.unknown)


def test_influence_memory_edge_is_stateful():
    index = ModelIndex(parse_xprt(MEMORY))
    result = influence(index, _empty_registry(), "main::From:0")
    hops = [hop for item in result.items for hop in item["hops"]]
    assert any(hop["kind"] == "stateful" and hop["state"]["kind"] == "memory"
               for hop in hops)


def test_influence_cycle_stops_unknown():
    index = ModelIndex(parse_xprt(CYCLE))
    result = influence(index, _semantic_registry(), "main::A:1")
    assert any("cycle" in item for item in result.unknown)


def test_influence_submodel_known_contract_two_branches():
    # SUB_KEY: субмодель с контрактом control + selected_input(mapping),
    # внутри Key3 класса Ключ-3 без контракта.
    index = ModelIndex(parse_xprt(SUB_KEY))
    result = influence(index, _key_registry(), "main::Sub:2")
    control = [item for item in result.items
               if any(hop["kind"] == "control" for hop in item["hops"])]
    branches = [item for item in result.items
                if any(hop["kind"] == "conditional" for hop in item["hops"])]
    assert len(control) == 1
    assert len(branches) == 2
    assert {hop["condition"]["cases"][0]["value"]
            for item in branches for hop in item["hops"]
            if hop["kind"] == "conditional"} == {0, 1}
    assert control[0]["evidence"]["status"] == "contract"
    assert all(item["evidence"]["status"] == "not_established"
               for item in branches)
    assert any("class_unknown" in item for item in result.unknown)
```

`SUB_MODEL`, `SUB_KEY`, `_submodel_registry`, `_empty_registry` и `_key_registry`
строятся в этом же файле по образцу `MODEL` из Task 4. `SUB_KEY` содержит
внешние `inport_1`, `control`, `inport_2`, `outport`, источник на `control`
и внутренний `Key3` класса `Ключ-3`; контракт
`Ключ управляемый перекидной по входам тип 2` утверждён, `selected_input`
имеет `mapping` на две ветви.

- [ ] **Step 2: Убедиться, что тесты падают**

Run:
```bash
python3 -m pytest tests/unit/test_model_ir_semantics.py -q -k "boundary or memory or cycle"
```
Expected: FAIL.

- [ ] **Step 3: Реализовать обход**

- На выходном порту, у которого есть входящее `memory`-ребро, идти по нему раньше контракта: ребро даёт хоп `stateful` с `state: {"kind": "memory"}`;
- на выходном порту субмодели сначала добавить внешние функциональные хопы по контракту, затем пройти `boundary` внутрь страницы;
- внешняя субмодель без страницы даёт терминальный `unknown` с причиной `external_submodel`;
- внутренний `unknown` понижает цепочку до `not_established`, даже если внешний контракт дал `contract`;
- повтор порта на текущем пути даёт терминальный `unknown` с причиной `cycle` и не продолжается;
- превышение `max_depth` даёт `unknown` с причиной `depth_limit`.

- [ ] **Step 4: Прогнать тесты**

Run:
```bash
python3 -m pytest tests/unit/test_model_ir_semantics.py -q
```
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add simintech_api/model_ir/semantics.py tests/unit/test_model_ir_semantics.py
git commit -m "feat(model-ir): границы субмоделей, память и циклы в influence"
```

---

### Task 7: `semantic_coverage`

**Files:**
- Modify: `simintech_api/model_ir/semantics.py`
- Modify: `simintech_api/model_ir/__init__.py`
- Test: `tests/unit/test_model_ir_semantics.py`

**Interfaces:**
- Produces: `semantic_coverage(model: ModelIR, registry: BlockContractRegistry | None = None) -> dict[str, Any]` с полями:
  - `objects_total`, `objects_with_behavior`, `objects_with_approved_behavior`, `objects_with_known_ports`;
  - `objects_unknown` с причинами `class_unknown`, `object_script`, `script_defined`, `external_submodel`, `behavior_unknown`, `unapproved`;
  - `dependencies_total`, `dependencies_known`, `known_absences_total`;
  - `pilot_scope_counts` по `live_acceptance`/`synthetic_only`/`auxiliary`;
  - `by_class` с `objects`, `with_behavior`, `approved`, `pilot_scope`.

- [ ] **Step 1: Написать падающие тесты**

```python
def test_semantic_coverage_separates_approved_and_unknown():
    index = ModelIndex(parse_xprt(MODEL))
    data = semantic_coverage(index.model, _semantic_registry())
    assert data["objects_total"] == 3
    assert data["objects_with_behavior"] == 2
    assert data["objects_with_approved_behavior"] == 2
    assert data["objects_unknown"]["behavior_unknown"] == 1
```

```python
def test_semantic_coverage_counts_object_script():
    # Класс «Язык программирования» и непустой Script у экземпляра:
    # более конкретная причина object_script важнее script_defined.
    ...
    assert data["objects_unknown"]["object_script"] == 1
    assert data["objects_unknown"].get("script_defined", 0) == 0


def test_semantic_coverage_pilot_scope_counts_auxiliary():
    # Ключ-3 с pilot_scope: auxiliary.
    ...
    assert data["pilot_scope_counts"]["auxiliary"] == 1
    assert data["pilot_scope_counts"].get("live_acceptance", 0) == 0
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run:
```bash
python3 -m pytest tests/unit/test_model_ir_semantics.py -q -k semantic_coverage
```
Expected: FAIL.

- [ ] **Step 3: Реализовать подсчёт**

- объекты: `kind in (BLOCK, SUBMODEL, UNKNOWN)`;
- `dependencies_total` считается после `dependencies_for`;
- `dependencies_known` учитывает `measured`/`claim` и `derived` с approved;
- каждый объект попадает ровно в одну причину `objects_unknown` в порядке: `class_unknown`, `object_script`, `script_defined`, `external_submodel`, `behavior_unknown`, `unapproved`;
- `pilot_scope_counts` считает классы, у которых `pilot_scope` непустой; `auxiliary` не входит в `live_acceptance`;
- `by_class` содержит `objects`, `with_behavior`, `approved`, `pilot_scope`.

- [ ] **Step 4: Прогнать тесты**

Run:
```bash
python3 -m pytest tests/unit/test_model_ir_semantics.py -q
```
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add simintech_api/model_ir/semantics.py simintech_api/model_ir/__init__.py tests/unit/test_model_ir_semantics.py
git commit -m "feat(model-ir): semantic_coverage с причинами неизвестности"
```

---

### Task 8: Секция `semantics` в паспорте

**Files:**
- Modify: `simintech_api/model_ir/manifest.py`
- Test: `tests/unit/test_model_ir_manifest.py`

**Interfaces:**
- Consumes: `semantic_coverage`.
- Produces: секция `## Semantics` в `build_manifest`; `focus="semantics"`.

- [ ] **Step 1: Написать падающий тест**

```python
def test_manifest_has_semantics_section():
    model = build_model_ir(xprt=parse_xprt(MODEL))
    text = build_manifest(model, budget_tokens=3000)
    assert "## Semantics" in text
    assert "objects_with_approved_behavior" in text
```

- [ ] **Step 2: Убедиться, что тест падает**

Run:
```bash
python3 -m pytest tests/unit/test_model_ir_manifest.py::test_manifest_has_semantics_section -v
```
Expected: FAIL.

- [ ] **Step 3: Реализовать секцию**

- `_semantics(model)` возвращает строки счётчиков;
- добавить `"semantics"` в `_FOCUS`;
- добавить `("semantics", _semantics(model))` в `optional`;
- секция участвует в бюджете и может попасть в `Omitted`.

- [ ] **Step 4: Прогнать тесты**

Run:
```bash
python3 -m pytest tests/unit/test_model_ir_manifest.py -q
```
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add simintech_api/model_ir/manifest.py tests/unit/test_model_ir_manifest.py
git commit -m "feat(model-ir): семантическое покрытие в паспорте модели"
```

---

### Task 8b: Схема `BehaviorSpec`

**Files:**
- Modify: `simintech_api/model_ir/semantics.py`
- Modify: `simintech_api/model_ir/__init__.py`
- Test: `tests/unit/test_model_ir_semantics.py`

**Interfaces:**
- Produces:
  - `BehaviorScenario(id: str, target: str, inputs: tuple[str, ...], checks: tuple[Mapping[str, Any], ...])`
  - `BehaviorSpec(schema: str, model_hash: str, scenarios: tuple[BehaviorScenario, ...])`
  - `parse_behavior_spec(data: Mapping[str, Any]) -> BehaviorSpec`

- [ ] **Step 1: Написать падающий тест**

```python
def test_behavior_spec_parses_scenarios():
    spec = parse_behavior_spec({
        "schema": "behavior-spec/1",
        "model_hash": "abc",
        "scenarios": [{
            "id": "speed_response",
            "target": "main::S:0",
            "inputs": ["main::K:0"],
            "checks": [{"op": "changed"}],
        }],
    })
    assert spec.schema == "behavior-spec/1"
    assert spec.scenarios[0].id == "speed_response"
    assert spec.scenarios[0].checks[0]["op"] == "changed"
```

- [ ] **Step 2: Убедиться, что тест падает**

Run:
```bash
python3 -m pytest tests/unit/test_model_ir_semantics.py::test_behavior_spec_parses_scenarios -v
```
Expected: FAIL.

- [ ] **Step 3: Реализовать разбор**

- `schema` обязан быть `behavior-spec/1`;
- `model_hash` непустой;
- у сценария обязательны `id` и `target`;
- `inputs` и `checks` могут быть пустыми;
- `checks` не исполняются, только хранятся.

- [ ] **Step 4: Прогнать тесты**

Run:
```bash
python3 -m pytest tests/unit/test_model_ir_semantics.py -q
```
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add simintech_api/model_ir/semantics.py simintech_api/model_ir/__init__.py tests/unit/test_model_ir_semantics.py
git commit -m "feat(model-ir): схема BehaviorSpec для сценариев модели"
```

---

### Task 9: Эталонная таблица и перенос в контракты

**Files:**
- Create: `tests/fixtures/semantics/pilot_blocks.yaml`
- Create: `scripts/merge_pilot_semantics.py`
- Test: `tests/unit/test_pilot_semantics_table.py`
- Modify: `simintech_api/data/block_contracts.json` (девять живых классов и `Ключ-3`; коммутатор не переносится)

**Interfaces:**
- Consumes: YAML-таблица, `block_contracts.json`.
- Produces:
  - `scripts/merge_pilot_semantics.py --check` возвращает 0 при совпадении и 1 при расхождении;
  - `scripts/merge_pilot_semantics.py --write` переносит таблицу в JSON;
  - `pilot_blocks.yaml` с `scope: live_acceptance|synthetic_only`.

- [ ] **Step 1: Создать черновик таблицы**

Схема:
```yaml
schema: pilot-semantics/1
classes:
  Константа:
    scope: live_acceptance
    behavior:
      operation: constant
      expression: "y = a"
      parameters: [a]
      provenance: {status: derived, ref: "block_catalog"}
    dependencies:
      - output: 0
        source: {kind: property, name: a}
        kind: unconditional
        provenance: {status: derived, ref: "block_catalog"}
    known_absences: []
    review: {status: preliminary, reviewer: "", date: ""}
```
Десять строк: восемь базовых, ключ типа 2, коммутатор по номеру порта.
У ключа типа 2 зависимости `control` и `selected_input` без `mapping`;
до эксперимента `condition: null`, `reason: condition_unknown`.
`Ключ-3` добавить отдельным ключом с `scope: auxiliary`, без счёта десяти:
behavior `select`, зависимости `control` и две `conditional`; значение
`control` не заполняется до эксперимента, ставится `condition: null`,
`reason: condition_unknown`. Все строки начинают с
`review.status: preliminary`; автор не подтверждает сам себя.

- [ ] **Step 2: Написать падающий тест схемы и дрейфа**

```python
def test_pilot_table_has_ten_classes_and_scopes():
    table = yaml.safe_load(TABLE.read_text(encoding="utf-8"))
    classes = table["classes"]
    assert len([name for name, row in classes.items()
                if row["scope"] != "auxiliary"]) == 10
    assert classes["Коммутатор входных сигналов по номеру порта"]["scope"] == "synthetic_only"
    assert classes["Ключ управляемый перекидной по входам тип 2"]["scope"] == "live_acceptance"
    assert classes["Ключ-3"]["scope"] == "auxiliary"


def test_auxiliary_scope_is_preserved():
    registry = load_default_contracts()
    assert registry.require("Ключ-3").pilot_scope == "auxiliary"


def test_pilot_table_matches_registry():
    assert subprocess.run(
        [sys.executable, "scripts/merge_pilot_semantics.py", "--check"],
        capture_output=True).returncode == 0
```

- [ ] **Step 3: Убедиться, что тесты падают**

Run:
```bash
python3 -m pytest tests/unit/test_pilot_semantics_table.py -q
```
Expected: FAIL.

- [ ] **Step 4: Реализовать merge-скрипт**

- читает YAML и JSON;
- переносит `behavior`, `dependencies`, `signal_types`, `review`, `known_absences`, `pilot_scope` только для `scope: live_acceptance` и `scope: auxiliary`;
- `scope` из YAML записывает в `pilot_scope` контракта;
- `synthetic_only` не переносит в production-реестр: контракт коммутатора живёт в `tests/fixtures/semantics/commutator_contract.json` (Task 10);
- добавляет `pilot:<date>` в `provenance`;
- `--check` сравнивает поля только для `live_acceptance` и `auxiliary` и печатает расхождения;
- `--write` пишет JSON без переупорядочивания остальных ключей.

- [ ] **Step 5: Прогнать тесты**

Run:
```bash
python3 scripts/merge_pilot_semantics.py --write
python3 scripts/merge_pilot_semantics.py --check
python3 -m pytest tests/unit/test_pilot_semantics_table.py tests/unit/test_model_ir_contracts.py -q
```
Expected: PASS. Строки `preliminary` дают `not_established`, не `contract`. Коммутатор остаётся вне production-реестра.

- [ ] **Step 6: Коммит**

```bash
git add tests/fixtures/semantics/pilot_blocks.yaml scripts/merge_pilot_semantics.py tests/unit/test_pilot_semantics_table.py simintech_api/data/block_contracts.json
git commit -m "feat(model-ir): эталонная таблица семантики и перенос в контракты"
```

---

### Task 10: Синтетический коммутатор и `nport_named`

**Files:**
- Modify: `simintech_api/model_ir/contracts.py` (тестовая портовая модель)
- Create: `tests/fixtures/semantics/commutator_contract.json`
- Create: модель коммутатора строкой в `tests/unit/test_model_ir_commutator.py`
- Create: `tests/fixtures/semantics/synthetic_questions.yaml`
- Test: `tests/unit/test_model_ir_commutator.py`

**Interfaces:**
- Produces:
  - `PortContract(model="nport_named", nport_property="nport")`;
  - `ports_for` раскрывает `number` + `data_1..data_n` + `outport`;
  - `influence` на синтетической модели находит управляющую зависимость `number` и условную зависимость `data_i`.

- [ ] **Step 1: Написать падающий тест `nport_named`**

```python
COMMUTATOR_CONTRACT = (
    Path(__file__).resolve().parents[2]
    / "tests" / "fixtures" / "semantics" / "commutator_contract.json")
QUESTIONS = (
    Path(__file__).resolve().parents[2]
    / "tests" / "fixtures" / "semantics" / "synthetic_questions.yaml")


def test_nport_named_ports_expand():
    registry = BlockContractRegistry(json.loads(
        COMMUTATOR_CONTRACT.read_text(encoding="utf-8")))
    ports = registry.ports_for(
        "Коммутатор входных сигналов по номеру порта", {"nport": "3"})
    assert [(p.index, p.name) for p in ports.inputs] == [
        (0, "number"), (1, "data_1"), (2, "data_2"), (3, "data_3")]
    assert [(p.index, p.name) for p in ports.outputs] == [(0, "outport")]
```

- [ ] **Step 2: Убедиться, что тест падает**

Run:
```bash
python3 -m pytest tests/unit/test_model_ir_commutator.py::test_nport_named_ports_expand -v
```
Expected: FAIL.

- [ ] **Step 3: Реализовать `nport_named`**

- добавить модель в `_ALLOWED_PORT_MODELS`;
- в `ports_for` раскрывать входы: `number` с индексом 0, `data_i` с индексами 1..n;
- выходы брать из контракта;
- валидатор требует `nport_property`.

- [ ] **Step 4: Написать тест синтетического influence**

Модель: коммутатор с тремя `data` входами, выход в график. Контракт:
- `pilot_scope: synthetic_only`;
- `control` для `number`;
- `conditional` для `selected_input` с `mapping`
  `[{value: 1, input: 1}, {value: 2, input: 2}, {value: 3, input: 3}]`
  и `condition.op = select`.
Проверить:
```python
assert any(item["source"]["address"].endswith(":0") and
           any(hop["kind"] == "control" for hop in item["hops"])
           for item in result.items)
assert any(hop["kind"] == "conditional" and hop["condition"]["op"] == "select"
           for item in result.items for hop in item["hops"])
```

- [ ] **Step 4b: Добавить тест публичных вопросов**

```python
def test_synthetic_questions_are_public_and_expected_unknowns():
    text = QUESTIONS.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert data["schema"] == "synthetic-questions/1"
    assert data["questions"]
    assert data["questions"][0]["expected_unknown"]
    assert "internal" not in text.lower()
```
Run:
```bash
python3 -m pytest tests/unit/test_model_ir_commutator.py -q
```
Expected: PASS.

- [ ] **Step 5: Прогнать тесты**

Run:
```bash
python3 -m pytest tests/unit/test_model_ir_commutator.py -q
```
Expected: PASS.

- [ ] **Step 6: Коммит**

```bash
git add simintech_api/model_ir/contracts.py tests/fixtures/semantics tests/unit/test_model_ir_commutator.py
git commit -m "feat(model-ir): синтетический коммутатор с nport_named"
```

---

### Task 11: Релиз ядра

**Files:**
- Modify: `simintech_api/__init__.py` (версия)
- Modify: `docs/knowledge/11-model-ir.md` (краткая запись о новых запросах)
- Test: полный набор.

- [ ] **Step 1: Поднять версию**

`__version__ = "0.19.0"`.

- [ ] **Step 2: Полный прогон**

```bash
python3 -m pytest -q
python3 -m pytest -m performance -q
flake8 simintech_api tests
mypy simintech_api
```
Expected: новые тесты зелёные; известные падения не выросли.

- [ ] **Step 3: Проверить дрейф таблицы**

```bash
python3 scripts/merge_pilot_semantics.py --check
```
Expected: 0.

- [ ] **Step 4: Коммит и PR**

```bash
git add simintech_api/__init__.py docs/knowledge/11-model-ir.md
git commit -m "release(model-ir): 0.19.0 с функциональной семантикой"
git push -u origin feat/functional-semantics-core
```
Создать issue и PR по правилам репозитория: `Closes #N` первой строкой, без атрибуции Claude, без длинного тире, `public_data_check.py` перед push. После merge поставить тег `v0.19.0`.

---

## Что осталось для второго плана

- MCP-обвязка `query_model` (`influence`, `semantic_coverage`), `load_model`.
- Пин `simintech-api==0.19.0`.
- Живая приёмка на копии привода: девять классов, ключ типа 2, две ветви управления.
- Внутренние свидетельства и отчёт приёмки.
- Проверка владельцем строк таблицы: `preliminary` -> `approved`.
