"""Тесты Simulation: ожидание модельного времени (без COM).

`RunTo` в этой сборке SimInTech не блокирующий: он возвращается раньше, чем
расчёт дойдёт до отметки, а `WaitForTime` возвращает 0 немедленно. Поэтому
`run_to` подтверждает достижение опросом `GetProjectTime` — и должен честно
возвращать False, если время не дошло.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest  # noqa: E402

from simintech_api.core import simulation as sim_module  # noqa: E402
from simintech_api.core.simulation import Simulation  # noqa: E402


class FakeSimClient:
    """Клиент с управляемой последовательностью модельного времени."""

    def __init__(self, times):
        self.calls = []
        self._times = list(times)
        self._last = 0.0

    def call(self, method, *args):
        self.calls.append((method, *args))
        if method == "GetProjectTime":
            if self._times:
                self._last = self._times.pop(0)
            return self._last
        return 0


def _no_sleep(monkeypatch):
    monkeypatch.setattr(sim_module.time, "sleep", lambda seconds: None)


def test_run_to_returns_true_when_target_reached(monkeypatch):
    """run_to возвращает True, когда время действительно дошло до отметки."""
    _no_sleep(monkeypatch)
    client = FakeSimClient([0.1, 0.3, 0.5])
    sim = Simulation(client, 42)

    assert sim.run_to(0.5) is True
    assert ("RunTo", 42, 0.5) in client.calls


def test_run_to_stops_polling_when_target_already_reached(monkeypatch):
    """Цель уже достигнута — опрашивать нечего, и RunTo всё равно вызывается."""
    _no_sleep(monkeypatch)
    client = FakeSimClient([5.0])
    sim = Simulation(client, 42)

    assert sim.run_to(1.0) is True
    assert ("RunTo", 42, 1.0) in client.calls
    assert [c for c in client.calls if c[0] == "GetProjectTime"] == [
        ("GetProjectTime", 42)]


def test_run_to_returns_false_when_time_stalls(monkeypatch):
    """Время не растёт — расчёт не идёт, ждать бессмысленно."""
    _no_sleep(monkeypatch)
    client = FakeSimClient([0.0] * 100)
    sim = Simulation(client, 42)

    assert sim.run_to(1.0, timeout=30.0, stall=0.1) is False


def test_run_to_gives_up_on_timeout(monkeypatch):
    """Медленный, но живой расчёт упирается в общий таймаут."""
    clock = {"t": 0.0}
    monkeypatch.setattr(sim_module.time, "monotonic", lambda: clock["t"])

    def tick(_seconds):
        clock["t"] += 0.5

    monkeypatch.setattr(sim_module.time, "sleep", tick)
    client = FakeSimClient([0.001 * i for i in range(1, 500)])
    sim = Simulation(client, 42)

    assert sim.run_to(100.0, timeout=1.0, stall=60.0) is False


def test_wait_for_time_returns_false_when_time_stands_still(monkeypatch):
    """wait_for_time без вызова RunTo — тот же честный результат."""
    _no_sleep(monkeypatch)
    client = FakeSimClient([0.0] * 50)
    sim = Simulation(client, 42)

    assert sim.wait_for_time(1.0, timeout=5.0, stall=0.1) is False
    assert ("RunTo", 42, 1.0) not in client.calls


@pytest.mark.parametrize("target", [0.5, 2.0])
def test_run_to_passes_target_as_float(monkeypatch, target):
    """Момент времени уходит в COM числом с плавающей точкой."""
    _no_sleep(monkeypatch)
    client = FakeSimClient([target])
    sim = Simulation(client, 42)

    sim.run_to(target)

    assert ("RunTo", 42, float(target)) in client.calls
