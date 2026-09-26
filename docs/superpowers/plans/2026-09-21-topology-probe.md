# Topology Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дать библиотеке чтение топологии модели — объекты, порты и связи текущего контейнера — поверх уже работающего `ScriptBridge`.

**Architecture:** Чистая часть (сборка тела пробы на встроенном языке и строгий однопроходный разбор результата) живёт в `simintech_api/topology.py` без COM и попадает в точечный mypy-гейт. COM-часть — тонкая обёртка `read_topology` в `simintech_api/core/topology.py` над `ScriptBridge.run_probe`; транспортной логики она не дублирует.

**Tech Stack:** Python 3.11, pytest. Новых зависимостей нет.

**Основание:** `docs/superpowers/specs/2026-09-21-topology-probe-design.md`.

**Вне области этого плана:** субмодели, координаты, правка портов, выход в MCP.

---

## Файловая структура

| Файл | Ответственность |
|---|---|
| `simintech_api/topology.py` (создать) | Протокол: модель данных, канонический ключ связи, `build_topology_probe()`, `parse_topology()`. Без COM и без файловой системы |
| `simintech_api/exceptions.py` (изменить) | `TopologyError` |
| `simintech_api/__init__.py` (изменить) | Экспорт `TopologyError` |
| `pyproject.toml` (изменить) | `simintech_api/topology.py` — в `[tool.mypy] files` |
| `simintech_api/core/topology.py` (создать) | `read_topology(client, project_id, result_path) -> Topology` |
| `tests/unit/test_topology.py` (создать) | Разбор: happy path, тринадцать защит, канонизация |
| `tests/integration/test_topology_live.py` (создать) | Живой прогон и сверка с COM |
| `docs/api.md`, `CLAUDE.md` (изменить) | Описание |

**Протокол** (три фазы, поля через табуляцию):

```
object<TAB>имя<TAB>класс
port<TAB>имя объекта<TAB>индекс<TAB>направление<TAB>имя порта
conn<TAB>имя объекта<TAB>индекс<TAB>имя объекта<TAB>индекс
```

---

## Task 1: Исключение TopologyError

**Files:**
- Modify: `simintech_api/exceptions.py`
- Test: `tests/unit/test_topology.py`

- [ ] **Step 1: Написать падающий тест**

Создать `tests/unit/test_topology.py`:

```python
"""Разбор протокола топологии: грамматика, фазы, ссылки, канонизация."""

import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from simintech_api.exceptions import SimInTechError, TopologyError  # noqa: E402


def test_topology_error_is_simintech_error():
    assert issubclass(TopologyError, SimInTechError)
```

**Из этого сниппета снято три элемента — все три оказались дефектами плана,
и все три выявились при исполнении:**

- `import pytest` — в этой задаче pytest не используется ни одним тестом, и
  flake8 даёт на нём `F401`. Возвращать его надо тогда, когда появится первый
  тест с `pytest.raises` (Task 4), а не «на будущее». `noqa: E402` в сниппете
  закрывал только E402, но не F401, — то есть дословный файл плана не проходил
  собственный линт репозитория.
- `test_topology_error_is_exported_from_package_root` — **строго избыточен**, а
  его docstring ложен. `test_surface` собирает классы исключений динамически
  (`obj.__module__ == exceptions.__name__`), поэтому `TopologyError` попадает в
  его набор сам, и там уже проверяются наличие в корне, наличие в `__all__` и
  **тождество ссылки** (`getattr(simintech_api, name) is getattr(exceptions,
  name)`). Утверждение снятого теста — подмножество этой проверки. Мутация
  (снятие импорта из `__init__.py`) роняет `test_surface` без него.
  `test_topology_error_is_simintech_error` при этом **остаётся**: наследование
  от `SimInTechError` в `test_surface` не утверждается — там `issubclass(obj,
  Exception)` стоит фильтром, а не проверкой, — и больше нигде не закреплено.
- `test_parse_topology_is_importable` — импортирует `parse_topology`, которой в
  этой задаче ещё нет: тест заведомо красный на шаге 4 своей же задачи.
  Импортируемость доказывается в Task 3, где тесты импортируют `parse_topology`
  напрямую. Тест не перенесён, а отброшен — отдельно проверять нечего.

Файл `simintech_api/topology.py` в этой задаче состоит из docstring и
`from __future__ import annotations`: импорт `TopologyError` приезжает в Task 3
вместе с первым `raise`, а не лежит заготовкой под `# noqa` с обоснованием,
которое в Task 1 неверно («используется ниже» — ниже пусто), а после Task 3
станет лишним, и flake8 об этом не скажет.

- [ ] **Step 2: Прогнать — убедиться, что падает**

Run: `python3.11 -m pytest tests/unit/test_topology.py -q`
Expected: FAIL — `ImportError: cannot import name 'TopologyError'`

- [ ] **Step 3: Объявить и экспортировать**

В `simintech_api/exceptions.py` добавить рядом с `ScriptBridgeError`:

```python
class TopologyError(SimInTechError):
    """Строка протокола топологии не соответствует грамматике.

    Отдельный класс, а не `ValueError`: это отказ разбора данных, пришедших из
    среды, и вызывающий должен отличать его от ошибок собственного кода.
    """
```

В `simintech_api/__init__.py` добавить `TopologyError` в импорт из `.exceptions` и в `__all__`.

Создать `simintech_api/topology.py` — заготовку, которая наполняется в
задачах 2–7:

```python
"""Топология модели через встроенный язык: сборка тела пробы и разбор ответа.

Без COM и без файловой системы — всё, что здесь есть, проверяется в CI.
"""

from __future__ import annotations
```

Модуль лежит в самом пакете, поэтому импорт относительный, с одной точкой.

- [ ] **Step 4: Прогнать — убедиться, что проходит**

Run: `python3.11 -m pytest tests/unit/test_topology.py tests/unit/test_surface.py -q`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add simintech_api/exceptions.py simintech_api/__init__.py simintech_api/topology.py tests/unit/test_topology.py
git commit -m "feat(topology): исключение TopologyError"
```

---

## Task 2: Модель данных и канонический ключ связи

**Files:**
- Modify: `simintech_api/topology.py`
- Test: `tests/unit/test_topology.py`

- [ ] **Step 1: Написать падающие тесты**

Дописать в `tests/unit/test_topology.py`:

```python
from simintech_api.topology import (  # noqa: E402
    CONN_ROW,
    OBJECT_ROW,
    PORT_ROW,
    Connection,
    ObjectRow,
    PortRow,
    Topology,
    connection_key,
)


def test_connection_key_canonicalises_both_directions():
    """Связь видна с обеих сторон — ключ обязан совпасть."""
    forward = Connection("A", 0, "B", 1)
    backward = Connection("B", 1, "A", 0)
    assert connection_key(forward) == connection_key(backward)


def test_connection_key_orders_by_object_name_then_index():
    assert connection_key(Connection("B", 0, "A", 5)) == (("A", 5), ("B", 0))


def test_connection_key_distinguishes_different_ports():
    a = connection_key(Connection("A", 0, "B", 0))
    b = connection_key(Connection("A", 1, "B", 0))
    assert a != b


def test_row_types_are_the_protocol_keywords():
    assert (OBJECT_ROW, PORT_ROW, CONN_ROW) == ("object", "port", "conn")


def test_topology_keeps_row_types():
    topology = Topology(objects=[ObjectRow("A", "Константа")], ports=[], connections=[])
    assert topology.objects[0].name == "A"
    assert PortRow("A", 0, "in", "x").direction == "in"
```

- [ ] **Step 2: Прогнать — убедиться, что падает**

Run: `python3.11 -m pytest tests/unit/test_topology.py -q`
Expected: FAIL — `ImportError: cannot import name 'CONN_ROW'`

- [ ] **Step 3: Реализовать**

Дописать в `simintech_api/topology.py`:

```python
from typing import List, NamedTuple, Tuple

#: Типы строк протокола. Первая строка задаёт фазу, отдельных маркеров нет.
OBJECT_ROW = "object"
PORT_ROW = "port"
CONN_ROW = "conn"

#: Разделитель полей — ровно один символ табуляции.
FIELD_SEPARATOR = "\t"

#: Направления порта. Режим берётся из `getportinfo`: 0 — вход, 1 — выход,
#: 2 — ненаправленный. Режим вне этих трёх проба пишет сырым числом, и разбор
#: его отвергает: недокументированное значение обязано быть видно отказом.
DIRECTIONS = ("in", "out", "undirected")


class ObjectRow(NamedTuple):
    """Объект страницы: имя и класс."""

    name: str
    class_name: str


class PortRow(NamedTuple):
    """Порт объекта. Адрес порта — пара (имя объекта, индекс), а не имя."""

    object_name: str
    index: int
    direction: str
    name: str


class Connection(NamedTuple):
    """Связь между портами двух объектов."""

    object_a: str
    index_a: int
    object_b: str
    index_b: int


class Topology(NamedTuple):
    """Снимок топологии одного контейнера."""

    objects: List[ObjectRow]
    ports: List[PortRow]
    connections: List[Connection]


def connection_key(connection: Connection) -> Tuple[Tuple[str, int], Tuple[str, int]]:
    """Канонический ключ связи: концы упорядочены по (имя объекта, индекс).

    `traceallports` возвращает цепочку с обеих сторон, поэтому одна и та же
    связь приходит дважды — как `(A, i, B, j)` и как `(B, j, A, i)`. Ключ
    приводит обе записи к одному виду: сравнивать надо ключи, а не «схлопнутые»
    списки.
    """
    first = (connection.object_a, connection.index_a)
    second = (connection.object_b, connection.index_b)
    return (first, second) if first <= second else (second, first)
