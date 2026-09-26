# Починка потери скрипта неглавной страницы: план реализации

> **Для агента-исполнителя:** обязательный навык — `superpowers:subagent-driven-development`
> (рекомендуется) или `superpowers:executing-plans`. Шаги помечены чекбоксами
> (`- [x]`) — **это журнал исполнения, а не шаблон**: все семь задач выполнены.
> Там, где реализация разошлась с шагом, расхождение записано рядом со шагом
> (разделы «что изменилось после ревью»), а источник истины — код.

**Цель:** `read_topology` (и любая проба поверх `ScriptBridge`) перестаёт стирать
скрипт неглавной страницы, а когда установить, какую именно страницу она трогает,
не удаётся — сообщает об этом отдельным типом отказа, не притворяясь успехом.

**Архитектура:** мост перестаёт «читать текущий скрипт» — такого надёжного способа
не существует. Вместо этого он снимает **все** скриптовые записи проекта до и
после установки пробы, находит ту, которую изменил `SetPageScript`, и именно её
прежнее содержимое возвращает. Метка `//SCRIPT_BRIDGE_TARGET_<hex>`, свой nonce
на запуск, стоит первым комментарием скрипта: она доказывает, что запись изменили
**мы**, а не что она просто оказалась единственной изменившейся.

**Стек:** Python 3.11, `comtypes` (COM, только Windows), pytest. Спецификация —
`docs/superpowers/specs/2026-09-22-page-script-loss-design.md`, все замеры в ней
сделаны на копиях поставки SimInTech64.

## Файловая структура

| Файл | Что с ним |
|---|---|
| `simintech_api/exceptions.py` | +`ScriptBridgeUnsafeStateError` |
| `simintech_api/__init__.py` | +экспорт нового исключения |
| `simintech_api/script_probe.py` | +метка, +разбор снимка скриптовых записей, +поиск изменившейся записи, +проверка отсутствия метки; `build_probe_script` получает метку; **убирается** `read_page_script` |
| `simintech_api/core/script_bridge.py` | **убирается** `capture_script`; `run_probe` переписан на «снимок → установка → опознание → возврат → сверка»; +`_dump_records`, +`_describe_mismatch` |
| `tests/unit/test_script_probe.py` | добавляются тесты снимка и опознания; при удалении старой механики снимается пять тестов `test_read_page_script_*` |
| `tests/unit/test_script_bridge.py` | `FakeEnv` расширяется до многопстраничного проекта; тесты переписываются |
| `tests/integration/test_script_bridge_live.py` | `capture_script` заменяется на снимки |
| `tests/integration/test_topology_live.py` | +регрессия «скрипт страницы субмодели выжил» |
| `docs/api.md`, `CLAUDE.md`, `docs/reference/com_api_inventory.md` | предупреждение снимается, факты обновляются |

---

## Task 1: Исключение для неизвестного состояния

**Files:**
- Modify: `simintech_api/exceptions.py`
- Modify: `simintech_api/__init__.py`
- Test: `tests/unit/test_script_bridge.py`

- [x] **Step 1: Написать падающий тест**

В конец `tests/unit/test_script_bridge.py`:

```python
def test_unsafe_state_error_is_script_bridge_error():
    """Дочерний, а не независимый: `except ScriptBridgeError` обязан ловить."""
    assert issubclass(ScriptBridgeUnsafeStateError, ScriptBridgeError)
    assert issubclass(ScriptBridgeUnsafeStateError, SimInTechError)
```

Импорты в шапке файла дополнить:

```python
from simintech_api.exceptions import (
    ScriptBridgeError,
    ScriptBridgeUnsafeStateError,
    SimInTechError,
)
```

- [x] **Step 2: Убедиться, что тест падает**

Run: `python3.11 -m pytest tests/unit/test_script_bridge.py -q`
Expected: FAIL — `ImportError: cannot import name 'ScriptBridgeUnsafeStateError'`

- [x] **Step 3: Добавить класс**

В `simintech_api/exceptions.py` — после `ScriptBridgeError`:

```python
class ScriptBridgeUnsafeStateError(ScriptBridgeError):
    """Состояние скриптов страниц не установлено: восстанавливать некуда.

    Отдельный класс, **дочерний** `ScriptBridgeError`, а не независимый:
    `except ScriptBridgeError` обязан по-прежнему ловить отказ моста целиком,
    иначе правка сломает вызывающий код. А отдельный тип позволяет отличить
    именно этот случай — «в проекте, возможно, остался пробный скрипт, а
    автоматическое восстановление не было безопасным» — и сказать об этом
    пользователю, не разбирая текст сообщения.
    """
```

- [x] **Step 4: Добавить в экспорт**

В `simintech_api/__init__.py` — в список исключений (рядом с `ScriptBridgeError`):

```python
    "ScriptBridgeUnsafeStateError",
```

- [x] **Step 5: Прогнать тест**

Run: `python3.11 -m pytest tests/unit/test_script_bridge.py -q`
Expected: PASS

- [x] **Step 6: Коммит**

```bash
git add simintech_api/exceptions.py simintech_api/__init__.py tests/unit/test_script_bridge.py
git commit -m "feat(errors): ScriptBridgeUnsafeStateError — дочерний от ScriptBridgeError"
```

---

## Task 2: Метка цели

**Files:**
- Modify: `simintech_api/script_probe.py`
- Test: `tests/unit/test_script_probe.py`

- [x] **Step 1: Написать падающие тесты**

В `tests/unit/test_script_probe.py`:

