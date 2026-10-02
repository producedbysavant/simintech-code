"""Тесты process helpers без запуска SimInTech."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from simintech_api.utils.processes import wait_for_pid_exit


def test_wait_for_pid_exit_returns_true_when_pid_is_absent(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        "simintech_api.utils.processes.get_mmain_pids",
        lambda: set(),
    )

    assert wait_for_pid_exit(12345, timeout=1.0) is True


def test_wait_for_pid_exit_returns_false_at_timeout(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        "simintech_api.utils.processes.get_mmain_pids",
        lambda: {12345},
    )

    assert wait_for_pid_exit(12345, timeout=0.0) is False
