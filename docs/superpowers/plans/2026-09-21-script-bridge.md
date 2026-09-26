# Script Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дать библиотеке возможность выполнить код встроенного языка внутри открытого проекта SimInTech и получить результат файлом, с проверками, которые отличают успех от молчаливого обрыва.

**Architecture:** Чистая часть (сборка текста скрипта, разбор результата, чтение прежнего скрипта страницы из `.xprt`) живёт в `simintech_api/script_probe.py` без COM и попадает в точечный mypy-гейт. COM-часть — класс `ScriptBridge` в `simintech_api/core/script_bridge.py`, рядом с остальными обёртками COM. Мост ставит скрипт в проект через `SetPageScript`, запускает расчёт, читает файл и **обязательно** возвращает прежний скрипт на место.

**Tech Stack:** Python 3.11, `comtypes` (COM), pytest. Никаких новых зависимостей.

**Основание:** `docs/superpowers/specs/2026-09-21-script-bridge-design.md` — спецификация с измерениями на живом SimInTech64.

**Вне области этого плана:** конкретная проба топологии (обход портов и линий, структурированный результат) — отдельный план; вывод моста в MCP — отдельное решение. Здесь только механизм и его контракт отказа.

---

## Файловая структура

| Файл | Ответственность |
|---|---|
| `simintech_api/script_probe.py` (создать) | Сборка текста скрипта, разбор файла результата, чтение скрипта страницы из `.xprt`. Без COM, без файловой системы — на входе и выходе строки. |
| `simintech_api/core/script_bridge.py` (создать) | Оркестрация: сохранить прежний скрипт, поставить свой, запустить расчёт, дождаться роста модельного времени, прочитать результат, вернуть прежний скрипт. |
| `simintech_api/exceptions.py` (изменить) | Новый класс `ScriptBridgeError`. |
| `simintech_api/__init__.py` (изменить) | Экспорт `ScriptBridgeError`, `ScriptBridge`, `script_probe`-хелперов. |
| `pyproject.toml` (изменить) | `simintech_api/script_probe.py` — в список `[tool.mypy] files`. |
| `tests/unit/test_script_probe.py` (создать) | Тесты чистой части, без COM. |
| `tests/unit/test_script_bridge.py` (создать) | Тесты оркестрации на фейковом клиенте. |
| `tests/integration/test_script_bridge_live.py` (создать) | Живой прогон, маркер `integration`. |
| `docs/api.md` (изменить) | Раздел о мосте. |
| `CLAUDE.md` (изменить) | Ключевые факты: контракт `SetPageScript`. |

---

## Task 1: Результат пробы и его разбор

**Files:**
- Create: `simintech_api/script_probe.py`
- Test: `tests/unit/test_script_probe.py`

- [ ] **Step 1: Написать падающий тест**

```python
"""Разбор результата пробы: маркеры, полный и оборванный результат."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from simintech_api.script_probe import (  # noqa: E402
    BEGIN_MARKER,
    END_MARKER,
    parse_probe_result,
)


def test_parse_complete_result():
    text = f"{BEGIN_MARKER}\nстрока 1\nстрока 2\n{END_MARKER}\n"
    result = parse_probe_result(text)
    assert result.complete is True
    assert result.lines == ["строка 1", "строка 2"]


def test_parse_result_without_end_marker_is_incomplete():
    text = f"{BEGIN_MARKER}\nстрока 1\n"
    result = parse_probe_result(text)
    assert result.complete is False
    assert result.lines == ["строка 1"]


def test_parse_empty_file_is_incomplete():
    result = parse_probe_result("")
    assert result.complete is False
    assert result.lines == []


def test_parse_result_without_begin_marker_is_incomplete():
    result = parse_probe_result("мусор\nещё мусор\n")
    assert result.complete is False
    assert result.lines == []


def test_end_marker_before_begin_is_incomplete():
    """Конечный маркер раньше начального — полным результат не делает."""
    text = f"{END_MARKER}\nстрока\n{BEGIN_MARKER}\nхвост\n"
    result = parse_probe_result(text)
    assert result.complete is False
    assert result.lines == ["хвост"]
```

- [ ] **Step 2: Прогнать тест — убедиться, что падает**

Run: `python3.11 -m pytest tests/unit/test_script_probe.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'simintech_api.script_probe'`

- [ ] **Step 3: Написать минимальную реализацию**

Создать `simintech_api/script_probe.py`:

