"""Синтетический коммутатор: nport_named и условный выбор."""

import json
import os
import sys
from pathlib import Path

import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from simintech_api.model_ir import (  # noqa: E402
    BlockContractRegistry,
    ModelIndex,
    influence,
    parse_xprt,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "tests" / "fixtures" / "semantics" / "commutator_contract.json"
MODEL = ROOT / "tests" / "fixtures" / "semantics" / "commutator_model.xprt"
QUESTIONS = ROOT / "tests" / "fixtures" / "semantics" / "synthetic_questions.yaml"


def _registry():
    return BlockContractRegistry(json.loads(
        CONTRACT.read_text(encoding="utf-8")))


def test_nport_named_ports_expand():
    ports = _registry().ports_for(
        "Коммутатор входных сигналов по номеру порта", {"nport": "3"})
    assert [(item.index, item.name) for item in ports.inputs] == [
        (0, "number"), (1, "data_1"), (2, "data_2"), (3, "data_3")]
    assert [(item.index, item.name) for item in ports.outputs] == [
        (4, "outport")]


def test_influence_commutator_control_and_data_separate():
    index = ModelIndex(parse_xprt(MODEL.read_text(encoding="utf-8")))
    result = influence(index, _registry(), "main::Mux:4")
    control = [item for item in result.items
               if any(hop["kind"] == "control" for hop in item["hops"])]
    branches = [item for item in result.items
                if any(hop["kind"] == "conditional" for hop in item["hops"])]
    assert len(control) == 1
    assert len(branches) == 3
    assert control[0]["hops"][0]["kind"] == "control"
    assert {item["source"]["address"] for item in branches} == {
        "main::Mux:1", "main::Mux:2", "main::Mux:3"}
    assert {hop["condition"]["cases"][0]["value"]
            for item in branches for hop in item["hops"]
            if hop["kind"] == "conditional"} == {1, 2, 3}


def test_synthetic_questions_are_public_and_expected_unknowns():
    text = QUESTIONS.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert data["schema"] == "synthetic-questions/1"
    assert data["questions"]
    assert data["questions"][0]["expected_unknown"]
    assert "electric-drive" not in text
