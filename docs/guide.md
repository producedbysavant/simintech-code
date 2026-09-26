# Руководство пользователя

Пошаговое создание первой модели через simintech-api.

## 0. Требования

- **Windows** (COM API SimInTech работает только там).
- Установленный SimInTech 64 и зарегистрированный COM-объект:
  ```
  C:\SimInTech64\bin\mmain.exe /regserver
  ```
- Python 3.9+, comtypes:
  ```
  pip install -e ".[test]"
  ```

## 1. Подключение

```python
from simintech_api import COMClient
client = COMClient(silent_mode=True).connect()
```

`silent_mode=True` скрывает UI. Если нужно видеть окно — `silent_mode=False`.
Метод `connect()` поднимет `ComConnectionError`, если COM недоступен
(не Windows / mmain.exe не зарегистрирован).

## 2. Создание проекта и блоков

```python
from simintech_api import Project

prj = Project.from_template(client)   # проект из шаблона — только такой считает
prj.set_calc_end_time(5.0)            # конечное время расчёта (endtime слоя)
page = prj.get_main_page()            # главная страница

b1 = page.create_block("Ступенька", 0, 0)     # класс + координаты
b1.set_property("t", 0.0)          # момент скачка
b1.set_property("y0", 0.0)
b1.set_property("yk", 5.0)         # амплитуда

b2 = page.create_block("Усилитель", 200, 0)
b2.set_property("a", 2.0)          # коэффициент
```

> **Почему не `Project.new()`**: он создаёт пустой проект — без расчётного слоя
> и настроек расчёта. В таком проекте модельное время не растёт **ничем**, при
> этом `run`/`step`/`run_to` сообщают об успехе, а `get_time()` остаётся `0.0`.
> Проект из шаблона (`Project.from_template`) считает; конечное время расчёта
> задаётся `set_calc_end_time`, иначе берётся значение шаблона — 10 с. Тем же
> свойством слоя задаются `starttime`, `hmin`, `hmax`, `intmet`
> (`set_calc_setting`, прочитать — `calc_settings`).

Имена классов — русские, регистрозависимы («Константа», «Усилитель»,
«Сумматор», «Интегратор», «Производная», «Ступенька» и др.). Полный список
доступных классов см. в библиотеках блоков SimInTech (`bin/*.csl`).

> **Известное ограничение**: классы «Из памяти» и «Порт выхода»
> `Page.create_block` отвергает (`UnsupportedBlockError`). Это защита
> библиотеки, а не отказ COM: замерено на живом COM 2026-09-18 — `CreateBlock`
> создаёт обе записи и возвращает ненулевой id, блок появляется на странице и
> свойства читаются. Годятся ли эти блоки в модели, не проверено, поэтому
> защита оставлена; обходной путь — встроенный язык SimInTech
> (макросы / блок «Язык программирования»).
>
> Блоки библиотеки «Конечные автоматы» создаются, но только по **полному имени
> записи** — с префиксом `Конечные автоматы - ` (см.
> `constants.FSM_BLOCK_RECORDS`, `constants.fsm_record()`); короткий заголовок
> с палитры (`Состояние автомата`) `CreateBlock` не принимает и возвращает 0.

## 3. Соединение

```python
b1.connect(b2)                     # out0 -> b2.in0
# с указанием портов:
b1.get_out_port(0).connect(b2.get_in_port(1))
```

## 4. Расчёт

```python
sim = prj.simulation()
sim.start()                        # инициализация
reached = sim.run_to(5.0)          # расчёт до 5 с; True, только если время дошло
sim.get_time()                     # текущее модельное время
if not reached:
    print("Расчёт не дошёл: проверьте set_calc_end_time и входы блоков "
          "(неподключённый вход молча останавливает расчёт всей модели).")
sim.stop()
```

`run_to` не блокирующий: он возвращает `False`, если время не вышло на отметку.
Дальше расчёта конечного времени (`set_calc_end_time`) время не идёт — большее
`to_time` недостижимо.

## 5. Чтение сигналов

```python
sig = prj.signal("имя_записи")     # FindSignalData: сигнал по имени записи
value = sig.read()                 # тип автоматически по DataType
sig.write(3.14)                    # запись

# Внешние (обменные) сигналы — блоки «Вход/Выход алгоритма»:
for info in prj.list_signals():
    print(info.name, info.caption)
```

`signal(name)` / `find_signal(name)` ищут сигнал через `FindSignalData` по
имени записи. Обмен идёт через **базу сигналов проекта**: читаются только
сигналы проекта с подключённой базой — без неё `SignalError`, и имя блока
сигналом не является.

`list_signals()` возвращает только **внешние (обменные)** сигналы (блоки
«Вход/Выход алгоритма»). Внутренние сигналы блоков в него не входят. Если
обменных сигналов нет, возвращаются имена блоков из `.xprt` с `source='xml'`
и `readable=False` — это подсказка о схеме, а не читаемые сигналы. Имена
сигналов также можно взять из БД сигналов (SDB в SimInTech).

## 6. Сохранение

```python
prj.save_xml("model.xprt")         # XML — удобно для git-диффа
# или prj.save_binary("model.prt")
prj.close()
client.disconnect()
```

## 7. Автоматическая расстановка и линии

Для больших моделей используйте layout (см. `docs/algorithms.md`):

```python
from simintech_api.layout import LayeredPlacer

positions = LayeredPlacer().place(block_ids, connections, sizes=sizes)
for bid, (cx, cy) in positions.items():
    blocks[bid].set_center(cx, cy, *sizes[bid])
for src, dst in connections:
    page.create_wire(blocks[src].get_out_port(0),
                     blocks[dst].get_in_port(0))
```

**Линии трассирует SimInTech, а не библиотека.** Маршрут выбирает
`NormalizeWire` (после перерисовки редактора), опорные точки на него не
влияют — `create_wire(points=…)` и `set_points(…)` маршрутом не управляют и
предупреждают об этом (`UserWarning`). Чистая схема получается расстановкой:
источник с единственным приёмником ставьте вплотную к приёмнику — тогда
середина маршрута попадает в свободный коридор (`LayeredPlacer` это делает
сам). `AStarRouter` только считает ортогональный маршрут; применить его к
линии нечем.

## 8. ИИ-агент / CLI

```python
from simintech_api.agent import SimInTechAgent
agent = SimInTechAgent()
print(agent.execute("help"))       # список команд
agent.execute('create project "Demo"')
agent.execute('add block "Ступенька" as src with yk=5')
agent.execute('add block "Усилитель" as amp with a=2')
agent.execute("connect src.out to amp.in")
agent.execute("run for 5 seconds")
```

Из консоли:

```
simintech-cli "create project \"Demo\"" "add block \"Ступенька\"" 
simintech-cli    # интерактивный режим
```

## 9. Типичные ошибки и решения

| Ошибка | Причина | Решение |
|---|---|---|
| `ComConnectionError` | COM недоступен (не Windows / не /regserver) | Выполнить `mmain.exe /regserver`; проверить платформу |
| `SignalError: не найден` | Имя сигнала неверное | `prj.list_signals()` → проверить точное имя |
| `UnsupportedBlockError` | Класс отвергнут библиотекой (COM его создаёт) | Использовать встроенный язык SimInTech |
| `PortError` | Нет порта с таким индексом | `get_port_count()` / `get_ports()` |
| `LayoutError` | Путь между портами невозможен | Ослабить препятствия / увеличить сетку |
| Расчёт «завис» | `run()` без stop в непрерывном режиме | Использовать `run_to()` + `stop()` |
