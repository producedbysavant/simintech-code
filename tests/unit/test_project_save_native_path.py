"""`Project.save_*`: путь COM-записи — в «родном» виде Windows.

Живой замер 05.10.2026: `SaveProjectXML` и `SaveProjectBinary` с путём «C:/…»
сообщают об успехе, **не создавая файла**; с «C:\\…» — пишут (тот же проект,
каталог и формат). `OpenProject` при этом прямые слэши принимает — строга
именно запись. Нормализуется в библиотеке, а не у каждого вызывающего.

Запись после вызова **проверяется** (`_require_written`): успех без файла —
отказ. Фейк поэтому моделирует переход «запись → файл появился», а не
подставляет один и тот же удобный ответ всем вызовам.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest  # noqa: E402

from simintech_api.core.project import Project, native_path  # noqa: E402
from simintech_api.exceptions import ProjectError  # noqa: E402


class _FakeClient:
    """Клиент, запоминающий вызовы; `write` — файл, который «пишет среда».

    `write=None` — среда молчит (ровно тот случай, ради которого появилась
    проверка), `write=<путь>` — после вызова файл создаётся.
    """

    def __init__(self, write=None):
        self.calls = []
        self._write = write

    def call(self, method, *args):
        self.calls.append((method, args))
        if self._write is not None:
            with open(self._write, "wb") as fh:
                fh.write(b"x")
        return 0


@pytest.mark.parametrize("method,invoke", [
    ("SaveProjectXML", lambda project, path: project.save_xml(path)),
    ("SaveProjectBinary", lambda project, path: project.save_binary(path)),
    ("ExportDBToXML", lambda project, path: project.export_db_to_xml(path)),
    ("WriteProjectRestart", lambda project, path: project.write_restart(path)),
])
def test_save_paths_reach_com_in_native_form(tmp_path, method, invoke):
    real = tmp_path / "sub" / "proj.out"
    real.parent.mkdir()
    client = _FakeClient(write=str(real))
    project = Project(client, 5)

    invoke(project, str(real))

    called, args = client.calls[0]
    assert called == method
    assert args[0] == 5
    assert "/" not in args[1] and "\\" in args[1], (
        f"путь к COM-записи не нормализован: {args[1]!r}")


def test_native_path_keeps_backslash_path():
    """Уже родной путь не портится (идемпотентность)."""
    assert native_path(r"C:\dir\sub\proj.xprt") == r"C:\dir\sub\proj.xprt"


def test_native_path_translates_slashes():
    """Прямые слэши переводятся в родные — независимо от ОС клиента."""
    assert native_path("C:/dir/sub/proj.xprt") == "C:\\dir\\sub\\proj.xprt"


def test_native_path_rejects_empty():
    """Пустой путь — отказ, а не «.»: `PureWindowsPath("")` — текущий каталог.

    Иначе среда приняла бы «.» за цель записи, и пустой путь клиента стал бы
    молчаливой записью не туда.
    """
    with pytest.raises(ValueError, match="пуст"):
        native_path("")
    with pytest.raises(ValueError, match="пуст"):
        native_path("   ")


def test_save_refuses_silent_success_without_file(tmp_path):
    """«Успех» без файла — отказ, а не ложное «сохранено».

    Ровно так среда отвечает на прямые слэши (замер 05.10.2026); после
    нормализации та же проверка ловит любой другой молчаливый отказ записи.
    """
    real = tmp_path / "proj.xprt"
    client = _FakeClient(write=None)
    project = Project(client, 5)

    with pytest.raises(ProjectError, match="файла .* нет"):
        project.save_xml(str(real))


def test_save_refuses_untouched_existing_file(tmp_path):
    """Существовавший файл обязан измениться — иначе перезаписи не было."""
    real = tmp_path / "proj.xprt"
    real.write_bytes(b"old")
    client = _FakeClient(write=None)
    project = Project(client, 5)

    with pytest.raises(ProjectError, match="не изменился"):
        project.save_binary(str(real))


def test_save_accepts_rewritten_existing_file(tmp_path):
    """Перезапись существующего файла принята: размер и время изменились."""
    real = tmp_path / "proj.xprt"
    real.write_bytes(b"old")
    client = _FakeClient(write=str(real))
    project = Project(client, 5)

    project.save_xml(str(real))

    assert real.read_bytes() == b"x"
