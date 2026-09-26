"""Семантический слой: группировка топологии, подпись контейнера, форма ответа."""

import json
import os
import sys
from pathlib import Path
from typing import Any, cast

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest  # noqa: E402

from simintech_api import COMClient  # noqa: E402
from simintech_api.core import semantic as core_semantic  # noqa: E402
from simintech_api.exceptions import TopologyError  # noqa: E402
from simintech_api.semantic import (  # noqa: E402
    CONTAINER_KINDS,
    ContainerRef,
    ModelOverview,
    PortPeer,
    connection_query_to_dict,
    inspect_object,
    inspect_port,
    inspection_to_dict,
    overview_from_topology,
    overview_to_dict,
    port_inspection_to_dict,
    query_connections,
)
from simintech_api.topology import (  # noqa: E402
    Connection,
    ObjectRow,
    PortRow,
    Topology,
    connection_key,
    parse_topology,
)

#: Снимок протокола — **свой**, а не импортированный из соседнего теста: тесты
#: не должны зависеть друг от друга, иначе правка в одном молча меняет условие
#: другого. Здесь намеренно есть всё, что нужно слою: объект без портов (`C`),
#: ненаправленный порт (`A.2`) и связь, записанная с обеих сторон (после
#: разбора она одна).
SNAPSHOT = (
    "object\tA\tУсилитель\n"
    "object\tB\tКонстанта\n"
    "object\tC\tКомментарий\n"
    "port\tA\t0\tin\tx\n"
    "port\tA\t1\tout\ty\n"
    "port\tA\t2\tundirected\t\n"
    "port\tB\t0\tout\t\n"
    "conn\tB\t0\tA\t1\n"
    "conn\tA\t1\tB\t0\n"
)


def _overview(container: ContainerRef | None = None) -> ModelOverview:
    return overview_from_topology(
        parse_topology(SNAPSHOT), container or ContainerRef.main())


def test_overview_groups_ports_by_object_in_protocol_order():
    overview = _overview()
    assert [obj.name for obj in overview.objects] == ["A", "B", "C"]
    assert [obj.class_name for obj in overview.objects] == [
        "Усилитель", "Константа", "Комментарий"]
    assert [(port.index, port.direction) for port in overview.objects[0].ports] == [
        (0, "in"), (1, "out"), (2, "undirected")]
    assert [port.name for port in overview.objects[0].ports] == ["x", "y", ""]


def test_object_without_ports_stays_in_overview():
    """Объект без портов — не мусор: у настоящих блоков портов может не быть.

    Пропусти слой такой объект — обзор молча терял бы данные, а отличить это от
    «объекта в модели нет» было бы нечем.
    """
    last = _overview().objects[2]
    assert last.name == "C"
    assert last.ports == []
    assert (last.in_ports, last.out_ports, last.undirected_ports) == (0, 0, 0)


def test_connections_come_from_topology_unchanged():
    """Слой не пересчитывает связи — он их переносит как есть."""
    topology = parse_topology(SNAPSHOT)
    overview = _overview()
    assert overview.connections == list(topology.connections)
    assert len(overview.connections) == 1, (
        "зеркальная пара должна была схлопнуться ещё в разборе")


def test_overview_does_not_deduplicate_by_itself():
    """Дедупликация — дело разбора, и слой её не повторяет.

    Проверяется на топологии, собранной вручную: если слой начнёт «улучшать»
    связи, он станет вторым источником истины о них, и разойтись с `topology.py`
    они смогут молча.
    """
    mirrored = [
        Connection("A", 0, "B", 1),
        Connection("B", 1, "A", 0),
    ]
    topology = Topology(
        objects=[ObjectRow("A", "Усилитель"), ObjectRow("B", "Константа")],
        ports=[PortRow("A", 0, "in", "x"), PortRow("B", 1, "out", "y")],
        connections=mirrored)
    overview = overview_from_topology(topology, ContainerRef.main())
    assert overview.connections == mirrored


def test_counts_by_direction_and_totals():
    overview = _overview()
    first = overview.objects[0]
    assert (first.in_ports, first.out_ports, first.undirected_ports) == (1, 1, 1)
    assert overview.object_count == 3
    assert overview.port_count == 4


