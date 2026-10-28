"""Проверка реестра фактов и сборка производных видов (матрица, противоречия).

Реестр (`docs/evidence/claims.yaml`, схема v3) нужен затем, чтобы агент и
человек различали «подтверждено живым замером», «следует из кода», «покрыто
тестом на подделке» и «предполагается». Без валидатора он превращается в ещё
один документ, который расходится с кодом: тест переименовали — ссылка на него
осталась, и запись выглядит подтверждённой, хотя за ней уже ничего нет.

Правила схемы v3 (их и проверяем):

* **статус × источник**: `documented` ← `official-doc`, `live-verified` ←
  {`live-com`, `controlled-experiment`, `xprt-observation`},
  `vendor-confirmed` ← `vendor`, `code-confirmed` ← `source-code`;
* **производный документ не доказывает**: с `derived-doc` (README, скиллы,
  журналы) допустимы только `hypothesis`/`unknown`/`contradicted` — повторение
  утверждения в README статус не повышает;
* **тест на фейке** (`unit-fake`) не может быть единственной опорой
  `live-verified`;
* у `live-verified`/`vendor-confirmed` обязательны версия, дата
  (`environment`) и `reproduction`;
* ссылки `ref` репо-квалифицированы; локальные пути обязаны существовать;
* id, названные в таблицах `docs/knowledge/**/*.md`, обязаны существовать.

Производные виды (`verification-matrix.md`, `contradictions.md`) генерируются
отсюда; их расхождение с реестром ловит тест.

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
CONTRADICTIONS = ROOT / "docs" / "evidence" / "contradictions.md"

#: Тип источника: откуда взято утверждение.
SOURCE_TYPES = {
    "official-doc",           # справка поставки, help.simintech.ru
    "vendor",                 # ответ поддержки вендора, листинг его исходника
    "live-com",               # живой прогон через COM
    "controlled-experiment",  # поставленный опыт (сравнение вариантов)
    "xprt-observation",       # наблюдение в выгрузке проекта
    "source-code",            # следует из кода (нашего или поставки)
    "derived-doc",            # производный документ: README, скиллы, журналы
}

STATUSES = {
    "documented",        # так написано в официальной документации
    "code-confirmed",    # следует из кода; тест на фейке — контракт кода
    "live-verified",     # живой прогон / опыт / наблюдение выгрузки
    "vendor-confirmed",  # вендор подтвердил (поддержка, листинг исходника)
    "hypothesis",        # предположение
    "contradicted",      # проверено и опровергнуто
    "unknown",           # не измерено
}

TEST_KINDS = {"live", "unit-fake", "unit-pure", "distribution"}

#: Какие источники законны для статуса. Статусов вне словаря здесь нет:
#: hypothesis/contradicted/unknown принимают любой источник.
_STATUS_SOURCES = {
    "documented": {"official-doc"},
    "live-verified": {"live-com", "controlled-experiment", "xprt-observation"},
    "vendor-confirmed": {"vendor"},
    "code-confirmed": {"source-code"},
}

#: Статусы, требующие версии и даты: без них «подтверждено» непроверяемо.
_DATED_STATUSES = {"live-verified", "vendor-confirmed"}

#: С производным документом допустимы только эти статусы.
_DERIVED_ALLOWED = {"hypothesis", "contradicted", "unknown"}

#: Префиксы чужих репозиториев: существование пути там не проверить (соседний
#: checkout не обязан лежать рядом) — такие ссылки принимаются с квалификацией
#: репозитория, а не молчаливым относительным путём.
_SIBLING_PREFIXES = ("simintech-mcp/", "simintech-skill/")

#: Префиксы локальных путей: обязаны существовать в этом репозитории.
_LOCAL_PREFIXES = (
    "docs/", "simintech_api/", "tests/", "scripts/", "automation/",
    "language/", "blocks/", "patterns/", "tutorials/", "examples/",
    ".github/",
)

_PATH_RE = re.compile(r"([A-Za-z0-9_./-]+\.(?:md|py|json|yaml|inc|txt|pak|tbl))")
_KNOWLEDGE_CITATION_RE = re.compile(r"^\|\s*`([a-z0-9][a-z0-9-]{2,})`\s*\|")
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")


def load_claims(path: Path = CLAIMS) -> List[Dict]:
    """Записи реестра; пустой файл — пустой список."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError("claims.yaml должен содержать список записей")
    return data


def validate(claims: Sequence[Dict], root: Path = ROOT) -> List[str]:
    """Нарушения реестра; пустой список — реестр цел."""
    problems: List[str] = []
    seen: set[str] = set()
    ids = {str(claim.get("id", "")) for claim in claims}

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
        stype = source.get("type")
        if stype not in SOURCE_TYPES:
            problems.append(f"{cid}: неизвестный тип источника {stype!r}")

        allowed = _STATUS_SOURCES.get(str(status))
        if allowed is not None and stype not in allowed:
            problems.append(
                f"{cid}: статус {status!r} требует источник "
                f"{sorted(allowed)}, а указан {stype!r}")

        if stype == "derived-doc" and status not in _DERIVED_ALLOWED:
            problems.append(
                f"{cid}: производный документ не доказывает статус {status!r} "
                f"(с ним допустимы {sorted(_DERIVED_ALLOWED)})")

        if status in _DATED_STATUSES:
            environment = claim.get("environment") or {}
            for field in ("product", "version", "observed_at"):
                if not environment.get(field):
                    problems.append(
                        f"{cid}: статус {status} без {field} в environment — "
                        f"«подтверждено» без версии и даты непроверяемо")
            if not str(claim.get("reproduction") or "").strip():
                problems.append(
                    f"{cid}: статус {status} без reproduction — не сказано, "
                    f"чем воспроизвести")

        if status == "contradicted":
            refuted = claim.get("contradicted_by") or {}
            if refuted.get("type") not in SOURCE_TYPES or not refuted.get("ref"):
                problems.append(
                    f"{cid}: contradicted без contradicted_by (type/ref) — "
                    f"не сказано, чем опровергнуто")

        for token in _PATH_RE.findall(str(source.get("ref") or "")):
            if token.startswith(_SIBLING_PREFIXES):
                continue
            if token.startswith(_LOCAL_PREFIXES) and not (root / token).exists():
                problems.append(
                    f"{cid}: ref указывает на несуществующий путь {token!r}")

        for superseded in claim.get("supersedes") or []:
            if superseded not in ids:
                problems.append(
                    f"{cid}: supersedes ссылается на неизвестную запись "
                    f"{superseded!r}")

        tests = claim.get("tests") or []
        if status == "live-verified" and tests:
            kinds = {test.get("kind") for test in tests}
            if not kinds & {"live", "distribution"} \
                    and not str(claim.get("reproduction") or "").strip():
                problems.append(
                    f"{cid}: live-verified опирается только на тест на фейке — "
                    f"это код-подтверждение, а не поведение среды")
        for test in tests:
            problems.extend(_test_problems(cid, test, root))

    problems.extend(_knowledge_citation_problems(ids, root))
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