```python
"""Сборка и разбор пробных скриптов SimInTech — без COM.

Скриптовый мост устроен так: внешний клиент кладёт в проект скрипт страницы,
запускает расчёт и читает файл, который скрипт записал. Средств диагностики у
среды нет — измерено 2026-09-21 на SimInTech64: ошибка скрипта наружу не
сообщается ничем, а `SetPageScript` возвращает 1 и при синтаксически неверном
скрипте. Поэтому единственный различимый признак обрыва — отсутствие маркера
завершения, который скрипт пишет последней строкой.

Здесь лежит всё, что проверяется без COM: сборка текста скрипта, разбор
результата и чтение прежнего скрипта страницы из выгрузки `.xprt`. COM-часть —
`simintech_api/core/script_bridge.py`.
"""

from __future__ import annotations

from typing import List, NamedTuple

#: Маркеры, между которыми скрипт пишет полезные строки. Отсутствие конечного
#: означает, что скрипт оборвался: ошибка времени выполнения молча прекращает
#: его выполнение, а среда об этом не сообщает.
BEGIN_MARKER = "SCRIPT_BRIDGE_BEGIN"
END_MARKER = "SCRIPT_BRIDGE_END"


class ProbeResult(NamedTuple):
    """Разобранный результат пробы.

    `complete` — есть ли маркер завершения. `lines` — строки между маркерами;
    у оборванного результата это то, что успело записаться.
    """

    lines: List[str]
    complete: bool


def parse_probe_result(text: str) -> ProbeResult:
    """Разобрать файл результата.

    Полным считается результат, у которого есть оба маркера и конечный идёт
    после начального. Строки между ними — полезные; маркеры в них не входят.
    """
    lines = text.splitlines()
    try:
        start = lines.index(BEGIN_MARKER)
    except ValueError:
        return ProbeResult(lines=[], complete=False)
    try:
        end = lines.index(END_MARKER, start + 1)
    except ValueError:
        return ProbeResult(lines=lines[start + 1:], complete=False)
    return ProbeResult(lines=lines[start + 1:end], complete=True)
```

- [ ] **Step 4: Прогнать тест — убедиться, что проходит**

Run: `python3.11 -m pytest tests/unit/test_script_probe.py -q`
Expected: PASS, 5 passed

- [ ] **Step 5: Коммит**

```bash
git add simintech_api/script_probe.py tests/unit/test_script_probe.py
git commit -m "feat(script): разбор результата пробы с проверкой маркера завершения"
```

---

## Task 2: Сборка текста скрипта

**Files:**
- Modify: `simintech_api/script_probe.py`
- Test: `tests/unit/test_script_probe.py`

- [ ] **Step 1: Написать падающий тест**

Дописать в `tests/unit/test_script_probe.py`:

```python
from simintech_api.script_probe import build_probe_script  # noqa: E402


def test_build_wraps_body_with_markers_and_file():
    script = build_probe_script('writelnutf8(fid, "привет");', r"C:\tmp\out.txt")
    assert 'createfile("C:\\tmp\\out.txt", -1)' in script
    assert f'writelnutf8(fid, "{BEGIN_MARKER}")' in script
    assert f'writelnutf8(fid, "{END_MARKER}")' in script
    assert 'writelnutf8(fid, "привет");' in script
    assert script.index(BEGIN_MARKER) < script.index("привет") < script.index(END_MARKER)
    assert "freeobject(fid);" in script


def test_build_uses_firststep_not_initialization():
    """Обход топологии — на первом шаге: порты субмоделей на инициализации
    могут быть ещё не установлены (сказано в демо поставки)."""
    script = build_probe_script("", r"C:\tmp\out.txt")
    assert script.lstrip().startswith("if firststep then")
    assert "initialization" not in script


def test_build_rejects_quote_and_newline_in_path():
    """Путь подставляется в литерал встроенного языка — кавычка сломает скрипт."""
    import pytest

    with pytest.raises(ValueError):
        build_probe_script("", 'C:\\tmp\\bad"name.txt')
    with pytest.raises(ValueError):
        build_probe_script("", "C:\\tmp\\bad\nname.txt")
```

- [ ] **Step 2: Прогнать тест — убедиться, что падает**

Run: `python3.11 -m pytest tests/unit/test_script_probe.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_probe_script'`

- [ ] **Step 3: Написать минимальную реализацию**

Дописать в `simintech_api/script_probe.py`:

```python
def build_probe_script(body: str, result_path: str) -> str:
    """Собрать скрипт страницы, который выполнит `body` и запишет результат.

    `body` — строки на встроенном языке, пишущие в уже открытый файл вызовами
    `writelnutf8(fid, ...)`. Открытие файла, маркеры и закрытие берёт на себя
    эта функция, поэтому телу не нужно знать про маркеры.

    Тело идёт под `if firststep then`, а не в секцию `initialization`: на
    инициализации порты субмоделей могут быть ещё не установлены, и обход
    топологии даст неполную картину (сказано в демо поставки «Анализ
    топологии скриптами»).
    """
    if '"' in result_path or "\n" in result_path or "\r" in result_path:
        raise ValueError(
            "путь результата не может содержать кавычку или перевод строки: "
            f"{result_path!r} — он подставляется в литерал встроенного языка")
    indented = "".join(
        f"  {line}\n" for line in body.splitlines() if line.strip())
    return (
        "if firststep then begin\n"
        "  var fid: integer;\n"
        f'  fid = createfile("{result_path}", -1);\n'
        f'  writelnutf8(fid, "{BEGIN_MARKER}");\n'
        f"{indented}"
        f'  writelnutf8(fid, "{END_MARKER}");\n'
        "  freeobject(fid);\n"
        "end;\n"
    )
```

