"""Разбор протокола топологии: грамматика, фазы, ссылки, канонизация."""

import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest  # noqa: E402

from simintech_api.exceptions import SimInTechError, TopologyError  # noqa: E402
from simintech_api.topology import (  # noqa: E402
    CONN_ROW,
    DIRECTIONS,
    ELIGIBLE_OBJECT_TYPES,
    OBJECT_ROW,
    PORT_ROW,
    Connection,
    ObjectRow,
    PortRow,
    Topology,
    build_topology_probe,
    connection_key,
    parse_topology,
)

#: Функции, подтверждённые поставкой, — и весь список. Источник подтверждения
#: не реестр (он даёт существование имени, но не работоспособность), а
#: **работающий скрипт вендора** `bin/include_mvtu/export_sheme_functions.inc`
#: и демо «Анализ топологии скриптами». Один список на две проверки: и «все
#: названы», и «нет незнакомых» — иначе второй список разошёлся бы с первым.
#:
#: Два имени подтверждены иначе, и это сказано явно, чтобы следующему читателю
#: не показалось, будто они попали сюда на глазок:
#:
#: - `getportwireid` — тем же вендорским файлом, строкой 85 (условие `<> 0`
#:   вокруг `traceallports`), то есть происхождение то же, что у остальных;
#: - `getcurrentcontainer` — в `export_sheme_functions.inc` его **нет**, но он
#:   есть в другом include поставки (`developerKit_RunGuiTest.inc:203`) и в
#:   реестре со страницей справки. Решающее подтверждение сильнее обоих:
#:   эксперимент D спецификации моста измерил его в работе — скрипт из-под COM
#:   дал файл с `PROBE objects=7`, а `GetPageObjectCount` по COM дал те же 7, —
#:   то есть сверка с независимым источником, которой у вендорских имён нет.
#:
#: Зовётся он **без скобок**, поэтому в проверку вызовов не попадал бы вовсе —
#: и без него проверка на незнакомые имена краснеет на настоящем теле.
CONFIRMED_FUNCTIONS = (
    "getobjcount", "getobj", "getobjname", "getobjclassname",
    "getblockportcount", "getblockportid", "getportinfo", "traceallports",
    "getportblockid", "getportindex", "cols", "inttostr", "chr", "writelnutf8",
    "getcurrentcontainer", "getportwireid", "getobjtypeid",
    # Подтверждён тем же вендорским файлом, строкой 107: `if
    # getownercontainer(connected_to_object) = getownercontainer(objid) then` —
    # то есть имя зовётся рабочей поставкой, а не выведено из реестра. Нужен он
    # там же, где и вендору: `traceallports` отдаёт соседей любого контейнера.
    "getownercontainer",
    # Подтверждён тем же вендорским файлом, строкой 99: `if aportmode = 0 then
    # count_of_conn = min(1, cols(conn_port_list))` — правило кратности вендора,
    # которое проба теперь воспроизводит целиком, вместе с этим вызовом. Живой
    # прогон тела с `min` прошёл 2026-09-23: то же правило отдельной пробой дало
    # на демо ровно эталонные 32 связи, а на развилке — звезду вместо
    # треугольника.
    "min",
)

#: Ключевые слова и типы встроенного языка — всё, что телу разрешено писать
#: помимо подтверждённых функций и собственных переменных. `for(obj_idx=1, …)`
#: выглядит для проверки на отсутствие как вызов функции, а `integer` и
#: `intarray` — как имена, и без этих двух списков она ругалась бы на всю пробу.
#: `or` добавлен фильтром по типу: это оператор языка, а не имя — вендорский
#: скрипт пишет им то же самое условие (`export_sheme_functions.inc:44`).
LANGUAGE_KEYWORDS = ("var", "for", "begin", "end", "if", "then", "else", "or")
LANGUAGE_TYPES = ("integer", "string", "intarray")


def test_topology_error_is_simintech_error():
    assert issubclass(TopologyError, SimInTechError)


def test_connection_key_canonicalises_both_directions():
    """Зеркальные записи одной связи — ключ обязан совпасть."""
    forward = Connection("A", 0, "B", 1)
    backward = Connection("B", 1, "A", 0)
    assert connection_key(forward) == connection_key(backward)


