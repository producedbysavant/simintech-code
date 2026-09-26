"""Эталон вендора как источник: его собственные инварианты и сверка с кодом.

Числа эталона (35 объектов, 64 записи о портах, 64 записи `ConnectedTo`) жили
константой внутри живого теста, а сам файл
`tests/integration/fixtures/vendor_topology_reference.json` не читал ни один
тест — то есть мог разойтись с тестом молча, а сверка с ним сводилась бы к
сравнению числа с числом, вбитым руками. Здесь эталон становится **несущим**:
разбирается общим модулем (`tests/vendor_reference.py`) и проверяется на своих
же инвариантах. Живой тест сверяет с разобранным эталоном уже **имена,
направления и ключи связей**, а не счётчики.

Разбор построчный — файл не валидный JSON (в поле `Value` одного свойства
записан RTF с незаэкраненными слэшами, см. `fixtures/README.md`); читается он
через общий модуль, чтобы у живого теста и здесь был **один** разбор.
"""

import os
import sys
from collections import Counter

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import vendor_reference  # noqa: E402
from vendor_reference import connection_key_of, load_reference  # noqa: E402

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from simintech_api.topology import Connection, connection_key  # noqa: E402

#: Имена объектов эталона — списком, а не числом. Число 35 ничего не говорит о
#: том, **кто** в эталоне: подмена имени прошла бы незамеченной, а живой тест
#: сверял бы множество имён с эталоном, у которого имя испорчено, — и красным
#: стал бы он, обвинив пробу. Список снят с самого файла и живёт здесь, чтобы
#: расхождение с файлом было видно в юнит-тесте, где нет ни COM, ни демо.
EXPECTED_NAMES = frozenset({
    "Key_manual_button_1",
    "Key_manual_button_2",
    "Key_manual_button_3",
    "Macro235",
    "Macro236",
    "Macro245",
    "Macro246",
    "Macro248",
    "Macro263",
    "Macro268",
    "Macro270",
    "Macro272",
    "Macro273",
    "Macro274",
    "Macro275",
    "RTFComment6",
    "acrms_Ground4",
    "acrms_Ground6",
    "acrms_Q_P3",
    "acrms_Q_P4",
    "acrms_Q_P5",
    "acrms_node15",
    "acrms_node16",
    "acrms_node17",
    "acrms_node18",
    "acrms_node19",
    "acrms_node20",
    "acrms_node21",
    "acrms_node22",
    "acrms_node24",
    "acrms_node2v5",
    "acrms_node2v7",
    "acrms_node2v8",
    "acrms_node2v9",
    "k1",
})


@pytest.fixture(scope="module")
def reference():
    return load_reference()


def test_objects_are_the_expected_thirty_five(reference):
    """Список имён — не число: 35 объектов это именно эти имена."""
    names = [row.name for row in reference.objects]
    assert len(names) == 35
    assert len(set(names)) == 35, "имена объектов эталона обязаны быть уникальны"
    assert set(names) == EXPECTED_NAMES, (
        f"имена разошлись с эталоном: лишние {sorted(set(names) - EXPECTED_NAMES)}, "
        f"пропавшие {sorted(EXPECTED_NAMES - set(names))}")


def test_every_object_has_a_class(reference):
    assert all(row.class_name for row in reference.objects), (
        "объект эталона без класса — эталон испорчен")


def test_comment_object_is_the_documented_counterexample(reference):
    """`RTFComment6` класса «Комментарий» — доказательство оговорки про фильтр.

    В документации сказано, что формулировка «объекты модели» неверна: тип 100
    есть и у подписи. Эталон это подтверждает **своим составом**: его писал
    скрипт вендора с фильтром `getobjtypeid ∈ {100, 102}`, поэтому подпись,
    попавшая в эталонные 35, прошла этот фильтр. Проверка держит оговорку
    привязанной к файлу, а не к пересказу.
    """
    by_name = {row.name: row.class_name for row in reference.objects}
    assert by_name.get("RTFComment6") == "Комментарий"


