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

from .core.com_client import COMClient, SessionOwnership
from .core.project import Project
from .core.page import Page
from .core.block import Block
from .core.port import Port
from .core.wire import Wire
from .core.signal import Signal
from .core.simulation import Simulation
from .core.script_bridge import ScriptBridge, PageRunResult
from .core.pack import Pack
from .core.topology import read_topology
from .script_probe import (
    OUTCOME_ABORTED,
    OUTCOME_MODEL_NOT_RUNNING,
    OUTCOME_NOT_COMPILED,
    OUTCOME_OK,
    OUTCOME_SECTION_NOT_RUN,
    classify_page_result,
)
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
    "SessionOwnership",
    "Project",
    "Page",
    "Block",
    "Port",
    "Wire",
    "Signal",
    "Simulation",
    "ScriptBridge",
    "PageRunResult",
    "classify_page_result",
    "OUTCOME_OK",
    "OUTCOME_MODEL_NOT_RUNNING",
    "OUTCOME_ABORTED",
    "OUTCOME_NOT_COMPILED",
    "OUTCOME_SECTION_NOT_RUN",
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
#: 0.11.0: минорный — ownership COM-сессии и managed shutdown: `SessionOwnership`,
#: `COMClient.session_pid`, автоматическая очистка только OWNED PID с ожиданием
#: и exact-PID fallback. `SetShutdownOnLastRelease` намеренно не используется:
#: живой замер 02.10.2026 не подтвердил детерминированного завершения или
#: owner-death cleanup этого флага.
#:
#: 0.10.0: минорный — чтение скрипта страницы: `ScriptBridge.read_page_script`.
#: COM чтения скрипта не отдаёт (`GetPageScript` в интерфейсе нет), поэтому
#: страница опознаётся тем же снимком выгрузки, каким мост возвращает прежний
#: скрипт, — но **без запуска расчёта**: `ProjectStart` обнуляет модельное
#: время, и читающий инструмент уничтожал бы результаты расчёта вызывающего.
#:
#: 0.9.0: минорный — контур языкового слоя: `ScriptBridge.run_page_script`,
#: `PageRunResult`, пять исходов (`OUTCOME_*`) и классификатор
#: `classify_page_result`; тела операций — `model_operations`. Существующие
#: методы и тексты их отказов не изменились.
#:
#: Отличие от пробы — секция, в которой исполняется тело: `run_probe` идёт под
#: `if firststep then`, а этот режим — в `initialization`, потому что только
#: там разрешено создавать объекты. Неподвижное время здесь не отказ, а исход:
#: маркеры `CTX_*` пишет сам скрипт, и по ним «не собрался» отличается от
#: «модель не считает» — то, чего мост различить не мог. Уборка (остановка
#: расчёта, возврат прежнего скрипта, сверка снимков) — общая с пробой.
#:
#: 0.8.0: минорный — запрос связей пары: `query_connections`, `ConnectionQuery`,
#: `connection_query_to_dict` (`simintech_api.semantic`). Отвечает на вопрос
#: «какие связи идут между этими двумя объектами»: отбор по уже прочитанному
#: отношению, **новых COM-вызовов нет**.
#:
#: Отвечает **связями, а не соседями**: у каждой возвращённой связи названы оба
#: конца, поэтому между одними и теми же объектами видно каждую пару портов, а не
#: «ещё одного соседа». Адрес здесь — имя объекта, а не пара (имя, индекс):
#: индексы портов видны в самих связях. Отказы проверяют **оба** названных конца —
#: иначе «нет объекта» указывало бы на первый из двух, а про второй нельзя было бы
#: отличить «его нет» от «он есть, но связи нет». Отсутствие связи — не отказ, а
#: обычное состояние модели (`links == []`). Форма связи — та же, что в обзоре.
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
#:
#: 0.10.1: патч — фикс очистки временного каталога моста (#19), провенанс
#: записи реестра утверждений (#20). Выпуск закрепляется тегом `v0.10.1`:
#: на релизные теги (`v*`) ссылается пин `simintech-mcp`, а двигать и удалять
#: их не даёт ruleset `protect-release-tags`.
#: 0.12.0: минорный — job-объект (`KILL_ON_JOB_CLOSE`) над процессом
#: OWNED-сессии: смерть процесса-клиента снимает `mmain.exe` силами ядра
#: (`COMClient.job_handle`, `job_error`); `disconnect` остаётся отпусканием,
#: а не завершением. Замеры 02.10.2026 (назначение существующего
#: `-Embedding`-процесса; снятие ядром при смерти держателя, n=2).
__version__ = "0.12.0"
