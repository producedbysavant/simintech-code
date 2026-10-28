"""Проверить block_contracts.json: покрытие 958 классов и провенанс."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from simintech_api.model_ir.contracts import validate_contract_data  # noqa: E402


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contracts", type=Path,
                        default=root / "simintech_api" / "data"
                        / "block_contracts.json")
    parser.add_argument("--catalog", type=Path,
                        default=root / "simintech_api" / "data"
                        / "block_catalog.json")
    args = parser.parse_args()
    data = json.loads(args.contracts.read_text(encoding="utf-8"))
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    problems = validate_contract_data(data, catalog)
    sha = hashlib.sha256(args.catalog.read_bytes()).hexdigest()
    if data.get("meta", {}).get("catalog_sha256") != sha:
        problems.append("meta.catalog_sha256 не совпадает с каталогом")
    if problems:
        for problem in problems:
            print("ОШИБКА:", problem)
        return 1
    print(f"контрактов: {len(data['classes'])}; "
          f"портовые модели: {data['meta']['port_model_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
