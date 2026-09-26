"""Живой прогон топологической пробы: SimInTech, реальный COM."""

import os
import shutil
import sys

import pytest

from simintech_api.catalog import decode_xprt
from simintech_api.core.project import Project
from simintech_api.core.script_bridge import ScriptBridge
from simintech_api.core.topology import read_topology
from simintech_api.script_probe import parse_xprt_script_records
from simintech_api.topology import (
    CONN_ROW,
    build_topology_probe,
    connection_key,
    parse_topology,
)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from vendor_reference import load_reference  # noqa: E402

pytestmark = pytest.mark.integration

#: Демо вендора с заведомо известной топологией. Эталон — выгрузка его скрипта
#: (`fixtures/vendor_topology_reference.json`). Числа эталона — 35 объектов,
#: 64 записи о портах с проводом (32 входа и 32 выхода), 64 записи
#: `ConnectedTo` = **32 уникальные связи**, самоссылок ноль — закреплены
#: юнит-тестом `tests/unit/test_vendor_reference.py`; здесь они только справка.
#:
#: Числа нельзя путать: 64 — это количество записей в выгрузке вендора (связь
#: записана с обеих сторон, и только для портов с проводом), а проба печатает
#: **все** порты и схлопывает связь каноническим ключом. Ожидаемый результат
#: пробы: 35 объектов, ≥64 порта, **32 связи**.
#:
#: Совпадение «64 порта» — не тождество величин, а совпадение на этом демо: у
#: всех отобранных блоков здесь провод есть. На модели из двух блоков у `kx_0`
#: порт 0 без провода, и проба вернула 3 порта при 1 связи. Поэтому живая
#: сверка требует от портов `>=`, а не `==`.
VENDOR_DEMO = (r"C:\SimInTech64\Demo\Приёмы работы\Анализ и отчеты"
               r"\Анализ топологии скриптами и экспорт в json"
               r"\Экспорт топологии и свойств в json"
               r"\Экспорт топологии и свойств в json.prt")

#: Имя блока-контейнера на главной странице демо. Эталон снят **внутри** него
#: (имя файла эталона — `…json.acrms_Circuit1.json`), а проба читает текущий
#: контейнер: чтобы сверить с ним результат, надо войти в этот блок.
#:
#: Вопрос «какой контейнер читает проба» был первым вопросом прогона и держал
#: печатающий тест `test_current_container_identity` — без единого `assert`, то
#: есть отвечавший «зелено» на любой исход. Discovery состоялся, и тест удалён
#: как одноразовый: ответ закреплён дважды и с двух сторон. Проба читает
#: **тот** контейнер, который текущий по мнению COM, — это доказывают
#: `test_objects_match_com` (свой проект, каждый объект пробы разрешается COM по
#: имени) и `test_probe_matches_vendor_reference_inside_container` (после
#: активации страницы субмодели проба отдаёт **внутренние** 35 объектов, а не
#: объекты главной). Прогон на самом демо сверху, без входа в блок, остался —
#: в `test_probe_works_on_vendor_demo`.
VENDOR_CONTAINER = "acrms_Circuit1"

#: Классы дополнительных типов, которые критерий допустимости **пропускает**:
#: 104 «В память» и 106 «Временной график». Допустимость измерена 2026-09-23
#: (адресация, перечислимость портов, применимость `getportwireid` и
#: `getportinfo`), и на них проверяется, что объект объявляется, а связь к нему
#: доходит до разбора, — прежде эти классы отсеивались.
ELIGIBLE_EXTRA_CLASSES = ("В память", "Временной график")

#: Демо, на котором у отобранных объектов есть порты **режима 2** — то есть
#: `undirected` получается сам, без правки модели. Найдено замером по выборке
#: (70 моделей: 0 — 586 портов, 1 — 448, 2 — 303); подходящих моделей пять, взята
#: самая маленькая — 4 объекта и 9 портов, из них 4 ненаправленных.
#:
#: Путь приходится пинить так же, как у демо эталона: ненаправленные порты есть не
#: везде, а сделать их нарочно нельзя — `setportmode(portid, 2)` на порту блока
#: останавливает расчёт (измерено контрольным опытом, см.
#: `test_probe_directions_match_com_port_modes`).
VENDOR_UNDIRECTED_DEMO = (
    r"C:\SimInTech64\Demo\Электрика\ЭЦ-Oбщие элементы"
    r"\Тесты блоков\Тесты базовых объектов"
    r"\Тест простая проводимость\Тест простой проводимости.prt")

#: Режим порта из COM (`GetPortInfo().Mode`) → направление протокола. Таблица
#: написана здесь **заново**, а не взята из пробы: сверка с COM обязана быть
#: независимой, иначе обе её стороны сломались бы одинаково.
MODE_TO_DIRECTION = {0: "in", 1: "out", 2: "undirected"}


@pytest.fixture(scope="module")
def reference():
    """Разобранный эталон вендора — тем же разбором, что и в юнит-тесте.

    Эталон перестал быть картинкой: сверка идёт по именам, направлениям и
    ключам связей из него, а не по числам, вбитым константой. Разбор один на
    оба уровня (`tests/vendor_reference.py`) — иначе живой тест проверял бы не
    то, что закреплено юнит-тестом, и разъехались бы они молча.
    """
    return load_reference()


@pytest.fixture()
def wired_project(client):
    """Проект из двух блоков и **одной** линии — тот же, что дал находку Task 9.

    Именно на нём измерено, что без фильтра по типу проба видит 4 объекта и 3
    связи: линия попадает и в объекты, и в связи, а обе лишние связи ведут к
    самому объекту линии (`MBTYWire`). Перемерено 2026-09-23.
    """
    project = Project.from_template(client)
    project.set_calc_end_time(1.0)
    page = project.get_main_page()
    source = page.create_block("Ступенька", 0, 0)
    gain = page.create_block("Усилитель", 200, 0)
    source.connect(gain)
    try:
        yield project
    finally:
        project.close()


