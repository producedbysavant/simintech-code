# План реализации: контур языкового слоя — PR-1 «механика» (`simintech-code`)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** дать библиотеке режим «скрипт страницы целиком» и классификацию исхода
(пять различимых состояний), на которых строится весь языковой слой MCP.

**Architecture:** чистые сборщики и классификатор — в `simintech_api/script_probe.py`
и новом `simintech_api/model_operations.py`; COM-часть — второй режим моста в
`simintech_api/core/script_bridge.py`, собираемый из уже проверенных частей
`run_probe` (преамбула, снимки, возврат прежнего скрипта) плюс «рост времени
как данные», а не как исключение.

**Tech Stack:** Python 3.11, pytest, flake8, mypy (два прохода), comtypes.

Спецификация: `docs/superpowers/specs/2026-09-29-language-contour.md`.

---

## Область плана

- **Этот план — PR-1 полностью** (механика в `simintech-code`). Он даёт рабочий,
  тестируемый результат сам по себе: библиотека умеет выполнить тело в
  `initialization` и сказать, что именно произошло.
- **Отчёт об изменениях** (спецификация §3.7: сколько объектов и какие имена
  появились) в PR-1 не входит: его собирает слой MCP из уже существующих
  инструментов (`list_blocks` до и после вызова). PR-1 со своей стороны отдаёт
  `PageRunResult.restored_script` — строку «прежний скрипт возвращён».
- **PR-2 (инструменты `simintech-mcp`) и PR-3 (знание `simintech-skill` +
  пример) — отдельными планами.** Их код опирается на публичную форму
  `run_page_script`, которая замерзает только после мержа PR-1, а `simintech-mcp`
  дополнительно требует поднять пин `simintech-api` на коммит PR-1. Писать их
  сейчас — значит писать план против ещё не существующего API.
  Перечень того, что в них войдёт, — в конце документа.

## Карта файлов

| Файл | Что делаем | Ответственность |
|---|---|---|
| `simintech_api/script_probe.py` | дополняем | маркеры `CTX_*`, `build_page_script`, `ContourOutcome`, `classify_page_result` — чистые функции без COM |
| `simintech_api/model_operations.py` | создаём | чистые сборщики тел трёх операций и литерал встроенного языка |
| `simintech_api/core/script_bridge.py` | правим | `_prepare`/`_execute_installed`/`_try_start_and_wait` (рефакторинг без смены поведения), `PageRunResult`, `run_page_script` |
| `simintech_api/__init__.py` | правим | экспорт `PageRunResult`, `OUTCOME_*`, запись в журнал версий, `0.9.0` |
| `pyproject.toml` | правим | `simintech_api/model_operations.py` в `[tool.mypy] files` |
| `tests/unit/test_script_probe.py` | дополняем | сборка скрипта страницы, пять исходов классификатора |
| `tests/unit/test_model_operations.py` | создаём | литерал языка и три тела операций |
| `tests/unit/test_script_bridge.py` | дополняем | `run_page_script` на `FakeEnv`; `raw_result` в подделке |
| `tests/integration/test_language_contour_live.py` | создаём | живой прогон: объект создан, прежний скрипт вернулся |
| `docs/api.md`, `docs/evidence/claims.yaml`, `docs/evidence/verification-matrix.md`, `docs/knowledge-snapshot.md` | правим | документация, утверждение, матрица, снапшот |

Порядок задач выбран так, чтобы каждая заканчивалась зелёным набором: сначала
чистые функции (их можно писать до COM-части), затем рефакторинг под зелёными
тестами, затем новая COM-функция, затем живые прогоны и документы.

---

## Задача 0: ветка

**Files:** нет изменений.

- [ ] **Step 1: создать ветку от main**

```bash
cd /mnt/c/git/simintech-code
git checkout main
git pull --ff-only
git checkout -b feat/language-contour-pr1
```

Ожидание: `git branch --show-current` печатает `feat/language-contour-pr1`.

---

## Задача 1: маркеры контура и сборка скрипта страницы

**Files:**
- Modify: `simintech_api/script_probe.py` (после `build_probe_script`)
- Test: `tests/unit/test_script_probe.py`

- [ ] **Step 1: написать падающий тест**

```python
def test_page_script_frames_body_with_markers_and_keeps_token_first():
    """Скрипт страницы: метка первой строкой, тело в initialization, маркеры вокруг."""
    from simintech_api.script_probe import (
        DECOY_DESCRIPTOR_NAME, PAGE_BEGIN_MARKER, PAGE_END_MARKER,
        build_page_script,
    )

    script = build_page_script("seterrorflag(0);", "C:/out/r.txt", token="//TOK_1")
    lines = script.splitlines()

    assert lines[0] == "//TOK_1", "метка обязана быть первой строкой"
    assert "initialization" in script
    assert f'writelnutf8(br_result_1, "{PAGE_BEGIN_MARKER}");' in script
    assert f'writelnutf8(br_result_1, "{PAGE_END_MARKER}");' in script
    assert "  seterrorflag(0);" in script, "тело попадает в скрипт с отступом"
    assert f"  {DECOY_DESCRIPTOR_NAME} = br_result_1;" in script
    assert "if firststep then" not in script, (
        "тело скрипта страницы идёт в initialization: под firststep создавать "
        "объекты уже запрещено")


def test_page_script_uses_forward_slashes_and_refuses_quotes():
    from simintech_api.script_probe import build_page_script

    script = build_page_script("seterrorflag(0);", r"C:\out\r.txt", token="//TOK")
    assert 'createfile("C:/out/r.txt", -1)' in script

    with pytest.raises(ValueError):
        build_page_script("seterrorflag(0);", 'C:/out/кав"ычка.txt', token="//TOK")
```

- [ ] **Step 2: убедиться, что тест падает**

Run: `python3.11 -m pytest tests/unit/test_script_probe.py -q -k page_script`
Expected: FAIL — `ImportError: cannot import name 'PAGE_BEGIN_MARKER'`.

- [ ] **Step 3: реализовать**

Добавить в `simintech_api/script_probe.py` сразу после `build_probe_script`:

```python
#: Маркеры контура языкового слоя. От маркеров моста (`SCRIPT_BRIDGE_*`)
#: отличаются намеренно: там границу держит **проба**, здесь — скрипт страницы,
#: и по маркерам контур различает пять исходов
#: (`docs/superpowers/specs/2026-09-29-language-contour.md` §3). Смешать их
#: значило бы потерять это различие: у моста «нет конечного маркера» — отказ,
#: у контура — один из четырёх различимых исходов.
PAGE_BEGIN_MARKER = "CTX_BEGIN"
PAGE_END_MARKER = "CTX_END"


def build_page_script(body: str, result_path: str, token: str) -> str:
    """Собрать скрипт страницы: `initialization`, маркеры контура и тело.

    Тело исполняется в секции `initialization`, потому что создавать объекты
    разрешено только там (измерено 2026-09-28: во время расчёта среда отвечает
    «Установка блока на схему в процессе моделирования запрещена», а
    `createblock` возвращает 0).

    Метка (`token`) ставится **первой строкой**, до секции: она остаётся в
    скрипте, даже если тело не скомпилировалось, — а именно по ней мост
    опознаёт в выгрузке ту запись, которую изменил он сам, чтобы вернуть
    прежний скрипт (`find_changed_script_record`).

    Дескриптор результата недоступен телу по имени: он назван случайной частью
    метки (`bridge_descriptor_name`), а `fid` — приманка. Причина та же, что у
    `build_probe_script`: чужой код внутри тела (вендорская
    `export_1layer_topology`) присваивает `fid = createfile(...)` и увёл бы
    дескриптор контура вместе с его маркерами.

    Путь переводится в прямые слэши и не может содержать кавычку или перевод
    строки — он подставляется в литерал встроенного языка.
    """
    if '"' in result_path or "\n" in result_path or "\r" in result_path:
        raise ValueError(
            "путь результата не может содержать кавычку или перевод строки: "
            f"{result_path!r} — он подставляется в литерал встроенного языка")
    literal_path = result_path.replace("\\", "/")
    name = bridge_descriptor_name(token)
    indented = "".join(
        f"  {line}\n" for line in body.splitlines() if line.strip())
    return (
        f"{token}\n"
        "initialization\n"
        f"  var {name}: integer;\n"
        f"  var {DECOY_DESCRIPTOR_NAME}: integer;\n"
        f'  {name} = createfile("{literal_path}", -1);\n'
        f'  writelnutf8({name}, "{PAGE_BEGIN_MARKER}");\n'
        f"  {DECOY_DESCRIPTOR_NAME} = {name};\n"
        f"{indented}"
        f'  writelnutf8({name}, "{PAGE_END_MARKER}");\n'
        f"  freeobject({name});\n"
        "end;\n"
    )
```

- [ ] **Step 4: убедиться, что тест проходит**

Run: `python3.11 -m pytest tests/unit/test_script_probe.py -q -k page_script`
Expected: `2 passed`.

- [ ] **Step 5: коммит**

```bash
git add simintech_api/script_probe.py tests/unit/test_script_probe.py
git commit -m "feat(script): сборка скрипта страницы с маркерами контура"
```

---

## Задача 2: классификация исхода — пять состояний

**Files:**
- Modify: `simintech_api/script_probe.py` (после `classify_page_result`)
- Test: `tests/unit/test_script_probe.py`

- [ ] **Step 1: написать падающий тест**

```python
def test_classify_page_result_reads_five_outcomes():
    """Пять исходов различимы: успех, модель не считает, обрыв, не собрался, секция не шла."""
    from simintech_api.script_probe import (
        OUTCOME_ABORTED, OUTCOME_MODEL_NOT_RUNNING, OUTCOME_NOT_COMPILED,
        OUTCOME_OK, OUTCOME_SECTION_NOT_RUN, PAGE_BEGIN_MARKER,
        PAGE_END_MARKER, classify_page_result,
    )

    full = f"{PAGE_BEGIN_MARKER}\nСТРОКА_ТЕЛА\n{PAGE_END_MARKER}\n"
    aborted = f"{PAGE_BEGIN_MARKER}\nУСПЕЛО\n"

    ok = classify_page_result(full, time_grew=True)
    assert ok.kind == OUTCOME_OK
    assert ok.lines == ["СТРОКА_ТЕЛА"]

    stuck = classify_page_result(full, time_grew=False)
    assert stuck.kind == OUTCOME_MODEL_NOT_RUNNING
    assert stuck.lines == ["СТРОКА_ТЕЛА"]

    broken = classify_page_result(aborted, time_grew=False)
    assert broken.kind == OUTCOME_ABORTED
    assert broken.lines == ["УСПЕЛО"], "у обрыва видно, что успело записаться"

    not_compiled = classify_page_result("", time_grew=False)
    assert not_compiled.kind == OUTCOME_NOT_COMPILED
    assert not_compiled.lines == []

    section_skipped = classify_page_result("", time_grew=True)
    assert section_skipped.kind == OUTCOME_SECTION_NOT_RUN
```

- [ ] **Step 2: убедиться, что тест падает**

Run: `python3.11 -m pytest tests/unit/test_script_probe.py -q -k classify_page_result`
Expected: FAIL — `ImportError: cannot import name 'OUTCOME_OK'`.

- [ ] **Step 3: реализовать**

Добавить в `simintech_api/script_probe.py`:

```python
#: Исходы контура. Строки, а не перечисление: значение уходит в тексты ответов
#: и в тесты, где перечисление пришлось бы разворачивать обратно.
OUTCOME_OK = "ok"
OUTCOME_MODEL_NOT_RUNNING = "model-not-running"
OUTCOME_ABORTED = "aborted"
OUTCOME_NOT_COMPILED = "not-compiled"
OUTCOME_SECTION_NOT_RUN = "section-not-run"


class ContourOutcome(NamedTuple):
    """Разобранный исход контура.

    `kind` — один из `OUTCOME_*`; `lines` — строки тела между маркерами (у
    обрыва — то, что успело записаться; у «не собрался» и «секция не шла» —
    пусто: данных нет, а хранить их рядом с исходом — приглашение однажды ими
    воспользоваться).
    """

    kind: str
    lines: List[str]


def classify_page_result(text: str, *, time_grew: bool) -> ContourOutcome:
    """Классифицировать исход по файлу результата и росту времени.

    До этой функции мост различал только «есть ровно одна пара маркеров» или
    отказ, и два разных состояния — «скрипт не собрался» и «скрипт собрался, а
    модель не считает» — выглядели одинаково.

    Маркеры пишет **сам** скрипт страницы (`build_page_script`), поэтому:

    * начального маркера нет — секция `initialization` до исполнения не дошла.
      Если при этом время росло, расчёт шёл, а секция не выполнилась (редкий
      случай: сообщаем как есть); если не росло — вероятнее всего скрипт не
      скомпилировался, и это единственный различимый признак, потому что
      ошибок компиляции через COM не видно;
    * начальный есть, конечного нет — тело оборвалось на исполнении (ошибка
      времени выполнения молча прекращает скрипт);
    * оба есть — тело дошло до конца; исход зависит от того, пошёл ли расчёт.
    """
    lines = text.splitlines()
    begins = [index for index, line in enumerate(lines)
              if line == PAGE_BEGIN_MARKER]
    if not begins:
        kind = OUTCOME_SECTION_NOT_RUN if time_grew else OUTCOME_NOT_COMPILED
        return ContourOutcome(kind=kind, lines=[])
    start = begins[0]
    ends = [index for index, line in enumerate(lines)
            if line == PAGE_END_MARKER and index > start]
    if not ends:
        return ContourOutcome(kind=OUTCOME_ABORTED, lines=lines[start + 1:])
    kind = OUTCOME_OK if time_grew else OUTCOME_MODEL_NOT_RUNNING
    return ContourOutcome(kind=kind, lines=lines[start + 1:ends[0]])
```

- [ ] **Step 4: убедиться, что тест проходит**

Run: `python3.11 -m pytest tests/unit/test_script_probe.py -q`
Expected: все тесты файла зелёные.

- [ ] **Step 5: коммит**

```bash
git add simintech_api/script_probe.py tests/unit/test_script_probe.py
git commit -m "feat(script): пять исходов контура — классификация по маркерам и времени"
```

---

## Задача 3: рефакторинг моста — поведение не меняется

**Files:**
- Modify: `simintech_api/core/script_bridge.py`
- Test: `tests/unit/test_script_bridge.py` (существующие тесты — защита от регрессии)

Задача меняет устройство, а не поведение: весь существующий набор обязан
остаться зелёным без правок. Ломать его нельзя — на нём стоят замеры возврата
скрипта.

- [ ] **Step 1: зафиксировать зелёный набор до правок**

Run: `python3.11 -m pytest tests/unit/test_script_bridge.py -q`
Expected: все тесты проходят; запомнить число.

- [ ] **Step 2: выделить преамбулу `_prepare`**

Перенести в новый приватный метод начало `run_probe` **дословно** (строки с
`_refuse_if_calculating()`, `GetCurentPage`, первый снимок, проверку метки):

```python
    def _prepare(self) -> Tuple[int, List[str], str]:
        """Преамбула: отказ на идущем расчёте, страница, снимок, метка.

        Стоит до любых изменений в проекте, и это её главное свойство: сбой
        здесь означает «проба не начата, проект не тронут» — утверждение,
        которое обязано дойти до вызывающего дословно.
        """
        self._refuse_if_calculating()
        try:
            target_page_id = int(self._client.call("GetCurentPage",
                                                   self._project_id))
        except ScriptBridgeError:
            raise
        except BaseException as exc:                              # noqa: BLE001
            raise ScriptBridgeError(
                f"не удалось определить текущую страницу проекта ({exc}). "
                "Проба не начата, проект не тронут.") from exc
        try:
            before = self._dump_records()
        except ScriptBridgeError:
            raise
        except BaseException as exc:                              # noqa: BLE001
            raise ScriptBridgeError(
                "не удалось снять снимок скриптовых записей проекта "
                f"({exc}). Проба не начата, проект не тронут.") from exc
        token = new_target_token()
        if token_present_in(before, TARGET_TOKEN_PREFIX):
            raise ScriptBridgeUnsafeStateError(
                "в скриптовых записях проекта уже есть метка моста: значит, в "
                "проекте остался пробный скрипт предыдущего запуска (возврат "
                "тогда не прошёл либо его не было вовсе). Проба не начата, "
                "проект не тронут. Номеров страниц в выгрузке нет, поэтому "
                "какой именно странице принадлежит метка — по ней не "
                "определить: проверьте скрипты страниц проекта.")
        return target_page_id, before, token
```

- [ ] **Step 3: выделить исполнение `_execute_installed`**

Перенести **дословно** в новый приватный метод блок `run_probe`, начинавшийся
с `target = None` и заканчивавшийся `return result`, заменив сборку скрипта на
параметр `script`. Возвращать нужно и текст результата, и прежний скрипт:

```python
class InstalledRun(NamedTuple):
    """Результат установки и прогона готового скрипта.

    `text` — сырой текст файла результата (разбор у вызывающего: мосту нужна
    пара маркеров как признак, контуру — маркеры контура и частичные данные
    обрыва). `restored_script` — прежний скрипт страницы, возвращённый на место.
    """

    text: str
    restored_script: str


    def _execute_installed(self, script: str, result_path: Path, token: str,
                           target_page_id: int,
                           before: List[str]) -> InstalledRun:
        """Поставить готовый скрипт, посчитать, вернуть прежний, прочитать файл."""
```

Внутри — существующий код (строки 227–315 исходного `run_probe`) с тремя
заменами: скрипт приходит параметром, запуск идёт через `_try_start_and_wait`
(шаг 4), результат читается сырым текстом (шаг 5). Комментарии переносятся
**дословно**: в этом файле они объясняют «почему» и несут основную нагрузку.

