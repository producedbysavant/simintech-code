"""Тесты консольного входа simintech-cli (без COM).

Точки входа не касался ни один тест, поэтому дефект
`agent.client.set_silent_mode(...)` — метода у COMClient нет — не видела ни
одна проверка, а сама команда падала с AttributeError до выполнения первой
команды. Здесь под тестом именно поверхность точки входа: клиент создаётся
явно, а не дотягиванием до него через агента.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest  # noqa: E402

from simintech_api import agent as agent_module  # noqa: E402
from simintech_api import cli  # noqa: E402


class _FakeClient:
    """Подмена COMClient: без COM, помнит запрошенный режим."""

    def __init__(self, silent_mode=True, com_progid=None):
        self.silent_mode = silent_mode
        self.com_progid = com_progid
        self.connected = False

    def connect(self):
        self.connected = True
        return self


@pytest.mark.skipif(sys.platform == "win32", reason="проверка не-Windows ветки")
def test_main_refuses_off_windows(capsys):
    """Вне Windows CLI отказывает, не трогая COM и не создавая клиента."""
    assert cli.main([]) == 2
    assert "Windows" in capsys.readouterr().err


def _run(monkeypatch, argv):
    """Прогнать `main` на «Windows» с фейковым клиентом.

    Возвращает клиента, до которого дошёл агент: `_run_batch` подменён, поэтому
    команда не выполняется, но маршрут «клиент → агент» проверяется целиком
    (реальный SimInTechAgent, реальный путь через свойство `client`).
    """
    monkeypatch.setattr(sys, "platform", "win32")
    # COMClient подменяется и в cli, и в agent: без второй подмены агент при
    # автоподключении дошёл бы до настоящего COMClient и на Linux упал бы с
    # ComConnectionError — раньше, чем до вызова несуществующего метода, и
    # провал теста указывал бы не на тот дефект.
    monkeypatch.setattr(cli, "COMClient", _FakeClient, raising=False)
    monkeypatch.setattr(agent_module, "COMClient", _FakeClient, raising=False)
    seen = {}

    def fake_batch(agent, commands):
        seen["client"] = agent.client
        return 0

    monkeypatch.setattr(cli, "_run_batch", fake_batch)
    assert cli.main(argv) == 0
    return seen["client"]


def test_main_builds_silent_client_by_default(monkeypatch):
    """Без флага клиент скрытый (silent_mode=True) и уже подключён."""
    client = _run(monkeypatch, ["create project Demo"])
    assert client.silent_mode is True
    assert client.connected is True


def test_main_no_silent_builds_visible_client(monkeypatch):
    """`--no-silent` доходит до клиента: режим не подменяется автоподключением."""
    client = _run(monkeypatch, ["--no-silent", "create project Demo"])
    assert client.silent_mode is False
