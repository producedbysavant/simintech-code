"""Model IR: разбор .xprt и публичный контракт структур."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from simintech_api.model_ir import (  # noqa: E402
    ContainerKind,
    ObjectKind,
    PortDirection,
    SourceKind,
    WireEndKind,
    WireKind,
    parse_xprt,
)

MINIMAL = """<Header><project><page>
  <object>
    <name>`K`</name>
    <class_name>`Константа`</class_name>
    <obj_type>`100`</obj_type>
    <ports><port><name>`y`</name><mode>`1`</mode></port></ports>
    <custom_props><data><name>`a`</name><value>`1`</value></data></custom_props>
  </object>
</page></project></Header>"""


def test_parse_minimal_object_and_port():
    ir = parse_xprt(MINIMAL)

    assert ir.meta.primary_source is SourceKind.XPRT
    assert len(ir.containers) == 1
    main = ir.containers[0]
    assert main.kind is ContainerKind.PROJECT
    assert main.address == "main"

    assert len(ir.objects) == 1
    obj = ir.objects[0]
    assert obj.name == "K"
    assert obj.class_name == "Константа"
    assert obj.obj_type == "100"
    assert obj.kind is ObjectKind.BLOCK
    assert obj.container_id == main.id
    assert len(obj.ports) == 1
    port = obj.ports[0]
    assert port.name == "y"
    assert port.index == 0
    assert port.direction is PortDirection.OUT
    assert obj.props["a"].value == "1"
    assert ir.coverage.objects == 1
    assert ir.coverage.ports_real == 1


WIRE_MODEL = """<Header><project><page>
  <object>
    <name>`A`</name><class_name>`Ступенька`</class_name><obj_type>`100`</obj_type>
    <ports><port><name>`y`</name><mode>`1`</mode></port></ports>
  </object>
  <object>
    <name>`B`</name><class_name>`Усилитель`</class_name><obj_type>`100`</obj_type>
    <ports>
      <port><name>`u1`</name><mode>`0`</mode></port>
      <port><name>`u2`</name><mode>`0`</mode></port>
    </ports>
  </object>
  <object>
    <name>`W`</name>
    <class_name>`Математическая связь`</class_name>
    <obj_type>`101`</obj_type>
    <start_bl_index>`0`</start_bl_index><start_bl_name>`A`</start_bl_name>
    <start_port_index>`0`</start_port_index>
    <end_bl_index>`1`</end_bl_index><end_bl_name>`B`</end_bl_name>
    <end_port_index>`0`</end_port_index>
    <base_points><type>`26`</type><value>`[(0, 0),(16, 0)]`</value></base_points>
  </object>
  <object>
    <name>`W2`</name>
    <class_name>`Математическая связь`</class_name>
    <obj_type>`101`</obj_type>
    <start_bl_index>`-1`</start_bl_index><start_port_index>`-1`</start_port_index>
    <parentwirenode>`0`</parentwirenode>
    <parent_wire_index>`2`</parent_wire_index>
    <parent_wire_name>`W`</parent_wire_name>
    <end_bl_index>`1`</end_bl_index><end_bl_name>`B`</end_bl_name>
    <end_port_index>`1`</end_port_index>
    <base_points><type>`26`</type>
      <value>`[(8, 0),(8, 16),(16, 16)]`</value></base_points>
  </object>
</page></project></Header>"""


def test_wire_and_branch_resolve_to_objects_and_ports():
    ir = parse_xprt(WIRE_MODEL)

    assert len(ir.wires) == 2
    wire = ir.wire(ir.wires[0].id)
    assert wire is not None
    assert wire.name == "W"
    assert wire.kind is WireKind.WIRE
    assert wire.start.kind is WireEndKind.PORT
    assert wire.start.object_name == "A"
    assert wire.start.port_index == 0
    assert wire.start.resolved is True
    assert wire.end.object_name == "B"
    assert wire.end.port_index == 0
    assert wire.points == ((0.0, 0.0), (16.0, 0.0))

    branch = ir.wire(ir.wires[1].id)
    assert branch is not None
    assert branch.kind is WireKind.BRANCH
    assert branch.start.kind is WireEndKind.BRANCH
    assert branch.branch_parent_id == wire.id
    assert branch.branch_node == 0
    assert branch.end.object_name == "B"
    assert branch.end.port_index == 1
    assert ir.coverage.wires == 2
    assert ir.coverage.branches == 1
    assert ir.coverage.unresolved_ends == 0
    assert ir.coverage.unresolved_branches == 0


SUBMODEL_MODEL = """<Header><project><page>
  <object>
    <name>`S`</name><class_name>`Субмодель`</class_name><obj_type>`102`</obj_type>
    <ports>
      <port><name>`x`</name><mode>`0`</mode></port>
      <port><name>`y`</name><mode>`1`</mode></port>
    </ports>
    <blockimage><page>
      <object>
        <name>`icon_line`</name><class_name>`Line`</class_name><obj_type>`1`</obj_type>
        <points><type>`26`</type><value>`[(0, 0),(10, 0)]`</value></points>
      </object>
    </page></blockimage>
    <page>
      <name></name>
      <object>
        <name>`In`</name><class_name>`Порт входа`</class_name><obj_type>`103`</obj_type>
        <ports><port><name>`x`</name><mode>`1`</mode></port></ports>
        <visual_props><data><name>`PortNames`</name><value>`X`</value></data></visual_props>
      </object>
      <object>
        <name>`Out`</name>
        <class_name>`Порт выхода`</class_name>
        <obj_type>`103`</obj_type>
        <ports><port><name>`y`</name><mode>`0`</mode></port></ports>
        <visual_props><data><name>`PortNames`</name><value>`Y`</value></data></visual_props>
      </object>
      <object>
        <name>`K`</name><class_name>`Усилитель`</class_name><obj_type>`100`</obj_type>
        <ports>
          <port><name>`u`</name><mode>`0`</mode></port>
          <port><name>`y`</name><mode>`1`</mode></port>
        </ports>
      </object>
      <object>
        <name>`IW`</name>
        <class_name>`Математическая связь`</class_name>
        <obj_type>`101`</obj_type>
        <start_bl_index>`0`</start_bl_index><start_bl_name>`In`</start_bl_name>
        <start_port_index>`0`</start_port_index>
        <end_bl_index>`2`</end_bl_index><end_bl_name>`K`</end_bl_name>
        <end_port_index>`0`</end_port_index>
      </object>
      <object>
        <name>`IW2`</name>
        <class_name>`Математическая связь`</class_name>
        <obj_type>`101`</obj_type>
        <start_bl_index>`2`</start_bl_index><start_bl_name>`K`</start_bl_name>
        <start_port_index>`1`</start_port_index>
        <end_bl_index>`1`</end_bl_index><end_bl_name>`Out`</end_bl_name>
        <end_port_index>`0`</end_port_index>
      </object>
    </page>
  </object>
