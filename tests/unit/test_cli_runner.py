"""Тесты CLI-обёртки над mmain.exe (без запуска SimInTech)."""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest  # noqa: E402

from simintech_api import cli_runner  # noqa: E402
from simintech_api.cli_runner import CLIAdapter, CLIResult  # noqa: E402


@pytest.fixture()
def no_mmain(monkeypatch, tmp_path):
    """Сделать так, чтобы mmain.exe не нашёлся нигде.

    Путь по умолчанию подменяется: на машине с установленным SimInTech он
    существует, и без подмены ветка «не найден» недостижима.
    """
    monkeypatch.delenv("SIMINTECH_PATH", raising=False)
    monkeypatch.delenv("SIMINTECH", raising=False)
    monkeypatch.setattr(cli_runner, "DEFAULT_MMAIN_PATH",
                        tmp_path / "нет" / "mmain.exe")
    return tmp_path / "нет" / "mmain.exe"


def test_decode_handles_cp1251():
    """Вывод mmain.exe приходит в cp1251 — русский текст читается."""
    raw = "Ошибка расчёта".encode("cp1251")

    assert CLIAdapter._decode(raw) == "Ошибка расчёта"


def test_decode_falls_back_to_utf8():
    assert CLIAdapter._decode("OK".encode("utf-8")) == "OK"


def test_decode_survives_broken_bytes():
    """Битый вывод не должен ронять разбор."""
    assert isinstance(CLIAdapter._decode(b"\xff\xfe\xfd\x00"), str)


def test_build_cmd_adds_silentmode():
    cli = CLIAdapter(mmain_path=__file__)

    cmd = cli.build_cmd("/start", "/run")

    assert cmd[0] == str(Path(__file__).absolute())
    assert cmd[1] == "/silentmode"
    assert cmd[2:] == ["/start", "/run"]


def test_build_cmd_without_silentmode():
    cli = CLIAdapter(mmain_path=__file__, silent=False)

    assert cli.build_cmd("/exit") == [str(Path(__file__).absolute()), "/exit"]


def test_resolve_mmain_path_accepts_directory(tmp_path):
    """Если передан каталог — ищется mmain.exe внутри."""
    (tmp_path / "mmain.exe").write_bytes(b"")

    cli = CLIAdapter(mmain_path=str(tmp_path))

    assert cli.mmain_path.endswith("mmain.exe")


def test_resolve_mmain_path_uses_env(monkeypatch, tmp_path):
    """Переменная SIMINTECH_PATH имеет приоритет над путём по умолчанию."""
    (tmp_path / "mmain.exe").write_bytes(b"")
    monkeypatch.setenv("SIMINTECH_PATH", str(tmp_path))

    cli = CLIAdapter()

    assert cli.mmain_path.endswith("mmain.exe")


def test_resolve_mmain_path_raises_when_missing(no_mmain):
    with pytest.raises(FileNotFoundError, match="mmain.exe не найден"):
        CLIAdapter()


def test_run_sync_reports_missing_binary(no_mmain):  # noqa: D103
    """Несуществующий бинарник — результат с success=False, а не исключение."""
    # Создаём с валидным путём и подменяем после: конструктор сам проверяет
    # наличие mmain.exe и на отсутствующем бросил бы исключение раньше.
    cli = CLIAdapter(mmain_path=__file__)
    cli.mmain_path = str(no_mmain)

    result = cli.run_sync("/exit", timeout=5)

    assert isinstance(result, CLIResult)
    assert result.success is False
    assert "не найден" in result.message


# ─── Защита от подстановки лишних опций ───────────────────────────

def _cli():
    """Адаптер с валидным путём (сам mmain.exe не запускается)."""
    return CLIAdapter(mmain_path=__file__)


def test_set_parameter_rejects_whitespace_in_value():
    """Пробел в значении породил бы лишние опции mmain.exe.

    Опции передаются одной строкой («/setparameter имя значение»), а
    mmain.exe разбирает командную строку сам — поэтому пробел внутри
    значения становится разделителем аргументов.
    """
    with pytest.raises(ValueError, match="пробел"):
        _cli().set_parameter("model.prt", "Kp", "1.5 /close /exit")


# ─── Рестарты и кодогенерация ─────────────────────────────────────

def _capture(cli):
    """Подменить запуск процесса и вернуть место, куда пишутся аргументы."""
    calls = {}

    def fake_run_sync(*args, **kwargs):
        calls["args"] = args
        return CLIResult(success=True)

    cli.run_sync = fake_run_sync
    return calls


def test_save_restart_passes_path_and_closes():
    """`/saverestart` получает путь, процесс закрывается и завершается."""
    cli = _cli()
    calls = _capture(cli)

    cli.save_restart("model.prt", "C:\\rst\\model.rst")

    assert calls["args"] == ("model.prt", "/saverestart C:\\rst\\model.rst",
                             "/close", "/exit")


def test_load_restart_passes_path_and_closes():
    """`/loadrestart` отличается от `/saverestart` только опцией."""
    cli = _cli()
    calls = _capture(cli)

    cli.load_restart("model.prt", "rst.rst")

    assert calls["args"][1] == "/loadrestart rst.rst"


