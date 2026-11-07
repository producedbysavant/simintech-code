"""Консервативная оценка токенов Markdown-паспорта.

Оценка завышена, а не занижена: кириллица дороже ASCII, разметка и
переводы строк добавляют запас. Точный токенизатор не используется,
поэтому оценка не зависит от сети и версии словаря.
"""

from __future__ import annotations

ESTIMATOR_VERSION = "chars/1"
_ASCII_UNITS = 4
_CYRILLIC_UNITS = 7
_OTHER_UNITS = 7
_NEWLINE_UNITS = 6


def estimate_tokens(text: str) -> int:
    """Верхняя оценка числа токенов для русского и ASCII текста."""
    if not text:
        return 0
    units = 0
    for char in text:
        if char == "\n":
            units += _NEWLINE_UNITS
        elif ord(char) < 128:
            units += _ASCII_UNITS
        elif "Ѐ" <= char <= "ӿ":
            units += _CYRILLIC_UNITS
        else:
            units += _OTHER_UNITS
    return (units + 9) // 10


def fits_budget(text: str, budget_tokens: int) -> bool:
    return estimate_tokens(text) <= budget_tokens
