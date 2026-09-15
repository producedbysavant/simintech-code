
> **Для разработчиков тулкита.** Этот файл содержит внутреннюю техническую информацию и не требуется для повседневного использования тулкита.

# COM API SimInTech: полный справочник методов IMVTU_Server

Официальная справка: [API SimInTech](https://help.simintech.ru/27_SimInTech_api/DIR_api.html),
[Командная строка](https://help.simintech.ru/27_SimInTech_api/DIR_komandnaya_stroka.html).

Источник: `mmain.hpp` (MIDL), `SIT COM DEMO.cpp`, эксплуатация через comtypes.
CLSID: `{ACE730D7-1712-4C70-87C8-7E4C55622E91}`
IID: `{145848B3-2BE8-4497-9A6B-8A42DA658844}`

Статусы: ✅ проверено на практике, ➖ проверено частично, ❓ не проверено.

---

## 1. Управление проектами

| Метод | Сигнатура | Статус | Описание |
|-------|-----------|--------|----------|
| `GetProjectCount` | `() → long` | ✅ | Количество открытых проектов |
| `GetProjectIdByNumber` | `(long PrjNumber) → __int64` | ✅ | ID проекта по индексу (0-based) |
| `GetProjectIdByFileName` | `(BSTR PrjFileName) → __int64` | ✅ | ID проекта по имени файла |
| `OpenProject` | `(BSTR PrjFileName) → __int64` | ✅ | Открыть .prt/.xprt файл |
| `CloseProject` | `(__int64 ProjectId)` | ✅ | Закрыть проект |
| `GetActiveProject` | `() → __int64` | ✅ | ID активного проекта |
| `NewProject` | `() → __int64` | ✅ | Создать новый пустой проект. **В нём нет расчётного слоя — не считает, см. §18** |
| `OpenTemplate` | `(BSTR TemplateName) → __int64` | ✅ | Создать проект из шаблона; нужен полный путь к `.prt` (см. §18) |
| `GetOpenedFileName` | `(__int64 ProjectId) → BSTR` | ✅ | Путь к открытому файлу проекта |

---

## 2. Управление симуляцией (ядро тест-раннера)

| Метод | Сигнатура | Статус | Описание |
|-------|-----------|--------|----------|
| `ProjectStart` | `(__int64 ProjectId)` | ✅ | Активировать солвер (обязательно перед Run/Step) |
| `ProjectRun` | `(__int64 ProjectId)` | ✅ | Запустить симуляцию (неблокирующий) |
| `ProjectStop` | `(__int64 ProjectId)` | ✅ | Остановить симуляцию |
| `ProjectPause` | `(__int64 ProjectId)` | ✅ | Поставить на паузу |
| `ProjectStep` | `(__int64 ProjectId)` | ✅ | Один шаг (~0.001 ед. времени) |
| `RunTo` | `(__int64 ProjectId, double TargetTime) → __int64` | ✅ | Запустить до target time. **Не блокирующий** — см. ниже |
| `WaitForTime` | `(__int64 ProjectId, double TargetTime) → __int64` | ➖ | Ожидать target time во время Run. В этой сборке возвращает 0 немедленно |
| `GetProjectTime` | `(__int64 ProjectId) → double` | ✅ | Текущее модельное время |

**Порядок:** `ProjectStart` → `ProjectRun` (или `RunTo`, или `ProjectStep`) → `ProjectStop`

**`RunTo` не блокирует.** Проверено на SimInTech64 (2026-09-15): сразу после
`RunTo(0.5)` модельное время 0.240 с, через мгновение — уже 0.5 с. Код возврата
не означает достижения цели, а `WaitForTime` в этой сборке возвращает 0
немедленно и фактически не ждёт. Достижение подтверждается **только** опросом
`GetProjectTime` — так делает `Simulation.run_to` (библиотека) и `run` (MCP).

**`ProjectStep` — около 0.001 ед. времени за шаг** (измерено на проекте из
шаблона: 0.001, 0.002, … после пяти шагов).

---

## 3. Доступ к сигналам (основной способ обмена данными)

| Метод | Сигнатура | Статус | Описание |
|-------|-----------|--------|----------|
| `FindSignalData` | `(BSTR SignalName, __int64 ProjectId) → TDataDescriptor` | ✅ | Найти сигнал по имени (внешние/внутренние) |
| `FindProjectData` | `(BSTR DataName, __int64 ProjectId, long AccesForWrite) → TDataDescriptor` | ➖ | Поиск данных проекта (сложные имена, см. тесты) |
| `ReadAsFloat` | `(TDataDescriptor) → double` | ✅ | Чтение double-значения сигнала |
| `ReadAsInteger` | `(TDataDescriptor) → __int64` | ➖ | Чтение целого значения |
| `ReadAsString` | `(TDataDescriptor) → BSTR` | ➖ | Чтение строкового значения |
| `WriteAsFloat` | `(TDataDescriptor, double)` | ✅ | Запись double-значения сигнала |
| `WriteAsInteger` | `(TDataDescriptor, __int64)` | ➖ | Запись целого значения |
| `WriteAsString` | `(TDataDescriptor, BSTR)` | ➖ | Запись строки |

### Работа с массивами

| Метод | Сигнатура | Статус | Описание |
|-------|-----------|--------|----------|
| `GetArrayCount` | `(TDataDescriptor) → long` | ✅ | Размер массива |
| `GetExtArrayElement` | `(TDataDescriptor, long Index) → double` | ✅ | Чтение элемента double-массива |
| `GetIntArrayElement` | `(TDataDescriptor, long Index) → __int64` | ➖ | Чтение элемента int-массива |
| `SetExtArrayElement` | `(TDataDescriptor, long Index, double)` | ➖ | Запись элемента double-массива (нужен desc) |
| `SetIntArrayElement` | `(TDataDescriptor, long Index, __int64)` | ➖ | Запись элемента int-массива (нужен desc) |
| `SetArrayCount` | `(TDataDescriptor, long Count)` | ➖ | Изменить размер массива (нужен desc) |

### Типы данных сигналов (DataType в TDataDescriptor)

| Код | Тип | Описание |
|-----|-----|----------|
| 0 | double | Вещественное число |
| 1 | integer | Целое 64-bit |
| 2 | boolean | Логическое |
| 4 | string | Строка |
| 5 | array | Массив double (out_0..out_14) |
| 12 | intarray | Массив integer |

**TDataDescriptor** - структура `{ __int64 DataId; long DataType; }` с UUID `9A591BFF-874A-4801-9C62-4B91C4C098F5` (VT_RECORD). Требует **comtypes** для корректного marshalling - pywin32 ломает VT_RECORD.

---

## 4. Списки сигналов (обнаружение всех сигналов проекта)

| Метод | Сигнатура | Статус | Описание |
|-------|-----------|--------|----------|
| `GetProjectSignalList` | `(__int64 ProjectId) → SAFEARRAY(__int64)` | ⚠️ | Список сигналов проекта. **Не работает под Wine** (SAFEARRAY не маршалится). Workaround: XPRT-парсер. |
| `GetPackSignalList` | `(__int64 PackId) → __int64` | ✅ | Список сигналов пака |
| `GetListCount` | `(__int64 ListId) → __int64` | ➖ | Количество элементов в списке |
| `GetDataInfoFromList` | `(__int64 ListId, long ElementNumber) → (name, caption, desc)` | ➖ | Информация об элементе |
| `FindDataInListByName` | `(__int64 ListId, BSTR Name) → long` | ➖ | Поиск индекса по имени |

**Примечание:** `GetProjectSignalList` требует comtypes (с pywin32 не работают вызовы с возвратом __int64).

---

## 5. Управление блоками

| Метод | Сигнатура | Статус | Описание |
|-------|-----------|--------|----------|
| `CreateBlock` | `(__int64 ProjectId, long LayerNo, __int64 ParentBlock, BSTR LibRecordName) → __int64` | ✅ | Создать блок по имени класса |
| `SetBlockPosition` | `(__int64 BlockId, double Left, double Top, double W, double H, double Angle)` | ➖ | Позиционирование блока |
| `SetBlockProp` | `(__int64 BlockId, BSTR PropName, BSTR StrValue)` | ✅ | Установка свойства (все значения - строкой!) |
| `GetBlockPropAsString` | `(__int64 BlockId, BSTR PropName) → BSTR` | ✅ | Чтение свойства блока |
| `GetBlockPluginName` | `(__int64 BlockId) → BSTR` | ➖ | Имя плагина блока (сигнатура: нужен BlockId) |
| `GetBlockCalcTemplate` | `(__int64 BlockId) → BSTR` | ➖ | Шаблон расчёта (сигнатура: нужен BlockId) |
| `SetGraphBlockProp` | `(__int64 BlockId, BSTR PropName, BSTR StrValue)` | ✅ | Установка графического свойства |
| `GetPropHandle` | `(__int64 BlockId, BSTR PropName) → __int64` | ✅ | Handle свойства |
| `GetGraphPropHandle` | `(__int64 BlockId, BSTR PropName) → __int64` | ✅ | Handle графического свойства |
| `GetBlockEngine` | `(__int64 BlockId) → __int64` | ✅ | ID движка блока |
| `InitBlock` | `(__int64 BlockId)` | ✅ | Переинициализация блока |
| `BlockAfterEdit` | `(__int64 BlockId)` | ✅ | Сигнал редактору о изменении |
| `ExecutePropScript` | `(__int64 BlockId, __int64 DataId)` | ✅ | Выполнить скрипт свойства |
| `GetPageObjectCount` | `(__int64 ProjectId) → long` | ✅ | Количество объектов на странице |
| `GetPageBlockId` | `(__int64 ProjectId, long BlockIndex) → __int64` | ✅ | ID блока по индексу |

**Размер блока задавать нельзя — его надо читать у блока.** Проверено на
SimInTech64 (2026-09-15). `SetBlockPosition` задаёт размер **явно**, вместе с
положением: переместить блок, не трогая размер, одним вызовом нельзя, поэтому
незаданные W/H надо брать у самого блока и возвращать их же.

Читаются размеры свойствами `GetBlockPropAsString(BlockId, "Width")` и
`"Height"` — строкой (`'32'`, `'16'`). Отдельного `GetBlockPosition` в API нет,
а `x`, `y`, `Left`, `Top`, `w`, `h` в качестве свойств **не читаются** (пусто),
и их установка — молчаливый no-op: `SetBlockProp("x", …)` принимается без
ошибки и ничего не делает.

**`CreateBlock` создаёт блок 60x40 — это не штатный размер.** Замерено на 20+
эталонных моделях поставки и папки «Модели SimInTech» (2026-09-15):

| Класс | Штатный размер |
|---|---|
| `Константа` | 32x16 (31 модель; один раз 40x20) |
| `Усилитель` | 32x32 (30 моделей) |
| `Интегратор` | 32x32 (15) |
| `Сумматор` | 32x32 при двух входах, 32x48 при трёх (11 и 10) |
| `Ступенька`, `Синусоида` | 32x32 |
| `Временной график` | 48x32 и 48x48 |

Блок нестандартного размера — нарушение правил разработки SimInTech, поэтому
размер выставляется при создании по таблице `constants.STANDARD_BLOCK_SIZES`
(`standard_block_size(class_name, in_ports)`). Обёртки: `Block.get_size()`,
`Page.create_block`; `set_position`/`set_center` сохраняют размер сами.

**Библиотека «Конечные автоматы» через COM не создаётся.** Проверено на
SimInTech64 (2026-09-15): `CreateBlock` вернул 0 для всех восьми классов —
`Карта состояний конечного автомата`, `Состояние автомата`, `Вход состояния`,
`Выход состояния`, `Выдержка состояния`, `Переменная выдержка состояния`,
`Выход данных состояния`, `Селектор данных состояния`,
`Флаг входа в состояние`. Передача `ParentBlock` (карта состояний как
родитель) тоже не помогает, как и внутренние имена вроде `State`, `FSM`,
`StateMachine`, `Условие перехода`. Эти классы внесены в
`constants.UNSUPPORTED_COM_BLOCK_CLASSES`, попытка создания даёт понятный
отказ, а не нулевой id.

Причина: блоки автоматов **встроены в сам редактор** (`mmain.exe`), а не
лежат данными. Строки `Состояние автомата` нет ни в одном файле поставки: ни
в каталоге включаемых моделей `bin/include_mvtu` (1125 `.prt` + 97 `.inc`;
`.prt` сжаты zlib — обычный `grep` по ним не работает), ни в библиотечных
`.db`. Свойств `state_cod`/`isstartstate`/`condition_cod` нет и у создаваемых
классов (`Константа`, `Язык программирования`, `Порт входа`, `Временной
график`), а `SetBlockProp("state_cod", …)` — молчаливый no-op.

Что известно о самом механизме — из `bin/include_mvtu/fsm.inc` (генератор кода
автомата, текст UTF-8+BOM): «состояние» — объект со свойством `state_cod`,
`state_num` — его индекс, `isstartstate` — стартовое состояние, `init_cod` —
код входа, у условия перехода — `condition_cod`; скрипт висит на блоке-карте
на хуках `beforecompile`/`formattext` и генерирует `switch(new_state)` с
переменными `curent_state`, `old_state`, `fsm_iter_count`, `storestates`.

Практические пути без COM-создания этих блоков: (1) собрать автомат из
доступных блоков — рецепт ниже; (2) загрузить **готовую** модель автомата,
сохранённую из GUI, в блок через `LoadSubmodel`; (3) скриптовый блок
(«Язык программирования» создаётся) с логикой автомата на встроенном языке.

Автомат собирается из доступных блоков. Проверенный рецепт для перехода
`1 → 2 → 3 → 1` по времени:

* `Константа a=[1]` — начальное состояние;
* `Ступенька t=[1], y0=[0], yk=[1]` — переход в состояние 2 на 1 с;
* `Ступенька t=[2], y0=[0], yk=[1]` — переход в состояние 3 на 2 с;
* `Ступенька t=[3], y0=[0], yk=[-2]` — возврат в состояние 1 на 3 с;
* `Сумматор` с четырьмя входами (`in_ports=4`, `a=[1 , 1 , 1 , 1]`) — значение
  состояния, оно же пишется «В файл».

Траектория из файла результата (шаг 0.25 с): 1 до 1 с, 2 до 2 с, 3 до 3 с,
с 3 с — снова 1. Для более длинного цикла нужен повторный запуск (рестарт),
поскольку блоков памяти предметной области через COM нет.

### Имена классов для CreateBlock (подтверждённые)

| Имя класса | Описание |
|------------|----------|
| `Константа` | Блок-константа (свойство "a") |
| `Язык программирования` | Блок-скрипт (свойство "Code") |
| `Порт выхода` | Output port block |
| `Сумматор` | Сумматор |
| `Передаточная функция` | Передаточная ф-я (Laplace) |
| `Demultiplexor_vec` | Демультиплексор (разбивка шины) |

### Подтверждённые свойства блоков

| Свойство | Блок | Описание |
|----------|------|----------|
| `name` | Любой | Имя блока |
| `a` | Константа | Значение константы (строка!) |
| `Code` | Язык программирования | Текст скрипта Pascal |
| `Color` | Любой | Цвет блока (int → PASS/FAIL: 65280=зелёный, 255=красный) |
| `value` | Порт выхода | Выходное значение (double) |
| `x` | Любой | Координата X |
| `y` | Любой | Координата Y |

---

## 6. Порты и соединения

| Метод | Сигнатура | Статус | Описание |
|-------|-----------|--------|----------|
| `GetInPort` | `(__int64 BlockId, long InNo) → __int64` | ✅ | Получить входной порт по номеру |
| `GetOutPort` | `(__int64 BlockId, long OutNo) → __int64` | ✅ | Получить выходной порт по номеру |
| `GetPortCount` | `(__int64 BlockId) → long` | ✅ | Количество портов блока |
| `SetPortCount` | `(__int64 BlockId, long Count, long DefaultMode, long DefaultType, long DefaultSide)` | ✅ | Изменить количество портов |
| `SetCondPortCount` | `(...)` | ➖ | Условное количество портов |
| `GetPortInfo` | `(__int64 PortId) → (Name, Side, Mode, TypeId, ItemId, ...)` | ✅ | Полная информация о порте (12 полей) |
| `GetBlockPort` | `(__int64 BlockId, long Index) → __int64` | ✅ | Порт блока по индексу |
| `SetPortSide` | `(__int64 PortId, long Side)` | ✅ | Сторона порта (left/right/top/bottom) |
| `SetPortInverse` | `(__int64 PortId, long Inverse)` | ✅ | Инвертировать порт |
| `SetPortItemId` | `(__int64 PortId, long ItemId)` | ✅ | ID элемента порта |
| `SetPortMode` | `(__int64 PortId, long Mode)` | ✅ | Режим порта |
| `SetPortName` | `(__int64 PortId, BSTR PortName)` | ✅ | Имя порта |
| `SetPortLineTypeId` | `(__int64 PortId, long LineTypeId)` | ✅ | Тип линии порта |
| `SetPortInvisible` | `(__int64 PortId, long Invisible)` | ✅ | Скрыть порт |
| `CreateWire` | `(__int64 ProjectId, long LayerNo, long WireType, ...) → __int64` | ✅ | Создать провод между портами |
| `SetWirePoint` | `(__int64 WireId, long PointNo, double X, double Y)` | ✅ | Точка излома провода |
| `NormalizeWire` | `(__int64 WireId)` | ✅ | Нормализовать провод |

**Геометрию линии задаёт SimInTech, а не вызывающий.** Проверено на
SimInTech64 (2026-09-15). Свежесозданная линия идёт **по прямой между портами**
— то есть по диагонали, если блоки стоят на разной высоте. `NormalizeWire`
ломает её на ортогональные участки, но маршрут выбирает сам: поворот делается
примерно на середине между портами, препятствия не учитываются вовсе. Если
середина попадает на блок, линия пройдёт **сквозь** него; если считать
маршрут по несобранной схеме (блоки ещё в (0,0) друг на друге), в геометрии
остаются точки вида `(-160,-1056)` за пределами схемы, и повторная
нормализация их уже не убирает.

`SetWirePoint` маршрутом **не управляет**: на линии без размеченных точек он
не даёт ничего (нормализация его игнорирует), а на размеченной — вставляет
точку в ломаную, из-за чего она идёт назад (зигзаг). Способа задать свои
изломы в API нет.

Практический вывод: чистая схема получается **расстановкой** блоков — источник
с единственным приёмником надо ставить вплотную к приёмнику, тогда середина
маршрута попадает в свободный коридор (`LayeredPlacer` это делает сам).
`NormalizeWire` всегда возвращает 0 и на неверном `WireId` не отказывает:
проверить результат можно только по геометрии в файле. Построение обёрток:
`Wire.normalize()`, порядок — `RepaintEditor` (см. §7), затем нормализация.

---

## 7. Страницы и субмодели

| Метод | Сигнатура | Статус | Описание |
|-------|-----------|--------|----------|
| `GetMainPage` | `(__int64 ProjectId) → __int64` | ✅ | ID главной страницы |
| `SetCurrentPage` | `(__int64 ProjectId, __int64 PageId)` | ✅ | Активировать страницу (нужно для доступа к блокам) |
| `GetCurentPage` | `(__int64 ProjectId) → __int64` | ➖ | ID текущей страницы |
| `GetSubmodelPage` | `(__int64 BlockId) → __int64` | ✅ | Страница субмодели (внутрь Macro_2) |
| `PageUp` | `(__int64 PageId) → __int64` | ✅ | Родительская страница |
| `LoadSubmodel` | `(__int64 BlockId, BSTR FileName)` | ✅ | Загрузить субмодель в блок |
| `AssignSubmodel` | `(__int64 ProjectId, __int64 BlockId, BSTR FileName)` | ✅ | Назначить субмодель |
| `SaveProjectBinary` | `(__int64 PrjId, BSTR FileName)` | ✅ | Сохранить как .prt |
| `SaveProjectXML` | `(__int64 PrjId, BSTR FileName)` | ✅ | Сохранить как XML (для отладки) |
| `SetPageScript` | `(__int64 ProjectId, BSTR Script, long CompileNow)` | ✅ | Скрипт страницы |
| `SetPageWindow` | `(__int64 PageId, Left, Top, Width, Height)` | ✅ | Окно страницы |
| `SetPageCoords` | `(__int64 PageId, double X, double Y, double Scale)` | ✅ | Координаты страницы |
| `ShowAllBlocks` | `(__int64 ProjectId)` | ✅ | Показать все блоки |
| `RepaintEditor` | `(__int64 ProjectId)` | ✅ | Перерисовать редактор |
| `ClearProjectActions` | `(__int64 ProjectId)` | ✅ | Очистить действия |

**Порядок «переместить блоки → перерисовать → трассировать» обязателен.**
Проверено на SimInTech64 (2026-09-15). `Block.set_center` переносит блок и его
порты (координаты портов в файле обновляются сразу), но **внутренние
прямоугольники, по которым SimInTech прокладывает провода, обновляются только
при перерисовке**. Если сразу после расстановки позвать `NormalizeWire`,
маршрут строится в обход блоков на прежних местах — в геометрии остаются
точки вида ``(-160,-1056)``, уходящие далеко за пределы схемы, и линия
остаётся кривой: повторная нормализация их уже не убирает. С
`RepaintEditor(ProjectId)` те же линии получаются ортогональными.

`BlockAfterEdit` для каждого блока это **не** заменяет — проверено, геометрия
остаётся сломанной. Обёртки: `Project.repaint()`, `Wire.normalize()`.
Отдельно: `NormalizeWire` всегда возвращает 0 и на неверном `WireId` не
отказывает — проверить результат из API нельзя, только по геометрии в файле.

---

## 8. Pack (многопроектный режим)

| Метод | Сигнатура | Статус | Описание |
|-------|-----------|--------|----------|
| `GetPackCount` | `() → long` | ✅ | Количество открытых паков |
| `GetPackId` | `(long PackNumber) → __int64` | ✅ | ID пака по индексу |
| `GetPackIdByFileName` | `(BSTR PackFileName) → __int64` | ✅ | ID пака по имени |
| `OpenPack` | `(BSTR FileName) → __int64` | ✅ | Открыть .pak файл |
| `ClosePack` | `(__int64 PackId)` | ✅ | Закрыть пак |
| `FindPackSignal` | `(__int64 PackId, BSTR SignalName) → TDataDescriptor` | ✅ | Найти сигнал в паке |
| `PackStart` | `(__int64 PackId)` | ✅ | Старт всех проектов пака |
| `PackRun` | `(__int64 PackId)` | ✅ | Запуск всех проектов |
| `PackPause` | `(__int64 PackId)` | ✅ | Пауза всех проектов |
| `PackStop` | `(__int64 PackId)` | ✅ | Остановка всех проектов |
| `PackStep` | `(__int64 PackId)` | ✅ | Один шаг всех проектов |
| `RunToPack` | `(__int64 PackId, double TargetTime)` | ✅ | RunTo для пака |
| `WaitForTimePack` | `(__int64 PackId, double TargetTime)` | ✅ | WaitForTime для пака |
| `SetRealTimeDelayPack` | `(__int64 PackId, long Flag, double Scale)` | ✅ | Синхронизация с реальным временем |
| `PackGetProjCount` | `(__int64 PackId) → long` | ✅ | Количество проектов в паке |
| `PackGetProjectIdByIndex` | `(__int64 PackId, long Index) → __int64` | ✅ | ID проекта по индексу |

---

## 9. Exchange File (файловый обмен данными)

| Метод | Сигнатура | Статус | Описание |
|-------|-----------|--------|----------|
| `OpenExchangeFile` | `(TExchangeMethod, BSTR FileName) → __int64` | ✅ | Открыть файл обмена |
| `CloseExchangeFile` | `(__int64 EngineId)` | ➖ | Закрыть файл обмена (type issue под Wine) |
| `AddToReadList` | `(TDataDescriptor)` | ➖ | Добавить в список чтения |
| `AddToWriteList` | `(TDataDescriptor)` | ➖ | Добавить в список записи |
| `ClearReadList` | `()` | ✅ | Очистить список чтения |
| `ClearWriteList` | `()` | ✅ | Очистить список записи |
| `ReadList` | `(__int64 EngineId)` | ✅ | Выполнить чтение |
| `WriteList` | `(__int64 EngineId)` | ✅ | Выполнить запись |
| `Read` | `(THandleArray, __int64 EngineId)` | ➖ | Чтение через handle-массив (type issue под Wine) |
| `Write` | `(THandleArray, __int64 EngineId)` | ➖ | Запись через handle-массив (type issue под Wine) |

TExchangeMethod: `exmFile = 0`, `exmMemMapFile = 1`

---

## 10. Управление формой/окном

| Метод | Сигнатура | Статус | Описание |
|-------|-----------|--------|----------|
| `FormShow` | `(__int64 ProjectId)` | ✅ | Показать форму |
| `FormHide` | `(__int64 ProjectId)` | ✅ | Скрыть форму |
| `FormBringToFront` | `(__int64 ProjectId)` | ✅ | На передний план |
| `FormSendToBack` | `(__int64 ProjectId)` | ✅ | На задний план |
| `GetFormVisible` | `(__int64 ProjectId) → long` | ➖ | Видимость формы (нужен ProjectId, не `()`) |
| `GetFormState` | `(__int64 ProjectId) → long` | ➖ | Состояние формы (нужен ProjectId) |
| `SetFormState` | `(__int64 ProjectId, long Value)` | ✅ | Установить состояние |
| `GetFormHandle` | `(__int64 ProjectId) → __int64` | ➖ | HWND формы (нужен ProjectId) |
| `GetFormCoords` | `(__int64 ProjectId) → (Left, Top, Right, Bottom, Xcenter, Ycenter, Scale)` | ➖ | Координаты формы (нужен ProjectId) |
| `SetFormCoords` | `(__int64 ProjectId, ...)` | ➖ | Установить координаты (есть Flags) |
| `GetFormStyle` | `(__int64 ProjectId) → long` | ➖ | Стиль формы (нужен ProjectId) |
| `SetFormStyle` | `(__int64 ProjectId, long Value)` | ✅ | Установить стиль |
| `GetFormBorderStyle` | `(__int64 ProjectId) → long` | ➖ | Стиль рамки (нужен ProjectId) |
| `SetFormBorderStyle` | `(__int64 ProjectId, long Value)` | ✅ | Установить стиль рамки |
| `SetFormCaption` | `(__int64 ProjectId, BSTR ACaption)` | ✅ | Заголовок формы |
| `SetGraphicView` | `(__int64 ProjectId, long Left, ...)` | ➖ | Графическое отображение |
| `SetMainFormVisible` | `(long Value)` | ✅ | Видимость главного окна |

**`FormShow` нужен перед сохранением, иначе проект «не открывается» в GUI.**
Проверено на SimInTech64 (2026-09-15). Состояние окна хранится в самом
проекте — в шапке файла это ``<visible>`` внутри `<Header><project>`. Сессия,
работающая через COM, формы не показывает, поэтому в сохранённый файл уходит
``<visible>0</visible>``. Файл при этом рабочий: `OpenProject` его открывает и
модель считается — но **GUI восстанавливает сохранённое состояние окна и
оставляет окно модели скрытым**. Пользователь видит пустую рамку SimInTech и
сообщает, что проект не открылся.

`FormShow(ProjectId)` переводит флаг в 1, и файл открывается как обычно.
Касается и `.prt`, и `.xprt` — проверено правкой одного `<visible>` в XML.
`SetFormState(pid, 1)` флаг **не** меняет (и окна не показывает),
`SetMainFormVisible(1)` — тоже. `FormShow` показывает окно на машине с
COM-сервером: для безоконного сохранения вызов можно пропустить, но тогда
файл в GUI не покажется. Обёртка — `Project.show_form()`.

---

## 11. Рестарт (checkpoint/restore)

| Метод | Сигнатура | Статус | Описание |
|-------|-----------|--------|----------|
| `WriteProjectRestart` | `(__int64 ProjectId, BSTR FileName)` | ✅ | Сохранить рестарт |
| `ReadProjectRestart` | `(__int64 ProjectId, BSTR FileName)` | ✅ | Загрузить рестарт |
| `ResetProjectEngines` | `(__int64 ProjectId)` | ✅ | Сброс движков |
| `WriteRestartPoint` | `(__int64 ProjectId)` | ✅ | Точка рестарта |
| `ReadRestartPoint` | `(__int64 ProjectId)` | ✅ | Восстановить точку |
| `SetProjectReadRestartFile` | `(...)` | ➖ | Настройка чтения рестарта (есть fLoadRst) |
| `SetProjectWriteRestartFile` | `(...)` | ➖ | Настройка записи рестарта (есть fSaveRst) |
| `GetProjectRestartNames` | `(__int64 ProjectId) → (readFile, writeFile, ...)` | ➖ | Имена файлов рестарта (нужен ProjectId) |
| `SetRestartPreserveFlag` | `(__int64 ProjectId, long Flag)` | ✅ | Флаг сохранения рестарта |

---

## 12. Системные методы

| Метод | Сигнатура | Статус | Описание |
|-------|-----------|--------|----------|
| `SetSilentMode` | `(long Mode)` | ✅ | 1 = без GUI, 0 = с GUI |
| `SetShutdownOnLastRelease` | `(long Value)` | ✅ | Завершать процесс при последнем Release |
| `SetNoCloseAppFlag` | `(long Value)` | ✅ | Не закрывать приложение при закрытии проекта |
| `SetNoCloseFlag` | `(__int64 ProjectId, long Value)` | ✅ | Per-project no-close |
| `SetDesktopAsParent` | `(long Value)` | ✅ | Desktop как родительское окно |
| `SetReadOnlyFlag` | `(__int64 ProjectId, long ReadOnlyFlag)` | ✅ | Read-only режим |
| `GetEditorFlags` | `(__int64 ProjectId) → (Modified, Saved, PageModified, ReadOnly)` | ➖ | Флаги редактора (нужен ProjectId) |
| `GetProjectStateFlag` | `(__int64 ProjectId) → long` | ➖ | Флаг состояния проекта (нужен ProjectId) |
| `GetProcessID` | `() → unsigned long` | ✅ | PID процесса SimInTech |
| `SetSystemVariable` | `(BSTR aVarName, BSTR aValue)` | ✅ | Системная переменная |
| `GetSystemVariableValue` | `(BSTR aVarName) → BSTR` | ✅ | Чтение системной переменной |
| `SetSysProp` | `(...)` | ➖ | Системные свойства проекта |
| `SetLayerProp` | `(__int64 ProjectId, long LayerNo, BSTR PropName, BSTR StrValue)` | ✅ | Свойства слоя |
| `SetProjectModified` | `(__int64 ProjectId, long AModified)` | ✅ | Флаг модификации |
| `SetParentPrjHandle` | `(__int64 ProjectId, __int64 Handle)` | ✅ | Parent handle |
| `SetPrjPosByPrjId` | `(__int64 SrcPrjId, __int64 DestPrjId)` | ✅ | Позиция проекта |
| `SetRealTimeDelay` | `(__int64 ProjectId, long Flag, double Scale)` | ❌ | Не реализован в этой версии SimInTech |
| `WaitForAllLoading` | `()` | ✅ | Ждать загрузки всех ресурсов |
| `ProcessAllMessages` | `()` | ✅ | Обработка сообщений Windows |

---

## 13. База данных и плагины

| Метод | Сигнатура | Статус | Описание |
|-------|-----------|--------|----------|
| `ExportDBToXML` | `(__int64 ProjectId, BSTR DBFileName) → long` | ✅ | Экспорт БД в XML |
| `GetProjectDB` | `(__int64 ProjectId) → (DBPlugin, DBName)` | ➖ | Информация о БД проекта (нужен ProjectId) |
| `ReloadProjectDB` | `(__int64 ProjectId, BSTR DBPluginName, BSTR DBName)` | ✅ | Перезагрузить БД |
| `SetDBOverride` | `(BSTR aOverrideDBPlugin, BSTR aOverrideDBName)` | ✅ | Переопределение БД |
| `GetLayerName` | `(__int64 ProjectId, long LayerNumber) → BSTR` | ✅ | Имя слоя |
| `SendPluginCommand` | `(BSTR PluginName, long CommandId, BSTR CommandStr, __int64 ObjId) → (ResultStr, ResultPtr)` | ✅ | Команда плагину |

---

## 14. Примитивы (графика)

| Метод | Сигнатура | Статус | Описание |
|-------|-----------|--------|----------|
| `CreatePrimitiv` | `(__int64 ProjectId, long LayerNo, __int64 Parent, long PrimitivId) → __int64` | ✅ | Создать примитив |
| `AddObjectPoint` | `(__int64 BlockId, double X, double Y)` | ✅ | Добавить точку |
| `InsertObjectPoint` | `(__int64 BlockId, long Index, double X, double Y)` | ✅ | Вставить точку |
| `DeleteObjectPoint` | `(__int64 BlockId, long Index, long Count)` | ✅ | Удалить точки |
| `GetPointCount` | `(__int64 BlockId) → long` | ✅ | Количество точек |

---

## 15. Утилиты

| Метод | Сигнатура | Статус | Описание |
|-------|-----------|--------|----------|
| `SetJournalSavePeriod` | `(long Period)` | ➖ | Период сохранения журнала (мс) |
| `SetPipeName` | `(BSTR PipeName)` | ➖ | Имя пайпа для лога |
| `SetCallbackHandleAndDataID` | `(__int64 CallbackHWND, __int64 CallBackDataId)` | ✅ | Callback для событий |
| `SetCmdStr` | `(__int64 ProjectId, BSTR CmdStr)` | ✅ | Команда проекту |
| `GetCmdStr` | `(__int64 ProjectId) → BSTR` | ➖ | Чтение команды (нужен ProjectId) |
| `WriteAsFont` | `(TDataDescriptor, BSTR FontName, long FontSize, byte FontStyle)` | ➖ | Запись шрифта (нужен desc) |
| `SetFontData` | `(__int64 PropHandle, BSTR FontName, long Height, long Color, byte Style)` | ✅ | Данные шрифта |

---

## 16. Рекомендуемый порядок работы (проверенный workflow)

```
1. SetSilentMode(1)
2. OpenProject("path.xprt") → pj_id
3. GetProjectIdByNumber(0) → pj_id (защита от дублирования ID)
4. GetMainPage(pj_id) → page_id
5. SetCurrentPage(pj_id, page_id)
6. FindSignalData("name", pj_id) → desc  (для каждого сигнала)
7. WriteAsFloat(desc, value)  (запись входов ДО старта)
8. ProjectStart(pj_id)
9. ProjectRun(pj_id) или RunTo(pj_id, time) или ProjectStep(pj_id)
10. ReadAsFloat(desc) → value (чтение выходов)
11. ProjectStop(pj_id)
12. CloseProject(pj_id)
```

### Порядок с WriteAsFloat между шагами (динамическое управление)

```
1-8. Как выше
9. ProjectRun(pj_id)
10. poll GetProjectTime(pj_id)
11. WriteAsFloat(desc_in, new_value)  (изменение входа на лету)
12. ProjectStep(pj_id)
13. ReadAsFloat(desc_out) → value
14. goto 10 или ProjectStop
```

---

## 17. Критические ограничения

| Проблема | Причина | Решение |
|----------|---------|---------|
| pywin32 не работает | VT_RECORD marshalling broken | comtypes |
| SetBlockProp("a") не влияет на симуляцию | Константы инициализируются до ProjectStart | WriteAsFloat напрямую |
| Color не читается из скрипта блока | Color - design-time property | Читать через COM API после остановки |
| OpenProject не принимает .xprt? | Баг COM API - некоторые версии | Открывать .prt или использовать SaveProjectBinary |
| `GetProjectTime` не растёт, хотя `ProjectRun`/`RunTo`/`ProjectStep` возвращают успех | Проект создан через `NewProject`: в нём нет расчётного слоя и настроек | Открывать **шаблон** через `OpenTemplate` — см. §18 |

---

## 18. Создание проекта: шаблон, а не `NewProject`

Проверено на SimInTech64 (2026-09-15).

`NewProject` создаёт **пустой** проект. В экспорте `.xprt` у него один слой
«Нулевой слой» с пустыми `<groups>` и `<pluginname>`, а секция параметров слоя
`<parameters>` пуста. У работоспособного проекта слой называется «Автоматика»,
его плагин — `$(Root)\mbtylib.dll@layer`, а в `<parameters>` лежат настройки
расчёта: подписи «Начальное/Конечное время расчёта» → `starttime`/`endtime`,
а также `hmin`, `hmax`, `startstep`, `intmet`, `synstep`, `serial_mode` и др.

Следствие: у пустого проекта модельное время **не растёт ничем** — `ProjectRun`
(опрос 6 с), `RunTo` (возвращает `1`), `WaitForTime` (`0`), `ProjectStep`,
`GetProjectStateFlag` (`0`). Не помогают `save_binary` с повторным открытием,
`WaitForAllLoading` и `SetSilentMode(0)`. Ошибки при этом нет: вызовы сообщают
об успехе, а расчёт не идёт.

**Рабочий путь — `OpenTemplate` с шаблоном пустой модели из поставки:**

```
C:\SimInTech64\bin\Template\Схема модели общего вида.prt
```

В GUI это то же, что «Файл → Создать → Схема модели общего вида». По короткому
имени (без пути) `OpenTemplate` возвращает `0`, нужен полный путь. Рядом лежат
и другие шаблоны: `Схема БТС.prt`, `Схема ГПС.prt`, `Схема теплогидравлическая.prt`,
`Схема электрическая.prt`, `Web интерфейс.prt`.

**Настройки расчёта меняются свойством расчётного слоя** (`SetLayerProp`),
номер слоя `0`, значение — строкой:

```python
client.call("SetLayerProp", project_id, 0, "endtime", "2.0")   # → handle != 0
```

Возврат `0` — свойство не принято (например, у проекта нет расчётного слоя:
для `NewProject` вызов возвращает `0` и ничего не меняет). У шаблонного проекта
`endtime` по умолчанию `10`; после записи `2` расчёт останавливается ровно на
`2.0`. Другие свойства слоя задаются так же.

**Методы, отсутствовавшие в таблицах выше** (найдены интроспекцией интерфейса
`IMVTU_Server`):

| Метод | Назначение |
|---|---|
| `SendDataToLayer(i64, long, long, BSTR, …)` | «Послать произвольные данные в расчётный слой» |
| `GetProjectByCOMName(BSTR) → i64` | Проект по COM-имени |

Остальные имена совпали с уже описанными: `GetPropHandle` («ссылка на элемент
данных по имени настраиваемого свойства»), `ReloadProjectDB`,
`ResetProjectEngines`, `ProcessAllMessages`, `RepaintEditor`.

**Вывод результатов.** `get_signal`/`ReadAsFloat` работают только у проекта с
подключённой базой сигналов. Независимый путь — блок **«В файл»** (класс для
`CreateBlock`: `В файл`, автоимя `ToFile_0`; справка — «Вывод данных → В файл»):
пишет по строке на момент времени в формате `<время> <значение 1> … <значение n>`.
Свойства: `filename` (по умолчанию `file.dat`), `count` (число входов), `step`
(массив шага записи, по умолчанию `[1]`), `fform`, `strendformat`, `divstyle`.
Проверено: `Константа(2) → Усилитель(3) → В файл(step=[0.2])` при `endtime=1`
даёт 6 строк `0 … 1` со значением `6`.

**Неподключённый вход останавливает расчёт всей модели — молча.** Проверено
там же: схема «Константа → В файл» при связанных входах считает до `1.0`; та же
схема с висящим входом у «В файл» даёт `GetProjectTime = 0.0` и **никакой
ошибки**; одна «Константа» без «В файл» — снова `1.0`. То есть отсутствие
соединения — такая же причина «расчёт не идёт», как и отсутствие расчётного
слоя, и отличается от него только диагностикой.
