"""Model IR: функциональное влияние входов на выход."""

import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from simintech_api.model_ir import (  # noqa: E402
    SCHEMA,
    VERSION,
    BlockContractRegistry,
    ModelIndex,
    ModelQueryError,
    parse_xprt,
)
from simintech_api.model_ir.semantics import (  # noqa: E402
    influence,
    parse_behavior_spec,
    semantic_coverage,
)

from test_model_ir_graph import (  # noqa: E402
    CYCLE,
    MEMORY,
    MODEL as GRAPH_MODEL,
)

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


def _semantic_data():
    return {
        "Константа": {
            "class": "Константа", "status": "derived",
            "ports": {"model": "fixed", "inputs": [],
                      "outputs": [{"index": 0, "name": "y",
                                   "direction": "out"}]},
            "behavior": {"operation": "constant", "expression": "y = a",
                         "parameters": ["a"],
                         "provenance": {"status": "claim", "ref": "test"}},
            "dependencies": [{
                "output": 0,
                "source": {"kind": "property", "name": "a"},
                "kind": "unconditional",
                "provenance": {"status": "claim", "ref": "test"},
            }],
            "review": {"status": "approved", "reviewer": "test",
                       "date": "2026-10-31"},
        },
        "Усилитель": {
            "class": "Усилитель", "status": "derived",
            "ports": {"model": "fixed",
                      "inputs": [{"index": 0, "name": "u",
                                  "direction": "in"}],
                      "outputs": [{"index": 1, "name": "y",
                                   "direction": "out"}]},
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
            "review": {"status": "approved", "reviewer": "test",
                       "date": "2026-10-31"},
        },
        "Временной график": {
            "class": "Временной график", "status": "derived",
            "ports": {"model": "unknown", "reason": "not_observed"},
            "behavior": {"operation": "unknown"},
            "review": {"status": "preliminary", "reviewer": "", "date": ""},
        },
    }


def _semantic_registry(data=None):
    return BlockContractRegistry({
        "schema": SCHEMA, "version": VERSION,
        "classes": data if data is not None else _semantic_data(),
        "meta": {},
    })


def _chain_to(result, prefix):
    chains = [item for item in result.items
              if item["source"]["address"].startswith(prefix)]
    assert chains, result.items
    return chains[0]


def test_influence_returns_chain_with_functional_hops():
    index = ModelIndex(parse_xprt(MODEL))
    result = influence(index, _semantic_registry(), "main::S:0")
    chain = _chain_to(result, "main::K@property:a")
    assert chain["source"]["kind"] == "property"
    assert [hop["kind"] for hop in chain["hops"]] == [
        "unconditional", "unconditional"]
    assert chain["evidence"]["status"] == "contract"


def test_influence_keeps_each_hop_kind():
    data = copy.deepcopy(_semantic_data())
    data["Усилитель"]["dependencies"][0]["kind"] = "conditional"
    data["Усилитель"]["dependencies"][0]["condition"] = {
        "op": "equals",
        "source": {"kind": "property", "name": "a"},
        "value": 0,
    }
    result = influence(
        ModelIndex(parse_xprt(MODEL)), _semantic_registry(data), "main::S:0")
    chain = _chain_to(result, "main::K@property:a")
    assert [hop["kind"] for hop in chain["hops"]] == [
        "conditional", "unconditional"]


def test_influence_unknown_contract_returns_unknown():
    data = copy.deepcopy(_semantic_data())
    data.pop("Усилитель")
    result = influence(
        ModelIndex(parse_xprt(MODEL)), _semantic_registry(data), "main::S:0")
    assert all(item["evidence"]["status"] != "contract"
               for item in result.items)
    assert any("class_unknown" in item for item in result.unknown)


def _with_review(registry, class_name, status):
    data = copy.deepcopy(_semantic_data())
    data[class_name]["review"]["status"] = status
    return _semantic_registry(data)


def _with_dependency_provenance(registry, class_name, status,
                                review="approved"):
    data = copy.deepcopy(_semantic_data())
    data[class_name]["dependencies"][0]["provenance"]["status"] = status
    data[class_name]["review"]["status"] = review
    return _semantic_registry(data)


def test_influence_preliminary_row_is_not_contract():
    registry = _with_review(_semantic_registry(), "Усилитель", "preliminary")
    result = influence(ModelIndex(parse_xprt(MODEL)), registry, "main::S:0")
    chain = _chain_to(result, "main::K@property:a")
    assert chain["evidence"]["status"] == "not_established"
    assert chain["evidence"]["reason"] == "unapproved"


def test_influence_structural_measured_does_not_upgrade_functional():
    registry = _with_dependency_provenance(
        _semantic_registry(), "Усилитель", "derived", review="preliminary")
    result = influence(ModelIndex(parse_xprt(MODEL)), registry, "main::S:0")
    chain = _chain_to(result, "main::K@property:a")
    assert chain["evidence"]["status"] == "not_established"


