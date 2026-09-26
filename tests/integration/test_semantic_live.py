"""Живой прогон семантического слоя: SimInTech, реальный COM.

Проверяется то, чего не подтвердить фейками: обзор собирается из **того**
контейнера, в который вошли, и совпадает с эталоном вендора по именам объектов и
ключам связей — а не по числам, вбитым константой.

Сверка сознательно повторяет форму топологического живого теста, но **своими**
константами и своим помощником: живые тесты не импортируют друг из друга — иначе
правка в одном молча меняет условие другого.
"""

import collections
import os
import shutil
import sys
from pathlib import Path

import pytest

from simintech_api import COMClient
from simintech_api.core.project import Project
from simintech_api.core.semantic import read_model_overview
from simintech_api.semantic import (
    ContainerRef,
    inspect_object,
    inspect_port,
    overview_to_dict,
    query_connections,
)
from simintech_api.topology import Connection, connection_key

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from vendor_reference import VendorReference, load_reference  # noqa: E402

pytestmark = pytest.mark.integration

#: Демо вендора: эталон снят его же скриптом **внутри** контейнера, поэтому обзор
#: надо читать оттуда же — иначе сверять будет нечего.
VENDOR_DEMO = (r"C:\SimInTech64\Demo\Приёмы работы\Анализ и отчеты"
               r"\Анализ топологии скриптами и экспорт в json"
               r"\Экспорт топологии и свойств в json"
               r"\Экспорт топологии и свойств в json.prt")

#: Имя блока-контейнера на главной странице демо (эталон снят внутри него).
VENDOR_CONTAINER = "acrms_Circuit1"


@pytest.fixture(scope="module")
def reference() -> VendorReference:
    """Разобранный эталон вендора — тем же разбором, что и в юнит-тесте."""
    return load_reference()


def _open_demo(client: COMClient, tmp_path: Path) -> Project:
    """Копия демо: проба пишет в проект, и поставку трогать нельзя."""
    if not os.path.exists(VENDOR_DEMO):
        pytest.skip(f"нет демо вендора: {VENDOR_DEMO}")
    work = tmp_path / "demo.prt"
    shutil.copy2(VENDOR_DEMO, work)
    return Project.open(client, str(work))


def test_model_overview_matches_vendor_reference_inside_container(
        client: COMClient, tmp_path: Path,
        reference: VendorReference) -> None:
    """Обзор внутри контейнера: имена объектов и ключи связей — как в эталоне.

    Портов требуется **не меньше** эталонных: вендор выгружает только порты с
    проводом, а обзор показывает все. Сверка по именам и ключам, а не по числам,
    держится независимо от того, появится ли в копии демо неподключённый блок.
    """
    project = _open_demo(client, tmp_path)
    try:
        container = project.get_main_page().find_block(VENDOR_CONTAINER)
        assert container is not None, (
            f"на главной странице демо нет блока {VENDOR_CONTAINER!r}")
        project.submodel_page(container.id).activate()

        overview = read_model_overview(
            client, project.id, tmp_path / "overview.txt",
            container=ContainerRef.submodel(container.id,
                                            container.get_name()))

        assert {obj.name for obj in overview.objects} == {
            row.name for row in reference.objects}, (
            "обзор описывает не тот контейнер, из которого снят эталон")
        assert {connection_key(link) for link in overview.connections} == (
            reference.connection_keys()), (
            "ключи связей обзора разошлись с эталоном вендора")
        assert overview.port_count >= len(reference.ports), (
            "обзор показывает меньше портов, чем эталон: порты потерялись")

        assert (overview.container.kind, overview.container.block_id,
                overview.container.block_name) == ("submodel", container.id,
                                                   VENDOR_CONTAINER)

        as_dict = overview_to_dict(overview)
        assert as_dict["summary"] == {
            "objects": len(overview.objects),
            "ports": overview.port_count,
            "connections": len(overview.connections),
        }, "сводка разошлась с самими данными обзора"
        assert sum(len(obj.ports) for obj in overview.objects) == overview.port_count, (
            "порты не разложены по объектам: часть потерялась при группировке")
        assert all(obj.name for obj in overview.objects), (
            "в обзоре есть объект без имени — адресовать его нечем")
    finally:
        project.close()


def test_model_overview_on_own_project_matches_the_documented_example(
        client: COMClient, tmp_path: Path) -> None:
    """Свой проект: числа примера из `docs/api.md` — измеренные, а не написанные.

    Документация обещает «один объект, один порт, направление `out`». Проверять
    пример тем же способом, каким он написан, нельзя: тогда опечатка в нём
    закрепилась бы как ожидаемое. Здесь эти числа получаются прогоном, и если
    они разойдутся с примером, падать будет тест, а не молчание документа.
    """
    project = Project.from_template(client)
    project.set_calc_end_time(1.0)
    try:
        project.get_main_page().create_block("Ступенька", 0, 0)
        overview = read_model_overview(
            client, project.id, tmp_path / "own.txt",
            container=ContainerRef.main())

        assert overview.object_count == 1, (
            f"в проекте один блок, а обзор видит {overview.object_count}")
        assert [obj.class_name for obj in overview.objects] == ["Ступенька"]
        assert overview.port_count == 1, (
            f"у «Ступеньки» один порт, а обзор показывает {overview.port_count}")
        assert overview.objects[0].ports[0].direction == "out"
        assert overview.connections == [], "связей в проекте нет"
    finally:
        project.close()


