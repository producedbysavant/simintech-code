# Доработки экосистемы SimInTech по внешнему аудиту

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** закрыть дефекты целостности (мёртвый пин зависимости роняет CI
`simintech-mcp`), добавить публичную политику безопасности и данных, превратить
разрозненные доказательства в структурированный evidence-слой и привязать
знаниевые снапшоты к версии SimInTech.

**Architecture:** три репозитория (`simintech-code` — библиотека и знания,
`simintech-mcp` — MCP-слой, `simintech-skill` — доменные знания агента) остаются
раздельными; доработки — это (а) гейты в CI, (б) документы политики, (в) новый
`docs/evidence/` со схемой «claim → источник → версия → замер → тест → статус»,
который валидируется тестами и генерирует матрицу проверки.

**Tech Stack:** Python 3.11, pytest, flake8, mypy, GitHub Actions, gitleaks,
`tomllib`, PyYAML (новая зависимость для evidence-слоя), hatchling.

---

## 0. Что подтвердилось и что устарело (проверено 2026-09-26)

| Утверждение аудита | Проверка | Итог |
|---|---|---|
| CI `simintech-mcp` красный | `gh run list` → run `36221460449`, `failure` | ✅ подтверждено |
| Причина — мёртвый SHA `13415c5e…` | лог: `fatal: remote error: upload-pack: not our ref 13415c5e…` на шаге установки | ✅ подтверждено |
| SHA не существует в origin | `gh api …/commits/13415c5e…` → 422 «No commit found» | ✅ подтверждено |
| CI `simintech-code` и `simintech-skill` зелёные | `gh run list` → оба `success` | ✅ подтверждено |
| Комментарий про `.gitleaks-corporate.toml` | есть в `.gitleaks.toml` всех трёх репозиториев | ✅ подтверждено, **снимается с работы** (см. ниже) |
| Нет `SECURITY.md` / `DATA_POLICY.md` / `AGENTS.md` | `ls` в трёх репозиториях | ✅ подтверждено |
| В `code` нет `docs/evidence/` | `ls docs` | ✅ подтверждено |
| Файлов `.prt/.xprt/.db/.sdb/.tbl/.pak` в git нет | `git ls-files` в `code` и `mcp` → 0 | ✅ политика пока держится на дисциплине, а не на гейте |
| `language_functions.json` уже знает `help_version` | `resources.py`, аудит | ✅ подтверждено |
| «4 скилла, 958 классов, cross-check в CI `simintech-skill`» | `ls skills-catalog`, CI skill | ✅ подтверждено |

**Снято с работы по указанию владельца:** пункт аудита про отсутствующий
`.gitleaks-corporate.toml`. Файл не нужен, внутренние правила в публичном дереве
не живут; устаревший комментарий о нём **удаляется** (задача P0-4).

**Состояние на 2026-09-26 (сверено с origin):**

| Репозиторий | Версия | `origin/main` | CI | Пины |
|---|---|---|---|---|
| `simintech-code` | 0.7.0 | `db0fc05a27ec7d1e14eb1da0858e6d1cd9c8e42a` | ✅ | — |
| `simintech-mcp` | 0.2.0 | `8916e99c738d72ac2a5f2abf185275bfc309f4a5` | ❌ | `simintech-api` → **мёртвый** `13415c5e…` |
| `simintech-skill` | 0.2.0 | `a3f062ff3e2a3dd30377228694dabc7204f4026f` | ✅ | — |

> **Примечание (добавлено после волны P1).** SHA в таблице — состояние на
> момент разбора. Позже, в тот же день, историю всех трёх репозиториев
> переписали (следы рабочего окружения), поэтому эти SHA снова мертвы, а пин
> `simintech-mcp` переведён на `0db494d6358a868b2f1afdae779a97e4d7d58eb5`.
> Таблица не переписывается: она фиксирует, что было **до** перезаписи, и
> именно по ней разбирался дефект CI.

Локальные чекауты `code` и `skill` совпадали с origin (история обоих —
один коммит `Initial commit`, то есть SHA, упомянутые в старых документах и
комментариях, мертвы как класс, а не единично).

---

## 1. Волна P0 — целостность зависимостей (сначала `simintech-mcp`)

Порядок обязателен: P0-1 закрывает красный CI, P0-2 делает рецидив
невозможным, P0-3 ловит второй класс той же ошибки («пин жив, но в нём нет
нужного API»).

### Task P0-1: заменить мёртвый пин на существующий коммит

**Files:**
- Modify: `simintech-mcp/pyproject.toml` (комментарий `16-34` и сама строка `35`)

**Контекст.** Комментарий объясняет «пин на коммит, а не на тег» и ссылается на
историю, которой больше нет: PR #11, merge `13415c5e`, тег `v0.3.0`,
`__version__ 0.1.0`. Причина пина остаётся верной, иллюстрация — нет; её надо
переписать на актуальную (текущая библиотека — 0.7.0, история репозитория
пересоздана, поэтому старые SHA недостижимы).

- [x] **Шаг 1: Убедиться, что целевой SHA существует в origin**

```bash
git ls-remote https://github.com/producedbysavant/simintech-code refs/heads/main
# Ожидаем: db0fc05a27ec7d1e14eb1da0858e6d1cd9c8e42a  refs/heads/main
```

- [x] **Шаг 2: Заменить строку зависимости**

```toml
    "simintech-api @ git+https://github.com/producedbysavant/simintech-code@db0fc05a27ec7d1e14eb1da0858e6d1cd9c8e42a",
```

- [x] **Шаг 3: Переписать комментарий над зависимостью**

Содержание (сохраняет прежний довод, убирает мёртвые ссылки):

```toml
    # Библиотека-ядро. Для локальной разработки заменить на path-зависимость:
    # simintech-api = { path = "../simintech-code", editable = true }
    #
    # Пин на КОММИТ, а не на тег: `refs/tags` можно передвинуть, и та же строка
    # зависимости начнёт разрешаться в другой код, причём молча.
    # db0fc05a — `main` репозитория simintech-code, версия библиотеки 0.7.0
    # (`simintech_api/__init__.py`). SHA переписать нельзя, поэтому закрепляет
    # именно он. Историю simintech-code пересоздавали, и прежде закреплённый
    # 13415c5e… в origin больше не существует — установка падала с
    # `upload-pack: not our ref`. От рецидива защищает `scripts/check_pins.py`
    # (P0-2): он падает до установки и называет мёртвый SHA.
    #
    # Перед сменой пина проверять, что новый коммит несёт нужное API:
    # `simintech_api/__init__.py` даёт ожидаемую `__version__`, а импорт сервера
    # и `tests/unit/test_dependency_contract.py` — что нужные символы на месте.
```

- [x] **Шаг 4: Проверить установку в чистом окружении**

```bash
cd /mnt/c/git/simintech-mcp
python3.11 -m venv /tmp/mcp-check && /tmp/mcp-check/bin/pip install -q -e ".[test]"
/tmp/mcp-check/bin/python -c "import simintech_api, simintech_mcp; print(simintech_api.__version__)"
# Ожидаем: 0.7.0
```

- [x] **Шаг 5: Прогнать гейты**