def test_overview_to_dict_has_the_declared_shape():
    """Форма ответа — то, что отдаёт адаптер, поэтому она сверяется целиком."""
    as_dict = overview_to_dict(_overview(ContainerRef.submodel(7, "acrms_Circuit1")))
    assert as_dict == {
        "container": {"kind": "submodel", "block_id": 7,
                      "block_name": "acrms_Circuit1"},
        "summary": {"objects": 3, "ports": 4, "connections": 1},
        "objects": [
            {"name": "A", "class_name": "Усилитель",
             "ports": [{"index": 0, "direction": "in", "name": "x"},
                       {"index": 1, "direction": "out", "name": "y"},
                       {"index": 2, "direction": "undirected", "name": ""}],
             "counts": {"in": 1, "out": 1, "undirected": 1}},
            {"name": "B", "class_name": "Константа",
             "ports": [{"index": 0, "direction": "out", "name": ""}],
             "counts": {"in": 0, "out": 1, "undirected": 0}},
            {"name": "C", "class_name": "Комментарий", "ports": [],
             "counts": {"in": 0, "out": 0, "undirected": 0}},
        ],
        "connections": [{"a": ["A", 1], "b": ["B", 0]}],
    }
    assert json.loads(json.dumps(as_dict)) == as_dict, (
        "ответ должен переживать JSON без доработки адаптером")


def test_container_ref_names_main_and_submodel():
    main = ContainerRef.main()
    assert main.kind in CONTAINER_KINDS
    assert (main.block_id, main.block_name) == (0, "")
    submodel = ContainerRef.submodel(7, "acrms_Circuit1")
    assert (submodel.kind, submodel.block_id, submodel.block_name) == (
        "submodel", 7, "acrms_Circuit1")


def test_container_ref_refuses_zero_block_id():
    """В COM ноль означает «блока нет» — такой ссылкой контейнер не назвать."""
    with pytest.raises(ValueError):
        ContainerRef.submodel(0, "acrms_Circuit1")


def test_overview_refuses_unknown_container_kind():
    """Опечатка в виде контейнера дала бы правдоподобную неверную подпись.

    Проверка живёт в сборке обзора, а не в конструкторе ссылки: сама по себе
    ссылка — это значение, и запрещать её создание незачем.
    """
    with pytest.raises(ValueError):
        overview_from_topology(parse_topology(SNAPSHOT),
                               ContainerRef(kind="submodelPage"))


class _NoCalls:
    """Клиент, который падает на любом обращении.

    Страж «слой не ходит в COM»: если семантический слой когда-нибудь заведёт
    собственный вызов к среде, тест упадёт здесь, а не выяснится живым прогоном.
    """

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"семантический слой обратился к COM: {name}")


