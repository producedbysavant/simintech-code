"""Реестр фактов: целостность ссылок и синхронность производных видов.

Проверки делятся надвое: **реальный** реестр обязан быть цел (иначе гейт
бесполезен), а на подставных записях проверяется, что валидатор **ловит**
поломки схемы v3 — иначе он зелён по построению и не отличает «всё хорошо» от
«ничего не проверено». Главные правила схемы: производный документ не повышает
статус, тест на фейке не делает факт живым, у «подтверждено» есть версия и дата.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(
    0,
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts")),
)

from evidence import (  # noqa: E402
    CONTRADICTIONS,
    MATRIX,
    load_claims,
    render_contradictions,
    render_matrix,
    validate,
)


def _claim(**overrides):
    """Запись-образец: валидная, пока её не испортили намеренно."""
    base = {
        "id": "example-claim",
        "statement": "Пример факта",
        "status": "live-verified",
        "source": {
            "type": "live-com",
            "ref": "simintech-mcp/docs/roadmap-agentic-ecosystem.md §1",
        },
        "environment": {
            "product": "SimInTech64",
            "version": "2.26.6.23",
            "observed_at": "2026-09-26",
        },
        "reproduction": "живой прогон: создать проект и прочитать время",
        "tests": [],
    }
    base.update(overrides)
    return base


def _derived(**overrides):
    """Запись на производном источнике — допустима только как гипотеза."""
    base = {"source": {"type": "derived-doc", "ref": "simintech-mcp/README.md"}}
    base.update(overrides)
    return _claim(environment=None, reproduction="", **base)


def test_real_registry_is_valid():
    """Реестр репозитория проходит проверки, и он не пуст."""
    claims = load_claims()
    assert claims, "реестр пуст — проверять нечего"
    assert validate(claims) == []


def test_matrix_matches_the_registry():
    """Матрица — производная: расхождение значит, что её не перегенерировали."""
    assert MATRIX.read_text(encoding="utf-8") == render_matrix(load_claims())


def test_contradictions_match_the_registry():
    """Вид противоречий — та же производная, и он тоже сверяется."""
    assert CONTRADICTIONS.read_text(encoding="utf-8") == render_contradictions(
        load_claims())


def test_duplicate_id_is_caught():
    problems = validate([_claim(), _claim()])
    assert any("повторяется" in problem for problem in problems)


def test_documented_requires_official_doc():
    """«В справке написано» — только с источником official-doc."""
    claim = _claim(status="documented",
                   source={"type": "source-code",
                           "ref": "simintech_api/constants.py"})
    problems = validate([claim])
    assert any("требует источник" in problem for problem in problems)


def test_vendor_confirmed_requires_vendor_source():
    """Ответ поддержки — это тип `vendor`, а не `live-com`."""
    problems = validate([_claim(status="vendor-confirmed")])
    assert any("требует источник" in problem for problem in problems)


def test_derived_doc_does_not_raise_status():
    """Повторение в README не доказывает: с derived-doc статус не выше гипотезы."""
    problems = validate([_derived(status="live-verified")])
    assert any("производный документ" in problem for problem in problems)


def test_derived_hypothesis_is_allowed(tmp_path):
    """Гипотеза на производном источнике — законная запись.

    Корень — пустой (`tmp_path`): проверка цитат базы знаний сверяет id
    документа `docs/knowledge/**` с **полным** реестром, а здесь реестр
    синтетический из одной записи — на реальном каталоге это заведомо
    расхождение, не относящееся к проверяемому правилу.
    """
    assert validate([_derived(status="hypothesis")], root=tmp_path) == []


def test_live_verified_without_environment_is_caught():
    """«Подтверждено» без версии и даты непроверяемо."""
    claim = _claim()
    claim.pop("environment")
    problems = validate([claim])
    assert any("без version" in problem for problem in problems)
    assert any("без product" in problem for problem in problems)


def test_live_verified_without_reproduction_is_caught():
    problems = validate([_claim(reproduction="")])
    assert any("без reproduction" in problem for problem in problems)


def test_contradicted_without_contradicted_by_is_caught():
    problems = validate([_claim(status="contradicted")])
    assert any("contradicted_by" in problem for problem in problems)


def test_unit_fake_cannot_be_the_only_basis_for_live_verified():
    """Тест на подделке не делает факт живым — это код-подтверждение."""
    tests = [{
        "file": "tests/unit/test_block.py",
        "id": "test_set_in_port_count_adds_inputs",
        "kind": "unit-fake",
    }]
    problems = validate([_claim(tests=tests, reproduction="")])
    assert any("только на тест на фейке" in problem for problem in problems)


def test_ref_to_missing_local_path_is_caught():
    """Локальная ссылка на несуществующий документ — висячий провенанс."""
    source = {"type": "live-com", "ref": "docs/no-such-document.md §1"}
    problems = validate([_claim(source=source)])
    assert any("несуществующий путь" in problem for problem in problems)


def test_sibling_ref_is_accepted(tmp_path):
    """Ссылка в соседний репозиторий принимается с квалификацией репозитория."""
    source = {"type": "derived-doc", "ref": "simintech-skill/README.md"}
    assert validate([_derived(status="hypothesis", source=source)],
                    root=tmp_path) == []


def test_supersedes_unknown_id_is_caught():
    problems = validate([_claim(supersedes=["no-such-fact"])])
    assert any("supersedes" in problem for problem in problems)


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


def test_unknown_test_kind_is_caught():
    tests = [
        {"file": "tests/unit/test_block.py", "id": "test_set_in_port_count_adds_inputs",
         "kind": "unit"}
    ]
    problems = validate([_claim(tests=tests)])
    assert any("неизвестный вид теста" in problem for problem in problems)


def test_knowledge_citation_must_exist(tmp_path):
    """id в таблице базы знаний обязан быть записью реестра."""
    knowledge = tmp_path / "docs" / "knowledge"
    knowledge.mkdir(parents=True)
    (knowledge / "01-example.md").write_text(
        "| `example-claim` | ok |\n", encoding="utf-8")
    assert validate([_claim()], root=tmp_path) == []

    (knowledge / "01-example.md").write_text(
        "| `no-such-fact` | oh |\n", encoding="utf-8")
    problems = validate([_claim()], root=tmp_path)
    assert any("нет в реестре" in problem for problem in problems)
