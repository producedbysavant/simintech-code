"""Model IR: экспериментальные свидетельства и ограничения influence."""

import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from simintech_api.model_ir import (  # noqa: E402
    ModelIndex,
    ModelQueryError,
    parse_xprt,
)
from simintech_api.model_ir.experiments import (  # noqa: E402
    EXPERIMENT_SCHEMA,
    parse_experiment_record,
    parse_experiment_records,
)
from simintech_api.model_ir.semantics import influence  # noqa: E402

from test_model_ir_semantics import (  # noqa: E402
    MODEL,
    _chain_to,
    _semantic_data,
    _semantic_registry,
)


def _index():
    return ModelIndex(parse_xprt(MODEL))


def _record(index, **overrides):
    data = {
        "schema": EXPERIMENT_SCHEMA,
        "id": "exp-1",
        "structure_hash": index.model.meta.structure_hash,
        "content_hash": index.model.meta.content_hash,
        "scenario": {
            "changed": "main::K:0", "from": 0.0, "to": 1.0, "at": 0.1},
        "run": {"step": 1e-6, "to_time": 0.5, "baseline": "base-1"},
        "observation": {
            "target": "main::S:0", "changed": True, "first_change_at": 0.1002},
        "status": "observed",
        "recorded_at": "2026-11-06",
        "limitations": [],
    }
    data.update(overrides)
    return data


def _preliminary_registry():
    data = copy.deepcopy(_semantic_data())
    data["Усилитель"]["review"] = {
        "status": "preliminary", "reviewer": "", "date": "",
        "ref": "pilot_blocks.yaml:Усилитель",
    }
    return _semantic_registry(data)


def test_parse_experiment_record_full_fields():
    record = parse_experiment_record(_record(_index()))
    assert record.id == "exp-1"
    assert record.target == "main::S:0"
    assert record.source == "main::K:0"
    assert record.observed is True
    assert record.run["baseline"] == "base-1"
    assert record.to_dict()["observation"]["changed"] is True


@pytest.mark.parametrize("field", ["structure_hash", "content_hash"])
def test_parse_experiment_record_requires_hashes(field):
    data = _record(_index())
    data[field] = ""
    with pytest.raises(ModelQueryError):
        parse_experiment_record(data)


def test_parse_experiment_record_allows_negative_scenario_values():
    data = _record(_index())
    data["scenario"]["from"] = -1.0
    data["scenario"]["to"] = 0.0
    record = parse_experiment_record(data)
    assert record.scenario["from"] == -1.0


def test_parse_experiment_record_rejects_target_as_source():
    data = _record(_index())
    data["scenario"]["changed"] = "main::S:0"
    with pytest.raises(ModelQueryError):
        parse_experiment_record(data)


def test_parse_experiment_record_requires_changed_source():
    data = _record(_index())
    data["scenario"]["changed"] = ""
    with pytest.raises(ModelQueryError):
        parse_experiment_record(data)


def test_parse_experiment_record_requires_run_conditions():
    data = _record(_index())
    data["run"]["step"] = 0
    with pytest.raises(ModelQueryError):
        parse_experiment_record(data)


def test_parse_experiment_record_requires_bool_observation():
    data = _record(_index())
    data["observation"]["changed"] = 1
    with pytest.raises(ModelQueryError):
        parse_experiment_record(data)


def test_parse_experiment_record_rejects_unknown_schema():
    data = _record(_index())
    data["schema"] = "experiment-record/2"
    with pytest.raises(ModelQueryError):
        parse_experiment_record(data)


def test_parse_experiment_records_rejects_duplicate_ids():
    data = _record(_index())
    with pytest.raises(ModelQueryError):
        parse_experiment_records([data, dict(data)])


def test_influence_experiment_marks_chain():
    index = _index()
    result = influence(
        index, _preliminary_registry(), "main::S:0",
        experiments=[_record(index)])
    chain = _chain_to(result, "main::K@property:a")
    assert chain["evidence"]["status"] == "experiment"
    assert chain["evidence"]["ref"] == "experiment:exp-1"
    assert chain["evidence"]["experiments"] == ["exp-1"]
    assert result.evidence["experiments"] == {
        "supplied": 1, "applied": 1, "blocked": 0,
        "negative": 0, "inapplicable": 0}
    assert any(item["kind"] == "experiment_scope"
               for item in result.evidence["limitations"])
    assert result.evidence["known_absences"] == []