def _knowledge_citation_problems(ids: set[str], root: Path) -> List[str]:
    """Id в таблицах `docs/knowledge/**` обязаны существовать в реестре.

    Соглашение простое: первая колонка таблицы факта — `` `id` `` из реестра.
    Так цитата в базе знаний не может пережить переименование записи. Каталога
    ещё нет — правило молчит, а не падает: разделы базы знаний приезжают своим
    PR.
    """
    knowledge = root / "docs" / "knowledge"
    if not knowledge.is_dir():
        return []
    problems: List[str] = []
    for path in sorted(knowledge.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), 1):
            match = _KNOWLEDGE_CITATION_RE.match(line)
            if match and match.group(1) not in ids:
                rel = path.relative_to(root).as_posix()
                problems.append(
                    f"{rel}:{number}: id {match.group(1)!r} нет в реестре")
    return problems


def render_matrix(claims: Sequence[Dict]) -> str:
    """Матрица проверки — производная от реестра, а не второй его вид."""
    lines = [
        "# Матрица проверки фактов",
        "",
        "Файл сгенерирован `scripts/evidence.py` из `claims.yaml` — правьте реестр.",
        "",
        "`kind` показывает, чем факт подтверждён: `live` — живой прогон,",
        "`distribution` — сверка с поставкой, `unit-pure` — чистый разбор,",
        "`unit-fake` — тест на подделке (контракт кода, не поведение среды).",
        "",
        "| id | статус | источник | версия | дата | подтверждение |",
        "|---|---|---|---|---|---|",
    ]
    for claim in claims:
        source = claim.get("source") or {}
        environment = claim.get("environment") or {}
        tests = claim.get("tests") or []
        if tests:
            proof = ", ".join(
                f"`{t.get('file')}::{t.get('id')}` ({t.get('kind')})"
                for t in tests
            )
        else:
            proof = "-"
        lines.append(
            f"| `{claim.get('id')}` | {claim.get('status')} | "
            f"{source.get('type')} | {environment.get('version', '-')} | "
            f"{environment.get('observed_at', '-')} | {proof} |"
        )
    return "\n".join(lines) + "\n"


def render_contradictions(claims: Sequence[Dict]) -> str:
    """Противоречия и записи на производных источниках — тоже производная."""
    lines = [
        "# Противоречия и производные источники",
        "",
        "Файл сгенерирован `scripts/evidence.py` из `claims.yaml` — правьте реестр.",
        "",
        "Два вопроса, на которые отвечает вид: что уже опровергнуто (чтобы вывод",
        "не «починили» обратно) и что опирается на производные документы — такие",
        "источники не являются доказательством.",
        "",
        "## Опровергнутые утверждения (`status: contradicted`)",
        "",
    ]
    contradicted = [c for c in claims if c.get("status") == "contradicted"]
    if not contradicted:
        lines.append("Опровергнутых записей нет.")
    for claim in contradicted:
        refuted = claim.get("contradicted_by") or {}
        lines += [
            f"### `{claim.get('id')}`",
            "",
            f"{claim.get('statement')}",
            "",
            f"Опровергнуто: `{refuted.get('type')}` — {refuted.get('ref')}",
            "",
            f"Воспроизведение: {claim.get('reproduction')}",
            "",
        ]
    lines += [
        "## Записи на производных источниках (`source.type: derived-doc`)",
        "",
        "Это не доказательства: производный документ может лишь хранить",
        "утверждение-гипотезу, опровергнутую версию или открытый вопрос.",
        "",
    ]
    derived = [c for c in claims
               if (c.get("source") or {}).get("type") == "derived-doc"]
    if not derived:
        lines.append("Записей на производных источниках нет.")
    for claim in derived:
        source = claim.get("source") or {}
        lines.append(
            f"- `{claim.get('id')}` ({claim.get('status')}): "
            f"{source.get('ref')}")
    return "\n".join(lines) + "\n"


def main() -> int:
    """0 — реестр цел и производные обновлены; 1 — нарушения (печатает их)."""
    claims = load_claims()
    problems = validate(claims)
    if problems:
        print("\n".join(problems))
        print(f"\nНарушений: {len(problems)}. Правьте docs/evidence/claims.yaml.")
        return 1
    MATRIX.write_text(render_matrix(claims), encoding="utf-8")
    CONTRADICTIONS.write_text(render_contradictions(claims), encoding="utf-8")
    print(f"Реестр цел: фактов {len(claims)}; матрица и противоречия обновлены.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