def test_probe_works_on_vendor_demo(client, tmp_path):
    """Первый вопрос: работает ли проба и что даёт `getportinfo`/`traceallports`.

    Это может опровергнуть всю затею, поэтому идёт первым. Здесь только
    минимум, без которого остальное бессмысленно: проба отработала, объекты
    есть, направления портов попадают в три известные значения.

    **Проверка направлений здесь слабая, и это сказано прямо.** На главной
    странице демо у единственного объекта портов нет, множество пусто, и
    утверждение истинно при любом коде. Направления проверяются там, где порты
    есть: `test_probe_reports_port_directions` (измеренный набор на своём
    проекте), `test_probe_matches_vendor_reference_inside_container` (сверка с
    эталоном внутри контейнера) и `test_probe_directions_match_com_port_modes`
    (сверка с режимами из COM).

    Оговорка про «вакуумно» стояла здесь по делу и **перестала быть верной после
    правки отображения режимов**: пока на всё, кроме 0 и 1, писалось `undirected`,
    множество из трёх значений не могло не сойтись. Теперь режим вне 0/1/2 идёт в
    протокол **сырым числом**, и это утверждение его ловит — то есть перестало
    быть истинным при любом коде.

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


def test_probe_reports_only_model_objects(client, tmp_path, wired_project):
    """Проверка А: фильтр по типу убирает из пробы линию и подпись.

    До правки проба на этой самой модели возвращала **4 объекта и 3 связи**:
    линия — объект страницы, у неё есть свои порты, и фаза связей трассировала
    её, добавляя к единственной настоящей связи два лишних ребра — к самому
    объекту линии. Здесь
    закреплено измерение «до/после», причём каждое число — против независимого
    источника: линии и объекты страницы считает COM.

    Ожидается ровно два моделирующих объекта (`Step_source_1`, `kx_0`) и одна
    связь. Число объектов по COM обязано быть **больше**: на странице лежат ещё
    линия и подпись, и если проба вернула столько же, сколько COM, — фильтр не
    сработал.
    """
    wires = wired_project.get_main_page().get_wires()
    by_com = client.call("GetPageObjectCount", wired_project.id)
    topology = read_topology(client, wired_project.id, tmp_path / "t.txt")
    names = {row.name for row in topology.objects}
    print(f"\nCOM видит на странице {by_com} объектов, из них линий {len(wires)}; "
          f"проба вернула объектов {len(topology.objects)} {sorted(names)}, "
          f"связей {len(topology.connections)}")

    assert len(wires) == 1, "линия не создалась — проверять фильтр не на чем"
    assert names == {"Step_source_1", "kx_0"}, (
        f"в объекты пробы попало не моделирующее: {sorted(names)}")
    assert len(topology.objects) < by_com, (
        "проба вернула столько же объектов, сколько COM видит на странице, — "
        "значит, линия и подпись не отфильтрованы")
    assert len(topology.connections) == 1, (
        "линия добавила лишние рёбра — к самому объекту линии: связей должно "
        "быть ровно столько, сколько линий между блоками")


def test_probe_reports_port_directions(client, tmp_path, wired_project):
    """`getportinfo` → `in`/`out` закреплено на живом прогоне, а не на пустом множестве.

    Проверка нужна потому, что прежняя — на главной странице демо — вакуумна: у
    единственного объекта там портов нет, и «направление лежит среди трёх
    известных значений» истинно при любом коде. Здесь порты есть, и их
    направления измерены: у «Ступеньки» один выход, у «Усилителя» выход и вход,
    всего три порта. Адрес порта — пара (имя объекта, индекс), и сверяется
    именно она: имена автоматические (`Step_source_1`, `kx_0`), их даёт
    `list_blocks`-эквивалент COM.

    **Чего эта проверка по-прежнему не закрывает.** Здесь у портов режимы 0 и 1,
    и ветвь `undirected` не исполняется: её доводит до разбора отдельный тест
    `test_probe_directions_match_com_port_modes` на демо, где такие порты есть.
    """
    topology = read_topology(client, wired_project.id, tmp_path / "t.txt")
    directions = {(port.object_name, port.index): port.direction
                  for port in topology.ports}
    print(f"\nпорты модели с направлениями: {sorted(directions.items())}")
    assert directions == {
        ("Step_source_1", 0): "out",
        ("kx_0", 0): "out",
        ("kx_0", 1): "in",
    }


def test_probe_directions_match_com_port_modes(client, tmp_path):
    """Направление **каждого** порта сверяется с режимом из COM — на живой модели.

    До этой проверки отображение режима в направление держалось только
    юнит-сенсором таблицы в теле пробы, а `undirected` не встречался ни на одном
    прогоне: он оставался единственной ветвью пробы без живого покрытия.

    **Почему не `setportmode`.** Первая редакция ставила режим 2 нарочно — и
    упала. Измерено контрольным опытом на двух одинаковых проектах
    (`from_template` + «Ступенька» → «Усилитель»): перестановка режима **на то же
    значение** (`set_mode(1)`) расчёт не трогает, проба проходит; а `set_mode(2)`
    на выходном порту усилителя **останавливает расчёт**, и мост отказывает про
    нерастущее модельное время. То есть режим порта — часть интерфейса блока:
    сделав выход ненаправленным, модель перестаёт компилироваться. Поэтому
    `undirected` берётся оттуда, где он есть **сам по себе**, — с демо поставки,
    найденного замером по выборке (из 70 моделей такие порты нашлись в пяти).

    **Что здесь независимый источник.** COM: `GetBlockPort` + `GetPortInfo().Mode`
    для того же адреса. Таблица `MODE_TO_DIRECTION` написана здесь заново, а не
    взята из пробы, — иначе обе стороны сверки сломались бы одинаково. Заодно
    проверяется и тождество, которое до сих пор ничем не закреплено: адрес порта
    у пробы — счётчик цикла, а порт у COM берётся по `GetBlockPort`, и разойдись
    эти два индекса, сверка покраснеет на каждом порту модели.

    **Вырождение проверяется явно.** Модель-демо может измениться; если в пробе
    не останется ни одного ненаправленного порта, тест обязан упасть — иначе он
    продолжит зеленеть, проверяя ветвь, которой больше нет.
    """
    if not os.path.exists(VENDOR_UNDIRECTED_DEMO):
        pytest.skip(f"нет демо вендора: {VENDOR_UNDIRECTED_DEMO}")
    work = tmp_path / "undirected.prt"
    shutil.copy2(VENDOR_UNDIRECTED_DEMO, work)
    project = Project.open(client, str(work))
    try:
        topology = read_topology(client, project.id, tmp_path / "t.txt")
        page = project.get_main_page()
        undirected = [(port.object_name, port.index) for port in topology.ports
                      if port.direction == "undirected"]
        assert undirected, (
            "на демо не осталось ненаправленных портов: ветвь `undirected` "
            "больше не проверяется, и тест обязан падать, а не зеленеть")

        wrong = []
        out_of_contract = []
        for port in topology.ports:
            block = page.find_block(port.object_name)
            assert block is not None, (
                f"COM не находит объект {port.object_name!r} из пробы")
            mode = int(block.get_block_port(port.index).get_info().mode)
            if mode not in MODE_TO_DIRECTION:
                out_of_contract.append((port.object_name, port.index, mode))
            elif MODE_TO_DIRECTION[mode] != port.direction:
                wrong.append((port.object_name, port.index, mode,
                              port.direction))

        print(f"\nдемо с ненаправленными портами: объектов {len(topology.objects)},"
              f" портов {len(topology.ports)}, ненаправленных {len(undirected)}"
              f" {undirected[:6]}")
        assert out_of_contract == [], (
            "COM вернул режимы вне справки (0 — вход, 1 — выход, "
            f"2 — ненаправленный): {out_of_contract}")
        assert wrong == [], (
            "направление разошлось с режимом COM "
            f"(объект, индекс, режим, направление пробы): {wrong}")
    finally:
        project.close()


@pytest.mark.parametrize("class_name", ELIGIBLE_EXTRA_CLASSES)
def test_probe_declares_eligible_neighbour_of_new_type(client, tmp_path,
                                                       class_name):
    """Схема с блоком дополнительного типа читается, и связь к нему **сохраняется**.

    Прежде этот тест утверждал обратное — что блок такого класса отсеивается, а
    связь к нему теряется молча. Так и было, пока отбор шёл по вендорскому
    признаку `{100, 102}`. Критерий допустимости (см. `ELIGIBLE_OBJECT_TYPES`)
    эти классы пропускает, поэтому контракт изменился, и тест переписан вместе с
    ним: объект **объявляется**, а связь доходит до разбора.

    Проверяется три вещи сразу: модель читается, объект дополнительного типа есть
    в `objects`, и обе связи (между прежними типами и к новому объекту) есть в
    `connections`. По COM линий две — связь физически существует, и топология
    обязана её показать.
    """
    project = Project.from_template(client)
    project.set_calc_end_time(1.0)
    page = project.get_main_page()
    source = page.create_block("Ступенька", 0, 0)
    gain = page.create_block("Усилитель", 200, 0)
    extra = page.create_block(class_name, 400, 0)
    source.connect(gain)
    gain.connect(extra)
    try:
        wires = page.get_wires()
        topology = read_topology(client, project.id, tmp_path / "t.txt")
        names = {row.name for row in topology.objects}
        classes = {row.class_name for row in topology.objects}
        print(f"\n{class_name}: по COM линий {len(wires)}, проба вернула "
              f"объектов {len(topology.objects)} {sorted(names)}, связей "
              f"{len(topology.connections)}")
        assert len(wires) == 2, "схема собралась не так: проверять нечего"
        assert any(row.class_name == class_name for row in topology.objects), (
            f"объект класса {class_name!r} не объявлен, хотя критерий его "
            f"пропускает: {sorted(classes)}")
        assert len(topology.connections) == 2, (
            "обе связи обязаны дойти до разбора: и между прежними типами, и к "
            "объекту дополнительного типа")
        touched = ({connection.object_a for connection in topology.connections}
                   | {connection.object_b for connection in topology.connections})
        assert not (names - touched), (
            f"объекты без единой связи: {sorted(names - touched)}")
    finally:
        project.close()


def test_probe_matches_vendor_reference_inside_container(client, tmp_path,
                                                         reference):
    """Проверка Б: критерий приёмки 1 — проба внутри контейнера равна эталону.

    Сверяется **разобранный эталон**, а не число с числом: множество имён
    объектов, направление каждого эталонного порта и множество канонических
    ключей связей. Раньше здесь стояли три константы (35, 64, 32), а сам файл
    эталона не читал ни один тест — разойтись они могли молча, и сверка
    вырождалась бы в сравнение числа с числом. Эталонные числа закреплены
    теперь юнит-тестом `tests/unit/test_vendor_reference.py` и читаются тем же
    разбором (`tests/vendor_reference.py`), что и здесь.

    Портов требуется **не меньше** эталонных, а не столько же. Вендор выгружает
    только порты с проводом, проба печатает все: на этом демо числа совпали, но
    на модели из двух блоков у `kx_0` порт 0 без провода — проба вернула 3 порта
    при 1 связи. Равенство держалось бы на совпадении и падало бы, стоит в копии
    демо появиться неподключённому блоку, — обвиняя пробу в неисправности,
    которой нет.

    Классы объектов **печатаются**, а не сверяются: `class_name` от языка и
    класс от COM могут законно расходиться (блок-плагин).

    Эталон снят вендорским скриптом **на внутренней странице** `acrms_Circuit1`,
    а проба читает текущий контейнер. Поэтому сначала страница делается текущей
    (`submodel_page` + `activate`), и только потом читается топология.

    **Только на копии.** Проба ставит в проект скрипт и считает модель, то есть
    пишет в файл проекта; копия — способ не трогать поставку вендора. Что
    прежний скрипт этой страницы при этом **возвращается на место**, проверяет
    `test_reading_topology_inside_container_keeps_its_script`: до правки моста
    проба стирала вендорский скрипт внутренней страницы (939 символов), а
    «проверка возврата» сравнивала главную страницу саму с собой.
    """
    if not os.path.exists(VENDOR_DEMO):
        pytest.skip(f"нет демо вендора: {VENDOR_DEMO}")
    work = tmp_path / "demo.prt"
    shutil.copy2(VENDOR_DEMO, work)
    project = Project.open(client, str(work))
    try:
        container = project.get_main_page().find_block(VENDOR_CONTAINER)
        assert container is not None, (
            f"на главной странице демо нет блока {VENDOR_CONTAINER!r}")
        project.submodel_page(container.id).activate()
        topology = read_topology(client, project.id, tmp_path / "t.txt")

        probe_names = {row.name for row in topology.objects}
        probe_classes = {row.name: row.class_name for row in topology.objects}
        probe_directions = {(port.object_name, port.index): port.direction
                            for port in topology.ports}
        probe_port_names = {(port.object_name, port.index): port.name
                            for port in topology.ports}
        probe_keys = {connection_key(link) for link in topology.connections}
        reference_classes = {row.name: row.class_name for row in reference.objects}
        reference_names = set(reference_classes)
        reference_directions = reference.port_directions()
        reference_port_names = {(port.object_name, port.index): port.name
                                for port in reference.ports}
        reference_keys = reference.connection_keys()
        # Страховка от вырождения сверки: на пустом эталоне все сравнения ниже
        # истинны при любом коде. Непустота эталона закреплена ещё и
        # юнит-тестом (`test_vendor_reference.py`), но живой тест обязан
        # падать сам, если сверять станет не с чем.
        assert reference_directions and reference_keys, (
            "эталон разобран пустым — сверять не с чем, и все проверки ниже "
            "были бы вакуумными")

        print(f"\nвнутри {VENDOR_CONTAINER}: объектов {len(topology.objects)}, "
              f"портов {len(topology.ports)}, связей {len(topology.connections)} "
              f"(эталон вендора: {len(reference.objects)}, "
              f"{len(reference.ports)}, {len(reference_keys)})")
        mismatched_classes = sorted(
            (name, reference_classes[name], class_name)
            for name, class_name in probe_classes.items()
            if reference_classes.get(name) not in (None, class_name))
        if mismatched_classes:
            print(f"классы разошлись у {len(mismatched_classes)} объектов "
                  f"(имя, эталон, проба): {mismatched_classes[:10]}")

        assert probe_names == reference_names, (
            f"имена разошлись: лишние {sorted(probe_names - reference_names)}, "
            f"пропавшие {sorted(reference_names - probe_names)}")
        assert len(topology.ports) >= len(reference.ports), (
            f"проба вернула портов {len(topology.ports)}, а в эталоне их "
            f"{len(reference.ports)} — порты эталона обязаны быть среди портов "
            "пробы: вендор выгружает их с проводом, а проба печатает все")

        missing = sorted(set(reference_directions) - set(probe_directions))
        assert missing == [], (
            f"в пробе нет эталонных портов {missing} — адрес порта это пара "
            "(имя объекта, индекс), и он обязан совпадать с эталонным")
        wrong_directions = sorted(
            (address, reference_directions[address], probe_directions[address])
            for address in reference_directions
            if probe_directions[address] != reference_directions[address])
        assert wrong_directions == [], (
            f"направления разошлись (адрес, эталон, проба): {wrong_directions}")

        # Имя порта сверяется отдельно от адреса, хотя адрес — это (объект,
        # индекс). Поле публичное, и до этой проверки оно не сверялось ни с чем:
        # проба могла перестать передавать имя из `getportinfo` (или передавать
        # чужое), а сверка направлений и адресов осталась бы зелёной — имя в неё
        # не входит. В эталоне оно есть (`SelfPortName`), и это тот же источник:
        # вендор зовёт `getportinfo` ровно так же.
        wrong_names = sorted(
            (address, reference_port_names[address], probe_port_names[address])
            for address in reference_port_names
            if probe_port_names[address] != reference_port_names[address])
        assert wrong_names == [], (
            f"имена портов разошлись (адрес, эталон, проба): {wrong_names}")

        assert probe_keys == reference_keys, (
            f"связи разошлись: лишние {sorted(probe_keys - reference_keys)}, "
            f"пропавшие {sorted(reference_keys - probe_keys)}")
    finally:
        project.close()


def _script_records(client, project, path) -> list:
    """Сырые скриптовые записи выгрузки — независимо от средств моста.

    Кодировку разбирает библиотечный `decode_xprt` (по байтам, с учётом BOM), а
    не `read_text`: подстановка U+FFFD скрыла бы порчу файла, ради обнаружения
    которой тест и написан.
    """
    client.call("SaveProjectXML", project.id, str(path))
    return parse_xprt_script_records(decode_xprt(path.read_bytes()))


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

        # Печать идёт до утверждений: измеренное надо увидеть и тогда, когда
        # прогон красный, — иначе о содержимом записи субмодели остаётся только
        # догадываться по тексту отказа.
        print(f"\nстраниц в выгрузке: {len(before)} -> {len(after)}; "
              f"непустые скриптовые записи (номер, символов) до: "
              f"{[(i, len(r)) for i, r in enumerate(before) if r]}")
        print("непустые скриптовые записи (номер, символов) после: "
              f"{[(i, len(r)) for i, r in enumerate(after) if r]}")

        assert len(topology.objects) == 35, "проба перестала читать контейнер"
        # Число страниц пинится к демо, а не выводится из сравнения снимков:
        # before и after разбирает **один** разбор, и систематический пропуск
        # страницы оставил бы `before == after` зелёным. Измерено 2026-09-22 на
        # этом демо: **83** страницы — и столько же скриптовых записей, в любом
        # состоянии проекта (сразу после открытия, после активации страницы
        # субмодели, после пробы). В плане стояло 67; расхождение — находка
        # прогона, а не подгонка: замер воспроизводится, а разбор сам сверяет
        # число записей с числом страниц, и на 67 он бы отказал.
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


def test_connections_raw_and_collapsed_are_reported(client, tmp_path,
                                                    wired_project):
    """На парной линии связь приходит с обеих сторон — сырых строк вдвое больше.

    Оговорка про «парную» здесь обязательна: симметрия наблюдения — свойство
    **этой** фикстуры (в модели одна линия с двумя концами), а не закона среды.
    После вендорского правила кратности входной порт берёт только первого соседа,
    и на развилке `traceallports` наблюдает связь не с обоих концов — это
    измерено отдельно (несимметричность на T2, см. `docs/api.md`).


    Тест переведён на проект **с объектами**. На `Project.from_template`
    объектов и линий нет вовсе: тест печатал «0, 0» и утверждал `0 == 0`, то
    есть не измерял ничего, — а находку Task 9 пришлось добывать отдельным
    прогоном. Здесь измеряются оба числа сразу: сколько строк `conn` написала
    проба и сколько связей осталось после схлопывания каноническим ключом.

    Числа известны заранее: в модели ровно одна линия, то есть одна связь, а у
    линии два конца — `traceallports` наблюдает её с обоих, и сырых строк ровно
    вдвое больше. Проверка «уникальных ключей столько же, сколько связей»
    остаётся: она ловит поломку канонизации, а не схлопывание.
    """
    result = ScriptBridge(client, wired_project.id).run_probe(
        build_topology_probe(), tmp_path / "t.txt")
    topology = parse_topology("\n".join(result.lines))
    raw = [line for line in result.lines if line.startswith(CONN_ROW + "\t")]
    keys = {connection_key(c) for c in topology.connections}
    print(f"\nсырых строк conn: {len(raw)}, связей после схлопывания: "
          f"{len(topology.connections)}, уникальных ключей: {len(keys)}")
    assert len(keys) == len(topology.connections), (
        "разбор вернул две записи об одной связи — канонизация сломана")
    assert len(topology.connections) == 1, "в модели ровно одна линия"
    assert len(raw) == 2 * len(topology.connections), (
        "на парной линии связь приходит с обоих концов: сырых строк вдвое "
        "больше")


def test_objects_match_com(client, tmp_path, wired_project):
    """Сверка с COM — источник, который для объектов сильнее пробы.

    Тест переведён на проект **с объектами**. На `Project.from_template` COM
    видит 0 объектов и проба возвращала 0: проверялось `0 == 0`, а цикл «COM
    находит каждый объект по имени» не исполнялся ни разу — тест не мог упасть
    ни при какой поломке (измерено живьём).

    Равенство «число объектов пробы = `GetPageObjectCount`» верно **только** на
    пустой странице: COM считает и линии, и подписи, а проба после правки — нет.
    Поэтому проверяется: (а) каждый объект пробы разрешается COM по имени —
    иначе две картины мира расходятся в самой идентичности объекта, и это
    противоречие, а не расхождение форматов; (б) объектов у пробы **меньше**,
    чем COM видит на странице, — иначе фильтр ничего не отсеял и тест опять
    ничего не измеряет; (в) классы **печатаются рядом**.

    **Имена классов не сверяются равенством** — прежняя оговорка в силе:
    `Block.class_name` в самой библиотеке документирует, что для блока-плагина
    свойство `ClassName` возвращает имя плагина, а не класс, — то есть
    равенство может не выполняться законно.
    """
    page = wired_project.get_main_page()
    by_com = client.call("GetPageObjectCount", wired_project.id)
    topology = read_topology(client, wired_project.id, tmp_path / "t.txt")
    assert topology.objects, "проба не вернула ни одного объекта — сверять не с чем"

    mismatched = []
    for row in topology.objects:
        block = page.find_block(row.name)
        assert block is not None, f"COM не находит объект {row.name!r}"
        if block.class_name != row.class_name:
            mismatched.append((row.name, row.class_name, block.class_name))

    assert len(topology.objects) < by_com, (
        f"проба вернула {len(topology.objects)} объектов, а COM видит на "
        f"странице {by_com}: фильтр не отсеял ни линии, ни подписи — сверять "
        "нечего")
    print(f"\nCOM видит на странице {by_com} объектов, проба вернула "
          f"{len(topology.objects)}: {[row.name for row in topology.objects]}")
    if mismatched:
        print("класс от языка и класс от COM разошлись "
              f"({len(mismatched)} из {len(topology.objects)}):")
        for name, by_lang, by_com_name in mismatched[:10]:
            print(f"  {name}: язык {by_lang!r}, COM {by_com_name!r}")
        print("это находка прогона — записать в спецификацию")


#: Тело пробы: для каждого порта страницы печатает и номер из цикла, и номер,
#: который возвращает вендорская пара функций для того же самого порта.
PORT_INDEX_ROUND_TRIP_BODY = """\
var contid: integer,
    objcnt: integer,
    obj_idx: integer,
    objid: integer,
    objtype: integer,
    portcnt: integer,
    port_idx: integer,
    portid: integer,
    back: integer;
