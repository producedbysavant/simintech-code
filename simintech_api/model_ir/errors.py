"""Отказы Model IR.

Повреждённый или слишком большой проект - это отказ, а не пустая модель:
иначе сжатие спрячет потерю данных, а агент примет обрывок за целое.
"""

from __future__ import annotations

from ..exceptions import SimInTechError


class ModelIRError(SimInTechError):
    """Базовая ошибка Model IR."""


class XprtParseError(ModelIRError):
    """Выгрузка .xprt не разобрана как корректный XML."""


class ModelIRLimitError(ModelIRError):
    """Проект превысил байтовый, объектный или проводной предел."""


class ModelTextParseError(ModelIRError):
    """Декларативный текст модели не разобран."""


class ModelIRConflictError(ModelIRError):
    """Расхождение источников в строгом режиме."""


class ModelQueryError(ModelIRError):
    """Запрос к IR не может быть выполнен однозначно."""


class SystemSpecError(ModelIRError):
    """SystemSpec не скомпилирован: ошибки собраны все, а не первая."""

    def __init__(self, problems: list[dict[str, str]]) -> None:
        self.problems = problems
        super().__init__(
            "SystemSpec: " + "; ".join(
                f"{item['path']}: {item['message']}" for item in problems))
