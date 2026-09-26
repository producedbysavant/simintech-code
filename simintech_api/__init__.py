"""simintech_api — Python-библиотека управления SimInTech через COM API.

Быстрый старт (только Windows):
    from simintech_api import COMClient, Project

    client = COMClient(silent_mode=True).connect()
    # Проект — из шаблона: у `Project.new()` нет расчётного слоя, и модельное
    # время в нём не растёт, хотя вызовы сообщают об успехе.
    prj = Project.from_template(client).set_calc_end_time(10.0)
    page = prj.get_main_page()
    b1 = page.create_block("Константа", 0, 0)
    b2 = page.create_block("Усилитель", 200, 0)
    b1.connect(b2)
    prj.save_xml("model.xprt")
"""

from .core.com_client import COMClient
from .core.project import Project
from .core.page import Page
from .core.block import Block
from .core.port import Port
from .core.wire import Wire
from .core.signal import Signal
from .core.simulation import Simulation
from .core.script_bridge import ScriptBridge
from .core.pack import Pack
from .core.topology import read_topology
from .topology import Connection, ObjectRow, PortRow, Topology
from .constants import DataType, PortSide
from .exceptions import (
    BlockError,
    ComCallError,
    ComConnectionError,
    LayoutError,
    PageError,
    PackError,
    PortError,
    ProjectError,
    ScriptBridgeError,
    ScriptBridgeUnsafeStateError,
    SignalError,
    SimInTechError,
    SimulationError,
    TopologyError,
    UnsupportedBlockError,
    WireError,
)

__all__ = [
    "COMClient",
    "Project",
    "Page",
    "Block",
    "Port",
    "Wire",
    "Signal",
    "Simulation",
    "ScriptBridge",
    "Pack",
    "DataType",
    "PortSide",
    "SimInTechError",
    "ComConnectionError",
    "ComCallError",
    "ProjectError",
    "PageError",
    "PackError",
    "BlockError",
    "UnsupportedBlockError",
    "PortError",
    "WireError",
    "SignalError",
    "SimulationError",
    "LayoutError",
    "ScriptBridgeError",
    "ScriptBridgeUnsafeStateError",
    "TopologyError",
    "read_topology",
    "Topology",
    "ObjectRow",
    "PortRow",
    "Connection",
]

#: Источник истины для версии: `pyproject.toml` объявляет её динамической и
#: читает отсюда. Прописывать её ещё и там — значит однажды снова разойтись.
#:
#: 0.7.0: минорный — досмотр порта: `inspect_port`, `PortInspection`,
#: `port_inspection_to_dict` (`simintech_api.semantic`). Отвечает на вопрос «что
#: это за порт и с чем он связан»: сам порт и чужие концы его связей.
#: **Новых COM-вызовов нет** — проекция обзора. Адрес порта — пара (имя объекта,
#: индекс); отказы различают «нет объекта» и «у объекта нет такого порта».
#:
#: Направление связи слоем **не выводится**: «вход принимает, выход отдаёт» —
#: догадка, а концы `Connection` неориентированы. Соседей у порта может быть
#: сколько угодно — вендорская кратность даёт одного соседа только входному порту.
#:
#: 0.6.0: минорный — досмотр объекта: `inspect_object`, `ObjectInspection`,
#: `PortPeer`, `inspection_to_dict` (`simintech_api.semantic`). Отвечает на вопрос
#: «что это за объект и с чем он связан»: порты объекта с направлениями, счётчики
#: по направлениям и связи с соседями. **Новых COM-вызовов нет** — это проекция
#: уже прочитанного обзора, и спрашивать можно по любому объекту из него.
#:
#: Направление у соседа не называется: сосед описан **своим** концом связи
#: (`port_index` — наш порт), потому что концы `Connection` неориентированы, а
#: вендорская кратность делает направление ненадёжным признаком. Неизвестное имя
#: — отказ с перечнем известных, а не пустой ответ.
#:
#: 0.5.0: минорный — семантический слой модели: `read_model_overview`,
#: `ModelOverview`, `ObjectView`, `ContainerRef` (модули `simintech_api.semantic`
#: и `simintech_api.core.semantic`). Отвечает на вопрос «что представляет собой
#: эта модель и как она устроена»: объекты текущего контейнера с портами, связи
#: между ними и подпись области обзора в JSON-готовой форме.
#:
#: **Слой не делает собственных COM-вызовов** — он читает топологию тем же
#: `read_topology` и группирует её; это проверяется стражем в юнит-тестах, а не
#: обещанием в докстринге. Иерархия контейнеров в слой не входит: вложенность
#: измерена на одном уровне, `Page.parent()` — предположение, а перечисления
#: контейнеров в COM нет вовсе. Связи — тот же `Connection` топологии, то есть
#: «что с чем соединено», а не восстановление проводки.
#:
#: 0.4.0: минорный — добавлен публичный API топологии: `read_topology`,
#: `Topology`, `ObjectRow`, `PortRow`, `Connection`, `TopologyError`. Читает
#: объекты, порты и связи текущего контейнера через встроенный язык поверх
#: `ScriptBridge` — того, чего в COM нет: связности.
#:
#: Тем же выпуском исправлена потеря скрипта страницы в `ScriptBridge`: мост
#: опознаёт ту страницу, в которую сам писал (снимок скриптовых записей до и
#: после установки пробы; цель — единственная изменившаяся запись с уникальной
#: меткой), и возвращает прежний скрипт в неё. Раньше прежний скрипт читался с
#: главной страницы, поэтому чтение внутри контейнера стирало скрипт этого
#: контейнера — на демо вендора 939 символов вендорского скрипта экспорта
#: топологии превращались в пустоту при успешном чтении. Состояние «цель
#: установить не удалось» поднимает новый публичный тип
#: `ScriptBridgeUnsafeStateError`.
#:
#: **Одно удаление, и оно названо явно.** Убран метод
#: `ScriptBridge.capture_script` — публичный по видимости, но внутренний по
#: смыслу: он читал прежний скрипт с главной страницы, что и было дефектом.
#: Вместе с ним убран `script_probe.read_page_script` (из корня пакета не
#: экспортировался). По правилам 0.x удаление в минорном выпуске допустимо, но
#: вызывающему коду, который звал `capture_script`, вызов придётся убрать:
#: замены нет и быть не должно — надёжного способа прочитать *текущий* скрипт
#: страницы не существует.
#:
#: 0.3.0: минорный, а не патч — со времени 0.2.0 добавлены читатели `.tbl`/
#: `.pak`/`.dbconf`, разделение линий и блоков страницы, поддержка FSM и
#: маркер PEP 561. Тег `v0.2.0` указывал на код 0.1.0 (47 коммитов назад),
#: поэтому имя тега новее содержимого; этот выпуск ловушку снимает.
__version__ = "0.7.0"