</page></project></Header>"""


def test_submodel_page_is_container_and_blockimage_is_excluded():
    ir = parse_xprt(SUBMODEL_MODEL)

    assert len(ir.containers) == 2
    main = next(item for item in ir.containers
                if item.kind is ContainerKind.PROJECT)
    sub = next(item for item in ir.containers
               if item.kind is ContainerKind.SUBMODEL)
    assert main.address == "main"
    assert sub.address == "main/S"
    assert sub.parent_object_id == ir.object_by_address("main::S").id

    assert [item.name for item in ir.objects_in(main.id)] == ["S"]
    assert sorted(item.name for item in ir.objects_in(sub.id)) == ["In", "K", "Out"]
    assert len(ir.wires_in(sub.id)) == 2

    assert ir.coverage.block_image_pages == 1
    assert ir.coverage.block_image_objects == 1
    assert all("icon" not in item.address.lower() for item in ir.objects)

    assert len(ir.boundaries) == 2
    assert all(item.resolved for item in ir.boundaries)
    by_name = {item.external_port_name: item for item in ir.boundaries}
    assert by_name["x"].internal_object_id == ir.object_by_address("main/S::In").id
    assert by_name["y"].internal_object_id == ir.object_by_address("main/S::Out").id
    assert by_name["x"].port_names == "X"
    assert by_name["y"].port_names == "Y"


PROPS_MODEL = """<Header><project><page>
  <object>
    <name>`K`</name><class_name>`Усилитель`</class_name><obj_type>`100`</obj_type>
    <uid>`42`</uid>
    <points><type>`26`</type><value>`[(0, 0),(16, 0)]`</value></points>
    <visual_props>
      <data><name>`PortNames`</name><value>`VAR`</value></data>
      <data><name>`Color`</name><value>`16777215`</value></data>
      <data><name>`UID`</name><value>`42`</value></data>
    </visual_props>
    <custom_props>
      <data><name>`a`</name><value>`1`</value><mode>`1`</mode></data>
      <data><name>`formula_visible`</name><value>`0`</value></data>
      <data><name>`Script`</name><value>`writeln("x");`</value></data>
      <data><name>`OnInitScript`</name><value>`n = 1;`</value></data>
    </custom_props>
    <custom_params>
      <data><name>`Y`</name><value>`[0]`</value></data>
    </custom_params>
  </object>
</page></project></Header>"""


def test_properties_scripts_and_volatile_values():
    ir = parse_xprt(PROPS_MODEL)
    obj = ir.object_by_address("main::K")

    assert obj is not None
    assert obj.props["a"].value == "1"
    assert obj.props["formula_visible"].value == "0"
    assert obj.visual_props["PortNames"].value == "VAR"
    assert "Color" not in obj.visual_props
    assert "Y" not in obj.props
    assert obj.uid == "42"
    assert obj.scripts["Script"].present is True
    assert obj.scripts["Script"].length > 0
    assert obj.scripts["Script"].sha256
    assert obj.scripts["OnInitScript"].present is True
    assert ir.coverage.skipped["custom_params"] == 1
    assert ir.coverage.skipped["visual_props"] == 1

    again = parse_xprt(PROPS_MODEL)
    assert again.meta.structure_hash == ir.meta.structure_hash
    assert again.meta.content_hash == ir.meta.content_hash

    changed_value = PROPS_MODEL.replace("<value>`1`</value>", "<value>`2`</value>")
    value_ir = parse_xprt(changed_value)
    assert value_ir.meta.structure_hash == ir.meta.structure_hash
    assert value_ir.meta.content_hash != ir.meta.content_hash

    changed_volatile = PROPS_MODEL.replace("<value>`[0]`</value>",
                                           "<value>`[1]`</value>")
    volatile_ir = parse_xprt(changed_volatile)
    assert volatile_ir.meta.structure_hash == ir.meta.structure_hash
    assert volatile_ir.meta.content_hash == ir.meta.content_hash

    changed_script = PROPS_MODEL.replace('writeln("x");', 'writeln("y");')
    script_ir = parse_xprt(changed_script)
    assert script_ir.meta.structure_hash == ir.meta.structure_hash
    assert script_ir.meta.content_hash != ir.meta.content_hash

    changed_points = PROPS_MODEL.replace("(16, 0)", "(24, 0)")
    points_ir = parse_xprt(changed_points)
    assert points_ir.meta.structure_hash == ir.meta.structure_hash
    assert points_ir.meta.content_hash != ir.meta.content_hash