def test_inspect_object_matches_vendor_reference(
        client: COMClient, tmp_path: Path,
        reference: VendorReference) -> None:
    """Досмотр объекта внутри контейнера совпадает с эталоном по портам и связям.

    Объект берётся **из эталона** — тот, у которого больше всего связей, — а не
    назначается вручную: тогда проверка не зависит от того, что именно лежит в
    демо, и не сломается от правки его копии. Направления портов сверяются: у
    эталона они измерены, и совпадение `index` при неверном `direction` ничего не
    доказывало бы.
    """
    project = _open_demo(client, tmp_path)
    try:
        container = project.get_main_page().find_block(VENDOR_CONTAINER)
        assert container is not None, (
            f"на главной странице демо нет блока {VENDOR_CONTAINER!r}")
        project.submodel_page(container.id).activate()
        overview = read_model_overview(
            client, project.id, tmp_path / "o.txt",
            container=ContainerRef.submodel(container.id, container.get_name()))

        keys = reference.connection_keys()
        degrees = collections.Counter()
        for left, right in keys:
            degrees[left[0]] += 1
            degrees[right[0]] += 1
        name = degrees.most_common(1)[0][0]

        inspection = inspect_object(overview, name)

        reference_ports = {(port.index, port.direction)
                           for port in reference.ports
                           if port.object_name == name}
        our_ports = {(port.index, port.direction)
                     for port in inspection.object.ports}
        assert reference_ports <= our_ports, (
            f"порты эталона не найдены в досмотре объекта {name!r}: "
            f"{reference_ports - our_ports}")

        our_keys = {connection_key(Connection(name, peer.port_index,
                                              peer.peer_object, peer.peer_index))
                    for peer in inspection.peers}
        expected = {key for key in keys if name in (key[0][0], key[1][0])}
        assert our_keys == expected, (
            f"связи досмотра объекта {name!r} разошлись с эталоном: "
            f"лишние {our_keys - expected}, потерянные {expected - our_keys}")
    finally:
        project.close()


def test_inspect_port_matches_vendor_reference(
        client: COMClient, tmp_path: Path,
        reference: VendorReference) -> None:
    """Досмотр порта внутри контейнера совпадает с эталоном по связям.

    Адрес порта берётся **из эталона** — самый связанный, — а не назначается
    вручную: проверка не зависит от того, что лежит в демо. Так же сверяется
    направление: оно у эталона измерено, и совпадение связей при неверном
    направлении ничего бы не доказывало.
    """
    project = _open_demo(client, tmp_path)
    try:
        container = project.get_main_page().find_block(VENDOR_CONTAINER)
        assert container is not None, (
            f"на главной странице демо нет блока {VENDOR_CONTAINER!r}")
        project.submodel_page(container.id).activate()
        overview = read_model_overview(
            client, project.id, tmp_path / "o.txt",
            container=ContainerRef.submodel(container.id, container.get_name()))

        keys = reference.connection_keys()
        degrees = collections.Counter()
        for left, right in keys:
            degrees[left] += 1
            degrees[right] += 1
        object_name, index = degrees.most_common(1)[0][0]

        inspection = inspect_port(overview, object_name, index)

        reference_direction = next(
            (port.direction for port in reference.ports
             if (port.object_name, port.index) == (object_name, index)), None)
        assert reference_direction is not None, (
            f"адрес {object_name}.{index} взят из эталона, но его порта там нет")
        assert inspection.port.direction == reference_direction, (
            f"направление порта {object_name}.{index} разошлось с эталоном")

        our_keys = {connection_key(Connection(object_name, index,
                                              peer.peer_object, peer.peer_index))
                    for peer in inspection.peers}
        expected = {key for key in keys
                    if (object_name, index) in (key[0], key[1])}
        assert our_keys == expected, (
            f"связи порта {object_name}.{index} разошлись с эталоном: "
            f"лишние {our_keys - expected}, потерянные {expected - our_keys}")
    finally:
        project.close()


