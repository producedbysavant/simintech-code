"""Снапшоты знаний привязаны к версии среды.

Зачем: «каталог собран из поставки» без версии неотличимо от каталога,
собранного из **другой** поставки, — а имена параметров между версиями
меняются (см. `docs/gap-closure-plan.md`, Н1: у «Интегратора с ограничением»
появились `minmaxsource` и `resettype`, которых прежний прогон не видел).
Тест держит поле обязательным, чтобы оно не потерялось при пересборке.

Честное `unknown` допускается: у текущих файлов дата прогона не зафиксирована,
и подставлять догадку хуже, чем признать пропуск.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[2] / "simintech_api" / "data"

SNAPSHOTS = ["block_catalog.json", "language_functions.json"]

REQUIRED_FIELDS = ["product", "version", "observed_at", "generator"]

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _observation(name: str) -> dict:
    data = json.loads((DATA / name).read_text(encoding="utf-8"))
    return data.get("meta", {}).get("observation") or {}


@pytest.mark.parametrize("name", SNAPSHOTS)
def test_snapshot_records_its_observation(name):
    """У снапшота есть observation и в нём заполнены обязательные поля."""
    observation = _observation(name)
    assert observation, f"{name}: нет meta.observation — знание не привязано к версии"
    for field in REQUIRED_FIELDS:
        assert observation.get(field), f"{name}: в observation пусто поле {field}"


@pytest.mark.parametrize("name", SNAPSHOTS)
def test_observed_at_is_a_date_or_unknown(name):
    """Дата наблюдаемая или честное `unknown` — но не выдумка."""
    value = str(_observation(name)["observed_at"])
    assert value == "unknown" or ISO_DATE.match(value), (
        f"{name}: observed_at={value!r} — нужна дата ISO или «unknown»"
    )


def test_generator_fills_observation_for_a_fresh_catalog():
    """Свежая сборка каталога сама проставляет наблюдение.

    Иначе поле живёт только в файле, и первая же пересборка его потеряет.
    """
    from simintech_api.catalog import build_catalog_from_xprt

    catalog = build_catalog_from_xprt("<project><objects /></project>")
    observation = catalog.meta.get("observation") or {}

    assert str(observation.get("generator", "")).startswith("simintech-api ")
    assert observation.get("dump_sha256"), "нет отпечатка выгрузки"
    assert ISO_DATE.match(str(observation.get("observed_at")))
    assert observation.get("product") == "SimInTech"