```

- [ ] **Step 4: Прогнать — убедиться, что проходит**

Run: `python3.11 -m pytest tests/unit/test_topology.py -q`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add simintech_api/topology.py tests/unit/test_topology.py
git commit -m "feat(topology): модель данных и канонический ключ связи"
```

---

## Task 3: Разбор — только правильный путь, без защит

**Files:**
- Modify: `simintech_api/topology.py`
- Test: `tests/unit/test_topology.py`

**Это намеренно промежуточное состояние.** Здесь реализуется только разбор
корректного потока: ссылки на объекты и порты **не проверяются**, потому что
проверять их пока не по чему — множества объявленных объектов и портов
заполняются, но не сверяются. Защиты добавляются в задачах 4–6, каждый со своим
падающим тестом. Код после задачи 3 принимает заведомо невалидный вход — и это
ожидаемо, а не дефект.

- [ ] **Step 1: Написать падающий тест**

```python
HAPPY = (
    "object\tA\tУсилитель\n"
    "object\tB\tКонстанта\n"
    "port\tA\t0\tin\tx\n"
    "port\tA\t1\tout\ty\n"
    "port\tB\t0\tout\t\n"          # пустое имя порта допустимо
    "conn\tB\t0\tA\t0\n"
    "conn\tA\t0\tB\t0\n"           # та же связь с другой стороны
)


def test_parse_happy_path():
    topology = parse_topology(HAPPY)
    assert [row.name for row in topology.objects] == ["A", "B"]
    assert topology.objects[1].class_name == "Константа"
    assert [(p.object_name, p.index, p.direction) for p in topology.ports] == [
        ("A", 0, "in"), ("A", 1, "out"), ("B", 0, "out")]
    assert topology.ports[2].name == ""


def test_both_directions_collapse_into_one_connection():
    topology = parse_topology(HAPPY)
    assert len(topology.connections) == 1
    assert connection_key(topology.connections[0]) == (("A", 0), ("B", 0))


def test_empty_input_gives_empty_topology():
    topology = parse_topology("")
    assert (topology.objects, topology.ports, topology.connections) == ([], [], [])
```

- [ ] **Step 2: Прогнать — убедиться, что падает**

Run: `python3.11 -m pytest tests/unit/test_topology.py -q`
Expected: FAIL — `ImportError: cannot import name 'parse_topology'`

- [ ] **Step 3: Реализовать**

Дописать в `simintech_api/topology.py`:

```python
#: Номер фазы: строки идут невозрастающими группами — все объекты, затем все
#: порты, затем все связи.
_PHASE = {OBJECT_ROW: 0, PORT_ROW: 1, CONN_ROW: 2}


def parse_topology(text: str) -> Topology:
    """Разобрать результат пробы топологии.

    Разбор однопроходный и строгий: каждая защита — отказ, а не догадка.
    Пустые строки пропускаются, всё прочее обязано соответствовать грамматике.
    """
    objects: List[ObjectRow] = []
    ports: List[PortRow] = []
    connections: Dict[Tuple[Tuple[str, int], Tuple[str, int]], Connection] = {}
    object_names: Set[str] = set()
    port_keys: Set[Tuple[str, int]] = set()
    phase = 0

    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        fields = line.split(FIELD_SEPARATOR)
        kind = fields[0]
        if kind not in _PHASE:
            raise TopologyError(
                f"строка {number}: неизвестный тип строки {kind!r}")
        if _PHASE[kind] < phase:
            raise TopologyError(
                f"строка {number}: тип {kind!r} идёт после более поздней фазы — "
                "порядок обязан быть: объекты, затем порты, затем связи")
        phase = _PHASE[kind]
        if kind == OBJECT_ROW:
            objects.append(_parse_object(fields, number, object_names))
        elif kind == PORT_ROW:
            ports.append(_parse_port(fields, number, port_keys))
        else:
            connection = _parse_connection(fields, number, port_keys)
            connections[connection_key(connection)] = connection

    return Topology(objects=objects, ports=ports,
                    connections=list(connections.values()))
```

**Поправка к плану.** В первой редакции этот вызов был записан как
`_parse_port(fields, number, object_names, port_keys)` — на четыре аргумента, а
функция ниже объявлена на три: код не собрался бы вовсе. `object_names` в
`_parse_port` не нужен до Task 5, где добавляется защита «порт ссылается на
необъявленный объект»; там параметр и появится.

И три разборщика строк — **в этом шаге только правильный путь**, защиты добавляются в задачах 4–6:

```python
def _parse_object(fields: List[str], number: int,
                  names: Set[str]) -> ObjectRow:
    if len(fields) != 3:
        raise TopologyError(
            f"строка {number}: у object должно быть 3 поля, получено {len(fields)}")
    row = ObjectRow(name=fields[1], class_name=fields[2])
    names.add(row.name)
    return row


def _parse_port(fields: List[str], number: int,
                keys: Set[Tuple[str, int]]) -> PortRow:
    if len(fields) != 5:
        raise TopologyError(
            f"строка {number}: у port должно быть 5 полей, получено {len(fields)}")
    row = PortRow(object_name=fields[1], index=_parse_index(fields[2], number),
                  direction=fields[3], name=fields[4])
    keys.add((row.object_name, row.index))
    return row


def _parse_connection(fields: List[str], number: int,
                      keys: Set[Tuple[str, int]]) -> Connection:
    if len(fields) != 5:
        raise TopologyError(
            f"строка {number}: у conn должно быть 5 полей, получено {len(fields)}")
    return Connection(object_a=fields[1], index_a=_parse_index(fields[2], number),
                      object_b=fields[3], index_b=_parse_index(fields[4], number))


def _parse_index(raw: str, number: int) -> int:
    try:
        value = int(raw)
    except ValueError:
        raise TopologyError(
            f"строка {number}: индекс порта {raw!r} не целое число") from None
    if value < 0:
        raise TopologyError(f"строка {number}: индекс порта не может быть отрицательным")
    return value
```

В блок импортов добавить `Dict`, `Set`, `Tuple` — и `from .exceptions import
TopologyError`: первое использование наконец появилось, и импорт приезжает сюда,
а не лежит заготовкой в Task 1. Модуль объявлен с
`from __future__ import annotations`, поэтому `Dict`/`Set` из `typing` нужны для
mypy в strict-режиме: он проверяет и тела функций.

- [ ] **Step 4: Прогнать — убедиться, что проходит**

Run: `python3.11 -m pytest tests/unit/test_topology.py -q`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add simintech_api/topology.py tests/unit/test_topology.py
git commit -m "feat(topology): однопроходный разбор протокола, правильный путь"
```

---

## Task 4: Защиты 1–7 и 12 — грамматика строки

**Files:**
- Modify: `simintech_api/topology.py`
- Test: `tests/unit/test_topology.py`

Защиты 1, 2, 3, 5, 6, 7 из таблицы критерия приёмки. Защита 4 (порядок фаз)
уже реализована в задаче 3 — на неё нужен явный тест.

**Что уже сделано и что осталось красным.** Сниппет Task 3 принёс с собой
проверки числа полей (2, 3), разбор индекса (5) и отрицательный индекс (6) —
их параметры позеленеют сразу, до всякой реализации этой задачи. Красным до неё
остаётся только `sideways` (защита 7), а тест на защиту 4 падает, потому что
сенсоры в первой редакции плана были **неверны** (см. ниже). Это не ломает цикл
на уровне файла — шаг 2 даёт красное, шаг 4 зелёное, — но «одна защита → красный
→ зелёный» здесь выполняется не для всех: 2, 3, 5, 6 приехали из Task 3, и их
невырожденность доказывается не этой задачей, а мутационной таблицей Task 6.

- [ ] **Step 1: Написать падающие тесты**

```python
@pytest.mark.parametrize("text, fragment", [
    ("blob\tA\tB\n", "неизвестный тип строки"),                # 1
    ("object\tA\n", "3 поля"),                                 # 2
    ("object\tA\tB\textra\n", "3 поля"),                       # 2
    ("object\tA\tB\tC\n", "3 поля"),                           # 3 (лишняя табуляция)
    # 2 (вторая половина): то же число полей у `port` и `conn`.
    # Эти параметры добавлены в Task 6 по результату мутационной проверки:
    # снятие `len(fields) != 5` не красило **ни один** тест — у половины защиты
    # 2 не было сенсора вовсе, и лишнее поле в строке порта или связи молча
    # игнорировалось бы, а короткая строка падала бы `IndexError` вместо отказа.
    ("port\tA\t0\tin\n", "5 полей"),                           # 2 (port, мало полей)
    ("port\tA\t0\tin\tp\textra\n", "5 полей"),                 # 2 (port, лишнее поле)
    ("conn\tA\t0\tB\n", "5 полей"),                            # 2 (conn, мало полей)
    ("conn\tA\t0\tB\t0\textra\n", "5 полей"),                  # 2 (conn, лишнее поле)
    ("port\tA\tx\tin\tp\n", "не целое"),                       # 5
    ("port\tA\t-1\tin\tp\n", "отрицательным"),                 # 6
    ("object\tA\tB\nport\tA\t0\tsideways\tp\n", "направление"),  # 7
    ("object\tA\tB\nport\tA\t0\t\tp\n", "направление"),          # 7 (пусто)
    # 4: фаза возвращается назад — object после conn
    # Порты объявлены заранее: с Task 5 связь обязана ссылаться на объявленный
    # порт, иначе отказ придёт по ссылке, а не по фазе.
    ("object\tA\tB\nport\tA\t0\tin\tp\nport\tA\t1\tout\tq\nconn\tA\t0\tA\t1\n"
     "object\tC\tK\n", "фазы"),
    # 4: то же с port после conn
    ("object\tA\tB\nport\tA\t0\tin\tp\nport\tA\t1\tout\tq\nconn\tA\t0\tA\t1\n"
     "port\tA\t2\tin\tr\n", "фазы"),
])


