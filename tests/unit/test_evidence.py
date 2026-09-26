"""Реестр утверждений: целостность ссылок и синхронность матрицы.

Проверки делятся надвое: **реальный** реестр обязан быть цел (иначе гейт
бесполезен), а на подставных записях проверяется, что валидатор **ловит**
поломки — иначе он зелён по построению и не отличает «всё хорошо» от «ничего
не проверено».
"""

from __future__ import annotations

import os
import sys

sys.path.insert(
    0,
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts")),
)

from evidence import (  # noqa: E402
    MATRIX,
    load_claims,
    render_matrix,
    validate,
)


def _claim(**overrides):
    """Запись-образец: валидная, пока её не испортили намеренно."""
    base = {
        "id": "example-claim",
        "claim": "Пример утверждения",
        "status": "measured",
        "source": {
            "type": "live-com",
            "ref": "docs/evidence/sources.md",
            "product_version": "SimInTech64",
            "observed_at": "2026-09-26",
        },
        "evidence": "замер",
        "tests": [],
    }
    base.update(overrides)
    return base


def test_real_registry_is_valid():
    """Реестр репозитория проходит проверки, и он не пуст."""
    claims = load_claims()
    assert claims, "реестр пуст — проверять нечего"
    assert validate(claims) == []


def test_matrix_matches_the_registry():
    """Матрица — производная: расхождение значит, что её не перегенерировали."""
    assert MATRIX.read_text(encoding="utf-8") == render_matrix(load_claims())


def test_duplicate_id_is_caught():
    problems = validate([_claim(), _claim()])
    assert any("повторяется" in problem for problem in problems)


def test_verified_without_live_test_is_caught():
    problems = validate([_claim(status="verified")])
    assert any("без подтверждающего теста" in problem for problem in problems)


def test_unit_test_does_not_make_a_claim_verified():
    """Тест на подделке не подтверждает поведение среды — это unit-only."""
    tests = [
        {
            "file": "tests/unit/test_block.py",
            "id": "test_set_in_port_count_adds_inputs",
            "kind": "unit",
        }
    ]
    problems = validate([_claim(status="verified", tests=tests)])
    assert any("unit-only" in problem for problem in problems)


def test_missing_test_file_is_caught():
    tests = [{"file": "tests/unit/нет_такого.py", "id": "test_x", "kind": "live"}]
    problems = validate([_claim(tests=tests)])
    assert any("нет" in problem for problem in problems)


def test_missing_test_name_is_caught():
    tests = [
        {"file": "tests/unit/test_block.py", "id": "test_нет_такого", "kind": "live"}
    ]
    problems = validate([_claim(tests=tests)])
    assert any("нет в" in problem for problem in problems)


def test_measured_without_date_is_caught():
    """«Проверено» без даты и версии непроверяемо."""
    source = {"type": "live-com", "product_version": "SimInTech64"}
    problems = validate([_claim(source=source)])
    assert any("без даты наблюдения" in problem for problem in problems)


def test_refuted_without_evidence_is_caught():
    problems = validate([_claim(status="refuted", evidence="")])
    assert any("чем опровергнуто" in problem for problem in problems)