- [ ] **Step 4: Прогнать тест — убедиться, что проходит**

Run: `python3.11 -m pytest tests/unit/test_script_probe.py -q`
Expected: PASS, 8 passed

- [ ] **Step 5: Коммит**

```bash
git add simintech_api/script_probe.py tests/unit/test_script_probe.py
git commit -m "feat(script): сборка скрипта пробы с маркерами начала и конца"
```

---

## Task 3: Чтение прежнего скрипта страницы из выгрузки

**Files:**
- Modify: `simintech_api/script_probe.py`
- Test: `tests/unit/test_script_probe.py`

Зачем: `SetPageScript` **перезаписывает** прежний скрипт страницы (измерено). Чтобы вернуть его на место, надо сначала прочитать.

- [ ] **Step 1: Написать падающий тест**

Дописать в `tests/unit/test_script_probe.py`:

```python
from simintech_api.script_probe import read_page_script  # noqa: E402

XPRT_WITH_SCRIPT = """<?xml version="1.0"?>
<model>
 <page>
  <name>`C:\\work\\model.prt`</name>
  <script>`начало`#13#10`  seterrorflag(1);`#13#10`конец`</script>
 </page>
</model>
"""

XPRT_WITHOUT_SCRIPT = """<?xml version="1.0"?>
<model>
 <page>
  <name>`C:\\work\\model.prt`</name>
  <script>``</script>
 </page>
</model>
"""


def test_read_page_script_decodes_line_endings_and_tabs():
    script = read_page_script(XPRT_WITH_SCRIPT)
    assert script == "начало\n  seterrorflag(1);\nконец"


def test_read_page_script_returns_empty_when_absent():
    assert read_page_script(XPRT_WITHOUT_SCRIPT) == ""


def test_read_page_script_prefers_main_page():
    """Главная страница — та, чьё имя оканчивается на .prt; её скрипт и нужен."""
    text = (
        "<page><name>`внутренняя`</name><script>`внутренний`</script></page>"
        "<page><name>`C:\\work\\model.prt`</name><script>`главный`</script></page>"
    )
    assert read_page_script(text) == "главный"
```

- [ ] **Step 2: Прогнать тест — убедиться, что падает**

Run: `python3.11 -m pytest tests/unit/test_script_probe.py -q`
Expected: FAIL — `ImportError: cannot import name 'read_page_script'`

- [ ] **Step 3: Написать минимальную реализацию**

Дописать в `simintech_api/script_probe.py` (и добавить `import re` в начало файла):

```python
#: Значение в выгрузке `.xprt` обёрнуто в обратные кавычки, а перевод строки и
#: табуляция закодированы как `#13#10` и `#9` — так их пишет `SaveProjectXML`.
#: Разбираем регуляркой, а не XML-парсером: тот же приём уже используется в
#: `utils/xprt_signals.py`, потому что файл несёт BOM и вольное экранирование.
_PAGE_RE = re.compile(
    r"<page>\s*<name>`([^`]*)`</name>\s*<script>`(.*?)`</script>", re.S)


def decode_xprt_value(raw: str) -> str:
    """Раскодировать значение из выгрузки: `#13#10` → перевод строки, `#9` → табуляция."""
    return (raw.replace("#13#10", "\n")
               .replace("#13", "\r")
               .replace("#10", "\n")
               .replace("#9", "\t"))


def read_page_script(xprt_text: str) -> str:
    """Вернуть скрипт главной страницы проекта из выгрузки `.xprt`.

    Главная страница — та, чьё `<name>` оканчивается на `.prt`: в выгрузке туда
    попадает путь к файлу проекта. Если такой страницы нет, берётся первая
    страница с непустым скриптом. Пустая строка означает, что скрипта нет.
    """
    fallback = ""
    for name, raw in _PAGE_RE.findall(xprt_text):
        script = decode_xprt_value(raw)
        if name.endswith(".prt"):
            return script
        if not fallback and script.strip():
            fallback = script
    return fallback
```

- [ ] **Step 4: Прогнать тест — убедиться, что проходит**

Run: `python3.11 -m pytest tests/unit/test_script_probe.py -q`
Expected: PASS, 11 passed

- [ ] **Step 5: Добавить модуль в mypy-гейт**

В `pyproject.toml`, в список `files` секции `[tool.mypy]`, добавить строку `"simintech_api/script_probe.py"` **после** `"simintech_api/pak.py"` (список отсортирован по алфавиту).

Run: `mypy --platform win32`
Expected: `Success: no issues found in 16 source files`

Если находятся ошибки — исправить аннотации, а не убирать файл из списка: модуль чистый по COM, и именно такие в гейт и попадают.

- [ ] **Step 6: Коммит**

```bash
git add simintech_api/script_probe.py tests/unit/test_script_probe.py pyproject.toml
git commit -m "feat(script): чтение прежнего скрипта страницы из выгрузки .xprt"
```

---

## Task 4: Исключение ScriptBridgeError

**Files:**
- Modify: `simintech_api/exceptions.py`
- Test: `tests/unit/test_script_probe.py`

- [ ] **Step 1: Посмотреть, как объявлены соседние исключения**

Run: `grep -n "class .*Error" simintech_api/exceptions.py`
Expected: список классов, наследующих `SimInTechError`; у каждого — краткий docstring на русском.

- [ ] **Step 2: Написать падающий тест**

Дописать в `tests/unit/test_script_probe.py`:

```python
from simintech_api.exceptions import ScriptBridgeError, SimInTechError  # noqa: E402


