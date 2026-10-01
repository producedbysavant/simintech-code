"""Живой прогон контура: тело в initialization и возврат прежнего скрипта.

Запуск (Windows, из WSL — через Windows-Python):

    cd /mnt/c/git/simintech-code && PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 \
      python.exe -m pytest tests/integration/test_language_contour_live.py \
      -m integration --run-simintech -q

Измерено (2026-09-29, поставка 2.26.6.23): создание объектов работает только в
`initialization`, `run_probe` для этого не годится (тело под `if firststep then`).

Возврат прежнего скрипта сверяется **двумя** способами: тем, что вернул мост, и
сырой выгрузкой проекта — независимо от средств моста. Второе важнее: первое
подтвердило бы успех при любой поломке внутри моста.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from simintech_api.catalog import decode_xprt
from simintech_api.core.project import Project
from simintech_api.core.script_bridge import ScriptBridge
from simintech_api.script_probe import (
    OUTCOME_OK,
    TARGET_TOKEN_PREFIX,
    parse_xprt_script_records,
    token_present_in,
)

pytestmark = pytest.mark.integration


def test_body_runs_in_initialization_and_previous_script_returns(
        client, tmp_path: Path) -> None:
    project = Project.from_template(client)
    try:
        bridge = ScriptBridge(client, project.id)
        contour_file = tmp_path / "contour.txt"
        body = (
            'f = createfile("' + str(contour_file).replace("\\", "/") + '", -1);\n'
            'writelnutf8(f, "МОДЕЛЬ СОБРАНА");\n'
            "freeobject(f);"
        )

        result = bridge.run_page_script(body, tmp_path / "result.txt")

        assert result.outcome.kind == OUTCOME_OK, result.outcome
        assert contour_file.read_text(encoding="utf-8").strip() == (
            "МОДЕЛЬ СОБРАНА"), "тело не исполнилось: файла с данными нет"
        assert result.restored_script == "", (
            "у проекта из шаблона скрипта страницы не было — возврат обязан "
            "вернуть пустой скрипт, а не оставить тело контура в проекте")
        # Независимая проверка возврата: по сырой выгрузке проекта. Метка
        # контура уникальна, поэтому её наличие в записях означало бы, что
        # тело осталось в странице, как бы ни отчитался мост.
        records = _records(client, project, tmp_path / "after.xprt")
        assert not token_present_in(records, TARGET_TOKEN_PREFIX), (
            "в скриптовых записях осталась метка контура: тело осталось в проекте")
        assert int(client.call("GetProjectStateFlag", project.id)) == 0, (
            "после прогона проект остался инициализированным: уборка не прошла")
    finally:
        # Уборка не зависит от исхода: остановка безвредна при любом
        # измеренном состоянии, а закрывать инициализированный проект нельзя.
        try:
            client.call("ProjectStop", project.id)
        except Exception:                                             # noqa: BLE001
            pass
        project.close()


def test_read_page_script_returns_script_and_keeps_model_time(client, tmp_path):
    """Чтение возвращает поставленный скрипт и **не сдвигает** модельное время.

    COM чтения скрипта страницы не отдаёт (`GetPageScript` в интерфейсе нет),
    поэтому страница опознаётся снимком выгрузки — и это обязано быть безопасно
    для чужого расчёта: `ProjectStart` обнулил бы время.
    """
    project = Project.from_template(client)
    script = "// ПРИМЕТА_ЧТЕНИЯ\nseterrorflag(0);\n"
    try:
        bridge = ScriptBridge(client, project.id)
        bridge.install_script(script)
        time_before = float(client.call("GetProjectTime", project.id))

        restored = bridge.read_page_script()

        assert restored == script, "прочитан не тот скрипт, что стоял в странице"
        time_after = float(client.call("GetProjectTime", project.id))
        assert time_after == time_before, (
            f"чтение сдвинуло модельное время ({time_before} -> {time_after}): "
            "значит, был ProjectStart")
        assert int(client.call("GetProjectStateFlag", project.id)) == 0, (
            "после чтения проект остался инициализированным")
    finally:
        try:
            client.call("ProjectStop", project.id)
        except Exception:                                             # noqa: BLE001
            pass
        project.close()


def _records(client, project, path: Path) -> list:
    """Сырые скриптовые записи выгрузки — независимо от средств моста."""
    client.call("SaveProjectXML", project.id, str(path))
    return parse_xprt_script_records(decode_xprt(path.read_bytes()))