```bash
python3.11 -m pytest tests/unit -q          # ожидаем: 185 passed
flake8 simintech_mcp tests --max-line-length=88 --extend-ignore=E203,W503
mypy
```

- [x] **Шаг 6: Коммит**

```bash
git add pyproject.toml
git commit -m "fix: закрепить simintech-api на существующий коммит (мёртвый SHA ронял CI)"
```

### Task P0-2: гейт «пин существует» до установки

**Files:**
- Create: `simintech-mcp/scripts/check_pins.py`
- Create: `simintech-mcp/tests/unit/test_check_pins.py`
- Modify: `simintech-mcp/.github/workflows/ci.yml` (шаг перед «Установка»)

- [x] **Шаг 1: Написать падающий тест**

```python
"""Гейт пинов: git-зависимости должны разрешаться в origin."""

from __future__ import annotations

import subprocess

import pytest

from check_pins import CheckPinsError, git_pins, main, pin_reachable


def test_git_pins_parses_pinned_dependency(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "x"\ndependencies = [\n'
        '  "mcp>=1.0.0",\n'
        '  "simintech-api @ git+https://github.com/o/r@' + "a" * 40 + '",\n'
        "]\n",
        encoding="utf-8",
    )
    pins = git_pins(pyproject)
    assert pins == [("simintech-api", "https://github.com/o/r", "a" * 40)]


def test_git_pins_rejects_short_sha(tmp_path):
    """Не-40-символьный ревизионный идентификатор — не immutable-пин."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "x"\ndependencies = ["p @ git+https://github.com/o/r@v1.0"]\n',
        encoding="utf-8",
    )
    with pytest.raises(CheckPinsError, match="не коммит"):
        git_pins(pyproject)


def test_pin_reachable_reports_dead_sha():
    def run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd, 1, "", "fatal: remote error: upload-pack: not our ref " + "b" * 40)

    assert pin_reachable("https://github.com/o/r", "b" * 40, run=run) is False


def test_main_fails_on_dead_pin(tmp_path, capsys):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "x"\ndependencies = ["p @ git+https://github.com/o/r@'
        + "c" * 40 + '"]\n',
        encoding="utf-8",
    )

    def run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, "", "not our ref")

    assert main(pyproject, run=run) == 1
    assert "c" * 40 in capsys.readouterr().out
```

- [x] **Шаг 2: Убедиться, что тест падает**

Run: `cd simintech-mcp && python3.11 -m pytest tests/unit/test_check_pins.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'check_pins'`

- [x] **Шаг 3: Реализовать скрипт**

```python
"""Проверить, что git-пины из pyproject.toml существуют в origin.

Зачем: закрепление зависимости по SHA защищает от подмены тега, но не от
исчезновения самого коммита. История `simintech-code` уже пересоздавалась, и
`simintech-mcp` уехал в `main` с мёртвым пином: CI падал не на тестах, а на
`pip install`, сообщением `upload-pack: not our ref`. Здесь это ловится ДО
установки и называется человеческим текстом.

Проверка — тем же действием, что делает pip (`git fetch --depth=1 <url> <sha>`),
поэтому результат совпадает с тем, что увидит установка.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Callable, List, Tuple

PIN_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9._-]+)\s*@\s*git\+(?P<url>https://[^@\s]+)@(?P<rev>\S+)$"
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")

Run = Callable[..., "subprocess.CompletedProcess[str]"]


class CheckPinsError(Exception):
    """Пин разобран, но не является immutable-коммитом."""


def git_pins(pyproject: Path) -> List[Tuple[str, str, str]]:
    """Пины вида ``name @ git+https://…@<sha>`` из `project.dependencies`."""
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    pins = []
    for spec in data.get("project", {}).get("dependencies", []):
        match = PIN_RE.match(spec.strip())
        if not match:
            continue
        rev = match["rev"]
        if not SHA_RE.match(rev):
            raise CheckPinsError(
                f"{match['name']}: ревизия «{rev}» — не коммит. "
                f"Закрепляйте 40-символьный SHA: тег или ветку можно передвинуть."
            )
        pins.append((match["name"], match["url"], rev))
    return pins


def pin_reachable(url: str, sha: str, *, run: Run = subprocess.run) -> bool:
    """Отдаёт ли сервер объект по этому SHA (то же, что делает pip)."""
    with tempfile.TemporaryDirectory() as tmp:
        result = run(
            ["git", "fetch", "--depth=1", "--quiet", url, sha],
            cwd=tmp, capture_output=True, text=True,
        )
    return result.returncode == 0


def main(pyproject: Path, *, run: Run = subprocess.run) -> int:
    """0 — все пины достижимы; 1 — есть мёртвый (печатает, какой)."""
    try:
        pins = git_pins(pyproject)
    except CheckPinsError as exc:
        print(f"Пин невалиден: {exc}")
        return 1
    if not pins:
        print("Git-пинов нет — проверять нечего.")
        return 0
    failed = False
    for name, url, sha in pins:
        if pin_reachable(url, sha, run=run):
            print(f"OK   {name} @ {sha[:12]} ({url})")
        else:
            failed = True
            print(
                f"МЁРТВЫЙ ПИН: {name} @ {sha} не найден в {url}. "
                f"Обновите pin в pyproject.toml на существующий коммит."
            )
    return 1 if failed else 0


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    sys.exit(main(root / "pyproject.toml"))
```

- [x] **Шаг 4: Тест зелёный**

Run: `python3.11 -m pytest tests/unit/test_check_pins.py -q`
Expected: `4 passed`
(Тест импортирует `check_pins` — добавить `scripts/` в `tests/unit/conftest.py`
через `sys.path.insert`, как уже сделано для корня.)

- [x] **Шаг 5: Прогнать скрипт на реальном пине**

```bash
python3.11 scripts/check_pins.py
# Ожидаем: OK   simintech-api @ db0fc05a27ec (https://github.com/producedbysavant/simintech-code)
```

- [x] **Шаг 6: Встроить в CI перед установкой**

```yaml
      - name: Пины зависимостей
        # До установки: иначе мёртвый SHA падает невнятным
        # `upload-pack: not our ref` уже внутри pip.
        run: python scripts/check_pins.py
```

- [x] **Шаг 7: Проверить, что гейт краснеет на подмене (мутация)**

```bash
sed -i 's/@db0fc05a27ec7d1e14eb1da0858e6d1cd9c8e42a/@13415c5e4927a05e17f6d8e3e096cb0b9c23f65b/' pyproject.toml
python3.11 scripts/check_pins.py; echo "exit=$?"   # ожидаем exit=1 и «МЁРТВЫЙ ПИН»
git checkout pyproject.toml
```

- [x] **Шаг 8: Коммит**

```bash
git add scripts/check_pins.py tests/unit/test_check_pins.py tests/unit/conftest.py .github/workflows/ci.yml
git commit -m "ci: гейт существования git-пинов (ловит мёртвый SHA до установки)"
```

### Task P0-3: контракт зависимости — символы API на месте

**Files:**
- Create: `simintech-mcp/tests/unit/test_dependency_contract.py`

- [x] **Шаг 1: Написать тест**

