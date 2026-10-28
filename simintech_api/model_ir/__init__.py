"""Model IR: нормализованное представление модели SimInTech.

Пакет не импортирует COM и не зависит от `simintech_api.core`. Источники
(сейчас `.xprt`, далее текст модели и протокол топологии) дают структуры
`ModelIR`; графовые запросы и паспорт строятся поверх них.
"""

from __future__ import annotations

from .codes import (
    ContainerKind,
    ObjectKind,
    PortDirection,
    ProvenanceStatus,
    Severity,
    SourceKind,
    SourceStatus,
    WireEndKind,
    WireKind,
)
from .errors import ModelIRError, ModelIRLimitError, XprtParseError
from .ids import content_hash, structure_hash
from .ir import (
    IR_SCHEMA_VERSION,
    BoundaryPort,
    Container,
    Coverage,
    Decoration,
    Discrepancy,
    MemoryLink,
    ModelIR,
    ModelMeta,
    ModelObject,
    ModelPort,
    ModelWire,
    Property,
    Provenance,
    ScriptInfo,
    WireEnd,
)
from .xprt_model import Limits, parse_xprt, parse_xprt_file

__all__ = [
    "IR_SCHEMA_VERSION",
    "BoundaryPort",
    "Container",
    "ContainerKind",
    "Coverage",
    "Decoration",
    "Discrepancy",
    "Limits",
    "MemoryLink",
    "ModelIR",
    "ModelIRError",
    "ModelIRLimitError",
    "ModelMeta",
    "ModelObject",
    "ModelPort",
    "ModelWire",
    "ObjectKind",
    "PortDirection",
    "Property",
    "Provenance",
    "ProvenanceStatus",
    "ScriptInfo",
    "Severity",
    "SourceKind",
    "SourceStatus",
    "WireEnd",
    "WireEndKind",
    "WireKind",
    "XprtParseError",
    "content_hash",
    "parse_xprt",
    "parse_xprt_file",
    "structure_hash",
]