def test_row_grammar_rejections(text, fragment):
    with pytest.raises(TopologyError) as exc:
        parse_topology(text)
    assert fragment in str(exc.value)


def test_direction_must_be_known():
    """Три допустимых направления — и ничего кроме."""
    assert DIRECTIONS == ("in", "out", "undirected")
    for direction in ("in", "out", "undirected"):
        parse_topology(f"object\tA\tK\nport\tA\t0\t{direction}\tp\n")
```

**Поправка к плану: сенсоры защиты 4.** В первой редакции здесь стояли «`conn`
без фаз 1–2» и «`conn` до портов» с ожиданием фрагмента `"фазы"`. Ни один из них
не работает:

- «`conn` без фаз 1–2» — это **законный** вход, а не отказ. Спецификация
  (`…-design.md`) прямо говорит: «Отдельных маркеров фаз не нужно: тип первой
  строки её и задаёт». Проба, начавшаяся со связей, отвергаться не должна —
  иначе отвергалась бы и любая страница без объектов. Возврат назад — это
  `object` **после** `conn`, а не `conn` с самого начала;
- «`conn` до портов» отвергается в Task 5 сверкой ссылок, но её сообщение —
  «связь ссылается на необъявленный порт A.0 — его не было в фазе портов», и
  подстроки `"фазы"` в нём нет (проверено программно). Шаг 4 «Expected: PASS»
  с таким сенсором недостижим, а строка 4 мутационной таблицы ссылалась бы на
  вечно красный тест — то есть мутационная проверка защиты 4 была бы
  бессмысленной.

Оба сенсора заменены на настоящий возврат фазы: `object` после `conn` и `port`
после `conn`. Порты в них объявлены заранее, а связь идёт между **разными**
портами одного объекта — и это не украшение. `conn` без объявленного порта
отвергается уже в Task 5 по ссылке, и до фазовой проверки дело не доходит; а
`conn` порта с самим собой в Task 6 отвергается ещё и защитой 13 (петля).
Исходные сенсоры оказались бы вечно красными — по чужой причине.

**Поправка к плану: сторож состава `DIRECTIONS`.** В первой редакции здесь было
только `for` по литералам, и docstring обещал «и ничего кроме» **без проверки**:
мутация «дописать четвёртое значение в кортеж» проходила зелёной, её ловил
только параметр `sideways`. У сторожа уникальная работа — расширение кортежа
значением, которого нет ни в одном сенсоре, не замечает больше ничто, а
перестановку замечает **только** он (порядок влияет лишь на текст сообщения,
которого не проверяет ни один тест). `DIRECTIONS` добавляется в импорт из
`simintech_api.topology`.


@pytest.mark.parametrize("text, fragment", [
    ("object\t\tB\n", "пустое имя объекта"),                          # 12
    ("object\tA\t\n", "пустой класс"),                                # 12
])
def test_empty_required_fields_rejected(text, fragment):
    """Пустое имя или класс объекта — отказ.

    Имя объекта — ключ, по которому адресуются порты и связи; объект без
    класса неотличим от мусора. Пустое имя ПОРТА при этом допустимо: адрес
    порта — индекс, а не имя.

    **Поправка к плану.** Здесь стояли ещё два параметра — `port` и `conn` с
    пустым именем объекта. Оба относятся к защите 12, но проверки для них
    задача добавляет не сюда, а в Task 5 (там же, где пустое имя объекта
    отвергается в строках ссылок). Оставить их здесь значило бы получить шаг 4
    «Expected: PASS», недостижимый до Task 5, — ровно та ошибка, что была с
    сенсорами защиты 4. Параметры переехали в Task 5 и названы там.
    """
    with pytest.raises(TopologyError) as exc:
        parse_topology(text)
    assert fragment in str(exc.value)


def test_empty_port_name_is_allowed():
    """Обратная сторона того же правила: у порта имя может быть не задано."""
    topology = parse_topology("object\tA\tK\nport\tA\t0\tin\t\n")
    assert topology.ports[0].name == ""
```

- [ ] **Step 2: Прогнать — убедиться, что падает**

Run: `python3.11 -m pytest tests/unit/test_topology.py -q`
Expected: FAIL ровно на трёх параметрах — `sideways` (направление не проверяется)
и два параметра про пустые обязательные поля. Остальные параметры позеленеют
сразу: их проверки приехали из сниппета Task 3.

- [ ] **Step 3: Реализовать проверку направления и пустых обязательных полей**

В `_parse_port` добавить перед созданием строки:

```python
    if fields[3] not in DIRECTIONS:
        raise TopologyError(
            f"строка {number}: неизвестное направление порта {fields[3]!r}, "
            f"допустимы {', '.join(DIRECTIONS)}")
```

В `_parse_object` — проверка пустых полей (защита 12):

```python
    if not fields[1]:
        raise TopologyError(f"строка {number}: пустое имя объекта")
    if not fields[2]:
        raise TopologyError(
            f"строка {number}: пустой класс объекта {fields[1]!r}")
```

**Критерий пустоты назван явно: пустая строка, а не пробельная.** `if not
fields[n]` отвергает `""`, но принимает `" "` — объект с именем из одного пробела
объявляется законно и попадает в `names`. Это решение, а не промах: имена
приходят из `getobjname` и `getobjclassname`, пробельное имя там означало бы
дефект среды, а не протокола, и молча превращать его в отказ значило бы
отвергать модель по признаку, которого спецификация не называет. Расхождение с
уровнем строк, где пустым считается `line.strip()`, осознанное: там пропускаются
пустые строки вывода, здесь проверяется **поле**. Пробельное имя стоит один раз
назвать в отчёте живого прогона, если среда его когда-нибудь отдаст.

- [ ] **Step 4: Прогнать — убедиться, что проходит**

Run: `python3.11 -m pytest tests/unit/test_topology.py -q`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add simintech_api/topology.py tests/unit/test_topology.py
git commit -m "feat(topology): защиты грамматики строки"
```

---

## Task 5: Защиты 8–11 — ссылки и дубликаты

**Files:**
- Modify: `simintech_api/topology.py`
- Test: `tests/unit/test_topology.py`

- [ ] **Step 1: Написать падающие тесты**

```python
@pytest.mark.parametrize("text, fragment", [
    # 9: дубликат имени объекта
    ("object\tA\tK\nobject\tA\tK2\n", "повторное имя объекта"),
    # 10: дубликат пары (объект, индекс)
    ("object\tA\tK\nport\tA\t0\tin\tx\nport\tA\t0\tout\ty\n", "повторная декларация порта"),
    # 11: conn на необъявленный порт
    ("object\tA\tK\nobject\tB\tK\nport\tA\t0\tin\tx\nport\tB\t1\tout\ty\n"
     "conn\tA\t0\tB\t0\n", "необъявленный порт"),
    # 11: не объявлен ПЕРВЫЙ конец
    ("object\tA\tK\nobject\tB\tK\nport\tA\t0\tin\tx\nport\tB\t0\tout\ty\n"
     "conn\tA\t9\tB\t0\n", "необъявленный порт"),
    # 13: петля не может обгонять сверку ссылок — порт A.9 не объявлен
    ("object\tA\tK\nport\tA\t0\tin\tx\nconn\tA\t9\tA\t9\n",
     "необъявленный порт"),
    # 13: и не может обгонять полноту имён
    ("object\tA\tK\nport\tA\t0\tin\tx\nconn\t\t0\t\t0\n",
     "пустое имя объекта"),
    # 8: port для необъявленного объекта
    ("object\tA\tK\nport\tB\t0\tin\tx\n", "необъявленный объект"),
])
def test_reference_and_duplicate_rejections(text, fragment):
    with pytest.raises(TopologyError) as exc:
        parse_topology(text)
    assert fragment in str(exc.value)


def test_duplicate_port_name_is_allowed():
    """Адрес порта — индекс, поэтому одинаковые имена допустимы."""
    topology = parse_topology(
        "object\tA\tK\nport\tA\t0\tin\tx\nport\tA\t1\tin\tx\n")
    assert len(topology.ports) == 2


@pytest.mark.parametrize("text, fragment", [
    ("object\tA\tB\nport\t\t0\tin\tp\n", "пустое имя объекта"),       # 12
    ("object\tA\tB\nport\tA\t0\tin\tp\nconn\t\t0\tA\t0\n",
     "пустое имя объекта"),                                            # 12
])
def test_empty_object_name_in_reference_rows_rejected(text, fragment):
    """Пустое имя объекта — отказ и в `port`, и в `conn`, а не только в `object`.

    Проверка **диагностическая, а не охранная**, и это измерено. Исчерпывающий
    дифференциальный прогон (все последовательности строк длиной до 4 из 16
    шаблонов, около 70 тысяч входов) даёт **ноль** различий по приёму/отказу при
    снятии любой из этих двух проверок — и 5382 и 10766 различий в тексте
    сообщения. Причина: `_parse_object` отвергает пустое имя, поэтому `""` не
    попадает ни в `names`, ни в `keys`, и проверки 8 и 11 отвергают пустое имя в
    ссылках всё равно. Ценность проверки в другом: без неё оператор на пустое
    поле получит «порт ссылается на необъявленный объект ''» — утверждение об
    отсутствующем объявлении там, где сломано поле. Держать её надо за это.

    **Порядок проверок в `_parse_connection` обязателен:** пустое имя объекта
    отвергается **до** сверки по `keys`, иначе второй параметр получит отказ
    «необъявленный порт .0» — верный по сути, но не тот, ради которого тест
    написан. Тест проверяет подстроку, а не смысл: с обратным порядком он
    покраснеет. Закреплён именно этот, **глобальный** порядок; консолидация двух
    циклов в один проход по концам ничем не ловится и меняет текст отказа — то
    есть сведение здесь запрещено, пока не появится свой сенсор.
    """
    with pytest.raises(TopologyError) as exc:
        parse_topology(text)
    assert fragment in str(exc.value)