SCRIPT_MODEL = MODEL.replace(
    "</ports>\n  </object>\n  <object><name>`G`</name>",
    "</ports>\n    <script>y := a;</script>\n  </object>\n"
    "  <object><name>`G`</name>",
    1,
)


def test_influence_script_preserves_kind_and_reason():
    result = influence(
        ModelIndex(parse_xprt(SCRIPT_MODEL)), _semantic_registry(), "main::S:0")
    chain = _chain_to(result, "main::K@property:a")
    assert chain["hops"][-1]["kind"] == "script"
    assert chain["hops"][-1]["evidence"]["reason"] == "object_script"
    assert chain["evidence"]["status"] == "not_established"


def test_influence_conditional_keeps_condition():
    data = copy.deepcopy(_semantic_data())
    data["Усилитель"]["dependencies"][0]["kind"] = "conditional"
    data["Усилитель"]["dependencies"][0]["condition"] = {
        "op": "equals",
        "source": {"kind": "property", "name": "a"},
        "value": 0,
    }
    result = influence(
        ModelIndex(parse_xprt(MODEL)), _semantic_registry(data), "main::S:0")
    chain = _chain_to(result, "main::K@property:a")
    assert chain["hops"][0]["condition"]["op"] == "equals"


def test_influence_stateful_keeps_state():
    data = copy.deepcopy(_semantic_data())
    data["Усилитель"]["dependencies"][0]["kind"] = "stateful"
    data["Усилитель"]["dependencies"][0]["state"] = {
        "kind": "history", "window": "unbounded"}
    result = influence(
        ModelIndex(parse_xprt(MODEL)), _semantic_registry(data), "main::S:0")
    chain = _chain_to(result, "main::K@property:a")
    assert chain["hops"][0]["kind"] == "stateful"
    assert chain["hops"][0]["state"]["kind"] == "history"


def test_influence_unknown_condition_is_not_established():
    data = copy.deepcopy(_semantic_data())
    data["Усилитель"]["dependencies"][0]["kind"] = "conditional"
    data["Усилитель"]["dependencies"][0]["condition"] = None
    data["Усилитель"]["dependencies"][0]["reason"] = "condition_unknown"
    result = influence(
        ModelIndex(parse_xprt(MODEL)), _semantic_registry(data), "main::S:0")
    chain = _chain_to(result, "main::K@property:a")
    assert chain["hops"][0]["kind"] == "conditional"
    assert chain["hops"][0]["condition"] is None
    assert chain["hops"][0]["evidence"]["reason"] == "condition_unknown"
    assert chain["evidence"]["status"] == "not_established"


def test_influence_known_absence_is_separate():
    data = copy.deepcopy(_semantic_data())
    data["Усилитель"]["dependencies"] = []
    data["Усилитель"]["known_absences"] = [{
        "output": 1,
        "source": {"kind": "port", "index": 0},
        "provenance": {"status": "claim", "ref": "test"},
    }]
    result = influence(
        ModelIndex(parse_xprt(MODEL)), _semantic_registry(data), "main::S:0")
    assert result.items == ()
    assert result.evidence["known_absences"][0]["source"]["index"] == 0


SUB_MODEL = GRAPH_MODEL.replace("`Усилитель`", "`Неизвестный`")

