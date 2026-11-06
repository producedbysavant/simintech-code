"""Экспериментальные свидетельства для запроса `influence`.

Запись относится к конкретному снимку модели: оба хеша обязательны.
Свидетельство не является контрактом и не доказывает отсутствие влияния.
Отрицательное наблюдение остаётся ограничением, а не известным отсутствием.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .errors import ModelQueryError

EXPERIMENT_SCHEMA = "experiment-record/1"
_MAX_RECORDS = 100
_ALLOWED_STATUS = {"observed", "experiment", "unknown"}


@dataclass(frozen=True, slots=True)
class ExperimentRecord:
    """Одно наблюдение, привязанное к снимку Model IR."""

    id: str
    structure_hash: str
    content_hash: str
    scenario: Mapping[str, Any]
    run: Mapping[str, Any]
    observation: Mapping[str, Any]
    status: str = "observed"
    recorded_at: str = ""
    limitations: tuple[str, ...] = ()

    @property
    def target(self) -> str:
        return str(self.observation.get("target", ""))

    @property
    def source(self) -> str:
        return str(self.scenario.get("changed", ""))

    @property
    def observed(self) -> bool:
        return bool(self.observation.get("changed", False))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "structure_hash": self.structure_hash,
            "content_hash": self.content_hash,
            "scenario": dict(self.scenario),
            "run": dict(self.run),
            "observation": dict(self.observation),
            "status": self.status,
            "recorded_at": self.recorded_at,
            "limitations": list(self.limitations),
        }


def _mapping(where: str, value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ModelQueryError(f"{where}: не объект")
    return value


def _text(where: str, value: Any) -> str:
    result = str(value or "").strip()
    if not result:
        raise ModelQueryError(f"{where}: пустое значение")
    return result


def _number(where: str, value: Any, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelQueryError(f"{where}: нужно число")
    result = float(value)
    if positive and result <= 0:
        raise ModelQueryError(f"{where}: нужно положительное число")
    if result < 0:
        raise ModelQueryError(f"{where}: отрицательное время")
    return result


def parse_experiment_record(data: Mapping[str, Any]) -> ExperimentRecord:
    """Разобрать запись эксперимента; форма проверяется до matching."""
    if not isinstance(data, Mapping):
        raise ModelQueryError("experiment: запись не объект")
    schema = str(data.get("schema", EXPERIMENT_SCHEMA))
    if schema != EXPERIMENT_SCHEMA:
        raise ModelQueryError(
            f"experiment: неизвестная схема {schema!r}")
    ident = _text("experiment.id", data.get("id"))
    structure_hash = _text("experiment.structure_hash",
                           data.get("structure_hash"))
    content_hash = _text("experiment.content_hash",
                         data.get("content_hash"))
    scenario = _mapping("experiment.scenario", data.get("scenario"))
    _text("experiment.scenario.changed", scenario.get("changed"))
    _number("experiment.scenario.from", scenario.get("from"))
    _number("experiment.scenario.to", scenario.get("to"))
    _number("experiment.scenario.at", scenario.get("at"))
    run = _mapping("experiment.run", data.get("run"))
    _number("experiment.run.step", run.get("step"), positive=True)
    _number("experiment.run.to_time", run.get("to_time"), positive=True)
    _text("experiment.run.baseline", run.get("baseline"))
    observation = _mapping("experiment.observation",
                           data.get("observation"))
    _text("experiment.observation.target", observation.get("target"))
    changed = observation.get("changed")
    if not isinstance(changed, bool):
        raise ModelQueryError(
            "experiment.observation.changed: нужен bool")
    if changed and "first_change_at" in observation:
        _number("experiment.observation.first_change_at",
                observation.get("first_change_at"))
    status = str(data.get("status", "observed"))
    if status not in _ALLOWED_STATUS:
        raise ModelQueryError(
            f"experiment.status: недопустимо {status!r}")
    recorded_at = _text("experiment.recorded_at", data.get("recorded_at"))
    raw_limitations = data.get("limitations", [])
    if not isinstance(raw_limitations, list) or not all(
            isinstance(item, str) for item in raw_limitations):
        raise ModelQueryError("experiment.limitations: нужен список строк")
    return ExperimentRecord(
        id=ident,
        structure_hash=structure_hash,
        content_hash=content_hash,
        scenario=dict(scenario),
        run=dict(run),
        observation=dict(observation),
        status=status,
        recorded_at=recorded_at,
        limitations=tuple(raw_limitations),
    )


def parse_experiment_records(
        items: Iterable[Mapping[str, Any]]) -> tuple[ExperimentRecord, ...]:
    """Разобрать набор записей и проверить уникальность идентификаторов."""
    records = tuple(parse_experiment_record(item) for item in items)
    if len(records) > _MAX_RECORDS:
        raise ModelQueryError(
            f"experiment: больше {_MAX_RECORDS} записей")
    seen: set[str] = set()
    for record in records:
        if record.id in seen:
            raise ModelQueryError(
                f"experiment: повтор идентификатора {record.id!r}")
        seen.add(record.id)
    return records
