"""Model IR: сборка источников и расхождения xprt/text/topology."""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from simintech_api.model_ir import (  # noqa: E402
    ModelIRConflictError,
    SourceKind,
    build_model_ir,
    parse_model_text,
    parse_xprt,
    topology_to_ir,
)
from simintech_api.topology import parse_topology  # noqa: E402

XML_MODEL = """<Header><project><page>
  <object>
    <name>`Step`</name>
    <class_name>`Ступенька`</class_name>
    <obj_type>`100`</obj_type>
    <ports><port><name>`y`</name><mode>`1`</mode></port></ports>
  </object>
  <object>
    <name>`Sub`</name>
    <class_name>`Субмодель`</class_name>
    <obj_type>`102`</obj_type>
    <ports>
      <port><name>`x`</name><mode>`0`</mode></port>
      <port><name>`x2`</name><mode>`0`</mode></port>
    </ports>
    <page><name></name>
      <object>
        <name>`In`</name>
    <class_name>`Порт входа`</class_name>
    <obj_type>`103`</obj_type>
        <ports><port><name>`x`</name><mode>`1`</mode></port></ports>
      </object>
      <object>
        <name>`K`</name>
    <class_name>`Усилитель`</class_name>
    <obj_type>`100`</obj_type>
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
    <name>`WStepSub`</name>
    <class_name>`Математическая связь`</class_name>
    <obj_type>`101`</obj_type>
    <start_bl_index>`0`</start_bl_index>
    <start_port_index>`0`</start_port_index>
    <end_bl_index>`1`</end_bl_index><end_port_index>`0`</end_port_index>
  </object>
  <object>
    <name>`WBranch`</name>
    <class_name>`Математическая связь`</class_name>
    <obj_type>`101`</obj_type>
    <start_bl_index>`-1`</start_bl_index><start_port_index>`-1`</start_port_index>
    <parent_wire_index>`2`</parent_wire_index>
    <parent_wire_name>`WStepSub`</parent_wire_name>
    <end_bl_index>`1`</end_bl_index><end_port_index>`1`</end_port_index>
  </object>
</page></project></Header>"""

TEXT_MODEL = """(
  Step: (type = "Ступенька", points = [(0, 0)]),
  Sub: (
    type = "Субмодель",
    points = [(100, 0)],
    subsystem: (
      In: (type = "Порт входа", portnames = "X"),
      K: (type = "Усилитель", a = 2),
      Out: (type = "Порт выхода", portnames = "Y"),
      w1: (type = "wire", src = "In:out:0", dst = "K:in:0"),
      w2: (type = "wire", src = "K:out:0", dst = "Out:in:0")
    )
  ),
  WStepSub: (type = "wire", src = "Step:out:0", dst = "Sub:in:0"),
  WBranch: (type = "wire", src = "WStepSub:0", dst = "Sub:in:1")
)"""


def _xprt():
    return parse_xprt(XML_MODEL)


def _text():
    return parse_model_text(TEXT_MODEL)


def test_xprt_and_text_are_consistent():
    merged = build_model_ir(xprt=_xprt(), text=_text())
    assert merged.meta.primary_source is SourceKind.XPRT
    assert merged.meta.source_set == (SourceKind.XPRT, SourceKind.MODEL_TEXT)
    assert set(merged.meta.source_hashes) == {"xprt", "model_text"}
    errors = [item for item in merged.discrepancies
              if item.severity.value == "error"]
    assert errors == []
    assert merged.meta.structure_hash


def test_class_mismatch_is_strict_refusal():
    text = parse_model_text(TEXT_MODEL.replace(
        'type = "Ступенька"', 'type = "Интегратор"'))
    with pytest.raises(ModelIRConflictError):
        build_model_ir(xprt=_xprt(), text=text, strict=True)
    merged = build_model_ir(xprt=_xprt(), text=text)
    assert "class_mismatch" in merged.coverage.discrepancy_counts


def test_missing_text_object_is_reported():
    text = parse_model_text(TEXT_MODEL.replace(
        'Step: (type = "Ступенька", points = [(0, 0)]),', ""))
    merged = build_model_ir(xprt=_xprt(), text=text)
    assert "object_extra_in_source" in merged.coverage.discrepancy_counts


def test_wire_difference_is_reported():
    text = parse_model_text(TEXT_MODEL.replace(
        'dst = "Sub:in:0"', 'dst = "Sub:in:1"'))
    merged = build_model_ir(xprt=_xprt(), text=text)
    counts = merged.coverage.discrepancy_counts
    assert counts["wire_missing_in_source"] == 1
    assert counts["wire_extra_in_source"] == 1


def test_text_only_is_partial_with_synthetic_ports():
    merged = build_model_ir(text=_text())
    assert merged.meta.primary_source is SourceKind.MODEL_TEXT
    assert merged.coverage.ports_synthetic > 0
    assert merged.coverage.source_status.value == "partial"


def test_topology_only_and_topology_cross_check():
    topology = parse_topology(
        "object\tStep\tСтупенька\nobject\tSub\tСубмодель\n"
        "port\tStep\t0\tout\ty\nport\tSub\t0\tin\tx\n"
        "conn\tStep\t0\tSub\t0\n")
    topology_ir = topology_to_ir(topology)
    merged = build_model_ir(topology=topology_ir)
    assert merged.meta.primary_source is SourceKind.TOPOLOGY
    assert merged.wires[0].kind.value == "topology_edge"

    cross = build_model_ir(xprt=_xprt(), topology=topology_ir, strict=True)
    assert "topology_scope_limited" in cross.coverage.discrepancy_counts
