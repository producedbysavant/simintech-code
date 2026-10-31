"""Model IR: графовые запросы, инварианты и сравнение моделей."""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from simintech_api.model_ir import (  # noqa: E402
    ModelIndex,
    ModelQueryError,
    parse_xprt,
)

from model_ir_synth import flat_model  # noqa: E402

MODEL = """<Header><project><page>
  <object>
    <name>`Step`</name><class_name>`Ступенька`</class_name><obj_type>`100`</obj_type>
    <ports><port><name>`y`</name><mode>`1`</mode></port></ports>
  </object>
  <object>
    <name>`Sub`</name><class_name>`Субмодель`</class_name><obj_type>`102`</obj_type>
    <ports>
      <port><name>`x`</name><mode>`0`</mode></port>
      <port><name>`y`</name><mode>`1`</mode></port>
    </ports>
    <page><name></name>
      <object>
        <name>`In`</name><class_name>`Порт входа`</class_name><obj_type>`103`</obj_type>
        <ports><port><name>`x`</name><mode>`1`</mode></port></ports>
      </object>
      <object>
        <name>`K`</name><class_name>`Усилитель`</class_name><obj_type>`100`</obj_type>
        <ports>
          <port><name>`u`</name><mode>`0`</mode></port>
          <port><name>`y`</name><mode>`1`</mode></port>
        </ports>
      </object>
      <object>
        <name>`Out`</name>
        <class_name>`Порт выхода`</class_name>
        <obj_type>`103`</obj_type>
        <ports><port><name>`y`</name><mode>`0`</mode></port></ports>
      </object>
      <object>
        <name>`w1`</name>
        <class_name>`Математическая связь`</class_name>
        <obj_type>`101`</obj_type>
        <start_bl_index>`0`</start_bl_index>
        <start_port_index>`0`</start_port_index>
        <end_bl_index>`1`</end_bl_index><end_port_index>`0`</end_port_index>
      </object>
      <object>
        <name>`w2`</name>
        <class_name>`Математическая связь`</class_name>
        <obj_type>`101`</obj_type>
        <start_bl_index>`1`</start_bl_index>
        <start_port_index>`1`</start_port_index>
        <end_bl_index>`2`</end_bl_index><end_port_index>`0`</end_port_index>
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
    <start_bl_index>`0`</start_bl_index>
    <start_port_index>`0`</start_port_index>
    <end_bl_index>`1`</end_bl_index><end_port_index>`0`</end_port_index>
  </object>
  <object>
    <name>`W2`</name>
    <class_name>`Математическая связь`</class_name>
    <obj_type>`101`</obj_type>
    <start_bl_index>`1`</start_bl_index>
    <start_port_index>`1`</start_port_index>
    <end_bl_index>`2`</end_bl_index><end_port_index>`0`</end_port_index>
  </object>
</page></project></Header>"""

MEMORY = """<Header><project><page>
  <object>
    <name>`To`</name><class_name>`В память`</class_name><obj_type>`104`</obj_type>
    <ports><port><name>`u`</name><mode>`0`</mode></port></ports>
    <visual_props><data><name>`PortNames`</name><value>`VAR`</value></data></visual_props>
  </object>
  <object>
    <name>`From`</name><class_name>`Из памяти`</class_name><obj_type>`105`</obj_type>
    <ports><port><name>`y`</name><mode>`1`</mode></port></ports>
    <visual_props><data><name>`PortNames`</name><value>`VAR`</value></data></visual_props>
  </object>
</page></project></Header>"""

CYCLE = """<Header><project><page>
  <object><name>`A`</name><class_name>`Усилитель`</class_name><obj_type>`100`</obj_type>
    <ports><port><name>`u`</name><mode>`0`</mode></port>
      <port><name>`y`</name><mode>`1`</mode></port></ports>
  </object>
  <object><name>`B`</name><class_name>`Усилитель`</class_name><obj_type>`100`</obj_type>
    <ports><port><name>`u`</name><mode>`0`</mode></port>
      <port><name>`y`</name><mode>`1`</mode></port></ports>
  </object>
  <object><name>`AB`</name>
    <class_name>`Математическая связь`</class_name>
    <obj_type>`101`</obj_type>
    <start_bl_index>`0`</start_bl_index>
    <start_port_index>`0`</start_port_index>
    <end_bl_index>`1`</end_bl_index><end_port_index>`0`</end_port_index>
  </object>
  <object><name>`BA`</name>
    <class_name>`Математическая связь`</class_name>
    <obj_type>`101`</obj_type>
    <start_bl_index>`1`</start_bl_index>
    <start_port_index>`1`</start_port_index>
    <end_bl_index>`0`</end_bl_index><end_port_index>`0`</end_port_index>
  </object>
</page></project></Header>"""

UNCONNECTED = """<Header><project><page>
  <object><name>`U`</name><class_name>`Усилитель`</class_name><obj_type>`100`</obj_type>
    <ports><port><name>`u`</name><mode>`0`</mode></port>
      <port><name>`y`</name><mode>`1`</mode></port></ports>
  </object>
</page></project></Header>"""


