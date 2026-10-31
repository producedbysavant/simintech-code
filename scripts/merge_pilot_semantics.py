"""Перенести эталонную семантику из YAML в реестр контрактов.

Строки `synthetic_only` в реестр не попадают: класс может отсутствовать в
каталоге 958 классов. `auxiliary` переносится с `pilot_scope: auxiliary` и не
входит в живую приёмку. `--check` ловит расхождение таблицы и реестра.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TABLE = ROOT / "tests" / "fixtures" / "semantics" / "pilot_blocks.yaml"
DEFAULT_REGISTRY = ROOT / "simintech_api" / "data" / "block_contracts.json"
FIELDS = ("behavior", "dependencies", "signal_types", "review",
          "known_absences")


def _expected(row: dict[str, Any]) -> dict[str, Any]:
    scope = str(row.get("scope", ""))
    result: dict[str, Any] = {
        "behavior": row.get("behavior", {"operation": "unknown"}),
        "dependencies": row.get("dependencies", []),
        "review": row.get("review", {
            "status": "preliminary", "reviewer": "", "date": "",
        }),
        "known_absences": row.get("known_absences", []),
        "pilot_scope": scope,
    }
    if "signal_types" in row:
        result["signal_types"] = row["signal_types"]
    return result


def _mergeable(table: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    for name, row in table.get("classes", {}).items():
        if str(row.get("scope", "")) == "synthetic_only":
            continue
        yield name, row


def check(table: dict[str, Any], registry: dict[str, Any],
          at: str) -> list[str]:
    problems: list[str] = []
    for name, row in _mergeable(table):
        expected = _expected(row)
        entry = registry.get("classes", {}).get(name)
        if entry is None:
            problems.append(f"{name}: нет в реестре")
            continue
        for key in FIELDS + ("pilot_scope",):
            if key in expected and entry.get(key) != expected[key]:
                problems.append(f"{name}.{key}: расхождение")
        mark = f"pilot:{at}"
        if mark not in entry.get("provenance", ()):
            problems.append(f"{name}: нет {mark}")
    return problems


def merge(table: dict[str, Any], registry: dict[str, Any],
          at: str) -> dict[str, Any]:
    for name, row in _mergeable(table):
        entry = registry.get("classes", {}).get(name)
        if entry is None:
            raise SystemExit(f"{name}: нет в реестре")
        entry.update(_expected(row))
        provenance = list(entry.get("provenance", ()))
        mark = f"pilot:{at}"
        if mark not in provenance:
            provenance.append(mark)
        entry["provenance"] = provenance
    return registry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--at", default="2026-10-31")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    table = yaml.safe_load(args.table.read_text(encoding="utf-8"))
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    if args.check:
        problems = check(table, registry, args.at)
        if problems:
            print("\n".join(problems))
            return 1
        print("реестр совпадает с таблицей")
        return 0
    merge(table, registry, args.at)
    args.registry.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n", encoding="utf-8")
    print(f"реестр обновлён: {args.registry}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