def test_connection_key_canonicalises_same_object_names():
    """У связи внутри одного объекта имена концов равны — ключ всё равно общий."""
    assert connection_key(Connection("A", 0, "A", 1)) == connection_key(
        Connection("A", 1, "A", 0))


def test_connection_key_orders_by_object_name_then_index():
    assert connection_key(Connection("B", 0, "A", 5)) == (("A", 5), ("B", 0))


def test_connection_key_distinguishes_different_ports():
    a = connection_key(Connection("A", 0, "B", 0))
    b = connection_key(Connection("A", 1, "B", 0))
    assert a != b


def test_parse_stores_canonical_connection_ends():
    """Сохранённые концы связи — канонические, а не «как пришло последним».

    Связь может прийти зеркальными записями, и разбор кладёт её в словарь по ключу:
    до этой проверки значением оставалась **последняя** пришедшая ориентация,
    то есть `Connection` в результате зависел от порядка обхода портов, а
    `object_a` не значил ничего сверх «этот конец пришёл последним».

    Здесь закреплено, что значение равно ключу. Тогда `Topology.connections`
    детерминирован для одного и того же графа, и потребителю (в том числе
    MCP-слою) не нужно помнить, что порядок концов незначим.
    """
    topology = parse_topology(
        "object\tB\tУсилитель\nobject\tA\tСтупенька\n"
        "port\tB\t1\tin\tinport\nport\tA\t0\tout\toutport\n"
        "conn\tB\t1\tA\t0\n")
    assert topology.connections == [Connection("A", 0, "B", 1)]


def test_row_types_are_the_protocol_keywords():
    assert (OBJECT_ROW, PORT_ROW, CONN_ROW) == ("object", "port", "conn")


def test_topology_keeps_row_types():
    topology = Topology(objects=[ObjectRow("A", "Константа")], ports=[], connections=[])
    assert topology.objects[0].name == "A"
    assert PortRow("A", 0, "in", "x").direction == "in"


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


def test_blank_and_whitespace_only_lines_are_skipped():
    """Пустые и пробельные строки не считаются строками протокола.

    Пробельная строка здесь не для полноты: без неё проверка `line.strip()`
    неотличима от `line == ""`, и мутация, заменившая одно на другое, выживает.
    """
    topology = parse_topology(
        "\nobject\tA\tK\n\n   \n\t\nport\tA\t0\tin\tp\n")
    assert [row.name for row in topology.objects] == ["A"]
    assert len(topology.ports) == 1


