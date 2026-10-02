"""Job-объект: платформенные стражи без Windows.

Настоящий Win32-путь (назначение процесса, `GetExitCodeProcess`) исполним
только на Windows и проверен живьём (проба `probe_job_object_owner_death`,
замер 02.10.2026); здешние тесты держат контракт «вне Windows — тихий
отказ», от которого зависит импортируемость модуля на Linux.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
)

from simintech_api.utils import job_object


def test_assign_skips_outside_windows(monkeypatch):
    """Вне Windows назначение не выполняется и не является ошибкой."""
    monkeypatch.setattr(sys, "platform", "linux")

    assert job_object.assign_kill_on_close(1234) == (None, 0)


def test_assign_skips_nonpositive_pid(monkeypatch):
    """Неположительный PID отвергается до обращения к kernel32."""
    monkeypatch.setattr(sys, "platform", "win32")

    assert job_object.assign_kill_on_close(0) == (None, 0)
    assert job_object.assign_kill_on_close(-1) == (None, 0)


def test_is_process_alive_false_outside_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")

    assert job_object.is_process_alive(1234) is False


def test_is_process_alive_false_for_nonpositive_pid(monkeypatch):
    """pid <= 0 отвергается до обращения к kernel32."""
    monkeypatch.setattr(sys, "platform", "win32")

    assert job_object.is_process_alive(0) is False


def test_close_handle_is_noop_outside_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")

    job_object.close_handle(4321)  # не должно бросить
    job_object.close_handle(0)


def test_close_handle_zero_is_noop_on_windows(monkeypatch):
    """Нулевой хэндл не доходит до kernel32 (страх до WinDLL)."""
    monkeypatch.setattr(sys, "platform", "win32")

    job_object.close_handle(0)
