"""Тесты методов рестарта проекта (без COM).

Рестарт (checkpoint/restore) адресуется **идентификатором проекта**, поэтому
обёртки живут на `Project`. На живом SimInTech группа не проверена — тесты
фиксируют только контракт обёрток: имя COM-метода, порядок аргументов и
разбор [out]-значений. Смысл флагов и кодов возврата здесь не проверяется:
проверять его нечем, пока нет подтверждения с живого SimInTech.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest  # noqa: E402

from simintech_api.core.project import Project  # noqa: E402
from simintech_api.exceptions import ComCallError  # noqa: E402
from simintech_api.model import RestartNames  # noqa: E402


class FakeClient:
    """Клиент, записывающий вызовы; на запрос — заранее заданный ответ.

    Ответ по умолчанию — `None`: так выглядит COM-метод, который ничего не
    вернул, и это же поведение нужно командам группы (они ничего не отдают).
    """

    def __init__(self, answers=None):
        self.calls = []
        self._answers = answers or {}

    def call(self, name, *args):
        self.calls.append((name, *args))
        return self._answers.get(name)


def test_restart_files_pass_project_id_and_path():
    """Рестарт адресуется проектом, путь уходит вторым аргументом."""
    client = FakeClient()

    prj = Project(client, 42)
    prj.write_restart("save.rst")
    prj.read_restart("load.rst")

    assert client.calls == [
        ("WriteProjectRestart", 42, "save.rst"),
        ("ReadProjectRestart", 42, "load.rst"),
    ]


def test_restart_point_methods_address_the_project():
    """Точка рестарта — тоже операция проекта, без пути к файлу."""
    client = FakeClient({"ReadRestartPoint": 2.5})

    prj = Project(client, 42)
    code = prj.write_restart_point()
    point = prj.read_restart_point()

    assert client.calls == [
        ("WriteRestartPoint", 42),
        ("ReadRestartPoint", 42),
    ]
    assert code == 0            # COM ничего не вернул — это 0, а не падение
    assert point == 2.5


def test_restart_preserve_flag_passes_project_and_flag():
    client = FakeClient()

    Project(client, 42).set_restart_preserve_flag(1)

    assert client.calls == [("SetRestartPreserveFlag", 42, 1)]


def test_restart_file_settings_pass_path_and_flag():
    """Настройка файлов рестарта — отдельная пара методов, с флагом."""
    client = FakeClient()

    prj = Project(client, 42)
    prj.set_read_restart_file("in.rst", 1)
    prj.set_write_restart_file("out.rst", 0)

    assert client.calls == [
        ("SetProjectReadRestartFile", 42, "in.rst", 1),
        ("SetProjectWriteRestartFile", 42, "out.rst", 0),
    ]


def test_restart_names_unpacks_all_six_values():
    """Шесть [out]-значений раскладываются по полям, а не по позициям.

    Порядок взят из RIDL: два имени файла, два флага, время и флаг времени.
    Проверяется каждое значение — ошибка в любом из них должна быть видна.
    """
    client = FakeClient({"GetProjectRestartNames": (
        "read.rst", "write.rst", 1, 0, 2.5, 1,
    )})

    names = Project(client, 42).restart_names()

    assert isinstance(names, RestartNames)
    assert names.read_file == "read.rst"
    assert names.write_file == "write.rst"
    assert names.read_flag == 1
    assert names.write_flag == 0
    assert names.new_restart_time == 2.5
    assert names.set_new_time_flag == 1
    assert client.calls == [("GetProjectRestartNames", 42)]


def test_restart_names_keeps_values_as_they_came():
    """Флаги и время не перетолковываются: приходят как есть, из COM."""
    client = FakeClient({"GetProjectRestartNames": (
        "", "", 7, 3, 0, 2,
    )})

    names = Project(client, 42).restart_names()

    assert names.read_file == ""
    assert names.read_flag == 7        # не True: 7 — это не «да»
    assert names.write_flag == 3
    assert names.new_restart_time == 0.0
    assert names.set_new_time_flag == 2


@pytest.mark.parametrize("answer", [None, ()])
def test_restart_names_refuses_when_com_returned_nothing(answer):
    """Пустой результат — понятный отказ, а не TypeError из распаковки."""
    client = FakeClient({"GetProjectRestartNames": answer})

    with pytest.raises(ComCallError) as exc:
        Project(client, 42).restart_names()

    assert "GetProjectRestartNames" in str(exc.value)
    assert "6" in str(exc.value)      # сказано, сколько ожидалось


def test_restart_names_refuses_short_tuple():
    """Значений меньше шести — разбор сдвинулся бы, поэтому отказ."""
    client = FakeClient({"GetProjectRestartNames": ("read.rst", "write.rst", 1)})

    with pytest.raises(ComCallError) as exc:
        Project(client, 42).restart_names()

    assert "3" in str(exc.value)
    assert "6" in str(exc.value)


def test_restart_names_refuses_single_value_without_tuple():
    """Одиночное значение вместо шести — тоже отказ, а не молчаливый разбор."""
    client = FakeClient({"GetProjectRestartNames": "read.rst"})

    with pytest.raises(ComCallError):
        Project(client, 42).restart_names()
