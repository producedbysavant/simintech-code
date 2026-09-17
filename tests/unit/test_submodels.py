"""Тесты субмоделей и переходов по страницам (без COM).

Субмодель адресуется **блоком**: страницу субмодели даёт `GetSubmodelPage`,
сама субмодель берётся из файла. Поэтому обёртки принимают идентификатор
блока явно (`Project.submodel_page`, `load_submodel`, `assign_submodel`), а
переход на родительскую страницу живёт на `Page`. На живом SimInTech группа
не проверена — тесты фиксируют только контракт обёрток.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest  # noqa: E402

from simintech_api.core.page import Page  # noqa: E402
from simintech_api.core.project import Project  # noqa: E402
from simintech_api.exceptions import ComCallError, PageError  # noqa: E402


class FakeClient:
    """Клиент, записывающий вызовы; на запрос — заранее заданный ответ."""

    def __init__(self, answers=None):
        self.calls = []
        self._answers = answers or {}

    def call(self, name, *args):
        self.calls.append((name, *args))
        return self._answers.get(name)


def test_submodel_page_asks_by_block_id():
    """`GetSubmodelPage` принимает идентификатор блока, а не страницы."""
    client = FakeClient({"GetSubmodelPage": (777,)})

    page = Project(client, 42).submodel_page(5)

    assert client.calls == [("GetSubmodelPage", 5)]
    assert isinstance(page, Page)
    assert page.id == 777
    assert page.project.id == 42


def test_submodel_page_refuses_zero_page():
    """Нулевая страница — не страница: отказ, а не объект с id=0."""
    client = FakeClient({"GetSubmodelPage": (0,)})

    with pytest.raises(PageError) as exc:
        Project(client, 42).submodel_page(5)

    assert "5" in str(exc.value)      # сказано, для какого блока


@pytest.mark.parametrize("answer", [None, ()])
def test_submodel_page_refuses_when_com_returned_nothing(answer):
    """Пустой результат — понятный отказ, а не TypeError из индексации."""
    client = FakeClient({"GetSubmodelPage": answer})

    with pytest.raises(ComCallError) as exc:
        Project(client, 42).submodel_page(5)

    assert "GetSubmodelPage" in str(exc.value)


def test_load_submodel_passes_block_and_path():
    """`LoadSubmodel` — блок и файл, без идентификатора проекта."""
    client = FakeClient()

    Project(client, 42).load_submodel(5, "sub.prt")

    assert client.calls == [("LoadSubmodel", 5, "sub.prt")]


def test_assign_submodel_passes_project_block_and_path():
    """`AssignSubmodel` — проект, блок и файл; порядок аргументов из RIDL."""
    client = FakeClient()

    Project(client, 42).assign_submodel(5, "sub.prt")

    assert client.calls == [("AssignSubmodel", 42, 5, "sub.prt")]


def test_page_parent_returns_page_of_the_same_project():
    client = FakeClient({"PageUp": (9,)})
    page = Page(Project(client, 42), 7)

    parent = page.parent()

    assert client.calls == [("PageUp", 7)]
    assert parent is not None
    assert parent.id == 9
    assert parent.project is page.project


def test_page_parent_is_none_for_top_page():
    """Нулевая страница трактуется как отсутствие родителя (главная страница)."""
    client = FakeClient({"PageUp": (0,)})

    assert Page(Project(client, 42), 7).parent() is None


@pytest.mark.parametrize("answer", [None, ()])
def test_page_parent_refuses_when_com_returned_nothing(answer):
    """Пустой результат — другая сигнатура, а не «родителя нет»."""
    client = FakeClient({"PageUp": answer})

    with pytest.raises(ComCallError) as exc:
        Page(Project(client, 42), 7).parent()

    assert "PageUp" in str(exc.value)