```python
def test_target_token_is_a_comment_of_ascii_without_forbidden_chars():
    """Метка проходит через выгрузку обычным текстом.

    Это проверка **выборки**: запрещённый знак она поймает, только если тот
    выпал за 32 знака. Доказательством контракта она быть не может — 32 выбора
    из 17 знаков дают `(16/17)**32 ≈ 14%` на то, что добавленный знак не
    выпадет ни разу (измерено: мутация «добавить `#` в алфавит» проходила
    в 9 прогонах из 10). Детерминированную гарантию даёт тест пула ниже.
    """
    token = new_target_token()
    assert token.startswith("//SCRIPT_BRIDGE_TARGET_")
    assert len(token.split("_")[-1]) == TARGET_TOKEN_HEX_DIGITS
    assert set(token.split("_")[-1]) <= set("0123456789abcdef"), (
        "знак вне hex-набора и вне списка запрещённых (например `g`) цикл ниже "
        "не поймает вовсе — эта строка ловит, но тоже вероятностно")
    assert all(32 <= ord(char) < 127 for char in token)
    for char in "\"'`# \t\r\n":
        assert char not in token, f"в метке недопустимый символ {char!r}"


class _AlphabetRecordingRng(random.Random):
    """Источник случайности, запоминающий алфавит, из которого шёл выбор."""

    def __init__(self):
        super().__init__(0)
        self.alphabets = []

    def choice(self, seq):
        self.alphabets.append("".join(seq))
        return super().choice(seq)


def test_target_token_alphabet_is_only_hex_for_any_source():
    """Контракт держится **пулом**, а не выборкой — и это единственная гарантия.

    Проверять готовую метку бессмысленно как доказательство: она случайна.
    Здесь проверяется сам алфавит, из которого шёл выбор, и от случая это уже
    не зависит: мутация алфавита краснеет **всегда**.

    Тест сцеплён со способом расхода источника (`choice`): если
    `new_target_token` переписать на `randrange`, он покраснеет на
    `assert rng.alphabets` — шумный отказ вместо тихого согласия, и это
    намеренный выбор в пользу шумного.
    """
    rng = _AlphabetRecordingRng()
    new_target_token(rng)
    assert rng.alphabets, "источник случайности не использован"
    alphabet = set("".join(rng.alphabets))
    extra = sorted(alphabet - set("0123456789abcdef"))
    missing = sorted(set("0123456789abcdef") - alphabet)
    assert not extra and not missing, (
        f"алфавит метки разошёлся с hex-набором: лишние {extra!r}, "
        f"недостающие {missing!r} — сужение алфавита ослабляет nonce "
        "(32 знака из двухсимвольного алфавита — 32 бита вместо 128)")


def test_target_token_differs_between_calls():
    assert new_target_token() != new_target_token()


def test_target_token_consumes_the_injected_random_stream():
    """Источник случайности — параметр, и он расходуется.

    Равенство двух вызовов с одинаковым seed этого не доказывает: его
    выполняет и функция, возвращающая константу. А два вызова на одном и том
    же потоке обязаны дать разные метки — иначе параметр не используется.
    """
    rng = random.Random(1)
    assert new_target_token(rng) != new_target_token(rng)
```

Импорты в шапке дополнить: `import random`, `TARGET_TOKEN_HEX_DIGITS` и
`new_target_token` из `simintech_api.script_probe`.

- [x] **Step 2: Убедиться, что тесты падают**

Run: `python3.11 -m pytest tests/unit/test_script_probe.py -q`
Expected: FAIL — `ImportError: cannot import name 'new_target_token'`

- [x] **Step 3: Реализовать**

В `simintech_api/script_probe.py` (после маркеров):

```python
#: Префикс метки цели. Метка — **доказательство**, что скриптовую запись
#: изменили мы, а не просто «единственная изменившаяся»: без неё запись чужой
#: страницы, изменившаяся сама по себе, была бы принята за нашу, и возврат
#: положил бы в текущую страницу чужой скрипт.
TARGET_TOKEN_PREFIX = "//SCRIPT_BRIDGE_TARGET_"

#: Длина случайной части метки в шестнадцатеричных знаках.
TARGET_TOKEN_HEX_DIGITS = 32


def new_target_token(rng: Optional[random.Random] = None) -> str:
    """Сгенерировать метку цели — комментарий языка, свой на каждый запуск.

    Метка состоит только из ASCII-знаков и не содержит кавычек, обратных
    кавычек, решётки, пробелов и переводов строк. Это не стилистика: решётка
    сделала бы метку неотличимой от кодов `#NN`, которыми выгрузка кодирует
    спецсимволы, а кавычка и перевод строки ломают разметку значения `<script>`.

    `rng` — источник случайности, по умолчанию `SystemRandom`. Параметр нужен
    тестам: воспроизводимость важнее удобства.
    """
    source = rng if rng is not None else random.SystemRandom()
    digits = "".join(source.choice("0123456789abcdef")
                     for _ in range(TARGET_TOKEN_HEX_DIGITS))
    return TARGET_TOKEN_PREFIX + digits
```

Импорты модуля дополнить: `import random`.

- [x] **Step 4: Прогнать тесты**

Run: `python3.11 -m pytest tests/unit/test_script_probe.py -q`
Expected: PASS

- [x] **Step 5: Коммит**

```bash
git add simintech_api/script_probe.py tests/unit/test_script_probe.py
git commit -m "feat(probe): метка цели — доказательство, что запись изменили мы"
```

---

## Task 3: Разбор снимка скриптовых записей

**Files:**
- Modify: `simintech_api/script_probe.py` — **только добавление**
- Test: `tests/unit/test_script_probe.py` — **только добавление**

**Здесь ничего не удаляется, и это исправление плана, а не упущение.**
`read_page_script` ещё **используется**: его импортирует и зовёт
`ScriptBridge.capture_script` (`simintech_api/core/script_bridge.py:36,91`).
Удаление функции на этом шаге сломало бы импорт моста, и красным стал бы весь
файл `tests/unit/test_script_bridge.py` — то есть тесты, красные на шаге
проверки своей же задачи. Удаление `read_page_script` вместе с `_PAGE_RE`, его
пятью тестами `test_read_page_script_*` и тестом `test_wrong_page_is_never_substituted_for_main`
(он лежит в `tests/unit/test_script_bridge.py`, а не в файле пробы, как
говорил прежний текст этого шага) переезжает в Task 5 — туда, где уходит и
вызывающий, `capture_script`.

Так старая и новая механика чтения сосуществуют две задачи: это дешевле, чем
один коммит, в котором и появилась, и удалилась бы половина моста.

- [x] **Step 1: Написать падающие тесты нового разбора**

В `tests/unit/test_script_probe.py`:

```python
#: Выгрузка из трёх страниц: главная с путём в имени, страница субмодели с
#: ПУСТЫМ именем, и страница-контейнер. Форма записи — как в поставке: значение
#: в обратных кавычках и кодах, пустой скрипт — без кавычек вовсе.
def _dump(pages):
    body = "".join(
        f"<page>\n <name>{name}</name>\n <script>{value}</script>\n"
        f" <visible>`1`</visible>\n</page>\n"
        for name, value in pages)
    return "<project>\n" + body + "</project>\n"


def test_parse_script_records_returns_raw_values_in_document_order():
    """Записи возвращаются **сырыми**: сравнение снимков идёт по тексту файла."""
    text = _dump([("`C:\\work\\model.prt`", "`a`#10`b`"),
                  ("", "`sentinel`"),
                  ("`Container`", "")])
    assert parse_xprt_script_records(text) == ["`a`#10`b`", "`sentinel`", ""]


def test_parse_script_records_accepts_empty_name_without_backticks():
    """`<name></name>` — не аномалия, а форма страницы субмодели (измерено).

    Прежний разбор требовал кавычек вокруг имени и такую запись пропускал —
    вместе с ней пропадала и страница.
    """
    assert parse_xprt_script_records(_dump([("", "`x`")])) == ["`x`"]


def test_parse_script_records_refuses_dump_with_unparsed_page():
    """Число записей обязано сойтись с числом страниц: пропуск — не «меньше».

    Разбор, молча пропустивший страницу, сдвинул бы нумерацию записей, и
    возврат положил бы чужой скрипт. Поэтому расхождение — отказ.
    """
    text = _dump([("`a`", "`x`")]) + "<page>\n <script>no name</script>\n</page>\n"
    with pytest.raises(ScriptBridgeError) as exc:
        parse_xprt_script_records(text)
    assert "страниц" in str(exc.value)


def test_parse_script_records_does_not_take_data_script_for_page_script():
    """Скрипт свойства внутри объекта — не скрипт страницы.

    У объектов в выгрузке есть `<data><script>` (скрипты свойств). Разбор ищет
    скрипт сразу за `<name>` страницы, поэтому чужой `<script>` в середину не
    попадает.
    """
    text = ("<project>\n<page>\n <name>`p`</name>\n <script>`page`</script>\n"
            " <object>\n  <data>\n   <script>`prop`</script>\n  </data>\n"
            " </object>\n</page>\n</project>\n")
    assert parse_xprt_script_records(text) == ["`page`"]


def test_parse_script_records_refuses_page_without_its_own_script():
    """Правило «`<script>` сразу за `</name>`» — не украшение, и оно проверяется.

    Форма синтетическая: в поставке страницы без собственного скрипта не
    встречается (0 из 1534 — у каждой ровно один страничный `<script>`, и он
    всегда идёт сразу за `</name>`). Но именно она отделяет верный разбор от
    ослабленного: если снять примыкание к `</name>`, разбор вернёт **скрипт
    свойства** под видом скрипта страницы, а самопроверка по числу записей этого
    не увидит — числа сойдутся. Возврат же чужого скрипта в текущую страницу и
    есть та порча, ради запрета которой всё делается.

    Измерено ревью: без этого теста ослабленные формы
    (`<name>.*?</name>.*?<script>`, `</name>.*?<script>`) проходят все тесты и
    на всех 1534 страницах поставки неотличимы от верного разбора.
    """
    text = ("<project>\n<page>\n <name>`p`</name>\n <object>\n  <data>\n"
            "   <script>`prop`</script>\n  </data>\n </object>\n</page>\n"
            "</project>\n")
    with pytest.raises(ScriptBridgeError) as exc:
        parse_xprt_script_records(text)
    assert "страниц" in str(exc.value)


def test_token_present_in_finds_token_in_any_record():
    records = ["`a`", "`//SCRIPT_BRIDGE_TARGET_deadbeef`", "`b`"]
    assert token_present_in(records, "SCRIPT_BRIDGE_TARGET_deadbeef")
    assert not token_present_in(records, "SCRIPT_BRIDGE_TARGET_00000000")
```

Импорты в шапке `tests/unit/test_script_probe.py` дополнить:
`ScriptBridgeError` из `simintech_api.exceptions`, `parse_xprt_script_records` и
`token_present_in` из `simintech_api.script_probe`.

- [x] **Step 2: Убедиться, что тесты падают**

Run: `python3.11 -m pytest tests/unit/test_script_probe.py -q`
Expected: FAIL — `ImportError: cannot import name 'parse_xprt_script_records'`

- [x] **Step 3: Реализовать**

В `simintech_api/script_probe.py` — рядом с `read_page_script`, который
остаётся до Task 5 (там его уберут вместе с вызывающим):

```python
#: Скрипт страницы в выгрузке — `<script>` **сразу за** `<name>` страницы.
#: Имя бывает пустым и без обратных кавычек (`<name></name>`) — измерено на
#: странице субмодели демо вендора, и прежний разбор, требовавший кавычек,
#: пропускал такую страницу. Кавычки вокруг значения необязательны: пустой
#: скрипт пишется как `<script></script>`.
#:
#: Почему «сразу за»: у объектов внутри страницы есть свои `<script>` — скрипты
#: свойств в `<data>`. Взять первый `<script>` внутри страницы значило бы
#: схватить чужой.
_PAGE_SCRIPT_RE = re.compile(
    r"<page>\s*<name>(?:`[^`]*`)?</name>\s*<script>(.*?)</script>", re.S)

#: Открывающий тег страницы — для сверки числа записей с числом страниц.
_PAGE_OPEN_RE = re.compile(r"<page>")


def parse_xprt_script_records(xprt_text: str) -> List[str]:
    """Снять скриптовые записи выгрузки — **сырыми**, в порядке следования.

    Сырыми, а не декодированными: снимки сравниваются как текст файла, и это
    тот же уровень, на котором измерено «`SetPageScript` меняет ровно одну
    запись». Кодировку разбирает **не эта функция**: вызывающий декодирует
    (`decode_xprt_value`) ровно ту запись, которую предстоит вернуть на место.

    Разбор проверяет себя: число разобранных записей обязано совпасть с числом
    страниц. Молча пропущенная страница сдвинула бы нумерацию, и возврат
    положил бы чужой скрипт — поэтому расхождение это отказ, а не «сколько
    получилось».
    """
    records = _PAGE_SCRIPT_RE.findall(xprt_text)
    pages = len(_PAGE_OPEN_RE.findall(xprt_text))
    if len(records) != pages:
        raise ScriptBridgeError(
            f"в выгрузке {pages} страниц, но скриптовых записей разобрано "
            f"{len(records)}: форма выгрузки не та, что измерена, и продолжать "
            "нельзя — сдвиг нумерации записей означал бы возврат чужого скрипта")
    return records


def token_present_in(records: List[str], token: str) -> bool:
    """Встречается ли метка хоть в одной скриптовой записи."""
    return any(token in record for record in records)
```

Импорт исключения в шапку модуля:

```python
from .exceptions import ScriptBridgeError
```

- [x] **Step 4: Прогнать тесты**

Run: `python3.11 -m pytest tests/unit/test_script_probe.py -q`
Expected: PASS

- [x] **Step 5: Прогнать весь набор и линтеры**

Run: `python3.11 -m pytest tests/unit -q && python3.11 -m flake8 simintech_api tests --max-line-length=88 --extend-ignore=E203,W503`
Expected: PASS, 0 ошибок

- [x] **Step 6: Коммит**

```bash
git add simintech_api/script_probe.py tests/unit/test_script_probe.py
git commit -m "refactor(probe): снимок скриптовых записей вместо поиска страницы по имени"
```

---

## Task 4: Опознание цели по единственной изменившейся записи

**Files:**
- Modify: `simintech_api/script_probe.py`
- Test: `tests/unit/test_script_probe.py`

- [x] **Step 1: Написать падающую матрицу безопасности**

```python
#: Матрица безопасности опознания цели. Во всех строках сравниваются СНИМКИ:
#: списки сырых скриптовых записей. Метка — та, что стоит в установленном
#: скрипте; «до нас её не было» — отдельное условие, а не украшение.
TOKEN = "//SCRIPT_BRIDGE_TARGET_aabbccdd"


def test_find_changed_script_record_accepts_single_changed_with_token():
    before = ["`main`", "`sub`"]
    after = ["`main`", f"`{TOKEN}`#10`probe`"]
    assert find_changed_script_record(before, after, TOKEN) == 1


@pytest.mark.parametrize("after, fragment", [
    (["`main`", "`sub`"], "ни одна"),                        # ноль изменившихся
    (["`a`", "`b`"], "больше одной"),                         # изменились обе
    (["`main`", "`changed but no token`"], "метки"),          # чужая запись
    (["`main`", "`sub`", "`лишняя`"], "число"),               # записей больше
])
def test_find_changed_script_record_refuses_anything_but_unique_token(
        after, fragment):
    """Всё, кроме «ровно одна изменившаяся и в ней метка», — отказ.

    Третий случай — тот, ради которого метка и существует: единственная
    изменившаяся запись **без** метки означает, что изменилась чужая страница, и
    взять её значит положить в текущую страницу чужой скрипт.
    """
    before = ["`main`", "`sub`"]
    with pytest.raises(ScriptBridgeUnsafeStateError) as exc:
        find_changed_script_record(before, after, TOKEN)
    assert fragment in str(exc.value)


def test_find_changed_script_record_refuses_token_that_was_already_there():
    """Метка, встречавшаяся ДО нас, ничего не доказывает.

    Это случай «предыдущий запуск оставил пробный скрипт» либо совпадение
    nonce. Метка в записи доказывает авторство, только если её не было в
    снимке до установки, — иначе «метка есть» превращается в поиск подстроки.
    """
    token = "//SCRIPT_BRIDGE_TARGET_aabbccdd"
    before = [f"`{token}`", "`sub`"]
    after = ["`main`", f"`{token}`#10`probe`"]
    with pytest.raises(ScriptBridgeUnsafeStateError) as exc:
        find_changed_script_record(before, after, token)
    assert "до установки" in str(exc.value)
```

Импорты в шапке `tests/unit/test_script_probe.py` дополнить:
`ScriptBridgeUnsafeStateError` из `simintech_api.exceptions`, `find_changed_script_record`
из `simintech_api.script_probe`.

**Две правки в матрице против первого набора — они исправляют сам план.**
Фрагмент «ни одной» не совпадал с сообщением реализации («не изменилась **ни
одна** скриптовая запись»): `in` был ложен, тест падал на верном коде.
Второй элемент давал **три** записи `after` против двух в `before` и попадал в
проверку длин, а не в ветку «больше одной»; при этом ветка `len(changed) > 1`
оказывалась недостижимой ни одной строкой матрицы, и строка мутационной таблицы
«`len(changed) > 1` → `> 2`» была невыполнима. Обе правки — в данных теста;
реализация оставлена дословной, потому что менять порядок проверок значило бы
давать на расхождении длин **ложный** диагноз «изменила больше одной записи».

Мораль на будущее: сниппеты плана обязаны быть прогоняемы друг против друга.
Обе ошибки — из тех, что видны на первом же прогоне, и обе дошли до исполнителя
в авторском тексте.

- [x] **Step 2: Убедиться, что тесты падают**

Run: `python3.11 -m pytest tests/unit/test_script_probe.py -q`
Expected: FAIL — `ImportError: cannot import name 'find_changed_script_record'`

- [x] **Step 3: Реализовать**

```python
def find_changed_script_record(before: List[str], after: List[str],
                               token: str) -> int:
    """Номер скриптовой записи, которую изменила установка пробы.

    Условие цели — три части, и все обязательны:

    1. изменилась **ровно одна** запись (ноль — скрипт текущей страницы в
       выгрузку не попадает, и вернуть его нечем; больше одной — трогали не
       только её одну);
    2. метки **не было** ни в одной записи до установки — иначе она ничего не
       доказывает;
    3. метка есть в изменившейся записи — значит, изменили её **мы**.

    Нарушение любого из них — `ScriptBridgeUnsafeStateError`: в проекте остался
    пробный скрипт, а какую запись возвращать — неизвестно. Угадывать нельзя:
    ошибка здесь означает запись чужого скрипта в текущую страницу.
    """
    if token_present_in(before, token):
        raise ScriptBridgeUnsafeStateError(
            f"метка {token!r} встречалась в скриптовых записях ещё до установки "
            "пробы: она не доказывает, что запись изменили мы, и опознать цель "
            "нечем. Вероятная причина — в проекте остался пробный скрипт от "
            "предыдущего запуска.")
    if len(before) != len(after):
        raise ScriptBridgeUnsafeStateError(
            f"число скриптовых записей изменилось при установке пробы: "
            f"{len(before)} -> {len(after)}. Сопоставлять записи по номерам "
            "нельзя, цель не установлена.")
    changed = [index for index in range(len(before))
               if before[index] != after[index]]
    if not changed:
        raise ScriptBridgeUnsafeStateError(
            "после установки пробы не изменилась ни одна скриптовая запись: "
            "скрипт текущей страницы в выгрузку не попадает, и вернуть прежний "
            "нечем. Причины может быть две: пробный скрипт остался в проекте "
            "или скрипт этой страницы не сериализуется вовсе — проверьте обе "
            "перед следующим расчётом.")
    if len(changed) > 1:
        raise ScriptBridgeUnsafeStateError(
            f"установка пробы изменила больше одной скриптовой записи: "
            f"{changed}. Инвариант «установка меняет ровно одну запись» нарушен, "
            "и состояние проекта не таково, каким считалось: часть изменений — "
            "не наши. Восстановление по догадке положило бы чужой скрипт в "
            "текущую страницу, поэтому цель не установлена.")
    index = changed[0]
    if token not in after[index]:
        raise ScriptBridgeUnsafeStateError(
            f"изменилась скриптовая запись {index}, но метки в ней нет: значит, "
            "изменилась чужая страница, а не наша. Возврат в неё положил бы "
            "чужой скрипт в текущую страницу; цель не установлена.")
    return index
```

- [x] **Step 4: Прогнать тесты**

Run: `python3.11 -m pytest tests/unit/test_script_probe.py -q`
Expected: PASS

**Почему фрагменты в `assert fragment in str(exc.value)` — не украшение.**
Измерено ревью: у трёх мутантов из четырёх отказ **не исчезает** — он
выбрасывается другой веткой, с другим текстом. `pytest.raises` их бы пропустил,
и сенсором служат именно фрагменты:

| Мутация | Чем на самом деле отвечает мутант | Кто ловит |
|---|---|---|
| снять `token_present_in(before, …)` | веткой «больше одной» | фрагмент `"до установки"` |
| `len(changed) > 1` → `> 2` | веткой «нет метки в изменившейся» | фрагмент `"больше одной"` |
| снять проверку длин | веткой «ни одна изменившаяся» | фрагмент `"число"` |
| снять `token not in after[index]` | **возвращает индекс чужой записи** | `DID NOT RAISE` |

Оговорка по последней строке: снятие ветки «ни одна» краснит свой параметр не
через фрагмент, а падением внутри мутанта (`IndexError` на `changed[0]`). Красный
детерминирован, но фрагмент `"ни одна"` стережёт только переписывание текста.

То есть «отказ есть» и «отказ по правильной причине» — разные вещи, и различие
держат тексты сообщений. Отсюда требование к ним: сообщение обязано называть
**свою** причину, иначе сенсор слепнет.

- [x] **Step 5: Мутационная проверка сенсоров**

Четыре мутанта в `find_changed_script_record` — каждый обязан покраснеть:

| Мутация | Ожидание |
|---|---|
| снять проверку `token_present_in(before, ...)` | красный `..._refuses_token_that_was_already_there` |
| `len(changed) > 1` → `> 2` | красный параметр «больше одной» |
| снять проверку `token not in after[index]` | красный параметр «метки» |
| `len(before) != len(after)` → снять | красный параметр «число» |

Правки делать на копии файла, с `PYTHONDONTWRITEBYTECODE=1` и очисткой
`__pycache__`: на DrvFS (`/mnt/c`) устаревший `.pyc` отдаёт результат
**предыдущей** мутации.

- [x] **Step 6: Коммит**

```bash
git add simintech_api/script_probe.py tests/unit/test_script_probe.py
git commit -m "feat(probe): опознание цели по единственной изменившейся записи с меткой"
```

---

## Task 5: Мост: снимок вместо чтения главной страницы

**Files:**
- Modify: `simintech_api/core/script_bridge.py`
- Modify: `simintech_api/script_probe.py` (`build_probe_script` получает метку)
- Test: `tests/unit/test_script_bridge.py` (`FakeEnv` расширяется)
- Test: `tests/unit/test_script_probe.py` (правки `build_probe_script` и удаление старой механики)

> **Кодовые блоки ниже — первоначальная версия, а не итог.** Задача прошла два
> независимых ревью (соответствие и атака) и три круга правок; итог — коммиты
> `d592849`, `75b7c06`, `e1d9ab6`, и **источник истины теперь код**, а не эти
> сниппеты. Ниже перечислено, что изменилось и почему, чтобы сниппет не был
> восстановлен как «то, что было задумано».

**Что изменилось после ревью (и чем подтверждено).**

| Изменение | Почему | Чем держится |
|---|---|---|
| Хвост отказа строится **по факту метки** (`token_present_in`), а не по «вернулась ли запись цели» | в момент отказа `SetPageScript` уже уничтожил прежний скрипт страницы, и вызывающий обязан знать, осталась ли в проекте проба: от этого зависит, идти ли ему за копией | четыре ветки, по тесту на каждую; мутация «выдать отсутствие за факт, не проверив» краснит |
| Четвёртое состояние хвоста: «метки нет, но и об этой странице снимок молчит» | при неопознанной записи цели отсутствие метки **не доказывает** отсутствия пробы — записи этой страницы может не быть в выгрузке вовсе; три состояния печатали противоречие в одном сообщении | фейк `page_scripts_not_serialized` + тест; без него параметр выживал мутацию |
| Перед записью страница **проверяется чтением**, при неудаче — отказ **до** записи | молчаливый отказ — замеренный контракт среды; без проверки запись уходит в **чужую** страницу и уничтожает её скрипт (измерено атакой) | `test_run_probe_does_not_write_to_a_foreign_page`, мутация «снять перечит» |
| `_describe_mismatch` перечисляет **все** расхождения, а не первое | ранний `return` прятал диагноз «изменились чужие записи» ровно в том сценарии, ради которого проверка писалась | тест на два одновременных расхождения + мутация |
| Расхождение **числа** записей — не отказ, если метки нет нигде и прежний текст записи цели в снимке есть; иначе отказ. Плюс `UserWarning` | рост числа записей — законное поведение среды (активация страницы создаёт записи, замер 14), а позиционное сравнение при разных длинах всё равно ничего не доказывало | три теста (успех с предупреждением и два отказа), три мутации |
| `decode_xprt_value` отвергает `#1114112` и суррогаты `#55296`…`#57343`; `_dump_records` оборачивает клиентские ошибки | сырые `ValueError`/`UnicodeEncodeError`/`FileNotFoundError` летели **вне иерархии** и молчали о состоянии проекта | параметризованный тест + мутации |
| Фейк перестал повторять допущение кода: `pages_added_by_run`, `page_scripts_not_serialized`, `restore_writes_other_text`, `set_current_page_is_ignored`, полный `_SPECIAL` | фейк, повторяющий допущение кода, не может его опровергнуть — из-за этого ложный отказ в сценарии с активацией был невидим тестам | каждый флаг держит свой тест |
| Совет «очистите скрипт этой страницы» убран | проверка идёт по всем записям, а номеров страниц в выгрузке нет — совет мог указывать не на ту страницу | — |
| Предупреждение о расхождении длин выдаётся **после** `try`, а его собственное исключение перехватывается (`except Warning`) | с фильтром `-W error` предупреждение внутри `try` попадало в `except Exception` и превращало **успешный** возврат в ложный отказ с текстом о несделанном возврате; а без перехвата `-W error` роняет сам вызов `warnings.warn`. Решение осознанное, не измеренное: `-W error` означает «предупреждение = баг в моём коде», а здесь предупреждение описывает **законное** событие среды, и ронять из-за него удачный возврат хуже, чем не показать уведомление | тест, красный на прошлом коммите 3/3 и зелёный сейчас; плюс сенсор к `stacklevel` |

- [x] **Step 1: Расширить фейк до многопстраничного проекта**

`FakeEnv` в `tests/unit/test_script_bridge.py` моделирует **одну** страницу.
Нужны минимум две и переходы между ними — иначе поведение из замера 10
(«стирается скрипт неглавной страницы») невоспроизводимо и тест его не поймает.

Заменить в `FakeEnv.__init__` поля скрипта на список страниц:

```python
    def __init__(self, *, pages=(MAIN, "Container"), installed="seterrorflag(0);",
                 other_scripts=None, current_index=0, time_grows=True,
                 initial_time=0.0, writes_result=True,
                 script_result=END_MARKER + "\n",
                 restore_raises=None, restore_is_ignored=False):
        #: Имена страниц — как их пишет выгрузка; первая всегда главная.
        self.pages = list(pages)
        #: Скрипты страниц. Имя `installed` сохранено намеренно: на нём стоят
        #: шесть существующих тестов, и оно честно называет, что это — скрипт,
        #: лежавший в проекте до пробы.
        self.scripts = [installed] + list(
            other_scripts if other_scripts is not None
            else [""] * (len(self.pages) - 1))
        self.current_index = current_index
        # остальные поля (`time_grows`, `initial_time`, `writes_result`,
        # `script_result`, `restore_raises`, `restore_is_ignored`, `calls`,
        # `_stepped`) сохраняются как есть
```

`SaveProjectXML` пишет **все** страницы:

```python
        if name == "SaveProjectXML":
            body = "".join(
                f"<page>\n <name>{'`' + page + '`' if page else ''}</name>\n"
                f" <script>{self._record(i)}</script>\n</page>\n"
                for i, page in enumerate(self.pages))
            Path(args[1]).write_text(body, encoding="utf-8")
            return 1
        if name == "SetPageScript":
            if self.restore_raises is not None and args[1] == self.restore_raises:
                raise OSError("COM недоступен")
            if self.restore_is_ignored and "createfile(" not in args[1]:
                return 1
            if self.writes_are_not_serialized:
                return 1
            # запись, пришедшая сырой, установка заменяет целиком
            self.raw_scripts.pop(self.current_index, None)
            self.scripts[self.current_index] = args[1]
            return 1
        if name == "GetCurentPage":
            return 1000 + self.current_index
        if name == "SetCurrentPage":
            self.current_index = int(args[1]) - 1000
            return 1

    def _record(self, index):
        """Значение `<script>` для страницы: сырое, если помечена повреждённой."""
        if index in self.raw_scripts:
            return self.raw_scripts[index]
        return _encode_value(self.scripts[index])
```

Плюс в `__init__` — модель повреждённой записи:

```python
        #: Индексы страниц, чьи скрипты в выгрузке идут СЫРЫМ текстом, который
        #: кодек покрывает не весь. Модель повреждённой записи: установка пробы
        #: такую запись заменяет целиком, поэтому сырость снимается при записи.
        self.raw_scripts = {}
```

- [x] **Step 2: Написать падающий тест — регрессия на дефект**

```python
def test_run_probe_does_not_touch_script_of_another_page(tmp_path):
    """Та самая регрессия: проба уходит в текущую страницу, а не в главную.

    Измерено на поставке: `SetPageScript` пишет в **текущую** страницу, а
    прежний скрипт мост читал с главной, поэтому чтение внутри контейнера
    стирало скрипт этого контейнера и рапортовало об успешном восстановлении.
    """
    env, bridge = _bridge(installed="", other_scripts=["STAYS_HERE"],
                          current_index=1)
    bridge.run_probe('writelnutf8(fid, "x");', tmp_path / "probe.txt")
    assert env.scripts[1] == "STAYS_HERE", "скрипт текущей страницы потерян"
    assert env.scripts[0] == "", "тронули главную страницу, хотя проба шла не в ней"


def test_run_probe_raises_unsafe_when_no_record_changed(tmp_path):
    """Скрипт текущей страницы не попал в выгрузку → цель не установлена.

    Модель: у страницы нет записи `<script>`, поэтому установка пробы в
    выгрузке ничего не меняет — вернуть прежний скрипт нечем.
    """
    env, bridge = _bridge()
    env.writes_are_not_serialized = True
    with pytest.raises(ScriptBridgeUnsafeStateError) as exc:
        bridge.run_probe('writelnutf8(fid, "x");', tmp_path / "probe.txt")
    assert "ни одна скриптовая запись" in str(exc.value)


def test_run_probe_never_restores_partially_decoded_record(tmp_path):
    """Запись цели, которую кодек покрывает не весь, — отказ, а не «как выйдет».

    `decode_xprt_value` разбирает куски и коды, но не проверяет покрытие: если
    в записи есть текст вне кусков и кодов, разбор теряет символы и вернул бы на
    место **усечённый** скрипт. Ровно против этого в модуле есть `leftover_of`,
    и здесь проверяется, что мост им пользуется: цель найдена, но восстанавливать
    нечем — и повторной записи не происходит.
    """
    env, bridge = _bridge(installed="", other_scripts=["STAYS_HERE"],
                          current_index=1)
    env.raw_scripts = {1: "abc`не покрыто`"}   # текст вне кусков и кодов
    with pytest.raises(ScriptBridgeUnsafeStateError) as exc:
        bridge.run_probe('writelnutf8(fid, "x");', tmp_path / "probe.txt")
    assert "нераспознанный текст" in str(exc.value)
    assert len(env.set_page_script_calls()) == 1, (
        "после отказа восстановление всё равно писало скрипт")
```

Для последнего теста в `FakeEnv` нужен ещё один переключатель: он моделирует
случай «установка прошла, но в выгрузке этого не видно» — тогда ни одна запись
не изменится, и цель опознать нечем. Убрать `<script>` из выгрузки **нельзя**:
тогда разбор снимка откажет раньше по расхождению числа записей и страниц, и
проверялась бы не та ветка.

```python
        #: Модель «установленный скрипт в выгрузку не попадает»: вызов
        #: проходит, состояние меняется, а выгрузка этого не отражает.
        self.writes_are_not_serialized = False
```

и в `SetPageScript`, перед записью в список:

```python
            if self.writes_are_not_serialized:
                return 1
```

- [x] **Step 3: Убедиться, что тесты падают**

Run: `python3.11 -m pytest tests/unit/test_script_bridge.py -q`
Expected: FAIL — у `FakeEnv` нет `pages`/`scripts`; `run_probe` зовёт `GetOpenedFileName`

- [x] **Step 4: Научить `build_probe_script` метке**

В `simintech_api/script_probe.py` — сигнатура и первая строка возврата:

```python
def build_probe_script(body: str, result_path: str, token: str) -> str:
    # докстринг и проверка пути — как сейчас, без изменений
    return (
        f"{token}\n"
        "if firststep then begin\n"
        "  var fid: integer;\n"
        f'  fid = createfile("{literal_path}", -1);\n'
        f'  writelnutf8(fid, "{BEGIN_MARKER}");\n'
        f"{indented}"
        f'  writelnutf8(fid, "{END_MARKER}");\n'
        "  freeobject(fid);\n"
        "end;\n"
    )
```

Остальное тело функции не меняется; `_encode_value` в тестах уже умеет
кодировать перевод строки, так что метка в выгрузке окажется в первой строке
значения `<script>`.

**Пять существующих тестов сборки скрипта придётся поправить — в первой версии
плана это не было сказано, и они ломаются.** `token` стал обязательным
параметром, а `test_build_uses_firststep_not_initialization` утверждал
`script.lstrip().startswith("if firststep then")`, что после метки первой строкой
становится ложью. Передать во все пять вызовов один и тот же `PROBE_TOKEN`, а
проверку переписать на позиции строк: `lines[0] == PROBE_TOKEN`,
`lines[1] == "if firststep then begin"` — смысл «тело под `firststep`, а не под
`initialization`» при этом сохраняется.

Плюс добавить `test_build_puts_token_on_first_line_before_the_body`: шаг меняет
именно это, а теста на это в плане не было.

Докстринг дополнить:

```python
    Метка ставится **первой строкой**, до исполняемого тела: тогда она остаётся
    в скрипте, даже если тело не скомпилировалось, — а именно этот случай и
    надо уметь опознать, чтобы вернуть прежний скрипт.
```

- [x] **Step 5: Переписать `run_probe`**

В `simintech_api/core/script_bridge.py` — убрать `capture_script` целиком,
добавить:

```python
    def _dump_records(self) -> List[str]:
        """Снять скриптовые записи проекта выгрузкой `.xprt`.

        Другого способа увидеть скрипты страниц у COM нет: идентификаторов
        страниц в выгрузке не бывает, а `SetPageScript` пишет в текущую
        страницу, ничего не сообщая о прежнем содержимом.

        Кодировку разбирает `decode_xprt` — **до** разбора разметки и по
        байтам: `read_text` с `errors="replace"` подменил бы испорченный байт
        на U+FFFD и превратил порчу файла в тихую правку скрипта.
        """
        with tempfile.TemporaryDirectory(prefix="simintech-bridge-") as tmp:
            path = Path(tmp) / "page.xprt"
            self._client.call("SaveProjectXML", self._project_id, str(path))
            text = decode_xprt(path.read_bytes())
        return parse_xprt_script_records(text)
```

`run_probe`:

```python
    def run_probe(self, body: str, result_path: Path) -> ProbeResult:
        """Выполнить `body` в проекте и вернуть разобранный результат.

        Порядок продиктован замерами (спецификация 2026-09-22):

        1. запомнить **COM ID текущей страницы** и снять снимок скриптовых
           записей проекта;
        2. убедиться, что в снимке нет **маркера** пробного скрипта
           (`TARGET_TOKEN_PREFIX`), и сгенерировать метку цели: маркер ловит
           остаток предыдущего запуска, у которого nonce другой, — а это не
           гипотеза, а реальный случай;
        3. поставить пробу с меткой; снять второй снимок и найти запись,
           которую изменила установка, — только она и есть цель;
        4. удалить прежний файл результата и запустить расчёт;
        5. вернуть прежний скрипт **в ту страницу, которую изменили**, и
           сверить снимки;
        6. если цель не установлена — не угадывать: `ScriptBridgeUnsafeStateError`
           прямо говорит, что в проекте остался пробный скрипт.
        """
        target_page_id = int(self._client.call("GetCurentPage", self._project_id))
        before = self._dump_records()
        if token_present_in(before, TARGET_TOKEN_PREFIX):
            raise ScriptBridgeUnsafeStateError(
                "в снимке уже есть маркер пробного скрипта "
                f"({TARGET_TOKEN_PREFIX!r}): в проекте остался скрипт "
                "предыдущего запуска. Проба не начата — проект не тронут; "
                "разберитесь со скриптом страницы перед следующим расчётом.")
        token = new_target_token()
        script = build_probe_script(body, str(result_path), token=token)

        target = None
        original = None
        probe_error = None
        try:
            self.install_script(script)
            after = self._dump_records()
            target = find_changed_script_record(before, after, token)
            raw_original = before[target]
            if leftover_of(raw_original):
                raise ScriptBridgeUnsafeStateError(
                    f"скриптовая запись {target} содержит нераспознанный текст "
                    "выгрузки: восстановление небезопасно — кодек покрывает не "
                    "весь текст, и на место вернулся бы усечённый скрипт")
            original = decode_xprt_value(raw_original)
            result_path.unlink(missing_ok=True)
            self._start_and_wait()
            result = self._read_result(result_path)
        except BaseException as exc:
            probe_error = exc
            raise
        finally:
            if target is not None and original is not None:
                self._restore_script(before, target, original, target_page_id,
                                     probe_error)
        return result
```

`_restore_script` и `_describe_mismatch`:

```python
    def _restore_script(self, before: List[str], target: int, original: str,
                        target_page_id: int,
                        probe_error: Optional[BaseException]) -> None:
        """Вернуть прежний скрипт в **ту самую** страницу и сверить снимки.

        `SetPageScript` пишет в текущую страницу, поэтому перед возвратом
        текущая страница возвращается на `target_page_id`: её могла увести и
        сама модель (`gotopage` существует). Сверка идёт по снимку, а не по
        собственному чтению: прежняя проверка сравнивала главную страницу саму
        с собой и потому не видела потери.
        """
        problem = None
        target_intact = False
        try:
            current = int(self._client.call("GetCurentPage", self._project_id))
            if current != target_page_id:
                self._client.call("SetCurrentPage", self._project_id,
                                  target_page_id)
            self.install_script(original)
            verify = self._dump_records()
            target_intact = (len(verify) == len(before)
                             and verify[target] == before[target])
            problem = self._describe_mismatch(before, verify, target)
        except Exception as exc:  # noqa: BLE001
            problem = f"вызов не прошёл: {exc}"
        if problem is None:
            return
        # Хвост выбирается по типу расхождения, а не пишется один на оба: если
        # запись цели вернулась, пробного скрипта в проекте уже нет, и фраза о
        # нём была бы ложью, которую пользователь прочитает как факт.
        if target_intact:
            tail = ("Запись цели вернулась на место, но состояние проекта "
                    "изменилось вне пробы — проверьте скрипты страниц.")
        else:
            tail = ("В проекте остался пробный скрипт — проверьте его перед "
                    "следующим расчётом.")
        message = f"прежний скрипт страницы не восстановлен: {problem}. {tail}"
        if probe_error is not None:
            message = f"проба уже завершилась отказом ({probe_error}), и " + message
        raise ScriptBridgeUnsafeStateError(message) from probe_error

    def _describe_mismatch(self, before: List[str], verify: List[str],
                           target: int) -> Optional[str]:
        """Чем снимок после возврата отличается от снимка до установки.

        Сравниваются **скриптовые записи**, а не выгрузки: между установкой и
        возвратом шёл расчёт, и он переписывает вычисленные значения свойств
        (измерено: 21 запись из 67, 5.8 млн символов), а скрипты не трогает.
        """
        if len(verify) != len(before):
            return (f"число скриптовых записей изменилось: {len(before)} -> "
                    f"{len(verify)}")
        if verify[target] != before[target]:
            return f"скрипт записи {target} не совпал с прежним"
        others = [i for i in range(len(before))
                  if i != target and before[i] != verify[i]]
        if others:
            return f"изменились чужие скриптовые записи: {others}"
        return None
```

Импорты дополнить: `List` из `typing`, `decode_xprt_value`,
`find_changed_script_record`, `leftover_of`, `new_target_token`,
`parse_xprt_script_records`, `ScriptBridgeUnsafeStateError`,
`TARGET_TOKEN_PREFIX`, `token_present_in`; убрать `read_page_script`.

**Почему проверка `leftover_of` стоит именно на записи цели и именно здесь.**
`decode_xprt_value` разбирает куски и коды, но не проверяет, что покрыт **весь**
текст: непокрытый остаток означает, что разбор теряет символы, и на место
вернулся бы усечённый скрипт — то есть молчаливая порча ровно там, где вся
архитектура построена на её запрете. Проверять заранее, «до установки, у всех
записей сразу», не нужно и вредно: сравнение снимков идёт по сырому тексту,
декодируется **только** запись цели, поэтому нечитаемая чужая запись ничему не
мешает, а предварительная проверка всех записей отказывала бы в пробе на проекте
с одной экзотической страницей. Цена такой проверки — доступность, выигрыш —
ноль.

- [x] **Step 6: Убрать старую механику чтения**

Теперь, когда вызывающий уходит, убрать и то, что он звал:

- `simintech_api/script_probe.py`: функция `read_page_script` целиком вместе с
  её докстрингом и regex `_PAGE_RE`;
- `tests/unit/test_script_probe.py`: пять тестов `test_read_page_script_*` и
  всё, что после их удаления осталось неиспользованным (проверить `flake8`: он
  поймает F401 на осиротевшем импорте или помощнике);
- `tests/unit/test_script_bridge.py`: тест `test_wrong_page_is_never_substituted_for_main`.

Всего при удалении снимается **восемь** определений `def test_` (четыре в
`test_script_probe.py`, четыре в `test_script_bridge.py`) плюс два
переименовываются с сохранением смысла:
`test_capture_uses_temporary_directory_and_removes_it` →
`test_dump_records_uses_temporary_directory_and_removes_it` и
`test_read_page_script_decodes_real_value_without_backticks_or_codes` →
`test_decode_xprt_value_decodes_real_value_without_backticks_or_codes`.

Они проверяли абстракцию «найди страницу по имени» — ту самую, из-за которой
чтение неглавной страницы стирало её скрипт. Держать её ради количества тестов
значило бы сохранить и неправильную модель.

Run: `python3.11 -m pytest tests/unit -q && python3.11 -m flake8 simintech_api tests --max-line-length=88 --extend-ignore=E203,W503`
Expected: PASS, 0 ошибок

- [x] **Step 7: Переписать тесты, привязанные к `capture_script`**

Удалить тесты, проверяющие снятую абстракцию (`test_capture_script_*`,
`test_wrong_page_is_never_substituted_for_main`,
`test_run_probe_aborts_without_touching_project_when_capture_fails`), и заменить
их по смыслу:

```python
def test_run_probe_does_not_touch_project_when_token_already_present(tmp_path):
    """Метка из прошлого запуска (или коллизия) — отказ ДО установки пробы."""
    env, bridge = _bridge()
    env.scripts[0] = "//SCRIPT_BRIDGE_TARGET_deadbeefdeadbeef"
    with pytest.raises(ScriptBridgeUnsafeStateError):
        bridge.run_probe('writelnutf8(fid, "x");', tmp_path / "probe.txt")
    assert env.set_page_script_calls() == [], "проект тронут до проверки метки"


def test_run_probe_verifies_by_snapshot_not_by_reading_main_page(tmp_path, monkeypatch):
    """Возврат сверяется снимком: смолчавший `SetPageScript` обязан быть замечен."""
    env, bridge = _bridge(restore_is_ignored=True)
    with pytest.raises(ScriptBridgeUnsafeStateError) as exc:
        bridge.run_probe('writelnutf8(fid, "x");', tmp_path / "probe.txt")
    assert "не восстановлен" in str(exc.value)
```

Остальные тесты (`test_run_probe_returns_complete_result`,
`..._restores_script_even_on_failure`, `..._reports_frozen_model_time` и т. д.)
сохраняются; им нужен лишь новый `FakeEnv`.

- [x] **Step 8: Прогнать весь набор, линтеры и типы**

Run:
```bash
python3.11 -m pytest tests/unit -q
python3.11 -m flake8 simintech_api tests --max-line-length=88 --extend-ignore=E203,W503
python3.11 -m mypy && python3.11 -m mypy --platform win32
```
Expected: PASS, 0 ошибок, `Success: no issues found in 17 source files` ×2

**Мутационная проверка сенсоров моста — обязательна, и вот почему.** Две ветки
плана первой версии не были прикрыты **ничем**, и это измерено исполнителем:
мутация «убрать возврат текущей страницы на `target_page_id`» проходила весь
набор, хотя возврат в **ту самую** страницу — центральное обещание правки;
мутация «сверять `verify` с самим собой» ловилась, но список сенсоров плана её
не называл. Прогони пять мутаций, каждая должна покраснеть:

| Мутация | Ожидание |
|---|---|
| убрать проверку `leftover_of` | красный тест нерaспознанной записи, и `SetPageScript` вызывается второй раз |
| убрать предустановочную проверку маркера | `DID NOT RAISE` — проект тронут, хотя состояние уже подозрительно |
| убрать `SetCurrentPage(target_page_id)` | красный тест «прежний скрипт вернулся в ту же страницу» |
| сверять `verify` с `before` вместо `verify` | красные тесты неудавшегося возврата |
| один хвост сообщения на оба расхождения | красный тест «чужая запись изменилась — пробный скрипт не виноват» |
| снять `warnings.warn` о расхождении длин | красный тест «терпимое расхождение выдаёт предупреждение» |
| снять проверку «прежний текст записи цели есть в снимке» | красный тест отказа при пропавшей записи |
| снять проверку «метки нет нигде» при выросшем снимке | красный тест отказа при оставшейся метке |
| снять запрет суррогатов в `decode_xprt_value` | красные два суррогатных параметра |
| снять перечит `GetCurentPage` перед возвратом | красный тест «не писать в чужую страницу» |
| выдавать отсутствие пробы за факт без снимка | красный тест «снимок молчит — не утверждать отсутствие» |

Последние пять строк добавлены после второго и третьего кругов правок: каждый
сенсор появился вместе с ветвью, которую он держит, и ни один не был в плане
изначально.

- [x] **Step 9: Коммит**

```bash
git add simintech_api/core/script_bridge.py simintech_api/script_probe.py tests/unit/test_script_bridge.py tests/unit/test_script_probe.py
git commit -m "fix(bridge): возврат скрипта в ту страницу, которую изменили"
```

---

## Task 6: Живой прогон

**Files:**
- Modify: `tests/integration/test_topology_live.py` (+регрессия)
- Modify: `tests/integration/test_script_bridge_live.py` (`capture_script` → снимки)

- [x] **Step 1: Написать падающий живой тест — скрипт выжил**

В `tests/integration/test_topology_live.py`:

```python
def test_reading_topology_inside_container_keeps_its_script(client, tmp_path):
    """Регрессия: чтение топологии внутри контейнера не трогает его скрипт.

    Измерено 2026-09-22 на копии демо вендора: до правки скрипт страницы
    субмодели `acrms_Circuit1` (939 символов, вендорский скрипт экспорта
    топологии) заменялся пустотой, а `read_topology` возвращал свои 35
    объектов, 64 порта и 32 связи — то есть дефект выглядел как успех.

    Сверка идёт по **сырым выгрузкам**, а не через средства моста: только
    независимое чтение и может поймать, что мост вернул не то, что взял.
    """
    if not os.path.exists(VENDOR_DEMO):
        pytest.skip(f"нет демо вендора: {VENDOR_DEMO}")
    work = tmp_path / "demo.prt"
    shutil.copy2(VENDOR_DEMO, work)
    project = Project.open(client, str(work))
    try:
        container = project.get_main_page().find_block(VENDOR_CONTAINER)
        assert container is not None
        project.submodel_page(container.id).activate()

        before = _script_records(client, project, tmp_path / "b.xprt")
        topology = read_topology(client, project.id, tmp_path / "t.txt")
        after = _script_records(client, project, tmp_path / "a.xprt")

        assert len(topology.objects) == 35, "проба перестала читать контейнер"
        # Число страниц пинится к демо, а не выводится из сравнения снимков:
        # before и after разбирает **один** разбор, и систематический пропуск
        # страницы оставил бы `before == after` зелёным. Замер живого прогона:
        # 83 страницы и столько же скриптовых записей (разбор сам сверяет эти
        # числа и на расхождении отказывает).
        #
        # 83, а не 67 из более раннего замера: число записей зависит от того,
        # успели ли отработать инициализационные скрипты страниц — они создают
        # страницы. Это **свидетельство конкретной сериализации этой модели**, а
        # не инвариант: инвариант продакшна — «число записей не изменилось,
        # изменилась ровно одна, и в ней наша метка».
        assert len(before) == 83, (
            f"разбор снимка нашёл {len(before)} страниц вместо измеренных 83: "
            "сверять снимки не с чем")
        assert len(after) == 83, (
            f"после пробы разбор нашёл {len(after)} страниц вместо 83")
        lost = [i for i in range(len(before)) if before[i] != after[i]]
        if lost:
            raise AssertionError(
                f"скрипты страниц изменились на записях {lost}; "
                f"в записи {lost[0]} было {before[lost[0]][:60]!r}, "
                f"стало {after[lost[0]][:60]!r}")
    finally:
        project.close()
```

Хелпер рядом с тестом:

```python
def _script_records(client, project, path) -> list:
    """Сырые скриптовые записи выгрузки — независимо от средств моста.

    Кодировку разбирает библиотечный `decode_xprt` (по байтам, с учётом BOM), а
    не `read_text`: подстановка U+FFFD скрыла бы порчу файла, ради обнаружения
    которой тест и написан.
    """
    client.call("SaveProjectXML", project.id, str(path))
    return parse_xprt_script_records(decode_xprt(path.read_bytes()))
```

- [x] **Step 2: Убедиться, что тест красный на прежнем коде**

Отложить правку Task 5 (или прогнать на `git stash`): тест обязан упасть с
сообщением о изменившейся записи 1 и `было '`initialization`#13#10...`.

Run: `python -m pytest tests/integration/test_topology_live.py -m integration -q -k keeps_its_script -s`
Expected: FAIL на непоправленном мосте (это и есть доказательство, что тест
держит дефект), PASS после правки

**Как получен красный прогон.** Репозиторий скопирован в `/tmp/oldtree` и
переключён на родителя починки; туда положены новые тестовые файлы. Отдельно
проверено, что импортируется **копия**, а не editable-установка: иначе прогон
проверял бы не тот код и «красный» был бы фиктивным.

**Измеренный красный прогон** (на `945a89f`, родителе починки моста): падение на
записи **2** — `было '`include "export_sheme_functions.inc";`…#13#10…initiali',
стало ''`. Запись 2, а не 1, и **пусто** вместо скопированного текста главной
страницы: старый `capture_script` брал скрипт главной страницы, а он на этом демо
пуст, и возвращал эту пустоту в текущую страницу. Индекс и число страниц —
свидетельства этой сериализации, инвариантом они не являются.

- [x] **Импорты в живых тестах.** Оба файла придётся дополнить — сниппеты ниже
используют то, чего в них сейчас нет:

- `tests/integration/test_topology_live.py`: `parse_xprt_script_records` из
  `simintech_api.script_probe`, `decode_xprt` из `simintech_api.catalog`
  (рядом с существующим импортом `parse_topology`), плюс хелпер `_script_records`;
- `tests/integration/test_script_bridge_live.py`: `parse_xprt_script_records` и
  `decode_xprt` для того же хелпера.

Хелпер в обоих файлах свой (копия, а не импорт): живые тесты не должны зависеть
друг от друга.

**Третий живой тест — снять, а не переписывать.** Помимо двух вызовов
`bridge.capture_script()`, которые заменяются снимками, в файле есть
`test_bridge_reports_missing_main_page_instead_of_guessing`: он проверяет ровно
ту абстракцию («главную страницу опознать не удалось»), которую Task 5 удалил.
Переписывать его нечем — снимать.

**Step 3: Переписать живой тест моста**

В `tests/integration/test_script_bridge_live.py` три использования
`bridge.capture_script()` заменить на снимок до/после:

```python
def test_probe_restores_page_script(client, tmp_path):
    """Прежний скрипт страницы возвращается — сверка по сырой выгрузке."""
    project = Project.from_template(client)
    project.set_calc_end_time(1.0)
    page = project.get_main_page()
    page.activate()
    client.call("SetPageScript", project.id, SCRIPT_WITH_OPERATORS, 1)
    try:
        bridge = ScriptBridge(client, project.id)
        before = _records(client, project, tmp_path / "b.xprt")
        bridge.run_probe('writelnutf8(fid, "x");', tmp_path / "probe.txt")
        after = _records(client, project, tmp_path / "a.xprt")
        assert after == before, "скрипт страницы после пробы не совпал с прежним"
    finally:
        project.close()
```

Хелпер `_records` — тот же, что в `test_topology_live.py` (скопировать, а не
импортировать: живые тесты не должны зависеть друг от друга).

- [x] **Step 4: Прогнать живой набор**

Run: `python -m pytest tests/integration -m integration -q`
Expected: PASS, включая `test_probe_matches_vendor_reference_inside_container`
(35 объектов, 64 порта, 32 связи) и новый тест

- [x] **Step 5: Коммит**

```bash
git add tests/integration/
git commit -m "test(bridge): живая регрессия — скрипт неглавной страницы выживает"
```

---

## Task 7: Документы

**Files:**
- Modify: `docs/api.md`, `CLAUDE.md`, `docs/reference/com_api_inventory.md`,
  `docs/superpowers/specs/2026-09-22-page-script-loss-design.md`

- [x] **Step 1: Снять предупреждение в `api.md`**

Абзац «⚠ **Чтение неглавной страницы переписывает её скрипт скриптом главной.**»
заменить на описание того, как мост теперь опознаёт цель: снимок выгрузки до и
после установки, единственная изменившаяся запись, метка, и `unsafe`-отказ, если
цель не установлена.

- [x] **Step 2: Обновить факты в `CLAUDE.md`**

Абзац про дефект моста (строки ~218–222) заменить на: «мост опознаёт страницу по
единственной изменившейся записи выгрузки; если цель не установлена —
`ScriptBridgeUnsafeStateError`». Добавить факт: «`capture_script` убран: надёжного
способа прочитать *текущий* скрипт страницы не существует».

- [x] **Step 3: Обновить статус `GetCurentPage` в инвентаре**

В `docs/reference/com_api_inventory.md`: `GetCurentPage` помечен `➖` (проверено
частично). Замер 1 подтвердил его работу на активации страницы — пометить `✅` и
указать, что именно проверено.

- [x] **Step 4: Синхронизировать спеку**

В спеке: снять пометки «на ревью» там, где решения приняты реализацией (имена
функций, место метки) и записать фактическое поведение, если оно отличается от
задуманного.

- [x] **Step 5: Финальные гейты**

Run:
```bash
python3.11 -m pytest tests/unit -q
python3.11 -m flake8 simintech_api tests --max-line-length=88 --extend-ignore=E203,W503
python3.11 -m mypy && python3.11 -m mypy --platform win32
python -m pytest tests/integration -m integration -q    # Windows
```
Expected: всё зелёное

- [x] **Step 6: Коммит**

```bash
git add docs/ CLAUDE.md
git commit -m "docs(bridge): опознание цели вместо чтения главной страницы"
```

---

## Что проверить перед merge

Четыре утверждения, каждое из которых должно быть подтверждено **тестом или
измерением**, а не чтением кода:

1. `unsafe` действительно означает «цель не установлена» — во всех четырёх
   случаях и без исключений;
2. после успешного опознания цели возврат **никогда не угадывает** страницу: он
   идёт либо в `target_page_id`, либо в `target_page_id` после возврата текущей
   страницы;
3. повреждённая запись не может пройти путь `decode → restore`: `leftover_of`
   стоит на пути и покрыт тестом;
4. на демо вендора внутри `acrms_Circuit1` — 35 объектов, 64 порта, 32 связи, и
   исходный скрипт страницы (939 символов) не изменился ни на байт.

## Что этот план не делает

- **`ProjectStop` после пробы** — следующая работа по порядку из
  `simintech-mcp/docs/roadmap-agentic-ecosystem.md`. Смешивать её с этой нельзя:
  здесь меняется способ опознания страницы, там — жизненный цикл расчёта, и
  диагностика одного дефекта мешала бы диагностике другого.
- **Доказательство `port_idx == getportindex(peer)`** и **расширение фильтра
  типов** — после стабилизации моста: оба требуют живых прогонов, а гонять их на
  мосте, способном испортить страницу, значит добавлять шум в результаты.
- **Полная проверка кодека на произвольных скриптах.** Замеры 7 и 8 покрывают
  вендорский скрипт (939 символов) и синтетический злой; этого достаточно для
  починки, но не является доказательством для любых входов.