def test_model_overview_on_main_page_is_labeled_main(
        client: COMClient, tmp_path: Path,
        reference: VendorReference) -> None:
    """Обзор снаружи контейнера описывает главную страницу, и подпись честная.

    Проверяется не «слой умеет главную страницу», а соответствие подписи данным:
    снаружи виден блок-контейнер, а объектов внутри него — не видно. Различитель
    здесь — размер: на главной странице демо объектов заведомо меньше, чем внутри
    контейнера, и число берётся из эталона, а не вбито константой.
    """
    project = _open_demo(client, tmp_path)
    try:
        overview = read_model_overview(
            client, project.id, tmp_path / "main.txt",
            container=ContainerRef.main())

        names = {obj.name for obj in overview.objects}
        assert VENDOR_CONTAINER in names, (
            "на главной странице демо должен быть виден блок-контейнер")
        assert len(names) < len(reference.objects), (
            "снаружи видно не меньше объектов, чем внутри контейнера: обзор "
            "читает не ту страницу, которой подписан")
        assert overview.container.kind == "main"
        assert (overview.container.block_id, overview.container.block_name) == (0, "")
    finally:
        project.close()


def test_query_connections_matches_vendor_reference(
        client: COMClient, tmp_path: Path,
        reference: VendorReference) -> None:
    """Запрос пары внутри контейнера: связи — как в эталоне, а пустая пара — ответ.

    Пара берётся **из эталона**: самый связанный объект и один из его соседей, —
    поэтому проверка не зависит от того, что лежит в демо. Сверяются канонические
    ключи, то есть и порты. Вторая половина проверяет обратное: у пары, которой
    эталон не соединяет, ответ **пуст** и это не отказ — «связи нет» и «объекта
    нет» живой слой различает так же, как юнит.
    """
    project = _open_demo(client, tmp_path)
    try:
        container = project.get_main_page().find_block(VENDOR_CONTAINER)
        assert container is not None, (
            f"на главной странице демо нет блока {VENDOR_CONTAINER!r}")
        project.submodel_page(container.id).activate()
        overview = read_model_overview(
            client, project.id, tmp_path / "q.txt",
            container=ContainerRef.submodel(container.id, container.get_name()))

        keys = reference.connection_keys()
        degrees = collections.Counter()
        for left, right in keys:
            degrees[left[0]] += 1
            degrees[right[0]] += 1
        name = degrees.most_common(1)[0][0]
        partners = sorted({other
                           for key in keys
                           for other in (key[0][0], key[1][0])
                           if other != name and name in (key[0][0], key[1][0])})
        assert partners, f"у объекта {name!r} в эталоне нет ни одной связи"
        partner = partners[0]

        query = query_connections(overview, name, partner)
        our_keys = {connection_key(link) for link in query.links}
        expected = {key for key in keys
                    if {key[0][0], key[1][0]} == {name, partner}}
        assert our_keys == expected, (
            f"связи пары {name!r}—{partner!r} разошлись с эталоном: "
            f"лишние {our_keys - expected}, потерянные {expected - our_keys}")

        names = sorted({other for key in keys for other in (key[0][0], key[1][0])})
        joined = [{key[0][0], key[1][0]} for key in keys]
        unlinked = next(((left, right)
                         for left in names
                         for right in names
                         if left != right and {left, right} not in joined), None)
        assert unlinked is not None, "эталон соединяет все свои объекты попарно"
        assert query_connections(overview, *unlinked).links == [], (
            f"пара {unlinked} в эталоне не соединена, а запрос вернул связи")
    finally:
        project.close()


def test_query_connections_on_own_project_sees_the_wire_we_made(
        client: COMClient, tmp_path: Path) -> None:
    """Свой проект: запрос пары видит ту связь, которую провели **мы сами**.

    Сверка не с эталоном, а со своим действием: два блока соединены через COM, и
    запрос обязан вернуть ровно одну связь между ними, назвав оба конца — причём
    порты в ней должны быть настоящими портами этих объектов, а не выдуманными
    индексами. Пара «блок с самим собой» при этом пуста: замка мы не делали.
    """
    project = Project.from_template(client)
    project.set_calc_end_time(1.0)
    try:
        page = project.get_main_page()
        source = page.create_block("Константа", 0, 0)
        gain = page.create_block("Усилитель", 200, 0)
        gain.set_property("a", 2.0)
        source.connect(gain)

        overview = read_model_overview(
            client, project.id, tmp_path / "own_query.txt",
            container=ContainerRef.main())

        query = query_connections(overview, source.get_name(), gain.get_name())
        assert len(query.links) == 1, (
            f"проведена одна связь, а запрос вернул {len(query.links)}: "
            f"{query.links}")
        link = query.links[0]
        wired = {source.get_name(), gain.get_name()}
        assert {link.object_a, link.object_b} == wired, (
            f"связь ведёт не к тем объектам, которые мы соединили: {link}")

        ports = {(port.object_name, port.index)
                 for obj in overview.objects for port in obj.ports}
        assert (link.object_a, link.index_a) in ports, (
            f"в связи назван порт, которого у объектов обзора нет: {link}")
        assert (link.object_b, link.index_b) in ports, (
            f"в связи назван порт, которого у объектов обзора нет: {link}")

        assert query_connections(overview, source.get_name(),
                                 source.get_name()).links == [], (
            "запрос пары «блок с самим собой» вернул связи, хотя замка нет")
    finally:
        project.close()
