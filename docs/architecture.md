# Архитектура simintech-api

Python-библиотека для управления SimInTech через COM API (`IMVTU_Server`, сервер `mmain.exe`, out-of-proc).

## Ключевые решения (по итогам исследования Фазы 1)

1. **COM-движок — comtypes** (не pywin32). Причина: `TDataDescriptor` — структура `VT_RECORD`; pywin32 ломает её marshalling. Проверено в `docs/reference/com_api_inventory.md`.
2. **Один интерфейс `IMVTU_Server`.** Карта — `docs/reference/com_api_inventory.md` (~198 строк-методов; в первой редакции измерений было 176, §18 доводит пять методов, найденных позже). Все результаты — через `[out]`-параметры, идентификаторы — `__int64` (VT_I8), строки `[in]` = BSTR.
3. **`TDataDescriptor{DataId: i64, DataType: long}`** — центральная структура: `Find*` возвращает по указателю, `Read*/Write*` принимают по значению. DataType: 0=double, 1=int, 2=bool, 4=string, 5=array(double[]), 12=intarray.
4. **Два механизма создания моделей**: COM API (`CreateBlock`, имя класса строкой) и встроенный язык SimInTech (`createblock`/`createmodel` — отдельный механизм для обхода неработающих классов). Резервный путь создания через макросы/`.inc` и `SetPageScript`.
5. **Трассировка опирается на `GetPortInfo`** — возвращает `X, Y, XGlobal, YGlobal` (координаты порта на схеме).
6. **Ограничение окружения**: COM работает только на Windows. Тесты: unit (моки) в любом окружении, integration (реальный COM) — маркер `@pytest.mark.integration`, запуск на Windows.

## Структура пакета

Актуализировано 2026-10-16 (аудит экосистемы): прежний список не знал половины
модулей — моста, топологии, реестра языка, каталога и форматов.

```
simintech_api/
├── __init__.py            # экспорт публичного API; __version__ — источник истины
├── constants.py           # DataType, PortMode, штатные размеры, UNSUPPORTED/FSM-записи
├── model.py               # TDataDescriptor (comtypes record), дата-классы
├── exceptions.py          # SimInTechError, ComCallError, ScriptBridgeError, TopologyError…
├── core/
│   ├── com_client.py      # COMClient: CreateObject, ownership, job-объект, shutdown
│   ├── project.py         # Project: new/open/from_template/save, слой расчёта, субмодели
│   ├── page.py            # Page: текущая страница, create_block, create_wire, get_wires
│   ├── block.py           # Block: props, position, ports, connect
│   ├── port.py            # Port: info (сторона, имя, координаты), set_side/name/mode
│   ├── wire.py            # Wire: normalize, branch (маршрут задаёт среда)
│   ├── signal.py          # Signal: read/write по DataType, массивы поэлементно
│   ├── simulation.py      # Simulation: start/run/step, run_to — опрос времени
│   ├── pack.py            # Pack: пакет проектов (PackStep и т.п.)
│   ├── script_bridge.py   # ScriptBridge: контур страницы, пять исходов, возврат скрипта
│   ├── topology.py        # read_topology поверх ScriptBridge (проба object/port/conn)
│   └── semantic.py        # read_model_overview: обзор поверх топологии
├── script_probe.py        # сборка/разбор скриптов и маркеров без COM
├── model_operations.py    # тела операций с текстом модели (выгрузка и сборка)
├── catalog.py             # каталог имён свойств: генератор, разбор .xprt, decode_xprt
├── catalog_tool.py        # CLI simintech-generate-catalog
├── language.py            # реестр функций встроенного языка из webhelp (схема 2)
├── layout/
│   ├── canon.py           # канон ТЗ 4.2–4.4: WIRE_PITCH/STUB/channel_width/cut_sizes
│   ├── grid.py            # ObstacleGrid: сетка с препятствиями
│   ├── placer.py          # LayeredPlacer: слои, каналы разреза, обратные связи
│   ├── repeat.py          # повторяющаяся ячейка (ТЗ 4.4)
│   └── router.py          # AStarRouter: расчётный путь (среда свой не принимает)
├── pak.py                 # пакет проектов .pak (разбор и запись текстом)
├── tbl.py                 # таблицы .tbl
├── sdb.py                 # база сигналов (XML через defusedxml)
├── dbconf.py              # .dbconf/.dblocalconf — роль узла в сетевом расчёте
├── csl_library.py         # индекс палитры .csl
├── cli_runner.py          # путь командной строки mmain.exe (резерв без COM)
├── cli.py                 # CLI-интерфейс (Фаза 5)
├── agent.py               # SimInTechAgent: текстовые команды (Фаза 5)
├── semantic.py            # обзор модели поверх топологии (без своих COM-вызовов)
└── utils/
    ├── converters.py      # значения <-> строки свойств, разбор Points
    ├── job_object.py      # KILL_ON_JOB_CLOSE над процессом OWNED-сессии
    ├── processes.py       # снимки PID mmain (wmic/tasklist/powershell)
    ├── logger.py          # PipeLogger: канал лога сервера
    └── xprt_signals.py    # имена блоков из .xprt (кандидаты в сигналы)
```

