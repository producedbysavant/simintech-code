"""Model IR: разбор декларативного текста savemodeltofile."""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from simintech_api.model_ir import (  # noqa: E402
    ContainerKind,
    Limits,
    ModelIRLimitError,
    ModelTextParseError,
    ObjectKind,
    SourceKind,
    SourceStatus,
    WireEndKind,
    WireKind,
    parse_model_text,
)

TEXT = """(
  // свойства страницы
  x_center = 0,
  script = "contour",
  Step: (
    type = "Ступенька",
    points = [(0, 0)],
    t = [0],
    y0 = [0],
    yk = [1]
  ),
  Sub: (
    type = "Субмодель",
    points = [(100, 0)],
    subsystem: (
      In: (type = "Порт входа", portnames = "X"),
      K: (type = "Усилитель", a = 2, a.formula = "10"),
      Out: (type = "Порт выхода", portnames = "Y"),
      w1: (type = "wire", src = "In:out:0", dst = "K:in:0"),
      w2: (type = "wire", src = "K:out:0", dst = "Out:in:0")
    )
  ),
  WStepSub: (
    type = "wire",
    points = [(0, 0), (100, 0)],
    src = "Step:out:0",
    dst = "Sub:in:0"
  ),
  WBranch: (
    type = "wire",
    src = "WStepSub:0",
    dst = "Sub:in:1"
  )
)"""


def test_text_model_builds_containers_objects_and_synthetic_ports():
    ir = parse_model_text(TEXT, source_name="model.txt")

    assert ir.meta.primary_source is SourceKind.MODEL_TEXT
    assert ir.meta.source_name == "model.txt"
    assert ir.coverage.source_status is SourceStatus.PARTIAL
    assert len(ir.containers) == 2
    main = next(item for item in ir.containers
                if item.kind is ContainerKind.PROJECT)
    sub = next(item for item in ir.containers
               if item.kind is ContainerKind.SUBMODEL)
    assert main.address == "main"
    assert sub.address == "main/Sub"

    assert sorted(item.name for item in ir.objects_in(main.id)) == [
        "Step", "Sub"]
    assert sorted(item.name for item in ir.objects_in(sub.id)) == [
        "In", "K", "Out"]
    assert ir.object_by_address("main/Sub::In").kind is ObjectKind.PORT_BLOCK
    assert ir.object_by_address("main::Sub").kind is ObjectKind.SUBMODEL
    assert ir.object_by_address("main/Sub::K").props["a"].value == "2"
    assert (ir.object_by_address("main/Sub::K")
            .props["a.formula"].value == "10")
    assert (ir.object_by_address("main/Sub::In")
            .visual_props["PortNames"].value == "X")

    assert ir.coverage.ports_synthetic == 7
    assert ir.coverage.wires == 4
    assert ir.coverage.branches == 1
    assert ir.coverage.skipped["page_script_temporary"] == 1

    step = ir.object_by_address("main::Step")
    sub_obj = ir.object_by_address("main::Sub")
    assert step is not None and sub_obj is not None
    assert [(p.index, p.direction.value) for p in step.ports] == [(0, "out")]
    assert sorted((p.index, p.direction.value) for p in sub_obj.ports) == [
        (0, "in"), (1, "in")]

    branch = next(item for item in ir.wires if item.name == "WBranch")
    parent = next(item for item in ir.wires if item.name == "WStepSub")
    assert branch.kind is WireKind.BRANCH
    assert branch.start.kind is WireEndKind.BRANCH
    assert branch.branch_parent_id == parent.id
    assert branch.start.object_id == parent.id
    assert parent.points == ((0.0, 0.0), (100.0, 0.0))

    again = parse_model_text(TEXT)
    assert again.meta.structure_hash == ir.meta.structure_hash
    assert again.meta.content_hash == ir.meta.content_hash


def test_text_embedded_quote_and_comments():
    text = """(
      // комментарий
      K: (type = "Усилитель", LabelText = "a"+chr(34)+"b")
    )"""
    ir = parse_model_text(text)
    obj = ir.object_by_address("main::K")
    assert obj is not None
    assert obj.props["LabelText"].value == 'a"b'


def test_text_without_closing_parenthesis_is_refusal():
    with pytest.raises(ModelTextParseError):
        parse_model_text('( K: (type = "Усилитель")')


def test_text_limits():
    with pytest.raises(ModelIRLimitError):
        parse_model_text(TEXT, limits=Limits(max_bytes=10))
    with pytest.raises(ModelIRLimitError):
        parse_model_text(TEXT, limits=Limits(max_objects=1))
    with pytest.raises(ModelIRLimitError):
        parse_model_text(TEXT, limits=Limits(max_wires=1))
    with pytest.raises(ModelIRLimitError):
        parse_model_text(TEXT, limits=Limits(max_depth=0))
