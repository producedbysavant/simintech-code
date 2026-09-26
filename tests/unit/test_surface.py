"""Публичная поверхность пакета: корень экспортирует все классы исключений.

`docs/api.md:3` и `docs/source/api.rst:4` обещают доступность всех классов
исключений из корня `simintech_api`, а `LayoutError` из этого набора выпал: он
был объявлен в `.exceptions`, но отсутствовал и в импорте корня, и в `__all__`.
Отказ громкий (`ImportError`/`AttributeError`), но натыкается на него только
тот, кто пишет код по документации, поэтому набор закреплён тестом — иначе
пропуск ничем не ловится (`grep -rn '__all__' tests/` до этого теста был пуст).
"""

import inspect
import os
import pathlib
import re
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import simintech_api  # noqa: E402
from simintech_api import exceptions  # noqa: E402
from simintech_api import topology as topology_module  # noqa: E402


def _exception_classes():
    """Имена классов исключений, объявленных в `simintech_api.exceptions`."""
    return sorted(
        name for name, obj in vars(exceptions).items()
        if inspect.isclass(obj) and issubclass(obj, Exception)
        and obj.__module__ == exceptions.__name__
    )


def test_all_exception_classes_exported_at_package_root():
    names = _exception_classes()
    # Страховка от вырождения теста: пустой или урезанный набор прошёл бы
    # проверки ниже, ничего не проверив.
    assert "LayoutError" in names
    assert len(names) >= 13

    not_imported = [n for n in names if not hasattr(simintech_api, n)]
    assert not_imported == [], f"нет в корне пакета: {not_imported}"

    not_in_all = [n for n in names if n not in simintech_api.__all__]
    assert not_in_all == [], f"нет в __all__: {not_in_all}"

    for name in names:
        # Именно тот же объект, а не одноимённая копия.
        assert getattr(simintech_api, name) is getattr(exceptions, name)


def test_layout_error_is_the_exported_class():
    """LayoutError — тот самый класс, ради которого заведён тест."""
    assert simintech_api.LayoutError is exceptions.LayoutError


# Заметка выпуска 0.4.0 объявляет публичным API топологии `read_topology`,
# `Topology`, `ObjectRow`, `PortRow`, `Connection`. Из корня пакета был
# реэкспортирован только `TopologyError` — то же расхождение текста выпуска с
# кодом, что и с `LayoutError` выше, и так же незаметное: имена достижимы по
# внутренним путям (`simintech_api.topology.Topology`), поэтому `ImportError`
# не возникает ни у кого, кроме того, кто пишет код по обещанию выпуска.
#
# Проверка читает заметку выпуска как текст и требует ровно то, что она
# обещает: перечень в ней — источник истины, а не список в тесте, иначе они
# разойдутся так же молча.

RELEASE_NOTE_ANCHOR = "добавлен публичный API топологии:"

#: Публичный API топологии, объявленный **выпуском** 0.4.0. Набор закреплён
#: дословно, потому что это выпущенный контракт, а не текущее содержимое
#: заметки. Без этого сверка заметки с кодом — проверка равенства текста
#: самому себе: имя, убранное сразу из заметки, импорта и `__all__`, не
#: роняет набор из пяти оставшихся, и публичный API молча укорачивается —
#: ровно то, что выпуск обещал не делать (в 0.x удаление допустимо, но
#: названное явно, а не прошедшее по недосмотру).
RELEASED_TOPOLOGY_API = (
    "read_topology",
    "Topology",
    "ObjectRow",
    "PortRow",
    "Connection",
    "TopologyError",
)


def _declared_topology_api():
    """Имена, объявленные публичным API топологии в заметке выпуска 0.4.0."""
    path = (pathlib.Path(__file__).resolve().parents[2]
            / "simintech_api" / "__init__.py")
    text = path.read_text(encoding="utf-8")
    assert RELEASE_NOTE_ANCHOR in text, (
        "в заметке выпуска нет объявления публичного API топологии — "
        "тест разошёлся с источником"
    )
    claim = text.split(RELEASE_NOTE_ANCHOR, 1)[1].split(".", 1)[0]
    return re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", claim)


def test_release_note_matches_released_topology_api():
    """Заметка выпуска перечисляет ровно выпущенный набор — в обе стороны.

    Ослабленная версия (`len(declared) >= 5` плюс пара имён поимённо)
    пропускала удаление `Connection` из всех трёх мест сразу: набор из пяти
    имён проходил её целиком. Сверка с закреплённым набором ловит и пропажу,
    и незаявленное добавление.
    """
    declared = set(_declared_topology_api())
    released = set(RELEASED_TOPOLOGY_API)

    assert declared == released, (
        f"заметка выпуска разошлась с выпущенным контрактом: "
        f"лишние — {sorted(declared - released)}, "
        f"пропали — {sorted(released - declared)}"
    )


def test_declared_topology_api_is_exported():
    """Объявленное публичным API топологии достижимо из корня пакета."""
    declared = RELEASED_TOPOLOGY_API

    not_imported = [n for n in declared if not hasattr(simintech_api, n)]
    assert not_imported == [], f"объявлены публичными, но нет в корне: {not_imported}"

    not_in_all = [n for n in declared if n not in simintech_api.__all__]
    assert not_in_all == [], f"нет в __all__: {not_in_all}"


def test_topology_types_are_the_exported_ones():
    """Реэкспортированы те же объекты, а не одноимённые копии."""
    for name in ("ObjectRow", "PortRow", "Connection", "Topology"):
        assert getattr(simintech_api, name) is getattr(topology_module, name)