```

**Почему у защиты 11 два параметра.** Сверка идёт по **обоим** концам связи, и
одного параметра на неё не хватало: мутант, сверяющий только второй конец
(`for object_name, index in ((connection.object_b, connection.index_b),)`),
переживает весь набор — связь `conn A 9 B 0` при объявленном `B.0` принимается
вместе с несуществующим портом `A.9`. Половина защиты была не покрыта, и строка
11 мутационной таблицы отчиталась бы зелёной при открытой дыре.

**Защита 8 распадается на два случая, и это исправление к плану.** Первая
редакция объявляла её целиком покрытой тестом 11 — это неверно. Тест 11 ловит
`conn`, ссылающуюся на необъявленный **порт**; но `port`, объявленный для
несуществующего **объекта**, не отвергался ничем: строка попадала в `keys`, и
дальше `conn` на неё проходила проверку 11 законно. То есть дыра была ровно в
том месте, где спецификация требует «имена объектов в `port` и `conn` есть
среди объявленных `object`». Тест на этот случай добавлен выше, проверка — в
шаге 3. Для `conn` спецификация выполняется транзитивно: пара `(объект, индекс)`
попадает в `keys` только из объявленного порта.

- [ ] **Step 2: Прогнать — убедиться, что падает**

Run: `python3.11 -m pytest tests/unit/test_topology.py -q`
Expected: FAIL — дубликаты и ссылки сейчас принимаются

- [ ] **Step 3: Реализовать**

В `_parse_object`:

```python
    if row.name in names:
        raise TopologyError(
            f"строка {number}: повторное имя объекта {row.name!r} — связи "
            "адресуются по имени, и дубликат делает адресацию неоднозначной")
```

В `_parse_port` — сигнатура получает `names`, и добавляются две проверки:

```python
def _parse_port(fields: List[str], number: int, names: Set[str],
                keys: Set[Tuple[str, int]]) -> PortRow:
    ...
    if row.object_name not in names:
        raise TopologyError(
            f"строка {number}: порт ссылается на необъявленный объект "
            f"{row.object_name!r} — объекта с таким именем не было среди "
            "строк object")
    key = (row.object_name, row.index)
    if key in keys:
        raise TopologyError(
            f"строка {number}: повторная декларация порта {row.object_name}."
            f"{row.index} — пара (объект, индекс) это ключ порта")
```

Вызов в `parse_topology` соответственно возвращается к четырём аргументам:
`_parse_port(fields, number, object_names, port_keys)` — тем самым, что в первой
редакции плана стояли по ошибке, но здесь они уже обоснованы.

В `_parse_port` — пустое имя объекта недопустимо и здесь (спецификация требует
непустого имени объекта в любой строке, где он упоминается):

```python
    if not fields[1]:
        raise TopologyError(
            f"строка {number}: пустое имя объекта в строке порта")
```

**Порядок проверок в `_parse_port` обязателен и таков:**

```
число полей → пустое имя объекта → направление → индекс
            → объявленность объекта → дубликат ключа
```

Правило, из которого он выведен: **сначала грамматика и полнота самих полей,
потом связи с уже объявленным состоянием.** Внутри первой группы пустота имени
идёт раньше всего остального, потому что называть её надо пустотой: на
`port\t\t0\tbad\tp` проверка направления сказала бы «неизвестное направление
порта 'bad'», а на `port\t\t0\tin\tp` проверка объявленности — «порт объявлен для
необъявленного объекта ''». Оба сообщения верны по сути и оба не о том, что
сломалось. Тест, ждущий подстроку «пустое имя объекта», на них покраснеет —
и будет прав.

Направление стоит **до** индекса, как уже сложилось в Task 4 (проверка
направления там поставлена перед конструированием строки, а индекс разбирается
внутри него). Менять это не нужно — важно лишь, что обе эти проверки идут после
пустоты имени и до всего, что смотрит на накопленное состояние.

Границу групп стоит отметить комментарием в обоих разборщиках — перед сверкой с
накопленным состоянием. После Task 6 проверок станет семь подряд, и невидимая
граница между «грамматикой» и «состоянием» — единственное, что там легко
потерять при следующей правке.

**Сводить разборщики нельзя.** Объединение двух циклов `_parse_connection` в
один проход по концам (пустота и членство на каждом конце сразу) переживает весь
набор тестов и **меняет текст отказа**: `conn A 9 <пусто> 0` начинает отвечать
про необъявленный порт вместо пустого имени. То есть сведение сейчас молча
обменяло бы диагностику на три строки экономии — в задаче, которая целиком
посвящена тому, чтобы отказы были внятными.

В `_parse_connection` — та же проверка (для **обоих** концов, и тоже **до**
сверки по `keys`, по той же причине) плюс сверка обоих концов:

```python
def _parse_connection(fields: List[str], number: int,
                      keys: Set[Tuple[str, int]]) -> Connection:
    if len(fields) != 5:
        raise TopologyError(
            f"строка {number}: у conn должно быть 5 полей, получено {len(fields)}")
    connection = Connection(
        object_a=fields[1], index_a=_parse_index(fields[2], number),
        object_b=fields[3], index_b=_parse_index(fields[4], number))
    for object_name in (connection.object_a, connection.object_b):
        if not object_name:
            raise TopologyError(
                f"строка {number}: пустое имя объекта в строке связи")
    for object_name, index in ((connection.object_a, connection.index_a),
                               (connection.object_b, connection.index_b)):
        if (object_name, index) not in keys:
            raise TopologyError(
                f"строка {number}: связь ссылается на необъявленный порт "
                f"{object_name}.{index} — его не было в фазе портов")
    return connection
```

- [ ] **Step 4: Прогнать — убедиться, что проходит**

Run: `python3.11 -m pytest tests/unit/test_topology.py -q`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add simintech_api/topology.py tests/unit/test_topology.py
git commit -m "feat(topology): защиты ссылок и дубликатов"
```

---

## Task 6: Защита 13 — петля, и мутационная проверка всех тринадцати

**Files:**
- Modify: `simintech_api/topology.py`
- Test: `tests/unit/test_topology.py`

- [ ] **Step 1: Написать падающий тест**

```python
def test_self_loop_is_rejected():
    """Три входа — не украшение: без третьего мутация, сужающая проверку до
    конкретного имени, выживает (`Connection.object_a == "A"` проходит все
    тесты, если оба входа используют объект A). Сужение до конкретного индекса
    ловит второй вход."""
    for text in (
        "object\tA\tK\nport\tA\t0\tin\tx\nconn\tA\t0\tA\t0\n",
        "object\tA\tK\nport\tA\t3\tin\tx\nconn\tA\t3\tA\t3\n",
        "object\tB\tK\nport\tB\t1\tout\ty\nconn\tB\t1\tB\t1\n",
    ):
        with pytest.raises(TopologyError) as exc:
            parse_topology(text)
        assert "петля" in str(exc.value)


def test_connection_between_different_ports_of_one_object_is_allowed():
    """Петлёй считается только связь порта с самим собой, не внутри объекта."""
    text = ("object\tA\tK\nport\tA\t0\tin\tx\nport\tA\t1\tout\ty\n"
            "conn\tA\t0\tA\t1\n")
    assert len(parse_topology(text).connections) == 1


def test_model_assumptions_are_not_enforced():
    """Разбор не проверяет догадки о модели SimInTech.

    «Выход соединяется только со входом» и «у порта одно соединение» — это
    предположения о модели, а не о протоколе. Разбор, отвергающий по ним,
    ломался бы на законной модели, то есть был бы хуже, чем без них. Оба
    утверждения вводятся только после подтверждения живым прогоном.
    """
    text = ("object\tA\tK\nobject\tB\tK\nobject\tC\tK\n"
            "port\tA\t0\tout\tx\nport\tB\t0\tout\ty\nport\tC\t0\tin\tz\n"
            "conn\tA\t0\tB\t0\n"     # выход к выходу — принимается
            "conn\tA\t0\tC\t0\n")    # у порта два соединения — принимается
    assert len(parse_topology(text).connections) == 2

- [ ] **Step 2: Прогнать — убедиться, что падает**

Run: `python3.11 -m pytest tests/unit/test_topology.py -q`
Expected: FAIL — петля сейчас принимается

- [ ] **Step 3: Реализовать**

В `_parse_connection` после проверки ссылок:

```python
    if (connection.object_a, connection.index_a) == \
            (connection.object_b, connection.index_b):
        raise TopologyError(
            f"строка {number}: петля — порт {connection.object_a}."
            f"{connection.index_a} соединён сам с собой")
