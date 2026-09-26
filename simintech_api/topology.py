"""Топология модели через встроенный язык: сборка тела пробы и разбор ответа.

Без COM и без файловой системы — всё, что здесь есть, проверяется в CI.
"""

from __future__ import annotations

from typing import Dict, List, NamedTuple, Set, Tuple

from .exceptions import TopologyError

#: Типы строк протокола. Первая строка задаёт фазу, отдельных маркеров нет.
OBJECT_ROW = "object"
PORT_ROW = "port"
CONN_ROW = "conn"

#: Разделитель полей — ровно один символ табуляции.
FIELD_SEPARATOR = "\t"

#: Направления порта. Режим берётся из `getportinfo`: 0 — вход, 1 — выход,
#: 2 — ненаправленный. Других значений справка не знает, и режим вне этих трёх
#: до сюда не доходит: проба пишет в поле направления сырое число, а разбор его
#: отвергает. Так отображение `0/1/else → undirected` (вендорское) не превращает
#: дрейф контракта в корректное на вид направление.
DIRECTIONS = ("in", "out", "undirected")


class ObjectRow(NamedTuple):
    """Объект страницы: имя и класс."""

    name: str
    class_name: str


class PortRow(NamedTuple):
    """Порт объекта. Адрес порта — пара (имя объекта, индекс), а не имя.

    Имя поля задано протоколом и не меняется: адрес порта — именно индекс, и
    так он называется во всех задачах и тестах. Оно затеняет унаследованный
    от `tuple` метод `tuple.index`, поэтому строка поля несёт единственное в
    пакете подавление. Оно узкое — по коду `[assignment]`, а не голое
    `type: ignore`, которое глушило бы и будущие настоящие ошибки на этой
    строке, — и безвредное в работе: метода `tuple.index` у этих строк никто
    не зовёт. Тег в строке короткий намеренно: текст после кода mypy
    принимает только как ещё один комментарий, иначе — «Invalid "type:
    ignore" comment».
    """

    object_name: str
    index: int  # type: ignore[assignment]  # затеняет tuple.index
    direction: str
    name: str


class Connection(NamedTuple):
    """Связь между портами двух объектов.

    Концы неориентированы: `object_a` — не «источник», а лишь тот конец, чей
    адрес оказался меньше по `connection_key`. Разбор кладёт связь в словарь по
    каноническому ключу и **сохраняет сам ключ**, поэтому запись детерминирована:
    для одного и того же графа `Topology.connections` одинаков независимо от
    порядка обхода портов, и равные связи равны как значения. Равенство при
    этом слабее ключа: `Connection("A", 0, "B", 1)` и `Connection("B", 1, "A", 0)`
    — одна связь, но разные значения, и сравнивать их надо через
    `connection_key`.
    """

    object_a: str
    index_a: int
    object_b: str
    index_b: int


class Topology(NamedTuple):
    """Снимок топологии одного контейнера.

    `connections` — **совместимое с вендором отношение связей**, а не обратимое
    описание проводки. Кратность соседей взята у вендорского экспортёра: на
    входной порт идёт один сосед, на остальные — все
    (`export_sheme_functions.inc:99`). Отсюда потеря формы линии, и она измерена:
    ветвление двумя `connect` и ветвление `branch_to` дают **одно и то же**
    множество связей при разной внутренней структуре — живой тест
    `test_branch_shapes_give_the_same_connections`. Для анализа структуры
    проводки нужен wire-level API; исследованные `getportwireid` и
    `tracestartportwires` дают для этого исходные данные, но достаточность их
    сочетания для восстановления проводки **не доказана**. Это поле отвечает на
    вопрос «что с чем соединено», а не «как это проложено».
    """

    objects: List[ObjectRow]
    ports: List[PortRow]
    connections: List[Connection]


