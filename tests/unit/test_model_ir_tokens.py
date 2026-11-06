"""Model IR: консервативная оценка токенов паспорта."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from simintech_api.model_ir.tokens import (  # noqa: E402
    ESTIMATOR_VERSION,
    estimate_tokens,
    fits_budget,
)


def test_estimate_tokens_empty_is_zero():
    assert estimate_tokens("") == 0


def test_estimate_tokens_ascii_units():
    assert estimate_tokens("x" * 300) == 120


def test_estimate_tokens_cyrillic_is_more_expensive():
    assert estimate_tokens("я" * 100) == 70
    assert estimate_tokens("я" * 100) > estimate_tokens("x" * 100)


def test_estimate_tokens_line_overhead():
    flat = estimate_tokens("x" * 10)
    lines = estimate_tokens("x\n" * 10)
    assert lines > flat


def test_estimate_tokens_is_monotone():
    text = "Усилитель: y = a * u\n"
    assert estimate_tokens(text + "я") >= estimate_tokens(text)
    assert estimate_tokens(text + "x") >= estimate_tokens(text)


def test_estimate_tokens_mixed_exact():
    assert estimate_tokens("a\nя") == 2
    assert estimate_tokens("aя") == 2
    assert estimate_tokens("\n") == 1
    assert ESTIMATOR_VERSION == "chars/1"


def test_fits_budget():
    assert fits_budget("x" * 300, 120)
    assert not fits_budget("x" * 301, 120)