```python
    def _execute_installed(self, script: str, result_path: Path, token: str,
                           target_page_id: int, before: List[str], *,
                           time_growth_is_an_error: bool = True) -> InstalledRun:
        """Поставить готовый скрипт, посчитать, вернуть прежний, прочитать файл.

        `time_growth_is_an_error` — как понимать неподвижное время. Мост
        (`run_probe`) на нём отказывает: он не умеет отличить «скрипт не
        собрался» от «модель не считает». Контур передаёт `False` и получает
        ответ в `self._last_time_grew`, чтобы классифицировать исход по маркерам.
        """
        target = None
        original = None
        probe_error = None
        calculation_started = False
        self._last_time_grew = False
        text = ""
        try:
            try:
                self.install_script(script)
            except BaseException as exc:                          # noqa: BLE001
                # Вызов мог примениться и упасть уже после применения (таймаут
                # на отпущенном COM-вызове), поэтому «не установлено» здесь —
                # догадка: состояние берём из свежего снимка.
                raise self._unsafe(
                    f"не удалось установить пробу: {exc}.",
                    self._records_or_none(), token,
                    snapshot_proves_absence=False) from exc
            try:
                after = self._dump_records()
            except BaseException as exc:                          # noqa: BLE001
                raise self._unsafe(
                    "не удалось снять снимок скриптовых записей после "
                    f"установки пробы: {exc}.",
                    self._records_or_none(), token,
                    snapshot_proves_absence=False) from exc
            try:
                target = find_changed_script_record(before, after, token)
            except ScriptBridgeUnsafeStateError as exc:
                # Отказ приходит из чистой функции, которая о состоянии проекта
                # знать не может, а знать его обязан: проба к этому моменту уже
                # стоит в текущей странице, и молчание об этом оставило бы
                # пользователя с испорченной страницей и без предупреждения.
                raise self._unsafe(f"{exc}", after, token,
                                   snapshot_proves_absence=False) from exc
            raw_original = before[target]
            if leftover_of(raw_original):
                raise self._unsafe(
                    f"скриптовая запись {target} содержит нераспознанный текст "
                    "выгрузки: восстановление небезопасно — кодек покрывает не "
                    "весь текст, и на место вернулся бы усечённый скрипт.",
                    after, token)
            try:
                original = decode_xprt_value(raw_original)
            except ScriptBridgeError as exc:
                raise self._unsafe(
                    f"скриптовая запись {target} не разбирается: {exc}.",
                    after, token) from exc
            try:
                result_path.unlink(missing_ok=True)
            except OSError as exc:
                # Тот же инвариант: сбой файловой системы не должен выглядеть
                # сбоем среды. Проба к этому моменту уже стоит, поэтому
                # сообщение называет состояние прямо — уборку делает `finally`.
                raise ScriptBridgeError(
                    f"не удалось удалить прежний файл результата "
                    f"{result_path} ({exc}). Проба установлена, расчёт ещё не "
                    "запущен; остановка и возврат скрипта выполняются, но "
                    "старый файл результата надо удалить вручную.") from exc
            # С этого момента расчёт запущен нами, и вернуть проект в
            # «остановлен» обязана проба — на любом пути, включая тот, где сам
            # ProjectStart бросил (тогда состояние неизвестно, но остановка
            # безвредна в любом измеренном состоянии).
            calculation_started = True
            if time_growth_is_an_error:
                self._start_and_wait()
                self._last_time_grew = True
            else:
                self._last_time_grew = self._try_start_and_wait()
            text = self._read_result_text(result_path)
        except BaseException as exc:                              # noqa: BLE001
            probe_error = exc
            raise
        finally:
            # Остановка идёт ПЕРВОЙ и в своей изоляции: при state=0 не запрещена
            # ни одна измеренная операция, поэтому возврат скрипта исполняется
            # на заведомо разрешённом состоянии. Порядок обязателен и в обратную
            # сторону: сбой возврата не отменяет остановку, сбой остановки не
            # отменяет возврат — иначе проект остаётся инициализированным ровно
            # там, где пользователь не поправит его и руками.
            stop_problem = self._stop_calculation(calculation_started)
            restore_problem = None
            if target is not None and original is not None:
                try:
                    self._restore_script(before, target, original,
                                         target_page_id, token, probe_error)
                except ScriptBridgeUnsafeStateError as exc:
                    restore_problem = exc
            if restore_problem is not None:
                if stop_problem is not None:
                    # Уровни не смешиваются: первичная причина (потеря скрипта)
                    # остаётся началом текста, сбой режима дописывается —
                    # и наоборот, сбой остановки не выдаётся за потерю скрипта.
                    restore_problem = ScriptBridgeUnsafeStateError(
                        f"{restore_problem} Дополнительно: {stop_problem}")
                raise restore_problem
            if stop_problem is not None:
                raise self._unsafe(stop_problem, self._records_or_none(), token,
                                   probe_error=probe_error)
        return InstalledRun(
            text=text,
            restored_script=original if original is not None else "")
```

- [ ] **Step 4: разложить ожидание роста времени**

Разделить `_start_and_wait` на «данные» и «отказ», не меняя ни одного текста
отказа:

```python
    def _try_start_and_wait(self) -> bool:
        """Запустить расчёт и вернуть, сдвинулось ли модельное время.

        `False` — **признак, а не диагноз**: так выглядят и скрипт, который не
        собрался (среда молчит), и модель, которая структурно не считает
        (неподключённый вход останавливает расчёт всей модели). Мост на этом
        отказывает (`_start_and_wait`), контур — различает по маркерам.
        """
        self._client.call("ProjectStart", self._project_id)
        initial_time = float(self._client.call("GetProjectTime", self._project_id))
        deadline = time.monotonic() + self._time_growth_timeout_s
        while True:
            self._client.call("ProjectStep", self._project_id)
            current_time = float(self._client.call("GetProjectTime", self._project_id))
            if current_time > initial_time:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)

    def _start_and_wait(self) -> None:
        """То же, но неподвижное время — отказ (поведение моста до контура)."""
        if self._try_start_and_wait():
            return
        raise ScriptBridgeError(
            "расчёт не подтвердил рост модельного времени за "
            f"{self._time_growth_timeout_s:g} с. По этому признаку "
            "причину определить нельзя: так выглядят и скрипт, "
            "который не собрался (среда об этом молчит), и модель, "
            "которая структурно не считает — например, блок с "
            "неподключённым входом останавливает расчёт всей модели. "
            "Проверьте и скрипт, и соединения модели.")
```

- [ ] **Step 5: разложить чтение файла результата**

