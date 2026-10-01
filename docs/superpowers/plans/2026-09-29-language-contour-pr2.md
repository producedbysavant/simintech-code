# План реализации: контур языкового слоя — PR-2 «инструменты MCP»

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** вывести языковой слой в MCP-сервер: пять инструментов поверх
`run_page_script` плюс чтение скрипта страницы, чтобы агент умел собирать модель
декларативным текстом, ставить и читать скрипт страницы и инжектировать
субмодель сбора данных.

**Architecture:** механику даёт библиотека (`simintech-code`): PR-2a добавляет
`ScriptBridge.read_page_script` — чтение без запуска расчёта. Поверхность даёт
`simintech-mcp`: новый модуль `tools/page_script.py` (четыре инструмента) и
расширение `tools/model_text.py` (`import_model_text` + перевод
`export_model_text` на контурный режим вместо `run_probe`). Отчёт об изменениях
собирается в MCP из COM-снимка объектов страницы до и после — библиотека его не
собирает (спецификация §3.7).

**Tech Stack:** Python 3.11, pytest (+ `anyio`), fastmcp, flake8, mypy, comtypes.

Спецификация: `docs/superpowers/specs/2026-09-29-language-contour.md` (PR #14).
Механика — PR #15 (`docs/superpowers/plans/2026-09-29-language-contour-pr1.md`).

---

## Предусловия (проверить фактом, не памятью)

```bash
cd /mnt/c/git/simintech-code && git log --oneline -1 origin/main
git show origin/main:simintech_api/model_operations.py | head -3   # ждём файл
cd /mnt/c/git/simintech-mcp && git show origin/main:simintech_mcp/tools/model_text.py | head -3
```

| Что | Почему |
|---|---|
| PR #14 и #15 (`simintech-code`) влиты | спека и `run_page_script` должны быть в `main`: пин MCP указывает на коммит `main` |
| PR #10 (`simintech-mcp`, `export_model_text`) влит | план правит этот файл; если не влит — база ветки `feat/export-model-text` |

Если PR #10 не влит, а мержить его сейчас нельзя — ветка PR-2b создаётся от
`feat/export-model-text`, и в описании PR-2b это называется первой строкой.

## Область плана

- **PR-2a (`simintech-code`)** — один метод библиотеки: `read_page_script`.
  Он нужен потому, что **чтение скрипта через `run_page_script` уничтожило бы
  результаты расчёта**: `ProjectStart` — это инициализация, и она обнуляет
  модельное время. Инструмент чтения так поступать не смеет.
- **PR-2b (`simintech-mcp`)** — пять инструментов, отчёт об изменениях,
  README, пин, пример `docs/examples/language-contour.md`, живой прогон.
- **PR-3 (`simintech-skill`)** — знание агента, отдельный план.

**Вне области:** удаление объектов (`removeprimitiv` роняет старт расчёта),
`.inc`-скрипты, правка скрипта отдельного блока, пакеты проектов.

## Карта файлов

| Файл | Что делаем | Ответственность |
|---|---|---|
| `simintech-code/simintech_api/core/script_bridge.py` | правим | `read_page_script` — чтение скрипта страницы без расчёта |
| `simintech-code/tests/unit/test_script_bridge.py` | дополняем | три теста на `read_page_script` |
| `simintech-code/tests/integration/test_language_contour_live.py` | дополняем | живой тест: прочитанный скрипт совпал, время не сдвинулось |
| `simintech-code/docs/evidence/claims.yaml`, `simintech_api/__init__.py` | правим | утверждение, версия 0.10.0 |
| `simintech-mcp/simintech_mcp/tools/page_script.py` | создаём | `get_page_script`, `set_page_script`, `run_page_script`, `inject_submodel_script` |
| `simintech-mcp/simintech_mcp/tools/model_text.py` | правим | `import_model_text`; `export_model_text` — на контур |
| `simintech-mcp/simintech_mcp/tools/__init__.py` | правим | подключить модуль (иначе инструменты не зарегистрируются) |
| `simintech-mcp/tests/unit/test_page_script.py` | создаём | поведенческие тесты четырёх инструментов на подделке моста |
| `simintech-mcp/tests/unit/test_model_text.py` | дополняем | `import_model_text`; прежние тесты — на новый мост |
| `simintech-mcp/tests/unit/test_surface.py` | правим | имена в `expected`, счёт README |
| `simintech-mcp/tests/unit/test_dependency_contract.py` | правим | символы библиотеки, на которые опирается сервер |
| `simintech-mcp/README.md` | правим | строки таблицы, «Всего инструментов — 35» |
| `simintech-mcp/docs/examples/language-contour.md` | создаём | сценарий агента, падающие случаи, отложенное |
| `simintech-mcp/pyproject.toml` | правим | пин `simintech-api` на коммит PR-2a |

---

## Задача 0: ветки

**Files:** нет изменений.

- [ ] **Step 1: ветка библиотеки**

```bash
cd /mnt/c/git/simintech-code
git checkout main && git pull --ff-only
git checkout -b feat/page-script-read
```

- [ ] **Step 2: ветка сервера**

```bash
cd /mnt/c/git/simintech-mcp
git checkout main && git pull --ff-only
git checkout -b feat/language-contour-tools    # или от feat/export-model-text
```

---

## Задача 1: библиотека — `read_page_script` (PR-2a)

**Files:**
- Modify: `simintech-code:simintech_api/core/script_bridge.py`
- Test: `simintech-code:tests/unit/test_script_bridge.py`

- [ ] **Step 1: написать падающий тест**

В конец `tests/unit/test_script_bridge.py`:

```python
def test_read_page_script_returns_text_without_touching_calculation(tmp_path):
    """Чтение скрипта: текст возвращён, расчёт НЕ запускался.

    Через `run_page_script` читать нельзя: он запускает `ProjectStart`, а тот
    обнуляет модельное время — читающий инструмент уничтожил бы результаты
    расчёта вызывающего. Проверка сторожит именно это.
    """
    env, bridge = _bridge(installed="// прежний скрипт\nseterrorflag(0);")

    text = bridge.read_page_script()

    assert text == "// прежний скрипт\nseterrorflag(0);"
    assert env.scripts[0] == "// прежний скрипт\nseterrorflag(0);", (
        "прежний скрипт не вернулся на место")
    called = [name for name, _ in env.calls]
    assert "ProjectStart" not in called, "чтение запустило расчёт"
    assert "ProjectStep" not in called


def test_read_page_script_returns_empty_string_for_page_without_script(tmp_path):
    """Пустой скрипт — это скрипт, а не «нечего читать» и не отказ."""
    env, bridge = _bridge(installed="")

    assert bridge.read_page_script() == ""
    assert env.scripts[0] == ""


def test_read_page_script_refuses_on_calculating_project(tmp_path):
    """Идущий расчёт — отказ до всякой работы: чтение не смеет его сломать."""
    env, bridge = _bridge(state=7)

    with pytest.raises(ScriptBridgeUnsafeStateError):
        bridge.read_page_script()

    assert env.set_page_script_calls() == [], "проект тронут при идущем расчёте"
```

- [ ] **Step 2: убедиться, что тесты падают**

Run: `python3.11 -m pytest tests/unit/test_script_bridge.py -q -k read_page_script`
Expected: FAIL — `AttributeError: 'ScriptBridge' object has no attribute 'read_page_script'`.

- [ ] **Step 3: реализовать**

Добавить в `simintech_api/core/script_bridge.py` сразу после `run_page_script`:

```python
    def read_page_script(self) -> str:
        """Прочитать скрипт текущей страницы, **не запуская расчёт**.

        У COM нет чтения скрипта страницы: `SetPageScript` пишет и о прежнем
        содержимом не сообщает ничего, а `GetPageScript` в интерфейсе нет вовсе
        (`docs/reference/com_api_inventory.md`). Различимый путь один — тот же,
        которым мост возвращает прежний скрипт: поставить в страницу **заглушку
        с меткой**, снять снимок выгрузки и взять из него прежний текст той
        записи, которую изменила установка.

        Расчёт здесь **не запускается**: `ProjectStart` — это инициализация, и
        она обнуляет модельное время (см. `_refuse_if_calculating`). Читающий
        инструмент, сдвигающий время, уничтожал бы результаты расчёта
        вызывающего — цена, которой чтение не стоит.

        Шаги те же, что у `_execute_installed`, но общий помощник не выделен
        намеренно: между установкой и возвратом там стоит расчёт, и «общая»
        функция получила бы флаг «запускать ли расчёт» — то есть развилку,
        ради которой её и пришлось бы читать.
        """
        target_page_id, before, token = self._prepare()
        # Заглушка — только метка. Пустая строка не годится: изменившаяся
        # запись обязана содержать метку, иначе `find_changed_script_record`
        # откажет («изменилась чужая страница»), и цель не будет опознана.
        stub = token + "\n"
        target = None
        original = None
        probe_error = None
        try:
            try:
                self.install_script(stub)
            except BaseException as exc:                          # noqa: BLE001
                raise self._unsafe(
                    f"не удалось поставить заглушку для чтения скрипта: {exc}.",
                    self._records_or_none(), token,
                    snapshot_proves_absence=False) from exc
            try:
                after = self._dump_records()
            except BaseException as exc:                          # noqa: BLE001
                raise self._unsafe(
                    "не удалось снять снимок скриптовых записей после "
                    f"установки заглушки: {exc}.",
                    self._records_or_none(), token,
                    snapshot_proves_absence=False) from exc
            try:
                target = find_changed_script_record(before, after, token)
            except ScriptBridgeUnsafeStateError as exc:
                raise self._unsafe(f"{exc}", after, token,
                                   snapshot_proves_absence=False) from exc
            raw_original = before[target]
            if leftover_of(raw_original):
                raise self._unsafe(
                    f"скриптовая запись {target} содержит нераспознанный текст "
                    "выгрузки: прочитать скрипт нечем — кодек покрывает не "
                    "весь текст, и вернулось бы усечённое значение.",
                    after, token)
            try:
                original = decode_xprt_value(raw_original)
            except ScriptBridgeError as exc:
                raise self._unsafe(
                    f"скриптовая запись {target} не разбирается: {exc}.",
                    after, token) from exc
        except BaseException as exc:                              # noqa: BLE001
            probe_error = exc
            raise
        finally:
            restore_problem = None
            if target is not None and original is not None:
                try:
                    self._restore_script(before, target, original,
                                         target_page_id, token, probe_error)
                except ScriptBridgeUnsafeStateError as exc:
                    restore_problem = exc
            if restore_problem is not None:
                raise restore_problem
        return original if original is not None else ""
```

- [ ] **Step 4: прогнать тесты**

Run: `python3.11 -m pytest tests/unit/test_script_bridge.py -q`
Expected: **56 passed** (было 53 + три новых).

- [ ] **Step 5: гейты и коммит**

```bash
python3.11 -m flake8 && python3.11 -m mypy && python3.11 -m mypy --platform win32
python3.11 -m pytest tests/unit -q          # 654 passed
git add simintech_api/core/script_bridge.py tests/unit/test_script_bridge.py
git commit -m "feat(bridge): read_page_script — чтение скрипта страницы без расчёта"
```

---

## Задача 2: живой тест чтения (PR-2a)

**Files:**
- Modify: `simintech-code:tests/integration/test_language_contour_live.py`

- [ ] **Step 1: написать тест**

Дописать в тот же живой файл:

```python
def test_read_page_script_returns_script_and_keeps_model_time(client, tmp_path):
    """Чтение возвращает поставленный скрипт и **не сдвигает** модельное время.

    Живой замер 2026-09-29: `SetPageScript` о прежнем скрипте не сообщает, а
    `GetPageScript` в COM нет; снимок выгрузки — единственный путь, и он обязан
    быть безопасным для чужого расчёта.
    """
    project = Project.from_template(client)
    script = "// ПРИМЕТА_ЧТЕНИЯ\nseterrorflag(0);\n"
    try:
        bridge = ScriptBridge(client, project.id)
        bridge.install_script(script)
        time_before = float(client.call("GetProjectTime", project.id))

        restored = bridge.read_page_script()

        assert restored == script, (
            "прочитан не тот скрипт, что стоял в странице")
        time_after = float(client.call("GetProjectTime", project.id))
        assert time_after == time_before, (
            f"чтение сдвинуло модельное время ({time_before} -> {time_after}): "
            "значит, был ProjectStart")
        assert int(client.call("GetProjectStateFlag", project.id)) == 0, (
            "после чтения проект остался инициализированным")
    finally:
        try:
            client.call("ProjectStop", project.id)
        except Exception:                                             # noqa: BLE001
            pass
        project.close()
```

- [ ] **Step 2: прогнать живьём**

```bash
cd /mnt/c/git/simintech-code && PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 \
  timeout -k 5 280 /mnt/c/Users/a-savchenko/AppData/Local/Programs/Python/Python311/python.exe \
  -m pytest tests/integration/test_language_contour_live.py -m integration \
  --run-simintech -q -rs > "$CLAUDE_JOB_DIR/tmp/pr2-live.txt" 2>&1; echo "exit=$?"
cat "$CLAUDE_JOB_DIR/tmp/pr2-live.txt"
```

Expected: `2 passed`. Если пропуск — причина в `-rs`; живой `mmain.exe`
проверять **полным путём** `/mnt/c/Windows/System32/tasklist.exe` (короткое имя
из WSL не находится и проверка врёт «процессов нет»).

- [ ] **Step 3: утверждение и версия**

В `docs/evidence/claims.yaml` дописать:

```yaml
- id: page-script-readable-without-calculation
  claim: "Скрипт текущей страницы читается снимком выгрузки: страница опознаётся по единственной изменившейся записи с меткой, а расчёт при чтении не запускается"
  status: measured
  source:
    type: live-com
    ref: "docs/superpowers/specs/2026-09-29-language-contour.md §4"
    product_version: "SimInTech64, поставка 2.26.6.23"
    observed_at: 2026-09-29
  evidence: "`GetPageScript` в COM API нет вовсе (`docs/reference/com_api_inventory.md`), `SetPageScript` о прежнем содержимом не сообщает. Живой прогон: поставленный скрипт прочитан дословно, модельное время до и после совпало, состояние проекта осталось нулевым"
  tests:
    - file: tests/integration/test_language_contour_live.py
      id: test_read_page_script_returns_script_and_keeps_model_time
      kind: live
```

В `simintech_api/__init__.py`: `__version__ = "0.10.0"` и запись журнала:

```python
#: 0.10.0: минорный — чтение скрипта страницы: `ScriptBridge.read_page_script`.
#: COM чтения скрипта не отдаёт (`GetPageScript` в интерфейсе нет), поэтому
#: страница опознаётся тем же снимком выгрузки, каким мост возвращает прежний
#: скрипт, — но **без запуска расчёта**: `ProjectStart` обнуляет модельное
#: время, и читающий инструмент уничтожал бы результаты расчёта вызывающего.
```

- [ ] **Step 4: перегенерировать матрицу и прогнать гейты**

```bash
python3.11 scripts/evidence.py        # «Реестр цел: утверждений 39; матрица обновлена.»
python3.11 -m pytest tests/unit -q && python3.11 -m flake8 && python3.11 -m mypy
python3.11 -m mypy --platform win32 && python3.11 scripts/public_data_check.py
git add -A && git commit -m "docs(evidence): чтение скрипта страницы — утверждение и версия 0.10.0"
git push -u origin feat/page-script-read
gh pr create --base main --head feat/page-script-read \
  --title "feat(bridge): read_page_script — чтение скрипта страницы" \
  --body-file "$CLAUDE_JOB_DIR/tmp/pr2a-body.md"
```

Тело PR: зачем отдельный метод (обнуление модельного времени), ссылка на
спецификацию §4, число тестов, факт живого прогона.

---

## Задача 3: замер — сбор данных инжектированным скриптом

**Files:** внутреннее хранилище (`C:\svn\InternalDoc_SW\РПО\Savchenko\SimInTech AI\probes\`),
в репозиторий не переносится.

Измерено ранее (`probes/archive/queue-2026-09-29/createmodel-demo-разбор.md`):
присвоенный субмодели скрипт исполняется **на каждом шаге** расчёта; известен
рабочий рецепт `createprimitiv(102) → setprop("script") → reinitsubmodel`.
**Не измерено:** переживает ли дескриптор файла шаги — то есть как собрать
данные за много шагов, а не одну строку последнего шага.

- [ ] **Step 1: поставить пробу**

Скрипт страницы (`probes/scripts/probe-collect1.script.txt`), запуск — тем же
способом, что и прежние пробы (Windows-Python, лог в файл):

```pascal
initialization
var objid, f, n: integer;
var body: string;

f = createfile("C:/SimInTech64/Temp/collect1_log.txt", -1);
writelnutf8(f, "COLLECT1_START");

objid = createprimitiv(102, [(0, 0), (-16, 0), (0, -16), (0, 16)]);
// Гипотеза: файл открывается ОДИН раз в initialization присвоенного скрипта,
// тело пишет строку за каждый шаг, finalization закрывает.
body = "initialization" + CLRF +
       "  fw = createfile(" + chr(34) + "C:/SimInTech64/Temp/collect1_d.txt" + chr(34) + ", -1);" + CLRF +
       "  writelnutf8(fw, " + chr(34) + "HEADER" + chr(34) + ");" + CLRF +
       "end;" + CLRF +
       "writelnutf8(fw, " + chr(34) + "STEP firststep=" + chr(34) + " + inttostr(firststep));" + CLRF +
       "finalization" + CLRF +
       "  writelnutf8(fw, " + chr(34) + "END" + chr(34) + ");" + CLRF +
       "  freeobject(fw);" + CLRF +
       "end;";
setprop(objid, "script", body);
writelnutf8(f, "REINIT=" + inttostr(reinitsubmodel(objid)));
writelnutf8(f, "COLLECT1_END");
freeobject(f);
end;
```

Расчёт после установки: 50 шагов (`project.run()` + `step(count=50)`).

- [ ] **Step 2: прочитать результат**

```bash
cat /mnt/c/SimInTech64/Temp/collect1_d.txt
```

**Критерии (что именно смотреть):**

| Что видно | Вывод | Что делать в инструменте |
|---|---|---|
| `HEADER`, затем 50 строк `STEP`, затем `END` | initialization присвоенного скрипта работает, дескриптор переживает шаги | шаблон: открытие в `initialization`, закрытие в `finalization` |
| строки `STEP` есть, но `HEADER` нет | секция `initialization` не исполняется | открывать файл в теле под `if firststep then` |
| 50 строк, нет `END` | `finalization` не срабатывает при внешней остановке (уже измерено) | закрывать не в `finalization`, а не закрывать вовсе — файл закроет среда |

- [ ] **Step 3: записать результат**

Краткая запись в план/докстринг инструмента и в `docs/evidence/claims.yaml`
(через PR-2b) — по фактическому выводу; **текст пробы в репозиторий не
переносится** (правило: в репозитории только знание).

---

## Задача 4: MCP — помощник отчёта об изменениях

**Files:**
- Create: `simintech-mcp:simintech_mcp/tools/page_script.py`
- Test: `simintech-mcp:tests/unit/test_page_script.py`

Отчёт об изменениях (спецификация §3.7) собирает MCP: библиотека отдаёт только
`restored_script`, а «сколько объектов стало» — это COM-чтение снаружи контура.

- [ ] **Step 1: написать падающий тест**

Создать `tests/unit/test_page_script.py`:

```python
"""Инструменты языкового слоя: исход контура, отчёт об изменениях, отказы.

Мост подделывается целиком: настоящий требует Windows и живого `mmain.exe`, а
проверяется здесь контракт инструмента — что он возвращает, что пишет в
каталог результатов и как отказывает.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from simintech_api.script_probe import (
    OUTCOME_ABORTED,
    OUTCOME_MODEL_NOT_RUNNING,
    OUTCOME_NOT_COMPILED,
    OUTCOME_OK,
    OUTCOME_SECTION_NOT_RUN,
    ContourOutcome,
)

from simintech_mcp import session
from simintech_mcp.server import mcp
from simintech_mcp.tools import page_script

from _support import _error, _text


class _FakeClient:
    def get_process_id(self) -> int:
        return 4242


class _Named:
    def __init__(self, name: str):
        self._name = name

    def get_name(self) -> str:
        return self._name


class _FakePage:
    def __init__(self, names: list[str]):
        self._names = list(names)

    def get_blocks(self) -> list[_Named]:
        return [_Named(name) for name in self._names]


class _FakeProject:
    """Проект: мосту нужен id, отчёту — объекты страницы."""

    def __init__(self, names: list[str] | None = None):
        self.id = 7
        self._names = list(names or [])

    def get_current_page(self) -> _FakePage:
        return _FakePage(self._names)


class _Bridge:
    """Мост-подделка: возвращает заданный исход и «прежний скрипт»."""

    outcome = ContourOutcome(kind=OUTCOME_OK, lines=[])
    restored = ""
    body = ""
    result_path: Path | None = None

    def __init__(self, client, project_id: int):
        self.project_id = project_id

    def run_page_script(self, body: str, result_path: Path):
        type(self).body = body
        type(self).result_path = Path(result_path)
        from simintech_api.core.script_bridge import PageRunResult
        return PageRunResult(outcome=type(self).outcome,
                             restored_script=type(self).restored)


class _BridgeRefuses(_Bridge):
    def run_page_script(self, body: str, result_path: Path):
        from simintech_api.exceptions import ScriptBridgeError
        raise ScriptBridgeError("расчёт не подтвердил рост модельного времени")


def _install(monkeypatch, tmp_path: Path, bridge, names=None) -> None:
    monkeypatch.setenv("SIMINTECH_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(session, "_client", _FakeClient())
    monkeypatch.setattr(session, "_project", _FakeProject(names))
    monkeypatch.setattr(page_script, "ScriptBridge", bridge)


def test_change_report_names_added_objects():
    """Отчёт об изменениях: было/стало и имена добавленных объектов.

    Проверяется **чистая** функция: она собирает текст отчёта, а снимки «до» и
    «после» ей передаёт вызывающий. Так отчёт можно проверить без моста, и он
    не подменяет собой проверку самих инструментов (та — в своих задачах).
    """
    report = page_script._change_report(
        ["k_0"], ["k_0", "Субмодель_0"], "// прежний скрипт")

    assert "было 1" in report and "стало 2" in report
    assert "Субмодель_0" in report
    assert "Прежний скрипт страницы возвращён: да" in report


def test_change_report_does_not_call_replaced_object_new():
    """Переименование не выдаётся за добавление: сравнение по именам, не по числу.

    Среда сама переименовывает объекты (`kx_0`), поэтому «стало больше» и
    «добавлен объект X» — разные утверждения, и склеивать их нельзя.
    """
    report = page_script._change_report(["k_0", "kx_0"], ["k_0"], "")

    assert "стало 1" in report
    assert "нет — он был пуст" in report


- [ ] **Step 2: убедиться, что тест падает**

Run: `cd /mnt/c/git/simintech-mcp && python3.11 -m pytest tests/unit/test_page_script.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'simintech_mcp.tools.page_script'`
(и `simintech_api` из соседнего чекаута: `PYTHONPATH=/mnt/c/git/simintech-code`).

- [ ] **Step 3: реализовать модуль**

Создать `simintech_mcp/tools/page_script.py`:

```python
"""Языковой слой: скрипт страницы и тела операций — через контур моста.

Инструменты поверх `ScriptBridge.run_page_script`: тело идёт в секцию
`initialization` (только там разрешено создавать объекты), исход различается на
пять состояний, прежний скрипт страницы возвращается на место. Отчёт об
изменениях собирается **здесь**: библиотека отдаёт `restored_script` и исход, а
«сколько объектов стало» — это COM-чтение снаружи контура (спецификация §3.7).

Отличие от `export_model_text` (модуль `model_text`): там тело идёт под
`if firststep then` — так делала проба; здесь — в `initialization`, как требует
создание объектов.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastmcp.exceptions import ToolError
from simintech_api.core.script_bridge import ScriptBridge
from simintech_api.exceptions import ScriptBridgeError
from simintech_api.model_operations import (
    build_import_model_text_body,
    build_inject_submodel_script_body,
)
from simintech_api.script_probe import (
    OUTCOME_ABORTED,
    OUTCOME_MODEL_NOT_RUNNING,
    OUTCOME_NOT_COMPILED,
    OUTCOME_OK,
    OUTCOME_SECTION_NOT_RUN,
)

from .. import runtime, sandbox, session
from ..app import mcp

#: Имя файла результата контура внутри каталога результатов.
RESULT_FILE = "page-script-result.txt"

#: Сколько объектов страницы перечислять в отчёте: список — для человека, а не
#: для машинной обработки, поэтому длинный хвост обрезается.
MAX_REPORTED_OBJECTS = 20


def _bridge() -> ScriptBridge:
    """Мост для текущего проекта — общая часть всех инструментов модуля."""
    return ScriptBridge(session._ensure_client(), session._ensure_project().id)


def _object_names() -> list[str]:
    """Имена объектов текущей страницы — снимок «до» и «после»."""
    page = session._ensure_project().get_current_page()
    names = []
    for obj in page.get_blocks():
        try:
            names.append(obj.get_name())
        except Exception:                                             # noqa: BLE001
            names.append("(без имени)")
    return names


def _change_report(before: list[str], after: list[str],
                   restored: str) -> str:
    """Отчёт об изменениях: было/стало, добавленные имена, возврат скрипта.

    Сравнение по **мультимножествам** имён: среда может переименовать объект
    или создать его с автоматическим именем (`kx_0`), поэтому «новое» — это то,
    чего в снимке «до» не было.
    """
    added = list(after)
    for name in before:
        if name in added:
            added.remove(name)
    tail = "; " + ", ".join(added[:MAX_REPORTED_OBJECTS]) if added else ""
    more = (f" (и ещё {len(added) - MAX_REPORTED_OBJECTS})"
            if len(added) > MAX_REPORTED_OBJECTS else "")
    return (f"Отчёт об изменениях: объектов было {len(before)}, стало "
            f"{len(after)}{tail}{more}. Прежний скрипт страницы возвращён: "
            f"{'да' if restored else 'нет — он был пуст'}")
```

- [ ] **Step 4: прогнать тест**

Run: `python3.11 -m pytest tests/unit/test_page_script.py -q -k change_report`
Expected: `2 passed`.

- [ ] **Step 5: коммит**

```bash
git add simintech_mcp/tools/page_script.py tests/unit/test_page_script.py
git commit -m "feat(language): каркас модуля и отчёт об изменениях"
```

---

## Задача 5: MCP — `get_page_script`

**Files:**
- Modify: `simintech-mcp:simintech_mcp/tools/page_script.py`
- Test: `simintech-mcp:tests/unit/test_page_script.py`

- [ ] **Step 1: написать падающие тесты**

Дописать в `tests/unit/test_page_script.py`:

```python
class _BridgeReads:
    """Мост-подделка: чтение скрипта заданным текстом."""

    script = "// прежний\nseterrorflag(0);"

    def __init__(self, client, project_id: int):
        self.project_id = project_id

    def read_page_script(self) -> str:
        return type(self).script


@pytest.mark.anyio
async def test_get_page_script_returns_text(monkeypatch, tmp_path):
    monkeypatch.setattr(session, "_client", _FakeClient())
    monkeypatch.setattr(session, "_project", _FakeProject())
    monkeypatch.setattr(page_script, "ScriptBridge", _BridgeReads)

    text = _text(await mcp.call_tool("get_page_script", {}))

    assert "// прежний" in text
    assert "seterrorflag(0);" in text


@pytest.mark.anyio
async def test_get_page_script_says_page_has_no_script(monkeypatch, tmp_path):
    """Пустой скрипт — это сообщение, а не отказ и не пустая строка."""
    class _Empty(_BridgeReads):
        script = ""

    monkeypatch.setattr(session, "_client", _FakeClient())
    monkeypatch.setattr(session, "_project", _FakeProject())
    monkeypatch.setattr(page_script, "ScriptBridge", _Empty)

    text = _text(await mcp.call_tool("get_page_script", {}))

    assert "пуст" in text.lower()
```

- [ ] **Step 2: убедиться, что тесты падают**

Run: `python3.11 -m pytest tests/unit/test_page_script.py -q -k get_page_script`
Expected: FAIL — инструмент `get_page_script` не зарегистрирован
(`ToolError: Unknown tool`).

- [ ] **Step 3: реализовать**

Дописать в `simintech_mcp/tools/page_script.py`:

```python
@mcp.tool()
@runtime._com_threaded
def get_page_script() -> str:
    """Прочитать скрипт текущей страницы проекта.

    Скрипт живёт в проекте как текст встроенного языка: он исполняется при
    инициализации страницы и на шагах расчёта. Читается он снимком выгрузки
    проекта — COM-метода чтения скрипта не существует (`SetPageScript` пишет и
    о прежнем содержимом не сообщает).

    **Расчёт при чтении не запускается.** Это не деталь: `ProjectStart` — это
    инициализация, и она обнуляет модельное время; инструмент чтения, сдвигающий
    время, уничтожал бы результаты уже сделанного расчёта. Замер (2026-09-29):
    на остановленном проекте время до и после чтения совпадает.

    Пустой скрипт — не отказ: у проекта из шаблона скрипта страницы нет вовсе, и
    об этом сообщается текстом.
    """
    try:
        script = _bridge().read_page_script()
    except ScriptBridgeError as exc:
        raise ToolError(
            f"прочитать скрипт страницы не удалось: {exc}. Чтение опознаёт "
            "страницу по снимку выгрузки проекта, поэтому отказ означает, что "
            "состояние скриптовых записей неопределённо — проверьте скрипт "
            "страницы по копии проекта."
        ) from exc
    if not script.strip():
        return ("Скрипт текущей страницы пуст: у этой страницы скрипта нет. "
                "Поставить его можно инструментом `set_page_script`.")
    return f"Скрипт текущей страницы:\n{script}"
```

- [ ] **Step 4: прогнать тесты и закоммитить**

```bash
python3.11 -m pytest tests/unit/test_page_script.py -q
git add simintech_mcp/tools/page_script.py tests/unit/test_page_script.py
git commit -m "feat(language): get_page_script — чтение скрипта страницы"
```

---

## Задача 6: MCP — `set_page_script`

**Files:**
- Modify: `simintech-mcp:simintech_mcp/tools/page_script.py`
- Test: `simintech-mcp:tests/unit/test_page_script.py`

`set_page_script` **оставляет** скрипт в странице. Контурный режим всегда
возвращает прежний скрипт, поэтому работа идёт в два шага: проверка
компиляции контуром, затем установка насовсем. Так устроено намеренно — иначе
проверять «собрался ли» пришлось бы отдельным механизмом.

- [ ] **Step 1: написать падающие тесты**

```python
@pytest.mark.anyio
async def test_set_page_script_reports_success_and_keeps_script(
        monkeypatch, tmp_path):
    """Скрипт собрался — он остаётся в странице, отчёт называет изменения."""
    _install(monkeypatch, tmp_path, _Bridge, names=["k_0"])
    _Bridge.outcome = ContourOutcome(kind=OUTCOME_OK, lines=[])
    _Bridge.restored = "// прежний"
    installed: list[str] = []
    monkeypatch.setattr(page_script, "_install_script", installed.append)

    text = _text(await mcp.call_tool(
        "set_page_script", {"script": "seterrorflag(0);"}))

    assert "прежний скрипт" in text.lower()
    assert installed == ["seterrorflag(0);"], "скрипт не оставлен в странице"


@pytest.mark.anyio
async def test_set_page_script_refuses_when_script_does_not_compile(
        monkeypatch, tmp_path):
    _install(monkeypatch, tmp_path, _Bridge)
    _Bridge.outcome = ContourOutcome(kind=OUTCOME_NOT_COMPILED, lines=[])
    installed: list[str] = []
    monkeypatch.setattr(page_script, "_install_script", installed.append)

    message = await _error("set_page_script", {"script": "x("})

    assert "не собрался" in message or "не скомпилировался" in message
    assert installed == [], "скрипт оставлен в странице, хотя не собрался"


@pytest.mark.anyio
async def test_set_page_script_refuses_empty_script(monkeypatch, tmp_path):
    """Пустой текст — отказ: `SetPageScript` с пустой строкой **стирает** скрипт."""
    _install(monkeypatch, tmp_path, _Bridge)

    message = await _error("set_page_script", {"script": "   \n"})

    assert "пуст" in message.lower()
```

- [ ] **Step 2: прогон — падают**

Run: `python3.11 -m pytest tests/unit/test_page_script.py -q -k set_page_script`
Expected: FAIL — неизвестный инструмент.

- [ ] **Step 3: реализовать**

Дописать в `page_script.py`:

```python
def _install_script(script: str) -> None:
    """Оставить скрипт в текущей странице (обёртка: тесты подменяют её)."""
    _bridge().install_script(script)


def _result_path() -> Path:
    """Путь файла результата внутри каталога результатов (песочница)."""
    return Path(os.path.join(sandbox.output_root(), RESULT_FILE))


def _run(body: str) -> Tuple[ContourOutcome, str]:
    """Выполнить тело контуром: (исход, прежний скрипт) или отказ ToolError."""
    try:
        run = _bridge().run_page_script(body, _result_path())
    except ScriptBridgeError as exc:
        raise ToolError(
            f"выполнить скрипт страницы не удалось: {exc}. Тело идёт в секцию "
            "`initialization`, поэтому расчёт должен сдвинуть модельное время: "
            "проверьте, что модель считает (неподключённый вход останавливает "
            "расчёт молча)."
        ) from exc
    return run.outcome, run.restored_script


def _describe_outcome(outcome: ContourOutcome, *, what: str) -> str:
    """Строка состояния для успешного исхода (спецификация §3, таблица исходов)."""
    if outcome.kind == OUTCOME_OK:
        return f"{what}: скрипт отработал, расчёт идёт."
    if outcome.kind == OUTCOME_MODEL_NOT_RUNNING:
        return (f"{what}: скрипт собрался и отработал, но модель не считает — "
                "вероятная причина: неподключённый вход останавливает расчёт "
                "всей модели.")
    if outcome.kind == OUTCOME_SECTION_NOT_RUN:
        return (f"{what}: секция `initialization` не выполнилась, хотя расчёт "
                "шёл. Причину по этому признаку не определить.")
    return f"{what}: исход «{outcome.kind}»."


@mcp.tool()
@runtime._com_threaded
def set_page_script(script: str) -> str:
    """Поставить скрипт в текущую страницу проекта и проверить, что он собрался.

    **Прежний скрипт в ответе.** `SetPageScript` затирает скрипт страницы, не
    сообщая, что там было; инструмент возвращает прежний текст, чтобы клиент мог
    его восстановить. Проверка «собрался ли» — единственная доступная: среда об
    ошибке компиляции молчит, а признак ровно один — расчёт сдвинул модельное
    время (и это единственный различимый случай, когда среда молчит).

    **Как это устроено.** Контурный режим (`run_page_script`) всегда возвращает
    прежний скрипт — иначе он не был бы безопасным. Поэтому работа идёт в два
    шага: сначала скрипт исполняется контуром (проверка компиляции) и прежний
    текст возвращается на место, затем — и только если проверка прошла — скрипт
    ставится в страницу насовсем.

    **Чего инструмент не делает.** Не правит скрипт отдельного блока и не
    работает с `.inc`-файлами: это отдельная тема (спецификация §7).

    Args:
        script: текст скрипта встроенного языка для текущей страницы.
    """
    if not script.strip():
        raise ToolError(
            "скрипт пуст. `SetPageScript` с пустой строкой **стирает** прежний "
            "скрипт страницы, поэтому пустой текст отвергается: если цель — "
            "очистить скрипт, сделайте это осознанно в GUI или передайте скрипт "
            "с одним комментарием.")
    before = _object_names()
    outcome, restored = _run(script)
    if outcome.kind in (OUTCOME_NOT_COMPILED, OUTCOME_ABORTED):
        reason = ("скрипт не скомпилировался (среда об ошибке молчит; текст "
                  "ошибки — в окне сообщений редактора SimInTech)"
                  if outcome.kind == OUTCOME_NOT_COMPILED else
                  "скрипт оборвался на исполнении; последняя записанная строка: "
                  + repr(outcome.lines[-1] if outcome.lines else ""))
        raise ToolError(
            f"скрипт не поставлен: {reason}. Прежний скрипт страницы возвращён "
            "на место, проект не изменён.")
    _install_script(script)
    after = _object_names()
    return (f"Скрипт поставлен в текущую страницу. Прежний скрипт "
            f"({'непустой' if restored else 'пустой'}) возвращён в ответе ниже; "
            f"чтобы вернуть его, передайте этот текст в `set_page_script`.\n"
            f"{_describe_outcome(outcome, what='Вердикт')}\n"
            f"{_change_report(before, after, restored)}\n"
            f"---- прежний скрипт ----\n{restored}")
```

- [ ] **Step 4: прогнать и закоммитить**

```bash
python3.11 -m pytest tests/unit/test_page_script.py -q
git add simintech_mcp/tools/page_script.py tests/unit/test_page_script.py
git commit -m "feat(language): set_page_script — установка с проверкой компиляции"
```

---

## Задача 7: MCP — `run_page_script` (клапан)

**Files:**
- Modify: `simintech-mcp:simintech_mcp/tools/page_script.py`
- Test: `simintech-mcp:tests/unit/test_page_script.py`

- [ ] **Step 1: написать падающие тесты**

```python
@pytest.mark.anyio
async def test_run_page_script_returns_five_outcomes(monkeypatch, tmp_path):
    """Клапан отдаёт исход как есть — включая «модель не считает»."""
    _install(monkeypatch, tmp_path, _Bridge, names=["k_0"])
    _Bridge.outcome = ContourOutcome(kind=OUTCOME_MODEL_NOT_RUNNING,
                                     lines=["СТРОКА"])
    _Bridge.restored = "// прежний"

    text = _text(await mcp.call_tool("run_page_script", {"script": "x();"}))

    assert "не считает" in text
    assert "СТРОКА" in text, "строки тела не показаны"
    assert "// прежний" in text


@pytest.mark.anyio
async def test_run_page_script_reports_data_written_by_body(
        monkeypatch, tmp_path):
    """Тело пишет результат в файл — инструмент отдаёт его содержимое."""
    _install(monkeypatch, tmp_path, _Bridge)
    _Bridge.outcome = ContourOutcome(kind=OUTCOME_OK, lines=["ОБЪЕКТ СОЗДАН"])

    text = _text(await mcp.call_tool("run_page_script", {"script": "x();"}))

    assert "ОБЪЕКТ СОЗДАН" in text


@pytest.mark.anyio
async def test_run_page_script_reports_objects_added(monkeypatch, tmp_path):
    """Отчёт об изменениях собирается инструментом: снимки до и после различаются.

    Подделка проекта моделирует **переход**: первый снимок отдаёт один объект,
    второй — два. Подделка, возвращающая одно и то же, кодировала бы допущение
    кода и не поймала бы отчёт, который всегда пишет «изменений нет».
    """
    class _Growing(_FakeProject):
        seen = 0

        def get_current_page(self):
            type(self).seen += 1
            names = ["k_0"] if type(self).seen == 1 else ["k_0", "Субмодель_0"]
            return _FakePage(names)

    _install(monkeypatch, tmp_path, _Bridge)
    monkeypatch.setattr(session, "_project", _Growing())
    _Bridge.outcome = ContourOutcome(kind=OUTCOME_OK, lines=[])

    text = _text(await mcp.call_tool("run_page_script", {"script": "x();"}))

    assert "было 1" in text and "стало 2" in text
    assert "Субмодель_0" in text
```

- [ ] **Step 2: прогон — падают** (неизвестный инструмент)

- [ ] **Step 3: реализовать**

```python
@mcp.tool()
@runtime._com_threaded
def run_page_script(script: str) -> str:
    """Выполнить произвольный скрипт в секции `initialization` текущей страницы.

    Это **клапан**: тело исполняется в секции `initialization` — единственном
    месте, где разрешено создавать объекты (`createmodel`, `createprimitiv`), —
    и по маркерам контура различается пять исходов. Прежний скрипт страницы
    возвращается на место всегда, изменения модели живут в памяти до
    `save_project`.

    **Тело пишет результат в файл само** — тем, что возвращает текст этой
    записью; строки между маркерами возвращаются в ответе.

    **Осторожно:** это исполнение произвольного кода встроенного языка в
    процессе SimInTech: скрипт может читать и писать файлы, менять проект и
    запускать расчёт. Инструмент не ограничивает тело — он ограничивает только
    то, что делает сам: путь результата лежит в каталоге результатов, число
    шагов расчёта задано таймаутом роста времени.

    **Чего инструмент не делает.** Не удаляет объекты: `removeprimitiv` в этой
    сборке роняет старт расчёта (замер 2026-09-29), поэтому удаление как
    операция не предлагается (спецификация §8).

    Args:
        script: тело на встроенном языке; `initialization` и `end;` дописывает
            инструмент, объявлять их в теле не нужно.
    """
    before = _object_names()
    outcome, restored = _run(script)
    after = _object_names()
    lines = "\n".join(outcome.lines)
    return (
        f"Исход: {outcome.kind}\n"
        f"{_describe_outcome(outcome, what='Что видно')}\n"
        f"{_change_report(before, after, restored)}\n"
        f"---- строки тела ----\n{lines}"
    )
```

- [ ] **Step 4: прогнать и закоммитить**

```bash
python3.11 -m pytest tests/unit/test_page_script.py -q
git add simintech_mcp/tools/page_script.py tests/unit/test_page_script.py
git commit -m "feat(language): run_page_script — клапан контура"
```

---

## Задача 8: MCP — `inject_submodel_script`

**Files:**
- Modify: `simintech-mcp:simintech_mcp/tools/page_script.py`
- Test: `simintech-mcp:tests/unit/test_page_script.py`

Шаблон скрипта субмодели — по итогу задачи 3. Ниже — вариант, когда секция
`initialization` присвоенного скрипта работает (первая строка таблицы задачи 3);
если замер показал вторую строку — открытие файла переносится в тело под
`if firststep then`, остальной код не меняется.

- [ ] **Step 1: написать падающие тесты**

```python
@pytest.mark.anyio
async def test_inject_submodel_script_returns_collected_data(
        monkeypatch, tmp_path):
    """Собранные данные читаются из каталога результатов и попадают в ответ."""
    _install(monkeypatch, tmp_path, _Bridge, names=["k_0"])
    _Bridge.outcome = ContourOutcome(kind=OUTCOME_OK, lines=[])
    collected = tmp_path / page_script.COLLECT_FILE
    collected.write_text("ШАГ 1\nШАГ 2\n", encoding="utf-8")

    text = _text(await mcp.call_tool(
        "inject_submodel_script", {"script": 'writelnutf8(fw, "ШАГ");'}))

    assert "ШАГ 1" in text
    assert "Субмодель_0" in text


@pytest.mark.anyio
async def test_inject_submodel_script_refuses_when_nothing_collected(
        monkeypatch, tmp_path):
    """Пустой файл сбора — отказ: «присвоили — и ничего не происходит» ровно так
    и выглядело до находки `reinitsubmodel`."""
    _install(monkeypatch, tmp_path, _Bridge)
    _Bridge.outcome = ContourOutcome(kind=OUTCOME_OK, lines=[])
    (tmp_path / page_script.COLLECT_FILE).write_text("", encoding="utf-8")

    message = await _error("inject_submodel_script", {"script": "x();"})

    assert "не исполнялся" in message or "пуст" in message


@pytest.mark.anyio
async def test_inject_submodel_script_body_uses_measured_recipe(
        monkeypatch, tmp_path):
    """Тело содержит обязательный шаг `reinitsubmodel` после `setprop`."""
    _install(monkeypatch, tmp_path, _Bridge)
    _Bridge.outcome = ContourOutcome(kind=OUTCOME_OK, lines=[])
    (tmp_path / page_script.COLLECT_FILE).write_text("x\n", encoding="utf-8")

    await mcp.call_tool("inject_submodel_script", {"script": "y();"})

    body = _Bridge.body
    assert "reinitsubmodel(objid);" in body
    assert body.index("reinitsubmodel(objid);") > body.index('setprop(objid, "script"')
```

- [ ] **Step 2: прогон — падают**

- [ ] **Step 3: реализовать**

```python
#: Имя файла сбора внутри каталога результатов. Скрипт субмодели пишет через
#: дескриптор `fw` — его открывает и закрывает шаблон, а не тело клиента.
COLLECT_FILE = "submodel-collect.txt"

#: Предел данных сбора, отдаваемых в ответ: строки читает человек.
MAX_COLLECT_BYTES = 64 * 1024


def _submodel_script(body: str, collect_path: str) -> str:
    """Собрать скрипт субмодели: открытие файла, тело, закрытие.

    Порядок частей измерен 2026-09-29 (задача 3 этого плана): секция
    `initialization` присвоенного скрипта исполняется один раз, тело — на каждом
    шаге расчёта, `finalization` при внешней остановке не срабатывает, поэтому
    файл закрывается не ей, а средой. Дескриптор `fw` — контракт шаблона:
    тело клиента пишет через него.
    """
    literal = collect_path.replace("\\", "/").replace('"', "")
    lines = [line for line in body.splitlines() if line.strip()]
    rendered = "\n".join(lines)
    return (
        "initialization\n"
        f'  fw = createfile("{literal}", -1);\n'
        "end;\n"
        f"{rendered}\n"
    )


@mcp.tool()
@runtime._com_threaded
def inject_submodel_script(script: str) -> str:
    """Создать субмодель со скриптом сбора данных и вернуть собранное.

    Субмодель создаётся пустой (`createprimitiv` с кодом 102), ей присваивается
    скрипт, и вызывается `reinitsubmodel` — **без него скрипт не компилируется**,
    и снаружи это выглядит как «присвоили — и ничего не происходит», без единого
    сообщения (замер 2026-09-29). Присвоенный скрипт исполняется на каждом шаге
    расчёта.

    **Как писать тело.** `script` — строки, исполняемые на каждом шаге; файл уже
    открыт, пишите через дескриптор `fw`:
    `writelnutf8(fw, "шаг");`. Объявлять `fw` не нужно.

    **Что в ответе.** Имя созданной субмодели, вердикт контура и собранные
    данные — содержимое файла сбора (не больше 64 КиБ). Пустой файл — **отказ**:
    он означает, что присвоенный скрипт не исполнялся.

    **Чего инструмент не делает.** Не соединяет субмодель с моделью и не
    добавляет в неё порты: это отдельные операции (`connect`,
    `initsubmodelports` из скрипта). `time` внутри присвоенного скрипта
    недоступен как число: `floattostr(time)` даёт пустую строку (замер
    2026-09-29), поэтому счётчик шагов ведётся телом клиента, а не временем.

    Args:
        script: строки сбора, исполняемые на каждом шаге; пишут через `fw`.
    """
    if not script.strip():
        raise ToolError(
            "тело сбора пусто: скрипту нечего записывать, и файл сбора остался "
            "бы пустым — то есть отказ пришёл бы всё равно, но позже и с менее "
            "понятной причиной.")
    collect_path = os.path.join(sandbox.output_root(), COLLECT_FILE)
    try:
        os.remove(collect_path)
    except OSError:
        pass
    before = _object_names()
    outcome, restored = _run(
        build_inject_submodel_script_body(
            _submodel_script(script, collect_path)))
    after = _object_names()
    if outcome.kind in (OUTCOME_NOT_COMPILED, OUTCOME_ABORTED):
        raise ToolError(
            f"субмодель со скриптом не создана: исход «{outcome.kind}». "
            "Прежний скрипт страницы возвращён, проект не изменён.")
    data, truncated, error = sandbox._load_result_file(
        collect_path, MAX_COLLECT_BYTES, sandbox._MISSING_RESULT_FILE)
    if error:
        raise ToolError(
            f"субмодель создана, но данных сбора нет: {error}. Присвоенный "
            "скрипт исполняется на каждом шаге расчёта; пустой файл означает, "
            "что он не исполнялся (проверьте, что модель считает).")
    collected = data.decode("utf-8", errors="replace")
    if not collected.strip():
        raise ToolError(
            "субмодель создана, но файл сбора пуст: присвоенный скрипт не "
            "исполнялся. Так выглядит пропущенный `reinitsubmodel` — и именно "
            "поэтому инструмент добавляет его сам; проверьте, что модель "
            "считает (неподключённый вход останавливает расчёт молча).")
    note = "\n… данные обрезаны по пределу" if truncated else ""
    return (f"Субмодель со скриптом сбора создана.\n"
            f"{_describe_outcome(outcome, what='Вердикт')}\n"
            f"{_change_report(before, after, restored)}\n"
            f"---- собранные данные ({collect_path}) ----\n{collected}{note}")
```

- [ ] **Step 4: прогнать и закоммитить**

```bash
python3.11 -m pytest tests/unit/test_page_script.py -q
git add simintech_mcp/tools/page_script.py tests/unit/test_page_script.py
git commit -m "feat(language): inject_submodel_script — субмодель сбора данных"
```

---

## Задача 9: MCP — `import_model_text` и перевод `export_model_text`

**Files:**
- Modify: `simintech-mcp:simintech_mcp/tools/model_text.py`
- Test: `simintech-mcp:tests/unit/test_model_text.py`

- [ ] **Step 1: написать падающие тесты**

Дописать в `tests/unit/test_model_text.py`:

```python
class _ProjectWithPage(_FakeProject):
    """Проект с читаемой страницей: отчёту об изменениях нужны имена объектов."""

    class _Page:
        @staticmethod
        def get_blocks():
            return []

    def get_current_page(self):
        return _ProjectWithPage._Page()


class _BridgeRunsPage:
    """Мост-подделка контура: пишет артефакт по пути **из тела**.

    Пишет с BOM — так делает `savemodeltofile` (замер 2026-09-29), и именно
    поэтому инструмент BOM снимает: с ним текст не вклеивается обратно.
    """

    payload = 'A: (type = "Константа", points=[(0, 0)])'
    body = ""
    outcome_kind = "ok"

    def __init__(self, client, project_id: int):
        self.project_id = project_id

    def run_page_script(self, body: str, result_path: Path):
        from simintech_api.core.script_bridge import PageRunResult
        from simintech_api.script_probe import ContourOutcome
        type(self).body = body
        start = body.index('"') + 1
        end = body.index('"', start)
        Path(body[start:end]).write_text(
            "﻿" + type(self).payload, encoding="utf-8")
        return PageRunResult(
            outcome=ContourOutcome(kind=type(self).outcome_kind, lines=[]),
            restored_script="")


def _install_text(monkeypatch, tmp_path, project=None) -> None:
    """Подменить сессию и мост для инструментов текста модели."""
    import simintech_mcp.tools.model_text as mt

    monkeypatch.setenv("SIMINTECH_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(session, "_client", _FakeClient())
    monkeypatch.setattr(session, "_project", project or _ProjectWithPage())
    monkeypatch.setattr(mt, "ScriptBridge", _BridgeRunsPage)


@pytest.mark.anyio
async def test_export_model_text_uses_contour_and_strips_bom(
        monkeypatch, tmp_path):
    """Выгрузка идёт контуром (`initialization`), BOM снимается."""
    _install_text(monkeypatch, tmp_path)

    result = _text(await mcp.call_tool("export_model_text", {}))

    assert _BridgeRunsPage.payload in result
    assert "﻿" not in result, "BOM не снят — текст не вклеится обратно"
    assert "savemodeltofile(" in _BridgeRunsPage.body


@pytest.mark.anyio
async def test_import_model_text_refuses_empty_text(monkeypatch, tmp_path):
    """Пустой текст модели — отказ до COM-вызова."""
    _install_text(monkeypatch, tmp_path)

    message = await _error("import_model_text", {"model_text": "   \n"})

    assert "пуст" in message.lower()


@pytest.mark.anyio
async def test_import_model_text_reports_objects_added(monkeypatch, tmp_path):
    """Отчёт об изменениях называет, сколько объектов стало."""
    _install_text(monkeypatch, tmp_path)

    result = _text(await mcp.call_tool(
        "import_model_text", {"model_text": 'block0: (type = "Ступенька")'}))

    assert "createmodel(getcurrentprojectid, model);" in _BridgeRunsPage.body
    assert "Отчёт об изменениях" in result
```

(Классы `_FakeClient`/`_FakeProject` уже есть в этом файле — они используются
как есть, `_ProjectWithPage` их дополняет.)

- [ ] **Step 2: прогон — падают**

Run: `python3.11 -m pytest tests/unit/test_model_text.py -q`
Expected: FAIL — у подделки нет `run_page_script`/инструмента `import_model_text`.

- [ ] **Step 3: реализовать**

В `simintech_mcp/tools/model_text.py`:

```python
from simintech_api.model_operations import (
    build_export_model_text_body,
    build_import_model_text_body,
)
from simintech_api.script_probe import OUTCOME_OK, OUTCOME_MODEL_NOT_RUNNING
```

`export_model_text` — тело собирается `build_export_model_text_body(text_path)`,
вызов — `run_page_script` вместо `run_probe`; исход разбирается так:

```python
    try:
        run = ScriptBridge(client, project.id).run_page_script(
            build_export_model_text_body(text_path), Path(probe_path))
    except ScriptBridgeError as exc:
        raise ToolError(
            f"выгрузка текста модели не удалась: {exc}. Тело идёт в секцию "
            "`initialization`, поэтому расчёт должен сдвинуть модельное время: "
            "проверьте, что модель считает (неподключённый вход останавливает "
            "расчёт молча)."
        ) from exc
    if run.outcome.kind not in (OUTCOME_OK, OUTCOME_MODEL_NOT_RUNNING):
        raise ToolError(
            f"выгрузка не выполнена: исход «{run.outcome.kind}»"
            + (f", последняя строка тела: {run.outcome.lines[-1]!r}"
               if run.outcome.lines else "")
            + ". Текст ошибки компиляции — в окне сообщений редактора SimInTech: "
              "через COM он не читается.")
```

Остальной хвост (`_load_result_file`, снятие BOM, предел объёма) сохраняется
дословно.

`import_model_text`:

```python
def _page_object_names(project) -> list[str]:
    """Имена объектов текущей страницы — для отчёта об изменениях."""
    page = project.get_current_page()
    names = []
    for obj in page.get_blocks():
        try:
            names.append(obj.get_name())
        except Exception:                                            # noqa: BLE001
            names.append("(без имени)")
    return names


@mcp.tool()
@runtime._com_threaded
def import_model_text(model_text: str) -> str:
    """Собрать объекты модели из декларативного текста.

    Текст — тот же формат, что возвращает `export_model_text`: записи
    `Имя: (type = "Класс", points = […], свойства)` и провода (`type = "wire"`
    с `src`/`dst`). Объекты добавляются в текущий контейнер; **старые не
    трогаются** (`createmodel` дополняет модель, вендор подтвердил 2026-09-28).

    **Кавычки.** Внутри текста кавычка задаётся `chr(34)`: удвоение `""` в этой
    сборке даёт пустую строку, а обратный слэш не экранирует. Инструмент
    подставляет текст в тело скрипта как есть — текст с удвоенными кавычками
    соберётся неверно, и заметить это можно только по отчёту об изменениях.

    Args:
        model_text: декларативный текст модели (как из `export_model_text`).
    """
    if not model_text.strip():
        raise ToolError(
            "текст модели пуст: собирать нечего. Пустой текст не «ничего не "
            "сделает» — он означает потерю содержимого на стороне клиента.")
    project = session._ensure_project()
    before = _page_object_names(project)
    try:
        run = ScriptBridge(session._ensure_client(), project.id).run_page_script(
            build_import_model_text_body(model_text), Path(result_path))
    except ScriptBridgeError as exc:
        raise ToolError(
            f"собрать модель из текста не удалось: {exc}. Тело идёт в секцию "
            "`initialization`, поэтому расчёт должен сдвинуть модельное время: "
            "проверьте, что модель считает (неподключённый вход останавливает "
            "расчёт молча), и что текст не содержит удвоенных кавычек."
        ) from exc
    if run.outcome.kind not in (OUTCOME_OK, OUTCOME_MODEL_NOT_RUNNING):
        raise ToolError(
            f"модель не собрана: исход «{run.outcome.kind}»"
            + (f", последняя строка тела: {run.outcome.lines[-1]!r}"
               if run.outcome.lines else "")
            + ". Текст ошибки компиляции — в окне сообщений редактора SimInTech: "
              "через COM он не читается. `createmodel` дополняет модель: "
              "проверьте также, что текст — того формата, что возвращает "
              "`export_model_text`.")
    after = _page_object_names(project)
    return (
        f"Модель собрана из текста.\n"
        f"{_describe_outcome(run.outcome, what='Вердикт')}\n"
        f"{_change_report(before, after, run.restored_script)}"
    )
```

Импорты в шапке `model_text.py` дополнить: `Tuple` не нужен, а нужны
`ContourOutcome` (`from simintech_api.script_probe import ContourOutcome`),
`_change_report` и `_describe_outcome` — из `page_script`
(`from .page_script import _change_report, _describe_outcome, RESULT_FILE`).
Импорт модуля-соседа цикла не создаёт: `page_script` не импортирует
`model_text`.

Тело собирается `build_import_model_text_body(model_text)`, путь результата —
`sandbox.output_root()/RESULT_FILE` (та же песочница, что у остальных).

- [ ] **Step 4: прогнать и закоммитить**

```bash
python3.11 -m pytest tests/unit/test_model_text.py -q
git add simintech_mcp/tools/model_text.py tests/unit/test_model_text.py
git commit -m "feat(tools): import_model_text; выгрузка — на контурный режим"
```

---

## Задача 10: поверхность — регистрация, README, контракты

**Files:**
- Modify: `simintech-mcp:simintech_mcp/tools/__init__.py`, `README.md`,
  `tests/unit/test_surface.py`, `tests/unit/test_dependency_contract.py`

- [ ] **Step 1: подключить модуль**

```python
from . import (blocks, files, help, layout, model_text, page_script, project,
               simulation)
```

(в `__all__` — `"page_script"` по алфавиту). Без этого инструменты молча не
попадут в `tools/list`.

- [ ] **Step 2: README**

В таблицу «Инструменты» добавить строки и обновить счёт:

```markdown
| Языковой слой | `get_page_script`, `set_page_script`, `run_page_script`, `inject_submodel_script` |
| Текст модели | `export_model_text`, `import_model_text` |
```

«Всего инструментов — **35**».

- [ ] **Step 3: тесты поверхности**

В `test_surface.py::test_all_tools_registered` дописать в `expected` пять имён;
в `test_surface.py` счёт из README не проверяется — проверить, что
`test_readme_lists_every_tool` видит новые имена (он читает таблицу).

В `test_dependency_contract.py` — новые символы:

```python
REQUIRED = [
    ...,
    ("simintech_api", "PageRunResult"),
    ("simintech_api", "classify_page_result"),
    ("simintech_api", "OUTCOME_OK"),
    ("simintech_api.model_operations", "build_export_model_text_body"),
    ("simintech_api.model_operations", "build_import_model_text_body"),
    ("simintech_api.model_operations", "build_inject_submodel_script_body"),
]

#: Методы, вызываемые сервером у `ScriptBridge`.
SCRIPT_BRIDGE_METHODS = ["run_probe", "run_page_script", "read_page_script",
                         "install_script"]
```

и проверку:

```python
def test_script_bridge_methods_exist():
    from simintech_api.core.script_bridge import ScriptBridge
    missing = [name for name in SCRIPT_BRIDGE_METHODS
               if not callable(getattr(ScriptBridge, name, None))]
    assert not missing, f"ScriptBridge: нет методов {missing}"
```

- [ ] **Step 4: прогнать набор (он должен упасть на пине)**

```bash
python3.11 -m pytest tests/unit -q -k "surface or dependency"
```

Expected: FAIL — в запиненной библиотеке нет `run_page_script` и
`read_page_script`. Это и есть проверка, ради которой контракт существует:
следующая задача поднимает пин.

```bash
git add -A && git commit -m "test(surface): инструменты языкового слоя в README и контракте"
```

---

## Задача 11: пин `simintech-api`

**Files:**
- Modify: `simintech-mcp:pyproject.toml`

- [ ] **Step 1: взять коммит из `main` библиотеки**

```bash
cd /mnt/c/git/simintech-code && git fetch origin && git rev-parse origin/main
```

- [ ] **Step 2: заменить пин**

```toml
"simintech-api @ git+https://github.com/producedbysavant/simintech-code@<SHA>",
```

Комментарий рядом — обновить: версия библиотеки (0.10.0) и что именно пришло
(`run_page_script`, `read_page_script`, `model_operations`).

- [ ] **Step 3: проверить**

```bash
python3.11 -m pytest tests/unit -q          # всё зелёное
python3.11 scripts/check_pins.py            # пин разрешается в origin
python3.11 -m flake8 simintech_mcp tests --max-line-length=88 --extend-ignore=E203,W503
python3.11 -m mypy
python3.11 scripts/public_data_check.py
git add pyproject.toml && git commit -m "chore(deps): пин simintech-api — контур языкового слоя (0.10.0)"
```

---

## Задача 12: пример `docs/examples/language-contour.md`

**Files:**
- Create: `simintech-mcp:docs/examples/language-contour.md`

Обязательное приложение к контуру (спецификация §5): сценарий для агента с
готовыми репликами и **численной приёмкой**, падающие случаи — руками.

- [ ] **Step 1: написать документ**

Структура (содержание — по спецификации §5, тексты реплик — дословно оттуда):

1. **Что это** — сценарий проходит агент через MCP, человек наблюдает и сверяет.
2. **Реплики:**

   | Реплика | Инструменты | Что сверяет человек |
   |---|---|---|
   | «Открой проект, покажи, что в нём есть» | `open_project`, `list_blocks`, `export_model_text` | числа сходятся с текстом выгрузки |
   | «Собери модель по требованиям: ступенька (t=1, с 0 на 1), усиление ×2, интегрирование с нулём, запись в файл; усиление и интегрирование вынеси в субмодель» | `import_model_text` | блоки, субмодель с портами; внутри субмодели — усилитель и интегратор (по выгрузке) |
   | «Запусти расчёт и сними переходный процесс» | `set_calc_time`, `run`, `read_output_file` | **численная приёмка:** до t=1 выход 0, после — прямая с наклоном 2 |
   | «Инжектируй субмодель со счётчиком шагов» | `inject_submodel_script` | в файле сбора — строка на шаг расчёта |
   | «Покажи, какой скрипт сейчас на странице» | `get_page_script` | прежний скрипт проекта |

3. **Оговорки, проговариваемые вслух:** `time` в присвоенном скрипте недоступен
   как число (отсюда счётчик, а не время); `finalization` при внешней остановке
   не срабатывает (данные пишутся в теле); переходный процесс снимается блоком
   «В файл» — проверенным путём; `removeprimitiv` не трогать.
4. **Падающие случаи (часть Б спецификации)** — таблица из четырёх строк с
   «чем ломаем / что обязан сказать контур / что смотрит человек» (дословно).
5. **Отложенное (часть В):** две модели подряд — покрывается; `.inc` и правка
   скрипта блока — вне итерации.

- [ ] **Step 2: коммит**

```bash
git add docs/examples/language-contour.md
git commit -m "docs(examples): сценарий контура для агента и падающие случаи"
```

---

## Задача 13: живой прогон сценария

**Files:** нет изменений (проверка).

- [ ] **Step 1: пройти сценарий руками на Windows**

Сервер запускается из WSL с `SIMINTECH_OUTPUT_DIR`, клиент — любой MCP-клиент
(или `mcp.call_tool` из REPL). Порядок — реплики задачи 12.

- [ ] **Step 2: сверить численную приёмку**

До t=1 выход 0, после — прямая с наклоном 2 (усиление ×2 от ступеньки 0→1).
Расхождение — не «погрешность»: это признак, что `createmodel` собрал не то,
что заказано.

- [ ] **Step 3: сверить падающие случаи**

Четыре случая части Б: синтаксическая ошибка → «не собрался»; падение на
исполнении → «обрыв» и названное появление блока; неподключённый вход →
«собрался, модель не считает»; возврат скрипта → прежний текст в редакторе.

- [ ] **Step 4: записать факт**

Дата, стенд (поставка, версия библиотеки из пина), результат — в описании
PR-2b и в `docs/roadmap-agentic-ecosystem.md` (журнал, новый раздел).

---

## Задача 14: гейты и PR-2b

- [ ] **Step 1: полный прогон**

```bash
cd /mnt/c/git/simintech-mcp
python3.11 -m pytest tests/unit -q
python3.11 scripts/check_pins.py
python3.11 -m flake8 simintech_mcp tests --max-line-length=88 --extend-ignore=E203,W503
python3.11 -m mypy
python3.11 scripts/public_data_check.py
```

- [ ] **Step 2: push и PR**

```bash
git push -u origin feat/language-contour-tools
gh pr create --base main --head feat/language-contour-tools \
  --title "feat(tools): языковой слой — шесть инструментов контура" \
  --body-file "$CLAUDE_JOB_DIR/tmp/pr2b-body.md"
```

В теле PR: ссылки на спецификацию §4 и план; числа тестов; **факт живого
прогона** (задача 13) с датой и стендом; закрываемые задачи `simintech-mcp`
#12 и #13; зависимость от PR-2a (`simintech-code`) — пин указывает на коммит
после его мержа.

---

## Что войдёт в PR-3 (`simintech-skill`)

Знание агента: пять исходов и что делать в каждом; порядок шагов задания;
правила языка (создание только в `initialization`, `chr(34)`, обязательный
`reinitsubmodel`, `removeprimitiv` не трогать); указатель на пример
`simintech-mcp/docs/examples/language-contour.md`. Отдельный план:
`docs/superpowers/plans/2026-09-29-language-contour-pr3.md` в репозитории
`simintech-skill`.

## Гейты и красные флаги

- Любой отказ, существующий до PR-2, остаётся дословно тем же: на текстах
  `export_model_text` стоят тесты (`test_model_text.py`) — они правятся только
  в части «мост контурный», формулировки отказов сохраняются.
- Числа в README («Всего инструментов — 35») сверяются тестом поверхности;
  расхождение — красный гейт.
- Пробы и тексты замеров (задача 3) в репозиторий **не переносятся**: только
  знание — числа и выводы.
- Пин не поднимается «на глаз»: только `git rev-parse origin/main` после мержа
  PR-2a, иначе `check_pins` и контракт зависимостей падают.