def test_script_bridge_error_is_simintech_error():
    """Отказ моста — часть общего контракта библиотеки, а не отдельная иерархия."""
    assert issubclass(ScriptBridgeError, SimInTechError)


def test_script_bridge_error_is_exported_from_package_root():
    import simintech_api

    assert simintech_api.ScriptBridgeError is ScriptBridgeError
```

- [ ] **Step 3: Прогнать тест — убедиться, что падает**

Run: `python3.11 -m pytest tests/unit/test_script_probe.py -q`
Expected: FAIL — `ImportError: cannot import name 'ScriptBridgeError'`

- [ ] **Step 4: Объявить исключение и экспортировать**

В `simintech_api/exceptions.py` добавить рядом с остальными:

```python
class ScriptBridgeError(SimInTechError):
    """Не удалось выполнить скрипт в проекте или получить его результат.

    Отдельный класс нужен потому, что причину отказа среда не сообщает:
    различить «скрипт оборвался» и «скрипт не скомпилировался» можно только по
    косвенным признакам (маркер завершения, рост модельного времени), и в
    тексте исключения эти признаки должны быть названы.
    """
```

В `simintech_api/__init__.py` добавить `"ScriptBridgeError"` в список `__all__` (рядом с остальными исключениями) и в соответствующий импорт.

- [ ] **Step 5: Прогнать тест — убедиться, что проходит**

Run: `python3.11 -m pytest tests/unit/test_script_probe.py -q`
Expected: PASS, 13 passed

- [ ] **Step 6: Коммит**

```bash
git add simintech_api/exceptions.py simintech_api/__init__.py tests/unit/test_script_probe.py
git commit -m "feat(script): исключение ScriptBridgeError"
```

---

## Task 5: Мост — сохранение, установка и возврат скрипта

**Files:**
- Create: `simintech_api/core/script_bridge.py`
- Test: `tests/unit/test_script_bridge.py`

- [ ] **Step 1: Написать тест с фейковым клиентом**

Создать `tests/unit/test_script_bridge.py`:

```python
"""Мост на фейковом клиенте: какие COM-вызовы он делает и в каком порядке."""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from simintech_api.core.script_bridge import ScriptBridge  # noqa: E402

XPRT = (
    "<page><name>`C:\\work\\model.prt`</name>"
    "<script>`seterrorflag(0);`</script></page>"
)


class FakeClient:
    """Записывает вызовы; SaveProjectXML пишет заранее заданную выгрузку."""

    def __init__(self, xprt_text: str = XPRT):
        self.xprt_text = xprt_text
        self.calls = []

    def call(self, name, *args):
        self.calls.append((name, args))
        if name == "SaveProjectXML":
            Path(args[1]).write_text(self.xprt_text, encoding="utf-8")
        return 1


def test_capture_script_reads_page_script_from_export():
    bridge = ScriptBridge(FakeClient(), project_id=42)
    assert bridge.capture_script() == "seterrorflag(0);"


def test_install_script_calls_set_page_script_with_compile_now():
    client = FakeClient()
    ScriptBridge(client, project_id=42).install_script("x = 1;")
    assert client.calls == [("SetPageScript", (42, "x = 1;", 1))]


def test_capture_uses_temporary_file_and_removes_it():
    """Выгрузка идёт во временный файл: рабочий каталог засорять нельзя."""
    client = FakeClient()
    bridge = ScriptBridge(client, project_id=42)
    before = set(os.listdir(tempfile.gettempdir()))
    bridge.capture_script()
    after = set(os.listdir(tempfile.gettempdir()))
    assert after - before == set()