```python
"""Контракт simintech-api: символы, на которые опирается сервер, существуют.

Второй класс той же ошибки, что и мёртвый пин: коммит существует, но API в нём
нет. Импорт на уровне модулей ловит только часть (`language`, `catalog`), а
ленивые импорты внутри инструментов (`dbconf`, `sdb`, `layout`,
`utils.xprt_signals`) — нет, и падение случилось бы в рантайме, у клиента.
"""

from __future__ import annotations

import importlib
import re

import pytest

#: (модуль, атрибут) — по факту использования в simintech_mcp.
REQUIRED = [
    ("simintech_api", "COMClient"),
    ("simintech_api", "Project"),
    ("simintech_api", "Wire"),
    ("simintech_api", "ComCallError"),
    ("simintech_api", "ComConnectionError"),
    ("simintech_api", "language"),
    ("simintech_api.catalog", "load_default_catalog"),
    ("simintech_api.catalog", "decode_xprt"),
    ("simintech_api.catalog", "parse_xprt_block_props"),
    ("simintech_api.catalog", "parse_xprt_readonly"),
    ("simintech_api.constants", "SUPPORTED_COM_BLOCK_CLASSES"),
    ("simintech_api.constants", "default_output_dir"),
    ("simintech_api.constants", "standard_block_size"),
    ("simintech_api.constants", "DataType"),
    ("simintech_api.dbconf", "load_db_config"),
    ("simintech_api.sdb", "SignalDatabase"),
    ("simintech_api.layout", "LayeredPlacer"),
    ("simintech_api.exceptions", "SimInTechError"),
    ("simintech_api.utils.xprt_signals", "XprtSignalReader"),
    ("simintech_api.utils.converters", "value_to_prop_string"),
]

#: Методы, вызываемые сервером у Project/COMClient.
PROJECT_METHODS = [
    "from_template", "open", "close", "get_main_page", "repaint",
    "set_calc_end_time", "set_calc_setting", "calc_settings", "simulation",
    "list_signals", "signal", "export_db_to_xml", "show_form",
    "save_xml", "save_binary",
]


@pytest.mark.parametrize("module_name,attr", REQUIRED)
def test_required_symbol_exists(module_name, attr):
    module = importlib.import_module(module_name)
    assert hasattr(module, attr), f"{module_name}.{attr} отсутствует"


@pytest.mark.parametrize("method", PROJECT_METHODS)
def test_project_has_method(method):
    from simintech_api import Project

    assert callable(getattr(Project, method, None)), f"Project.{method} отсутствует"
```

- [x] **Шаг 2: Прогнать**

Run: `python3.11 -m pytest tests/unit/test_dependency_contract.py -q`
Expected: PASS (на установленной 0.7.0). На версии без `language` — FAIL,
и это ровно тот сигнал, который нужен.

- [x] **Шаг 3: Коммит**

```bash
git add tests/unit/test_dependency_contract.py
git commit -m "test: контрактные символы simintech-api, которые использует сервер"
```

### Task P0-4: удалить устаревший комментарий про `.gitleaks-corporate.toml`

**Files:**
- Modify: `simintech-mcp/.gitleaks.toml:5-6`
- Modify: `simintech-code/.gitleaks.toml:5-6`
- Modify: `simintech-skill/.gitleaks.toml:5-6`

- [x] **Шаг 1: Заменить формулировку (три репозитория, текст одинаковый)**

Было:

```
# текущем дереве. Правила — поставляемые gitleaks; своих здесь нет намеренно,
# идентификаторы организации живут в `.gitleaks-corporate.toml`, у которого
# свой проход.
```

Стало:

```
# текущем дереве. Правила — поставляемые gitleaks; своих здесь нет намеренно.
```

- [x] **Шаг 2: Прогнать gitleaks локально (там, где он есть)**

```bash
gitleaks git --log-opts="--all" --config .gitleaks.toml --no-banner . ; echo "exit=$?"
# Ожидаем exit=0
```

- [x] **Шаг 3: Коммиты (по одному в каждом репозитории)**

```bash
git add .gitleaks.toml && git commit -m "chore: убрать устаревший комментарий о corporate-конфиге"
```

**Критерий готовности волны P0:** CI `simintech-mcp` зелёный; `check_pins.py`
краснеет на подмене SHA; контрактный тест зелёный; упоминаний
`.gitleaks-corporate` нет ни в одном из трёх деревьев.

### Отклонения при исполнении (2026-09-26)

Записаны потому, что это результат, а не мелочь: первое изменило шаг плана,
второе — сам гейт.

1. **Шаг 4 задачи P0-1 (venv) заменён.** В этой WSL нет `python3.11-venv`
   (пакет не установлен, `ensurepip` недоступен без root), поэтому проверка
   выполнена тем же, что делает установка, но без изоляции окружения:
   `git fetch --depth=1 <url> <sha>` и
   `pip download --no-deps "<спецификация>"` → собралось
   `simintech-api-0.7.0.zip`. Оба шага подтверждают, что пин разрешается.
2. **Найден и исправлен дефект гейта P0-2, которого не видели тесты.**
   Первый прогон `check_pins.py` объявил мёртвым **живой** SHA: `git fetch`
   вне репозитория падает («not a git repository»), а временный каталог
   репозиторием не был. Подделка `run` этого не показывает — она подменяет
   действие целиком. Исправлено (`git init` перед `fetch`) и закрыто тестом
   `test_fetch_runs_in_initialized_repo`, который фиксирует подготовку
   репозитория. Живой прогон после правки: `OK simintech-api @ db0fc05a27ec`.
3. **Контрактный тест P0-3 уточнён по факту:** `simintech_api.language` — не
   атрибут пакета до импорта подмодуля, поэтому проверяются его функции
   (`language_functions`, `find_function`, `registry_meta`). Вакуумность
   проверена обратным прогоном: на установленной библиотеке 0.2.0 тест
   краснеет — 13 падений.
4. **Гейты волны (в worktree `simintech-mcp`):** 227 passed, flake8 — 0,
   mypy — чисто, `check_pins.py` — `OK`. Правки `.gitleaks.toml` в `code` и
   `skill` сведены в их `main`; временные worktree удалены.
5. **Что критерий ещё не подтверждает:** зелёный CI. Он проверяется только
   пушем — ветку (`worktree-p0-dependency-integrity`, 4 коммита) пушит
   владелец, после чего смотрим прогон. До этого «CI зелёный» — ожидание,
   а не факт.

---

## 2. Волна P1 — публичная политика и DLP-гейт

### Task P1-1: `SECURITY.md` (все три репозитория)

**Files:** Create: `SECURITY.md` в `simintech-code`, `simintech-mcp`, `simintech-skill`

- [x] **Шаг 1: Написать документ** (текст общий, как у `CONTRIBUTING.md`)

Обязательные разделы и содержание:

1. **Как сообщить об уязвимости** — приватный канал: GitHub Security Advisory
   (`Security` → `Report a vulnerability`) в соответствующем репозитории. Публичный
   issue с деталями не создавать до исправления.
