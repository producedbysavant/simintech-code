"""Проверка реестра утверждений и сборка матрицы проверки.

Реестр (`docs/evidence/claims.yaml`) нужен затем, чтобы агент и человек
различали «подтверждено живым замером», «покрыто тестом на подделке» и
«предполагается». Без валидатора он превращается в ещё один документ, который
расходится с кодом: тест переименовали — ссылка на него осталась, и запись
выглядит подтверждённой, хотя за ней уже ничего нет.

Матрица (`verification-matrix.md`) — производное: она генерируется отсюда, и
её расхождение с реестром ловит тест.

Запуск: `python scripts/evidence.py`
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, List, Sequence

import yaml

ROOT = Path(__file__).resolve().parents[1]
CLAIMS = ROOT / "docs" / "evidence" / "claims.yaml"
MATRIX = ROOT / "docs" / "evidence" / "verification-matrix.md"

#: Тип источника: откуда взято утверждение.
SOURCE_TYPES = {
    "official-doc",          # справка поставки
    "live-com",              # живой прогон через COM
    "xprt-observation",      # наблюдение в выгрузке проекта
    "source-code",           # следует из кода (в т.ч. чужого — поставки)
    "controlled-experiment",  # поставленный опыт (сравнение вариантов)
    "inference",             # вывод, не проверенный напрямую
    "unknown",
}

STATUSES = {
    "verified",         # подтверждено источником вне нашего кода
    "measured",         # живой замер в документе, автотеста нет
    "unit-only",        # покрыто только тестом на подделке
    "refuted",          # проверено и опровергнуто
    "unknown",
    "version-specific",  # верно для конкретной версии
}

TEST_KINDS = {"live", "unit", "distribution"}

#: Статусы, для которых источник обязан быть датированным: «проверено» без
#: версии и даты непроверяемо.
_DATED_STATUSES = {"verified", "measured", "refuted"}

#: Тип источника, при котором автотест не требуется: справка вендора сама
#: является доказательством.
_SELF_SUFFICIENT_SOURCES = {"official-doc"}

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")


def load_claims(path: Path = CLAIMS) -> List[Dict]:
    """Записи реестра; пустой файл — пустой список."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError("claims.yaml должен содержать список утверждений")
    return data


def validate(claims: Sequence[Dict], root: Path = ROOT) -> List[str]:
    """Нарушения реестра; пустой список — реестр цел."""
    problems: List[str] = []
    seen: set[str] = set()

    for claim in claims:
        cid = str(claim.get("id", ""))
        if not _ID_RE.match(cid):
            problems.append(f"{cid!r}: id должен быть kebab-case (3+ символа)")
        if cid in seen:
            problems.append(f"{cid}: id повторяется")
        seen.add(cid)

        status = claim.get("status")
        if status not in STATUSES:
            problems.append(f"{cid}: неизвестный статус {status!r}")

        source = claim.get("source") or {}
        if source.get("type") not in SOURCE_TYPES:
            problems.append(f"{cid}: неизвестный тип источника {source.get('type')!r}")
        if status in _DATED_STATUSES:
            if not source.get("observed_at"):
                problems.append(f"{cid}: статус {status} без даты наблюдения")
            if not source.get("product_version"):
                problems.append(f"{cid}: статус {status} без версии продукта")

        if status == "refuted" and not claim.get("evidence"):
            problems.append(
                f"{cid}: опровергнутое утверждение без записи, чем опровергнуто"
            )

        tests = claim.get("tests") or []
        if status == "verified":
            if not tests and source.get("type") not in _SELF_SUFFICIENT_SOURCES:
                problems.append(
                    f"{cid}: verified без подтверждающего теста — для этого статуса "
                    f"нужен живой или distribution-тест (или источник official-doc)"
                )
            kinds = {test.get("kind") for test in tests}
            if tests and not kinds & {"live", "distribution"}:
                problems.append(
                    f"{cid}: verified подтверждён только тестом на подделке — "
                    f"это статус unit-only, а не verified"
                )
        for test in tests:
            problems.extend(_test_problems(cid, test, root))

    return problems


def _test_problems(cid: str, test: Dict, root: Path) -> List[str]:
    """Проверить одну ссылку на тест: файл есть, имя теста в нём есть."""
    problems: List[str] = []
    rel = str(test.get("file", ""))
    target = root / rel
    if test.get("kind") not in TEST_KINDS:
        problems.append(f"{cid}: неизвестный вид теста {test.get('kind')!r}")
    if not target.is_file():
        problems.append(f"{cid}: файла теста {rel!r} нет")
        return problems
    name = str(test.get("id", ""))
    if not name:
        problems.append(f"{cid}: у теста {rel!r} не указано имя")
    elif f"def {name}(" not in target.read_text(encoding="utf-8"):
        problems.append(f"{cid}: теста {name!r} нет в {rel!r}")
    return problems


def render_matrix(claims: Sequence[Dict]) -> str:
    """Матрица проверки — производная от реестра, а не второй его вид."""
    lines = [
        "# Матрица проверки утверждений",
        "",
        "Файл сгенерирован `scripts/evidence.py` из `claims.yaml` — правьте реестр.",
        "",
        "`kind` показывает, чем утверждение подтверждено: `live` — живой прогон,",
        "`distribution` — сверка с поставкой, `unit` — тест на подделке (контракт",
        "кода, не поведение среды).",
        "",
        "| id | статус | источник | версия | дата | подтверждение |",
        "|---|---|---|---|---|---|",
    ]
    for claim in claims:
        source = claim.get("source") or {}
        tests = claim.get("tests") or []
        if tests:
            proof = ", ".join(
                f"`{t.get('file')}::{t.get('id')}` ({t.get('kind')})" for t in tests
            )
        else:
            proof = "—"
        lines.append(
            f"| `{claim.get('id')}` | {claim.get('status')} | "
            f"{source.get('type')} | {source.get('product_version', '—')} | "
            f"{source.get('observed_at', '—')} | {proof} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    """0 — реестр цел и матрица обновлена; 1 — нарушения (печатает их)."""
    claims = load_claims()
    problems = validate(claims)
    if problems:
        print("\n".join(problems))
        print(f"\nНарушений: {len(problems)}. Правьте docs/evidence/claims.yaml.")
        return 1
    MATRIX.write_text(render_matrix(claims), encoding="utf-8")
    print(f"Реестр цел: утверждений {len(claims)}; матрица обновлена.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
