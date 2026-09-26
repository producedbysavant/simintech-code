"""Обзор модели поверх топологической пробы.

Тонкая обёртка, как `core/topology.py`: транспорт целиком в `read_topology`,
здесь только связывание его с семантическим слоем. Собственных COM-вызовов слой
не делает — и это не экономия, а условие: каждое новое обращение к среде
пришлось бы измерять отдельно, а первый срез семантики намеренно не добавляет
ничего непроверенного.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..semantic import ContainerRef, ModelOverview, overview_from_topology
from .topology import read_topology

if TYPE_CHECKING:
    from .com_client import COMClient


def read_model_overview(client: "COMClient", project_id: int, result_path: Path,
                        *, container: ContainerRef) -> ModelOverview:
    """Прочитать обзор текущего контейнера проекта.

    Файл по `result_path` — рабочий: мост пишет в него результат пробы и удаляет
    прежний (как и у `read_topology`).

    `container` обязателен намеренно. Данные описывают **текущий** контейнер —
    тот, в который вызывающий вошёл через `activate()`/`submodel_page()`, — и
    слой не может это проверить: идентификатора контейнера среда в Python не
    отдаёт. Поэтому подпись обзора — утверждение вызывающего, и значение по
    умолчанию здесь означало бы подписывать обзор субмодели именем главной
    страницы.
    """
    topology = read_topology(client, project_id, result_path)
    return overview_from_topology(topology, container)