def test_influence_experiment_does_not_downgrade_contract():
    index = _index()
    result = influence(
        index, _semantic_registry(), "main::S:0",
        experiments=[_record(index)])
    chain = _chain_to(result, "main::K@property:a")
    assert chain["evidence"]["status"] == "contract"
    assert chain["evidence"]["experiments"] == ["exp-1"]


def test_influence_experiment_hash_mismatch_is_inapplicable():
    index = _index()
    data = _record(index, structure_hash="0" * 64)
    result = influence(
        index, _preliminary_registry(), "main::S:0", experiments=[data])
    chain = _chain_to(result, "main::K@property:a")
    assert chain["evidence"]["status"] == "not_established"
    assert result.evidence["experiments"]["inapplicable"] == 1
    assert any(item["kind"] == "experiment_inapplicable"
               for item in result.evidence["limitations"])


def test_influence_negative_experiment_does_not_create_absence():
    index = _index()
    data = _record(index)
    data["observation"]["changed"] = False
    result = influence(
        index, _preliminary_registry(), "main::S:0", experiments=[data])
    chain = _chain_to(result, "main::K@property:a")
    assert chain["evidence"]["status"] == "not_established"
    assert result.evidence["experiments"]["negative"] == 1
    assert result.evidence["known_absences"] == []
    assert any(item["kind"] == "experiment_negative"
               for item in result.evidence["limitations"])


def test_influence_experiment_target_missing_is_unmatched():
    index = _index()
    data = _record(index)
    data["observation"]["target"] = "main::Nope:0"
    result = influence(
        index, _preliminary_registry(), "main::S:0", experiments=[data])
    assert result.evidence["experiments"]["applied"] == 0
    assert any(item["kind"] == "experiment_unmatched"
               for item in result.evidence["limitations"])


def test_influence_experiment_object_source_is_wider():
    index = _index()
    data = _record(index)
    data["scenario"]["changed"] = "main::K"
    result = influence(
        index, _preliminary_registry(), "main::S:0", experiments=[data])
    chain = _chain_to(result, "main::K@property:a")
    assert chain["evidence"]["status"] == "experiment"
    assert any(item["kind"] == "experiment_object_address"
               for item in result.evidence["limitations"])


def test_influence_include_filters_experiment():
    index = _index()
    data = _record(index)
    result = influence(
        index, _preliminary_registry(), "main::S:0",
        include=("contract",), experiments=[data])
    assert result.items == ()
    assert result.evidence["experiments"]["applied"] == 1
    assert any(item["kind"] == "experiment_filtered"
               for item in result.evidence["limitations"])

    only = influence(
        index, _preliminary_registry(), "main::S:0",
        include=("experiment",), experiments=[data])
    assert only.items
    assert all(item["evidence"]["status"] == "experiment"
               for item in only.items)


def test_influence_limitations_are_always_present():
    result = influence(
        _index(), _semantic_registry(), "main::S:0")
    assert result.evidence["limitations"]
    assert any(item["kind"] == "experiments_absent"
               for item in result.evidence["limitations"])


def test_influence_truncated_adds_limitation():
    result = influence(
        _index(), _semantic_registry(), "main::S:0", max_items=0)
    assert result.truncated is True
    assert any(item["kind"] == "truncated"
               for item in result.evidence["limitations"])


def test_influence_rejected_chain_is_not_upgraded():
    data = copy.deepcopy(_semantic_data())
    data["Усилитель"]["review"] = {
        "status": "rejected", "reviewer": "инженер",
        "date": "2026-11-06", "ref": "pilot_blocks.yaml:Усилитель",
    }
    result = influence(
        _index(), _semantic_registry(data), "main::S:0",
        experiments=[_record(_index())])
    chain = _chain_to(result, "main::K@property:a")
    assert chain["evidence"]["status"] == "not_established"
    assert chain["evidence"]["reason"] == "rejected"
    assert "experiments" not in chain["evidence"]
    assert result.evidence["experiments"]["blocked"] == 1
    assert any(item["kind"] == "experiment_not_applicable"
               for item in result.evidence["limitations"])


def test_influence_rejects_too_many_experiments():
    index = _index()
    records = [_record(index, id=f"exp-{number}") for number in range(101)]
    with pytest.raises(ModelQueryError):
        influence(
            index, _preliminary_registry(), "main::S:0",
            experiments=records)


def test_parse_experiment_record_rejects_too_many_limitations():
    data = _record(_index())
    data["limitations"] = ["ограничение"] * 21
    with pytest.raises(ModelQueryError):
        parse_experiment_record(data)