def test_restart_rejects_whitespace_in_path():
    """Пробел в пути рестарта породил бы лишние опции mmain.exe."""
    with pytest.raises(ValueError, match="пробел"):
        _cli().save_restart("model.prt", "rst.rst /exit")


def test_generate_code_puts_outdir_before_gencode():
    """Каталог вывода задаётся до генерации — так задан порядок в справке.

    Аргументов у `/gencode` и `/cg*` справка не описывает вовсе, поэтому
    проверяется ровно то, что мы решили: минимальный набор и порядок.
    """
    cli = _cli()
    calls = _capture(cli)

    cli.generate_code("model.prt", output_dir="C:\\gen")

    assert calls["args"] == ("model.prt", "/cgsetoutdir C:\\gen", "/gencode",
                             "/close", "/exit")


def test_generate_code_without_outdir_omits_the_option():
    """Без каталога опция не подставляется: пустой путь сломал бы разбор."""
    cli = _cli()
    calls = _capture(cli)

    cli.generate_code("model.prt")

    assert calls["args"] == ("model.prt", "/gencode", "/close", "/exit")


def test_generate_code_waits_longer_than_usual():
    """Сборка конфигурации дольше обычной операции — таймаут по умолчанию больше."""
    cli = _cli()
    seen = {}

    def fake_run_sync(*args, **kwargs):
        seen.update(kwargs)
        return CLIResult(success=True)

    cli.run_sync = fake_run_sync
    cli.generate_code("model.prt")

    assert seen["timeout"] > 300


def test_project_macro_uses_its_own_option():
    """`/projmacros` — отдельная опция, а не `/macros`: их различие и проверяем."""
    cli = _cli()
    calls = _capture(cli)
    macro = str(Path(__file__).parent / "macro.txt")

    cli.project_macro(macro)

    assert calls["args"][0].startswith("/projmacros ")


def test_project_macro_rejects_whitespace_in_path():
    with pytest.raises(ValueError):
        _cli().project_macro("/tmp/macro.txt /exit")


def test_set_parameter_rejects_option_like_param():
    with pytest.raises(ValueError):
        _cli().set_parameter("model.prt", "/exit", "1")


def test_set_parameter_rejects_option_like_value():
    with pytest.raises(ValueError):
        _cli().set_parameter("model.prt", "Kp", "/exit")


def test_set_parameter_rejects_control_characters():
    with pytest.raises(ValueError):
        _cli().set_parameter("model.prt", "Kp", "1\n/exit")


def test_save_as_rejects_whitespace_in_path():
    with pytest.raises(ValueError, match="пробел"):
        _cli().save_as("model.prt", "out.xprt /close /exit")


def test_run_macro_file_rejects_whitespace_in_path():
    with pytest.raises(ValueError):
        _cli().run_macro_file("/tmp/macro.txt /exit")


def test_normal_values_pass_validation(monkeypatch):
    """Обычные значения не отбраковываются: защита не ломает работу."""
    calls = {}
    cli = _cli()

    def fake_run_sync(*args, **kwargs):
        calls["args"] = args
        return CLIResult(success=True)

    monkeypatch.setattr(cli, "run_sync", fake_run_sync)

    cli.set_parameter("model.prt", "Kp", "1.5")
    assert calls["args"] == ("model.prt", "/setparameter Kp 1.5",
                             "/close", "/exit")

    cli.save_as("model.prt", "C:\\out.xprt")
    assert calls["args"][1] == "/saveas C:\\out.xprt"


# ─── Отрицательные значения не должны отбраковываться ─────────────

@pytest.mark.parametrize("value", ["-1.5", "-3", "-0.5", "-1,5", "-1e-3"])
def test_set_parameter_allows_negative_numbers(value):
    """Уставка бывает отрицательной: '-1.5' — значение, а не опция.

    Защита от подстановки опций отклоняет значения с ведущим '-' или '/',
    но числа — исключение, иначе запись отрицательного параметра ломалась бы.
    """
    calls = {}
    cli = _cli()

    def fake_run_sync(*args, **kwargs):
        calls["args"] = args
        return CLIResult(success=True)

    cli.run_sync = fake_run_sync
    cli.set_parameter("model.prt", "Kp", value)

    assert calls["args"][1] == f"/setparameter Kp {value}"


@pytest.mark.parametrize("value", ["-exit", "/exit", "--force", "/close"])
def test_set_parameter_rejects_non_numeric_option_like(value):
    """Похожее на ключ, но не число — по-прежнему отклоняется."""
    with pytest.raises(ValueError):
        _cli().set_parameter("model.prt", "Kp", value)


@pytest.mark.parametrize("param", ["/exit", "-exit", "/close"])
def test_param_name_rejects_option_like(param):
    """Имя параметра опцией быть не может, послабления для чисел тут не нужны."""
    with pytest.raises(ValueError):
        _cli().set_parameter("model.prt", param, "5")
