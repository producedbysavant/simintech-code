Руководство пользователя
========================

Создание первой модели через simintech-api.

Требования
----------

* **Windows** (COM API SimInTech работает только там).
* Установленный SimInTech 64 и зарегистрированный COM-объект:

  .. code-block:: text

     C:\\SimInTech64\\bin\\mmain.exe /regserver

* Python 3.9+, comtypes:

  .. code-block:: bash

     pip install -e ".[test]"

Подключение
-----------

.. code-block:: python

   from simintech_api import COMClient
   client = COMClient(silent_mode=True).connect()

``silent_mode=True`` скрывает UI. ``connect()`` бросает
``ComConnectionError``, если COM недоступен (не Windows / не /regserver).

Проект и блоки
--------------

.. code-block:: python

   from simintech_api import Project

   prj = Project.from_template(client)   # проект из шаблона — только такой считает
   prj.set_calc_end_time(5.0)            # конечное время расчёта (endtime слоя)
   page = prj.get_main_page()

   b1 = page.create_block("Ступенька", 0, 0)
   b1.set_property("t", 0.0)
   b1.set_property("y0", 0.0)
   b1.set_property("yk", 5.0)

   b2 = page.create_block("Усилитель", 200, 0)
   b2.set_property("a", 2.0)

.. note::

   ``Project.new()`` создаёт пустой проект — без расчётного слоя и настроек
   расчёта; модельное время в нём не растёт, хотя ``run``/``step``/``run_to``
   сообщают об успехе. Для расчёта — ``Project.from_template()`` и явное
   ``set_calc_end_time()`` (иначе берётся значение шаблона, 10 с).

Имена классов — русские, регистрозависимы («Константа», «Усилитель»,
«Сумматор», «Интегратор», «Производная», «Ступенька», «Синусоида»,
«Временной график» и др.).

.. note::

   Классы «Из памяти» и «Порт выхода» отвергает ``Page.create_block``
   (``UnsupportedBlockError``) — это защита библиотеки, а не отказ COM:
   замерено на живом COM 2026-09-18, ``CreateBlock`` создаёт обе записи и
   возвращает ненулевой id. Годятся ли они в модели, не проверено, поэтому
   защита оставлена. Обходной путь — встроенный язык SimInTech.

.. note::

   Блоки библиотеки «Конечные автоматы» создаются, но только по **полному имени
   записи** — с префиксом ``Конечные автоматы - `` (см.
   ``constants.FSM_BLOCK_RECORDS``, ``constants.fsm_record()``). Короткий
   заголовок с палитры (``Состояние автомата``) ``CreateBlock`` не принимает и
   возвращает 0.

Соединение и расчёт
-------------------

.. code-block:: python

   b1.connect(b2)                 # out0 -> b2.in0
   sim = prj.simulation()
   sim.start()                    # инициализация (обязательна!)
   sim.run_to(5.0)                # расчёт до 5 с
   sim.stop()

Сигналы
-------

.. code-block:: python

   sig = prj.signal("имя_сигнала")
   value = sig.read()             # тип по DataType
   sig.write(3.14)

   for info in prj.list_signals():
       print(info.name, info.caption)

.. warning::

   ``list_signals()`` и ``find_signal()`` работают **только после
   ``sim.start()``** (ProjectStart) — модель компилируется и сигналы
   появляются в списке. До старта список пуст.

Сохранение
----------

.. code-block:: python

   prj.save_xml("model.xprt")
   prj.close()
   client.shutdown()     # завершает процесс mmain.exe (если порождён нами)

Layout и линии
--------------

.. code-block:: python

   from simintech_api.layout import LayeredPlacer

   positions = LayeredPlacer().place(block_ids, connections, sizes=sizes)
   for bid, (cx, cy) in positions.items():
       blocks[bid].set_center(cx, cy, *sizes[bid])
   for src, dst in connections:
       page.create_wire(blocks[src].get_out_port(0),
                        blocks[dst].get_in_port(0))

.. note::

   Линии трассирует SimInTech, а не библиотека: маршрут выбирает
   ``NormalizeWire`` (после перерисовки редактора), а опорные точки на него не
   влияют — ``create_wire(points=…)`` и ``set_points(…)`` маршрутом не
   управляют и предупреждают об этом (``UserWarning``). Чистая схема
   получается расстановкой: источник с единственным приёмником — вплотную к
   приёмнику. ``AStarRouter`` только считает ортогональный маршрут; применить
   его к линии нечем.

ИИ-агент / CLI
--------------

.. code-block:: python

   from simintech_api.agent import SimInTechAgent
   agent = SimInTechAgent()
   print(agent.execute("help"))

.. code-block:: text

   simintech-cli "create project \"Demo\"" "add block \"Ступенька\""