contid = getcurrentcontainer;
objcnt = getobjcount(contid);
for(obj_idx=1, objcnt) begin
  objid = getobj(contid, obj_idx);
  objtype = getobjtypeid(objid);
  if (objtype = 100) or (objtype = 102) then begin
    portcnt = getblockportcount(objid);
    for(port_idx=0, portcnt-1) begin
      portid = getblockportid(objid, port_idx);
      back = getportindex(portid);
      writelnutf8(fid, getobjname(objid) + chr(9) + inttostr(port_idx)
                       + chr(9) + inttostr(back));
    end;
  end;
end;
"""


def test_port_index_round_trip_is_identity(client, tmp_path):
    """Живой замер: `getportindex(getblockportid(obj, i))` равно `i`.

    До этого прогона тождество опиралось на совпадение чисел на измеренных
    моделях и на пример из вендорской справки — то есть было подтверждено
    документацией, но не измерено. Здесь проба берёт порт **по номеру** и
    спрашивает у среды его номер **обратно**; расхождение печатается, а не
    сглаживается.

    Почему это не придирка. Разбор топологии адресует порт счётчиком цикла
    (`getblockportid(objid, i)`), а порт соседа — результатом `getportindex`.
    Разойдись эти нумерации, связи указывали бы не на те порты, и отказ был бы
    громким («необъявленный порт»), но разбираться пришлось бы в графе, а не в
    прогоне.
    """
    project = Project.from_template(client)
    project.set_calc_end_time(1.0)
    page = project.get_main_page()
    # Модель обязана **считаться**: скрипт исполняется на расчётном шаге, а
    # неподключённый вход молча останавливает расчёт всей модели — и мост
    # читает это как «скрипт не скомпилировался». Поэтому все входы соединены.
    #
    # Сумматор берётся с тремя входами: тождество проверяется перебором
    # номеров, и на двухпортовом блоке перебор вырожден.
    source = page.create_block("Ступенька", 0, 0)
    summer = page.create_block("Сумматор", 200, 0)
    summer.set_in_port_count(3)
    for in_index in range(3):
        source.connect(summer, 0, in_index)
    gain = page.create_block("Усилитель", 400, 0)
    integ = page.create_block("Интегратор", 600, 0)
    summer.connect(gain)
    gain.connect(integ)
    try:
        result = ScriptBridge(client, project.id).run_probe(
            PORT_INDEX_ROUND_TRIP_BODY, tmp_path / "t.txt")
        rows = []
        for line in result.lines:
            parts = line.split("\t")
            if len(parts) == 3:
                rows.append((parts[0], int(parts[1]), int(parts[2])))

        # Страховка от вырождения: без портов и на одном блоке утверждение
        # ниже истинно при любом коде.
        assert rows, "проба не вернула ни одного порта — сверять не с чем"
        assert len(rows) >= 4, f"портов всего {len(rows)} — проверка вырождена"
        assert len({name for name, _, _ in rows}) >= 2, (
            "порты только одного блока — сквозная нумерация не проверена")

        mismatched = [(n, i, b) for n, i, b in rows if i != b]
        print(f"\nпортов проверено: {len(rows)}, блоков: "
              f"{len({n for n, _, _ in rows})}")
        if mismatched:
            print("РАСХОЖДЕНИЕ номера порта и getportindex:")
            for name, number, back in mismatched[:10]:
                print(f"  {name}: цикл {number}, getportindex {back}")
        assert not mismatched, (
            f"тождество нарушено на {len(mismatched)} из {len(rows)} портов — "
            "адресация связей в топологии недостоверна")
    finally:
        project.close()


#: Правило кратности вендора в теле пробы (`export_sheme_functions.inc:99`).
#: Мутация ищет **эту строку**, а не позицию в тексте: переименованное правило
#: обязано провалить мутацию, а не пройти незамеченным.
MIN_RULE = "if mode = 0 then count_of_conn = min(1, cols(peers));"

#: Все соседи без обрезки — семантика редакции до 2026-09-23. Мутант проверяет
#: **правило контракта**, а не имя вызванной функции.
NO_MIN_RULE = "if mode = 0 then count_of_conn = cols(peers);"


def _branch_project(client, kind: str):
    """Ступенька, усилитель и интегратор — две формы одной и той же развилки.

    `"branch"` — одна линия с ответвлением (`Wire.branch_to`), `"two_connects"` —
    два отдельных `connect` с выхода ступеньки. Формы проводки разные, публичный
    результат у них одинаковый: см. `test_branch_shapes_give_the_same_connections`.
    """
    project = Project.from_template(client)
    project.set_calc_end_time(1.0)
    page = project.get_main_page()
    step = page.create_block("Ступенька", 0, 0)
    gain = page.create_block("Усилитель", 300, 0)
    integ = page.create_block("Интегратор", 300, 200)
    if kind == "branch":
        wire = step.connect(gain, 0, 0)
        wire.branch_to(integ.get_in_port(0))
    else:
        step.connect(gain, 0, 0)
        step.connect(integ, 0, 0)
    return project


def _probe_topology(client, project, tmp_path, body):
    """Одна проба на проект.

    Вторая проба на той же странице роста модельного времени не находит, поэтому
    каждое тело получает свой проект: тот же приём, что в `14_harness_smoke` и в
    разборе провала пробы (см. `test_probe_works_on_vendor_demo`).
    """
    result = ScriptBridge(client, project.id).run_probe(body, tmp_path / "t.txt")
    return parse_topology("\n".join(result.lines))


def _ends_by_direction(topology):
    """Связи как набор пар направлений концов — чем звезда отличается от треугольника.

    Сравнивать сами адреса здесь нельзя: тест обязан отличать **форму**, а имена
    блоков в фикстуре зависят от библиотеки, а не от правила кратности.
    """
    direction = {(p.object_name, p.index): p.direction for p in topology.ports}
    return {
        frozenset((direction[(c.object_a, c.index_a)],
                   direction[(c.object_b, c.index_b)]))
        for c in topology.connections
    }


def test_vendor_cardinality_rule_makes_the_branch_a_star(client, tmp_path):
    """Правило кратности вендора — то, что делает развилку звездой, а не треугольником.

    Контракт найден в поставке 2026-09-23: `bin/include_mvtu/
    export_sheme_functions.inc:99` берёт на **входной** порт не больше одного
    соседа (`min(1, cols(...))`), на остальные — всех. Проба воспроизводит это
    правило, и тест держит не запись в списке имён, а **само правило**: рядом с
    правильным телом запускается мутант, где обрезка снята, и он обязан вернуть
    ровно прежнюю семантику.

    Почему это вообще различимо. `traceallports` отдаёт не соседа, а **всю
    связную компоненту**: на измеренной развилке каждый из трёх портов видит
    обоих остальных (измерено 2026-09-23 телом пробы: у входа их два, включая
    брата по разветвлению). Без обрезки вход называет соседом брата, и в
    протоколе появляется ребро вход–вход; с обрезкой — только ребро к выходу.
    Отсюда проверка формы, а не числа: у звезды **каждый** конец связи — вход и
    выход, у треугольника добавляется пара вход–вход.

    Форма выбрана вместо адресов сознательно, и вот измеренное основание. На
    демо вендора редакции **неразличимы** (64 сырые строки и 32 связи у обеих:
    там у всех 32 линий ровно два конца), поэтому демо это правило не проверяет
    вовсе, а прежняя редакция проходила сверку с эталоном. Различает только
    развилка, и на ней числа измерены: правило вендора — 4 сырые строки и 2
    связи, мутант — 6 и 3.
    """
    body = build_topology_probe()
    mutated = body.replace(MIN_RULE, NO_MIN_RULE)
    assert mutated != body, (
        "мутация не применилась: строка правила кратности в теле изменилась, и "
        "тест проверял бы мутанта против мутанта")

    project = _branch_project(client, "branch")
    try:
        star = _probe_topology(client, project, tmp_path, body)
    finally:
        project.close()

    project = _branch_project(client, "branch")
    try:
        triangle = _probe_topology(client, project, tmp_path, mutated)
    finally:
        project.close()

    print(f"\nправило вендора: связей {len(star.connections)}, "
          f"наборы направлений концов {_ends_by_direction(star)}")
    print(f"мутант без обрезки: связей {len(triangle.connections)}, "
          f"наборы направлений концов {_ends_by_direction(triangle)}")

    assert len(star.connections) == 2, (
        "на развилке вендорское правило даёт звезду из двух связей — по одной на "
        "каждого потребителя")
    assert _ends_by_direction(star) == {frozenset({"in", "out"})}, (
        "у звезды каждый конец связи — вход и выход; пара вход–вход означала бы, "
        "что обрезка правила кратности не сработала")

    assert len(triangle.connections) == 3, (
        "мутант без обрезки обязан вернуть треугольник — иначе он не "
        "воспроизводит прежнюю редакцию, и правило кратности ничем не проверено")
    assert frozenset({"in", "in"}) in _ends_by_direction(triangle), (
        "мутант обязан вернуть связь вход–вход (брат по разветвлению) — ровно то "
        "ребро, которого в вендорской выгрузке нет")


def test_branch_shapes_give_the_same_connections(client, tmp_path):
    """Две разные формы проводки дают одно и то же множество связей — потеря формы.

    Это не дефект пробы, а **граница контракта**, и тест держит её явно. Одна
    линия с ответвлением (`branch_to`) и два отдельных `connect` с одного выхода
    устроены внутри по-разному: у первой ветвь — свой сегмент линии, у вторых
    своя линия у каждого потребителя (измерено `getportwireid`, 2026-09-23).
    Публичный `conn` у них совпадает, потому что кратность соседей взята у
    вендора, а вендор в `conn` пишет отношение связей, а не проводку.

    Отсюда — то, ради чего тест написан: `Topology.connections` нельзя читать
    как обратимое описание линий. Ветвление, восстановленное из `conn`, не
    отличит одну разветвлённую линию от двух отдельных — и это надо знать до
    того, как на этом поле строить что-то ещё.
    """
    shapes = {}
    for kind in ("branch", "two_connects"):
        project = _branch_project(client, kind)
        try:
            topology = _probe_topology(client, project, tmp_path,
                                       build_topology_probe())
        finally:
            project.close()
        shapes[kind] = {connection_key(c) for c in topology.connections}
        print(f"\n{kind}: связей {len(topology.connections)} {sorted(shapes[kind])}")

    assert len(shapes["branch"]) == 2 and len(shapes["two_connects"]) == 2, (
        "обе формы обязаны дать по две связи — иначе сравнивать нечего")
    assert shapes["branch"] == shapes["two_connects"], (
        "формы проводки разные, а отношение связей у них одно: расхождение "
        "означало бы, что вендорская кратность где-то не воспроизведена")


#: Тело переписи: снимает по каждому объекту (кроме линий и подписи) тип, число
#: портов, владельца, класс, имя и по каждому порту — режим, линию и **обратный
#: переход** `getportindex(getblockportid(obj, i))`. Использовалось для замера
#: критерия допустимости 2026-09-23; здесь закрепляет его результат.
ELIGIBILITY_CENSUS_BODY = """\
var contid: integer,
    objcnt: integer,
    obj_idx: integer,
    objid: integer,
    objtype: integer,
    objowner: integer,
    portcnt: integer,
    port_idx: integer,
    portid: integer,
    mode: integer,
    alinetype: integer,
    wid: integer,
    back: integer,
    nm: string,
    cn: string,
    portname: string,
    TAB: string;
