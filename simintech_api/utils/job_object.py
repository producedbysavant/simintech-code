"""Job Object с `KILL_ON_JOB_CLOSE` — уборка процесса OWNED-сессии.

Смерть процесса-клиента не завершает `mmain.exe`, поднятый COM-SCA: rundown
отпускает сервер, но процесс может остаться жить (замеры 02.10.2026: клиент
убит — процесс жив 4/4), а убирать сироту некому. Механизм уборки: процесс
OWNED-сессии назначается в job-объект с `KILL_ON_JOB_CLOSE`, хэндл которого
держит клиент. Когда процесс-клиент умирает, ядро закрывает его хэндлы — и
завершает процессы job'а; ни «своего запуска» `mmain`, ни отдельного
сторожа-процесса для этого не требуется.

Замер 02.10.2026 (SimInTech64, поставка 2.26.6.23; проба
`probe_job_object_owner_death`, n=2): существующий `-Embedding`-процесс
(родитель — `svchost`) назначается в job (`AssignProcessToJobObject`), сессия
после назначения отвечает и создаёт проект из шаблона, а смерть держателя
хэндла снимает процесс силами ядра.

Модуль импортируется на любой платформе: Win32-вызовы уходят в `kernel32`
только после проверки `sys.platform` — она же скрывает их от mypy на Linux
(см. `pyproject.toml`, `[tool.mypy]`, и слепой карман `--platform win32`).
"""

from __future__ import annotations

import ctypes
import sys
from typing import Any, Optional, Tuple

#: LimitFlags: завершить процессы job'а при закрытии последнего хэндла.
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
#: Информационный класс JOBOBJECT_EXTENDED_LIMIT_INFORMATION.
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_PROCESS_TERMINATE = 0x0001
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_SYNCHRONIZE = 0x00100000
#: Код выхода живого процесса (`GetExitCodeProcess`).
_STILL_ACTIVE = 259


class _IoCounters(ctypes.Structure):
    """IO_COUNTERS — не используются, но входят в структуру job-лимитов."""

    _fields_ = [("ReadOperationCount", ctypes.c_ulonglong),
                ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong),
                ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong),
                ("OtherTransferCount", ctypes.c_ulonglong)]


class _BasicLimitInformation(ctypes.Structure):
    """JOBOBJECT_BASIC_LIMIT_INFORMATION: задаётся только `LimitFlags`."""

    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", ctypes.c_uint32),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", ctypes.c_uint32),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", ctypes.c_uint32),
                ("SchedulingClass", ctypes.c_uint32)]


class _ExtendedLimitInformation(ctypes.Structure):
    """JOBOBJECT_EXTENDED_LIMIT_INFORMATION: 144 байта на x64 (замер)."""

    _fields_ = [("BasicLimitInformation", _BasicLimitInformation),
                ("IoInfo", _IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


def assign_kill_on_close(pid: int) -> Tuple[Optional[int], int]:
    """Назначить процесс `pid` в новый job с `KILL_ON_JOB_CLOSE`.

    Только для своего (OWNED) процесса: закрытие последнего хэндла этого
    job'а завершает процессы в нём, и чужой процесс сюда попадать не должен.

    Returns:
        ``(хэндл, 0)`` — назначено; хэндл обязан жить, пока должна жить
        защита (закрытие хэндла — в том числе смертью процесса-клиента —
        завершает процессы job'а силами ядра). ``(None, код)`` — отказ: вне
        Windows ``(None, 0)``, иначе код ошибки `OpenProcess`/
        `AssignProcessToJobObject` (процесса нет, прав мало, или процесс уже
        в несовместимом job'е — вложенность появилась в Windows 8). Отказ
        назначения не является отказом сессии: вызывающий продолжает работать
        без гарантии уборки, а код остаётся у него для диагностики.
    """
    if sys.platform != "win32":
        return None, 0
    if pid <= 0:
        return None, 0

    kernel32 = _kernel32()
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return None, ctypes.get_last_error()

    limits = _ExtendedLimitInformation()
    limits.BasicLimitInformation.LimitFlags = (
        _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE)
    if not kernel32.SetInformationJobObject(
            job, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits), ctypes.sizeof(limits)):
        error = ctypes.get_last_error()
        kernel32.CloseHandle(job)
        return None, error

    process = kernel32.OpenProcess(
        _PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, pid)
    if not process:
        error = ctypes.get_last_error()
        kernel32.CloseHandle(job)
        return None, error

    assigned = kernel32.AssignProcessToJobObject(job, process)
    if not assigned:
        error = ctypes.get_last_error()
        kernel32.CloseHandle(process)
        kernel32.CloseHandle(job)
        return None, error
    # Хэндл процесса job'у больше не нужен — job держит своё.
    kernel32.CloseHandle(process)
    return int(job), 0


def close_handle(handle: int) -> None:
    """Закрыть хэндл Win32 (job-объекта); 0 и не-Windows — ничего не делают.

    Вызывается, когда процессы job'а уже завершены: закрытие последнего
    хэндла тогда не завершает ничего живого. Хэндл, оставленный незакрытым,
    закрывает сама ОС при смерти процесса-владельца — и это штатное
    срабатывание уборки.
    """
    if sys.platform != "win32":
        return
    if not handle:
        return
    _kernel32().CloseHandle(handle)


def is_process_alive(pid: int) -> bool:
    """Жив ли процесс по PID (Windows); вне Windows и для pid <= 0 — False.

    Отказ открыть процесс (`OpenProcess` вернул 0) считается «не жив»:
    решается судьба только своего (OWNED) процесса, а неоткрываемый процесс
    трогать нельзя в любом случае.
    """
    if sys.platform != "win32":
        return False
    if pid <= 0:
        return False

    kernel32 = _kernel32()
    # Без PROCESS_QUERY_LIMITED_INFORMATION `GetExitCodeProcess` отказывает —
    # грабля живых замеров 02.10.2026 (код выхода читался только с ним).
    handle = kernel32.OpenProcess(
        _SYNCHRONIZE | _PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        code = ctypes.c_uint32()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == _STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _kernel32() -> Any:
    """`kernel32` с прототипами нужных функций (`use_last_error=True`).

    Прототипы обязательны: без `restype` хэндлы обрезались бы до 32 бит
    (умолчание `c_int`) — классическая грабля ctypes на x64.
    """
    if sys.platform != "win32":  # pragma: no cover — Windows-only
        raise RuntimeError("Job Objects доступны только на Windows")

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = ctypes.c_void_p
    kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p)
    kernel32.SetInformationJobObject.restype = ctypes.c_int
    kernel32.SetInformationJobObject.argtypes = (
        ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32)
    kernel32.AssignProcessToJobObject.restype = ctypes.c_int
    kernel32.AssignProcessToJobObject.argtypes = (
        ctypes.c_void_p, ctypes.c_void_p)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.OpenProcess.argtypes = (
        ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
    kernel32.GetExitCodeProcess.restype = ctypes.c_int
    kernel32.GetExitCodeProcess.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    kernel32.CloseHandle.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    return kernel32