```

- [ ] **Step 2: Прогнать тест — убедиться, что падает**

Run: `python3.11 -m pytest tests/unit/test_script_bridge.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'simintech_api.core.script_bridge'`

- [ ] **Step 3: Написать минимальную реализацию**

Создать `simintech_api/core/script_bridge.py`:

```python
"""Скриптовый мост: выполнить код встроенного языка внутри проекта и забрать результат.

Зачем. В COM-интерфейсе нет ни удаления блока, ни чтения концов линий, а во
встроенном языке всё это есть. Мост доставляет скрипт в проект и забирает то,
что скрипт записал в файл.

Контракт измерен 2026-09-21 на SimInTech64 (см.
`docs/superpowers/specs/2026-09-21-script-bridge-design.md`):

* `SetPageScript` возвращает `1` всегда — и при синтаксически неверном скрипте
  тоже, поэтому код возврата как признак успеха бесполезен;
* `SetPageScript` **перезаписывает** прежний скрипт страницы, поэтому его надо
  сохранить и вернуть на место;
* ошибка скрипта наружу не сообщается: синтаксическая молча останавливает
  расчёт (`start`/`step` успешны, модельное время стоит на нуле), ошибка
  времени выполнения молча обрывает остаток скрипта.

Отсюда три обязательные проверки, и ни одну нельзя опустить: маркер завершения
в файле результата, рост модельного времени и возврат прежнего скрипта.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from ..catalog import decode_xprt
from ..exceptions import ScriptBridgeError
from ..script_probe import read_page_script

if TYPE_CHECKING:
    from .com_client import COMClient


class ScriptBridge:
    """Выполнить скрипт в проекте и получить результат файлом.

    Принимает пару «клиент + идентификатор проекта», как `Simulation` и `Page`:
    у `Project` публичного доступа к идентификатору нет, и заводить его ради
    одного потребителя — отдельное решение, а не побочный эффект этой работы.
    Вызывающий берёт идентификатор там, где он у него уже есть.
    """

    def __init__(self, client: "COMClient", project_id: int) -> None:
        self._client = client
        self._project_id = project_id

    def capture_script(self) -> str:
        """Прочитать текущий скрипт главной страницы проекта.

        Читается выгрузкой в `.xprt`: другого способа получить текст прежнего
        скрипта у COM-интерфейса нет. Выгрузка идёт во временный каталог и
        удаляется вместе с ним.
        """
        with tempfile.TemporaryDirectory(prefix="simintech-bridge-") as tmp:
            path = os.path.join(tmp, "page.xprt")
            self._client.call("SaveProjectXML", self._project_id, path)
            with open(path, "rb") as handle:
                data = handle.read()
        return read_page_script(decode_xprt(data))

    def install_script(self, script: str) -> None:
        """Поставить скрипт страницы. Прежний при этом теряется."""
        self._client.call("SetPageScript", self._project_id, script, 1)
```

- [ ] **Step 4: Прогнать тест — убедиться, что проходит**

Run: `python3.11 -m pytest tests/unit/test_script_bridge.py -q`
Expected: PASS, 3 passed

- [ ] **Step 5: Коммит**

```bash
git add simintech_api/core/script_bridge.py tests/unit/test_script_bridge.py
git commit -m "feat(script): мост сохраняет и ставит скрипт страницы"
```

---

## Task 6: Полный цикл пробы

**Files:**
- Modify: `simintech_api/core/script_bridge.py`
- Test: `tests/unit/test_script_bridge.py`

- [ ] **Step 1: Написать падающие тесты**

Дописать в `tests/unit/test_script_bridge.py`:

```python
import pytest  # noqa: E402

from simintech_api.exceptions import ScriptBridgeError  # noqa: E402
from simintech_api.script_probe import BEGIN_MARKER, END_MARKER  # noqa: E402


class FakeSimulationClient(FakeClient):
    """Клиент, который «считает»: время растёт, скрипт пишет файл результата."""

    def __init__(self, *, time_grows=True, script_result=END_MARKER + "\n",
                 xprt_text=XPRT):
        super().__init__(xprt_text)
        self.time_grows = time_grows
        self.script_result = script_result
        self.time = 0.0

    def call(self, name, *args):
        if name == "ProjectStart":
            self.time = 0.0
            return 0
        if name == "GetProjectTime":
            self.time = 0.1 if self.time_grows else 0.0
            return self.time
        if name == "SetPageScript":
            # Скрипт «исполняется»: пишет результат в путь из своего текста.
            body = args[1]
            start = body.index('createfile("') + len('createfile("')
            end = body.index('"', start)
            Path(body[start:end]).write_text(
                BEGIN_MARKER + "\n" + self.script_result, encoding="utf-8")
        return super().call(name, *args)


def _bridge(tmp_path, **kwargs):
    client = FakeSimulationClient(**kwargs)
    return client, ScriptBridge(client, project_id=42)


def test_run_probe_returns_complete_result(tmp_path):
    out = tmp_path / "out.txt"
    client, bridge = _bridge(tmp_path)
    result = bridge.run_probe("writelnutf8(fid, \"ok\");", out)
    assert result.complete is True


def test_run_probe_restores_previous_script(tmp_path):
    """Прежний скрипт обязан вернуться: SetPageScript его перезаписывает."""
    out = tmp_path / "out.txt"
    client, bridge = _bridge(tmp_path)
    bridge.run_probe("", out)
    assert ("SetPageScript", (42, "seterrorflag(0);", 1)) in client.calls
    assert client.calls[-1] == ("SetPageScript", (42, "seterrorflag(0);", 1))


def test_run_probe_restores_script_even_on_failure(tmp_path):
    out = tmp_path / "out.txt"
    client, bridge = _bridge(tmp_path, time_grows=False)
    with pytest.raises(ScriptBridgeError):
        bridge.run_probe("", out)
    assert client.calls[-1] == ("SetPageScript", (42, "seterrorflag(0);", 1))


def test_run_probe_reports_frozen_model_time(tmp_path):
    """Синтаксическая ошибка в скрипте молча останавливает расчёт: start и step
    «успешны», а модельное время стоит на нуле."""
    out = tmp_path / "out.txt"
    _, bridge = _bridge(tmp_path, time_grows=False)
    with pytest.raises(ScriptBridgeError) as exc:
        bridge.run_probe("", out)
    assert "модельное время" in str(exc.value)


def test_run_probe_reports_incomplete_result(tmp_path):
    """Скрипт оборвался: маркер завершения не записан."""
    out = tmp_path / "out.txt"
    _, bridge = _bridge(tmp_path, script_result="")
    with pytest.raises(ScriptBridgeError) as exc:
        bridge.run_probe("", out)
    assert "маркер" in str(exc.value).lower()


def test_run_probe_removes_previous_result_file(tmp_path):
    """Старый файл результата не должен быть принят за новый."""
    out = tmp_path / "out.txt"
    out.write_text(END_MARKER + "\nстарое\n", encoding="utf-8")
    client, bridge = _bridge(tmp_path, script_result="")
    with pytest.raises(ScriptBridgeError):
        bridge.run_probe("", out)
```

- [ ] **Step 2: Прогнать тест — убедиться, что падает**

Run: `python3.11 -m pytest tests/unit/test_script_bridge.py -q`
Expected: FAIL — `AttributeError: 'ScriptBridge' object has no attribute 'run_probe'`

- [ ] **Step 3: Написать минимальную реализацию**

Дописать в `simintech_api/core/script_bridge.py` (в класс `ScriptBridge`; в блок импортов добавить `import time`, `from ..script_probe import build_probe_script, parse_probe_result`; тип `ProbeResult` — из `..script_probe`):

```python
    #: Сколько ждать роста модельного времени, прежде чем признать, что расчёт
    #: не пошёл. Шаг расчёта на модели из демо занимает доли секунды; запас
    #: нужен на медленные и большие модели.
    TIME_GROWTH_TIMEOUT_SECONDS = 60.0

    def run_probe(self, body: str, result_path: Path) -> ProbeResult:
        """Выполнить `body` в проекте и вернуть разобранный результат.

        Порядок обязателен и продиктован измерениями:

        1. сохранить прежний скрипт — `SetPageScript` его перезаписывает;
        2. удалить прежний файл результата — иначе старый будет принят за новый;
        3. поставить скрипт и запустить расчёт;
        4. убедиться, что модельное время выросло, — иначе скрипт не
           скомпилировался, и расчёт молча не пошёл;
        5. прочитать файл и проверить маркер завершения;
        6. вернуть прежний скрипт — в любом случае, включая отказ.
        """
        original = self.capture_script()
        try:
            self.install_script(build_probe_script(body, str(result_path)))
            result_path.unlink(missing_ok=True)
            self._start_and_wait()
            if not result_path.exists():
                raise ScriptBridgeError(
                    "скрипт не создал файл результата: расчёт шёл, но скрипт "
                    "оборвался до записи. Проверьте тело пробы — ошибка "
                    "времени выполнения прерывает скрипт молча.")
            result = parse_probe_result(
                result_path.read_text(encoding="utf-8", errors="replace"))
            if not result.complete:
                raise ScriptBridgeError(
                    "в результате нет маркера завершения: скрипт оборвался, "
                    "не дойдя до конца. Записанные строки могут быть "
                    "неполными — использовать их как полный результат нельзя.")
            return result
        finally:
            # Возврат прежнего скрипта — не косметика: без него в проекте
            # останется наш скрипт, и следующий запуск модели поведёт себя
            # иначе.
            self.install_script(original)

    def _start_and_wait(self) -> None:
        """Запустить расчёт и дождаться, пока модельное время сдвинется.

        Неподвижное время — единственный различимый признак того, что скрипт
        не скомпилировался: `ProjectStart` и `ProjectStep` в этом случае
        сообщают об успехе.
        """
        self._client.call("ProjectStart", self._project_id)
        deadline = time.monotonic() + self.TIME_GROWTH_TIMEOUT_SECONDS
        while True:
            self._client.call("ProjectStep", self._project_id)
            if float(self._client.call("GetProjectTime", self._project_id)) > 0.0:
                return
            if time.monotonic() >= deadline:
                raise ScriptBridgeError(
                    "модельное время не растёт: скрипт страницы не "
                    "скомпилировался, и расчёт молча не пошёл. Проверьте "
                    "синтаксис пробы — среда об этой ошибке не сообщает.")
            time.sleep(0.05)
```

Тип `ProbeResult` импортировать в блоке `from ..script_probe import (...)`.

- [ ] **Step 4: Прогнать тест — убедиться, что проходит**

Run: `python3.11 -m pytest tests/unit/test_script_bridge.py -q`
Expected: PASS, 9 passed

- [ ] **Step 5: Прогнать весь набор и линт**

Run: `python3.11 -m pytest -q && flake8 && mypy --platform win32`
Expected: все тесты зелёные, flake8 чист, mypy без находок

- [ ] **Step 6: Коммит**

```bash
git add simintech_api/core/script_bridge.py tests/unit/test_script_bridge.py
git commit -m "feat(script): полный цикл пробы — запуск, проверки, возврат скрипта"
```

---

## Task 7: Интеграционный тест на живом SimInTech

**Files:**
- Create: `tests/integration/test_script_bridge_live.py`

Тест помечен `integration` и на не-Windows пропускается — как остальные в этом каталоге.

- [ ] **Step 1: Написать тест**

```python
"""Живой прогон моста: SimInTech, реальный COM.