contid = getcurrentcontainer;
objcnt = getobjcount(contid);
TAB = chr(9);
for(obj_idx=1, objcnt) begin
  objid = getobj(contid, obj_idx);
  objtype = getobjtypeid(objid);
  objowner = getownercontainer(objid);
  portcnt = getblockportcount(objid);
  nm = getobjname(objid);
  cn = getobjclassname(objid);
  writelnutf8(fid, "K" + TAB + inttostr(objtype) + TAB + inttostr(portcnt) + TAB
                   + inttostr(objowner) + TAB + cn + TAB + nm);
  if objtype <> 101 then begin
    if objtype <> 108 then begin
      for(port_idx=0, portcnt-1) begin
        portid = getblockportid(objid, port_idx);
        mode = getportinfo(portid, portname, alinetype);
        wid = getportwireid(portid);
        back = getportindex(portid);
        writelnutf8(fid, "A" + TAB + nm + TAB + inttostr(port_idx) + TAB
                         + inttostr(mode) + TAB + inttostr(wid) + TAB
                         + inttostr(back));
      end;
    end;
  end;
end;
"""

#: Тело адресного прогона по отсекаемым типам: пишет строку объекта **до**
#: вызовов порта, поэтому по последней строке видно, на чём оборвалось.
BY_LINE_BODY = """\
var contid: integer,
    objcnt: integer,
    obj_idx: integer,
    objid: integer,
    objtype: integer,
    portcnt: integer,
    port_idx: integer,
    portid: integer,
    mode: integer,
    alinetype: integer,
    wid: integer,
    back: integer,
    nm: string,
    cn: string,
    portname: string,
    TAB: string;