2. **Что считать уязвимостью** — выход за песочницу чтения файлов
   (`SIMINTECH_OUTPUT_DIR`), выполнение кода через аргументы инструментов,
   подмена зависимости, утечка секретов в историю.
3. **Случайно закоммиченный секрет** — секрет считается скомпрометированным:
   сначала **отозвать** (ротация), потом удалять из истории; ссылаться на
   `gitleaks` и запрет force-push в `main`.
4. **Данные, которых не должно быть в публичном дереве** — ссылка на
   `DATA_POLICY.md` (P1-2); реальные проекты `.prt/.xprt`, базы `.db/.sdb`,
   лицензии, внутренние пути и имена заказчиков.
5. **Фикстуры** — допустимы синтетические и публично поставляемые вендором;
   происхождение указывается в `tests/fixtures/README.md`.
6. **Disclosure** — срок ответа и политика публикации после исправления
   (предложить: подтверждение в течение 7 дней, раскрытие после выпуска фикса).
7. **Область** — явно: SimInTech — сторонний продукт; уязвимости самой среды
   сообщаются вендору, а не в эти репозитории.

- [x] **Шаг 2: Коммит в каждом репозитории**

```bash
git add SECURITY.md && git commit -m "docs: политика безопасности и раскрытия уязвимостей"
```

### Task P1-2: `DATA_POLICY.md` — граница public/private

**Files:** Create: `DATA_POLICY.md` в `simintech-code` (там же — `tests/fixtures/README.md`)

- [x] **Шаг 1: Написать политику**

Разделы:

1. **Назначение** — репозитории публичные; всё, что попадает в коммит и в
   историю, считается опубликованным навсегда.
2. **Категории** (используются DLP-гейтом P1-3):
   `PUBLIC` (публичные факты вендора), `PUBLIC-DERIVED` (наши замеры и выводы),
   `SYNTHETIC` (сгенерированные фикстуры), `INTERNAL` (не публикуется),
   `SECRET` (ключи, токены, пароли).
3. **Разрешено публиковать:** `simintech.ru`, `help.simintech.ru`,
   `C:\SimInTech64`, `mmain.exe`, номера версий, имена классов блоков, номера
   публичных PR/issues этого проекта.
4. **Запрещено:** реальные модели заказчиков (`*.prt`, `*.xprt`), базы
   сигналов (`*.db`, `*.sdb`), файлы поставки, лицензионные ключи и сертификаты,
   внутренние имена хостов и UNC-пути, домашние каталоги с реальным именем
   пользователя, адреса и телефоны, номера договоров, внутренние тикеты.
5. **Фикстуры:** `tests/fixtures/synthetic/` и `tests/fixtures/vendor-public/`;
   в `README.md` каждой — происхождение и дата; файлы поставки — только те,
   что вендор публикует сам (справка), и только в виде, не воспроизводящем
   содержимое чужих проектов.
6. **Проверка:** перечислить гейты (gitleaks по истории, `public_data_check.py`,
   запрет расширений).

- [x] **Шаг 2: Коммит**

```bash
git add DATA_POLICY.md tests/fixtures/README.md
git commit -m "docs: политика данных — что публикуется, что не должно попадать в git"
```

### Task P1-3: DLP-гейт `public-data`

**Files:**
- Create: `simintech-code/scripts/public_data_check.py`
- Create: `simintech-code/tests/unit/test_public_data_check.py`
- Create: `simintech-code/.publicdata-allowlist` (пути-исключения и разрешённые образцы)
- Modify: `simintech-code/.github/workflows/ci.yml`
- (после проверки механики — перенести скрипт в `simintech-mcp` и `simintech-skill`
  как есть)

- [x] **Шаг 1: Написать падающий тест**

```python
"""Правила DLP-гейта: ловим приватное, не трогаем публичное."""

from __future__ import annotations

from public_data_check import Findings, scan_text, scan_tree


def test_private_ip_is_flagged():
    findings = scan_text("адрес стенда 192.168.10.7", path="docs/x.md")
    assert findings


def test_public_vendor_path_is_allowed():
    assert not scan_text(r"поставка лежит в C:\SimInTech64\bin", path="README.md")


def test_real_user_profile_is_flagged():
    findings = scan_text(r"C:\Users\ivanov\AppData\Local", path="x.md")
    assert findings


def test_placeholder_profile_is_allowed():
    assert not scan_text(r"C:\Users\<user>\AppData", path="x.md")
    assert not scan_text(r"C:\Users\Public\Documents", path="x.md")


def test_unc_path_is_flagged():
    assert scan_text(r"\\srv-files\share\project", path="x.md")


def test_vendor_help_domain_is_allowed():
    assert not scan_text("см. https://help.simintech.ru/", path="README.md")


def test_email_domain_allowlist():
    assert scan_text("пишите на ivan.petrov@corp-holding.ru", path="x.md")
    assert not scan_text("noreply@example.com", path="x.md")


def test_findings_report_lines():
    findings = Findings()
    findings.add("x.md", 3, "private-ip", "192.168.10.7")
    assert "x.md:3" in str(findings)


def test_format_discussion_is_not_a_dump():
    """Разговор о формате — не дамп: правило ловит путь к файлу, а не слово."""
    assert not scan_text("сохранённый проект (.xprt) разбирается без COM", path="README.md")


def test_project_path_is_flagged():
    assert scan_text(r"модель лежит в D:\стенд\заказчик.prt", path="x.md")


def test_forbidden_file_in_tree(tmp_path):
    (tmp_path / "model.prt").write_text("не модель, но расширение чужое", encoding="utf-8")
    assert scan_tree(tmp_path)


def test_vendor_fixture_directory_is_allowed(tmp_path):
    fixture = tmp_path / "tests" / "fixtures" / "vendor-public" / "sample.tbl"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("1 2 3", encoding="utf-8")
    assert not scan_tree(tmp_path)
```

- [x] **Шаг 2: Тест падает**

Run: `python3.11 -m pytest tests/unit/test_public_data_check.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'public_data_check'`

- [x] **Шаг 3: Реализовать сканер**

Ключевое: правила **узкие** и с allowlist — гейт, который краснеет на
документации о самом себе, будет отключён через неделю.