Проверяет то, что фейки подтвердить не могут: скрипт действительно
исполняется средой, результат доходит файлом, а прежний скрипт страницы
возвращается на место.
"""

import sys
from pathlib import Path

import pytest

from simintech_api import COMClient
from simintech_api.core.script_bridge import ScriptBridge

pytestmark = pytest.mark.integration


@pytest.fixture()
def client():
    if sys.platform != "win32":
        pytest.skip("COM доступен только на Windows")
    com = COMClient(silent_mode=True)
    com.connect()
    try:
        yield com
    finally:
        com.disconnect()


def test_bridge_returns_topology_object_count(client, tmp_path):
    """Проба читает число объектов страницы — и оно сходится с COM-счётчиком."""
    from simintech_api.core.project import Project
    from simintech_api.core.simulation import Simulation

    project = Project.from_template(client)
    project.set_calc_end_time(1.0)
    sim = Simulation(client, project._id)
    bridge = ScriptBridge(client, project._id)

    out = tmp_path / "probe.txt"
    result = bridge.run_probe(
        'writelnutf8(fid, "objects=" + floattostr('
        "getobjcount(getcurrentcontainer)));",
        out)

    assert result.complete
    assert result.lines
    # COM-счётчик и счётчик языка должны сойтись: это перекрёстная проверка
    # того, что проба читала тот же проект.
    count_by_com = client.call("GetPageObjectCount", project._id)
    assert f"objects={count_by_com}" in result.lines
    project.close()


def test_bridge_restores_previous_script(client, tmp_path):
    """Прежний скрипт возвращается: иначе в проекте останется наш."""
    from simintech_api.core.project import Project

    project = Project.from_template(client)
    bridge = ScriptBridge(client, project._id)
    client.call("SetPageScript", project._id, "// прежний", 1)

    bridge.run_probe('writelnutf8(fid, "x");', tmp_path / "probe.txt")

    assert bridge.capture_script() == "// прежний"
    project.close()
```

- [ ] **Step 2: Прогнать на Windows**

Run: `python3.11 -m pytest tests/integration -m integration -q`
Expected: PASS. Если падает на создании проекта — проверить, что `mmain.exe /regserver` выполнен и `SIMINTECH_TEMPLATE` доступен (`find_model_template`).

- [ ] **Step 3: Убедиться, что шаг 1 плана подтверждён**

Отдельно проверить то, что в спецификации помечено как непроверенное и на что опирается возврат скрипта: **возврат пустого скрипта**. Выполнить вручную:

```
SetPageScript(pid, "", 1)  →  выгрузить .xprt  →  в <page><script> пусто?
```

Если пустой скрипт не очищает прежний, дописать в `capture_script`/`run_probe` обработку и обновить спецификацию: это измеренный факт, а не догадка.

- [ ] **Step 4: Коммит**

```bash
git add tests/integration/test_script_bridge_live.py
git commit -m "test(script): живой прогон моста на реальном COM"
```

---

## Task 8: Документация

**Files:**
- Modify: `docs/api.md`
- Modify: `CLAUDE.md`
- Modify: `README.md`

- [ ] **Step 1: Добавить раздел в `docs/api.md`**

Дописать после раздела о `Simulation`:

```markdown
## Script Bridge

`ScriptBridge(client, project_id)` выполняет код встроенного языка внутри
открытого проекта и возвращает то, что скрипт записал в файл.

```python
from pathlib import Path
from simintech_api import COMClient, Project
from simintech_api.core.script_bridge import ScriptBridge

client = COMClient().connect()
project = Project.from_template(client)
bridge = ScriptBridge(client, project._id)

result = bridge.run_probe(
    'writelnutf8(fid, "objects=" + floattostr(getobjcount(getcurrentcontainer)));',
    Path(r"C:\Temp\probe.txt"))
if result.complete:
    print(result.lines)
```

**Почему так, а не иначе.** Мост существует потому, что в COM нет ни удаления
блока, ни чтения концов линий, а во встроенном языке есть. Контракт измерен на
SimInTech64: `SetPageScript` возвращает `1` и при синтаксически неверном
скрипте, ошибка скрипта наружу не сообщается, а прежний скрипт страницы
**перезаписывается**. Поэтому `run_probe` всегда возвращает прежний скрипт на
место, требует маркер завершения в файле результата и проверяет рост модельного
времени. `result.complete == False` означает, что скрипт оборвался и строки
неполны — использовать их как полный результат нельзя.

Подробности и измерения: `docs/superpowers/specs/2026-09-21-script-bridge-design.md`.
```

- [ ] **Step 2: Добавить факты в `CLAUDE.md`**

В раздел «Библиотека: ключевые факты» дописать:

```markdown
- **`SetPageScript` возвращает 1 всегда** — и при синтаксически неверном
  скрипте тоже. Как признак успеха бесполезен (измерено 2026-09-21).
- **Ошибка скрипта наружу не сообщается.** Синтаксическая — молча
  останавливает расчёт: `start`/`step` успешны, модельное время стоит на нуле.
  Ошибка времени выполнения — молча обрывает остаток скрипта. Различимый
  признак обрыва один: отсутствие маркера завершения в файле результата.
  Мост (`core/script_bridge.py`) эти проверки и делает.
- **Скрипт страницы персистентен** — лежит в `<page><script>` внутри
  `.prt`/`.xprt`, — и `SetPageScript` его **перезаписывает**, а не добавляет.
- **`initialization` для чтения топологии не годится**: порты субмоделей на
  инициализации могут быть не установлены, обход делают на `firststep`.
```

- [ ] **Step 3: Добавить мост в список возможностей `README.md`**

В таблице состава или в разделе о библиотеке — одна строка: что мост даёт
(выполнение кода встроенного языка внутри проекта) и где лежит.

- [ ] **Step 4: Прогнать полный набор**

Run: `python3.11 -m pytest -q && flake8 && mypy --platform win32`
Expected: всё зелёное

- [ ] **Step 5: Коммит**

```bash
git add docs/api.md CLAUDE.md README.md
git commit -m "docs: скриптовый мост описан в api, CLAUDE.md и README"
```

---

## Что этот план не делает

- **Не выводит мост в MCP.** В `simintech-mcp` ничего не меняется: произвольный
  исполнитель скриптов наружу не отдаётся — по той же причине, по которой там
  нет `run_macro`. Если проба топологии понадобится агенту, она выйдет
  отдельным инструментом с фиксированным телом, а не общим `run_script`.
- **Не реализует обход топологии.** `run_probe` принимает тело пробы; сам обход
  (порты, линии, структурированный результат) — отдельный план поверх этого
  механизма.
- **Не трогает `SetPipeName`/`SetJournalSavePeriod`.** Перехват журнала в опытах
  не удался; если понадобится, это отдельная работа со своим планом.

## Что осталось непроверенным из спецификации

Эти вопросы спецификация называет открытыми; **этот план их не закрывает** и не
должен создавать впечатление, что закрыл:

| Вопрос | Почему не здесь |
|---|---|
| Различие `CompileNow=0` и `CompileNow=1` | Мост всегда ставит `1`. Если различие важно, это отдельный опыт |
| Флаг модификации проекта после `SetPageScript` | На диске проект не меняется, пока не сохранён; внутреннее состояние среды не измерялось |
| Пустой скрипт как способ очистки | Проверяется шагом 3 задачи 7 — потому что от него зависит возврат скрипта |
| Работа на проекте без расчётного слоя | `run_probe` потребует роста времени; на таком проекте откажет. Нужен ли отдельный контракт — вопрос |
| Пределы объёма результата и времени скрипта | Появится вместе с реальной пробой топологии |

---

## Отступления при выполнении

План выполнен целиком, но четыре места оказались неверны — записаны, чтобы план
не вводил в заблуждение того, кто прочтёт его позже.

1. **Тест на замороженное время ждал бы 60 секунд.** Таймаут роста модельного
   времени был зашит константой, а тест `test_run_probe_reports_frozen_model_time`
   упирается ровно в него. Таймаут стал параметром конструктора
   (`time_growth_timeout_s`), тест передаёт 0.2 с.

2. **Фейк писал файл результата не в тот момент.** В плане он писал его на
   `SetPageScript`, тогда как среда исполняет скрипт **во время расчёта**. Из-за
   этого мост справедливо удалял файл как «старый» (защита от прошлого
   результата), и тесты ловили ошибку фейка, а не поведение моста. Фейк
   переписан: пишет на `ProjectStep`.

3. **У `Project` есть публичный `id`** (`Project.id`, `Project.client`) — в плане
   записано обратное, и пример в документации предлагал `project._id`. Добавленное
   «из-за отсутствия доступа» свойство оказалось дубликатом, flake8 поймал его
   (`F811`), дубликат убран, пример в `docs/api.md` использует `project.id`.

4. **Тест экспорта `ScriptBridgeError` дублировал существующий.**
   `test_all_exception_classes_exported_at_package_root` уже проверяет, что каждый
   класс из `exceptions.py` доступен из корня. Он и стал падающим тестом задачи 4 —
   отдельный тест не понадобился.

Плюс одно уточнение по ходу: тест «выгрузка идёт во временный каталог» в плане
сравнивал листинг системного временного каталога до и после — мигающий тест.
Заменён на проверку самого пути выгрузки.
