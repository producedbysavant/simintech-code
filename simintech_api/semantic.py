"""Семантический слой модели: что представляет собой модель и как она устроена.

Без COM и без файловой системы — как и `simintech_api/topology.py`, всё здесь
проверяется в CI. Слой **ничего не добавляет** к измеренному: он группирует
прочитанную топологию в объекты с портами и называет область обзора.

Контракт и границы — `docs/superpowers/specs/2026-09-24-semantic-model.md`.
Коротко: `connections` здесь — тот же `Connection` топологии, то есть отношение
«что с чем соединено», а не описание проводки; контейнер описывается путём,
которым его получили, потому что собственного идентификатора контейнера среда в
Python не отдаёт.
"""

from __future__ import annotations

from typing import Any, Dict, List, NamedTuple

from .topology import Connection, PortRow, Topology

#: Виды контейнера, которыми вызывающий может назвать область обзора.
CONTAINER_MAIN = "main"
CONTAINER_SUBMODEL = "submodel"
CONTAINER_KINDS = (CONTAINER_MAIN, CONTAINER_SUBMODEL)


def _refuse_unknown_container(kind: str) -> None:
    """Отказ на неизвестный вид контейнера — вместо тихой неверной подписи.

    Вид контейнера попадает в результат как подпись области обзора. Опечатка в
    нём дала бы правдоподобный на вид, но неверный ответ, а отличить его было бы
    нечем: данных о том, где мы находимся, у слоя нет.
    """
    if kind not in CONTAINER_KINDS:
        raise ValueError(
            f"неизвестный вид контейнера {kind!r}: допустимы "
            f"{', '.join(CONTAINER_KINDS)}")


class ContainerRef(NamedTuple):
    """Как получена страница, содержимое которой описывает обзор.

    Идентификатора контейнера у нас нет и быть не может: `getcurrentcontainer`
    и `getownercontainer` живут только **внутри тела пробы**, а COM-метода
    «какой контейнер текущий» в интерфейсе нет (измерено). Поэтому контейнер
    описывается **путём**: `main` — главная страница проекта, `submodel` —
    страница субмодели блока.

    Данные обзора при этом описывают тот контейнер, который текущий **по мнению
    среды**, и это доказано живыми тестами (`test_objects_match_com`,
    `test_probe_matches_vendor_reference_inside_container`). Значит, `ContainerRef`
    — утверждение вызывающего о том, куда он вошёл, а не то, что слой проверил
    сам: назвать здесь другой контейнер — единственный способ получить обзор с
    неверной подписью, и слою нечем это поймать.
    """

    kind: str
    block_id: int = 0
    block_name: str = ""

    @classmethod
    def main(cls) -> "ContainerRef":
        """Главная страница проекта."""
        return cls(kind=CONTAINER_MAIN)

    @classmethod
    def submodel(cls, block_id: int, block_name: str) -> "ContainerRef":
        """Страница субмодели блока; имя берёт вызывающий у блока.

        `block_id = 0` отвергается сразу: в COM ноль означает «блока нет», и
        такой ссылкой назвать контейнер нельзя. Отказ здесь лучше, чем обзор с
        подписью «субмодель блока 0».
        """
        if not block_id:
            raise ValueError(
                "субмодель адресуется блоком: block_id обязателен, но получен "
                f"{block_id!r}")
        return cls(kind=CONTAINER_SUBMODEL, block_id=block_id,
                   block_name=block_name)


class ObjectView(NamedTuple):
    """Объект модели: имя, класс и порты, в порядке протокола.

    Порты — те же `PortRow`, что и в топологии, без переупаковки: параллельный
    тип ради экономии поля `object_name` дал бы два описания одного и того же,
    которые разошлись бы молча. Поле `object_name` внутри объекта избыточно и
    сохраняется намеренно.
    """

    name: str
    class_name: str
    ports: List[PortRow]

    def _of(self, direction: str) -> int:
        return sum(1 for port in self.ports if port.direction == direction)

    @property
    def in_ports(self) -> int:
        return self._of("in")

    @property
    def out_ports(self) -> int:
        return self._of("out")

    @property
    def undirected_ports(self) -> int:
        return self._of("undirected")


class ModelOverview(NamedTuple):
    """Обзор одного контейнера: объекты с портами и связи между ними.

    `connections` — связи топологии **как есть**: разбор уже сложил их по
    каноническому ключу, и второй дедупликации здесь нет. Слой ничего не
    пересчитывает — иначе он стал бы вторым источником истины о связях.
    """

    container: ContainerRef
    objects: List[ObjectView]
    connections: List[Connection]

    @property
    def object_count(self) -> int:
        return len(self.objects)

    @property
    def port_count(self) -> int:
        return sum(len(obj.ports) for obj in self.objects)


