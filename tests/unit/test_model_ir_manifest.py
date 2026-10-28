"""Model IR: компактный паспорт и жёсткий бюджет."""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from simintech_api.model_ir import (  # noqa: E402
    ModelQueryError,
    build_manifest,
    parse_xprt,
)

MODEL = """<Header><project><page>
  <object>
    <name>`Step`</name>
    <class_name>`Ступенька`</class_name>
    <obj_type>`100`</obj_type>
    <ports><port><name>`y`</name><mode>`1`</mode></port></ports>
  </object>
  <object>
    <name>`Graph`</name>
    <class_name>`Временной график`</class_name>
    <obj_type>`106`</obj_type>
    <ports><port><name>`u`</name><mode>`0`</mode></port></ports>
  </object>
  <object>
    <name>`W`</name>
    <class_name>`Математическая связь`</class_name>
    <obj_type>`101`</obj_type>
    <start_bl_index>`0`</start_bl_index><start_port_index>`0`</start_port_index>
    <end_bl_index>`1`</end_bl_index><end_port_index>`0`</end_port_index>
  </object>
</page></project></Header>"""


def test_manifest_has_header_coverage_and_no_xml():
    ir = parse_xprt(MODEL)
    text = build_manifest(ir, budget_tokens=3000)
    assert text.startswith("# Model IR")
    assert "model_hash:" in text
    assert "## Coverage" in text
    assert "## Structure" in text
    assert "## Classes" in text
    assert "<object" not in text
    assert "<?xml" not in text
    assert len(text) <= 3000 * 3


def test_manifest_focus_and_budget_validation():
    ir = parse_xprt(MODEL)
    classes = build_manifest(ir, budget_tokens=3000, focus="classes")
    assert "## Classes" in classes
    assert "## Structure" not in classes
    with pytest.raises(ModelQueryError):
        build_manifest(ir, budget_tokens=1000)
    with pytest.raises(ModelQueryError):
        build_manifest(ir, budget_tokens=3000, focus="unknown")


def test_manifest_omits_what_does_not_fit():
    parts = ["<Header><project><page>"]
    for index in range(300):
        parts.append(
            f"<object><name>`S{index}`</name>"
            f"<class_name>`Субмодель`</class_name><obj_type>`102`</obj_type>"
            f"<page><name></name><object><name>`K{index}`</name>"
            f"<class_name>`Класс{index}`</class_name>"
            f"<obj_type>`100`</obj_type></object></page></object>")
    parts.append("</page></project></Header>")
    ir = parse_xprt("".join(parts))
    text = build_manifest(ir, budget_tokens=2000)
    assert len(text) <= 2000 * 3
    assert "## Omitted" in text
    assert "query_model" in text
