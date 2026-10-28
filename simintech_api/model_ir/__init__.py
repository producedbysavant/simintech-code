"""Model IR: нормализованное представление модели SimInTech.

Пакет не импортирует COM и не зависит от `simintech_api.core`. Источники
(сейчас `.xprt`, далее текст модели и протокол топологии) дают структуры
`ModelIR`; графовые запросы и паспорт строятся поверх них.
"""

from __future__ import annotations

from .contracts import (
    BlockContract,
    BlockContractRegistry,
    Constraint,
    ContractCoverage,
    CreationPath,
    PortContract,
    PortSpec,
    PropertyContract,
    load_default_contracts,
    validate_contract_data,
)
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
from .errors import (
    ModelIRConflictError,
    ModelIRError,
    ModelIRLimitError,
    ModelQueryError,
    ModelTextParseError,
    XprtParseError,
)
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
from .graph import ModelIndex, QueryResult
from .manifest import build_manifest
from .merge import build_model_ir
from .text_model import parse_model_text
from .topology_model import topology_to_ir
from .xprt_model import Limits, parse_xprt, parse_xprt_file

__all__ = [
    "IR_SCHEMA_VERSION",
    "BlockContract",
    "BlockContractRegistry",
    "BoundaryPort",
    "Constraint",
    "Container",
    "ContractCoverage",
    "CreationPath",
    "ContainerKind",
    "Coverage",
    "Decoration",
    "Discrepancy",
    "Limits",
    "MemoryLink",
    "ModelIR",
    "ModelIRConflictError",
    "ModelIRError",
    "ModelIRLimitError",
    "ModelIndex",
    "ModelQueryError",
    "ModelTextParseError",
    "ModelMeta",
    "ModelObject",
    "ModelPort",
    "ModelWire",
    "ObjectKind",
    "PortContract",
    "PortDirection",
    "PortSpec",
    "Property",
    "PropertyContract",
    "Provenance",
    "ProvenanceStatus",
    "QueryResult",
    "ScriptInfo",
    "Severity",
    "SourceKind",
    "SourceStatus",
    "WireEnd",
    "WireEndKind",
    "WireKind",
    "XprtParseError",
    "build_manifest",
    "build_model_ir",
    "content_hash",
    "load_default_contracts",
    "parse_model_text",
    "parse_xprt",
    "parse_xprt_file",
    "structure_hash",
    "topology_to_ir",
    "validate_contract_data",
]