```python
    def _read_result_text(self, result_path: Path) -> str:
        """Прочитать файл результата **сырым** текстом.

        Разбор у вызывающего: мосту нужна пара маркеров как признак, контуру —
        маркеры контура и то, что успело записаться при обрыве.
        """
        if not result_path.exists():
            raise ScriptBridgeError(
                "скрипт не создал файл результата: расчёт шёл, но скрипт "
                f"оборвался до записи в {result_path}. Ошибка времени "
                "выполнения прерывает скрипт молча, поэтому причину придётся "
                "искать по телу пробы.")
        try:
            return result_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ScriptBridgeError(
                f"файл результата не читается как UTF-8: {exc}. Скрипт пишет "
                "через writelnutf8, поэтому испорченный файл означает потерю "
                "данных — подставлять замены вместо символов нельзя.") from exc

    def _read_result(self, result_path: Path) -> ProbeResult:
        """Прочитать файл и потребовать ровно одну пару маркеров моста."""
        result = parse_probe_result(self._read_result_text(result_path))
        if not result.complete:
            raise ScriptBridgeError(
                "в результате нет ровно одной пары маркеров начала и конца: "
                "скрипт оборвался или записал маркер сам. Данные неполны или "
                "неоднозначны — как результат их использовать нельзя.")
        return result
```

- [ ] **Step 6: `run_probe` становится коротким**

```python
    def run_probe(self, body: str, result_path: Path) -> ProbeResult:
        """Выполнить `body` в проекте и вернуть разобранный результат.

        <существующий докстринг с шестью шагами сохраняется без изменений>
        """
        target_page_id, before, token = self._prepare()
        script = build_probe_script(body, str(result_path), token=token)
        run = self._execute_installed(script, result_path, token,
                                      target_page_id, before)
        return self._require_marker_pair(run.text)

    @staticmethod
    def _require_marker_pair(text: str) -> ProbeResult:
        """Потребовать ровно одну пару маркеров моста — прежнее поведение.

        Текст отказа обязан совпасть с прежним дословно: на нём стоят тесты и
        обещания вызывающему.
        """
        result = parse_probe_result(text)
        if not result.complete:
            raise ScriptBridgeError(
                "в результате нет ровно одной пары маркеров начала и конца: "
                "скрипт оборвался или записал маркер сам. Данные неполны или "
                "неоднозначны — как результат их использовать нельзя.")
        return result
```

(Проверку из старого `_read_result` переносим в `_require_marker_pair`
дословно, а `_read_result` после этого не нужен — он удаляется.)

- [ ] **Step 7: прогнать весь набор моста**

Run: `python3.11 -m pytest tests/unit/test_script_bridge.py -q`
Expected: **то же число тестов, все зелёные**, ни один текст отказа не изменён.

- [ ] **Step 8: коммит**

```bash
git add simintech_api/core/script_bridge.py
git commit -m "refactor(bridge): преамбула, исполнение и рост времени — разделены"
```

---

## Задача 4: `run_page_script` — второй режим моста

**Files:**
- Modify: `simintech_api/core/script_bridge.py`
- Test: `tests/unit/test_script_bridge.py`

- [ ] **Step 1: добавить в подделку `raw_result`**

В `FakeEnv.__init__` — параметр и поле:

```python
                 raw_result=None):
        ...
        #: Текст, которым подделка **дословно** заполняет файл результата.
        #: Нужен контуру: его маркеры (`CTX_*`) пишет сам скрипт, а подделка по
        #: умолчанию пишет маркеры моста.
        self.raw_result = raw_result
```

и в `_maybe_write_result` первой строкой:

```python
        if self.raw_result is not None:
            if self.writes_result and "createfile(" in self.scripts[self.current_index]:
                start = self.scripts[self.current_index].index('createfile("') + len('createfile("')
                end = self.scripts[self.current_index].index('"', start)
                Path(self.scripts[self.current_index][start:end]).write_text(
                    self.raw_result, encoding="utf-8")
            return
```

- [ ] **Step 2: написать падающие тесты**

```python
def test_run_page_script_reports_success_and_returns_previous_script(tmp_path):
    """Успех: маркеры контура и рост времени; прежний скрипт возвращён."""
    from simintech_api.script_probe import OUTCOME_OK, PAGE_BEGIN_MARKER, PAGE_END_MARKER

    env, bridge = _bridge(raw_result=f"{PAGE_BEGIN_MARKER}\nСТРОКА\n{PAGE_END_MARKER}\n")
    result = bridge.run_page_script("seterrorflag(0);", tmp_path / "r.txt")

    assert result.outcome.kind == OUTCOME_OK
    assert result.outcome.lines == ["СТРОКА"]
    assert result.restored_script == "seterrorflag(0);"


def test_run_page_script_distinguishes_not_compiled_from_stuck_model(tmp_path):
    """Без начального маркера: время стоит — «не собрался», время растёт — «секция не шла»."""
    from simintech_api.script_probe import OUTCOME_NOT_COMPILED, OUTCOME_SECTION_NOT_RUN

    env, bridge = _bridge(time_grows=False, raw_result="")
    assert bridge.run_page_script("x();", tmp_path / "a.txt").outcome.kind == OUTCOME_NOT_COMPILED

    env, bridge = _bridge(time_grows=True, raw_result="")
    assert bridge.run_page_script("x();", tmp_path / "b.txt").outcome.kind == OUTCOME_SECTION_NOT_RUN


def test_run_page_script_reports_abort_with_what_was_written(tmp_path):
    """Обрыв: начальный маркер есть, конечного нет — видны успевшие строки."""
    from simintech_api.script_probe import OUTCOME_ABORTED, PAGE_BEGIN_MARKER

    env, bridge = _bridge(raw_result=f"{PAGE_BEGIN_MARKER}\nУСПЕЛО\n")
    result = bridge.run_page_script("x();", tmp_path / "c.txt")

    assert result.outcome.kind == OUTCOME_ABORTED
    assert result.outcome.lines == ["УСПЕЛО"]


def test_run_page_script_keeps_model_stuck_separate_from_success(tmp_path):
    """Маркеры на месте, время стоит — «модель не считает», а не успех."""
    from simintech_api.script_probe import (
        OUTCOME_MODEL_NOT_RUNNING, PAGE_BEGIN_MARKER, PAGE_END_MARKER,
    )

    env, bridge = _bridge(time_grows=False,
                          raw_result=f"{PAGE_BEGIN_MARKER}\nA\n{PAGE_END_MARKER}\n")
    result = bridge.run_page_script("x();", tmp_path / "d.txt")

    assert result.outcome.kind == OUTCOME_MODEL_NOT_RUNNING
    assert result.outcome.lines == ["A"]
```

