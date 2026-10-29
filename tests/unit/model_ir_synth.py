"""Синтетические модели Model IR для проверок масштаба.

Генераторы детерминированы и не трогают файловую систему: одинаковые
аргументы дают байт-идентичный текст. Ожидаемые числа считаются при
эмиссии, а не повторным разбором IR: иначе тест повторял бы допущение
парсера.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SynthModel:
    text: str
    expected: dict[str, Any]
    addresses: dict[str, str] = field(default_factory=dict)


def _object(name: str, class_name: str, obj_type: int,
            ports: tuple[tuple[str, int], ...] = ()) -> str:
    body = "".join(
        f"<port><name>`{port_name}`</name><mode>`{mode}`</mode></port>"
        for port_name, mode in ports)
    port_block = f"<ports>{body}</ports>" if body else ""
    return (f"<object><name>`{name}`</name>"
            f"<class_name>`{class_name}`</class_name>"
            f"<obj_type>`{obj_type}`</obj_type>{port_block}</object>")


def _wire(name: str, start: int, start_port: int,
          end: int, end_port: int) -> str:
    return (f"<object><name>`{name}`</name>"
            f"<class_name>`Математическая связь`</class_name>"
            f"<obj_type>`101`</obj_type>"
            f"<start_bl_index>`{start}`</start_bl_index>"
            f"<start_port_index>`{start_port}`</start_port_index>"
            f"<end_bl_index>`{end}`</end_bl_index>"
            f"<end_port_index>`{end_port}`</end_port_index></object>")


def _wrap(body: str) -> str:
    return f"<Header><project><page>{body}</page></project></Header>"


def _base_expected(**overrides: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "containers": 1,
        "objects": 0,
        "ports_real": 0,
        "ports_synthetic": 0,
        "wires": 0,
        "branches": 0,
        "decorations": 0,
        "block_image_pages": 0,
        "block_image_objects": 0,
        "unresolved_ends": 0,
        "unconnected_ends": 0,
        "unresolved_branches": 0,
        "unknown_object_types": 0,
        "external_submodels": 0,
        "source_status": "ok",
    }
    result.update(overrides)
    return result


def flat_model(objects: int) -> SynthModel:
    """Цепочка из блоков: у каждого вход u и выход y."""
    parts = []
    for index in range(objects):
        parts.append(_object(
            f"B{index}", "Усилитель", 100,
            (("u", 0), ("y", 1))))
    for index in range(objects - 1):
        parts.append(_wire(f"W{index}", index, 1, index + 1, 0))
    return SynthModel(
        text=_wrap("".join(parts)),
        expected=_base_expected(
            objects=objects, ports_real=objects * 2,
            wires=max(0, objects - 1)),
        addresses={"first": "main::B0",
                   "last": f"main::B{objects - 1}"})


def loose_model(objects: int) -> SynthModel:
    """Блоки без проводов: каждый вход и выход висит."""
    parts = [
        _object(f"B{index}", "Усилитель", 100, (("u", 0), ("y", 1)))
        for index in range(objects)
    ]
    return SynthModel(
        text=_wrap("".join(parts)),
        expected=_base_expected(objects=objects, ports_real=objects * 2),
        addresses={"last": f"main::B{objects - 1}"})


def star_model(sinks: int) -> SynthModel:
    """Один источник и веер ветвей к приёмникам."""
    parts = [_object("S", "Константа", 100, (("y", 1),))]
    parts.extend(
        _object(f"T{index}", "Временной график", 106, (("u", 0),))
        for index in range(sinks))
    parts.append(_wire("W0", 0, 0, 1, 0))
    for index in range(1, sinks):
        parts.append(
            f"<object><name>`W{index}`</name>"
            f"<class_name>`Математическая связь`</class_name>"
            f"<obj_type>`101`</obj_type>"
            f"<start_bl_index>`-1`</start_bl_index>"
            f"<start_port_index>`0`</start_port_index>"
            f"<parent_wire_name>`W0`</parent_wire_name>"
            f"<parent_wire_index>`0`</parent_wire_index>"
            f"<parentwirenode>`0`</parentwirenode>"
            f"<end_bl_index>`{index + 1}`</end_bl_index>"
            f"<end_port_index>`0`</end_port_index></object>")
    return SynthModel(
        text=_wrap("".join(parts)),
        expected=_base_expected(
            objects=1 + sinks, ports_real=1 + sinks,
            wires=sinks, branches=max(0, sinks - 1)),
        addresses={"source": "main::S",
                   "last_sink": f"main::T{sinks - 1}"})


def direct_star_model(sinks: int) -> SynthModel:
    """Один источник и прямые провода к каждому приёмнику."""
    parts = [_object("S", "Константа", 100, (("y", 1),))]
    parts.extend(
        _object(f"T{index}", "Временной график", 106, (("u", 0),))
        for index in range(sinks))
    parts.extend(
        _wire(f"W{index}", 0, 0, index + 1, 0)
        for index in range(sinks))
    return SynthModel(
        text=_wrap("".join(parts)),
        expected=_base_expected(
            objects=1 + sinks, ports_real=1 + sinks, wires=sinks),
        addresses={"source": "main::S",
                   "last_sink": f"main::T{sinks - 1}"})


def cycle_model() -> SynthModel:
    """Два блока, связанных встречными проводами."""
    parts = [
        _object("A", "Усилитель", 100, (("u", 0), ("y", 1))),
        _object("B", "Усилитель", 100, (("u", 0), ("y", 1))),
        _wire("W1", 0, 1, 1, 0),
        _wire("W2", 1, 1, 0, 0),
    ]
    return SynthModel(
        text=_wrap("".join(parts)),
        expected=_base_expected(objects=2, ports_real=4, wires=2),
        addresses={"a": "main::A", "b": "main::B"})


def deep_model(levels: int) -> SynthModel:
    """Вложенные субмодели: на каждом уровне In, K, Out и следующая Sub."""
    def page(level: int) -> str:
        parts = [
            _object("In", "Порт входа", 103, (("x", 1),)),
            _object("K", "Усилитель", 100, (("u", 0), ("y", 1))),
            _object("Out", "Порт выхода", 103, (("y", 0),)),
            _wire("w1", 0, 0, 1, 0),
            _wire("w2", 1, 1, 2, 0),
        ]
        if level < levels:
            parts.append(
                f"<object><name>`S{level}`</name>"
                f"<class_name>`Субмодель`</class_name>"
                f"<obj_type>`102`</obj_type>"
                f"<page><name></name>{page(level + 1)}</page></object>")
        return "".join(parts)

    return SynthModel(
        text=_wrap(page(0)),
        expected=_base_expected(
            containers=levels + 1,
            objects=4 * levels + 3,
            ports_real=4 * (levels + 1),
            wires=2 * (levels + 1)),
        addresses={"deepest": "main"})


def wide_model(submodels: int) -> SynthModel:
    """Много субмоделей первого уровня, по одному блоку внутри."""
    parts = []
    for index in range(submodels):
        child = _object(f"K{index}", "Усилитель", 100)
        parts.append(
            f"<object><name>`S{index}`</name>"
            f"<class_name>`Субмодель`</class_name>"
            f"<obj_type>`102`</obj_type><page><name></name>"
            f"{child}</page></object>")
    return SynthModel(
        text=_wrap("".join(parts)),
        expected=_base_expected(
            containers=submodels + 1, objects=submodels * 2),
        addresses={"first": "main::S0",
                   "last": f"main::S{submodels - 1}"})
