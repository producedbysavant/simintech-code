"""Работа с процессами SimInTech (mmain.exe).

Надёжное получение PID'ов процессов SimInTech и их завершение. Используется
для очистки процессов, порождённых тестами, не трогая процессы, которые
существовали до начала работы.
"""
from __future__ import annotations

import subprocess
import sys
from typing import Iterable, Set


def get_mmain_pids() -> Set[int]:
    """Вернуть множество PID всех запущенных процессов mmain.exe.

    Использует несколько методов (wmic, tasklist, PowerShell) и объединяет
    результаты — так надёжнее, чем любой один метод (зависит от локали,
    прав, версии Windows). Вне Windows — пустое множество.

    Вывод команд читается с `errors="replace"`, и это не украшение: под
    `PYTHONUTF8=1` (обязательным для живых прогонов) текстовый режим
    `subprocess` декодирует вывод как UTF-8, а `tasklist`/`wmic` на русской
    консоли пишут в cp866 — поток-читатель падал `UnicodeDecodeError`-ом, и
    фикстура владения процессами срывалась на ровном месте (замер
    01.10.2026: живой прогон упал в setup с PytestUnhandledThreadException).
    PID'ы — цифры, и они переживают любую однобайтовую перекодировку.
    """
    if sys.platform != "win32":
        return set()
    pids: Set[int] = set()
    pids |= _pids_wmic()
    pids |= _pids_tasklist()
    pids |= _pids_powershell()
    return pids


def kill_pids(pids: Iterable[int]) -> None:
    """Принудительно завершить процессы по PID (Windows)."""
    if sys.platform != "win32":
        return
    for pid in pids:
        try:
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True, timeout=10,
            )
        except Exception:
            pass


# ─── Внутренние методы ─────────────────────────────────────────────

def _pids_wmic() -> Set[int]:
    try:
        out = subprocess.run(
            ["wmic", "process", "where", "name='mmain.exe'", "get", "ProcessId"],
            capture_output=True, text=True, errors="replace", timeout=10,
        ).stdout
    except Exception:
        return set()
    result: Set[int] = set()
    for line in out.splitlines():
        line = line.strip()
        if line.isdigit():
            result.add(int(line))
    return result


def _pids_tasklist() -> Set[int]:
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq mmain.exe",
             "/FO", "CSV", "/NH"],
            capture_output=True, text=True, errors="replace", timeout=10,
        ).stdout
    except Exception:
        return set()
    result: Set[int] = set()
    for line in out.splitlines():
        parts = [p.strip().strip('"') for p in line.split(",")]
        if len(parts) >= 2 and parts[1].isdigit():
            result.add(int(parts[1]))
    return result


def _pids_powershell() -> Set[int]:
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-Process mmain -ErrorAction SilentlyContinue "
             "| Select-Object -ExpandProperty Id"],
            capture_output=True, text=True, errors="replace", timeout=15,
        ).stdout
    except Exception:
        return set()
    result: Set[int] = set()
    for line in out.splitlines():
        line = line.strip()
        if line.isdigit():
            result.add(int(line))
    return result