SUB_KEY = """<Header><project><page>
  <object>
<name>`Ctrl`</name>
<class_name>`Константа`</class_name>
<obj_type>`100`</obj_type>
    <ports><port><name>`y`</name><mode>`1`</mode></port></ports>
  </object>
  <object>
<name>`S1`</name>
<class_name>`Константа`</class_name>
<obj_type>`100`</obj_type>
    <ports><port><name>`y`</name><mode>`1`</mode></port></ports>
  </object>
  <object>
<name>`S2`</name>
<class_name>`Константа`</class_name>
<obj_type>`100`</obj_type>
    <ports><port><name>`y`</name><mode>`1`</mode></port></ports>
  </object>
  <object>
<name>`Sub`</name>
<class_name>`Ключ управляемый перекидной по входам тип 2`</class_name>
<obj_type>`102`</obj_type>
    <ports>
      <port><name>`inport_1`</name><mode>`0`</mode></port>
      <port><name>`control`</name><mode>`0`</mode></port>
      <port><name>`outport`</name><mode>`1`</mode></port>
      <port><name>`inport_2`</name><mode>`0`</mode></port>
    </ports>
    <page><name></name>
      <object>
<name>`In1`</name>
<class_name>`Порт входа`</class_name>
<obj_type>`103`</obj_type>
        <ports><port><name>`inport_1`</name><mode>`1`</mode></port></ports>
      </object>
      <object>
<name>`InC`</name>
<class_name>`Порт входа`</class_name>
<obj_type>`103`</obj_type>
        <ports><port><name>`control`</name><mode>`1`</mode></port></ports>
      </object>
      <object>
<name>`In2`</name>
<class_name>`Порт входа`</class_name>
<obj_type>`103`</obj_type>
        <ports><port><name>`inport_2`</name><mode>`1`</mode></port></ports>
      </object>
      <object>
<name>`Key3`</name>
<class_name>`Ключ-3`</class_name>
<obj_type>`100`</obj_type>
        <ports>
          <port><name>`Port_1`</name><mode>`0`</mode></port>
          <port><name>`Port_2`</name><mode>`0`</mode></port>
          <port><name>`Port_3`</name><mode>`0`</mode></port>
          <port><name>`Port_0`</name><mode>`1`</mode></port>
        </ports>
      </object>
      <object>
<name>`Out`</name>
<class_name>`Порт выхода`</class_name>
<obj_type>`103`</obj_type>
        <ports><port><name>`outport`</name><mode>`0`</mode></port></ports>
      </object>
      <object>
<name>`w1`</name>
<class_name>`Математическая связь`</class_name>
<obj_type>`101`</obj_type>
        <start_bl_index>`0`</start_bl_index><start_port_index>`0`</start_port_index>
        <end_bl_index>`3`</end_bl_index><end_port_index>`0`</end_port_index>
      </object>
      <object>
<name>`w2`</name>
<class_name>`Математическая связь`</class_name>
<obj_type>`101`</obj_type>
        <start_bl_index>`1`</start_bl_index><start_port_index>`0`</start_port_index>
        <end_bl_index>`3`</end_bl_index><end_port_index>`1`</end_port_index>
      </object>
      <object>
<name>`w3`</name>
<class_name>`Математическая связь`</class_name>
<obj_type>`101`</obj_type>
        <start_bl_index>`2`</start_bl_index><start_port_index>`0`</start_port_index>
        <end_bl_index>`3`</end_bl_index><end_port_index>`2`</end_port_index>
      </object>
      <object>
<name>`w4`</name>
<class_name>`Математическая связь`</class_name>
<obj_type>`101`</obj_type>
        <start_bl_index>`3`</start_bl_index><start_port_index>`3`</start_port_index>
        <end_bl_index>`4`</end_bl_index><end_port_index>`0`</end_port_index>
      </object>
    </page>
  </object>
  <object>
<name>`Sink`</name>
<class_name>`Временной график`</class_name>
<obj_type>`106`</obj_type>
    <ports><port><name>`u`</name><mode>`0`</mode></port></ports>
  </object>
  <object>
<name>`W1`</name>
<class_name>`Математическая связь`</class_name>
<obj_type>`101`</obj_type>
    <start_bl_index>`0`</start_bl_index><start_port_index>`0`</start_port_index>
    <end_bl_index>`3`</end_bl_index><end_port_index>`1`</end_port_index>
  </object>
  <object>
<name>`W2`</name>
<class_name>`Математическая связь`</class_name>
<obj_type>`101`</obj_type>
    <start_bl_index>`1`</start_bl_index><start_port_index>`0`</start_port_index>
    <end_bl_index>`3`</end_bl_index><end_port_index>`0`</end_port_index>
  </object>
  <object>
<name>`W3`</name>
<class_name>`Математическая связь`</class_name>
<obj_type>`101`</obj_type>
    <start_bl_index>`2`</start_bl_index><start_port_index>`0`</start_port_index>
    <end_bl_index>`3`</end_bl_index><end_port_index>`3`</end_port_index>
  </object>
  <object>
<name>`W4`</name>
<class_name>`Математическая связь`</class_name>
<obj_type>`101`</obj_type>
    <start_bl_index>`3`</start_bl_index><start_port_index>`2`</start_port_index>
    <end_bl_index>`4`</end_bl_index><end_port_index>`0`</end_port_index>
  </object>
</page></project></Header>"""


def _empty_registry():
    return BlockContractRegistry({
        "schema": SCHEMA, "version": VERSION, "classes": {}, "meta": {},
    })


def _submodel_registry():
    return BlockContractRegistry({
        "schema": SCHEMA, "version": VERSION, "meta": {},
        "classes": {"Субмодель": {
            "class": "Субмодель", "status": "derived",
            "ports": {"model": "submodel",
                      "inputs": [{"index": 0, "name": "x",
                                  "direction": "in"}],
                      "outputs": [{"index": 1, "name": "y",
                                   "direction": "out"}]},
            "review": {"status": "preliminary", "reviewer": "", "date": ""},
        }},
    })