def overview_from_topology(topology: Topology,
                           container: ContainerRef) -> ModelOverview:
    """Сгруппировать прочитанную топологию в обзор контейнера.

    Единственная работа, которую делает слой: разложить порты по объектам, к
    которым они относятся. Объекты идут в порядке протокола, порты — тоже, и
    объект без портов остаётся в обзоре: у настоящих модельных блоков портов
    может не быть, и пропажа такого объекта из обзора была бы потерей данных.
    """
    _refuse_unknown_container(container.kind)
    ports_by_object: Dict[str, List[PortRow]] = {}
    for port in topology.ports:
        ports_by_object.setdefault(port.object_name, []).append(port)
    objects = [ObjectView(name=row.name, class_name=row.class_name,
                          ports=ports_by_object.get(row.name, []))
               for row in topology.objects]
    return ModelOverview(container=container, objects=objects,
                         connections=list(topology.connections))


def _port_to_dict(port: PortRow) -> Dict[str, Any]:
    """Форма одного порта — одна на все ответы слоя.

    Порт встречается в обзоре, в досмотре объекта и в досмотре порта; разойдись
    эти формы, агент получал бы об одном порте разные представления в зависимости
    от того, каким вызовом спросил.
    """
    return {"index": port.index, "direction": port.direction, "name": port.name}


def _peer_to_dict(peer: PortPeer) -> Dict[str, Any]:
    """Форма чужого конца связи — без нашей стороны: она названа вызывающим."""
    return {"object": peer.peer_object, "index": peer.peer_index}


def _object_to_dict(obj: ObjectView) -> Dict[str, Any]:
    """Форма одного объекта в ответе — одна на обзор и на досмотр.

    Общая не ради экономии строк: разойдись эти две формы, агент получал бы об
    одном объекте два разных представления в зависимости от того, каким вызовом
    его спросили.
    """
    return {
        "name": obj.name,
        "class_name": obj.class_name,
        "ports": [_port_to_dict(port) for port in obj.ports],
        "counts": {
            "in": obj.in_ports,
            "out": obj.out_ports,
            "undirected": obj.undirected_ports,
        },
    }


def overview_to_dict(overview: ModelOverview) -> Dict[str, Any]:
    """JSON-готовая форма обзора — то, что отдаёт адаптер (MCP).

    Словарь, а не структуры: адаптер не должен знать ни COM, ни типов топологии,
    а форма ответа должна быть видна целиком в одном месте. `object_name` у
    портов не повторяется — внутри объекта он уже назван ключом.
    """
    return {
        "container": {
            "kind": overview.container.kind,
            "block_id": overview.container.block_id,
            "block_name": overview.container.block_name,
        },
        "summary": {
            "objects": overview.object_count,
            "ports": overview.port_count,
            "connections": len(overview.connections),
        },
        "objects": [_object_to_dict(obj) for obj in overview.objects],
        "connections": [
            {"a": [link.object_a, link.index_a],
             "b": [link.object_b, link.index_b]}
            for link in overview.connections
        ],
    }


class PortPeer(NamedTuple):
    """Чужой конец связи и наш порт, которым эта связь к нам пришла.

    Имена полей намеренно **не** «источник» и «приёмник»: концы связи
    неориентированы (`Connection`), поэтому «чужой» здесь — просто второй конец
    пары. `port_index` — наш порт, `peer_object`/`peer_index` — второй конец.
    """

    port_index: int
    peer_object: str
    peer_index: int


class ObjectInspection(NamedTuple):
    """Ответ на вопрос «что это за объект и с чем он связан».

    Объект — тот же `ObjectView` обзора, без переупаковки; соседи — проекция
    `connections`, а не отдельное отношение. Связь учитывается **один раз** на
    каждый свой порт, которым она пришла, — даже если с тем же соседом есть
    вторая связь другим портом.
    """

    object: ObjectView
    peers: List[PortPeer]


def _find_object(overview: ModelOverview, name: str) -> ObjectView:
    """Найти объект по имени — с отказом, который перечисляет известные имена.

    Поиск один на оба досмотра: иначе «нет такого объекта» звучало бы в них
    по-разному, а вызывающий сравнивал бы два текста вместо одного состояния.
    """
    found = next((obj for obj in overview.objects if obj.name == name), None)
    if found is None:
        known = ", ".join(obj.name for obj in overview.objects)
        raise ValueError(
            f"в обзоре контейнера нет объекта {name!r}; известные имена: "
            f"{known or '(обзор пуст)'}")
    return found


