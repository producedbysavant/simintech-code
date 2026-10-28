"""Идентификаторы, адреса и хеши Model IR.

Идентификатор не зависит от порядка словарей и от момента сборки. Он строится
по адресу и порядку, а не по имени провода или необязательному uid: имена
проводов в выгрузке повторяются, а uid заполнен не у всех объектов.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .ir import ModelIR


def _short(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def container_id(address: str) -> str:
    return "c:" + _short("container:" + address)


def object_id(container_id: str, order: int) -> str:
    return "o:" + _short(f"object:{container_id}:{order}")


def port_id(object_id: str, index: int) -> str:
    return f"p:{object_id}:{index}"


def wire_id(container_id: str, order: int) -> str:
    return "w:" + _short(f"wire:{container_id}:{order}")


def boundary_id(submodel_object_id: str, external_index: int) -> str:
    return "b:" + _short(f"boundary:{submodel_object_id}:{external_index}")


def memory_id(variable: str) -> str:
    return "m:" + _short("memory:" + variable)


def decoration_id(container_id: str, order: int) -> str:
    return "d:" + _short(f"decoration:{container_id}:{order}")


def canonical(value: Any) -> str:
    """Канонический JSON: сортировка ключей и без лишних пробелов."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _structure_payload(model: "ModelIR") -> list[Any]:
    containers = [
        [item.address, item.kind.value, item.name]
        for item in model.containers
    ]
    objects = [
        [
            item.address,
            item.name,
            item.class_name,
            item.obj_type,
            item.kind.value,
            [[port.index, port.name, port.direction.value]
             for port in item.ports],
        ]
        for item in model.objects
    ]
    wires = [
        [
            item.address,
            item.kind.value,
            [
                item.start.kind.value,
                item.start.object_name,
                item.start.port_index,
                item.start.resolved,
            ],
            [
                item.end.kind.value,
                item.end.object_name,
                item.end.port_index,
                item.end.resolved,
            ],
            item.branch_parent_id,
            item.branch_node,
        ]
        for item in model.wires
    ]
    boundaries = [
        [
            item.submodel_object_id,
            item.external_port_index,
            item.external_port_name,
            item.internal_object_id,
            item.internal_port_index,
            item.resolved,
        ]
        for item in model.boundaries
    ]
    memories = [
        [
            item.variable,
            list(item.writers),
            list(item.readers),
            item.resolved,
        ]
        for item in model.memory_links
    ]
    return [
        "model-ir",
        model.meta.ir_schema,
        sorted(containers),
        sorted(objects),
        sorted(wires),
        sorted(boundaries),
        sorted(memories),
    ]


#: Свойства страницы, которые описывают вид, а не модель.
_PAGE_VIEW_PROPS = frozenset({
    "x", "y", "width", "height", "x_center", "y_center", "x_scale",
    "y_scale", "scalex", "scaley", "visible", "backcolor", "transparent",
    "snap", "snapstep", "grid", "imagemode", "angle", "printarea",
    "prngridon", "lmargin", "rmargin", "tmargin", "bmargin", "curentlayer",
    "layered", "opacity", "enabledls", "visiblels", "curentls", "uselsonrun",
})


def _content_payload(model: "ModelIR") -> list[Any]:
    objects = [
        [
            item.address,
            sorted([name, prop.value, prop.section]
                   for name, prop in item.props.items()),
            sorted([name, prop.value]
                   for name, prop in item.visual_props.items()),
            sorted([slot, script.sha256, script.length]
                   for slot, script in item.scripts.items()),
            item.points,
            [port.index for port in item.ports],
            [[port.index, port.x, port.y, port.x_glob, port.y_glob]
             for port in item.ports],
        ]
        for item in model.objects
    ]
    containers = [
        [
            item.address,
            sorted([name, prop.value]
                   for name, prop in item.props.items()
                   if name not in _PAGE_VIEW_PROPS),
            item.script_hash,
            item.script_present,
        ]
        for item in model.containers
    ]
    wires = [
        [
            item.address,
            item.points,
            item.node_points,
            list(item.start_xy),
            list(item.end_xy),
            sorted([name, prop.value]
                   for name, prop in item.props.items()),
        ]
        for item in model.wires
    ]
    return [
        sorted(containers),
        sorted(objects),
        sorted(wires),
    ]


def structure_hash(model: "ModelIR") -> str:
    return digest(_structure_payload(model))


def content_hash(model: "ModelIR") -> str:
    return digest([_structure_payload(model), _content_payload(model)])
