"""Управление расчётом проекта/пакета SimInTech."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .com_client import COMClient

#: Значения по умолчанию для ожидания выхода модельного времени на отметку.
CALC_POLL_SECONDS = 0.05     # период опроса GetProjectTime
CALC_WAIT_SECONDS = 30.0     # общий предел ожидания
CALC_STALL_SECONDS = 1.0     # простой, после которого расчёт считается вставшим


class Simulation:
    """Управление расчётом проекта (ProjectStart/Run/Step/...).

    Args:
        client: COM-клиент.
        project_id: id проекта (или пакета для Pack-методов).
    """

    def __init__(self, client: "COMClient", project_id: int):
        self._client = client
        self._id = project_id

    # ─── Проект ─────────────────────────────────────────────────────

    def start(self) -> "Simulation":
        """Инициализировать расчёт (ProjectStart)."""
        self._client.call("ProjectStart", self._id)
        return self

    def run(self) -> "Simulation":
        """Запустить непрерывный расчёт."""
        self._client.call("ProjectRun", self._id)
        return self

    def step(self) -> "Simulation":
        """Выполнить один шаг расчёта."""
        self._client.call("ProjectStep", self._id)
        return self

    def pause(self) -> "Simulation":
        """Приостановить расчёт."""
        self._client.call("ProjectPause", self._id)
        return self

    def stop(self) -> "Simulation":
        """Остановить расчёт."""
        self._client.call("ProjectStop", self._id)
        return self

    def run_to(self, target_time: float,
               timeout: float = CALC_WAIT_SECONDS,
               stall: float = CALC_STALL_SECONDS) -> bool:
        """Расчёт до заданного времени; True, если время **дошло** до отметки.

        `RunTo` в этой сборке SimInTech **не блокирующий**: он возвращается
        раньше, чем расчёт дойдёт до отметки (проверено: сразу после вызова
        модельное время 0.240 с при цели 0.5 с). Поэтому достижение проверяется
        по `GetProjectTime`, а не по коду возврата — иначе метод рапортовал бы
        об успехе мгновенно и всегда.

        Args:
            target_time: момент, до которого считается модель.
            timeout: предел ожидания в секундах.
            stall: простой модельного времени, после которого расчёт считается
                вставшим и ожидание прекращается.

        Returns:
            True, если модельное время действительно достигло `target_time`.
        """
        self._client.call("RunTo", self._id, float(target_time))
        return self.wait_for_time(target_time, timeout=timeout, stall=stall)

    def wait_for_time(self, target_time: float,
                      timeout: float = CALC_WAIT_SECONDS,
                      stall: float = CALC_STALL_SECONDS) -> bool:
        """Дождаться модельного времени `target_time`; True при достижении.

        Опросом `GetProjectTime`, а не COM-методом `WaitForTime`: в этой сборке
        `WaitForTime` возвращает 0 немедленно и фактически не ждёт (проверено
        на реальном SimInTech в проектах с настроенным расчётом и без).

        Ожидание ограничено двумя способами: общим `timeout` и простоем —
        если время не растёт `stall` секунд, расчёт не идёт и ждать нечего.
        """
        deadline = time.monotonic() + timeout
        stall_limit = max(1, int(stall / CALC_POLL_SECONDS))
        actual = self.get_time()
        stale = 0
        while actual + 1e-9 < target_time and time.monotonic() < deadline:
            time.sleep(CALC_POLL_SECONDS)
            new = self.get_time()
            stale = stale + 1 if new <= actual else 0
            actual = new
            if stale >= stall_limit:
                break
        return actual + 1e-9 >= target_time

    def get_time(self) -> float:
        """Текущее модельное время проекта."""
        return float(self._client.call("GetProjectTime", self._id))

    def get_state(self) -> int:
        """Состояние проекта (флаги GetProjectStateFlag)."""
        return _as_int(self._client.call("GetProjectStateFlag", self._id))

    # ─── Пакет ──────────────────────────────────────────────────────

    def pack_start(self) -> "Simulation":
        """Инициализировать пакет."""
        self._client.call("PackStart", self._id)
        return self

    def pack_run(self) -> "Simulation":
        """Запустить расчёт пакета."""
        self._client.call("PackRun", self._id)
        return self

    def pack_step(self) -> "Simulation":
        """Шаг расчёта пакета."""
        self._client.call("PackStep", self._id)
        return self

    def pack_pause(self) -> "Simulation":
        """Пауза пакета."""
        self._client.call("PackPause", self._id)
        return self

    def pack_stop(self) -> "Simulation":
        """Остановить пакет."""
        self._client.call("PackStop", self._id)
        return self

    def run_to_pack(self, target_time: float) -> bool:
        """Расчёт пакета до заданного времени.

        Возвращается результат `WaitForTimePack` как есть. Опросом подтвердить
        достижение нельзя: модельное время **пакета** отдельным методом не
        читается (для проектов это `GetProjectTime`, см. `run_to`). Поведение
        на реальном SimInTech не проверялось — не опирайтесь на этот `bool`.
        """
        self._client.call("RunToPack", self._id, float(target_time))
        wait = self._client.call("WaitForTimePack", self._id, float(target_time))
        return _as_int(wait) != 0

    # ─── Реальное время ─────────────────────────────────────────────

    def set_realtime_delay(self, delay_flag: int, delay_scale: float) -> "Simulation":
        """Синхронизация с реальным временем."""
        self._client.call("SetProjectRealTimeDelay", self._id, delay_flag,
                          float(delay_scale))
        return self


def _as_int(value) -> int:
    if hasattr(value, "value"):
        return int(value.value)
    return int(value)
