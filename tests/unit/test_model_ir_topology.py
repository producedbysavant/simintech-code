"""Model IR: адаптер протокола topology."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from simintech_api.model_ir import (  # noqa: E402
    PortDirection,
    SourceKind,
    SourceStatus,
    WireKind,
    topology_to_ir,
)
from simintech_api.topology import parse_topology  # noqa: E402

TOPOLOGY = """object\tB\tУсилитель
object\tA\tСтупенька
port\tB\t1\tin\tinport
port\tA\t0\tout\toutport
conn\tB\t1\tA\t0
"""


def test_topology_to_ir_builds_objects_ports_and_edges():
    ir = topology_to_ir(parse_topology(TOPOLOGY), source_name="model.topology")

    assert ir.meta.primary_source is SourceKind.TOPOLOGY
    assert ir.meta.source_name == "model.topology"
    assert len(ir.containers) == 1
    assert len(ir.objects) == 2
    assert len(ir.wires) == 1
    assert ir.coverage.source_status is SourceStatus.PARTIAL
    assert ir.coverage.wires == 1
    assert ir.coverage.ports_real == 2

    a = ir.object_by_address("main::A")
    b = ir.object_by_address("main::B")
    assert a is not None and b is not None
    assert a.ports[0].direction is PortDirection.OUT
    assert b.ports[0].direction is PortDirection.IN

    edge = ir.wires[0]
    assert edge.kind is WireKind.TOPOLOGY_EDGE
    assert edge.start.resolved and edge.end.resolved
    assert {edge.start.object_name, edge.end.object_name} == {"A", "B"}
    assert "geometry_not_in_topology" in ir.coverage.skipped


def test_topology_hash_is_stable():
    first = topology_to_ir(parse_topology(TOPOLOGY))
    second = topology_to_ir(parse_topology(TOPOLOGY))
    assert first.meta.structure_hash == second.meta.structure_hash
    assert first.meta.content_hash == second.meta.content_hash