```

- [ ] **Step 4: Прогнать — убедиться, что проходит**

Run: `python3.11 -m pytest tests/unit/test_topology.py -q`
Expected: PASS

- [ ] **Step 5: Мутационная проверка каждой защиты**

Снять каждую защиту по очереди и убедиться, что **её sentinel-тест** падает.
Таблица обязательна: без неё мутация «где-то в файле» ничего не доказывает.

| № | Защита | Sentinel-тест | Где мутировать |
|---|---|---|---|
| 1 | неизвестный тип строки | `test_row_grammar_rejections[blob…]` | `if kind not in _PHASE` |
| 2 | число полей | `test_row_grammar_rejections[object\tA]`, а также `[port\tA\t0\tin]` и `[conn\tA\t0\tB]` | `if len(fields) != 3` (и 5) |
| 3 | лишняя табуляция | `test_row_grammar_rejections[object\tA\tB\textra]` | тот же `len(fields)` |
| 4 | порядок фаз | `test_row_grammar_rejections[object…object после conn]` | `if _PHASE[kind] < phase` |
| 5 | индекс не целое | `test_row_grammar_rejections[port…x…]` | `except ValueError` в `_parse_index` |
| 6 | отрицательный индекс | `test_row_grammar_rejections[port…-1…]` | `if value < 0` |
| 7 | направление | `test_row_grammar_rejections[…sideways…]` | `if fields[3] not in DIRECTIONS` |
| 8 | ссылка на необъявленный объект | `test_reference_and_duplicate_rejections[object…port B…]` | `if row.object_name not in names` в `_parse_port` |
| 9 | дубликат имени объекта | `test_reference_and_duplicate_rejections[…object\tA…]` | `if row.name in names` |
| 10 | дубликат пары (объект, индекс) | `test_reference_and_duplicate_rejections[…port\tA\t0…]` | `if key in keys` |
| 11 | необъявленный порт | `test_reference_and_duplicate_rejections[…conn\tA\t0\tB\t0]` | та же сверка `keys` |
| 12 | пустое обязательное поле | `test_empty_required_fields_rejected[…]` и `test_empty_object_name_in_reference_rows_rejected[…]` | проверки `if not fields[n]` |
| 13 | петля | `test_self_loop_is_rejected` | `if (…a…) == (…b…)` |

Защита, снятие которой **не** роняет своего теста, означает вакуумный тест —
её надо переписать, а не принять. Этот класс ошибки в проекте уже дважды
проходил незамеченным; здесь он закрывается по построению.

**Отдельно про защиту 12 в строках ссылок: она диагностическая, а не охранная.**
Измерено исчерпывающим дифференциальным прогоном на Task 5 — корпус всех
последовательностей строк длиной до 4 из 16 шаблонов, около 70 тысяч входов:
снятие проверки пустого имени в `_parse_port` даёт **ноль** различий по
приёму/отказу и 5382 различия по тексту сообщения; в `_parse_connection` — ноль
и 10766.

Причина структурная: `_parse_object` отвергает пустое имя, поэтому `""` никогда
не попадает ни в `names`, ни в `keys` — и проверки 8 и 11 отвергают пустое имя в
ссылках всё равно. Снятие любой **одной** из этих проверок дыры не открывает.

Что это значит для таблицы: строка 12 остаётся рабочей — снятие проверки
краснит свой sentinel, потому что тест сравнивает **подстроку** и получает при
этом сообщение от другой проверки. Но называть её защитой в том же смысле, что
защиты 1–11 и 13, неверно: она не меняет, что разбор принимает, — она меняет,
что оператор прочитает в логе. Держать её надо именно за это, и падение
sentinel-а здесь доказывает не охранную силу, а качество диагностики.

**Проверка — не формальность: на первом прогоне Task 6 она нашла незакрытую
половину защиты 2.** Снятие `len(fields) != 5` не красило **ни один** тест: у
строк `port` и `conn` сенсоров числа полей не было вовсе. Последствия были не
теоретические — строка `port A 0 in p extra` молча принималась (лишнее поле
игнорировалось), а короткая падала `IndexError` вместо `TopologyError`, то есть
без контракта отказа. Проверки в коде были на месте; не хватало сенсоров, и
нашло это именно измерение, а не чтение. Четыре параметра добавлены в Task 4.

**Дисциплина мутации — измерена на Task 2, и её нельзя опускать.** Репозиторий
лежит на DrvFS (`/mnt/c`), а CPython считает `.pyc` свежим по паре
`(int(st_mtime), size)`. Замена, сохраняющая длину файла и попавшая в ту же
целую секунду, оставляет прежний байткод: прогон покажет результат **предыдущей**
мутации. Измерено: 3 из 4 прогонов ложные. Отсюда три правила:

1. `PYTHONDONTWRITEBYTECODE=1` **и** очистка кэша в начале батча (`rm -rf` по
   `__pycache__`); одно `PYTHONPYCACHEPREFIX` защитой не является — оно лишь
   переносит кэш, проверка `(mtime, size)` остаётся (8 ложных из 8).
2. Перед прогоном сверять содержимое файла **на диске** с задуманной мутацией.
3. Мутации делать **равной длины**. Мутация, меняющая размер файла, инвалидирует
   кэш сама — на ней ложный результат не воспроизводится, и «защита» проверяется
   вхолостую. Первый демонстрационный прогон сорвался именно на этом.

- [ ] **Step 6: Коммит**

```bash
git add simintech_api/topology.py tests/unit/test_topology.py
git commit -m "feat(topology): защита от петли; мутационная проверка всех защит"
```

---

## Task 7: Сборка тела пробы

**Files:**
- Modify: `simintech_api/topology.py`
- Test: `tests/unit/test_topology.py`

- [ ] **Step 1: Написать падающий тест**

```python
from simintech_api.topology import build_topology_probe  # noqa: E402


def test_probe_declares_variables_before_use():
    """`var` во встроенном языке объявляется одним блоком в начале тела."""
    body = build_topology_probe()
    assert body.lstrip().startswith("var ")
    assert body.index("var ") < body.index("contid =")


def test_probe_has_three_phases_in_order():
    body = build_topology_probe()
    objects = body.index('"object"')
    ports = body.index('"port"')
    conns = body.index('"conn"')
    assert objects < ports < conns


def test_probe_reads_current_container_only():
    body = build_topology_probe()
    assert "getcurrentcontainer" in body
    assert "getsubmodelid" not in body and "reinit" not in body


#: Функции, подтверждённые поставкой, — и весь список. Источник подтверждения
#: не реестр (он даёт существование имени, но не работоспособность), а
#: **работающий скрипт вендора** `bin/include_mvtu/export_sheme_functions.inc`
#: и демо «Анализ топологии скриптами».
#: `getcurrentcontainer` подтверждён **другим** источником, и это сказано явно,
#: чтобы следующему читателю не показалось, будто имя попало сюда на глазок:
#: скрипт, поставленный из-под COM, дал файл с `PROBE objects=7`, а
#: `GetPageObjectCount` по COM дал те же 7 (`2026-09-21-script-bridge-design.md`,
#: эксперимент D). Это сильнее подтверждения по скрипту вендора, где сверки с
#: независимым источником нет. Зовётся оно **без скобок**, поэтому в проверку
#: вызовов не попадало бы вовсе — и без него сильный сенсор краснеет на
#: настоящем теле.
CONFIRMED_FUNCTIONS = (
    "getobjcount", "getobj", "getobjname", "getobjclassname",
    "getblockportcount", "getblockportid", "getportinfo", "traceallports",
    "getportblockid", "getportindex", "cols", "inttostr", "chr", "writelnutf8",
    "getcurrentcontainer", "getportwireid",
)

#: Ключевые слова и типы встроенного языка — всё, что телу разрешено писать
#: помимо подтверждённых функций и собственных переменных.
LANGUAGE_KEYWORDS = ("var", "for", "begin", "end", "if", "then", "else")
LANGUAGE_TYPES = ("integer", "string", "intarray")


def test_probe_uses_only_confirmed_functions():
    """Все подтверждённые функции в теле названы."""
    body = build_topology_probe()
    for name in CONFIRMED_FUNCTIONS:
        assert name in body, f"в пробе нет {name}"


def _declared_variables(body: str) -> set:
    """Имена, объявленные в секции `var` тела."""
    block = body[body.index("var ") + 4:body.index(";", body.index("var "))]
    return {
        piece.split(":")[0].strip()
        for piece in block.split(",")
        if piece.strip()
    }


def test_probe_uses_only_confirmed_names():
    """Тело состоит только из подтверждённых имён — и ничего кроме.

    «Кроме» — объявленные переменные тела и `fid`: сенсор проверяет, что в теле
    нет **незнакомых имён**, а не то, что каждое имя где-то вызывается. Иначе
    получалось бы утверждение шире кода: объявленное имя можно позвать как
    функцию, и сенсор этого не заметит.

    Проверка на **отсутствие**, а не на присутствие: предыдущий тест перечисляет
    четырнадцать имён и молчит о пятнадцатом. Собираются **все** идентификаторы
    тела (без строковых литералов и комментариев), а не только вызовы со скобкой.

    Почему так строго — измерено. Весь набор тестов переживали: чужая функция
    **без скобок**, чужая функция с именем **с заглавной буквы** и
    переименование `getcurrentcontainer` в `getcurrentcontainerx` (последнее —
    потому что тест «читается только текущий контейнер» подстрочный, а
    `getcurrentcontainer` входит в `getcurrentcontainerx` подстрокой).
    """
    body = build_topology_probe()
    # Литералы вырезаются регуляркой по парным кавычкам, поэтому нечётное их
    # число сделало бы проверку вакуумной на целом участке: измерено — кавычка
    # в комментарии (`// атрибут "имя"`) съедала текст до следующей кавычки
    # тела, и чужое имя внутри этого участка не находилось.
    assert body.count('"') % 2 == 0, "непарная кавычка в теле — литералы не вырезать"
    # Секция `var` должна быть ровно одна: разбор берёт первую, и повторное
    # объявление (почти наверняка ошибка компиляции, а отказ среды молчаливый)
    # иначе невидимо.
    assert body.count("var ") == 1, "в теле больше одной секции var"
    without_literals = re.sub(r'"[^"]*"', '""', body)
    without_comments = re.sub(r"//[^\n]*", "", without_literals)
    identifiers = set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", without_comments))
    known = (
        set(CONFIRMED_FUNCTIONS)
        | set(LANGUAGE_KEYWORDS)
        | set(LANGUAGE_TYPES)
        | _declared_variables(body)
        | {"fid"}
    )
    assert identifiers - known == set(), \
        f"в теле незнакомые имена: {sorted(identifiers - known)}"