```python
"""DLP-гейт: приватные данные в публичном дереве.

Проверяются не секреты (это делает gitleaks), а потенциально приватные
идентификаторы: адреса, телефоны, внутренние имена и пути, чужие проектные
файлы. Правила намеренно узкие, а исключения — рядом с правилами: гейт, который
краснеет на собственной документации, будет отключён.

Категории — в DATA_POLICY.md. Публичные факты вендора (simintech.ru,
help.simintech.ru, C:\\SimInTech64) разрешены явно, а не «по недосмотру».
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Pattern, Tuple

#: Разрешённые образцы: проверяются ДО остальных правил и гасят находку.
ALLOWED: Tuple[Pattern[str], ...] = (
    re.compile(r"help\.simintech\.ru"),
    re.compile(r"simintech\.ru"),
    re.compile(r"C:\\SimInTech64"),
    re.compile(r"example\.(com|org)"),
    re.compile(r"noreply@"),
    re.compile(r"C:\\Users\\(<[^>]+>|Public|Default|user|username|%USERNAME%)"),
)

RULES: Tuple[Tuple[str, Pattern[str]], ...] = (
    ("private-ip", re.compile(r"\b(10\.\d{1,3}|172\.(1[6-9]|2\d|3[01])|192\.168)\.\d{1,3}\.\d{1,3}\b")),
    ("unc-path", re.compile(r"\\\\[A-Za-z0-9._-]+\\[A-Za-z0-9._$-]+")),
    ("user-profile", re.compile(r"[A-Za-z]:\\Users\\[^\\<>%\s]+")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("phone-ru", re.compile(r"\+7[\s(-]?\d{3}[\s)-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}\b")),
    ("internal-host", re.compile(r"\b[a-z0-9-]+\.(local|corp|internal|lan)\b", re.I)),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    # Путь к конкретному файлу, а не разговор о формате: «сохранённый проект
    # (.xprt)» в README — это документация, а `D:\стенд\заказчик.prt` — дамп.
    ("project-dump", re.compile(
        r"([A-Za-z]:\\|\\\\)[^\s`»«]*\.(prt|xprt|sdb|db|saraface)\b", re.I)),
)

#: Расширения файлов, которых в публичном дереве быть не должно.
FORBIDDEN_SUFFIXES = {".prt", ".xprt", ".sdb", ".db", ".saraface", ".pak", ".tbl"}

#: Каталог легитимных вендорских фикстур — исключение по пути, а не по гейту.
FIXTURE_DIR = "tests/fixtures/vendor-public/"


@dataclass
class Findings:
    """Находки: путь, строка, правило, фрагмент."""

    items: List[Tuple[str, int, str, str]] = field(default_factory=list)

    def add(self, path: str, line: int, rule: str, fragment: str) -> None:
        self.items.append((path, line, rule, fragment.strip()[:80]))

    def __bool__(self) -> bool:
        return bool(self.items)

    def __str__(self) -> str:
        return "\n".join(
            f"{path}:{line}: [{rule}] {fragment}" for path, line, rule, fragment in self.items
        )


def scan_text(text: str, *, path: str = "<text>") -> Findings:
    """Найти приватные маркеры в тексте (allowlist гасит находку)."""
    findings = Findings()
    for number, line in enumerate(text.splitlines(), start=1):
        if any(pattern.search(line) for pattern in ALLOWED):
            continue
        for rule, pattern in RULES:
            match = pattern.search(line)
            if match:
                findings.add(path, number, rule, match.group(0))
    return findings
```

- [x] **Шаг 4: Тест зелёный**

Run: `python3.11 -m pytest tests/unit/test_public_data_check.py -q`
Expected: `12 passed`

- [x] **Шаг 5: Добавить обход дерева и CLI**

```python
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", "build", "dist"}
SKIP_SUFFIXES = {".pyc", ".png", ".jpg", ".gif", ".pdf", ".zip"}


def scan_tree(root: Path) -> Findings:
    """Пройти дерево: расширения файлов, затем содержимое."""
    findings = Findings()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if SKIP_DIRS & set(path.parts) or path.suffix in SKIP_SUFFIXES:
            continue
        relative = str(path.relative_to(root))
        if path.suffix.lower() in FORBIDDEN_SUFFIXES and not relative.startswith(FIXTURE_DIR):
            findings.add(relative, 0, "forbidden-file", path.name)
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        findings.items.extend(scan_text(text, path=relative).items)
    return findings


def main(root: Path) -> int:
    findings = scan_tree(root)
    if findings:
        print(findings)
        print(f"\nНаходок: {len(findings.items)}. См. DATA_POLICY.md.")
        return 1
    print("Приватных маркеров не найдено.")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(__file__).resolve().parents[1]))
```

- [x] **Шаг 6: Прогнать по дереву и разобрать находки**

```bash
python3.11 scripts/public_data_check.py; echo "exit=$?"
```

Каждую находку разобрать по одному из трёх оснований: правило слишком широкое
(сузить), образец публичный (в allowlist с комментарием «почему публично»),
файл действительно приватный (удалить из дерева и истории). **Ни одну находку
не гасить без основания** — в отчёте коммита перечислить разбор.

- [x] **Шаг 7: Добавить job в CI**

```yaml
  public-data:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Публичные данные
        run: python scripts/public_data_check.py
```

- [x] **Шаг 8: Проверить гейт мутацией**

```bash
printf 'стенд 10.20.30.40\n' >> docs/guide.md
python3.11 scripts/public_data_check.py; echo "exit=$?"   # ожидаем exit=1 и находку
git checkout docs/guide.md
```

- [x] **Шаг 9: Перенести скрипт в `simintech-mcp` и `simintech-skill`**

Тот же файл + свой `SKIP_FILES` (если нужно) + job в CI. Тесты переносятся
вместе со скриптом.

- [x] **Шаг 10: Коммиты**

```bash
git add scripts/public_data_check.py tests/unit/test_public_data_check.py .github/workflows/ci.yml
git commit -m "ci: DLP-гейт публичных данных (адреса, внутренние пути, чужие проекты)"
```

### Task P1-4: запрет проектных и бинарных файлов

Отдельного механизма не заводить: проверка уже встроена в `scan_tree`
(P1-3, шаг 3) — файл с расширением из `FORBIDDEN_SUFFIXES` становится находкой
`forbidden-file` до чтения содержимого. Здесь остаётся закрепить это в
pre-commit и убедиться, что легитимный случай не требует отключения гейта.

**Files:** Modify: `.pre-commit-config.yaml` в трёх репозиториях; `tests/fixtures/README.md`

- [x] **Шаг 1: Добавить pre-commit-хук в трёх репозиториях**

```yaml
  - repo: local
    hooks:
      - id: public-data
        name: Публичные данные (DATA_POLICY.md)
        entry: python3 scripts/public_data_check.py
        language: system
        pass_filenames: false
