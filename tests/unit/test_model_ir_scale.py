"""P5: контекст, полнота и пределы на синтетических моделях."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from simintech_api.model_ir import (  # noqa: E402
    ModelIRLimitError,
    ModelIndex,
    build_manifest,
    compile_system_spec,
    parse_xprt,
    verify_model,
)
from simintech_api.model_ir.codes import WireEndKind, WireKind  # noqa: E402

from model_ir_synth import (  # noqa: E402
    broken_model,
    cycle_model,
    deep_model,
    direct_star_model,
    flat_model,
    loose_model,
    self_loop_model,
    star_model,
    unknown_type,
    wide_model,
)


def _coverage(ir):
    cov = ir.coverage
    return {
        "containers": cov.containers,
        "objects": cov.objects,
        "ports_real": cov.ports_real,
        "ports_synthetic": cov.ports_synthetic,
        "wires": cov.wires,
        "branches": cov.branches,
        "decorations": cov.decorations,
        "block_image_pages": cov.block_image_pages,
        "block_image_objects": cov.block_image_objects,
        "unresolved_ends": cov.unresolved_ends,
        "unconnected_ends": cov.unconnected_ends,
        "unresolved_branches": cov.unresolved_branches,
        "unknown_object_types": cov.unknown_object_types,
        "external_submodels": cov.external_submodels,
        "source_status": cov.source_status.value,
    }


def test_generators_are_reproducible():
    pairs = [
        (flat_model(50), flat_model(50)),
        (deep_model(5), deep_model(5)),
        (star_model(20), star_model(20)),
        (wide_model(10), wide_model(10)),
        (loose_model(20), loose_model(20)),
        (cycle_model(), cycle_model()),
    ]
    for first, second in pairs:
        assert first.text == second.text
        assert first.expected == second.expected


def test_flat_coverage_is_exact():
    model = flat_model(300)
    ir = parse_xprt(model.text)
    assert _coverage(ir) == model.expected
    assert ir.coverage.ports_real == sum(len(obj.ports) for obj in ir.objects)
    assert len({obj.address for obj in ir.objects}) == len(ir.objects)
    assert len({wire.address for wire in ir.wires}) == len(ir.wires)


def test_deep_coverage_and_default_limit():
    model = deep_model(63)
    ir = parse_xprt(model.text)
    assert _coverage(ir) == model.expected
    assert ir.coverage.unresolved_ends == 0
    with pytest.raises(ModelIRLimitError):
        parse_xprt(deep_model(64).text)


def test_star_branches_are_exact():
    model = star_model(300)
    ir = parse_xprt(model.text)
    assert _coverage(ir) == model.expected
    branches = [wire for wire in ir.wires if wire.kind is WireKind.BRANCH]
    assert len(branches) == 299
    assert all(wire.start.kind is WireEndKind.BRANCH for wire in branches)


def test_acyclic_chain_has_no_cycles():
    index = ModelIndex(parse_xprt(flat_model(10).text))
    assert index.find_cycles().items == ()


def test_real_cycle_is_reported():
    index = ModelIndex(parse_xprt(cycle_model().text))
    cycles = index.find_cycles()
    assert len(cycles.items) == 1
    assert set(cycles.items[0]["objects"]) == {"main::A", "main::B"}


def test_wire_self_loop_is_reported():
    index = ModelIndex(parse_xprt(self_loop_model().text))
    cycles = index.find_cycles()
    assert len(cycles.items) == 1
    assert cycles.items[0]["objects"] == ["main::A"]


def test_long_chain_does_not_raise_recursion_error():
    index = ModelIndex(parse_xprt(flat_model(1200).text))
    cycles = index.find_cycles()
    assert cycles.items == ()
    assert cycles.truncated is False


def test_ancestors_are_capped():
    index = ModelIndex(parse_xprt(flat_model(300).text))
    result = index.ancestors("main::B299", max_depth=10000)
    assert len(result.items) <= 200
    assert result.truncated is True
    assert result.evidence["items_total"] == 300


def test_find_objects_limit_cannot_exceed_cap():
    index = ModelIndex(parse_xprt(flat_model(300).text))
    result = index.find_objects(limit=1000)
    assert len(result.items) == 200
    assert result.truncated is True
    assert result.evidence["items_total"] == 300


def test_check_connections_is_capped():
    index = ModelIndex(parse_xprt(loose_model(300).text))
    result = index.check_connections()
    assert len(result.items) <= 200
    assert result.truncated is True
    assert result.evidence["violations_total"] == 600
    assert result.evidence["items_total"] == 600


def test_check_connections_puts_errors_first():
    index = ModelIndex(parse_xprt(broken_model(300).text))
    result = index.check_connections()
    assert result.evidence["status"] == "fail"
    assert result.items[0]["code"] == "wire_end_unresolved"
    assert result.truncated is True


def test_list_discrepancies_reports_total_before_limit():
    index = ModelIndex(parse_xprt(unknown_type(300).text))
    result = index.list_discrepancies(limit=50)
    assert len(result.items) == 50
    assert result.evidence["items_total"] == 300
    assert result.truncated is True


def test_trace_signal_reports_total_before_cap():
    index = ModelIndex(parse_xprt(flat_model(300).text))
    result = index.trace_signal("main::B0", max_depth=10000)
    assert len(result.items) == 200
    assert result.evidence["items_total"] == 600
    assert result.truncated is True


def test_trace_both_deduplicates_unknown():
    index = ModelIndex(parse_xprt(broken_model(3).text))
    result = index.trace_signal("main::B0", direction="both")
    assert len(result.unknown) == 1
    assert result.evidence["unknown_total"] == 1


def test_required_inputs_connected_uses_full_count_when_capped():
    index = ModelIndex(parse_xprt(loose_model(300).text))
    result = index.validate_invariants([
        {"id": "inputs", "kind": "required_inputs_connected"},
    ])
    assert result.items[0]["status"] == "failed"
    assert "300" in result.items[0]["detail"]


def test_no_cycles_requirement_passes_on_acyclic_chain():
    model = flat_model(10)
    spec = {
        "schema": "system-spec/1",
        "blocks": [
            {"name": f"B{index}", "class": "Усилитель",
             "ports": {"inputs": ["u"], "outputs": ["y"]}}
            for index in range(10)
        ],
        "wires": [
            {"src": f"B{index}:out:0", "dst": f"B{index + 1}:in:0"}
            for index in range(9)
        ],
        "requirements": [{
            "id": "acyclic", "check": {"kind": "no_cycles"},
            "text": "в модели нет обратных связей",
        }],
    }
    report = verify_model(parse_xprt(model.text), compile_system_spec(spec))
    assert report.verdict == "passed"
    assert report.counts["failed"] == 0


def test_compare_models_is_capped():
    left = parse_xprt(flat_model(300).text)
    right = parse_xprt(flat_model(300).text.replace(
        "`Усилитель`", "`Интегратор`"))
    result = ModelIndex(left).compare_models(right)
    assert len(result.items) <= 200
    assert result.truncated is True
    assert result.evidence["items_total"] == 300


def test_inspect_node_wires_are_capped():
    index = ModelIndex(parse_xprt(direct_star_model(300).text))
    result = index.inspect_node("main::S")
    assert len(result.items[0]["wires"]) <= 200
    assert result.items[0]["wires_total"] == 300
    assert result.truncated is True


def test_verification_counts_all_invariants_beyond_query_cap():
    spec = {
        "schema": "system-spec/1",
        "blocks": [
            {"name": "A", "class": "Усилитель",
             "ports": {"inputs": ["u"], "outputs": ["y"]}},
            {"name": "B", "class": "Усилитель",
             "ports": {"inputs": ["u"], "outputs": ["y"]}},
        ],
        "wires": [
            {"src": "A:out:0", "dst": "B:in:0"},
            {"src": "B:out:0", "dst": "A:in:0"},
        ],
        "invariants": [
            {"id": f"names{index}", "kind": "unique_object_names"}
            for index in range(200)
        ] + [{"id": "depth", "kind": "container_depth", "max": -1}],
    }
    report = verify_model(
        parse_xprt(cycle_model().text), compile_system_spec(spec))
    assert report.counts["failed"] == 1
    assert report.verdict == "failed"
    assert report.truncated is True
    assert any(item["id"] == "depth" and item["status"] == "failed"
               for item in report.items)


def test_verification_report_is_capped():
    class_name = "Arduino - I2C - Ведомый I2C"
    objects = "".join(
        f"<object><name>`U{index}`</name>"
        f"<class_name>`{class_name}`</class_name>"
        f"<obj_type>`100`</obj_type></object>"
        for index in range(300))
    actual = parse_xprt(
        f"<Header><project><page>{objects}</page></project></Header>")
    spec = {
        "schema": "system-spec/1",
        "blocks": [{"name": f"U{index}", "class": class_name}
                   for index in range(300)],
    }
    report = verify_model(actual, compile_system_spec(spec))
    assert len(report.items) <= 200
    assert report.truncated is True
    assert report.counts["not_evaluated"] == 300


def test_wire_indices_are_direction_ordinals():
    xml = """<Header><project><page>
  <object><name>`Step`</name><class_name>`Константа`</class_name>
    <obj_type>`100`</obj_type>
    <ports><port><name>`outport`</name><mode>`1`</mode></port></ports>
  </object>
  <object><name>`Gain`</name><class_name>`Усилитель`</class_name>
    <obj_type>`100`</obj_type>
    <ports>
      <port><name>`outport`</name><mode>`1`</mode></port>
      <port><name>`inport`</name><mode>`0`</mode></port>
    </ports>
  </object>
  <object><name>`W`</name><class_name>`Математическая связь`</class_name>
    <obj_type>`101`</obj_type>
    <start_bl_index>`0`</start_bl_index><start_port_index>`0`</start_port_index>
    <end_bl_index>`1`</end_bl_index><end_port_index>`1`</end_port_index>
  </object>
