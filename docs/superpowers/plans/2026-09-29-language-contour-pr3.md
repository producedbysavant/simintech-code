# План реализации: контур языкового слоя — PR-3 «знание агента» (`simintech-skill`)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** научить агента пользоваться контуром: пять исходов и что делать в
каждом, порядок шагов задания, правила языка, указатель на пример — и убрать из
скиллов то, что контур уже опроверг.

**Architecture:** правки только в текстах знаний (`skills-catalog/**/SKILL.md`,
`manifest.yaml`) и в тестах, которые держат знание привязанным к машинным
источникам (`tests/unit/test_skills_catalog.py`). Новых скиллов не появляется:
контур — продолжение `simintech-language-core`.

**Tech Stack:** Python 3.11, pytest, PyYAML, flake8. Пакета-кода в репозитории
нет: в колесо кладётся только `skills-catalog/`.

Спецификация: `simintech-code`, `docs/superpowers/specs/2026-09-29-language-contour.md` §6.3.
План PR-2: `simintech-code`, `docs/superpowers/plans/2026-09-29-language-contour-pr2.md`.

---

## Предусловия (проверить фактом)

```bash
cd /mnt/c/git/simintech-skill && git fetch origin && git log --oneline -1 origin/main
cd /mnt/c/git/simintech-skill && git show origin/main:skills-catalog/simintech-language-core/SKILL.md | grep -c "инжектирование"
```

| Что | Почему |
|---|---|
| PR #10 (`simintech-skill`, ветка `feat/language-submodel-script`) влит | разделы про субмодель и обход контейнеров — база, на которую опирается раздел о контуре; одновременно это последний известный текст скилла |
| PR-2b (`simintech-mcp`) влит или хотя бы его пример лежит в `main` | скилл ссылается на `simintech-mcp/docs/examples/language-contour.md`; ссылка на несуществующий файл — то, что ловит `test_referenced_paths_exist_in_simintech_code` (для `simintech-code`) и что обязано быть верным по смыслу для `simintech-mcp` |

Если PR-2b ещё не влит — ветка PR-3 создаётся от `main` скилла, а ссылка на
пример оформляется отложенной задачей (последняя задача плана); до этого её
наличие проверяется отдельным тестом с `skip` и названной причиной.

## Область плана

- **Это PR-3 полностью**: знание агента о контуре.
- **Сопутствующие исправления** (задачи 5 и 6) — дрейф, найденный при разведке;
  если решено не смешивать темы в одном PR, они выносятся в отдельную ветку
  `fix/stale-language-knowledge` тем же коммитом-содержимым.
- **Вне области:** новые скиллы, изменение README (состав скиллов не меняется),
  правка `simintech-code`/`simintech-mcp`.

## Карта файлов

| Файл | Что делаем | Ответственность |
|---|---|---|
| `skills-catalog/simintech-language-core/SKILL.md` | правим | новый раздел «Контур: как код доезжает до проекта», правка абзаца «Готовой доставки у агента нет» |
| `skills-catalog/simintech-language-core/manifest.yaml` | правим | `source_of_truth` (спецификация, MCP-пример), `verified_note`, версия скилла |
| `skills-catalog/simintech-model-building/SKILL.md` | правим | снять опровергнутый отрицательный результат про `createmodelfromfile` |
| `tests/unit/test_skills_catalog.py` | правим | якоря контура, исходы, указатель на пример, запрет «доставки нет» |
| `scripts/public_data_check.py` | правим | ALLOWLIST_PATHS: путь плана переехал в `archive/` ещё 2026-09-28 |

---

## Задача 0: ветка

- [ ] **Step 1**

```bash
cd /mnt/c/git/simintech-skill
git checkout main && git pull --ff-only
git checkout -b docs/language-contour-knowledge
```

---

## Задача 1: раздел о контуре в скилле языка

**Files:**
- Modify: `skills-catalog/simintech-language-core/SKILL.md`

Раздел встаёт **после** «Построение модели встроенным языком» (строка ~184 в
текущем тексте — перед «Декларативный текст модели»): сначала «чем собирать», потом
«как код доезжает до проекта».

