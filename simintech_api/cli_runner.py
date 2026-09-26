"""Запуск SimInTech через командную строку (`mmain.exe`).

Резервный путь без COM: работает из WSL, где COM недоступен. Опции
документированы в справке SimInTech («Командная строка»). Вывод `mmain.exe`
приходит в cp1251 или cp866 — декодируется в `_decode`.

Перенесено из репозитория `simintech-connector` (заархивирован 2026-09-10).
"""

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass
class CLIResult:
    """Результат запуска mmain.exe через командную строку.

    Args:
        success: завершился ли процесс успешно.
        message: описание результата.
        data: ``{"stdout": ..., "stderr": ...}`` при наличии вывода.
    """

    success: bool
    message: str = ""
    data: Optional[Any] = None


#: Путь по умолчанию для окружения WSL. Вынесен в константу, чтобы его
#: можно было подменить в тестах: на машине с установленным SimInTech этот
#: файл существует, и проверка «mmain.exe не найден» иначе недостижима.
DEFAULT_MMAIN_PATH = Path("/mnt/c/SimInTech64/bin/mmain.exe")


def _check_arg(value: str, name: str, *, option_like: bool = False) -> str:
    """Отклонить значение, которое mmain.exe разберёт как лишний ключ.

    Часть опций передаётся одной строкой (`/saveas <путь>`,
    `/setparameter <имя> <значение>`), а mmain.exe разбирает собственную
    командную строку сам. Поэтому пробел или перевод строки внутри значения
    становится разделителем, и остаток превращается в отдельные опции —
    например, `out.xprt /close /exit` закрыло бы и завершило процесс.

    Args:
        value: проверяемое значение.
        name: имя параметра — попадает в сообщение об ошибке.
        option_like: отклонять ли значения, начинающиеся с `/` или `-`.
            Включается там, где ожидается имя или число, а не путь: путь
            может быть абсолютным (в WSL начинается с `/`).
    """
    if any(ch.isspace() or ord(ch) < 32 for ch in value):
        raise ValueError(
            f"{name}: пробелы и управляющие символы недопустимы — "
            f"mmain.exe разберёт их как разделители аргументов"
        )
    if option_like and value.startswith(("/", "-")):
        # Числа — исключение: отрицательное значение параметра начинается
        # с '-', но опцией не является. Отбраковывать его нельзя.
        if not _is_number(value):
            raise ValueError(
                f"{name}: значение не должно начинаться с '/' или '-' "
                f"(будет принято за опцию mmain.exe)"
            )
    return value


def _is_number(text: str) -> bool:
    """Похоже ли значение на число (в том числе отрицательное).

    Десятичный разделитель допускается и точкой, и запятой: SimInTech
    принимает оба.
    """
    try:
        float(text.replace(",", "."))
    except ValueError:
        return False
    return True