- [ ] **Step 3: убедиться, что тесты падают**

Run: `python3.11 -m pytest tests/unit/test_script_bridge.py -q -k run_page_script`
Expected: FAIL — `AttributeError: 'ScriptBridge' object has no attribute 'run_page_script'`.

- [ ] **Step 4: реализовать**

```python
class PageRunResult(NamedTuple):
    """Результат прогона тела в секции `initialization`.

    `outcome` — исход (`ContourOutcome`), `restored_script` — прежний скрипт
    страницы, возвращённый на место. Оба поля обязательны: контур обещает и
    диагностику, и возврат.
    """

    outcome: ContourOutcome
    restored_script: str


    def run_page_script(self, body: str, result_path: Path) -> PageRunResult:
        """Выполнить `body` в секции `initialization` и классифицировать исход.

        Отличие от `run_probe` — где исполняется тело. Проба идёт под
        `if firststep then`, потому что на инициализации порты субмоделей могут
        быть ещё не установлены; здесь тело идёт **в `initialization`**, потому
        что только там разрешено создавать объекты (`createmodel`,
        `createprimitiv`).

        Неподвижное время — не отказ, а исход: мост на нём останавливался,
        потому что не умел отличить «скрипт не собрался» от «модель не
        считает»; контур отличает их по маркерам и сообщает, что именно
        увидел.
        """
        target_page_id, before, token = self._prepare()
        script = build_page_script(body, str(result_path), token=token)
        run = self._execute_installed(script, result_path, token,
                                      target_page_id, before,
                                      time_growth_is_an_error=False)
        outcome = classify_page_result(run.text, time_grew=self._last_time_grew)
        return PageRunResult(outcome=outcome, restored_script=run.restored_script)
```

`self._last_time_grew` — поле, которое `_execute_installed` выставляет при
`time_growth_is_an_error=False` (в конструкторе инициализируется `False`).
Записывать его в конструкторе обязательно, иначе mypy (strict) не пропустит
обращение к необъявленному атрибуту.

Импорты в шапке файла дополнить: `PageRunResult` не импортируется — он
определён здесь; из `..script_probe` добавить `ContourOutcome`,
`build_page_script`, `classify_page_result`, `parse_probe_result`.

- [ ] **Step 5: прогнать тесты**

Run: `python3.11 -m pytest tests/unit/test_script_bridge.py tests/unit/test_script_probe.py -q`
Expected: все зелёные.

- [ ] **Step 6: коммит**

```bash
git add simintech_api/core/script_bridge.py tests/unit/test_script_bridge.py
git commit -m "feat(bridge): run_page_script — тело в initialization и пять исходов"
```

---

## Задача 5: сборщики тел трёх операций

**Files:**
- Create: `simintech_api/model_operations.py`
- Modify: `pyproject.toml` (список `[tool.mypy] files`)
- Test: `tests/unit/test_model_operations.py`

- [ ] **Step 1: написать падающий тест**

```python
"""Тела трёх операций языкового слоя — чистые строки без COM."""

from __future__ import annotations

from simintech_api.model_operations import (
    build_export_model_text_body,
    build_import_model_text_body,
    build_inject_submodel_script_body,
    to_language_literal,
)


def test_literal_escapes_quotes_and_newlines_the_measured_way():
    """Кавычка — через chr(34), перевод строки — через CLRF.

    Измерено 2026-09-29: удвоение `""` в этой сборке даёт пустую строку, а
    обратный слэш не экранирует; рабочая форма — chr(34). Переводы строк
    задаются константой CLRF.
    """
    literal = to_language_literal('type = "Усилитель"\nконец')

    assert literal == '"type = " + chr(34) + "Усилитель" + CLRF + "конец"'


def test_export_body_names_the_artifact_path():
    body = build_export_model_text_body("C:/out/model.txt")
    assert body == 'savemodeltofile(getcurrentprojectid, "C:/out/model.txt");'


def test_import_body_declares_model_as_const_and_calls_createmodel():
    body = build_import_model_text_body('block0: (type = "Ступенька")')

    assert body.startswith("const model : (")
    assert "createmodel(getcurrentprojectid, model);" in body


def test_inject_body_creates_submodel_assigns_script_and_reinits():
    """Рецепт измерен 2026-09-29: без reinitsubmodel скрипт не компилируется."""
    body = build_inject_submodel_script_body(
        "inj_result = createfile(\"C:/out/data.txt\", -1);", submodel_code=102)

    assert "createprimitiv(102," in body
    assert 'setprop(objid, "script",' in body
    assert body.index("reinitsubmodel(objid);") > body.index('setprop(objid, "script"')
```

- [ ] **Step 2: убедиться, что тесты падают**

Run: `python3.11 -m pytest tests/unit/test_model_operations.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'simintech_api.model_operations'`.

- [ ] **Step 3: реализовать**

Создать `simintech_api/model_operations.py`:

```python
"""Тела операций языкового слоя — сборка строк встроенного языка, без COM.

Здесь только текст: как собрать скрипт для выгрузки модели, её загрузки и
инжектирования субмодели. Доставка и проверка — `core/script_bridge.py`
(`run_page_script`), разбор исхода — `script_probe.classify_page_result`.

Правила экранирования измерены 2026-09-29 на поставке 2.26.6.23:
кавычка задаётся `chr(34)` (удвоение `""` даёт пустую строку, обратный слэш не
экранирует), перевод строки — константой `CLRF`.
"""

from __future__ import annotations

#: Код типа объекта «Субмодель» в `createprimitiv` (`otSubModel`).
SUBMODEL_OBJECT_CODE = 102

#: Точки пустой субмодели — те же, что в демонстрационном примере вендора.
EMPTY_SUBMODEL_POINTS = "[(0, 0), (-16, 0), (0, -16), (0, 16)]"


def to_language_literal(text: str) -> str:
    """Собрать строковый литерал встроенного языка из произвольного текста.

    Кавычка внутри литерала недопустима как есть, поэтому текст режется по
    кавычкам, а сами кавычки подставляются `chr(34)`. Перевод строки — `CLRF`:
    строковый литерал в языке не может занимать несколько строк.

    Пустые куски выбрасываются: `"" + ...` язык примет, но лишние склейки
    прячут настоящую длину выражения при отладке.
    """
    chunks: list[str] = []
    for line_index, line in enumerate(text.split("\n")):
        if line_index:
            chunks.append("CLRF")
        for piece_index, piece in enumerate(line.split('"')):
            if piece_index:
                chunks.append("chr(34)")
            if piece:
                chunks.append(f'"{piece}"')
    return " + ".join(chunks)


def build_export_model_text_body(artifact_path: str) -> str:
    """Тело выгрузки модели: `savemodeltofile` в файл-артефакт."""
    return f'savemodeltofile(getcurrentprojectid, "{_path(artifact_path)}");'


def build_import_model_text_body(model_text: str) -> str:
    """Тело загрузки модели: объявление кортежа и `createmodel`.

    Форма взята из демонстрационных проектов вендора (`const model : ( … );`) —
    это не строка, а запись языка, введённая в текст скрипта.
    """
    return f"const model : (\n{model_text}\n);\ncreatemodel(getcurrentprojectid, model);"


def build_inject_submodel_script_body(injected_script: str,
                                      submodel_code: int = SUBMODEL_OBJECT_CODE) -> str:
    """Тело инжектирования: пустая субмодель + присвоенный скрипт + переинициализация.

    Порядок обязателен и измерен 2026-09-29: без `reinitsubmodel` присвоенный
    скрипт **не компилируется**, и снаружи это выглядит как «присвоили — и
    ничего не происходит», без сообщений.
    """
    return (
        f"objid = createprimitiv({submodel_code}, {EMPTY_SUBMODEL_POINTS});\n"
        f'setprop(objid, "script", {to_language_literal(injected_script)});\n'
        "reinitsubmodel(objid);"
    )


def _path(path: str) -> str:
    """Путь внутри литерала: прямые слэши, без кавычек и переводов строки."""
    if '"' in path or "\n" in path or "\r" in path:
        raise ValueError(
            f"путь не может содержать кавычку или перевод строки: {path!r}")
    return path.replace("\\", "/")
```

**Проверить на живом языке:** `to_language_literal` — единственная функция,
чей результат уходит в компилятор как есть; её форма (`"a" + chr(34) + "b"`)
совпадает с той, что мы писали руками в пробах (`probe-inject8/9/10`) и которая
исполнялась. Если тест `test_literal_escapes_quotes_and_newlines_the_measured_way`
даст другую строку — привести ожидание теста к фактическому выводу и записать
расхождение в `docs/evidence/claims.yaml` (утверждение ниже).

- [ ] **Step 4: добавить модуль в mypy-гейт**

В `pyproject.toml`, в список `[tool.mypy] files`, вставить по алфавиту:

```toml
    "simintech_api/model_operations.py",
```

Run: `python3.11 -m mypy` — должно быть чисто (модуль без COM, аннотации полные).

- [ ] **Step 5: прогнать тесты**

Run: `python3.11 -m pytest tests/unit/test_model_operations.py -q`
Expected: все зелёные.

- [ ] **Step 6: коммит**

```bash
git add simintech_api/model_operations.py tests/unit/test_model_operations.py pyproject.toml
git commit -m "feat(model-text): тела трёх операций языкового слоя"
```

---

## Задача 6: живой прогон

**Files:**
- Create: `tests/integration/test_language_contour_live.py`

Живой тест — единственное доказательство, что контур работает на поставке; в CI
он не идёт (маркер `integration`), запускается вручную на Windows.

- [ ] **Step 1: написать тест**

```python
"""Живой прогон контура: тело в initialization и возврат прежнего скрипта.

Запуск (Windows, из WSL — через Windows-Python):

    cd /mnt/c/git/simintech-code && PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 \
      python.exe -m pytest tests/integration/test_language_contour_live.py \
      -m integration --run-simintech -q

Измерено (2026-09-29, поставка 2.26.6.23): создание объектов работает только в
`initialization`, `run_probe` для этого не годится (тело под `if firststep then`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from simintech_api.core.project import Project
from simintech_api.core.script_bridge import ScriptBridge
from simintech_api.script_probe import OUTCOME_OK

pytestmark = pytest.mark.integration


def test_body_runs_in_initialization_and_previous_script_returns(
        client, tmp_path: Path) -> None:
    project = Project.from_template(client)
    bridge = ScriptBridge(client, project.id)
    body = (
        'f = createfile("' + str(tmp_path / "contour.txt").replace("\\", "/")
        + '", -1);\n'
        'writelnutf8(f, "МОДЕЛЬ СОБРАНА");\n'
        "freeobject(f);"
    )

    result = bridge.run_page_script(body, tmp_path / "result.txt")

    assert result.outcome.kind == OUTCOME_OK, result.outcome
    assert (tmp_path / "contour.txt").read_text(encoding="utf-8").strip() == (
        "МОДЕЛЬ СОБРАНА")
    assert result.restored_script == "", (
        "у проекта из шаблона скрипта страницы не было — возврат обязан "
        "вернуть пустой скрипт, а не оставить тело контура в проекте")
```

- [ ] **Step 2: прогнать живьём**

```bash
cd /mnt/c/git/simintech-code && PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 \
  /mnt/c/Users/a-savchenko/AppData/Local/Programs/Python/Python311/python.exe \
  -m pytest tests/integration/test_language_contour_live.py -m integration \
  --run-simintech -q > /tmp/contour-live.txt 2>&1; tail -20 /tmp/contour-live.txt
```

Expected: `1 passed`. Вывод — в файл, а не в конвейер: при снятии по таймауту
конвейер теряет вывод целиком.

- [ ] **Step 3: зафиксировать факт прогона**

Записать в `docs/evidence/claims.yaml` (см. задачу 7) дату, стенд и результат:
«живой прогон 2026-09-29, поставка 2.26.6.23 — 1 passed».

- [ ] **Step 4: коммит**

```bash
git add tests/integration/test_language_contour_live.py
git commit -m "test(live): контур — тело в initialization и возврат скрипта"
```

---

## Задача 7: документация, утверждение, версия

**Files:**
- Modify: `docs/evidence/claims.yaml`, `docs/evidence/verification-matrix.md`,
  `docs/knowledge-snapshot.md`, `docs/api.md`, `simintech_api/__init__.py`

