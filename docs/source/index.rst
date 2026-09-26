simintech-api documentation
============================

Python-библиотека для программного управления **SimInTech** через внешний
COM API (`IMVTU_Server`).

Содержание:

.. toctree::
   :maxdepth: 2

   guide
   api
   algorithms
   examples


Обзор
-----

Библиотека позволяет ИИ-агенту или пользователю:

* создавать проекты SimInTech и размещать блоки из стандартных библиотек;
* настраивать параметры блоков;
* соединять блоки линиями связи;
* запускать расчёт, читать и записывать сигналы;
* автоматически расставлять блоки без наложений (``LayeredPlacer``), а также
  считать ортогональные маршруты линий (``AStarRouter``) — геометрию линий
  задаёт сам SimInTech.

Быстрый старт
-------------

.. code-block:: python

   from simintech_api import COMClient, Project

   client = COMClient(silent_mode=True).connect()
   # Проект — из шаблона: только такой считает (`Project.new()` даёт пустой
   # проект без расчётного слоя, модельное время в нём не растёт).
   prj = Project.from_template(client).set_calc_end_time(10.0)
   page = prj.get_main_page()

   b1 = page.create_block("Константа", 0, 0)
   b1.set_property("a", 5.0)
   b2 = page.create_block("Усилитель", 200, 0)
   b2.set_property("a", 2.0)
   b1.connect(b2)

   prj.save_xml("model.xprt")
   prj.close()
   client.shutdown()