- [ ] **Step 1: написать падающий тест**

В `tests/unit/test_skills_catalog.py`, рядом с `TEXT_MODEL_FUNCTIONS`:

```python
#: Исходы контура — имена, под которыми их отдаёт MCP-инструмент. Скилл обязан
#: назвать их **дословно**: агент сверяет ответ инструмента со знанием, и
#: «примерно так» здесь стоит неверного решения о следующем шаге.
CONTOUR_OUTCOMES = (
    "ok",
    "model-not-running",
    "aborted",
    "not-compiled",
    "section-not-run",
)

#: Указатель на пример-сценарий: файл живёт в репозитории MCP-сервера.
CONTOUR_EXAMPLE_URL = (
    "https://github.com/producedbysavant/simintech-mcp/blob/main/"
    "docs/examples/language-contour.md"
)
```

и тест (в разделе «Знание о встроенном языке», после
`test_environment_rules_stay_in_the_skill`):

```python
def test_contour_outcomes_and_example_are_in_the_skill():
    """Скилл называет пять исходов контура и указывает на пример-сценарий.

    Исходы — контракт инструмента `run_page_script`: по ним агент решает, что
    делать дальше (повторить, остановиться, сказать человеку про неподключённый
    вход). Указатель на пример — не украшение: полный порядок шагов с численной
    приёмкой живёт там, и без ссылки агент его не найдёт.
    """
    text = _language_skill()

    missing = [name for name in CONTOUR_OUTCOMES if name not in text]
    assert not missing, f"в скилле нет исходов контура: {missing}"

    assert CONTOUR_EXAMPLE_URL in text, (
        "в скилле нет указателя на пример docs/examples/language-contour.md")
```

- [ ] **Step 2: убедиться, что тест падает**

Run: `python3.11 -m pytest tests/unit/test_skills_catalog.py -q -k contour`
Expected: FAIL — в скилле нет ни одного из имён исходов.

- [ ] **Step 3: написать раздел**

Вставить в `SKILL.md` после раздела «Построение модели встроенным языком»
(перед «Декларативный текст модели»):

````markdown
## Контур: как код доезжает до проекта

Скрипт в проект доставляет **MCP-сервер** (`simintech-mcp`): он ставит текст в
скрипт текущей страницы, запускает расчёт и читает файл результата. Команды —
`get_page_script`, `set_page_script`, `run_page_script`, `inject_submodel_script`,
`export_model_text`, `import_model_text`; прежний скрипт страницы возвращается на
место, а изменения модели живут в памяти до `save_project`.

**Среда молчит об ошибках скрипта.** `SetPageScript` возвращает `1` даже при
синтаксически неверном тексте, ошибка времени выполнения молча обрывает остаток
скрипта, а текст ошибки компиляции виден только в окне сообщений редактора
SimInTech — через COM он не читается. Поэтому инструменты не «верят» коду
возврата, а различают **пять исходов** по маркерам, которые сам скрипт пишет в
файл результата (`CTX_BEGIN` до тела, `CTX_END` после), и по росту модельного
времени:

| Исход | Что это значит | Что делать |
|---|---|---|
| `ok` | тело дошло до конца, расчёт идёт | читать строки тела из ответа |
| `model-not-running` | скрипт собрался и отработал, а **модель не считает** | проверить соединения: неподключённый вход останавливает расчёт всей модели молча; это не ошибка скрипта |
| `aborted` | обрыв на исполнении: начальный маркер есть, конечного нет | в ответе — последняя записанная строка; искать ошибку времени выполнения в теле |
| `not-compiled` | скрипт **не собрался** (маркеров нет, время стоит) | текст ошибки — в окне сообщений редактора SimIntech; чаще всего это забытая точка с запятой или кавычка не через `chr(34)` |
| `section-not-run` | маркеров нет, но расчёт шёл | секция `initialization` не выполнилась; сообщается как есть, причина по этому признаку не определяется |