def test_reader_uses_read_topology_and_nothing_else(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[tuple[object, int, Path]] = []

    def fake_read_topology(client: object, project_id: int,
                           result_path: Path) -> Topology:
        calls.append((client, project_id, result_path))
        return parse_topology(SNAPSHOT)

    monkeypatch.setattr(core_semantic, "read_topology", fake_read_topology)
    # `cast` — потому что подставной клиент обязан иметь тот же тип, что и
    # настоящий: слой принимает `COMClient`, а фейк нужен именно вместо него.
    client = cast(COMClient, _NoCalls())
    overview = core_semantic.read_model_overview(
        client, 42, tmp_path / "t.txt", container=ContainerRef.main())

    assert calls == [(client, 42, tmp_path / "t.txt")]
    assert overview.object_count == 3
    assert overview.connections == list(parse_topology(SNAPSHOT).connections)


def test_reader_propagates_refusal(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Отказ транспорта не превращается в пустой обзор."""
    def failing(client: object, project_id: int, result_path: Path) -> Topology:
        raise TopologyError("проба оборвалась")

    monkeypatch.setattr(core_semantic, "read_topology", failing)
    with pytest.raises(TopologyError):
        core_semantic.read_model_overview(
            cast(COMClient, _NoCalls()), 42, tmp_path / "t.txt",
            container=ContainerRef.main())


# ─── Досмотр объекта (M4.4) ───────────────────────────────────────

def test_inspect_object_gives_its_ports_and_peers():
    """Объект `A`: его порты, и связь с `B` — со **своей** стороны пары."""
    inspection = inspect_object(_overview(), "A")
    assert inspection.object.name == "A"
    assert [port.index for port in inspection.object.ports] == [0, 1, 2]
    assert inspection.peers == [PortPeer(port_index=1, peer_object="B", peer_index=0)]


def test_inspect_object_sees_the_same_connection_from_the_other_side():
    """Та же связь у соседа описана его портом: `B.0` ↔ `A.1`.

    Это проверка того, что проекция **не** воображает направление: у каждого
    объекта связь названа своим концом, и «источника» среди концов нет.
    """
    assert inspect_object(_overview(), "B").peers == [
        PortPeer(port_index=0, peer_object="A", peer_index=1)]


def test_inspect_object_keeps_object_without_ports_apart_from_missing():
    """Объект без портов — не то же самое, что отсутствующий объект."""
    empty = inspect_object(_overview(), "C")
    assert (empty.object.ports, empty.peers) == ([], [])
    with pytest.raises(ValueError):
        inspect_object(_overview(), "D")


def test_inspect_object_refusal_lists_known_names():
    """Отказ обязан быть полезным: что спросили и что вообще есть."""
    with pytest.raises(ValueError) as refused:
        inspect_object(_overview(), "нет_такого")
    text = str(refused.value)
    assert "нет_такого" in text
    assert "A" in text and "C" in text, f"отказ не перечисляет известные имена: {text}"


def test_inspect_object_counts_each_connection_once_per_its_port():
    """Две связи с тем же соседом разными портами — это два соседа, не один.

    Схлопывание «по соседу» потеряло бы, каким портом связь пришла, — а именно
    это и спрашивают у объекта.
    """
    topology = Topology(
        objects=[ObjectRow("A", "Усилитель"), ObjectRow("B", "Константа")],
        ports=[PortRow("A", 0, "in", "x"), PortRow("A", 1, "out", "y"),
               PortRow("B", 0, "out", "z"), PortRow("B", 1, "out", "w")],
        connections=[Connection("A", 0, "B", 0), Connection("A", 1, "B", 1)])
    peers = inspect_object(overview_from_topology(
        topology, ContainerRef.main()), "A").peers
    assert peers == [PortPeer(0, "B", 0), PortPeer(1, "B", 1)]


def test_inspection_to_dict_reuses_the_overview_object_shape():
    """Объект в досмотре — **тот же** словарь, что в обзоре.

    Разойдись формы — агент получал бы об одном объекте два разных
    представления в зависимости от того, каким вызовом спросил.
    """
    overview = _overview()
    as_dict = inspection_to_dict(inspect_object(overview, "A"))
    assert as_dict["object"] == overview_to_dict(overview)["objects"][0]
    assert as_dict["peers"] == [{"port": 1, "peer": {"object": "B", "index": 0}}]
    assert json.loads(json.dumps(as_dict)) == as_dict


# ─── Досмотр порта (M4.5) ─────────────────────────────────────────

def test_inspect_port_gives_its_data_and_peers():
    """Порт `A.1`: он сам (индекс, направление, имя) и связь с `B.0`."""
    inspection = inspect_port(_overview(), "A", 1)
    assert (inspection.object_name, inspection.port.index,
            inspection.port.direction, inspection.port.name) == ("A", 1, "out", "y")
    assert inspection.peers == [PortPeer(port_index=1, peer_object="B", peer_index=0)]


def test_inspect_port_without_connections_is_not_an_error():
    """Порт без провода — обычное состояние модели, а не отказ и не «нет порта»."""
    assert inspect_port(_overview(), "A", 0).peers == []


def test_inspect_port_refusal_separates_missing_object_from_missing_port():
    """«Объекта нет» и «у объекта нет такого порта» — разные состояния и тексты."""
    with pytest.raises(ValueError) as no_object:
        inspect_port(_overview(), "нет_такого", 0)
    assert "нет_такого" in str(no_object.value)

    with pytest.raises(ValueError) as no_port:
        inspect_port(_overview(), "A", 9)
    text = str(no_port.value)
    assert "'A'" in text and "9" in text, text
    assert "0, 1, 2" in text, f"отказ не перечисляет известные индексы: {text}"


def test_inspect_port_sees_the_connection_from_the_other_side():
    """Та же связь у порта `B.0` описана его соседом `A.1` — без «источника»."""
    inspection = inspect_port(_overview(), "B", 0)
    assert inspection.peers == [PortPeer(port_index=0, peer_object="A", peer_index=1)]
    assert "direction" not in port_inspection_to_dict(inspection)["peers"][0], (
        "у соседа не может быть направления: концы связи неориентированы")


def test_port_may_have_more_than_one_connection():
    """«Один порт — одна связь» — не предположение слоя: у порта может быть две.

    Вендорский экспортёр берёт одного соседа только на **входной** порт, поэтому
    слой обязан перечислять столько связей, сколько их есть.
    """
    topology = Topology(
        objects=[ObjectRow("A", "Усилитель"), ObjectRow("B", "Константа"),
                 ObjectRow("C", "Константа")],
        ports=[PortRow("A", 0, "out", "y"), PortRow("B", 0, "in", "x"),
               PortRow("C", 0, "in", "x")],
        connections=[Connection("A", 0, "B", 0), Connection("A", 0, "C", 0)])
    inspection = inspect_port(
        overview_from_topology(topology, ContainerRef.main()), "A", 0)
    assert inspection.peers == [PortPeer(0, "B", 0), PortPeer(0, "C", 0)]


def test_port_and_object_inspections_describe_the_same_connection():
    """Досмотр порта и досмотр объекта считают соседей **одним** кодом.

    Инвариант: соседи объекта — в точности соседи всех его портов, в порядке
    портов. Разойдись они, агент получал бы два ответа об одной связи.
    """
    overview = _overview()
    by_object = inspect_object(overview, "A")
    by_ports = [peer
                for port in by_object.object.ports
                for peer in inspect_port(overview, "A", port.index).peers]
    assert by_object.peers == by_ports


def test_port_inspection_to_dict_reuses_the_overview_port_shape():
    """Порт в досмотре — **тот же** словарь, что в объекте обзора."""
    overview = _overview()
    as_dict = port_inspection_to_dict(inspect_port(overview, "A", 1))
    assert as_dict["port"] == overview_to_dict(overview)["objects"][0]["ports"][1]
    assert as_dict == {
        "object": "A",
        "port": {"index": 1, "direction": "out", "name": "y"},
        "peers": [{"object": "B", "index": 0}],
    }
    assert json.loads(json.dumps(as_dict)) == as_dict


# ─── Запрос связей пары (M4.6) ────────────────────────────────────

def test_query_gives_the_link_between_two_objects():
    """«Какие связи между `A` и `B`» — связь, у которой названы **оба** конца.

    Разбор хранит связь в порядке канонического ключа, поэтому в ответе видно и
    `A.1`, и `B.0`: это не «сосед», у которого вторая сторона названа вызывающим,
    а связь целиком.
    """
    query = query_connections(_overview(), "A", "B")
    assert (query.object_a, query.object_b) == ("A", "B")
    assert query.links == [Connection("A", 1, "B", 0)]


def test_query_does_not_depend_on_the_order_of_the_pair():
    """Порядок в вопросе ничего не значит: `(A, B)` и `(B, A)` — один вопрос.

    Ответить по-разному значило бы утверждать направление связи, которого в
    данных нет. Подпись ответа повторяет вопрос — но не переставляет его, а связь
    остаётся в том порядке, в каком её записал разбор.
    """
    forward = query_connections(_overview(), "A", "B")
    backward = query_connections(_overview(), "B", "A")
    assert forward.links == backward.links == [Connection("A", 1, "B", 0)]
    assert (backward.object_a, backward.object_b) == ("B", "A")


def test_query_refusal_names_the_end_that_is_missing():
    """Нет объекта — отказ, и проверяются **оба** конца, а не первый из двух.

    Проверка только первого конца пропустила бы `("A", "нет_такого")` в пустой
    ответ: агент прочитал бы «связи нет» там, где объекта нет вовсе.
    """
    with pytest.raises(ValueError) as missing_second:
        query_connections(_overview(), "A", "нет_такого")
    assert "нет_такого" in str(missing_second.value)

    with pytest.raises(ValueError) as missing_first:
        query_connections(_overview(), "нет_такого", "A")
    text = str(missing_first.value)
    assert "нет_такого" in text
    assert "A" in text, f"отказ не перечисляет известные имена: {text}"


def test_query_without_links_is_not_an_error():
    """Отсутствие связи — обычное состояние модели, а не отказ.

    `C` в снимке — объект без портов: связей у него нет вовсе, и это ответ, а не
    повод отказать.
    """
    assert query_connections(_overview(), "A", "C").links == []
    assert query_connections(_overview(), "C", "C").links == []


def test_query_keeps_links_of_a_pair_apart_by_their_ports():
    """У пары объектов связей может быть несколько — и у каждой своя пара портов.

    Ответ называет каждую пару: «сосед» их не различил бы, и вопрос «через какие
    порты связаны эти двое» остался бы без ответа.
    """
    topology = Topology(
        objects=[ObjectRow("A", "Усилитель"), ObjectRow("B", "Константа")],
        ports=[PortRow("A", 0, "in", "x"), PortRow("A", 1, "out", "y"),
               PortRow("B", 0, "in", "x"), PortRow("B", 1, "out", "y")],
        # Порядок намеренно **не** совпадает с отсортированным по концам: иначе
        # тест проходил бы и на коде, который «нормализует» ответ сортировкой,
        # хотя обещан порядок разбора (`docs/api.md`). Проверено мутацией:
        # сортировка связей выживала на всём наборе, пока порядок здесь был
        # совпадающим.
        connections=[Connection("A", 1, "B", 0), Connection("A", 0, "B", 1)])
    overview = overview_from_topology(topology, ContainerRef.main())
    assert query_connections(overview, "A", "B").links == [
        Connection("A", 1, "B", 0), Connection("A", 0, "B", 1)]


def test_query_separates_a_self_link_from_links_with_others():
    """Связь объекта с самим собой спрашивается тем же вызовом — и не смешивается.

    «Связи `A`» включали бы и `A.0—A.1`, и `A.1—B.0`; вопрос про пару обязан
    отвечать на свою: иначе на вопрос «замкнут ли `A` на себя» приходил бы ответ
    со связями с соседями.
    """
    topology = Topology(
        objects=[ObjectRow("A", "Усилитель"), ObjectRow("B", "Константа")],
        ports=[PortRow("A", 0, "in", "x"), PortRow("A", 1, "out", "y"),
               PortRow("B", 0, "in", "x")],
        connections=[Connection("A", 0, "A", 1), Connection("A", 1, "B", 0)])
    overview = overview_from_topology(topology, ContainerRef.main())

    assert query_connections(overview, "A", "A").links == [
        Connection("A", 0, "A", 1)]
    assert query_connections(overview, "A", "B").links == [
        Connection("A", 1, "B", 0)]


def test_query_and_inspections_describe_the_same_links():
    """Запрос пары и досмотры называют **одни и те же** связи — в обе стороны.

    У каждой связи из ответа второй конец виден досмотром каждого из её концов, и
    наоборот: связи `A`, у которых второй конец `B`, — это ровно ответ запроса.
    Разойдись они, агент получал бы два описания одного отношения.
    """
    overview = _overview()
    query = query_connections(overview, "A", "B")
    assert query.links, "снимок соединён: ответ не может быть пустым"

    for link in query.links:
        from_a = inspect_port(overview, link.object_a, link.index_a).peers
        from_b = inspect_port(overview, link.object_b, link.index_b).peers
        assert PortPeer(link.index_a, link.object_b, link.index_b) in from_a
        assert PortPeer(link.index_b, link.object_a, link.index_a) in from_b

    expected = {connection_key(link)
                for link in overview.connections
                if {link.object_a, link.object_b} == {"A", "B"}}
    assert {connection_key(link) for link in query.links} == expected


def test_connection_query_to_dict_reuses_the_overview_connection_shape():
    """Связь в ответе на запрос — **тот же** словарь, что и в обзоре."""
    overview = _overview()
    as_dict = connection_query_to_dict(query_connections(overview, "A", "B"))
    assert as_dict == {
        "between": ["A", "B"],
        "connections": [{"a": ["A", 1], "b": ["B", 0]}],
    }
    assert as_dict["connections"] == overview_to_dict(overview)["connections"]
    assert json.loads(json.dumps(as_dict)) == as_dict
    # Пара в ответе — та, которую назвал вызывающий, и в том же порядке:
    # «B, A» не должен канонизироваться в «A, B», иначе ответ стирает вопрос.
    # Мутация «отсортировать пару» выживала, пока здесь был только один порядок.
    reversed_pair = connection_query_to_dict(query_connections(overview, "B", "A"))
    assert reversed_pair["between"] == ["B", "A"]