def _port_peers(overview: ModelOverview, object_name: str,
                index: int) -> List[PortPeer]:
    """Связи одного порта: чужие концы тех связей, где этот порт участвует.

    Одна связь даёт ровно одного соседа: разбор уже сложил связи по каноническому
    ключу, поэтому зеркальная запись не удвоит соседа. Связей у порта может быть
    **сколько угодно** — «один порт — одна связь» не предположение слоя, а
    наблюдаемое свойство конкретной модели (на входной порт вендорский экспортёр
    берёт одного соседа, на остальные — всех).
    """
    peers: List[PortPeer] = []
    for link in overview.connections:
        if (link.object_a, link.index_a) == (object_name, index):
            peers.append(PortPeer(index, link.object_b, link.index_b))
        elif (link.object_b, link.index_b) == (object_name, index):
            peers.append(PortPeer(index, link.object_a, link.index_a))
    return peers


def inspect_object(overview: ModelOverview, name: str) -> ObjectInspection:
    """Досмотр одного объекта обзора: его порты и связи с соседями.

    **Новых COM-вызовов не делает и файлов не читает**: всё, что здесь есть, уже
    прочитано в обзор. Объект ищется по имени — имя и есть адрес объекта в
    топологии (`ObjectRow.name`).

    Неизвестное имя — **отказ**, а не пустой ответ. «Такого объекта нет» и
    «объект есть, но связей у него нет» — разные состояния, и пустой результат
    их бы смешал; вызывающему пришлось бы отличать их по контексту, которого у
    него нет.
    """
    found = _find_object(overview, name)
    peers: List[PortPeer] = []
    for port in found.ports:
        peers.extend(_port_peers(overview, name, port.index))
    return ObjectInspection(object=found, peers=peers)


def inspection_to_dict(inspection: ObjectInspection) -> Dict[str, Any]:
    """JSON-готовая форма досмотра — тем же словарём объекта, что и в обзоре.

    У соседа названы обе стороны связи: наш порт (`port`) и второй конец
    (`peer`). Направления здесь нет и быть не может — связь неориентирована, а
    направление порта вызывающий видит в списке портов объекта.
    """
    return {
        "object": _object_to_dict(inspection.object),
        "peers": [
            {"port": peer.port_index, "peer": _peer_to_dict(peer)}
            for peer in inspection.peers
        ],
    }


class PortInspection(NamedTuple):
    """Ответ на вопрос «что это за порт и с чем он связан».

    Порт — тот же `PortRow`, что и в объекте, без переупаковки. Соседи — те же
    `PortPeer`, что у объекта, и считаются **тем же кодом** (`_port_peers`):
    иначе досмотр порта и досмотр объекта могли бы разойтись в описании одной и
    той же связи.
    """

    object_name: str
    port: PortRow
    peers: List[PortPeer]


def inspect_port(overview: ModelOverview, object_name: str,
                 index: int) -> PortInspection:
    """Досмотр одного порта: он сам и его связи.

    **Новых COM-вызовов не делает**: это проекция уже прочитанного обзора.

    Адрес порта — пара (имя объекта, индекс), а не имя: индекс и есть адрес в
    протоколе (`PortRow`). Отказы различают два разных состояния: объекта с таким
    именем нет в обзоре и объекта нет, а порта с таким индексом у него нет.
    Смешать их значило бы сказать «порта нет» там, где не хватает всего объекта.

    **Направление связи не выводится.** «Вход принимает, выход отдаёт» — догадка,
    которой слой не делает: концы связи неориентированы, а вендорская кратность
    (на входной порт идёт один сосед, на остальные — все) делает направление
    ненадёжным признаком. Поэтому соседи перечисляются как есть, а `direction`
    берётся только из данных порта.
    """
    obj = _find_object(overview, object_name)
    port = next((candidate for candidate in obj.ports if candidate.index == index),
                None)
    if port is None:
        known = ", ".join(str(candidate.index) for candidate in obj.ports)
        raise ValueError(
            f"у объекта {object_name!r} нет порта с индексом {index}; "
            f"известные индексы: {known or '(у объекта нет портов)'}")
    return PortInspection(object_name=object_name, port=port,
                          peers=_port_peers(overview, object_name, index))


def port_inspection_to_dict(inspection: PortInspection) -> Dict[str, Any]:
    """JSON-готовая форма досмотра порта.

    Соседи — плоский список чужих концов: своя сторона связи уже названа самим
    вызовом, и повторять её в каждом соседе значило бы обещать, что она у соседей
    разная.
    """
    return {
        "object": inspection.object_name,
        "port": _port_to_dict(inspection.port),
        "peers": [_peer_to_dict(peer) for peer in inspection.peers],
    }