class CLIAdapter:
    """Адаптер для управления SimInTech через командную строку."""

    def __init__(self, mmain_path: Optional[str] = None, silent: bool = True):
        self.mmain_path = self._resolve_mmain_path(mmain_path)
        self.silent = silent
        self._project_path: Optional[str] = None

    @staticmethod
    def _resolve_mmain_path(custom_path: Optional[str]) -> str:
        if custom_path:
            p = Path(custom_path)
            if p.is_file():
                return str(p.absolute())
            elif p.is_dir():
                candidate = p / "mmain.exe"
                if candidate.exists():
                    return str(candidate)
        env_path = os.environ.get("SIMINTECH_PATH")
        if env_path:
            candidate = Path(env_path) / "mmain.exe"
            if candidate.exists():
                return str(candidate)
        env_home = os.environ.get("SIMINTECH")
        if env_home:
            candidate = Path(env_home) / "mmain.exe"
            if candidate.exists():
                return str(candidate)
        if DEFAULT_MMAIN_PATH.exists():
            return str(DEFAULT_MMAIN_PATH)
        msg = (
            "mmain.exe не найден. Укажите путь через SIMINTECH_PATH "
            "или передайте mmain_path в конструктор."
        )
        raise FileNotFoundError(msg)

    @staticmethod
    def _decode(data: bytes) -> str:
        """Декодировать вывод mmain.exe (Windows-1251 → UTF-8)."""
        for enc in ("cp1251", "cp866", "utf-8"):
            try:
                return data.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        return data.decode("utf-8", errors="replace")

    @property
    def is_available(self) -> bool:
        """Проверить, доступен ли mmain.exe."""
        return Path(self.mmain_path).exists()

    def build_cmd(self, *args: str) -> list[str]:
        """Собрать команду запуска mmain.exe с опциями."""
        cmd = [self.mmain_path]
        if self.silent:
            cmd.append("/silentmode")
        cmd.extend(args)
        return cmd

    def run_sync(self, *args: str, timeout: int = 300) -> CLIResult:
        """Запустить mmain.exe с опциями и дождаться завершения."""
        cmd = self.build_cmd(*args)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=False,  # binary mode — mmain.exe под WSL выводит в cp1251
                timeout=timeout,
            )
            stdout = self._decode(result.stdout)
            stderr = self._decode(result.stderr)
            if result.returncode == 0:
                return CLIResult(
                    success=True,
                    message="Команда выполнена успешно",
                    data={"stdout": stdout, "stderr": stderr},
                )
            return CLIResult(
                success=False,
                message=f"mmain.exe завершился с кодом {result.returncode}",
                data={"stdout": stdout, "stderr": stderr},
            )
        except subprocess.TimeoutExpired:
            return CLIResult(
                success=False,
                message=f"Тайм-аут ({timeout}с): mmain.exe не завершился вовремя",
            )
        except FileNotFoundError:
            return CLIResult(
                success=False,
                message=f"mmain.exe не найден: {self.mmain_path}",
            )

    def open_and_run(self, project_path: str, timeout: int = 300) -> CLIResult:
        """Открыть проект и запустить расчёт."""
        return self.run_sync(
            project_path,
            "/start",
            "/run",
            "/exitonstop",
            timeout=timeout,
        )

    def open_project(self, project_path: str, timeout: int = 30) -> CLIResult:
        """Открыть проект без запуска расчёта."""
        return self.run_sync(project_path, timeout=timeout)

    def run_project(self, project_path: str, timeout: int = 300) -> CLIResult:
        """Открыть проект, запустить расчёт, дождаться останова."""
        return self.open_and_run(project_path, timeout=timeout)

    def run_step(self, project_path: str, timeout: int = 60) -> CLIResult:
        """Выполнить один шаг синхронизации."""
        return self.run_sync(
            project_path,
            "/start",
            "/runstep",
            "/exitonstop",
            timeout=timeout,
        )

    def save_as(self, project_path: str, output_path: str,
                timeout: int = 30) -> CLIResult:
        """Открыть проект и сохранить в другом формате."""
        _check_arg(output_path, "output_path")
        return self.run_sync(
            project_path,
            f"/saveas {output_path}",
            "/close",
            "/exit",
            timeout=timeout,
        )

    def set_parameter(self, project_path: str, param: str, value: str,
                      timeout: int = 30) -> CLIResult:
        """Установить параметр проекта из командной строки."""
        _check_arg(param, "param", option_like=True)
        _check_arg(value, "value", option_like=True)
        return self.run_sync(
            project_path,
            f"/setparameter {param} {value}",
            "/close",
            "/exit",
            timeout=timeout,
        )

    # ─── Точки рестарта из командной строки ────────────────────────

    def save_restart(self, project_path: str, restart_path: str,
                     timeout: int = 300) -> CLIResult:
        """Открыть проект и сохранить точку рестарта (`/saverestart`).

        Порядок опций справка не задаёт. Берётся тот же, что у `/saveas`:
        файл проекта, затем опция с путём, затем закрытие. Поведение на живом
        SimInTech не проверено — справка не описывает ни формат файла
        рестарта, ни совместимость с обычным прогоном.
        """
        _check_arg(restart_path, "restart_path")
        return self.run_sync(
            project_path,
            f"/saverestart {restart_path}",
            "/close",
            "/exit",
            timeout=timeout,
        )

    def load_restart(self, project_path: str, restart_path: str,
                     timeout: int = 300) -> CLIResult:
        """Открыть проект с готовой точкой рестарта (`/loadrestart`).

        Смысл — продолжить расчёт с сохранённого состояния, не пересобирая
        модель. На живом SimInTech не проверено.
        """
        _check_arg(restart_path, "restart_path")
        return self.run_sync(
            project_path,
            f"/loadrestart {restart_path}",
            "/close",
            "/exit",
            timeout=timeout,
        )

    # ─── Кодогенерация ─────────────────────────────────────────────

    def generate_code(self, project_path: str,
                      output_dir: Optional[str] = None,
                      timeout: int = 600) -> CLIResult:
        """Сгенерировать программу для проекта (`/gencode`, `/cgsetoutdir`).

        Аргументов у `/gencode` и группы `/cg*` справка не описывает вовсе —
        известны только имена опций (проверено по шести страницам раздела
        «Командная строка»). Поэтому собирается минимальный набор: каталог
        вывода, если он задан, и сам запуск генерации; порядок взят из порядка
        строк таблицы справки (`cgsetoutdir` идёт до `cggenerate`).

        Требуется лицензия на кодогенерацию: без неё среда сообщит об отказе,
        и это отказ среды, а не ошибка вызова.

        Args:
            project_path: файл проекта.
            output_dir: куда положить сгенерированный код (`/cgsetoutdir`).
            timeout: больше обычного: сборка конфигурации долгая.
        """
        args = [project_path]
        if output_dir is not None:
            _check_arg(output_dir, "output_dir")
            args.append(f"/cgsetoutdir {output_dir}")
        args.extend(["/gencode", "/close", "/exit"])
        return self.run_sync(*args, timeout=timeout)

    def project_macro(self, macro_path: str, timeout: int = 300) -> CLIResult:
        """Запустить макрос в контексте проекта (`/projmacros`).

        Отличие от `/macros` справкой не объяснено: у `/projmacros` в описании
        явно сказано про путь к файлу, у `/macros` — нет, хотя путь принимают
        оба. Отдельный метод заведён, чтобы разницу можно было проверить
        опытом, а не догадкой.
        """
        macro_abs = str(Path(macro_path).absolute())
        _check_arg(macro_abs, "macro_path")
        return self.run_sync(f"/projmacros {macro_abs}", timeout=timeout)

    # ─── Работа с макросами ────────────────────────────────────────

    def run_macro_file(self, macro_path: str, timeout: int = 300) -> CLIResult:
        """Запустить файл макроса SimInTech (/macros)."""
        macro_abs = str(Path(macro_path).absolute())
        _check_arg(macro_abs, "macro_path")
        return self.run_sync(f"/macros {macro_abs}", timeout=timeout)

    def run_macro(self, macro_content: str, timeout: int = 300) -> CLIResult:
        """Запустить произвольный макрос (создаёт временный файл)."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(macro_content)
            tmp_path = f.name
        try:
            return self.run_macro_file(tmp_path, timeout=timeout)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    # ─── Работа с Linux/Wine ────────────────────────────────────────

    def run_with_wine(self, *args: str, timeout: int = 300) -> CLIResult:
        """Запустить mmain.exe через Wine (для Linux без WSL)."""
        cmd = ["wine", self.mmain_path]
        if self.silent:
            cmd.append("/silentmode")
        cmd.extend(args)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "WINEDLLOVERRIDES": "winemenubuilder.exe=d"},
            )
            return CLIResult(
                success=result.returncode == 0,
                message=f"Wine mmain.exe завершился с кодом {result.returncode}",
                data={"stdout": result.stdout, "stderr": result.stderr},
            )
        except FileNotFoundError:
            return CLIResult(
                success=False,
                message="Wine не найден. Установите wine для запуска "
                        "mmain.exe под Linux."
            )
        except subprocess.TimeoutExpired:
            return CLIResult(
                success=False,
                message=f"Тайм-аут Wine ({timeout}с)"
            )
