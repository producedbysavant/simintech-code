"""Чтение топологии проекта поверх скриптового моста.

Тонкая обёртка: транспорт целиком в `ScriptBridge`, здесь только связывание
его с протоколом топологии. Дублировать проверки моста (маркер завершения,
рост модельного времени, возврат прежнего скрипта) нельзя — иначе они начнут
расходиться, и при отказе будет не понять, что сломалось: транспорт или проба.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..topology import Topology, build_topology_probe, parse_topology
from .script_bridge import ScriptBridge

if TYPE_CHECKING:
    from .com_client import COMClient


def read_topology(client: "COMClient", project_id: int,
                  result_path: Path) -> Topology:
    """Прочитать топологию текущего контейнера проекта.

    Файл по `result_path` — рабочий: мост пишет в него результат пробы и
    удаляет прежний.
    """
    result = ScriptBridge(client, project_id).run_probe(
        build_topology_probe(), result_path)
    return parse_topology("\n".join(result.lines))