def test_ports_are_the_wired_ones_and_only_they(reference):
    """64 записи о портах — 32 входа и 32 выхода, по одной на провод.

    Это не «порты страницы»: вендор выгружает только порты **с проводом**, и
    именно поэтому число 64 нельзя требовать от пробы равенством — проба
    печатает **все** порты отобранных объектов. Здесь проверяется инвариант
    самого эталона, а на живой сверке из него следует `>=`, а не `==`.
    """
    assert len(reference.ports) == 64
    directions = Counter(port.direction for port in reference.ports)
    assert directions == {"in": 32, "out": 32}, (
        f"направления эталона разошлись: {dict(directions)}")
    addresses = [(port.object_name, port.index) for port in reference.ports]
    assert len(set(addresses)) == len(addresses), (
        "порт эталона объявлен дважды — адрес порта обязан быть уникален")


def test_port_objects_are_declared(reference):
    declared = {row.name for row in reference.objects}
    undeclared = sorted({p.object_name for p in reference.ports} - declared)
    assert undeclared == [], (
        f"порты объявлены для несуществующих объектов: {undeclared}")


def test_connections_are_recorded_from_both_ends(reference):
    """64 записи `ConnectedTo` и 32 канонических ключа — по две записи на связь.

    Ради этого свойства канонизация и существует: `traceallports` отдаёт
    цепочку с обеих сторон. Здесь оно проверяется как инвариант **эталона**, а
    в живом тесте — как совпадение множеств ключей.
    """
    assert len(reference.connections) == 64
    per_key = Counter(connection_key_of(record) for record in reference.connections)
    assert set(per_key.values()) == {2}, (
        f"не каждая связь записана с обоих концов: {dict(per_key)}")
    assert len(per_key) == 32, f"ключей {len(per_key)}, а не 32"


def test_connections_reference_declared_ports(reference):
    """Оба конца каждой связи объявлены портами эталона.

    Проверка делает эталон **связным**: имя или индекс, испорченные в одном
    месте файла, перестают подтверждаться его же содержимым.
    """
    addresses = {(port.object_name, port.index) for port in reference.ports}
    declared = {row.name for row in reference.objects}
    for record in reference.connections:
        assert record.object_name in declared, record
        assert record.peer_name in declared, record
        assert (record.object_name, record.index) in addresses, record
        assert (record.peer_name, record.peer_index) in addresses, record


def test_connections_have_no_self_loops(reference):
    """Самоссылок в эталоне нет — это измеренный факт, а не допущение.

    Живой прогон отвечал на вопрос, входит ли порт в свой же след; эталон
    отвечает на него независимо: в выгрузке вендора ни одна запись не
    соединяет порт сам с собой.
    """
    loops = [record for record in reference.connections
             if (record.object_name, record.index)
             == (record.peer_name, record.peer_index)]
    assert loops == [], f"в эталоне самоссылки: {loops}"


def test_library_canonicalisation_agrees_with_the_reference(reference):
    """`connection_key` совпадает с независимой канонизацией эталона.

    В `vendor_reference` ключ считается **своим** кодом, а не вызовом
    библиотечного `connection_key`. Иначе поломка канонизации сдвинула бы обе
    стороны живой сверки одинаково, и сравнение множеств ключей осталось бы
    зелёным, ничего не проверяя. Здесь две реализации сводятся в одной точке —
    на настоящих данных эталона.
    """
    for record in reference.connections:
        mine = connection_key_of(record)
        library = connection_key(Connection(
            object_a=record.object_name, index_a=record.index,
            object_b=record.peer_name, index_b=record.peer_index))
        assert mine == library, (record, mine, library)


def test_parser_is_strict_about_the_grammar(tmp_path):
    """Разбор отвергает испорченный файл, а не возвращает что попало.

    Проверяется не «на всякий случай», а потому что на этом разборе стоит
    живая сверка: молча неверный эталон сделал бы её бессмысленной.
    """
    text = vendor_reference.REFERENCE_PATH.read_text(encoding="utf-8")
    broken = text.replace('"SelfPortDirection": "input"',
                          '"SelfPortDirection": "sideways"', 1)
    assert broken != text
    path = tmp_path / "broken.json"
    path.write_text(broken, encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        load_reference(path)
    assert "направление" in str(exc.value)
