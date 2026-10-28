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
