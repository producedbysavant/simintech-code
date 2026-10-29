"""P5: время разбора и индекса на крупных синтетических моделях.

Модуль исключён из обычного прогона маркером `performance`:
`pytest -m performance`. Потолки взяты с запасом к замерам 2026-10-29
на WSL; они ловят возврат квадратичности, а не точную скорость машины.
"""

from __future__ import annotations

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from simintech_api.model_ir import (  # noqa: E402
    ModelIndex,
    build_manifest,
    parse_xprt,
)

from model_ir_synth import deep_model, flat_model, star_model  # noqa: E402

pytestmark = pytest.mark.performance


def test_flat_10000_parse_index_manifest_within_ceilings():
    model = flat_model(10000)
    started = time.perf_counter()
    ir = parse_xprt(model.text)
    parsed = time.perf_counter() - started
    assert ir.coverage.objects == 10000
    assert ir.coverage.wires == 9999

    started = time.perf_counter()
    ModelIndex(ir)
    indexed = time.perf_counter() - started

    started = time.perf_counter()
    text = build_manifest(ir, budget_tokens=3000)
    manifest = time.perf_counter() - started

    assert parsed < 10.0, parsed
    assert indexed < 3.0, indexed
    assert manifest < 3.0, manifest
    assert len(text) <= 3000 * 3


def test_branch_6000_within_ceiling():
    model = star_model(6000)
    started = time.perf_counter()
    ir = parse_xprt(model.text)
    parsed = time.perf_counter() - started
    assert ir.coverage.branches == 5999
    assert ir.coverage.unresolved_branches == 0
    assert parsed < 12.0, parsed


def test_deep_63_within_ceiling():
    model = deep_model(63)
    started = time.perf_counter()
    ir = parse_xprt(model.text)
    parsed = time.perf_counter() - started
    assert ir.coverage.containers == 64
    assert parsed < 2.0, parsed