@pytest.mark.parametrize("text, fragment", [
    ("blob\tA\tB\n", "неизвестный тип строки"),                # 1
    ("object\tA\n", "3 поля"),                                 # 2
    ("object\tA\tB\textra\n", "3 поля"),                       # 2
    ("object\tA\tB\tC\n", "3 поля"),                           # 3 (лишняя табуляция)
    # 2 (вторая половина): то же число полей у `port` и `conn`.
    # Параметры добавлены измерением в Task 6, а в плане стоят в сниппете
    # Task 4 — там, где им и место, это грамматика строки.
    # Снятие `len(fields) != 5` не красило **ни один** тест: у половины защиты
    # 2 не было сенсора вовсе, и лишнее поле в строке порта или связи молча
    # игнорировалось бы, а короткая строка падала бы `IndexError` вместо отказа.
    # Подстрока названа вместе со словом `port`/`conn`, а не общим «5 полей»:
    # иначе перепутанное в сообщении слово пережило бы эти параметры.
    ("port\tA\t0\tin\n", "у port должно быть 5 полей"),         # 2 (port, мало)
    ("port\tA\t0\tin\tp\textra\n", "у port должно быть 5 полей"),  # 2 (port, лишнее)
    ("conn\tA\t0\tB\n", "у conn должно быть 5 полей"),          # 2 (conn, мало)
    ("conn\tA\t0\tB\t0\textra\n", "у conn должно быть 5 полей"),   # 2 (conn, лишнее)
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


def test_direction_rejects_undocumented_port_mode():
    """Сырой режим порта в поле направления — отказ, а не молчаливый `undirected`.

    Проба пишет в это поле **число**, если среда вернула режим вне справки
    (`getportinfo`: 0 — вход, 1 — выход, 2 — ненаправленный). Здесь закреплено,
    что такой токен до `Topology` не доходит: иначе обещание «недокументированный
    режим виден как отказ» держалось бы на слове, а проба молча выдавала бы
    корректное на вид направление.

    Проверка не гипотетическая: на 1337 портах 70 демо-моделей встретились
    только режимы 0, 1 и 2, то есть режим 3 — признак дрейфа контракта, и
    сообщение обязано назвать именно то значение, которое пришло.
    """
    with pytest.raises(TopologyError) as exc:
        parse_topology("object\tA\tK\nport\tA\t0\t3\tp\n")
    assert "неизвестное направление порта '3'" in str(exc.value)


@pytest.mark.parametrize("text, fragment", [
    ("object\t\tB\n", "пустое имя объекта"),                          # 12
    ("object\tA\t\n", "пустой класс"),                                # 12
])
def test_empty_required_fields_rejected(text, fragment):
    """Пустое имя или класс объекта — отказ.

    Имя объекта — ключ, по которому адресуются порты и связи; объект без
    класса неотличим от мусора. Пустое имя ПОРТА при этом допустимо: адрес
    порта — индекс, а не имя.

    Параметров про `port`/`conn` с пустым именем объекта здесь **нет** и быть
    не должно: проверки для этих строк план добавляет в Task 5, и оставить их
    тут значило бы получить шаг 4 «Expected: PASS», недостижимый до Task 5.
    """
    with pytest.raises(TopologyError) as exc:
        parse_topology(text)
    assert fragment in str(exc.value)


def test_empty_port_name_is_allowed():
    """Обратная сторона того же правила: у порта имя может быть не задано."""
    topology = parse_topology("object\tA\tK\nport\tA\t0\tin\t\n")
    assert topology.ports[0].name == ""


@pytest.mark.parametrize("text, fragment", [
    # 9: дубликат имени объекта
    ("object\tA\tK\nobject\tA\tK2\n", "повторное имя объекта"),
    # 10: дубликат пары (объект, индекс)
    ("object\tA\tK\nport\tA\t0\tin\tx\nport\tA\t0\tout\ty\n",
     "повторная декларация порта"),
    # 11: conn на необъявленный порт — не объявлен ВТОРОЙ конец
    ("object\tA\tK\nobject\tB\tK\nport\tA\t0\tin\tx\nport\tB\t1\tout\ty\n"
     "conn\tA\t0\tB\t0\n", "необъявленный порт"),
    # 11: то же, но не объявлен ПЕРВЫЙ конец: сверка обязана смотреть оба
    ("object\tA\tK\nobject\tB\tK\nport\tA\t0\tin\tx\nport\tB\t0\tout\ty\n"
     "conn\tA\t9\tB\t0\n", "необъявленный порт"),
    # 8: port для необъявленного объекта
    ("object\tA\tK\nport\tB\t0\tin\tx\n", "необъявленный объект"),
    # 13: петля не обгоняет сверку ссылок. Порт A.9 не объявлен, и ответ обязан
    # быть про отсутствующее объявление, а не про петлю между несуществующими
    # портами: «петля — порт A.9 соединён сам с собой» — утверждение о связи,
    # которой в модели нет. Измерено мутацией: перенос проверки петли выше
    # сверки ссылок этот параметр краснит.
    ("object\tA\tK\nport\tA\t0\tin\tx\nconn\tA\t9\tA\t9\n",
     "необъявленный порт"),
    # 13: и не обгоняет полноту имён — пустое поле это сломанное поле, а не петля.
    ("object\tA\tK\nport\tA\t0\tin\tx\nconn\t\t0\t\t0\n", "пустое имя объекта"),
])
def test_reference_and_duplicate_rejections(text, fragment):
    """Ссылки и дубликаты — отказ.

    Два последних параметра закрепляют не только проверки, но и их **порядок**:
    петля стоит после полноты имён и после сверки ссылок. Поэтому на строке,
    сломанной раньше (необъявленный порт, пустое поле), оператор прочитает отказ
    про сломанное место, а не про петлю между портами, которых нет. Перенос
    проверки петли выше красит ровно эти два параметра — измерено мутацией.
    """
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

    Проверка **диагностическая, а не охранная**, и падение этого теста доказывает
    качество отказа, а не охранную силу. Приём и отказ от неё не зависят:
    `_parse_object` отвергает пустое имя, поэтому `""` не попадает ни в `names`,
    ни в `keys` — и проверки 8 и 11 отвергают пустое имя в ссылках всё равно.
    Измерено исчерпывающим дифференциальным прогоном: ноль различий по
    приёму/отказу, различия только в тексте сообщения. Ценность её в адресности:
    без неё оператор на пустое поле прочитает «порт ссылается на необъявленный
    объект ''» — утверждение об отсутствующем объявлении там, где сломано само
    поле.

    Порядок проверок в `_parse_connection` при этом обязателен: пустое имя
    объекта отвергается **до** сверки по `keys`, иначе второй параметр получит
    отказ «необъявленный порт .0» — верный по сути, но не тот, ради которого тест
    написан. Тест проверяет подстроку, а не смысл: с обратным порядком он
    покраснеет.
    """
    with pytest.raises(TopologyError) as exc:
        parse_topology(text)
    assert fragment in str(exc.value)


def test_self_loop_is_rejected():
    """13: связь порта с самим собой — отказ.

    Петля не описывает связь между двумя портами — конец у неё один, — и потому
    связью не является. Инвариант не опирается на то, сколько раз среда вернёт
    такую строку: поведение `traceallports` на самовключении — вопрос **живого**
    прогона (Task 9), и здесь он не предполагается.

    Входы заданы разными индексами (0, 3, 1) и разными именами объектов (A, B):
    на одном `conn A 0 A 0` выживает проверка, суженная до конкретного значения
    индекса (`… and connection.index_a == 0`) или до конкретного имени объекта.
    Сенсор закрепляет **равенство адресов** концов, а не совпадение с образцом.
    """
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


def test_probe_maps_only_documented_port_modes():
    """Таблица режимов явная: недокументированный режим не становится `undirected`.

    Справка знает ровно три значения (`getportinfo`: 0 — вход, 1 — выход,
    2 — ненаправленный; `setportmode` принимает те же три). Вендорский скрипт
    (`export_sheme_functions.inc:125-131`) пишет `undirected` на **всё** прочее —
    отображение `0/1/else`. Проба отступает от него намеренно: режим вне 0/1/2 —
    весть о дрейфе контракта, и превращать её в корректное на вид направление
    значит терять её молча. Поэтому ветвь `else` пишет сырое число, а разбор его
    отвергает (`test_direction_rejects_undocumented_port_mode`).

    Цена отступления измерена и равна нулю на штатных данных: 1337 портов 70
    демо-моделей дали только 0 (586), 1 (448) и 2 (303). Заодно режим 2
    перестаёт быть теоретической ветвью — его массовость и есть причина, по
    которой отображение `2 → undirected` теперь названо явно, а не спрятано в
    `else`.
    """
    body = build_topology_probe()
    assert 'if mode = 0 then modestr = "in"' in body
    assert 'else if mode = 1 then modestr = "out"' in body
    assert 'else if mode = 2 then modestr = "undirected"' in body
    assert 'else modestr = inttostr(mode);' in body


def test_probe_bounds_peer_by_owner_of_object_not_by_container():
    """Граница контейнера — по **владельцу объекта**, а не по текущему контейнеру.

    Проверка текстовая, и это вынужденно: различить две формы прогоном нечем.
    `getownercontainer` и `getcurrentcontainer` на всех доступных моделях дают
    согласованный ответ (демо вендора читается одинаково и в той, и в другой
    форме), а внешних связей, ради которых страж и стоит, на них нет вовсе. То
    есть живого воспроизведения нет ни у стража, ни — тем более — у разницы
    между формами; остаётся закрепить **решение**, чтобы оно не было отменено
    «упрощением» при следующей правке.

    Отменять его нельзя: вендор сравнивает владельцев двух объектов
    (`export_sheme_functions.inc:107`), и только эта форма верна на любой
    вложенности. Форма с текущим контейнером на верхнем уровне страницы может
    оказаться ложной — и тогда проба перестанет читать **обычные** модели там,
    где сейчас читает.
    """
    body = build_topology_probe()
    assert "objowner = getownercontainer(objid);" in body
    assert "if getownercontainer(peerid) = objowner then begin" in body
    phase3 = body.split("// фаза 3")[1]
    assert "= contid" not in phase3, (
        "граница контейнера сравнена с текущим контейнером: "
        "getownercontainer и getcurrentcontainer не обязаны совпадать")


#: Страж отбора по типу самого объекта — он открывает блок в каждой из трёх фаз.
#:
#: Ожидание **выводится из критерия** (`ELIGIBLE_OBJECT_TYPES`), а не пишется
#: литералом: иначе в тесте появилась бы вторая правда о наборе типов, и правка
#: критерия не покраснела бы. Теперь любое изменение критерия требует, чтобы тело
#: пробы изменилось вместе с ним, — это и есть мутационная проверка критерия.
def _expected_guard(variable: str) -> str:
    return "if " + " or ".join(f"({variable} = {t})" for t in ELIGIBLE_OBJECT_TYPES) \
        + " then begin"


OBJECT_TYPE_GUARD = _expected_guard("objtype")

#: Стражи второго конца связи. Оба только в фазе связей и оба обязательны:
#: `traceallports` отдаёт соседей независимо и от их типа, и от их контейнера.
#:
#: Страж контейнера закрывает дыру, которую тип не закрывает: сосед может
#: принадлежать **другому контейнеру** — тогда его имя не объявлено в фазе
#: объектов, и разбор отвергнет результат целиком по защите 11. Форма взята у
#: вендора дословно (`export_sheme_functions.inc:107`): сравниваются **владельцы**
#: двух объектов — соседа и текущего, — а не владелец соседа с
#: `getcurrentcontainer`. Разница не косметическая: на верхнем уровне
#: `getownercontainer` не обязан совпадать с `getcurrentcontainer`, и сравнение с
#: ним сломало бы чтение на самой обычной странице, тогда как вендорская форма
#: верна на любой вложенности.
PEER_GUARDS = (
    _expected_guard("peerobjtype"),
    "if getownercontainer(peerid) = objowner then begin",
)

#: Ожидаемые стражи **по номеру фазы**. Именно по номерам, а не «сколько
#: нашлось»: прежняя форма (`if guard in phase`) молчала об отсутствующем страже
#: — вырезанный из тела страж просто не попадал в список, и сенсор оставался
#: зелёным. Для фазы 3 с двумя стражами это не теория: удаление проверки
#: контейнера оставляло тип соседа на месте, `assert guards` был сыт, и мутант
#: выживал. Измерено на этой правке.
PHASE_GUARDS = {
    1: (OBJECT_TYPE_GUARD,),
    2: (OBJECT_TYPE_GUARD,),
    3: (OBJECT_TYPE_GUARD,) + PEER_GUARDS,
}


def _guarded(phase: str, guard_start: int, write_start: int) -> bool:
    """Открыт ли блок стража в момент записи.

    Идём по фазе токенами `begin`/`end`, держа стек открытых блоков: запись
    обязана прийтись на момент, когда блок, открытый стражем, **ещё не
    закрыт**. Одной балансировки `begin`/`end` тут мало и по числу вложенности
    не отличить: у мутанта «страж закрыт сразу после `getblockportcount`»
    глубина в момент записи совпадает с правильной — совпадает **число**
    блоков, а не то, какие именно они. Стек различает именно это.
    """
    guard_begin = phase.index("begin", guard_start)
    open_blocks = []
    for token in re.finditer(r"\bbegin\b|\bend\b|writelnutf8", phase):
        if token.start() == write_start:
            return guard_begin in open_blocks
        if token.group() == "begin":
            open_blocks.append(token.start())
        elif token.group() == "end":
            if not open_blocks:
                return False
            open_blocks.pop()
    return False


def test_probe_filters_objects_by_type_in_every_phase():
    """Отбор по типу — в каждой фазе, и запись фазы стоит **внутри** стража.

    Иначе объект, отброшенный в фазе объектов, всё равно попадёт в порты и
    связи — и разбор отвергнет весь результат по защитам 8 и 11.

    Одних счётчиков подстрок мало, и это измерено. Мутант, где условие написано
    во **всех трёх** фазах, но `begin…end` фаз 2 и 3 закрыт сразу после
    `portcnt = getblockportcount(objid);`, проходит оба прежних счётчика: они
    сыты, а запись выполняется для **каждого** объекта страницы. Живьём такой
    мутант фатален — 13 строк и отказ «порт ссылается на необъявленный объект
    'TextLabel7'», — то есть сенсор не держал инвариант, ради которого написан.
    Поэтому проверяется вложенность: запись обязана лежать внутри блока,
    открытого стражем, а не просто идти после него по тексту.

    И проверяется **наличие каждого** ожидаемого стража, а не «хотя бы одного».
    Разница измерена на этой же правке: пока список стражей фильтровался
    условием `if guard in phase`, вырезанный страж не попадал в проверку вовсе —
    фаза 3 отдавала тип соседа, `assert guards` был сыт, и мутант без проверки
    контейнера выживал.
    """
    body = build_topology_probe()
    phases = body.split("// фаза ")
    assert len(phases) == 4, "в теле не три фазы — разрез по маркерам не сработал"
    for number, phase in enumerate(phases[1:], start=1):
        writes = [m.start() for m in re.finditer("writelnutf8", phase)]
        assert len(writes) == 1, (
            f"в фазе {number} не одна запись, а {len(writes)}: сенсор не знает, "
            "какую из них проверять")
        expected = PHASE_GUARDS[number]
        missing = [guard for guard in expected if guard not in phase]
        assert missing == [], (
            f"в фазе {number} нет стражей {missing} — запись фазы не защищена "
            "стражем вовсе, и объект вне отбора попадёт в протокол")
        for guard in expected:
            guard_start = phase.index(guard)
            assert _guarded(phase, guard_start, writes[0]), (
                f"в фазе {number} запись стоит вне стража "
                f"{phase[guard_start:guard_start + 40]!r} — объект, отброшенный "
                "по типу, попадёт в протокол, и разбор отвергнет всё")


def test_probe_uses_only_confirmed_functions():
    """Все подтверждённые функции в теле названы."""
    body = build_topology_probe()
    for name in CONFIRMED_FUNCTIONS:
        assert name in body, f"в пробе нет {name}"


def _declared_variables(body: str) -> set:
    """Имена, объявленные в секции `var` тела.

    Разбор заодно проверяет, что секция разбираема, — иначе список переменных
    пришлось бы перечислять руками, и он разошёлся бы с телом.
    """
    block = body[body.index("var ") + 4:body.index(";", body.index("var "))]
    return {
        piece.split(":")[0].strip()
        for piece in block.split(",")
        if piece.strip()
    }


def test_probe_uses_only_confirmed_names():
    """В теле нет незнакомых имён — и это всё, что сенсор утверждает.

    «Знакомые» — подтверждённые функции, ключевые слова и типы языка,
    объявленные в `var` переменные и `fid` моста. Сенсор проверяет именно
    отсутствие **незнакомых** имён, а не то, что каждое имя где-то вызывается:
    объявленную переменную можно позвать как функцию, и этого он не заметит.
    Утверждение шире кода было бы хуже отсутствия утверждения.

    Проверка на **отсутствие**, а не на присутствие: предыдущий тест перечисляет
    имена и молчит о лишнем. Собираются **все** идентификаторы тела (без
    строковых литералов и комментариев), а не только вызовы со скобкой.

    Почему так строго — измерено. Прежний сенсор (регулярка `имя(`) переживали
    три обхода: чужая функция **без скобок**, чужая функция с именем **с
    заглавной буквы** и переименование `getcurrentcontainer` в
    `getcurrentcontainerx` (последнее — потому что тест «читается только текущий
    контейнер» подстрочный, а `getcurrentcontainer` входит в
    `getcurrentcontainerx` подстрокой). Латать регулярку бессмысленно: каждая
    следующая мутация нашла бы новую щель.
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


def test_read_topology_uses_the_bridge(tmp_path, monkeypatch):
    """Обёртка не дублирует транспорт: она зовёт ScriptBridge.run_probe.

    Сверяются **переданные значения**, а не их наличие. Сравнение вида
    `calls[0] == ("init", calls[0][1], 42)` тавтологично: клиент берётся из той
    же записи, которую сравнивают, поэтому подмена клиента на чужой проходила
    незамеченной, а `calls[1][0] == "run_probe"` проверяло только имя метода —
    и переставленные аргументы, пустое тело пробы, чужой путь тоже выживали.
    Здесь записаны ровно те значения, которые обёртка обязана донести: клиент
    и номер проекта до моста, тело пробы и путь вызывающего до `run_probe`.
    В этом вся её работа — сама она ничего не считает.

    Число вызовов сверяется отдельно: без этого проба уходила бы в мост
    **дважды**, и никто бы не заметил — оба вызова записывались бы в `calls`, а
    проверялись только первые два элемента.
    """
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

    assert len(calls) == 2
    assert calls[0] == ("init", client, 42)
    assert calls[1] == ("run_probe", build_topology_probe(), tmp_path / "t.txt")
    assert [row.name for row in topology.objects] == ["A", "B"]


def test_read_topology_does_not_swallow_bridge_errors(tmp_path, monkeypatch):
    """Отказ транспорта доходит до вызывающего, а не превращается в пустую модель.

    Обёртка существует ровно затем, чтобы при отказе было видно, что сломалось:
    транспорт или проба. Проглоченный отказ даёт `Topology` без объектов —
    неотличимую от честно пустого контейнера, и вызывающий не узнает, что мост
    не сработал. Запасной ветки здесь быть не должно: retry, fallback и «не
    страшно, вернём пустое» превращают отказ транспорта в правдоподобный ответ.

    Проверяются тип и текст отказа, а не тождество объекта: пересоздание
    исключения с тем же типом и текстом (`raise ScriptBridgeError(str(exc))
    from exc`) этот тест пропустит — измерено, и это законно, потому что
    вызывающий видит тот же отказ с той же цепочкой причин. Ловится именно
    вредное: проглатывание и подмена на пустую модель.
    """
    from simintech_api.core import topology as core_topology
    from simintech_api.exceptions import ScriptBridgeError

    class FailingBridge:
        def __init__(self, client, project_id):
            pass

        def run_probe(self, body, result_path):
            raise ScriptBridgeError("прежний скрипт не прочитан")

    monkeypatch.setattr(core_topology, "ScriptBridge", FailingBridge)
    with pytest.raises(ScriptBridgeError) as exc:
        core_topology.read_topology(object(), 42, tmp_path / "t.txt")
    assert "прежний скрипт не прочитан" in str(exc.value)


def test_eligible_types_are_the_measured_set():
    """Допустимые типы — измеренный набор, и он один на все места фильтра.

    Список закреплён **значением** сознательно: критерий этой версии измерен
    2026-09-23 переписью по классам, и расширять его следует новым замером, а не
    правкой по догадке. Тест краснеет при любом изменении константы — это и есть
    требуемая мутация критерия, а не проверка «список непустой».
    """
    assert ELIGIBLE_OBJECT_TYPES == (100, 102, 104, 106)


def test_guards_are_built_from_the_criterion_not_repeated():
    """Условие допустимости собирается из критерия и стоит во всех нужных местах.

    Три фазы плюс страж типа соседа — четыре места, и все четыре обязаны нести
    **ту же** формулировку, выведенную из критерия. Иначе появится скрытая копия
    набора, и новый тип придётся искать по телу пробы.
    """
    body = build_topology_probe()
    assert body.count(OBJECT_TYPE_GUARD) == 3, (
        "страж допустимого типа стоит не в каждой из трёх фаз: отбор разъедется, "
        "и объект из одной фазы попадёт в протокол, не будучи в другой")
    assert body.count(_expected_guard("peerobjtype")) == 1, (
        "страж типа соседа не один — значит где-то осталась своя формулировка")


def test_line_and_label_are_not_eligible():
    """101 и 108 вне критерия, и это не «список по случаю».

    Линия отсекается **данными**: у неё адресация не держится — измерено
    2026-09-23, `getportindex(getblockportid(wire, 1))` вернул 2, а не 1 (живое
    подтверждение — `test_line_fails_addressing_round_trip`). Подпись имеет ноль
    портов, то есть отсекается условием «не презентационная инфраструктура».
    """
    assert 101 not in ELIGIBLE_OBJECT_TYPES
    assert 108 not in ELIGIBLE_OBJECT_TYPES
