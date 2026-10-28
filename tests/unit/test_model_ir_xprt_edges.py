"""Model IR: отказы, пределы, дубли имен, память и границы субмоделей."""

import hashlib
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from simintech_api.model_ir import (  # noqa: E402
    Limits,
    ModelIRLimitError,
    ObjectKind,
    XprtParseError,
    parse_xprt,
    parse_xprt_file,
)

MINIMAL = """<Header><project><page>
  <object>
    <name>`K`</name><class_name>`Константа`</class_name><obj_type>`100`</obj_type>
  </object>
</page></project></Header>"""

TWO_OBJECTS = """<Header><project><page>
  <object>
    <name>`A`</name>
    <class_name>`Ступенька`</class_name>
    <obj_type>`100`</obj_type></object>
  <object>
    <name>`B`</name>
    <class_name>`Усилитель`</class_name>
    <obj_type>`100`</obj_type></object>
</page></project></Header>"""

DUPLICATES = """<Header><project><page>
  <object><name>`X`</name><class_name>`Ступенька`</class_name><obj_type>`100`</obj_type></object>
  <object><name>`X`</name><class_name>`Усилитель`</class_name><obj_type>`100`</obj_type></object>
  <object><name>`W`</name>
    <class_name>`Математическая связь`</class_name>
    <obj_type>`101`</obj_type>
    <start_bl_index>`-1`</start_bl_index><end_bl_index>`-1`</end_bl_index>
  </object>
  <object><name>`W`</name>
    <class_name>`Математическая связь`</class_name>
    <obj_type>`101`</obj_type>
    <start_bl_index>`-1`</start_bl_index><end_bl_index>`-1`</end_bl_index>
  </object>
</page></project></Header>"""

UNKNOWN = """<Header><project><page>
  <object><name>`U`</name><class_name>`Неизвестный`</class_name><obj_type>`999`</obj_type></object>
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
  <object>
    <name>`To2`</name><class_name>`В память`</class_name><obj_type>`104`</obj_type>
    <ports><port><name>`u`</name><mode>`0`</mode></port></ports>
    <visual_props><data><name>`PortNames`</name><value>`OTHER`</value></data></visual_props>
  </object>
  <object>
    <name>`To3`</name><class_name>`В память`</class_name><obj_type>`104`</obj_type>
    <ports><port><name>`u`</name><mode>`0`</mode></port></ports>
  </object>
</page></project></Header>"""

BOUNDARY_UNRESOLVED = """<Header><project><page>
  <object>
    <name>`S`</name><class_name>`Субмодель`</class_name><obj_type>`102`</obj_type>
    <ports><port><name>`x`</name><mode>`0`</mode></port></ports>
    <page><name></name></page>
  </object>
</page></project></Header>"""

DEEP = """<Header><project><page>
  <object>
    <name>`S`</name><class_name>`Субмодель`</class_name><obj_type>`102`</obj_type>
    <page><name></name>
      <object><name>`K`</name><class_name>`Усилитель`</class_name><obj_type>`100`</obj_type></object>
    </page>
  </object>
</page></project></Header>"""


def test_broken_xml_is_refusal_not_empty_model():
    with pytest.raises(XprtParseError):
        parse_xprt("<Header><project><page>")


def test_object_limit_is_refusal():
    with pytest.raises(ModelIRLimitError):
        parse_xprt(TWO_OBJECTS, limits=Limits(max_objects=1))


def test_byte_limit_is_refusal():
    with pytest.raises(ModelIRLimitError):
        parse_xprt(MINIMAL, limits=Limits(max_bytes=10))


def test_depth_limit_is_refusal():
    with pytest.raises(ModelIRLimitError):
        parse_xprt(DEEP, limits=Limits(max_depth=1))


def test_duplicate_names_get_distinct_addresses_and_info():
    ir = parse_xprt(DUPLICATES)
    addresses = [item.address for item in ir.objects] + [
        item.address for item in ir.wires]
    assert len(addresses) == 4
    assert len(set(addresses)) == 4
    assert "main::X#0" in addresses
    assert "main::X#1" in addresses
    assert ir.coverage.discrepancy_counts["duplicate_object_name"] == 1
    assert ir.coverage.discrepancy_counts["duplicate_wire_name"] == 1


def test_unknown_object_type_is_kept_and_counted():
    ir = parse_xprt(UNKNOWN)
    obj = ir.object_by_address("main::U")
    assert obj is not None
    assert obj.kind is ObjectKind.UNKNOWN
    assert ir.coverage.unknown_object_types == 1
    assert ir.coverage.discrepancy_counts["unknown_object_type"] == 1


def test_memory_links_pair_by_portnames():
    ir = parse_xprt(MEMORY)
    by_variable = {item.variable: item for item in ir.memory_links}
    assert by_variable["VAR"].resolved is True
    assert by_variable["VAR"].writers == ("main::To:0",)
    assert by_variable["VAR"].readers == ("main::From:0",)
    assert by_variable["OTHER"].resolved is False
    assert by_variable["OTHER"].reason == "unpaired"
    assert "" in by_variable
    assert by_variable[""].reason == "memory_name_missing"
    assert ir.coverage.discrepancy_counts["memory_unpaired"] == 1
    assert ir.coverage.discrepancy_counts["memory_name_missing"] == 1