def test_probe_initialises_tab_before_first_write():
    """`TAB` инициализируется до первой записи, а не где-нибудь в теле.

    Измерено: перенос `TAB = chr(9)` в конец тела переживал весь набор — при
    этом первая же строка вывода склеилась бы с пустой строкой.
    """
    body = build_topology_probe()
    assert body.index("TAB = chr(9)") < body.index('"object"')
```

- [ ] **Step 2: Прогнать — убедиться, что падает**

Run: `python3.11 -m pytest tests/unit/test_topology.py -q`
Expected: FAIL — нет `build_topology_probe`

- [ ] **Step 3: Реализовать**

```python
def build_topology_probe() -> str:
    """Тело пробы топологии — три фазы: объекты, порты, связи.

    Тело идёт в `ScriptBridge.run_probe`, который обернёт его в `if firststep`
    и добавит маркеры результата. Объявления `var` собраны в одну секцию в
    начале тела.

    Строже про `var` сказать нельзя. Скрипт вендора объявляет переменные
    **после** исполняемых операторов (`fid = createfile(...)`, два `writelnutf8`),
    то есть объявление после операторов в этом диалекте законно. Но собранный
    скрипт содержит **две** секции `var`: свою пишет `build_probe_script`, — а
    что две секции в одном блоке законны, скрипт вендора не показывает. Это
    подтверждает первый живой прогон, и признак отказа у него свой: «в
    результате нет ровно одной пары маркеров».

    Фазы обязательны именно в таком порядке. Если писать `conn` сразу за
    портом, связь `A.0 → B.0` сошлётся на объект `B`, который объявится позже,
    — то есть проба породит ссылку вперёд, которую разбор обязан отвергать.
    """
    return (
        "  var contid: integer,\n"
        "      objid: integer,\n"
        "      objcnt: integer,\n"
        "      obj_idx: integer,\n"
        "      portcnt: integer,\n"
        "      port_idx: integer,\n"
        "      portid: integer,\n"
        "      mode: integer,\n"
        "      objtype: integer,\n"
        "      peerobjtype: integer,\n"
        "      alinetype: integer,\n"
        "      portname: string,\n"
        "      modestr: string,\n"
        "      peername: string,\n"
        "      peer_index: integer,\n"
        "      peers: intarray,\n"
        "      peer_idx: integer,\n"
        "      TAB: string;\n"
        '  TAB = chr(9);\n'
        "  contid = getcurrentcontainer;\n"
        "  objcnt = getobjcount(contid);\n"
        "\n"
        "  // фаза 1: типы 100 и 102\n"
        "  for(obj_idx=1, objcnt) begin\n"
        "    objid = getobj(contid, obj_idx);\n"
        "    objtype = getobjtypeid(objid);\n"
        "    if (objtype = 100) or (objtype = 102) then begin\n"
        '      writelnutf8(fid, "object" + TAB + getobjname(objid)\n'
        '                       + TAB + getobjclassname(objid));\n'
        "    end;\n"
        "  end;\n"
        "\n"
        "  // фаза 2: все порты\n"
        "  for(obj_idx=1, objcnt) begin\n"
        "    objid = getobj(contid, obj_idx);\n"
        "    objtype = getobjtypeid(objid);\n"
        "    if (objtype = 100) or (objtype = 102) then begin\n"
        "      portcnt = getblockportcount(objid);\n"
        "      for(port_idx=0, portcnt-1) begin\n"
        "        portid = getblockportid(objid, port_idx);\n"
        "        mode = getportinfo(portid, portname, alinetype);\n"
        '        if mode = 0 then modestr = "in"\n'
        '        else if mode = 1 then modestr = "out"\n'
        '        else if mode = 2 then modestr = "undirected"\n'
        "        else modestr = inttostr(mode);\n"
        '        writelnutf8(fid, "port" + TAB + getobjname(objid) + TAB\n'
        "                         + inttostr(port_idx) + TAB + modestr + TAB + portname);\n"
        "      end;\n"
        "    end;\n"
        "  end;\n"
        "\n"
        "  // фаза 3: все связи\n"
        "  for(obj_idx=1, objcnt) begin\n"
        "    objid = getobj(contid, obj_idx);\n"
        "    objtype = getobjtypeid(objid);\n"
        "    if (objtype = 100) or (objtype = 102) then begin\n"
        "      portcnt = getblockportcount(objid);\n"
        "      for(port_idx=0, portcnt-1) begin\n"
        "        portid = getblockportid(objid, port_idx);\n"
        "        if getportwireid(portid) <> 0 then begin\n"
        "          peers = traceallports(portid, 0);\n"
        "          for(peer_idx=1, cols(peers)) begin\n"
        "            peername = getobjname(getportblockid(peers[peer_idx]));\n"
        "            peerobjtype = getobjtypeid(getportblockid(peers[peer_idx]));\n"
        "            if (peerobjtype = 100) or (peerobjtype = 102) then begin\n"
        "              peer_index = getportindex(peers[peer_idx]);\n"
        '              writelnutf8(fid, "conn" + TAB + getobjname(objid) + TAB\n'
        "                               + inttostr(port_idx) + TAB + peername + TAB\n"
        "                               + inttostr(peer_index));\n"
        "            end;\n"
        "          end;\n"
        "        end;\n"
        "      end;\n"
        "    end;\n"
        "  end;\n"
    )