def test_inspect_trace_path_and_ancestors():
    index = ModelIndex(parse_xprt(MODEL))
    inspected = index.inspect_node("Step")
    assert inspected.items[0]["address"] == "main::Step"
    assert inspected.items[0]["ports"][0]["direction"] == "out"

    traced = index.trace_signal("Step")
    addresses = {item["address"] for item in traced.items}
    assert "main::Sink" in addresses
    assert "main/Sub::K" in addresses

    path = index.find_path("Step", "Sink")
    assert path.items[0]["path"][0] == "main::Step"
    assert path.items[0]["path"][-1] == "main::Sink"

    ancestors = index.ancestors("Sink")
    names = {item["address"] for item in ancestors.items}
    assert "main::Step" in names
    assert "main/Sub::K" in names


def test_memory_signal_crosses_portnames():
    index = ModelIndex(parse_xprt(MEMORY))
    traced = index.trace_signal("VAR")
    addresses = {item["address"] for item in traced.items}
    assert "main::To" in addresses
    assert "main::From" in addresses


def test_cycles_are_reported_not_error():
    index = ModelIndex(parse_xprt(CYCLE))
    cycles = index.find_cycles()
    assert cycles.items
    objects = set(cycles.items[0]["objects"])
    assert objects == {"main::A", "main::B"}


def test_check_connections_and_invariants():
    index = ModelIndex(parse_xprt(UNCONNECTED))
    check = index.check_connections()
    assert any(item["code"] == "unconnected_input"
               for item in check.items)
    invariants = index.validate_invariants([
        {"id": "inputs", "kind": "required_inputs_connected"},
        {"id": "contracts", "kind": "contract_ports_match"},
    ])
    statuses = {item["id"]: item["status"] for item in invariants.items}
    assert statuses["inputs"] == "failed"
    assert statuses["contracts"] == "not_evaluated"
    fanout = ModelIndex(parse_xprt(MODEL)).validate_invariants([
        {"id": "fanout", "kind": "max_fanout", "max": 0},
    ])
    assert fanout.items[0]["status"] == "failed"


def test_trace_both_returns_unique_nodes():
    index = ModelIndex(parse_xprt(flat_model(3).text))
    forward = {item["node"]
               for item in index.trace_signal("main::B1", "forward").items}
    backward = {item["node"]
                for item in index.trace_signal("main::B1", "backward").items}
    both = index.trace_signal("main::B1", "both")
    nodes = [item["node"] for item in both.items]
    assert len(nodes) == len(set(nodes))
    assert set(nodes) == forward | backward
    assert both.evidence["items_total"] == len(forward | backward)


def test_trace_both_counts_union_when_truncated():
    index = ModelIndex(parse_xprt(flat_model(300).text))
    result = index.trace_signal("main::B150", "both", max_depth=10000)
    assert len(result.items) == 200
    assert result.truncated is True
    # Цепочка из 300 блоков по два порта; объединение проходов - вся цепочка.
    assert result.evidence["items_total"] == 600


def test_query_requires_named_arguments():
    index = ModelIndex(parse_xprt(MODEL))
    with pytest.raises(ModelQueryError, match="trace_signal"):
        index.query("trace_signal", {})
    with pytest.raises(ModelQueryError, match="signal"):
        index.query("trace_signal", {"target": "Step"})
    with pytest.raises(ModelQueryError, match="node"):
        index.query("inspect_node", {})
    with pytest.raises(ModelQueryError, match="dst"):
        index.query("find_path", {"src": "Step"})


def test_find_objects_compare_and_unknown_query():
    index = ModelIndex(parse_xprt(MODEL))
    found = index.find_objects(query="K")
    assert found.items[0]["address"] == "main/Sub::K"
    changed = parse_xprt(MODEL.replace(
        "class_name>`Ступенька`", "class_name>`Интегратор`"))
    diff = index.compare_models(changed)
    assert any(item["kind"] == "class_changed" for item in diff.items)
    with pytest.raises(ModelQueryError):
        index.query("нет_такого")


def test_trace_signal_edge_kinds_filter():
    index = ModelIndex(parse_xprt(flat_model(3).text))
    structural = index.trace_signal(
        "main::B1:1", direction="forward",
        edge_kinds=("wire", "branch", "boundary", "memory"))
    block_only = index.trace_signal(
        "main::B1:0", direction="forward", edge_kinds=("block",))
    structural_input = index.trace_signal(
        "main::B1:0", direction="forward",
        edge_kinds=("wire", "branch", "boundary", "memory"))

    assert any(item["address"] == "main::B2" for item in structural.items)
    assert any(item["address"] == "main::B1" for item in structural.items)
    assert all(item["address"] != "main::B2" for item in block_only.items)
    assert all(item["address"] != "main::B2"
               for item in structural_input.items)


def test_trace_signal_rejects_unknown_edge_kind():
    index = ModelIndex(parse_xprt(flat_model(2).text))
    with pytest.raises(ModelQueryError):
        index.trace_signal("main::B0:1", edge_kinds=("teleport",))


def test_trace_signal_rejects_empty_edge_kinds():
    index = ModelIndex(parse_xprt(flat_model(2).text))
    with pytest.raises(ModelQueryError):
        index.trace_signal("main::B0:1", edge_kinds=())


def test_query_passes_edge_kinds():
    index = ModelIndex(parse_xprt(flat_model(3).text))
    result = index.query("trace_signal", {
        "signal": "main::B1:1", "direction": "forward",
        "edge_kinds": ["block"],
    })
    assert result.query == "trace_signal"
    assert all(item["address"] != "main::B2" for item in result.items)