## Потоки данных

### Подключение
```
COMClient(silent=True) → comtypes.CreateObject(MVTU_Server) → SetSilentMode(1) → SetNoCloseAppFlag(1)
```

### Создание модели (схема)
```
Project.from_template() → get_main_page() → Page.create_block("Усилитель", x, y)
  → InitBlock → SetBlockProp("a", "2") → SetBlockPosition(...)
Page.create_wire(port_out, port_in) → CreateWire(...PointCount=0) → NormalizeWire
```

Создаётся именно `from_template`, а не `Project.new()`: у последнего нет
моделирующего слоя, и модельное время в таком проекте не растёт.

### Сборка модели вручную (для агента)
```
SimInTechAgent.build_spec(spec) → LayeredPlacer.place(граф) → for each block: create + position
  → Page.create_wire(port, port) → NormalizeWire
```

Маршрут линии выбирает SimInTech, поэтому `AStarRouter` в сборке не
участвует: передать ему свои опорные точки нечем (`SetWirePoint` маршрутом не
управляет — `docs/reference/com_api_inventory.md` §6).

### Расчёт и сигналы
```
Project.run() → FindSignalData(name, prj, &desc) → read/write по desc.DataType
```

## Layout (Placer)

Sugiyama-подобный layered-алгоритм:
1. Ранжирование: блоки без входов → слой 0; далее N+1 по правилу «все входы из слоёв ≤ N, хотя бы один из N».
2. Упорядочивание внутри слоя: медианная эвристика (минимизация пересечений).
3. Координаты: X по слою, Y с равными промежутками, учёт размеров (ширина/высота из GetBlockPropAsString "Points" или дефолт).
4. Постобработка: компактизация.

## Router (A*)

1. Сетка с шагом 20 px; ячейки блоков = препятствия.
2. A* с манхэттенской метрикой, штраф за повороты.
3. Сглаживание (удаление коллинеарных точек), отступы от блоков.
4. Особые случаи: порты на одной линии → прямое соединение без точек.
   Ветвления здесь нет: `ParentWire` — функция встроенного языка, а не часть
   раскладчика (уточнено 16.10.2026). Фактическую форму линии задаёт SimInTech
   (`NormalizeWire`), поэтому маршруты `router.py` — расчётный путь, не то,
   что нарисует среда.

## Тестирование

- `tests/unit/` — layout (placer, router), конвертеры, COMClient с фейковым сервером (mock). Запуск: `pytest -m "not integration"`.
- `tests/integration/` — реальный COM на Windows: lifecycle проекта, создание блоков, линий, сигналы, расчёт, сборка модели SinSource→Gain. Запуск: `pytest -m integration` (требует зарегистрированный `mmain.exe /regserver`).
