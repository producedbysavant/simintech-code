"""Адаптер протокола `topology` (`object/port/conn`) в Model IR.

Протокол даёт связность текущего контейнера, но не форму линии, не ветви,
не свойства и не геометрию. Это честно отражено в покрытии: рёбра имеют вид
`topology_edge`, а не физический провод.
"""

from __future__ import annotations

from . import ids
from .codes import (
    ContainerKind,
    ObjectKind,
    PortDirection,
    ProvenanceStatus,
    SourceKind,
    SourceStatus,
    WireEndKind,
    WireKind,
)
from .ir import (
    IR_SCHEMA_VERSION,
    Container,
    Coverage,
    ModelIR,
    ModelMeta,
    ModelObject,
    ModelPort,
    ModelWire,
    Provenance,
    WireEnd,
)
from ..topology import Topology


def _direction(value: str) -> PortDirection:
    if value == "in":
        return PortDirection.IN
    if value == "out":
        return PortDirection.OUT
    if value == "undirected":
        return PortDirection.UNDIRECTED
    return PortDirection.UNKNOWN


def _kind(class_name: str) -> ObjectKind:
    if class_name in ("Порт входа", "Порт выхода"):
        return ObjectKind.PORT_BLOCK
    if class_name in ("В память", "Из памяти"):
        return ObjectKind.MEMORY_CELL
    if class_name == "Субмодель":
        return ObjectKind.SUBMODEL
    return ObjectKind.BLOCK


def topology_to_ir(topology: Topology, *,
                   container_address: str = "main",
                   source_name: str = "") -> ModelIR:
    """Построить частичный IR из уже разобранного протокола топологии."""
    container_id = ids.container_id(container_address)
    object_ids: dict[str, str] = {}
    objects: list[ModelObject] = []
    ports_by_object: dict[str, list[ModelPort]] = {}
    for order, row in enumerate(topology.objects):
        object_id = ids.object_id(container_id, order)
        object_ids[row.name] = object_id
        addresses = f"{container_address}::{row.name}"
        objects.append(ModelObject(
            id=object_id, address=addresses, container_id=container_id,
            name=row.name, class_name=row.class_name, obj_type="",
            order=order, kind=_kind(row.class_name),
            provenance=Provenance(SourceKind.TOPOLOGY,
                                  ProvenanceStatus.MEASURED, addresses)))
    for port_row in topology.ports:
        port_object_id = object_ids.get(port_row.object_name)
        if port_object_id is None:
            continue
        port = ModelPort(
            id=ids.port_id(port_object_id, port_row.index),
            object_id=port_object_id,
            index=port_row.index, name=port_row.name,
            direction=_direction(port_row.direction),
            provenance=Provenance(SourceKind.TOPOLOGY,
                                  ProvenanceStatus.MEASURED,
                                  f"{container_address}::{port_row.object_name}"))
        ports_by_object.setdefault(port_object_id, []).append(port)
    rebuilt: list[ModelObject] = []
    for item in objects:
        ports = tuple(sorted(ports_by_object.get(item.id, ()),
                             key=lambda port: port.index))
        rebuilt.append(ModelObject(
            id=item.id, address=item.address, container_id=item.container_id,
            name=item.name, class_name=item.class_name, obj_type=item.obj_type,
            order=item.order, kind=item.kind, ports=ports,
            provenance=item.provenance))
    wires: list[ModelWire] = []
    for order, connection in enumerate(topology.connections):
        start_id = object_ids.get(connection.object_a)
        end_id = object_ids.get(connection.object_b)
        if start_id is None or end_id is None:
            continue
        start = WireEnd(
            kind=WireEndKind.PORT, object_id=start_id,
            object_name=connection.object_a,
            port_index=connection.index_a, container_id=container_id,
            resolved=True,
            provenance=Provenance(SourceKind.TOPOLOGY,
                                  ProvenanceStatus.MEASURED,
                                  connection.object_a))
        end = WireEnd(
            kind=WireEndKind.PORT, object_id=end_id,
            object_name=connection.object_b,
            port_index=connection.index_b, container_id=container_id,
            resolved=True,
            provenance=Provenance(SourceKind.TOPOLOGY,
                                  ProvenanceStatus.MEASURED,
                                  connection.object_b))
        wires.append(ModelWire(
            id=ids.wire_id(container_id, order),
            address=f"{container_address}::edge#{order}",
            container_id=container_id, order=order,
            name=f"edge#{order}", kind=WireKind.TOPOLOGY_EDGE,
            start=start, end=end,
            provenance=Provenance(SourceKind.TOPOLOGY,
                                  ProvenanceStatus.MEASURED,
                                  f"{container_address}::edge#{order}")))
    source_hash = ids.digest({
        "objects": [[row.name, row.class_name] for row in topology.objects],
        "ports": [[row.object_name, row.index, row.direction, row.name]
                  for row in topology.ports],
        "connections": [[item.object_a, item.index_a, item.object_b,
                         item.index_b]
                        for item in topology.connections],
    })
    container = Container(
        id=container_id, address=container_address, kind=ContainerKind.PROJECT,
        name="main", object_ids=tuple(item.id for item in rebuilt),
        wire_ids=tuple(item.id for item in wires),
        provenance=Provenance(SourceKind.TOPOLOGY,
                              ProvenanceStatus.MEASURED,
                              container_address))
    coverage = Coverage(
        containers=1, objects=len(rebuilt),
        ports_real=sum(len(item.ports) for item in rebuilt),
        wires=len(wires), source_status=SourceStatus.PARTIAL,
        port_order_status=ProvenanceStatus.MEASURED,
        skipped={
            "geometry_not_in_topology": 1,
            "branches_not_in_topology": 1,
            "properties_not_in_topology": 1,
            "scripts_not_in_topology": 1,
            "hierarchy_not_in_topology": 1,
        })
    meta = ModelMeta(
        ir_schema=IR_SCHEMA_VERSION, primary_source=SourceKind.TOPOLOGY,
        source_set=(SourceKind.TOPOLOGY,),
        source_hashes={"topology": source_hash},
        structure_hash="", content_hash="", source_name=source_name)
    model = ModelIR(
        meta=meta, containers=(container,), objects=tuple(rebuilt),
        wires=tuple(wires), coverage=coverage)
    meta = ModelMeta(
        ir_schema=meta.ir_schema, primary_source=meta.primary_source,
        source_set=meta.source_set, source_hashes=meta.source_hashes,
        structure_hash=ids.structure_hash(model),
        content_hash=ids.content_hash(model), source_name=meta.source_name)
    return ModelIR(
        meta=meta, containers=model.containers, objects=model.objects,
        wires=model.wires, coverage=model.coverage)