```

**Фильтр распространён и на второй конец связи — иначе проба теряла модель
целиком.** `traceallports` возвращает соседей **независимо от их типа**,
поэтому отфильтрованный объект всё равно попадал в строку `conn`, и строгий
разбор отвергал **весь** результат: на схеме «Ступенька → Усилитель → В память»
проба отказывала с «связь ссылается на необъявленный порт ToMem_0.0». До
фильтра это было невозможно — объявлялось всё. Теперь тип соседа проверяется в
фазе 3 до записи. Цена — связь на отфильтрованный блок **тихо теряется**;
выбор осознанный: потерять одно ребро лучше, чем не прочитать модель. Вендор
делает то же самое, только по другому признаку: строка 107 того же файла
отсекает соседей из чужого контейнера.

**Проба читает только простые блоки и субмодели — по признаку вендора.** Живой прогон
(Task 9) показал, что без фильтра в `objects` попадают линии, подписи, текст и
графика, а каждая линия добавляет **два фантомных ребра**: проект из двух блоков
и одной линии давал 3 связи вместо 1. Линия — объект страницы, у неё есть свои
порты, и фаза связей трассирует и их.

Фильтр — вендорский, из `bin/include_mvtu/export_sheme_functions.inc:44-50`:
объект модели это `getobjtypeid(objid)` равный **100** (простой блок) или **102**
(субмодель). Проверка стоит в **каждой** из трёх фаз: если отфильтровать только
первую, порты и связи сошлются на объекты, которых нет в списке, и разбор
отвергнет всё по защитам 8 и 11.

**Что этот фильтр исключает — осознанно, а не по недосмотру.** Перепись по 14
живым страницам поставки: под 100/102 не проходят типы 104 «В память», 105
«Из памяти», 106 «Временной график», 109 «Блок со встроенным интерпретатором»
и 113 «Блок-узел» — то есть часть настоящих моделирующих блоков.
Живьём подтверждены 104 и 106; 105, 109 и 113 — предполагаемые. Это
**определение модели вендором**, а не свойство среды, и выбрано сознательно:
с ним числа эталона (35 объектов, 32 связи) становятся достижимыми и
проверяемыми. Расширять список — отдельное решение с отдельным доказательством.

> **Пометка 2026-09-24: запись устарела по существу.** Набор пересмотрен: отбор
> идёт по критерию допустимости (`ELIGIBLE_OBJECT_TYPES`), и типы 104 «В память» и
> 106 «Временной график» в него **входят**; не охвачены 105, 109 и 113 — блоки этих
> классов не удалось создать, то есть их допустимость живым прогоном не измерена
> (другое основание, чем отказ по критерию). Абзац выше оставлен как запись того
> решения и его обоснования; действующее описание — в `docs/api.md` и в докстринге
> `build_topology_probe`.

При этом вендорский фильтр по классу `{and (objclassname <> "СПТ - Узел -
ветвление")}` **не копируется**: фигурные скобки — блочный комментарий языка,
условие выключено. Подтверждено независимо: в эталонном JSON есть 4 объекта
класса «СПТ - Узел - ветвление», которые это условие отсекло бы.

**Что сверено с работающим скриптом вендора, а что нет.** Арность вызова
подтверждена: `bin/include_mvtu/export_scheme_functions.inc:93` и `:266` зовут
`traceallports(portid,0)` — с двумя аргументами, ровно как здесь (официальная
справка даёт сигнатуру с одним и, значит, описывает не тот вызов, которым
пользуется сам вендор).

Два места, где вендор делает больше. Оба проба в итоге **повторяет** — первое
сразу, второе с правки после ревью PR #13:

- **`getportwireid(portid) <> 0`** — вендор обрабатывает только порты, у которых
  есть провод. Проба **повторяет этот фильтр** (было решено оставить на живой
  прогон — и зря: фильтр закрывает риск бесплатно). Потерь нет: у порта без
  провода связей и не бывает, `cols(peers)` дал бы 0. А выигрыш прямой: без
  фильтра, если `traceallports` на порту без провода вернёт **сам порт**, проба
  напишет `conn A i A i`, и защита 13 отвергнет **всю** модель — не «частично
  неверно», а целиком, с неотличимым от «скрипт не скомпилировался» признаком.
- **`getownercontainer(connected_to_object) = getownercontainer(objid)`** — вендор
  отсекает связи, уходящие в другой контейнер. **Решение «проба этого не делает»
  отменено правкой после ревью PR #13**, и здесь снято, чтобы план не читался как
  действующий: отказ по защите 11 в этом случае **правильный, но избыточный** —
  одна связь через границу контейнера делала модель нечитаемой **целиком**, тогда
  как у фильтра по типу соседа уже принята ровно такая же цена «тихо потерять
  одно ребро». Форма взята вендорская, и это важнее, чем кажется: он сравнивает
  **владельцев двух объектов**, а не владельца соседа с `getcurrentcontainer`, —
  на верхнем уровне эти величины не обязаны совпадать, и вторая форма сломала бы
  чтение самой обычной страницы. Живого воспроизведения нет ни до, ни после
  входа внутрь контейнера: на демо связей наружу не нашлось.

- [ ] **Step 4: Прогнать — убедиться, что проходит**

Run: `python3.11 -m pytest tests/unit/test_topology.py -q`
Expected: PASS

- [ ] **Step 5: Добавить модуль в mypy-гейт**

В `pyproject.toml`, в `[tool.mypy] files`, добавить `"simintech_api/topology.py"` после `"simintech_api/tbl.py"`.

Run: `mypy --platform win32`

Expected: **сначала одна ошибка**, и это ожидаемо — план её не предвидел:

```
simintech_api/topology.py:NN: error: Incompatible types in assignment
  (expression has type "int", base class "tuple" defined the type as ...)  [assignment]
```

Номер строки здесь не проставлен намеренно: он сдвинется после Tasks 5–6, а
ошибка опознаётся по тексту — `Incompatible types in assignment` на поле
`PortRow.index`.

Причина: поле `PortRow.index` затеняет метод `tuple.index`, унаследованный
`NamedTuple`. Имя поля задано протоколом и менять его нельзя — адрес порта это
именно индекс, и он так называется во всех последующих задачах и тестах.
Затенение безвредно в работе (метод `tuple.index` у этих строк никто не зовёт),
но mypy его видит. Закрывается **точечным подавлением с объяснением**:

```python
    index: int  # type: ignore[assignment]  # затеняет tuple.index
```

**Форма подавления — не вкусовщина.** Первая редакция плана писала причину прямо
после кода (`# type: ignore[assignment]  — затеняет tuple.index`), и mypy 2.3.1
отвергает это: любой текст после кода подавления даёт **вторую** ошибку
`Invalid "type: ignore" comment [syntax]`. Законны ровно две формы — ничего после
кода либо ещё один `#`-комментарий. Проверено дифференциально, с латиницей и
кириллицей. Причина подавления поэтому живёт в докстринге `PortRow`, а в строке
остаётся короткий комментарий.

Подавление обязано быть узким (`[assignment]`) и объяснённым: `type: ignore` без
кода глушил бы и будущие настоящие ошибки на этой строке, а в этом пакете до сих
пор не было ни одного подавления вовсе — первое должно быть образцовым.

После правки: `Success: no issues found in 17 source files`.

- [ ] **Step 6: Коммит**

```bash
git add simintech_api/topology.py tests/unit/test_topology.py pyproject.toml
git commit -m "feat(topology): сборка тела пробы, три фазы"
```

---

## Task 8: COM-обёртка

**Files:**
- Create: `simintech_api/core/topology.py`
- Modify: `simintech_api/script_probe.py` — перевод обратных слэшей пути в прямые
- Modify: `tests/unit/test_script_probe.py` — там закреплено текущее поведение
  дословно: `assert 'createfile("C:\\tmp\\out.txt", -1)' in script`. Правка выше
  **уронит этот тест**, и это ожидаемо: тест закрепляет поведение, которое мы
  сознательно меняем. Привести его к новому (прямые слэши), а не подгонять код
  под тест.
- Test: `tests/unit/test_topology.py`

- [ ] **Step 1: Написать падающий тест**

```python
def test_read_topology_uses_the_bridge(tmp_path, monkeypatch):
    """Обёртка не дублирует транспорт: она зовёт ScriptBridge.run_probe."""
    from simintech_api.core import topology as core_topology
    from simintech_api.script_probe import ProbeResult

    calls = []

    class FakeBridge:
        def __init__(self, client, project_id):
            calls.append(("init", client, project_id))

        def run_probe(self, body, result_path):
            calls.append(("run_probe", body, result_path))
            return ProbeResult(lines=HAPPY.splitlines(), complete=True)

    monkeypatch.setattr(core_topology, "ScriptBridge", FakeBridge)
    client = object()
    topology = core_topology.read_topology(client, 42, tmp_path / "t.txt")

    assert calls[0] == ("init", client, 42)
    assert calls[1] == ("run_probe", build_topology_probe(), tmp_path / "t.txt")
    assert [row.name for row in topology.objects] == ["A", "B"]
```

**Поправка к плану: первые два утверждения были почти тавтологичны.** В первой
редакции стояло `calls[0] == ("init", calls[0][1], 42)` — клиент сравнивался сам
с собой, поэтому его тождество не проверялось вовсе; и `calls[1][0] == "run_probe"`
проверял только имя метода. Измерено: при таком тесте выживают мутанты «мост
получил чужой клиент», «аргументы `run_probe` переставлены», «в `run_probe`
ушло пустое тело» и «в `run_probe` ушёл чужой путь» — то есть ровно то, ради
чего обёртка и существует: **передать телу пробу, а мосту — путь вызывающего**.
Сравнение всей тройки аргументов закрывает все четыре.

- [ ] **Step 2: Прогнать — убедиться, что падает**

Run: `python3.11 -m pytest tests/unit/test_topology.py -q`
Expected: FAIL — нет модуля `core.topology`

- [ ] **Step 3: Реализовать**

Создать `simintech_api/core/topology.py`:

```python
"""Чтение топологии проекта поверх скриптового моста.

Тонкая обёртка: транспорт целиком в `ScriptBridge`, здесь только связывание
его с протоколом топологии. Дублировать проверки моста (маркер завершения,
рост модельного времени, возврат прежнего скрипта) нельзя — иначе они начнут
расходиться, и при отказе будет не понять, что сломалось: транспорт или проба.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..topology import Topology, build_topology_probe, parse_topology
from .script_bridge import ScriptBridge

if TYPE_CHECKING:
    from .com_client import COMClient


def read_topology(client: "COMClient", project_id: int,
                  result_path: Path) -> Topology:
    """Прочитать топологию текущего контейнера проекта.

    Файл по `result_path` — рабочий: мост пишет в него результат пробы и
    удаляет прежний.
    """

**Путь к файлу результата переводится в прямые слэши — и это правка
`build_probe_script`, а не обёртки.** `ResultPath` на Windows печатается с
обратными слэшами, а путь подставляется в строковый литерал встроенного языка.
Разбирает ли тот `\t` и `\r` как управляющие последовательности — **не
измерено**. Тогда `C:\tmp\result.txt` превратился бы в `C:<TAB>mp<CR>esult.txt`,
`createfile` ушёл бы не туда, а отказ выглядел бы как «нет ровно одной пары
маркеров» — то есть как обычный сбой скрипта.

Довод против тревоги есть, и он сильный: язык Паскалевый, а в Паскале обратный
слэш в строковом литерале управляющей последовательностью **не** является; в
теле для табуляции взято `chr(9)` потому, что так пишет вендор, а не потому, что
`"\t"` сломается. Живой прогон моста на Windows эту вилку тоже не развёл: путь
`tmp_path` от pytest содержал `\U`, `\A`, `\L`, `\p` — ни одной опасной пары.

Прямые слэши безопасны при **обоих** прочтениях: Windows их принимает, а
экранировать в них нечего. Поэтому перевод делается в `build_probe_script` (там
же, где путь уже проверяется на кавычку и перевод строки — ответственность та
же), а не в вызывающем коде: `Path` на Windows печатается с обратными слэшами
всегда, и обойти это на стороне вызывающего нельзя.
    result = ScriptBridge(client, project_id).run_probe(
        build_topology_probe(), result_path)
    return parse_topology("\n".join(result.lines))
```

- [ ] **Step 4: Прогнать — убедиться, что проходит**

Run: `python3.11 -m pytest tests/unit/test_topology.py -q`
Expected: PASS

- [ ] **Step 5: Полный прогон**

Run: `python3.11 -m pytest -q && flake8 && mypy --platform win32`
Expected: всё зелёное

- [ ] **Step 6: Коммит**

```bash
git add simintech_api/core/topology.py tests/unit/test_topology.py
git commit -m "feat(topology): чтение топологии поверх ScriptBridge"
```

---

## Task 9: Живой прогон

**Files:**
- Create: `tests/integration/test_topology_live.py`

- [ ] **Step 1: Написать тест**

Порядок проверок — от того, что может **опровергнуть всю затею**, к тому, что
лишь подтверждает: сначала проба на демо вендора (работает ли `getportinfo`,
что возвращает `traceallports`, какой контейнер читается), и только потом
сверка с COM на своём проекте.

**Первый вопрос — входит ли исходный порт в свой же след.** Это не любопытство:
исчерпывающий перебор законных моделей (Task 6) показал, что защита 13 —
**единственная** причина, по которой разбор может отвергнуть законный вход. Если
`traceallports(portid, 0)` включает сам `portid`, тело пробы (Task 7) напишет
строку `conn A 0 A 0` для каждого порта — и `parse_topology` отвергнет **всю**
модель на первой же строке связи, с сообщением «петля». Проба станет нечитаемой
целиком, а не «частично неверной».

Вот почему этот вопрос идёт первым, а не в общем списке диагностики. Ответ надо
записать в спецификацию рядом с обоснованием защиты 13 — вместе с тем, что
показал прогон. Если окажется, что исходный порт в списке есть, **защита 13 всё
равно верна** (петля в протоколе — это отказ), но тело пробы обязано отфильтровать
свой порт до записи строки, и это правка Task 7, а не Task 6.

**Косвенное свидетельство есть, и оно против самовключения.** Скрипт вендора
(`bin/include_mvtu/export_scheme_functions.inc:84-116`) зовёт `traceallports(portid,0)`
и для **входов** берёт ровно первый элемент (`min(1, cols(...))`). Его эталонный
JSON содержит 64 записи о связях на 64 порта — по одной на порт. Будь исходный
порт в списке, входы указывали бы сами на себя, и вендор это заметил бы. Но
косвенное свидетельство не заменяет измерения: фильтр вендора
`getownercontainer(...) = getownercontainer(objid)` отсекает чужие контейнеры, а
не сам порт, — то есть прямо этот вопрос его код не проверяет.

```python
"""Живой прогон топологической пробы: SimInTech, реальный COM."""

import os
import shutil
import sys

import pytest

from simintech_api import COMClient
from simintech_api.core.project import Project
from simintech_api.core.topology import read_topology
from simintech_api.topology import connection_key

pytestmark = pytest.mark.integration

#: Демо вендора с заведомо известной топологией. Эталон — его JSON, снятый
#: самим вендором. Измерено по файлу: 35 объектов, 64 записи о портах с
#: проводом (32 входа и 32 выхода), 64 записи `ConnectedTo` = **32 уникальные
#: связи**, самоссылок ноль, все соседи — среди тех же 35 объектов.
#:
#: Числа нельзя путать: 64 — это количество записей в выгрузке вендора (связь
#: записана с обеих сторон, и только для портов с проводом), а проба печатает
#: **все** порты и схлопывает связь каноническим ключом. Ожидаемый результат
#: пробы: 35 объектов, ≥64 порта, **32 связи**.
VENDOR_DEMO = (r"C:\SimInTech64\Demo\Приёмы работы\Анализ и отчеты"
               r"\Анализ топологии скриптами и экспорт в json"
               r"\Экспорт топологии и свойств в json"
               r"\Экспорт топологии и свойств в json.prt")


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


def test_probe_works_on_vendor_demo(client, tmp_path):
    """Первый вопрос: работает ли проба и что даёт `getportinfo`/`traceallports`.

    Это может опровергнуть всю затею, поэтому идёт первым. Здесь только
    минимум, без которого остальное бессмысленно: проба отработала, объекты
    есть, направления портов попадают в три известных значения.

    Прогон на КОПИИ: демо вендора не трогаем.
    """
    if not os.path.exists(VENDOR_DEMO):
        pytest.skip(f"нет демо вендора: {VENDOR_DEMO}")
    work = tmp_path / "demo.prt"
    shutil.copy2(VENDOR_DEMO, work)
    project = Project.open(client, str(work))
    try:
        topology = read_topology(client, project.id, tmp_path / "t.txt")
        assert topology.objects, "проба не вернула ни одного объекта"
        assert {p.direction for p in topology.ports} <= {"in", "out", "undirected"}, (
            "getportinfo вернул режим вне трёх известных значений")
        print(f"\nдемо вендора: объектов {len(topology.objects)}, "
              f"портов {len(topology.ports)}, связей {len(topology.connections)}")
        print(f"направления: "
              f"{sorted({p.direction for p in topology.ports})}")
    finally:
        project.close()


def test_current_container_identity(client, tmp_path):
    """Какой контейнер читает проба — обязательный вопрос первого прогона.

    Эталон вендора снят на внутренней странице `acrms_Circuit1` (имя его файла —
    `…json.acrms_Circuit1.json`), а проба читает текущий контейнер. Совпадают ли
    они, выясняется **сравнением с COM**: если проба вернула столько же
    объектов, сколько COM видит на главной странице, читалась главная; если
    больше — читалась внутренняя. Сравнивать числа с эталоном можно только
    после этого ответа.
    """
    if not os.path.exists(VENDOR_DEMO):
        pytest.skip(f"нет демо вендора: {VENDOR_DEMO}")
    work = tmp_path / "demo.prt"
    shutil.copy2(VENDOR_DEMO, work)
    project = Project.open(client, str(work))
    try:
        topology = read_topology(client, project.id, tmp_path / "t.txt")
        by_com = client.call("GetPageObjectCount", project.id)
        print(f"\nпроба вернула объектов {len(topology.objects)}, "
              f"COM видит на главной странице {by_com}")
        if len(topology.objects) == by_com:
            print("вывод: текущий контейнер — главная страница; "
                  "эталон вендора снят с внутренней, сравнивать числа нельзя")
        else:
            print("вывод: текущий контейнер — не главная страница; "
                  "сверить с эталоном вендора (35 объектов, 32 связи) и "
                  "записать результат в спецификацию")
    finally:
        project.close()


def test_connections_raw_and_collapsed_are_reported(client, tmp_path):
    """Диагностика, а не защита: возвращает ли `traceallports` обе стороны.

    Проверять здесь схлопывание бессмысленно: разбор хранит связи по
    каноническому ключу, и дубликат по построению невозможен — тест был бы
    вакуумным. Поэтому сообщаем числа и ничего не утверждаем: сравнение числа
    сырых строк пробы с числом уникальных связей показывает, приходит ли связь
    с обеих сторон, и это стоит знать перед следующей работой.
    """
    project = Project.from_template(client)
    project.set_calc_end_time(1.0)
    try:
        topology = read_topology(client, project.id, tmp_path / "t.txt")
        keys = {connection_key(c) for c in topology.connections}
        print(f"\nсвязей после схлопывания: {len(topology.connections)}, "
              f"уникальных ключей: {len(keys)}")
        assert len(keys) == len(topology.connections), (
            "разбор вернул две записи об одной связи — канонизация сломана")
    finally:
        project.close()


def test_objects_match_com(client, tmp_path):
    """Сверка с COM — источник, который для объектов сильнее пробы.

    Строго проверяются только **число объектов** и **то, что COM находит
    каждый объект по имени**: если не находит, две картины мира расходятся в
    самой идентичности объекта, и это противоречие, а не расхождение форматов.

    **Имена классов не сверяются равенством.** `Block.class_name` в самой
    библиотеке документирует, что для блока-плагина свойство `ClassName`
    возвращает имя плагина, а не класс, — то есть равенство может не выполняться
    законно. Поэтому классы **печатаются рядом**, а расхождение становится
    находкой первого прогона, а не красным тестом на непроверенном допущении.
    """
    project = Project.from_template(client)
    project.set_calc_end_time(1.0)
    try:
        topology = read_topology(client, project.id, tmp_path / "t.txt")
        assert len(topology.objects) == client.call("GetPageObjectCount", project.id)
        mismatched = []
        for row in topology.objects:
            block = project.get_main_page().find_block(row.name)
            assert block is not None, f"COM не находит объект {row.name!r}"
            if block.class_name != row.class_name:
                mismatched.append((row.name, row.class_name, block.class_name))
        if mismatched:
            print("\nкласс от языка и класс от COM разошлись "
                  f"({len(mismatched)} из {len(topology.objects)}):")
            for name, by_lang, by_com in mismatched[:10]:
                print(f"  {name}: язык {by_lang!r}, COM {by_com!r}")
            print("это находка первого прогона — записать в спецификацию")
    finally:
        project.close()
```

- [ ] **Step 2: Прогнать на Windows**

Run: `python3.11 -m pytest tests/integration/test_topology_live.py -m integration -q -s`
Expected: PASS либо **содержательный отказ**, который надо разобрать, а не заглушить. Печатаемые числа — ответ на вопрос о текущем контейнере; записать их в спецификацию.

- [ ] **Step 3: Сверить с эталоном вендора — если контейнер тот же**

Только если шаг 2 показал, что текущий контейнер и есть `acrms_Circuit1`:
открыть демо `Demo/Приёмы работы/Анализ и отчеты/…/Экспорт топологии и свойств
в json.prt` и сверить числа с эталоном: **35 объектов, ≥64 порта, 32 связи**
(в выгрузке вендора 64 — это записи о портах и о связях с обеих сторон, а не
уникальные связи; спутать эти числа значит прочесть верный результат как
дефект пробы). **Если
контейнер другой — сравнение не делать** и записать в спецификацию фактическое
поведение: критерий формулируется по факту, а не подгоняется.

- [ ] **Step 4: Коммит**

```bash
git add tests/integration/test_topology_live.py
git commit -m "test(topology): живой прогон и сверка с COM"
```

---

## Task 10: Документация

**Files:**
- Modify: `docs/api.md`, `CLAUDE.md`

- [ ] **Step 1: Раздел в `docs/api.md`**

После раздела `ScriptBridge` — короткий раздел `read_topology`: что читает
(только текущий контейнер), что возвращает, чего не делает (субмодели,
координаты), и что отказ разбора — это `TopologyError`, а не «пустая
топология».

- [ ] **Step 2: Факты в `CLAUDE.md`**

В «Библиотека: ключевые факты» дописать: протокол трёх фаз и **почему** он
такой (иначе генератор породит ссылку вперёд, которую разбор отвергает);
что связи канонизируются; что `get_wires` — диагностика, а не источник сверки.

- [ ] **Step 3: Полный прогон**

Run: `python3.11 -m pytest -q && flake8 && mypy --platform win32`
Expected: всё зелёное

- [ ] **Step 4: Коммит**

```bash
git add docs/api.md CLAUDE.md
git commit -m "docs: чтение топологии через встроенный язык"
```

---

## Что этот план не делает

- **Не читает субмодели.** Только текущий контейнер: рекурсивный снимок — это
  другая модель данных (путь контейнера, адресация портов внутри вложенных,
  связи через границу), и он требует отдельной спецификации.
- **Не правит топологию.** Ни удаления блоков, ни портов.
- **Не выводит в MCP.** Как и мост, наружу инструментом не отдаётся.
- **Не проверяет предположения о модели** (`out` только к `in`, одно
  соединение на порт) — пока живой прогон их не подтвердит.