**Порядок шагов задания.** Собирать модель текстом:

1. `export_model_text` — посмотреть, что уже есть на текущей странице (заодно
   образец синтаксиса для шага 3);
2. `import_model_text` — собрать объекты из текста; `createmodel` **дополняет**
   модель, старые объекты остаются;
3. сверить результат по отчёту об изменениях в ответе (сколько объектов было и
   стало, какие добавились) — «нет ошибки» успехом не считается;
4. `set_calc_time` → `run` → `read_output_file` — расчёт и снятие результата;
5. `get_page_script` — посмотреть, какой скрипт лежит на странице (чтение
   **не запускает** расчёт и не сдвигает модельное время).

**Скрипт пишут только тогда, когда текста модели не хватает** (сбор данных,
создание объекта определённого типа). Для этого `set_page_script` — он
проверяет, что скрипт собрался, и возвращает прежний текст; `inject_submodel_script` —
субмодель со скриптом сбора данных, который исполняется на каждом шаге расчёта;
`run_page_script` — произвольное тело в секции `initialization` (клапан, для
разведки и нестандартных случаев).

**Три запрета, которые контур не обходит.** Создавать объекты можно только в
секции `initialization` — инструменты ставят тело туда, а `finalization` при
внешней остановке расчёта не срабатывает, поэтому данные собирают записью в
теле. Кавычка внутри строкового литерала — только `chr(34)`. Удалять объекты в
живом проекте нельзя: `removeprimitiv` роняет следующий старт расчёта (access
violation в `mbtylib.dll`).