</page></project></Header>"""
    spec = {
        "schema": "system-spec/1",
        "blocks": [
            {"name": "Step", "class": "Константа",
             "ports": {"outputs": ["outport"]}},
            {"name": "Gain", "class": "Усилитель",
             "ports": {"inputs": ["inport"], "outputs": ["outport"]}},
        ],
        "wires": [{"src": "Step:out:0", "dst": "Gain:in:0"}],
    }
    report = verify_model(parse_xprt(xml), compile_system_spec(spec))
    assert report.verdict == "passed", report.items
    assert report.counts["failed"] == 0


def test_verification_report_keeps_failed_items_when_truncated():
    class_name = "Arduino - I2C - Ведомый I2C"
    objects = "".join(
        f"<object><name>`U{index}`</name>"
        f"<class_name>`{class_name}`</class_name>"
        f"<obj_type>`100`</obj_type></object>"
        for index in range(300))
    objects += (
        "<object><name>`Bf`</name><class_name>`Усилитель`</class_name>"
        "<obj_type>`100`</obj_type><ports>"
        "<port><name>`u`</name><mode>`0`</mode></port>"
        "<port><name>`y`</name><mode>`1`</mode></port></ports></object>")
    actual = parse_xprt(
        f"<Header><project><page>{objects}</page></project></Header>")
    spec = {
        "schema": "system-spec/1",
        "blocks": [{"name": f"U{index}", "class": class_name}
                   for index in range(300)]
        + [{"name": "Bf", "class": "Интегратор",
            "ports": {"inputs": ["Port_0"], "outputs": ["Port_1"]}}],
    }
    report = verify_model(actual, compile_system_spec(spec))
    assert report.truncated is True
    assert report.counts["failed"] == 2
    assert any(item["status"] == "failed" for item in report.items)


@pytest.mark.parametrize("budget", [2000, 3000, 5000])
def test_manifest_hard_budget_on_scale_models(budget):
    for model in (flat_model(300), deep_model(20), star_model(100),
                  wide_model(40)):
        text = build_manifest(parse_xprt(model.text),
                              budget_tokens=budget)
        assert len(text) <= budget * 3
        assert text.startswith("# Model IR")
        assert "## Coverage" in text
        assert "<?xml" not in text and "<object" not in text
        assert text == build_manifest(parse_xprt(model.text),
                                      budget_tokens=budget)


def test_manifest_omitted_is_reserved(monkeypatch):
    """Omitted не теряется, даже если вытесняет последнюю секцию."""
    from simintech_api.model_ir import manifest

    ir = parse_xprt(flat_model(3).text)
    monkeypatch.setattr(
        manifest, "_container_lines",
        lambda index: ["## Structure"] + ["s" * 100 for _ in range(55)])
    monkeypatch.setattr(
        manifest, "_classes",
        lambda index: ["## Classes"] + ["c" * 100 for _ in range(5)])
    monkeypatch.setattr(
        manifest, "_signals",
        lambda index: ["## Signals"] + ["g" * 100 for _ in range(5)])
    monkeypatch.setattr(
        manifest, "_contracts",
        lambda: ["## Contracts"] + ["x" * 100 for _ in range(5)])
    monkeypatch.setattr(
        manifest, "_hot",
        lambda index: ["## Hot nodes"] + ["h" * 100 for _ in range(5)])
    monkeypatch.setattr(
        manifest, "_discrepancies",
        lambda model: ["## Discrepancies"] + ["d" * 100 for _ in range(5)])

    text = manifest.build_manifest(ir, budget_tokens=2000)

    assert len(text) <= 6000
    assert "## Omitted" in text
    assert "containers" in text.split("## Omitted", 1)[1]