def connection_key(connection: Connection) -> Tuple[Tuple[str, int], Tuple[str, int]]:
    """Канонический ключ связи: концы упорядочены по (имя объекта, индекс).

    Одна и та же пара портов может прийти двумя записями-зеркалами — как
    `(A, i, B, j)` и как `(B, j, A, i)`, — и ключ приводит их к одному виду:
    сравнивать надо ключи, а не «схлопнутые» списки. Это **дедупликация
    представления**, а не утверждение о симметрии `traceallports`. На парной
    линии он и правда даёт связь с обеих сторон (измерено), но после вендорского
    правила кратности входной порт берёт только первого соседа, а на развилке
    наблюдение связи с обоих концов никем не обещано — несимметричность измерена
    на T2.
    """
    first = (connection.object_a, connection.index_a)
    second = (connection.object_b, connection.index_b)
    return (first, second) if first <= second else (second, first)


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
            ports.append(_parse_port(fields, number, object_names, port_keys))
        else:
            connection = _parse_connection(fields, number, port_keys)
            key = connection_key(connection)
            connections[key] = Connection(key[0][0], key[0][1],
                                          key[1][0], key[1][1])

    return Topology(objects=objects, ports=ports,
                    connections=list(connections.values()))


def _parse_object(fields: List[str], number: int,
                  names: Set[str]) -> ObjectRow:
    if len(fields) != 3:
        raise TopologyError(
            f"строка {number}: у object должно быть 3 поля, получено {len(fields)}")
    if not fields[1]:
        raise TopologyError(f"строка {number}: пустое имя объекта")
    if not fields[2]:
        raise TopologyError(
            f"строка {number}: пустой класс объекта {fields[1]!r}")
    row = ObjectRow(name=fields[1], class_name=fields[2])
    if row.name in names:
        raise TopologyError(
            f"строка {number}: повторное имя объекта {row.name!r} — связи "
            "адресуются по имени, и дубликат делает адресацию неоднозначной")
    names.add(row.name)
    return row


def _parse_port(fields: List[str], number: int, names: Set[str],
                keys: Set[Tuple[str, int]]) -> PortRow:
    if len(fields) != 5:
        raise TopologyError(
            f"строка {number}: у port должно быть 5 полей, получено {len(fields)}")
    if not fields[1]:
        raise TopologyError(
            f"строка {number}: пустое имя объекта в строке порта")
    if fields[3] not in DIRECTIONS:
        raise TopologyError(
            f"строка {number}: неизвестное направление порта {fields[3]!r}, "
            f"допустимы {', '.join(DIRECTIONS)}")
    row = PortRow(object_name=fields[1], index=_parse_index(fields[2], number),
                  direction=fields[3], name=fields[4])
    # Дальше — не грамматика: сверка с накопленным состоянием.
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
    keys.add(key)
    return row


def _parse_connection(fields: List[str], number: int,
                      keys: Set[Tuple[str, int]]) -> Connection:
    if len(fields) != 5:
        raise TopologyError(
            f"строка {number}: у conn должно быть 5 полей, получено {len(fields)}")
    connection = Connection(
        object_a=fields[1], index_a=_parse_index(fields[2], number),
        object_b=fields[3], index_b=_parse_index(fields[4], number))
    # Дальше — три проверки вне грамматики строки: полнота имён концов, сверка
    # с накопленным состоянием (объявлен ли порт) и петля. Последняя локальна
    # для строки и накопленного состояния не требует, но стоит последней: на
    # строке, сломанной раньше, ответ обязан говорить о сломанном месте.
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
    if (connection.object_a, connection.index_a) == \
            (connection.object_b, connection.index_b):
        raise TopologyError(
            f"строка {number}: петля — порт {connection.object_a}."
            f"{connection.index_a} соединён сам с собой")
    return connection


def _parse_index(raw: str, number: int) -> int:
    try:
        value = int(raw)
    except ValueError:
        raise TopologyError(
            f"строка {number}: индекс порта {raw!r} не целое число") from None
    if value < 0:
        raise TopologyError(
            f"строка {number}: индекс порта не может быть отрицательным")
    return value