**Полный сценарий с численной приёмкой и падающими случаями** —
[`docs/examples/language-contour.md`](https://github.com/producedbysavant/simintech-mcp/blob/main/docs/examples/language-contour.md)
в репозитории MCP-сервера: реплики агента, что сверяет человек, и четыре
случая, на которых контур обязан отказать внятно.
````

- [ ] **Step 4: прогнать тест**

Run: `python3.11 -m pytest tests/unit/test_skills_catalog.py -q -k contour`
Expected: PASS.

- [ ] **Step 5: коммит**

```bash
git add skills-catalog/simintech-language-core/SKILL.md tests/unit/test_skills_catalog.py
git commit -m "docs(skill): контур языкового слоя — пять исходов и порядок шагов"
```

---

## Задача 2: снять утверждение «готовой доставки у агента нет»

**Files:**
- Modify: `skills-catalog/simintech-language-core/SKILL.md`
- Test: `tests/unit/test_skills_catalog.py`

Сейчас в разделе «Построение модели встроенным языком» написано: «**Готовой
доставки у агента нет.** Инструмента для скриптов у MCP-сервера нет вовсе…».
После PR-2 это неверно, и неверное знание здесь дороже отсутствующего: агент
выберет обходной путь там, где есть штатный.

- [ ] **Step 1: написать тест-сторож**

```python
#: Утверждения, которые контур опроверг: пока они в тексте, агент обходит
#: инструменты стороной. Список — по факту формулировок, а не по смыслу
#: абзаца: правится текст — правится и список.
REFUTED_CONTOUR_PHRASES = (
    "Готовой доставки у агента нет",
    "Инструмента для скриптов у MCP-сервера нет",
)


def test_skill_does_not_deny_the_contour_tools():
    """Скилл не утверждает, что доставки скрипта у агента нет.

    Так было до `simintech-mcp` PR-2 — и утверждение честно описывало тогдашнее
    состояние. Теперь оно опровергнуто: `set_page_script`, `run_page_script` и
    `inject_submodel_script` ставят тело в `initialization`.
    """
    text = _language_skill()

    found = [phrase for phrase in REFUTED_CONTOUR_PHRASES if phrase in text]
    assert not found, (
        f"в скилле остались опровергнутые утверждения: {found} — доставка есть")
```

- [ ] **Step 2: прогон — падает**

Run: `python3.11 -m pytest tests/unit/test_skills_catalog.py -q -k does_not_deny`
Expected: FAIL — обе фразы в тексте.

- [ ] **Step 3: переписать абзац**

Было (фрагмент): «**Готовой доставки у агента нет.** Инструмента для скриптов у
MCP-сервера нет вовсе, а проба `ScriptBridge` ставит тело под `if firststep
then` — то есть в момент, когда создавать объекты уже запрещено. `install_script`
умеет поставить произвольный текст, но стирает прежний скрипт страницы…».

Стало:

```markdown
**Доставка есть — и ставит тело в `initialization`.** Инструменты MCP-сервера
(`set_page_script`, `run_page_script`, `inject_submodel_script`) выполняют текст
именно в этой секции — там, где создавать объекты разрешено, — и **возвращают
прежний скрипт страницы на место** в том же вызове. Прежняя проба
`ScriptBridge.run_probe` ставила тело под `if firststep then`, то есть в момент,
когда создавать объекты уже запрещено: для сборки модели она не годится, а
`ScriptBridge.install_script` стирает прежний скрипт, не сообщая, что там было.
Разбор исходов и порядок шагов — в разделе «Контур: как код доезжает до проекта».
```

- [ ] **Step 4: прогнать тесты**

Run: `python3.11 -m pytest tests/unit -q -rs`
Expected: зелёный набор (было 115 узлов; станет на 3 больше).

- [ ] **Step 5: коммит**

```bash
git add skills-catalog/simintech-language-core/SKILL.md tests/unit/test_skills_catalog.py
git commit -m "docs(skill): доставка скрипта у агента есть — снято опровергнутое"
```

---

## Задача 3: манифест скилла

**Files:**
- Modify: `skills-catalog/simintech-language-core/manifest.yaml`

- [ ] **Step 1: дополнить `source_of_truth`**

После блока ссылок на справку по субмодели:

```yaml
    # Контур языкового слоя: пять исходов, маркеры, порядок доставки скрипта.
    - https://github.com/producedbysavant/simintech-code/blob/main/docs/superpowers/specs/2026-09-29-language-contour.md
    - https://github.com/producedbysavant/simintech-code/blob/main/simintech_api/core/script_bridge.py
    # Пример-сценарий с численной приёмкой и падающими случаями (MCP-сервер).
    - https://github.com/producedbysavant/simintech-mcp/blob/main/docs/examples/language-contour.md
```

(ссылка на `script_bridge.py` уже есть в конце списка — дубликат **не
добавлять**: правило «источник называется один раз» проверяется глазами при
ревью, а `test_manifest_sources_are_urls` ловит только форму.)

- [ ] **Step 2: дописать `verified_note`**

Новый абзац в конец свёртки:

```yaml
    Контур языкового слоя измерен 2026-09-29 (та же поставка 2.26.6.23) и
    реализован в simintech-code PR #15 (механика: run_page_script, пять исходов,
    тела операций) и simintech-mcp PR-2 (инструменты). Тело, поставленное
    скриптом страницы, исполняется в секции initialization; исход различается по
    маркерам CTX_BEGIN/CTX_END и росту модельного времени: ok,
    model-not-running, aborted, not-compiled, section-not-run. Живой прогон:
    tests/integration/test_language_contour_live.py — 1 passed 2026-09-29.
    Порядок шагов задания и падающие случаи — в примере MCP-сервера.
```

- [ ] **Step 3: поднять версию скилла**

`version: 0.1.0` → `version: 0.2.0` (добавлен раздел и снято опровергнутое
утверждение; правило версий — как у библиотеки: знание изменилось — версия
изменилась).

- [ ] **Step 4: прогнать тесты манифеста**

```bash
python3.11 -m pytest tests/unit/test_skills_catalog.py -q -k manifest
git add skills-catalog/simintech-language-core/manifest.yaml
git commit -m "docs(skill): манифест — источники контура и версия 0.2.0"
```

---

## Задача 4: указатель на пример в скилле сборки модели

**Files:**
- Modify: `skills-catalog/simintech-model-building/SKILL.md`
- Test: `tests/unit/test_skills_catalog.py`

Скилл сборки модели — то, что читает агент, когда его просят «собери модель».
Ему нужен путь к контуру: без этого он снова начнёт собирать через
`add_block`/`connect`, не зная, что текст модели собирается одним вызовом.

- [ ] **Step 1: написать тест**

```python
def test_model_building_points_to_the_contour():
    """Скилл сборки модели указывает на пример контура.

    Проверяется **указатель**, а не пересказ: пересказ разошёлся бы с
    `simintech-language-core` при первой же правке (это уже случалось — см.
    `test_model_building_pointer_does_not_invent_names`).
    """
    text = _skill("simintech-model-building")

    assert CONTOUR_EXAMPLE_URL in text, (
        "в скилле сборки модели нет указателя на пример контура")
```

- [ ] **Step 2: прогон — падает**

Run: `python3.11 -m pytest tests/unit/test_skills_catalog.py -q -k model_building_points`
Expected: FAIL.

- [ ] **Step 3: дописать абзац**

В разделе «Встроенный язык — путь, который вендор называет для сборки схемы» —
после абзаца про загрузку текста (см. задачу 5, там же правится устаревшее):

```markdown
**Полный порядок сборки — в примере.** Реплики для агента, что сверяет человек
по шагам и какие четыре случая обязаны отказать внятно:
[`docs/examples/language-contour.md`](https://github.com/producedbysavant/simintech-mcp/blob/main/docs/examples/language-contour.md).
```

- [ ] **Step 4: коммит**

```bash
git add skills-catalog/simintech-model-building/SKILL.md tests/unit/test_skills_catalog.py
git commit -m "docs(skill): сборка модели ссылается на пример контура"
```

---

## Задача 5: снять опровергнутый результат в скилле сборки модели

**Files:**
- Modify: `skills-catalog/simintech-model-building/SKILL.md`

**Дефект (найден разведкой 2026-09-29).** В `simintech-model-building/SKILL.md`
(раздел «Встроенный язык…», стр. 169–190) до сих пор написано: «Загрузка текста
нашей стороной пока не подтверждена: `createmodelfromfile` … объектов **не
создал**, причина не локализована, а `createmodel` живым вызовом не проверялся».
Скилл языка это уже опроверг: причина была в экранировании кавычек, все пять
демо вендора проходят. Два скилла учат агента разному — и агент поверит тому,
который прочитал первым.

- [ ] **Step 1: написать тест-сторож**

```python
#: Опровергнутый отрицательный результат 2026-09-28: причина была в кавычках
#: (`chr(34)`), а не в среде. Строки держатся как якоря, чтобы абзац не вернулся.
REFUTED_LOAD_PHRASES = (
    "Загрузка текста нашей стороной пока не подтверждена",
    "причина не локализована, а `createmodel` живым вызовом не проверялся",
)


def test_model_building_does_not_repeat_the_refuted_load_result():
    """Отрицательный результат загрузки снят в обоих скиллах.

    `simintech-language-core` объясняет: `createmodelfromfile` объектов не
    создал из-за удвоенных кавычек, а не из-за среды; пять демонстрационных
    проектов вендора проходят (замер 2026-09-29).
    """
    for name in ("simintech-model-building", "simintech-language-core"):
        text = _skill(name)
        found = [p for p in REFUTED_LOAD_PHRASES if p in text]
        assert not found, f"{name}: остался опровергнутый результат: {found}"
```

- [ ] **Step 2: прогон — падает**

Run: `python3.11 -m pytest tests/unit/test_skills_catalog.py -q -k refuted_load`
Expected: FAIL на `simintech-model-building`.

- [ ] **Step 3: переписать абзац**

Стало:

```markdown
**Загрузка текста работает** — но с одной ловушкой: кавычка внутри строкового
литерала задаётся `chr(34)`. Удвоение `""` в этой сборке даёт **пустую строку**,
а обратный слэш не экранирует; текст при этом выглядит правдоподобно, объектов
не создаёт и сообщений не оставляет. Наш прежний отрицательный результат
(`createmodelfromfile` «не работает») был ошибкой на нашей стороне. Замер
2026-09-29: `savemodeltofile`, `createmodel`, `createmodelfromfile` проходят на
поставке 2.26.6.23 — пять демонстрационных проектов вендора и своя проба.
Семейство функций текста модели вендор называет из **четырёх** имён — вместе с
`savemodeltotext`; последней в поставке 2.26.6.23 мы не нашли, поэтому на это имя
в сценарии не опирайтесь (подробности — в скилле `simintech-language-core`).
```

- [ ] **Step 4: прогнать**

```bash
python3.11 -m pytest tests/unit -q -rs
git add skills-catalog/simintech-model-building/SKILL.md tests/unit/test_skills_catalog.py
git commit -m "docs(skill): загрузка текста модели работает — снят старый минус"
```

---

## Задача 6: починить путь в гейте публичных данных

**Files:**
- Modify: `scripts/public_data_check.py`

**Дефект (найден разведкой 2026-09-29).** В `ALLOWLIST_PATHS` скилла прописан
`("docs/superpowers/plans/2026-09-26-ecosystem-hardening.md", "*")` — такого
пути нет ни в этом репозитории, ни в `simintech-code`: 2026-09-28 планы
перенесены в `archive/`, и в `simintech-code` запись уже поправлена. Здесь —
осталась: правило, разрешающее несуществующий путь, молча бесполезно.

- [ ] **Step 1: заменить запись**

```python
    # План по этому гейту (с 2026-09-28 — в `archive/`): примеры правил и
    # разбор находок.
    ("docs/superpowers/archive/2026-09-26-ecosystem-hardening.md", "*"),
```

- [ ] **Step 2: прогнать гейт и его тесты**

```bash
python3.11 -m pytest tests/unit/test_public_data_check.py -q
python3.11 scripts/public_data_check.py     # «Нарушений не найдено», scanned > 0
```

- [ ] **Step 3: коммит**

```bash
git add scripts/public_data_check.py
git commit -m "fix(public-data): путь плана переехал в archive — правка allowlist"
```

---

## Задача 7: гейты и PR

- [ ] **Step 1: полный прогон**

```bash
cd /mnt/c/git/simintech-skill
python3.11 -m pytest tests/unit -q -rs
python3.11 -m flake8 tests --max-line-length=88 --extend-ignore=E203,W503
python3.11 scripts/public_data_check.py
SIMINTECH_CODE_DIR=/mnt/c/git/simintech-code python3.11 -m pytest tests/unit -q -rs  # сверка с чек-аутом
```

Последняя команда обязательна: без `SIMINTECH_CODE_DIR` часть проверок
пропускается, а набор выглядит зелёным.

- [ ] **Step 2: push и PR**

```bash
git push -u origin docs/language-contour-knowledge
gh pr create --base main --head docs/language-contour-knowledge \
  --title "docs(skills): знание о контуре языкового слоя" \
  --body-file "$CLAUDE_JOB_DIR/tmp/pr3-body.md"
```

В теле PR: ссылки на спецификацию (simintech-code §6.3), на план PR-2 и на
пример; что именно снято как опровергнутое (три формулировки); число тестов;
отдельным абзацем — **сопутствующие исправления** (задачи 5 и 6) и предложение
вынести их в отдельный PR, если решено не смешивать темы.

---

## Гейты и красные флаги

- Прогон без `SIMINTECH_CODE_DIR` — **не доказательство**: часть проверок
  скипается, и набор выглядит зелёным (в CI переменная ставится вторым
  checkout'ом).
- Число тестов в README не называется намеренно (коммит `20ff78e`): не
  добавлять.
- Два README (`README.md` и `skills-catalog/README.md`) обязаны остаться
  побайтово равными; правок в них этот план не делает.
- Ссылка на пример ведёт в **чужой** репозиторий (`simintech-mcp`):
  существование файла гейтом этого репозитория не проверяется — проверяется
  наличие ссылки в тексте (задача 1) и то, что файл действительно есть, задачей
  7 предпосылок.
