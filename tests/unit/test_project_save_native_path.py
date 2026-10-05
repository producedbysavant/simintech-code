"""`Project.save_*`: путь COM-записи — в «родном» виде Windows.

Живой замер 05.10.2026: `SaveProjectXML` и `SaveProjectBinary` с путём «C:/…»
сообщают об успехе, **не создавая файла**; с «C:\\…» — пишут (тот же проект,
каталог и формат). `OpenProject` при этом прямые слэши принимает — строга
именно запись. Нормализуется в библиотеке, а не у каждого вызывающего.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest  # noqa: E402

from simintech_api.core.project import Project  # noqa: E402


class _FakeClient:
    """Клиент, запоминающий вызовы; ответ — 0."""

    def __init__(self):
        self.calls = []

    def call(self, method, *args):
        self.calls.append((method, args))
        return 0


@pytest.mark.parametrize("method,invoke", [
    ("SaveProjectXML", lambda project: project.save_xml("C:/dir/sub/proj.xprt")),
    ("SaveProjectBinary",
     lambda project: project.save_binary("C:/dir/sub/proj.prt")),
    ("ExportDBToXML",
     lambda project: project.export_db_to_xml("C:/dir/sub/signals.xml")),
])
def test_save_paths_reach_com_in_native_form(method, invoke):
    client = _FakeClient()
    project = Project(client, 5)

    invoke(project)

    called, args = client.calls[0]
    assert called == method
    assert args[0] == 5
    assert "/" not in args[1] and "\\" in args[1], (
        f"путь к COM-записи не нормализован: {args[1]!r}")


def test_native_path_keeps_backslash_path():
    """Уже родной путь не портится (идемпотентность)."""
    client = _FakeClient()
    project = Project(client, 5)

    project.save_xml(r"C:\dir\sub\proj.xprt")

    assert client.calls[0][1][1] == r"C:\dir\sub\proj.xprt"