#: Типы объектов, допустимые для протокола топологии, — **единственный источник
#: этого решения**. Три места фильтрации в теле пробы (отбор объектов, отбор
#: портов, страж типа соседа) собираются из этой константы, поэтому новый тип
#: добавляется изменением одного места, а не поиском трёх скрытых копий условия.
#:
#: Критерий допустимости (решение 2026-09-23): объект допустим, если среда
#: однозначно адресует его, перечисляет его порты,
#: `getportindex(getblockportid(obj, i)) = i`, а `getportwireid` и `getportinfo`
#: к нему применимы, и он не является линией или презентационной
#: инфраструктурой. Вендорская выгрузка тут **не норматив, а oracle пересечения**:
#: она оптимизирована под собственный формат и допускает ссылку на необъявленный
#: объект (измерено: `ConnectedTo` на `TimeGraphic_0` при объявленном одном
#: `Step_source_1`), тогда как наш разбор такой ссылки не допускает.
#:
#: Измерено 2026-09-23 переписью по классам (тело снимает все четыре условия):
#: 100 (в том числе трёхпортовый «Сумматор»), 104 («В память») и 106 («Временной
#: график») — адресация держится у всех. 102 в списке по прежнему основанию:
#: субмодели демо (33 объекта) и сверка с эталоном, где они объявлены.
#:
#: Отсечение — **данными, а не списком**: у линии (101) адресация не держится,
#: `getportindex(getblockportid(wire, 1))` вернул 2, а не 1. Подпись (108) имеет
#: ноль портов и отсекается условием «не презентационная инфраструктура». Классы
#: 105, 109 и 113 не входят потому, что их **не удалось создать**
#: (`UnsupportedBlockError`, `BlockError`) — измерить не на чем.
#:
#: Граница критерия: комментарий имеет тип 100 (`RTFComment_0`, ноль портов),
#: поэтому от комментария критерий модельный объект **не отличает** — и он
#: объявляется, как и у вендора.
ELIGIBLE_OBJECT_TYPES = (100, 102, 104, 106)


def _type_guard(variable: str) -> str:
    """Условие допустимости типа для встроенного языка — из одного источника.

    Собирается из `ELIGIBLE_OBJECT_TYPES`, поэтому копий условия в теле пробы не
    бывает: изменился критерий — изменились все три места сразу.
    """
    return " or ".join(f"({variable} = {value})" for value in ELIGIBLE_OBJECT_TYPES)


