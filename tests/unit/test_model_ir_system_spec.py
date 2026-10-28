"""SystemSpec: компиляция, ошибки, сверка и вердикт."""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from simintech_api.model_ir import (  # noqa: E402
    SystemSpecError,
    compile_system_spec,
    parse_xprt,
    verify_model,
)

CHAIN_XML = """<Header><project><page>
  <object>
    <name>`Step`</name>
    <class_name>`Ступенька`</class_name><obj_type>`100`</obj_type>
    <ports><port><name>`y`</name><mode>`1`</mode></port></ports>
  </object>
  <object>
    <name>`Gain`</name>
    <class_name>`Усилитель`</class_name><obj_type>`100`</obj_type>
    <ports>
      <port><name>`u`</name><mode>`0`</mode></port>
      <port><name>`y`</name><mode>`1`</mode></port>
    </ports>
  </object>
  <object>
    <name>`Graph`</name>
    <class_name>`Временной график`</class_name><obj_type>`106`</obj_type>
    <ports><port><name>`u`</name><mode>`0`</mode></port></ports>
  </object>
  <object>
    <name>`W1`</name>
    <class_name>`Математическая связь`</class_name><obj_type>`101`</obj_type>
    <start_bl_index>`0`</start_bl_index><start_port_index>`0`</start_port_index>
    <end_bl_index>`1`</end_bl_index><end_port_index>`0`</end_port_index>
  </object>
  <object>
    <name>`W2`</name>
    <class_name>`Математическая связь`</class_name>
    <obj_type>`101`</obj_type>
    <start_bl_index>`1`</start_bl_index><start_port_index>`1`</start_port_index>
    <end_bl_index>`2`</end_bl_index><end_port_index>`0`</end_port_index>
  </object>
</page></project></Header>"""

CHAIN_SPEC = {
    "schema": "system-spec/1",
    "name": "chain",
    "blocks": [
        {"name": "Step", "class": "Ступенька",
         "ports": {"outputs": ["y"]}},
        {"name": "Gain", "class": "Усилитель",
         "ports": {"inputs": ["u"], "outputs": ["y"]}},
        {"name": "Graph", "class": "Временной график",
         "ports": {"inputs": ["u"]}},
    ],
    "wires": [
        {"src": "Step:out:0", "dst": "Gain:in:0"},
        {"src": "Gain:out:1", "dst": "Graph:in:0"},
    ],
}


def test_compile_chain_and_verify_passed():
    compiled = compile_system_spec(CHAIN_SPEC)
    assert compiled.name == "chain"
    assert compiled.profile["readback"] == ["xprt"]
    assert len(compiled.expected.level.objects) == 3
    report = verify_model(parse_xprt(CHAIN_XML), compiled)
    assert report.verdict == "passed"
    assert report.counts["failed"] == 0


W2_XML = """  <object>
    <name>`W2`</name>
    <class_name>`Математическая связь`</class_name>
    <obj_type>`101`</obj_type>
    <start_bl_index>`1`</start_bl_index><start_port_index>`1`</start_port_index>
    <end_bl_index>`2`</end_bl_index><end_port_index>`0`</end_port_index>
  </object>
"""


def test_missing_wire_fails_verification():
    compiled = compile_system_spec(CHAIN_SPEC)
    actual = parse_xprt(CHAIN_XML.replace(W2_XML, ""))
    report = verify_model(actual, compiled)
    assert report.verdict == "failed"
    assert any(item["kind"] == "wire_missing" for item in report.items)


def test_compile_collects_all_errors():
    bad = {
        "schema": "system-spec/1",
        "blocks": [
            {"name": "A", "class": "Нет класса"},
            {"name": "A", "class": "Константа", "props": {"bad": 1}},
            {"name": "B", "class": "Константа",
             "ports": {"outputs": ["y"]}},
        ],
        "wires": [
            {"src": "B:out:0", "dst": "B:in:0"},
            {"src": "Z:out:0", "dst": "B:in:0"},
        ],
        "invariants": [{"kind": "bad"}],
        "requirements": [{"id": "r", "check": {"kind": "bad"}}],
        "assertions": [{"id": "a", "op": "??"}],
    }
    with pytest.raises(SystemSpecError) as excinfo:
        compile_system_spec(bad)
    codes = {item["code"] for item in excinfo.value.problems}
    assert {"unknown_class", "duplicate_name", "unknown_prop", "self_loop",
            "unknown_block", "unknown_kind", "unknown_check",
            "unknown_op"} <= codes


def test_unknown_contract_is_partial_not_failed():
    spec = {
        "schema": "system-spec/1",
        "name": "unknown",
        "blocks": [{"name": "U", "class": "Arduino - I2C - Ведомый I2C"}],
    }
    compiled = compile_system_spec(spec)
    actual = parse_xprt("""<Header><project><page>
  <object><name>`U`</name>
    <class_name>`Arduino - I2C - Ведомый I2C`</class_name>
    <obj_type>`100`</obj_type></object>
</page></project></Header>""")
    report = verify_model(actual, compiled)
    assert report.verdict == "partial"
    assert any(item["status"] == "not_evaluated" for item in report.items)


def test_requirement_and_assertion_statuses():
    spec = dict(CHAIN_SPEC)
    spec["requirements"] = [
        {"id": "r1", "text": "блок Step есть",
         "check": {"kind": "object_present", "target": "Step"}},
        {"id": "r2", "text": "словами, без проверки"},
    ]
    spec["assertions"] = [{"id": "a1", "signal": "y", "op": ">", "value": 0}]
    report = verify_model(parse_xprt(CHAIN_XML),
                          compile_system_spec(spec))
    statuses = {item["id"]: item["status"] for item in report.items
                if item["kind"] in ("requirement", "assertion")}
    assert statuses["r1"] == "passed"
    assert statuses["r2"] == "not_evaluated"
    assert statuses["a1"] == "not_evaluated"
    assert report.verdict == "partial"


SUBMODEL_XML = """<Header><project><page>
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
</page></project></Header>"""

SUBMODEL_SPEC = {
    "schema": "system-spec/1",
    "name": "sub",
    "blocks": [{
        "name": "Sub", "class": "Субмодель",
        "ports": {"inputs": ["x"], "outputs": ["y"]},
        "subsystem": {
            "blocks": [
                {"name": "In", "class": "Порт входа",
                 "ports": {"outputs": ["x"]}},
                {"name": "K", "class": "Усилитель",
                 "ports": {"inputs": ["u"], "outputs": ["y"]}},
                {"name": "Out", "class": "Порт выхода",
                 "ports": {"inputs": ["y"]}},
            ],
            "wires": [
                {"src": "In:out:0", "dst": "K:in:0"},
                {"src": "K:out:1", "dst": "Out:in:0"},
            ],
        },
    }],
}

MEMORY_XML = """<Header><project><page>
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

MEMORY_SPEC = {
    "schema": "system-spec/1",
    "name": "memory",
    "blocks": [
        {"name": "To", "class": "В память", "ports": {"inputs": ["u"]}},
        {"name": "From", "class": "Из памяти", "ports": {"outputs": ["y"]}},
    ],
    "invariants": [{"id": "mem", "kind": "memory_pair_complete"}],
}


def test_submodel_and_memory_specs_verify_passed():
    sub = verify_model(parse_xprt(SUBMODEL_XML),
                       compile_system_spec(SUBMODEL_SPEC))
    assert sub.verdict == "passed", sub.items
    memory = verify_model(parse_xprt(MEMORY_XML),
                          compile_system_spec(MEMORY_SPEC))
    assert memory.verdict == "passed", memory.items