contid = getcurrentcontainer;
objcnt = getobjcount(contid);
TAB = chr(9);
for(obj_idx=1, objcnt) begin
  objid = getobj(contid, obj_idx);
  objtype = getobjtypeid(objid);
  if (objtype = 101) or (objtype = 108) then begin
    nm = getobjname(objid);
    cn = getobjclassname(objid);
    portcnt = getblockportcount(objid);
    writelnutf8(fid, "N" + TAB + inttostr(objtype) + TAB + inttostr(portcnt) + TAB
                     + cn + TAB + nm);
    for(port_idx=0, portcnt-1) begin
      portid = getblockportid(objid, port_idx);
      mode = getportinfo(portid, portname, alinetype);
      wid = getportwireid(portid);
      back = getportindex(portid);
      writelnutf8(fid, "B" + TAB + nm + TAB + inttostr(port_idx) + TAB
                       + inttostr(mode) + TAB + inttostr(wid) + TAB
                       + inttostr(back));
    end;
  end;
end;
"""


def _project_with_typed_candidates(client):
    """Источник и два объекта дополнительных типов: «В память» и «Временной график».

    Каждому — свой источник и подключённый вход: один выход на несколько входов
    перевешивает линию (измерено), а неподключённый вход останавливает расчёт
    всей модели (PR #19).
    """
    project = Project.from_template(client)
    project.set_calc_end_time(1.0)
    page = project.get_main_page()
    source = page.create_block("Ступенька", 0, 0)
    made = {}
    for name, x in (("В память", 300), ("Временной график", 600)):
        block = page.create_block(name, x, 0)
        own_source = page.create_block("Ступенька", x, 200)
        own_source.connect(block, 0, 0)
        made[name] = block
    source.connect(page.create_block("Усилитель", 900, 0), 0, 0)
    return project, made


def test_eligible_types_are_addressed_and_declared(client, tmp_path):
    """104/106 входят в object-set, их порты адресуются, связь к ним не теряется.

    Три проверки, и каждая про своё. Первая: критерий допустимости **измерен**, а
    не объявлен, поэтому живой прогон снимает обратный переход
    `getportindex(getblockportid(obj, i)) = i` для портов 104/106 — до этой правки
    такой прогон был только по 100/102. Вторая: проба объявляет эти объекты —
    иначе строка `conn` сослалась бы на необъявленный объект, и разбор отверг бы
    модель целиком. Третья: связи к ним **появляются** — до правки связь терялась
    молча, потому что объект не объявлялся.

    Сопоставление идёт **по классу**, а не по имени, и это измеренная причина: у
    объектов этих классов `Block.get_name()` возвращает **пустую строку**, тогда
    как языковая `getobjname` имя даёт — и именно оно попадает в протокол.
    """
    project, _made = _project_with_typed_candidates(client)
    try:
        result = ScriptBridge(client, project.id).run_probe(
            ELIGIBILITY_CENSUS_BODY, tmp_path / "t.txt")
        rows = [line.split("\t") for line in result.lines]
    finally:
        project.close()

    # Строка K: тип, число портов, владелец, класс, имя.
    by_class = {}
    for row in rows:
        if row[0] == "K":
            by_class[row[4]] = {"type": int(row[1]), "ports": int(row[2]),
                                "name": row[5], "port_rows": []}
    by_name = {data["name"]: data for data in by_class.values()}
    for row in rows:
        if row[0] == "A" and row[1] in by_name:
            # Строка A: имя, индекс, режим, линия, обратный переход.
            by_name[row[1]]["port_rows"].append(
                {"index": int(row[2]), "mode": int(row[3]),
                 "wire": int(row[4]), "back": int(row[5])})

    print(f"\nCLASSES: {sorted(by_class)}")
    for class_name in ("В память", "Временной график"):
        data = by_class.get(class_name)
        assert data is not None, (
            f"{class_name} не нашёлся в переписи: {sorted(by_class)}")
        assert data["ports"] >= 1, f"{class_name}: портов {data['ports']}"
        assert data["port_rows"], f"{class_name}: портов не перечислено"
        for port in data["port_rows"]:
            assert port["back"] == port["index"], (
                f"{class_name}: адресация не держится — getportindex дал "
                f"{port['back']} для индекса {port['index']}")
            assert port["mode"] in (0, 1, 2), (
                f"{class_name}: getportinfo вернул режим {port['mode']}")
        fed = [port for port in data["port_rows"] if port["mode"] == 0]
        assert fed and fed[0]["wire"] != 0, (
            f"{class_name}: подключённый вход без линии — getportwireid вернул 0")

    project, _made = _project_with_typed_candidates(client)
    try:
        topology = read_topology(client, project.id, tmp_path / "t2.txt")
    finally:
        project.close()

    classes = {row.class_name for row in topology.objects}
    assert {"В память", "Временной график"} <= classes, (
        f"object-set не содержит объекты дополнительных типов: {sorted(classes)}")
    eligible_names = {row.name for row in topology.objects
                      if row.class_name in ("В память", "Временной график")}
    print(f"ELIGIBLE-NAMES: {sorted(eligible_names)}; "
          f"CONNECTIONS: {len(topology.connections)}")
    assert eligible_names, "объекты дополнительных типов не объявлены по имени"
    touched = ({connection.object_a for connection in topology.connections}
               | {connection.object_b for connection in topology.connections})
    lost = eligible_names - touched
    assert not lost, (
        f"связи к объектам дополнительных типов потеряны: {sorted(lost)} "
        f"не встречаются ни в одной из {len(topology.connections)} связей")


def test_line_fails_addressing_round_trip(client, tmp_path):
    """Линия отсекается **данными**: её адресация не держится.

    Это не «101 в списке нет» — это измеренный признак, на котором стоит условие
    критерия. На фикстуре с несколькими линиями снимается
    `getportindex(getblockportid(wire, i))`, и хотя бы на одной линии он **не
    равен** индексу. Если такое перестанет воспроизводиться, тест покраснеет: это
    будет означать, что основание исключать линии надо перепроверить (тогда
    остаётся только условие «не презентационная инфраструктура»).
    """
    project, _made = _project_with_typed_candidates(client)
    try:
        result = ScriptBridge(client, project.id).run_probe(
            BY_LINE_BODY, tmp_path / "t.txt")
        rows = [line.split("\t") for line in result.lines]
    finally:
        project.close()

    lines = [row for row in rows if row[0] == "N" and row[1] == "101"]
    measured = [{"name": row[1], "index": int(row[2]), "back": int(row[5])}
                for row in rows if row[0] == "B"]
    print(f"\nлиний в фикстуре: {len(lines)}; адресных строк по линиям: "
          f"{len(measured)}")
    broken = [m for m in measured if m["back"] != m["index"]]
    for m in broken:
        print(f"  расхождение: {m['name']}.{m['index']} → getportindex "
              f"{m['back']}")
    assert lines, "в фикстуре нет ни одной линии — проверять нечего"
    assert measured, "адресных строк по линиям нет — тело не отработало"
    assert broken, (
        "ни одна линия не разошлась по адресации: основание исключать линии "
        "нужно перепроверить — измеренный признак перестал воспроизводиться")