def build_topology_probe() -> str:
    """Тело пробы топологии — три фазы: объекты, порты, связи.

    Тело идёт в `ScriptBridge.run_probe`, который обернёт его в `if firststep`
    и добавит маркеры результата. Объявления `var` собраны в одну секцию в
    начале тела.

    Строже про `var` сказать нельзя. Скрипт вендора объявляет переменные
    **после** исполняемых операторов (`fid = createfile(...)`, два
    `writelnutf8`), то есть объявление после операторов в этом диалекте
    законно. Но собранный скрипт содержит **две** секции `var`: свою пишет
    `build_probe_script`, — а что две секции в одном блоке законны, скрипт
    вендора не показывает. Это подтверждает первый живой прогон, и признак
    отказа у него свой: «в результате нет ровно одной пары маркеров».

    Фазы обязательны именно в таком порядке. Если писать `conn` сразу за
    портом, связь `A.0 → B.0` сошлётся на объект `B`, который объявится позже,
    — то есть проба породит ссылку вперёд, которую разбор обязан отвергать.

    Проба читает объекты, прошедшие **критерий допустимости**, — один именованный
    источник (`ELIGIBLE_OBJECT_TYPES` в этом модуле), из которого собираются все
    три места фильтрации. Критерий: объект адресуем, его порты перечислимы,
    `getportindex(getblockportid(obj, i)) = i`, `getportwireid` и `getportinfo`
    применимы, и он не линия и не презентационная инфраструктура. Прежде
    источником назывался вендорский скрипт (строка 44-50); теперь вендорская
    выгрузка — **oracle пересечения, а не норматив**: она допускает ссылку на
    необъявленный объект (измерено: `ConnectedTo` на `TimeGraphic_0` при одном
    объявленном `Step_source_1`), а наш разбор — нет, и у нас второй конец
    объявляется.

    Измерено 2026-09-23 переписью по классам: проходят 100 (в том числе
    трёхпортовый «Сумматор»), 104 («В память») и 106 («Временной график»); 102
    объявлен по прежнему основанию — субмодели демо и сверка с эталоном.
    Отсекается это **данными, а не списком**: у линии адресация не держится —
    `getportindex(getblockportid(wire, 1))` вернул 2, а не 1; подпись имеет ноль
    портов. Классы 105, 109 и 113 в набор не входят потому, что их нельзя
    создать, то есть измерить не на чем. Тип 100 есть и у подписи-комментария
    (`RTFComment6` класса «Комментарий» входит в эталонные 35 объектов), поэтому
    «объект модели» тут означало бы больше, чем делает код. Без отбора в
    объекты попадают линии связи, подписи, текст и графика, а линия становится
    ещё и **концом связи**: у неё есть свои порты, и связи к ней дают лишние
    рёбра. Перемерено 2026-09-23 текущей редакцией: проект из двух блоков и одной
    линии даёт без отбора 4 объекта, 5 портов и **3 связи** вместо 2 объектов и
    **1 связи** с отбором, и обе лишние ведут к объекту линии (`MBTYWire`); на
    контейнере демо — 68 объектов и 96 связей против 35 и 32. Проверка стоит в
    **каждой** из трёх фаз: отфильтруй только первую — порты и связи сошлются на
    объекты, которых нет в списке, и разбор отвергнет **весь** результат по
    защитам 8 и 11.

    Фильтр распространён и на **второй конец связи**. `traceallports` отдаёт
    соседей независимо от их типа, поэтому сосед, отброшенный в фазе объектов,
    всё равно попал бы в строку `conn` — и разбор отверг бы **весь** результат
    по защите 11, не сообщив вызывающему ничего: линия или подпись рядом со схемой
    делали модель нечитаемой целиком. Вендор делает то же самое
    (`export_sheme_functions.inc:107` отсекает соседей из чужого контейнера).
    Цена — связь на отфильтрованный объект (линию, подпись, блок неизмеренного
    типа) **тихо теряется**, и это осознанный выбор: молча потерять одно ребро
    лучше, чем не прочитать модель вообще.

    Второй страж соседа — **граница контейнера**, и он закрывает ту же дыру с
    другой стороны: сосед может принадлежать другому контейнеру, и тогда его имя
    не объявлено в фазе объектов, а связь на него отвергла бы результат целиком.
    Форма взята у вендора дословно (`:107`): сравниваются **владельцы** двух
    объектов — соседа и текущего, — а не владелец соседа с `getcurrentcontainer`.
    Разница не косметическая: на верхнем уровне `getownercontainer` не обязан
    совпадать с `getcurrentcontainer`, и сравнение с ним сломало бы чтение на
    самой обычной странице, тогда как вендорская форма верна на любой
    вложенности. Живого воспроизведения у этого стража нет и быть не может на
    доступных моделях: на демо вендора внешних связей не нашлось — проба читает
    его и **до** правки, возвращая те же 35 объектов и 32 связи. Основание здесь
    не измерение, а вендорский код и его комментарий «используем объекты только
    текущего уровня» (`:106`): вендор утверждает, что соседи чужих уровней в
    следе бывают.

    `getportinfo` отображён в направление **строже вендора**. Вендор пишет
    `undirected` на всё, что не 0 и не 1 (`:125-131`), проба знает три значения
    из справки (0 — вход, 1 — выход, 2 — ненаправленный) и пишет сырое число,
    если пришло что-то ещё: разбор такой токен отвергает, и вызывающий видит
    дрейф контракта, а не корректное на вид направление. На штатных данных
    отступление бесплатно: 1337 портов 70 демо-моделей дали ровно 0 (586),
    1 (448) и 2 (303). Заодно это делает ветвь `undirected` не теоретической:
    режим 2 — самый частый на страницах со вспомогательными объектами, и живой
    тест доводит его до разбора через `setportmode`.

    **Кратность соседей берётся у вендора, а не по-своему.** На входной порт
    вендор пишет не больше одного соседа
    (`if aportmode = 0 then count_of_conn = min(1, cols(conn_port_list))`, `:99`),
    на остальные порты — всех; проба повторяет это правило. Прежняя редакция
    брала всех у любого порта и называла это осознанным расхождением. Снято
    2026-09-23: расхождение оказалось не выбором формы, а **другим множеством
    связей**, и вот его измеренная цена.

    Обе редакции запускались телом пробы на четырёх схемах: демо вендора, T1
    (одна линия), T2 (ветвление двумя `connect`), T3 (ветвление `branch_to`).
    На демо они **неразличимы** — 64 сырые строки и 32 связи на выходе у обеих,
    и T1 тоже: 2 строки и 1 связь. Причина в том, что у всех 32 линий демо ровно
    два конца (измерено: портов 64, линий 32, у каждой по два порта), и обрезка
    до первого соседа там ничего не меняет. Поэтому прежняя редакция проходила
    сверку с эталоном, а расхождение на демо не было видно **в принципе**.
    Различает развилку только T3: `traceallports` отдаёт **всю компоненту**, и
    прежняя редакция на ней давала 6 сырых строк и 3 связи против 4 строк и
    2 связей у вендора; T2 — 4 строки и 3 связи против 3 и 2.

    Различие это не количественное, а по существу: ребро между двумя **входами**
    одной линии (брат по разветвлению) прежняя редакция писала, а в выгрузке
    вендора его нет. У вендора развилка выглядит **звездой** от выхода, у прежней
    редакции — треугольником из `C(k,2)` пар. Обратная сторона: эталонная
    выгрузка — **не полный оракул по форме линии** (см. `Topology.connections`):
    совпадение с ней по связям не означает совпадения по проводке.

    `findstartport` в фазе связей **не используется, и это решение с записью.**
    Он был введён в этой ветке как оракул ребра и потерял 31 связь эталона.
    Причина измерена: функция вернула порт **другого контейнера** — на демо она
    даёт `k6.0` для `acrms_Q_P3.0`, тогда как `traceallports` для того же порта
    даёт ровно эталонного соседа `Key_manual_button_1.0`, а объекта `k6` в
    контейнере нет ни среди 35 объектов эталона, ни в одном списке соседей.
    Это сигнальный резолвер, а не оракул электрической смежности, и вендорский
    экспортёр не зовёт его ни разу. Тот же замер снял и прежнее предположение о
    «фантомных рёбрах» **на разветвлении**: ребро вход–вход появляется не из
    среды, а из редакции без правила кратности. Это не тот случай, что лишние
    рёбра к **объекту линии** выше: те снимает отбор по типам, а это — правило
    кратности.

    Отбор пока не охватывает типы 105 «Из памяти», 109 «Блок со встроенным
    интерпретатором» и 113 «Блок-узел»: блоки этих классов **не удалось создать**
    (`UnsupportedBlockError`, `BlockError`), поэтому их допустимость живым
    прогоном не измерена. Это отдельное основание, отличное от измеренного отказа
    адресации у линии: там объект отсекается **данными**, здесь — недоступностью
    моделей. Расширять набор — отдельная работа с отдельным замером, а не правка
    константы.

    Фильтр `getportwireid(portid) <> 0` в фазе связей повторяет вендорский:
    вендор зовёт `traceallports` только для портов с проводом. Потерь нет — у
    порта без провода связей и не бывает. Выигрыш прямой: вендор этот случай не
    измерял, и если среда вернёт на порту без провода в следе **сам порт**,
    проба напишет `conn A i A i`, а защита 13 отвергнет **всю** модель, с
    признаком, неотличимым от остальных причин неподвижного модельного времени
    (см. `ScriptBridge._start_and_wait`).
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
        "      objowner: integer,\n"
        "      alinetype: integer,\n"
        "      portname: string,\n"
        "      modestr: string,\n"
        "      peers: intarray,\n"
        "      count_of_conn: integer,\n"
        "      peer_idx: integer,\n"
        "      peerid: integer,\n"
        "      peername: string,\n"
        "      peerobjtype: integer,\n"
        "      peer_index: integer,\n"
        "      TAB: string;\n"
        '  TAB = chr(9);\n'
        "  contid = getcurrentcontainer;\n"
        "  objcnt = getobjcount(contid);\n"
        "\n"
        "  // фаза 1: объекты, прошедшие критерий допустимости\n"
        "  for(obj_idx=1, objcnt) begin\n"
        "    objid = getobj(contid, obj_idx);\n"
        "    objtype = getobjtypeid(objid);\n"
        f"    if {_type_guard('objtype')} then begin\n"
        '      writelnutf8(fid, "object" + TAB + getobjname(objid)\n'
        '                       + TAB + getobjclassname(objid));\n'
        "    end;\n"
        "  end;\n"
        "\n"
        "  // фаза 2: все порты\n"
        "  for(obj_idx=1, objcnt) begin\n"
        "    objid = getobj(contid, obj_idx);\n"
        "    objtype = getobjtypeid(objid);\n"
        f"    if {_type_guard('objtype')} then begin\n"
        "      portcnt = getblockportcount(objid);\n"
        "      for(port_idx=0, portcnt-1) begin\n"
        "        portid = getblockportid(objid, port_idx);\n"
        "        mode = getportinfo(portid, portname, alinetype);\n"
        '        if mode = 0 then modestr = "in"\n'
        '        else if mode = 1 then modestr = "out"\n'
        '        else if mode = 2 then modestr = "undirected"\n'
        "        else modestr = inttostr(mode);\n"
        '        writelnutf8(fid, "port" + TAB + getobjname(objid) + TAB\n'
        "                         + inttostr(port_idx) + TAB + modestr + TAB "
        "+ portname);\n"
        "      end;\n"
        "    end;\n"
        "  end;\n"
        "\n"
        "  // фаза 3: связи — соседи порта с вендорским правилом кратности\n"
        "  for(obj_idx=1, objcnt) begin\n"
        "    objid = getobj(contid, obj_idx);\n"
        "    objtype = getobjtypeid(objid);\n"
        f"    if {_type_guard('objtype')} then begin\n"
        "      // владелец текущего объекта — граница контейнера, как у вендора\n"
        "      objowner = getownercontainer(objid);\n"
        "      portcnt = getblockportcount(objid);\n"
        "      for(port_idx=0, portcnt-1) begin\n"
        "        portid = getblockportid(objid, port_idx);\n"
        "        // вендор зовёт traceallports только для портов с проводом\n"
        "        if getportwireid(portid) <> 0 then begin\n"
        "          mode = getportinfo(portid, portname, alinetype);\n"
        "          peers = traceallports(portid, 0);\n"
        "          // правило кратности вендора (export_sheme_functions.inc:99):\n"
        "          // на вход — только первый сосед, на остальные порты — все\n"
        "          count_of_conn = cols(peers);\n"
        "          if mode = 0 then count_of_conn = min(1, cols(peers));\n"
        "          for(peer_idx=1, count_of_conn) begin\n"
        "            peerid = getportblockid(peers[peer_idx]);\n"
        "            peername = getobjname(peerid);\n"
        "            peerobjtype = getobjtypeid(peerid);\n"
        "            // сосед из чужого контейнера в фазе объектов не объявлен\n"
        "            if getownercontainer(peerid) = objowner then begin\n"
        f"              if {_type_guard('peerobjtype')} then begin\n"
        "                peer_index = getportindex(peers[peer_idx]);\n"
        '                writelnutf8(fid, "conn" + TAB + getobjname(objid) + TAB\n'
        "                                 + inttostr(port_idx) + TAB + peername + TAB\n"
        "                                 + inttostr(peer_index));\n"
        "              end;\n"
        "            end;\n"
        "          end;\n"
        "        end;\n"
        "      end;\n"
        "    end;\n"
        "  end;\n"
    )