- [ ] **Step 1: добавить утверждения в реестр**

Дописать в `docs/evidence/claims.yaml` **два** утверждения:

```yaml
- id: page-script-runs-in-initialization
  claim: "Тело, поставленное скриптом страницы, исполняется в секции `initialization`, и по маркерам `CTX_BEGIN`/`CTX_END` исход различается на пять состояний"
  status: measured
  source:
    type: live-com
    ref: "docs/superpowers/specs/2026-09-29-language-contour.md §3"
    product_version: "SimInTech64, поставка 2.26.6.23"
    observed_at: 2026-09-29
  evidence: "Маркер `CTX_BEGIN` пишется до тела, `CTX_END` — после: наличие первого без второго означает обрыв на исполнении, отсутствие обоих при неподвижном времени — что скрипт не скомпилировался. Живой прогон `tests/integration/test_language_contour_live.py`"
  tests:
    - file: tests/integration/test_language_contour_live.py
      id: test_body_runs_in_initialization_and_previous_script_returns
      kind: live

- id: language-literal-uses-chr34-and-clrf
  claim: "Строковый литерал встроенного языка собирается через `chr(34)` для кавычки и `CLRF` для перевода строки; удвоение кавычки даёт пустую строку, обратный слэш не экранирует"
  status: measured
  source:
    type: live-com
    ref: "docs/superpowers/specs/2026-09-29-language-contour.md §3"
    product_version: "SimInTech64, поставка 2.26.6.23"
    observed_at: 2026-09-29
  evidence: "Замеры 2026-09-28/29: текст модели с `chr(34)` принимается, тот же текст с удвоением — нет; в пробах инжектирования литерал собирался этой же формой и исполнялся"
  tests:
    - file: tests/unit/test_model_operations.py
      id: test_literal_escapes_quotes_and_newlines_the_measured_way
      kind: unit
```

- [ ] **Step 2: перегенерировать матрицу**

Run: `python3.11 scripts/evidence.py`
Expected: «Реестр цел: утверждений 45; матрица обновлена.»

- [ ] **Step 3: обновить снапшот знаний**

В `docs/knowledge-snapshot.md` — число утверждений и диапазон дат:

```markdown
| `docs/evidence/claims.yaml` | 45 утверждений о поведении среды | SimInTech64 2.26.6.23 | 2026-09-10 … 2026-09-29 | `scripts/evidence.py` + `tests/unit/test_evidence.py` |
```

- [ ] **Step 4: описать в `docs/api.md`**

Добавить раздел после описания `ScriptBridge`:

````markdown
### run_page_script

`ScriptBridge.run_page_script(body, result_path) -> PageRunResult` — выполнить
тело в секции `initialization` скрипта текущей страницы и классифицировать
исход. Отличие от `run_probe`: проба идёт под `if firststep then` (там порты
субмоделей уже установлены), а этот режим — в `initialization`, потому что
только там разрешено создавать объекты.

```python
bridge = ScriptBridge(client, project.id)
result = bridge.run_page_script(
    'const model : (block0: (type = "Ступенька", points=[(0, 0)]));\n'
    "createmodel(getcurrentprojectid, model);",
    Path("C:/out/result.txt"))
print(result.outcome.kind)      # ok | model-not-running | aborted | not-compiled | section-not-run
print(result.restored_script)   # прежний скрипт страницы, возвращённый на место
```
````

- [ ] **Step 5: журнал версий и экспорт**

В `simintech_api/__init__.py`:

```python
#: 0.9.0: минорный — контур языкового слоя: `ScriptBridge.run_page_script`,
#: `PageRunResult`, пять исходов (`OUTCOME_*`) и классификатор
#: `classify_page_result`; тела операций — `model_operations`. Существующие
#: методы и тексты их отказов не изменились.
```

и `__version__ = "0.9.0"`, в `__all__` добавить `PageRunResult`, `OUTCOME_OK`,
`OUTCOME_MODEL_NOT_RUNNING`, `OUTCOME_ABORTED`, `OUTCOME_NOT_COMPILED`,
`OUTCOME_SECTION_NOT_RUN`, `classify_page_result`.

- [ ] **Step 6: прогнать гейты**

```bash
python3.11 -m pytest tests/unit -q
python3.11 -m flake8
python3.11 -m mypy
python3.11 -m mypy --platform win32
python3.11 scripts/public_data_check.py
```

Expected: тесты зелёные, flake8/mypy/DLP чисто.

- [ ] **Step 7: коммит и PR**

```bash
git add -A
git commit -m "docs(evidence): утверждения контура и версия 0.9.0"
git push -u origin feat/language-contour-pr1
gh pr create --base main --head feat/language-contour-pr1 \
  --title "feat(bridge): контур языкового слоя — run_page_script и пять исходов" \
  --body-file .github/pull_request_template.md
```

В теле PR: ссылка на спецификацию, число тестов, факт живого прогона (задача 6),
закрываемые задачи `simintech-mcp` #12/#13 и `simintech-code` #12.

---

## Что войдёт в PR-2 и PR-3 (отдельные планы)

**PR-2, `simintech-mcp`:** пять инструментов поверх `run_page_script`
(`get_page_script`, `set_page_script`, `import_model_text`,
`inject_submodel_script`, `run_page_script`) и перевод существующего
`export_model_text` на библиотечную механику; строка в README и имена в
`test_surface`; поведенческие тесты на подделке моста; **поднятие пина
`simintech-api`** на коммит PR-1; пример `docs/examples/language-contour.md`
(сценарий для агента с численной приёмкой, четыре падающих случая, отложенное).

**PR-3, `simintech-skill`:** знание агента — пять исходов и что делать в каждом,
порядок шагов задания, правила языка (создание только в `initialization`,
`chr(34)`, обязательный `reinitsubmodel`, `removeprimitiv` не трогать),
указатель на пример.

## Гейты и красные флаги

- Любой текст отказа, существующий до PR-1, остаётся дословно тем же: на нём
  стоят тесты и обещания вызывающему.
- Задача 3 (рефакторинг) идёт **под зелёным набором**; если после неё число
  тестов изменилось — правка неверна.
- Ни одного нового параметра, задающего число COM-вызовов, в PR-1 не
  появляется: число шагов внутри `_try_start_and_wait` задано существующим
  таймаутом.