def test_boundary_without_internal_port_is_unresolved():
    ir = parse_xprt(BOUNDARY_UNRESOLVED)
    assert len(ir.boundaries) == 1
    boundary = ir.boundaries[0]
    assert boundary.resolved is False
    assert boundary.reason == "not_found"
    assert ir.coverage.discrepancy_counts["boundary_unresolved"] == 1


def test_file_parse_matches_text_and_hashes_bytes(tmp_path):
    path = tmp_path / "model.xprt"
    path.write_bytes(MINIMAL.encode("utf-8"))
    from_file = parse_xprt_file(path)
    from_text = parse_xprt(MINIMAL)
    assert from_file.meta.structure_hash == from_text.meta.structure_hash
    assert from_file.meta.content_hash == from_text.meta.content_hash
    assert from_file.meta.source_hashes["xprt"] == hashlib.sha256(
        MINIMAL.encode("utf-8")).hexdigest()


def test_xml_declaration_is_accepted():
    text = '<?xml version="1.0" encoding="utf-8"?>\n' + MINIMAL
    ir = parse_xprt(text)
    assert len(ir.objects) == 1


LEGACY_CONTAINER = """<Header><project><page>
  <object>
    <name>`S`</name><class_name>`Субмодель`</class_name><obj_type>`102`</obj_type>
    <containerblock>
      <object><name>`K`</name><class_name>`Усилитель`</class_name><obj_type>`100`</obj_type></object>
    </containerblock>
  </object>
</page></project></Header>"""

BRANCH_AMBIGUOUS = """<Header><project><page>
  <object>
    <name>`A`</name>
    <class_name>`Ступенька`</class_name>
    <obj_type>`100`</obj_type>
    <ports><port><name>`y`</name><mode>`1`</mode></port></ports>
  </object>
  <object>
    <name>`B`</name>
    <class_name>`Усилитель`</class_name>
    <obj_type>`100`</obj_type>
    <ports>
      <port><name>`u1`</name><mode>`0`</mode></port>
      <port><name>`u2`</name><mode>`0`</mode></port>
    </ports>
  </object>
  <object>
    <name>`P`</name>
    <class_name>`Математическая связь`</class_name>
    <obj_type>`101`</obj_type>
    <start_bl_index>`0`</start_bl_index><end_bl_index>`1`</end_bl_index>
    <end_port_index>`0`</end_port_index>
  </object>
  <object>
    <name>`P`</name>
    <class_name>`Математическая связь`</class_name>
    <obj_type>`101`</obj_type>
    <start_bl_index>`0`</start_bl_index><end_bl_index>`1`</end_bl_index>
    <end_port_index>`0`</end_port_index>
  </object>
  <object>
    <name>`BR`</name>
    <class_name>`Математическая связь`</class_name>
    <obj_type>`101`</obj_type>
    <start_bl_index>`-1`</start_bl_index><start_port_index>`-1`</start_port_index>
    <parent_wire_name>`P`</parent_wire_name><parentwirenode>`0`</parentwirenode>
    <end_bl_index>`1`</end_bl_index><end_port_index>`1`</end_port_index>
  </object>
</page></project></Header>"""

MEMORY_NO_PORT = """<Header><project><page>
  <object>
    <name>`To`</name><class_name>`В память`</class_name><obj_type>`104`</obj_type>
    <visual_props><data><name>`PortNames`</name><value>`VAR`</value></data></visual_props>
  </object>
</page></project></Header>"""

WIDTH_MODEL = """<Header><project><page>
  <object>
    <name>`K`</name><class_name>`Константа`</class_name><obj_type>`100`</obj_type>
    <visual_props><data><name>`Width`</name><value>`60`</value></data></visual_props>
  </object>
</page></project></Header>"""


def test_legacy_containerblock_is_counted_not_kept_as_object():
    ir = parse_xprt(LEGACY_CONTAINER)
    assert len(ir.objects) == 1
    assert ir.object_by_address("main::S") is not None
    assert ir.coverage.skipped["legacy_containerblock_objects"] == 1


def test_ambiguous_branch_parent_is_unresolved():
    ir = parse_xprt(BRANCH_AMBIGUOUS)
    branch = next(item for item in ir.wires if item.name == "BR")
    assert branch.start.resolved is False
    assert branch.start.reason == "branch_parent_not_found"
    assert ir.coverage.unresolved_branches == 1
    details = [item.detail for item in ir.discrepancies
               if item.code == "branch_parent_unresolved"]
    assert any("неоднозначен" in item for item in details)


def test_memory_cell_without_port_is_unresolved():
    ir = parse_xprt(MEMORY_NO_PORT)
    link = next(item for item in ir.memory_links if item.variable == "VAR")
    assert link.resolved is False
    assert link.reason == "port_missing"
    assert ir.coverage.discrepancy_counts["memory_port_missing"] == 1


def test_width_does_not_change_content_hash():
    base = parse_xprt(WIDTH_MODEL)
    changed = parse_xprt(WIDTH_MODEL.replace("<value>`60`</value>",
                                             "<value>`100`</value>"))
    assert changed.meta.structure_hash == base.meta.structure_hash
    assert changed.meta.content_hash == base.meta.content_hash
