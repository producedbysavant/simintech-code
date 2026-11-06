"""Model IR: компактный паспорт и жёсткий бюджет."""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from simintech_api.model_ir import (  # noqa: E402
    ModelQueryError,
    build_manifest,
    estimate_tokens,
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
    assert "estimated_tokens:" in text
    assert "budget_tokens: 3000" in text
    assert estimate_tokens(text) <= 3000


def test_manifest_focus_and_budget_validation():
    ir = parse_xprt(MODEL)
    classes = build_manifest(ir, budget_tokens=3000, focus="classes")
    assert "## Classes" in classes
    assert "## Structure" not in classes
    with pytest.raises(ModelQueryError):
        build_manifest(ir, budget_tokens=1000)
    with pytest.raises(ModelQueryError):
        build_manifest(ir, budget_tokens=3000, focus="unknown")


def test_manifest_contracts_section_uses_registry():
    from simintech_api.model_ir.contracts import load_default_contracts

    text = build_manifest(parse_xprt(MODEL), budget_tokens=3000)
    coverage = load_default_contracts().coverage()
    assert "## Contracts" in text
    assert f"registry: {coverage.classes} classes" in text
    assert "unavailable" not in text
    assert "- Ступенька: ports=fixed" in text
    assert "- Временной график: ports=nport" in text


def test_manifest_contracts_unavailable_names_reason(monkeypatch):
    from simintech_api.model_ir import manifest

    def broken():
        raise ModelQueryError("реестр не прочитан: файл отсутствует")

    monkeypatch.setattr(manifest, "load_default_contracts", broken)
    text = manifest.build_manifest(parse_xprt(MODEL), budget_tokens=3000)
    assert "## Contracts" in text
    assert "registry: unavailable" in text
    assert "реестр не прочитан" in text


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
    assert estimate_tokens(text) <= 2000
    assert "## Omitted" in text
    assert "query_model" in text


def test_manifest_has_semantics_section():
    text = build_manifest(parse_xprt(MODEL), budget_tokens=3000)
    assert "## Semantics" in text
    assert "objects_with_approved_behavior" in text
    assert "objects_with_init_script" in text


def test_manifest_focus_semantics():
    text = build_manifest(
        parse_xprt(MODEL), budget_tokens=3000, focus="semantics")
    assert "## Semantics" in text
    assert "## Classes" not in text


def test_manifest_has_review_section():
    from simintech_api.model_ir.contracts import load_default_contracts
    from simintech_api.model_ir.semantics import review_summary

    counts = review_summary(load_default_contracts())["counts"]
    text = build_manifest(parse_xprt(MODEL), budget_tokens=3000)
    assert "## Review" in text
    assert f"rows: {sum(counts.values())}" in text
    assert f"approved: {counts['approved']}" in text
    assert f"preliminary: {counts['preliminary']}" in text
    assert f"rejected: {counts['rejected']}" in text


def test_manifest_focus_review():
    text = build_manifest(
        parse_xprt(MODEL), budget_tokens=3000, focus="review")
    assert "## Review" in text
    assert "## Classes" not in text


def test_manifest_semantics_prints_review_counts():
    from simintech_api.model_ir.contracts import load_default_contracts
    from simintech_api.model_ir.semantics import review_summary

    counts = review_summary(load_default_contracts())["counts"]
    text = build_manifest(
        parse_xprt(MODEL), budget_tokens=3000, focus="semantics")
    assert (
        f"review: approved={counts['approved']}, "
        f"preliminary={counts['preliminary']}, "
        f"rejected={counts['rejected']}" in text)


def test_manifest_estimated_tokens_matches_text():
    text = build_manifest(parse_xprt(MODEL), budget_tokens=3000)
    match = re.search(r"^estimated_tokens: (\d+)$", text, re.MULTILINE)
    assert match is not None
    value = int(match.group(1))
    assert value == estimate_tokens(text)
    assert value <= 3000


def test_manifest_rejects_budget_below_minimum():
    with pytest.raises(ModelQueryError):
        build_manifest(parse_xprt(MODEL), budget_tokens=1999)


def test_manifest_refuses_when_mandatory_part_exceeds_budget(monkeypatch):
    from simintech_api.model_ir import manifest

    monkeypatch.setattr(
        manifest, "_coverage",
        lambda model: "\n".join(
            ["## Coverage"] + ["x" * 1000 for _ in range(10)]))
    with pytest.raises(ModelQueryError, match="обязательная часть"):
        build_manifest(parse_xprt(MODEL), budget_tokens=2000)


def test_manifest_long_russian_names_stay_in_budget():
    parts = ["<Header><project><page>"]
    for index in range(300):
        name = "Класс" + "я" * 200 + str(index)
        parts.append(
            f"<object><name>`O{index}`</name>"
            f"<class_name>`{name}`</class_name>"
            "<obj_type>`100`</obj_type></object>")
    parts.append("</page></project></Header>")
    text = build_manifest(parse_xprt("".join(parts)), budget_tokens=2000)
    assert estimate_tokens(text) <= 2000
    assert "estimated_tokens:" in text