```

- [x] **Шаг 2: Проверить, что запрет файлов работает и не мешает фикстурам**

```bash
printf 'x' > /tmp/проверка.prt && cp /tmp/проверка.prt ./проверка.prt
python3.11 scripts/public_data_check.py; echo "exit=$?"   # ожидаем exit=1, forbidden-file
rm ./проверка.prt
mkdir -p tests/fixtures/vendor-public && printf '1 2\n' > tests/fixtures/vendor-public/пример.tbl
python3.11 scripts/public_data_check.py; echo "exit=$?"   # ожидаем exit=0
```

- [x] **Шаг 3: `tests/fixtures/README.md`** — что здесь допустимо, откуда взят
каждый файл, дата и версия; для `vendor-public/` — ссылка на публичный источник.

### Task P1-5: разовый скан истории

- [x] **Шаг 1: Прогнать gitleaks по всей истории в трёх репозиториях**
(уже делает CI; здесь — зафиксировать результат на текущем `main`).

- [x] **Шаг 2: Прогнать DLP-сканер по истории** — `git log -p --all` в файл и
прогнать по нему `scan_text` построчно, чтобы не гонять `rglob` по временным
деревьям. Результат — отчёт в `docs/audit/2026-09-26-history-scan.md`:
что нашли, что признали ложным и почему. **Формулировка вывода — «найдено и
разобрано X», а не «приватных данных нет»**: скан не является доказательством
отсутствия.

### Отклонения при исполнении волны P1 (2026-09-26)

1. **Правило «путь к .prt/.xprt — это дамп» убрано из гейта.** План
   предусматривал его; замер на дереве `simintech-code` дал 43 находки из 62,
   и **все** — синтетические примеры в докстрингах и документации о форматах.
   Отличить пример от реального дампа по тексту нечем, а правило с таким шумом
   отключают. Реальные дампы ловит проверка **файлов** (`FORBIDDEN_SUFFIXES`),
   след чужого окружения — `user-profile`. Решение закреплено тестом
   `test_text_path_is_not_flagged`, чтобы его не «починили» обратно.
2. **Гейт смотрит только файлы под git** (`git ls-files`), а не всё дерево:
   иначе шум давали бы рабочие копии инструкций агента (`CLAUDE.md`,
   `.claude/`, `.remember/`), которые в публикацию не попадают. Проверено
   тестом `test_untracked_files_are_skipped`.
3. **Три дефекта гейта найдены автоматическим security-ревью коммита — и все
   три были настоящими:** allowlist гасил строку целиком (обход гейта: приватный
   адрес рядом с публичным доменом), зона матчилась по `startswith`
   (`tests-evil/` попадал под `tests/`), а `SKIP_DIRS` применялся к абсолютным
   путям (репозиторий внутри каталога `build` сканировался вхолостую и молча).
   Исправлено; на каждый дефект есть тест, включая мутацию «публичный домен +
   приватный адрес в одной строке».
4. **Разбор находок дал одну проверку, которую стоит помнить:** упоминание
   `KBA_CTL - генерация кода для АЭС/kba.pak` выглядело как имя заказчика, но
   это **имя каталога в публичной поставке вендора** (проверено `find` по
   `C:\SimInTech64\Demo\…`). Вывод делается после проверки источника, а не до.
5. **История уже опубликована.** Следы окружения (имя Windows-профиля и путь
   с именем рабочего проекта) есть в отправленных коммитах; их удаление требует
   force-push, который запрещён политикой и здесь не нужен (не секреты).
   Зафиксировано в отчёте скана как решение владельца. В самом плане и в отчёте
   они приводятся **обезличенно**: раз признали следом — нечего его
   тиражировать в новом документе.
6. **Гейты волны:** `simintech-code` — 618 passed, flake8 — 0, mypy — чисто,
   DLP — 0 находок на 169 файлах; `simintech-mcp` — 246 passed, DLP — 0 на 57;
   `simintech-skill` — 103 passed, DLP — 0 на 27. Правила описаны в
   `DATA_POLICY.md`, зоны синтетики — в самом скрипте рядом с правилами.

---

## 3. Волна P2 — доказательный слой и снапшоты знаний

### Task P2-1: `docs/evidence/` — claim → источник → тест → статус

**Files:**
- Create: `simintech-code/docs/evidence/claims.yaml`
- Create: `simintech-code/docs/evidence/sources.md`
- Create: `simintech-code/docs/evidence/verification-matrix.md` (генерируется)
- Create: `simintech-code/scripts/evidence.py`
- Create: `simintech-code/tests/unit/test_evidence.py`
- Modify: `simintech-code/pyproject.toml` (зависимость `PyYAML`)

- [x] **Шаг 1: Схема.** Каждое утверждение — запись:

```yaml
- id: setblockprop-ignores-unknown-name
  claim: "SetBlockProp с неизвестным именем не отвергается и не меняет значение"
  source:
    type: live-com            # official-doc | live-com | xprt-observation |
                              # source-code | controlled-experiment | inference | unknown
    ref: "docs/roadmap-agentic-ecosystem.md §3.1"
    product_version: "SimInTech64 (поставка 2.26.6.23)"
    observed_at: 2026-09-10
  evidence:
    negative: "Константа.y0 = 5 не меняет ничего и отказа не даёт"
  test:
    file: tests/unit/test_blocks_tools.py
    id: test_set_block_param_rejects_unknown
  status: verified            # verified | refuted | unknown | version-specific