def _key_registry():
    data = copy.deepcopy(_semantic_data())
    data["Ключ управляемый перекидной по входам тип 2"] = {
        "class": "Ключ управляемый перекидной по входам тип 2",
        "status": "derived",
        "ports": {
            "model": "submodel",
            "inputs": [
                {"index": 0, "name": "inport_1", "direction": "in"},
                {"index": 1, "name": "control", "direction": "in"},
                {"index": 3, "name": "inport_2", "direction": "in"},
            ],
            "outputs": [{"index": 2, "name": "outport",
                         "direction": "out"}],
        },
        "behavior": {"operation": "select", "expression": "y = select(control)",
                     "provenance": {"status": "claim", "ref": "help"}},
        "dependencies": [
            {"output": 2, "source": {"kind": "port", "index": 1},
             "kind": "control",
             "provenance": {"status": "claim", "ref": "help"}},
            {"output": 2,
             "source": {"kind": "port", "role": "selected_input",
                        "selector": {"kind": "port", "index": 1},
                        "mapping": [{"value": 0, "input": 0},
                                    {"value": 1, "input": 3}]},
             "kind": "conditional",
             "condition": {"op": "select",
                           "source": {"kind": "port", "index": 1}},
             "provenance": {"status": "claim", "ref": "help"}},
        ],
        "review": {"status": "approved", "reviewer": "test",
                   "date": "2026-10-31"},
    }
    return BlockContractRegistry({
        "schema": SCHEMA, "version": VERSION, "classes": data, "meta": {},
    })


def test_influence_boundary_without_contract_is_not_established():
    result = influence(
        ModelIndex(parse_xprt(SUB_MODEL)), _submodel_registry(),
        "main::Sub:1")
    assert all(item["evidence"]["status"] != "contract"
               for item in result.items)
    assert any("class_unknown" in item for item in result.unknown)


def test_influence_memory_edge_is_stateful():
    result = influence(
        ModelIndex(parse_xprt(MEMORY)), _empty_registry(), "main::From:0")
    hops = [hop for item in result.items for hop in item["hops"]]
    assert any(hop["kind"] == "stateful"
               and hop["state"]["kind"] == "memory" for hop in hops)


def test_influence_cycle_stops_unknown():
    result = influence(
        ModelIndex(parse_xprt(CYCLE)), _semantic_registry(), "main::A:1")
    assert any("cycle" in item for item in result.unknown)


def test_influence_submodel_known_contract_two_branches():
    result = influence(
        ModelIndex(parse_xprt(SUB_KEY)), _key_registry(), "main::Sub:2")
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


def test_semantic_coverage_separates_approved_and_unknown():
    data = semantic_coverage(parse_xprt(MODEL), _semantic_registry())
    assert data["objects_total"] == 3
    assert data["objects_with_behavior"] == 2
    assert data["objects_with_approved_behavior"] == 2
    assert data["objects_with_known_ports"] == 2
    assert data["objects_unknown"]["behavior_unknown"] == 1
    assert data["dependencies_total"] == 3
    assert data["dependencies_known"] == 3


def test_semantic_coverage_counts_object_script():
    data = semantic_coverage(parse_xprt(SCRIPT_MODEL), _semantic_registry())
    assert data["objects_unknown"]["object_script"] == 1
    assert data["objects_unknown"].get("script_defined", 0) == 0


def test_semantic_coverage_pilot_scope_counts_auxiliary():
    data = copy.deepcopy(_semantic_data())
    data["Константа"]["pilot_scope"] = "live_acceptance"
    data["Усилитель"]["pilot_scope"] = "live_acceptance"
    data["Ключ-3"] = {
        "class": "Ключ-3", "status": "derived", "pilot_scope": "auxiliary",
        "ports": {"model": "fixed", "inputs": [], "outputs": []},
        "behavior": {"operation": "select",
                     "provenance": {"status": "claim", "ref": "test"}},
        "dependencies": [{
            "output": 0,
            "source": {"kind": "port", "index": 0},
            "kind": "unconditional",
            "provenance": {"status": "claim", "ref": "test"},
        }],
        "review": {"status": "preliminary", "reviewer": "", "date": ""},
    }
    coverage = semantic_coverage(parse_xprt(MODEL), _semantic_registry(data))
    assert coverage["pilot_scope_counts"]["auxiliary"] == 1
    assert coverage["pilot_scope_counts"]["live_acceptance"] == 2


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


def test_behavior_spec_rejects_unknown_schema():
    with pytest.raises(ModelQueryError):
        parse_behavior_spec({"schema": "behavior-spec/2",
                             "model_hash": "abc", "scenarios": []})


def test_behavior_spec_requires_target():
    with pytest.raises(ModelQueryError):
        parse_behavior_spec({
            "schema": "behavior-spec/1",
            "model_hash": "abc",
            "scenarios": [{"id": "broken"}],
        })
