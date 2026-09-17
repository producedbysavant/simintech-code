"""Тесты пакета проектов (без COM).

Пакет адресуется **своим** идентификатором, а не идентификатором проекта:
раньше операции пакета жили на `Simulation` и передавали в COM id проекта, из-за
чего путь пакетов был недостижим, а вызовы — молча неверными.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest  # noqa: E402

from simintech_api.core.pack import Pack  # noqa: E402
from simintech_api.core.simulation import Simulation  # noqa: E402
from simintech_api.exceptions import PackError  # noqa: E402


class FakeClient:
    """Клиент, записывающий вызовы; на запрос — заранее заданный ответ."""

    def __init__(self, answers=None):
        self.calls = []
        self._answers = answers or {}

    def call(self, name, *args):
        self.calls.append((name, *args))
        return self._answers.get(name, 0)

    def close_pack(self, pack_id):
        self.calls.append(("ClosePack", pack_id))


def test_pack_project_ids_reads_count_and_indexes():
    client = FakeClient({"PackGetProjCount": 3})

    pack = Pack(client, 42)

    assert pack.project_count() == 3
    assert pack.project_ids() == [0, 0, 0]
    assert ("PackGetProjCount", 42) in client.calls
    assert ("PackGetProjectIdByIndex", 42, 2) in client.calls


def test_pack_operations_address_the_pack_not_a_project():
    """Все операции идут с идентификатором пакета — в этом и был дефект."""
    client = FakeClient()

    pack = Pack(client, 42)
    pack.start().run().step().pause().stop()

    assert client.calls == [
        ("PackStart", 42), ("PackRun", 42), ("PackStep", 42),
        ("PackPause", 42), ("PackStop", 42),
    ]


def test_pack_close():
    client = FakeClient()

    Pack(client, 42).close()

    assert client.calls == [("ClosePack", 42)]


def test_pack_run_to_returns_wait_result():
    client = FakeClient({"WaitForTimePack": 1})

    assert Pack(client, 42).run_to(5.0) is True
    assert ("RunToPack", 42, 5.0) in client.calls
    assert ("WaitForTimePack", 42, 5.0) in client.calls


def test_pack_require_open_refuses_closed_pack():
    with pytest.raises(PackError):
        Pack(FakeClient(), 0).require_open()


@pytest.mark.parametrize("method", ["pack_start", "pack_run", "pack_step",
                                    "pack_pause", "pack_stop", "run_to_pack"])
def test_simulation_pack_methods_refuse_and_point_to_pack(method):
    """Методы пакета на `Simulation` отказывают, а не делают вид, что работают.

    Они передавали в COM идентификатор проекта — обращение шло не туда, и
    вызывающий получал молчаливое «ничего не произошло». Тихая неверная
    операция хуже отсутствующей, поэтому здесь отказ со ссылкой на `Pack`.
    """
    sim = Simulation(FakeClient(), 7)
    args = [5.0] if method == "run_to_pack" else []

    with pytest.raises(PackError) as exc:
        getattr(sim, method)(*args)

    assert "Pack" in str(exc.value)
    assert "open_pack" in str(exc.value)