```

- [x] **Шаг 2: Наполнить начальным набором** — не «все утверждения проекта», а
те, на которых стоит поведение инструментов (12–15 записей):

| id | утверждение |
|---|---|
| `blocks-not-renamed` | `SetBlockProp("Name")` не переименовывает блок |
| `setblockprop-ignores-unknown-name` | неизвестное имя принимается молча |
| `constant-param-is-a` | у «Константы» параметр `a`, `y0` не существует |
| `summator-ports-via-setportcount` | длина `a` не добавляет входы; нужен `SetPortCount` |
| `new-project-does-not-calc` | проект из `NewProject` не считает (нет расчётного слоя) |
| `template-project-calcs` | проект из шаблона считает |
| `floating-input-stops-run` | неподключённый вход молча останавливает расчёт |
| `runto-is-not-blocking` | `RunTo` не блокирующий |
| `signals-need-database` | `get_signal` работает только с подключённой базой сигналов |
| `wires-have-no-ends-via-com` | концы линий через COM не читаются |
| `findstartport-is-signal-resolver` | `findstartport` — не оракул электрической смежности |
| `conn-is-pairwise-per-wire` | `conn` описывает концы линии попарно |
| `fsm-full-name-only` | FSM-блоки создаются только по полному имени записи |
| `unsigned-block-size` | `standard_block_size` покрывает не все классы |

- [x] **Шаг 3: Валидатор + генератор** (`scripts/evidence.py`):

```python
"""Проверка реестра утверждений и сборка матрицы проверки.

Реестр нужен затем, чтобы агент (и человек) различал «официально
задокументировано», «измерено на версии X» и «предполагается». Без валидатора
он превратится в ещё один документ, который расходится с кодом.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CLAIMS = ROOT / "docs" / "evidence" / "claims.yaml"
MATRIX = ROOT / "docs" / "evidence" / "verification-matrix.md"

SOURCE_TYPES = {
    "official-doc", "live-com", "xprt-observation", "source-code",
    "controlled-experiment", "inference", "unknown",
}
STATUSES = {"verified", "refuted", "unknown", "version-specific"}


def load_claims(path: Path = CLAIMS) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def validate(claims: list[dict], root: Path = ROOT) -> list[str]:
    """Вернуть список нарушений: пустой — реестр цел."""
    problems: list[str] = []
    seen: set[str] = set()
    for claim in claims:
        cid = claim.get("id", "")
        if not re.match(r"^[a-z0-9][a-z0-9-]{2,63}$", cid):
            problems.append(f"{cid!r}: id должен быть kebab-case")
        if cid in seen:
            problems.append(f"{cid}: id повторяется")
        seen.add(cid)
        source = claim.get("source") or {}
        if source.get("type") not in SOURCE_TYPES:
            problems.append(f"{cid}: неизвестный тип источника {source.get('type')!r}")
        if claim.get("status") not in STATUSES:
            problems.append(f"{cid}: неизвестный статус {claim.get('status')!r}")
        if claim.get("status") == "verified":
            if not source.get("observed_at") or not source.get("product_version"):
                problems.append(
                    f"{cid}: verified без observed_at/product_version — "
                    f"«проверено» без версии и даты непроверяемо"
                )
        test = claim.get("test") or {}
        target = root / str(test.get("file", ""))
        if not target.is_file():
            problems.append(f"{cid}: файл теста {test.get('file')!r} не существует")
        elif test.get("id") and test["id"] not in target.read_text(encoding="utf-8"):
            problems.append(
                f"{cid}: тест {test.get('id')!r} не найден в {test.get('file')}"
            )
    return problems


def render_matrix(claims: list[dict]) -> str:
    lines = [
        "# Матрица проверки утверждений",
        "",
        "Файл сгенерирован `scripts/evidence.py` из `claims.yaml` — правьте реестр.",
        "",
        "| id | статус | источник | версия | дата | тест |",
        "|---|---|---|---|---|---|",
    ]
    for claim in claims:
        source = claim.get("source") or {}
        test = claim.get("test") or {}
        lines.append(
            f"| `{claim['id']}` | {claim['status']} | {source.get('type')} | "
            f"{source.get('product_version', '—')} | {source.get('observed_at', '—')} | "
            f"`{test.get('file', '—')}::{test.get('id', '—')}` |"
        )
    return "\n".join(lines) + "\n"
```

Тесты (`tests/unit/test_evidence.py`): реальный реестр проходит `validate`;
`render_matrix` совпадает с лежащим в дереве `verification-matrix.md` (иначе
«матрицу забыли перегенерировать»). Мутации, на которых гейт обязан краснеть:
удалённый файл теста, дубль `id`, `verified` без `product_version`.

- [x] **Шаг 4: `sources.md` — список источников** (справка поставки,
`docs/reference/com_api_inventory.md`, выгрузки `.xprt`, живой COM) с датой,
версией и тем, что из него взято; на него ссылаются записи `claims.yaml` через
`source.ref`. Начать с восьми источников, реально использованных в
`code` и `mcp`, а не с полного перечня справки.

- [x] **Шаг 4: Прогнать и убедиться, что реестр и матрица синхронны**

```bash
python3.11 scripts/evidence.py            # валидирует и перезаписывает матрицу
python3.11 -m pytest tests/unit/test_evidence.py -q
git diff --exit-code docs/evidence/verification-matrix.md   # ожидаем пусто
```

- [x] **Шаг 5: Коммит**

```bash
git add docs/evidence scripts/evidence.py tests/unit/test_evidence.py pyproject.toml
git commit -m "docs: реестр утверждений с источником, версией и тестом"
```

### Task P2-2: версионирование снапшотов знаний

**Files:**
- Modify: `simintech-code/simintech_api/data/block_catalog.json` (поле `meta.source`)
- Modify: `simintech-code/simintech_api/data/language_functions.json`
- Modify: генератор каталога (`simintech_api/catalog_tool.py`) и сборщик реестра языка
- Modify: `simintech-code/tests/unit/test_catalog_dumps.py`

- [x] **Шаг 1: Схема метаданных** (единая для обоих файлов):

```json
"meta": {
  "source": {
    "product": "SimInTech",
    "version": "<версия поставки, напр. 15.05.2026 или версия bin>",
    "profile": "<профиль/сборка, для каталога — bins/Base>",
    "observed_at": "<ISO-дата генерации>",
    "dump_sha256": "<sha256 исходной выгрузки .xprt>",
    "generator": "<имя entry point и его версия>"
  }
}
```

- [x] **Шаг 2: Заполнить тем, что известно, остальное — `unknown`**

Честность важнее красоты: `help_version` для реестра языка известен
(`v15.05.2026`), для каталога дата прогона восстанавливается по журналу
работы, `dump_sha256` — только если выгрузка сохранена; если нет — `"unknown"`
и запись в `docs/knowledge-snapshot.md` о том, что требуется перегенерация.

- [x] **Шаг 3: Тест схемы** — поля присутствуют, `observed_at` либо ISO-дата,
либо `"unknown"`; `version` непустой.

- [x] **Шаг 4: Прогнать и закоммитить**

```bash
python3.11 -m pytest tests/unit/test_catalog_dumps.py -q
git add simintech_api/data simintech_api/catalog_tool.py tests/unit/test_catalog_dumps.py
git commit -m "feat: версия и дата наблюдения в снапшотах каталога и реестра языка"
```

### Task P2-3: `docs/knowledge-snapshot.md` и `docs/compatibility-matrix.md`

**Files:** Create: `simintech-code/docs/knowledge-snapshot.md`, `simintech-code/docs/compatibility-matrix.md`

- [x] **Шаг 1: `knowledge-snapshot.md`** — что и на какой версии SimInTech
измерено/сгенерировано: каталог (958 классов), реестр языка (907 функций,
878 имён), карта COM API, разборы форматов. Для каждой строки — версия, дата,
файл-артефакт, гейт (тест), который это держит.

- [x] **Шаг 2: `compatibility-matrix.md`** — трёхсторонняя таблица:

| `simintech-code` | `simintech-mcp` (пин) | `simintech-skill` | Статус |
|---|---|---|---|
| 0.7.0 `db0fc05a` | 0.2.0 | 0.2.0 | ✅ проверено `pytest` + импорт |

и правила: поднимать пин только после того, как `code` выпустил коммит; в
`mcp` — прогнать `check_pins.py`, контрактный тест и unit-набор; в `skill` —
сверку пересказов (уже есть в CI).

- [x] **Шаг 3: Сослаться на матрицу из README каждого репозитория** одной
строкой, чтобы она не жила в вакууме.

### Отклонения при исполнении волны P2 (2026-09-26)

1. **Набор статусов расширен.** План знал четыре (`verified`, `refuted`,
   `unknown`, `version-specific`); добавлены `measured` и `unit-only`. Причина
   не в удобстве: без различения «подтверждено живым замером» и «покрыто
   тестом на подделке» реестр врал бы ровно там, где он нужнее всего. Статус
   `unit-only` прямо называет, что тест на фейке фиксирует контракт кода, но не
   поведение среды.
2. **У записи не один тест, а список** (`tests`), и у каждого теста указан вид:
   `live` (живой COM), `distribution` (сверка с поставкой), `unit` (подделка).
   Валидатор требует, чтобы `verified` опирался на `live`/`distribution`.
3. **Поле наблюдения названо `observation`, а не `source`**: `meta.source` в
   каталоге уже занят строкой (`"generated"`), и переименование сломало бы
   читателя ради красоты схемы.
4. **У текущих снапшотов `observed_at` и `dump_sha256` — `unknown`.** Дата
   прогона генератора не записана, выгрузка не сохранена; подставлять догадку
   хуже, чем признать пропуск. Генератор проставляет поля сам, и следующая
   пересборка это закроет (отмечено в `docs/knowledge-snapshot.md`).
5. **Сборщик реестра языка живёт вне репозитория** — его `observation`
   поддерживается вручную; это тоже записано в снапшот, чтобы не выглядело
   забывчивостью.
6. **Гейты:** `simintech-code` — 632 passed (было 618: +9 проверок реестра,
   +5 схемы снапшотов), flake8 — 0, mypy — чисто, DLP — 0 находок на 175
   файлах. Реестр цел (14 утверждений), матрица в синхроне — проверяется тестом.

---

## 4. Волна P3 — воспроизводимость и знания

### Task P3-1: Windows-раннер — **решено: не подключаем**

**Решение владельца (2026-09-26):** Windows-машина с SimInTech есть, но она
**внутренняя** и к публичному репозиторию не подключается. Значит:

- self-hosted runner не заводим, `nightly-windows.yml` не пишем — для CI живое
  поведение COM **остаётся недостижимым**, и это осознанное ограничение, а не
  недоделка;
- **тесты с COM проводятся только локально**: `pytest -m integration` (и
  `-m distribution`) запускает тот, у кого есть Windows-машина с
  зарегистрированным `mmain.exe /regserver`;
- **каждый разработчик сам убеждается в правильности своего окружения** — это
  его ответственность, а не проверка CI.

Что из этого следует для остального хозяйства (и уже учтено):

1. **Зелёный CI — не доказательство работоспособности со средой.** Он говорит
   только о разборе, контрактах и гейтах. Формулировать это в отчётах честно:
   «тесты прошли» ≠ «проверено на SimInTech».
2. **Живые тесты обязаны быть воспроизводимы одной командой** — иначе локальный
   контур превращается в «у меня работало». Команда — `pytest -m integration`
   (описана в `docs/architecture.md` и `pyproject.toml`), требования к
   окружению — Windows с зарегистрированным `mmain.exe /regserver`
   (`CONTRIBUTING.md`). В `docs/knowledge-snapshot.md` записано следствие: до
   прогона живые тесты — «написаны, но не исполнены».
3. **Результат локального прогона стоит фиксировать**: если он что-то
   подтвердил — запись в `docs/evidence/claims.yaml` (статус и дата), а не
   только словами в переписке. Иначе знание умирает вместе с прогоном.
4. Если решение когда-нибудь изменится (появится отдельная внешняя машина или
   изолированный runner), задача возвращается — но уже с готовым набором живых
   тестов и реестром утверждений, которые надо исполнять.

### Task P3-2: расширение skills — только evidence-first

Кандидаты аудита (`project-lifecycle`, `signals-and-sdb`, `topology-analysis`,
`model-diagnostics`, `script-bridge`, `file-formats`, `automation`,
`code-generation`, `embedded-targets`, `verification`) берутся в работу по
одному и только при выполнении условия: **у темы есть записи в `claims.yaml`
со статусом `verified` и записи с `refuted`/`unknown`** — второе важнее, потому
что именно оно удерживает агента от выдумывания API.

Порядок: `signals-and-sdb` и `file-formats` (факты уже есть, покрытие высокое)
→ `project-lifecycle` → `model-diagnostics` → остальные по мере появления
измерений. `code-generation` и `embedded-targets` — **не начинать**: в аудите
зафиксировано, что кодогенерация не проверена даже один раз (нужна
лицензированная сборка), а знание без проверки — то, от чего этот проект
уходит.

### Task P3-3: вывод топологии в MCP — после контракта, а не до

Продолжение `simintech-code` M4 (`inspect_object` → `inspect_port` →
`query_connections`) и только затем M5 (MCP). При выводе учесть уже
зафиксированное: `read_topology` отказывает в небезопасном состоянии расчёта —
MCP обязан переводить `ScriptBridgeUnsafeStateError` в понятный агенту текст,
а не выглядеть поломкой.

### Task P3-4: формат research-треков

Дополнить шаблон спецификаций (`docs/superpowers/specs/`) обязательными
разделами: `hypotheses` → `live experiments` → `observations` →
`negative observations` → `confirmed | rejected | unknown | version-specific`.
Сегодня это уже фактически так (`2026-09-22-script-bridge-lifecycle-design.md`),
но не закреплено — а именно этот раздел аудит назвал главной сильной стороной.

---

## 5. Что из аудита не берём (и почему)

| Предложение | Почему нет |
|---|---|
| `.gitleaks-corporate.toml` и отдельный corporate-скан | Снято владельцем: устаревшая информация; комментарий удаляется (P0-4) |
| Реестр/публикация MCP-пакета, release-machinery, SHA256 бандла | Нет публикации в реестр и нет потребителя; появится — заведём отдельным планом |
| Мультиязычный README, `AGENTS.md`, `manifest.yaml` для MCP | Дублирование без пользы: агент читает `CLAUDE.md` и docstring'и, они и есть контракт |
| «Сделать репозитории похожими на MathWorks» | Ценность проекта — в доказательности конкретных утверждений, а не в объёме презентации |
| Полный переход на claims.yaml для всей документации | Дорого и не нужно: реестр покрывает только утверждения о поведении, на которых стоят инструменты |

---

## 6. Порядок, зависимости и критерии готовности

```
P0-4 ──┐
P0-1 ──┼─→ P0-2 ─→ P0-3            (mcp, последовательно: CI сначала зелёный)
P1-1 ──┼─→ P1-2 ─→ P1-3 ─→ P1-4 ─→ P1-5   (code → перенос в mcp/skill)
P2-1 ──┴─→ P2-2 ─→ P2-3            (code)
P3-*                               (после P0–P2; P3-1 решён: раннера нет — тесты с COM локально)
```

| Волна | Критерий готовности |
|---|---|
| P0 | CI `mcp` зелёный; `check_pins.py` краснеет на подмённом SHA; контрактный тест зелёный; `grep -r gitleaks-corporate` пуст в трёх деревьях |
| P1 | `SECURITY.md` + `DATA_POLICY.md` в трёх репозиториях; job `public-data` зелёный и краснеет на подставном `192.168.x.x`; отчёт по истории отработан |
| P2 | `claims.yaml` валидируется тестом; `verification-matrix.md` в синхроне (тест); у каталога и реестра языка есть `meta.source`; `compatibility-matrix.md` существует и совпадает с `pyproject.toml` (проверяется тестом) |
| P3 | P3-1 решён: Windows-раннера нет, живые тесты — локально (см. P3-1); P3-2…P3-4 берутся по evidence-first |

**Решения, нужные от владельца:**

1. ~~Windows-машина и лицензия для nightly (P3-1)~~ — **решено 2026-09-26:**
   машина внутренняя, к публичному репозиторию не подключается; живые тесты
   остаются локальными, окружение проверяет сам разработчик (см. P3-1).
2. ~~Канал приёма сообщений об уязвимостях (P1-1)~~ — **закрыто исполнением
   2026-09-26:** приватный GitHub Security Advisory, записан в `SECURITY.md`
   всех трёх репозиториев.
3. Список паттернов, которые для владельца означают «внутреннее» в
   DLP-гейте (P1-3): сегодня в правилах только то, что выведено из практики
   (адреса, пути, домены). Имена заказчиков и номера договоров в коде не
   угадываются.
4. ~~Объём первой волны исполнения: P0 целиком (рекомендуется) или P0+P1~~ —
   **закрыто исполнением 2026-09-26:** сделаны волны P0–P2, отклонения записаны
   в каждой.
