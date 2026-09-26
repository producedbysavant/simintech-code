"""Разбор эталонной выгрузки вендора — **один** на юнит-тест и на живой.

Модуль лежит в `tests/`, а не в `tests/unit/`: им пользуются оба уровня. Юнит-тест
(`tests/unit/test_vendor_reference.py`) проверяет на нём инварианты самого
эталона, живой (`tests/integration/test_topology_live.py`) сверяет с ним выдачу
пробы — имена объектов, направления портов и ключи связей. Два отдельных разбора
здесь разъехались бы: живой тест проверял бы не то, что закреплено юнит-тестом.

Файл `integration/fixtures/vendor_topology_reference.json` **не является валидным
JSON** (в поле `Value` одного свойства записан RTF с незаэкраненными слэшами,
см. `fixtures/README.md`), поэтому разбирается построчно. Про сам файл надо знать
ещё две вещи, обе измерены:

- переводы строк — CRLF, поэтому разбор идёт через `splitlines()`, а не по `\\n`;
- в файле **ровно один байт NUL** (в RTF-значении последнего свойства, строка
  1804). Из-за него `grep` без `-a` считает файл двоичным и **молчит** о
  совпадениях: «вывод пуст» здесь не значит «совпадений нет». Разбору этот байт
  не мешает — он лежит в поле, которое разбор не читает.

Ключ связи считается здесь **своим** кодом, а не вызовом библиотечного
`connection_key` — иначе поломка канонизации сдвинула бы обе стороны живой сверки
одинаково, и сравнение множеств ключей осталось бы зелёным. Согласие двух
реализаций проверяется отдельно, на этих же данных.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple

#: Адрес порта — (имя объекта, индекс); ключ связи — два адреса.
Address = Tuple[str, int]
ConnectionKey = Tuple[Address, Address]

REFERENCE_PATH = (Path(__file__).resolve().parent / "integration" / "fixtures"
                  / "vendor_topology_reference.json")

#: Направление в эталоне и в протоколе пробы названы по-разному: вендор пишет
#: `input`/`output`, проба — `in`/`out`/`undirected`. Сопоставление живёт здесь
#: одним словарём, чтобы живой тест не заводил своё и не разошёлся с юнит-тестом.
DIRECTION_FROM_VENDOR = {"input": "in", "output": "out"}


class ReferenceObject(NamedTuple):
    """Объект эталона: имя и класс."""

    name: str
    class_name: str


class ReferencePort(NamedTuple):
    """Порт эталона — только порты **с проводом**: вендор выгружает лишь их."""

    object_name: str
    index: int
    name: str
    direction: str  # "in" | "out"


class ReferenceConnection(NamedTuple):
    """Одна запись `ConnectedTo`: порт объекта и один его сосед.

    Записей вдвое больше, чем связей: связь выгружена с обоих концов.
    """

    object_name: str
    index: int
    peer_name: str
    peer_index: int


class VendorReference(NamedTuple):
    """Разобранный эталон: объекты, порты с проводом и записи о связях."""

    objects: List[ReferenceObject]
    ports: List[ReferencePort]
    connections: List[ReferenceConnection]

    def port_directions(self) -> Dict[Address, str]:
        """Направление по адресу порта — то, с чем сверяется выдача пробы."""
        return {(port.object_name, port.index): port.direction
                for port in self.ports}

    def connection_keys(self) -> set:
        """Множество канонических ключей связей."""
        return {connection_key_of(record) for record in self.connections}


def connection_key_of(record: ReferenceConnection) -> ConnectionKey:
    """Канонический ключ записи эталона: концы упорядочены по (имя, индекс).

    Независимая реализация того же правила, что и `topology.connection_key`:
    сравнивать ключи пробы с ключами эталона надо по одному правилу, но считать
    его обеими сторонами одной функцией нельзя (см. докстринг модуля).
    """
    first = (record.object_name, record.index)
    second = (record.peer_name, record.peer_index)
    return (first, second) if first <= second else (second, first)


#: Отступы — часть грамматики файла, а не оформление: на одном уровне лежат
#: ключи объектов, на другом — ключи свойств, и `Name` есть у обоих. Разбор
#: опирается на них явно, чтобы «найти все Name» не превратилось в подсчёт
#: свойств вместо объектов.
_OBJECT_NAME = re.compile(r'^ {3}"Name": "(?P<value>.*)",?$')
_OBJECT_CLASS = re.compile(r'^ {3}"Class": "(?P<value>.*)",?$')
_CONNECTED_TO = re.compile(r'^ {6}"ConnectedTo": \[$')
_SELF_NAME = re.compile(r'^ {6}"SelfPortName": "(?P<value>.*)",?$')
_SELF_INDEX = re.compile(r'^ {6}"SelfPortIndex": "(?P<value>\d+)",?$')
_SELF_DIRECTION = re.compile(
    r'^ {6}"SelfPortDirection": "(?P<value>[A-Za-z]+)",?$')
_PEER_NAME = re.compile(r'^ {9}"ConnectedObjName": "(?P<value>.*)",?$')
_PEER_INDEX = re.compile(r'^ {9}"ConnectedObjPortIndex": "(?P<value>\d+)",?$')


def load_reference(path: Path = REFERENCE_PATH) -> VendorReference:
    """Прочитать и разобрать эталон (по умолчанию — поставляемый файл)."""
    return parse_reference(path.read_text(encoding="utf-8"))


def parse_reference(text: str) -> VendorReference:
    """Разобрать выгрузку вендора построчно.

    Разбор строг к **грамматике** файла: число записей о связях обязано сойтись
    с числом массивов `ConnectedTo`, запись не может остаться незакрытой или
    содержать два индекса порта, направление — только из
    `DIRECTION_FROM_VENDOR`. Расхождение — `ValueError`, а не «сколько
    получилось»: на этом разборе стоит живая сверка, и молча неполный эталон
    сделал бы её бессмысленной.

    **Смысловые** утверждения (уникальность имён, наличие класса, самоссылки,
    ссылки на объявленные порты) здесь не проверяются — они принадлежат
    юнит-тесту: проверка внутри разбора сделала бы его тесты вакуумными.
    """
    objects: List[ReferenceObject] = []
    ports: List[ReferencePort] = []
    connections: List[ReferenceConnection] = []
    pending: List[Address] = []
    object_name = ""
    peer_name: Optional[str] = None
    record_name = ""
    record_index: Optional[int] = None
    records = 0
    connected_to = 0

    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        if match := _OBJECT_NAME.match(line):
            if record_index is not None or pending:
                raise ValueError(
                    f"строка {number}: объект начался внутри незакрытой записи "
                    "о связи")
            object_name = match["value"]
            objects.append(ReferenceObject(object_name, ""))
        elif match := _OBJECT_CLASS.match(line):
            if not objects:
                raise ValueError(
                    f"строка {number}: класс без объекта — разбор разошёлся с "
                    "файлом")
            objects[-1] = ReferenceObject(objects[-1].name, match["value"])
        elif _CONNECTED_TO.match(line):
            connected_to += 1
        elif match := _PEER_NAME.match(line):
            if peer_name is not None or record_index is not None:
                raise ValueError(
                    f"строка {number}: сосед объявлен внутри чужой записи")
            peer_name = match["value"]
        elif match := _PEER_INDEX.match(line):
            if peer_name is None:
                raise ValueError(
                    f"строка {number}: индекс соседа без имени соседа")
            pending.append((peer_name, int(match["value"])))
            peer_name = None
        elif match := _SELF_NAME.match(line):
            if record_name:
                raise ValueError(f"строка {number}: имя порта объявлено дважды")
            record_name = match["value"]
        elif match := _SELF_INDEX.match(line):
            if record_index is not None:
                raise ValueError(f"строка {number}: индекс порта объявлен дважды")
            record_index = int(match["value"])
        elif match := _SELF_DIRECTION.match(line):
            if record_index is None:
                raise ValueError(
                    f"строка {number}: направление порта без индекса порта")
            direction = DIRECTION_FROM_VENDOR.get(match["value"])
            if direction is None:
                raise ValueError(
                    f"строка {number}: неизвестное направление порта "
                    f"{match['value']!r}, допустимы "
                    f"{', '.join(DIRECTION_FROM_VENDOR)}")
            if not pending:
                raise ValueError(
                    f"строка {number}: у порта {object_name}.{record_index} нет "
                    "соседей — запись выгрузки обязана содержать `ConnectedTo`")
            ports.append(ReferencePort(object_name, record_index, record_name,
                                       direction))
            for peer_object, peer_index in pending:
                connections.append(ReferenceConnection(
                    object_name=object_name, index=record_index,
                    peer_name=peer_object, peer_index=peer_index))
            pending.clear()
            record_name = ""
            record_index = None
            records += 1

    if record_index is not None or pending or peer_name is not None:
        raise ValueError("последняя запись о связи не закрыта")
    if records != connected_to:
        raise ValueError(
            f"разобрано записей о связях {records}, а массивов ConnectedTo "
            f"{connected_to} — разбор разошёлся с файлом")

    return VendorReference(objects=objects, ports=ports,
                           connections=connections)
