"""Эталонная таблица семантики и её перенос в реестр контрактов."""

import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
TABLE = ROOT / "tests" / "fixtures" / "semantics" / "pilot_blocks.yaml"
REGISTRY = ROOT / "simintech_api" / "data" / "block_contracts.json"


def _table():
    return yaml.safe_load(TABLE.read_text(encoding="utf-8"))


def test_pilot_table_has_ten_classes_and_scopes():
    classes = _table()["classes"]
    assert len([name for name, row in classes.items()
                if row["scope"] != "auxiliary"]) == 10
    assert classes[
        "Коммутатор входных сигналов по номеру порта"
    ]["scope"] == "synthetic_only"
    assert classes[
        "Ключ управляемый перекидной по входам тип 2"
    ]["scope"] == "live_acceptance"
    assert classes["Ключ-3"]["scope"] == "auxiliary"


def test_pilot_table_matches_registry():
    result = subprocess.run(
        [sys.executable, "scripts/merge_pilot_semantics.py", "--check"],
        cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_auxiliary_scope_is_preserved():
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert registry["classes"]["Ключ-3"]["pilot_scope"] == "auxiliary"
    assert ("Коммутатор входных сигналов по номеру порта"
            not in registry["classes"])
