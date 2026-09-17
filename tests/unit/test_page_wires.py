"""Разделение блоков и линий связи на странице (без COM).

Перечисление объектов страницы (`GetPageObjectCount` + `GetPageBlockId`)
возвращает **все** объекты, включая линии: проверено на живом SimInTech64 —
после `CreateWire` счётчик вырастает на единицу, а по индексу линии приходит её
идентификатор с классом «Математическая связь». Пока это не учитывалось,
`get_blocks` отдавал линии как блоки (и они попадали в `list_blocks`).
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from simintech_api.core.page import Page  # noqa: E402


class ObjectClient:
    """Клиент страницы с заданным набором объектов.

    Args:
        objects: список троек (идентификатор, класс, имя).
        broken_props: идентификаторы, для которых чтение свойств падает.
    """

    def __init__(self, objects, broken_props=()):
        self.objects = list(objects)
        self.broken_props = set(broken_props)
        self.calls = []

    def call(self, method, *args):
        self.calls.append((method, args))
        if method == "GetPageObjectCount":
            return len(self.objects)
        if method == "GetPageBlockId":
            return self.objects[args[1]][0]
        if method == "GetBlockPropAsString":
            obj_id, prop = args[0], args[1]
            if obj_id in self.broken_props:
                from simintech_api.exceptions import ComCallError
                raise ComCallError(method, message="свойство недоступно")
            for oid, cls, name in self.objects:
                if oid == obj_id:
                    return cls if prop == "ClassName" else name
            return ""
        return 0


class FakeProject:
    id = 5

    def __init__(self, client):
        self.client = client


def _page(objects, **kwargs):
    client = ObjectClient(objects, **kwargs)
    return Page(FakeProject(client), 11), client


BLOCK = (101, "Усилитель", "kx_0")
WIRE = (202, "Математическая связь", "MBTYWire")
#: Тот же класс, но обрезанный — так его отдаёт COM в части вызовов.
WIRE_SHORT = (203, "Математическая", "MBTYWire1")


def test_get_blocks_skips_wires():
    """Линия не попадает в список блоков."""
    page, _ = _page([BLOCK, WIRE, WIRE_SHORT])

    assert [b.id for b in page.get_blocks()] == [BLOCK[0]]


def test_get_wires_returns_only_wires():
    """Линии отделены от блоков и возвращаются поимённо."""
    page, _ = _page([BLOCK, WIRE, WIRE_SHORT])

    assert sorted(w.id for w in page.get_wires()) == [WIRE[0], WIRE_SHORT[0]]


def test_page_without_wires_gives_empty_list():
    page, _ = _page([BLOCK])

    assert page.get_wires() == []
    assert [b.id for b in page.get_blocks()] == [BLOCK[0]]


def test_wire_is_recognised_by_name_when_class_is_unreadable():
    """Если класс прочитать не удалось, линия узнаётся по имени объекта.

    Имя `MBTYWire` — внутреннее имя линии; на живой сборке оно есть всегда.
    Без запасного признака такая линия считалась бы блоком.
    """
    page, _ = _page([(204, "", "MBTYWire7"), BLOCK])

    assert [w.id for w in page.get_wires()] == [204]


def test_wire_class_comparison_is_by_prefix():
    """Сверка идёт по началу строки: COM отдаёт и полное имя, и обрезанное.

    Равенство с «Математическая связь» пропустило бы обрезанный вариант, и
    линия снова стала бы блоком.
    """
    page, _ = _page([WIRE_SHORT])

    assert len(page.get_wires()) == 1


def test_broken_property_read_does_not_break_enumeration():
    """Отказ чтения свойств не роняет перечисление — объект просто не линия."""
    page, _ = _page([(303, "Усилитель", "k_0")], broken_props=[303])

    assert page.get_blocks() and page.get_wires() == []


def test_object_count_is_asked_for_project_not_page():
    """Идентификатор проекта, а не страницы: со страницей счётчик даёт 0.

    Проверено на живом SimInTech64: `GetPageObjectCount(page_id)` вернул 0 при
    двух созданных блоках, `GetPageObjectCount(project_id)` — 9.
    """
    page, client = _page([BLOCK])

    page.get_blocks()

    count_calls = [c for c in client.calls if c[0] == "GetPageObjectCount"]
    assert count_calls and count_calls[0][1] == (5,)
