"""Собрать реестр контрактов блоков из каталога и корпуса выгрузок.

Каталог даёт свойства и умолчания; корпус `.xprt` даёт наблюдаемые порты.
Всё, чего в корпусе нет, остаётся `unknown` с причиной. Даты и версии
наблюдения фиксируются аргументом, а не берутся из текущего времени:
повторный прогон с теми же входами обязан дать байт-идентичный файл.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from simintech_api import __version__  # noqa: E402
from simintech_api.constants import (  # noqa: E402
    FSM_BLOCK_RECORDS,
    SUPPORTED_COM_BLOCK_CLASSES,
    UNSUPPORTED_COM_BLOCK_CLASSES,
)
from simintech_api.model_ir import ObjectKind, parse_xprt_file  # noqa: E402
from simintech_api.model_ir.xprt_model import (  # noqa: E402
    MEMORY_CELLS,
    PORT_BLOCKS,
)

#: Классы, у которых nport задаёт число входов (правило MCP rules.py).
NPORT_INPUT_CLASSES = (
    "Мультиплексор", "Оператор И", "Оператор ИЛИ", "Перемножитель",
    "Минимум по входам",
)
#: Классы с nport, но с другим смыслом параметра (правило MCP rules.py).
NPORT_OTHER_CLASSES = (
    "Внешняя DLL", "Минимум по всем элементам вектора",
)
#: Классы, у которых число и имена входов задают веса `a`: живой замер
#: 30.10.2026 - «Сумматор» с `a = [1 , -1]` даёт «+» и «−» (U+2212), с
#: `a = [2 , -3]` - «2» и «-3», с тремя единицами - три входа «+».
WEIGHT_CLASSES = ("Сумматор",)
#: Классы, у которых имя порта не инвариантно: корпус дал `inport`, а живая
#: приёмка 29.10.2026 - `U` у того же класса. Сверка имена не проверяет.
INSTANCE_NAME_CLASSES = ("Оператор НЕ", "Операция БОЛЬШЕ", "Операция МЕНЬШЕ")
#: Условные порты: появляются, когда свойство включено. Живой замер
#: 30.10.2026 - `T1` у «Задержки по включению» есть при `addport = 1` и
#: отсутствует при `addport = 0` и пустом значении.
OPTIONAL_PORTS: dict[str, dict[str, Any]] = {
    "Задержка по включению": {
        "property": "addport",
        "port": {"index": 2, "name": "T1", "direction": "in"},
    },
}
SUB_MODEL = "Субмодель"
OBSERVED_AT_DEFAULT = "2026-10-28"


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _corpus(args: argparse.Namespace) -> list[Path]:
    raw: list[str] = list(args.corpus or [])
    if not raw:
        raw = [item for item in os.environ.get(
            "SIMINTECH_XPRT_DIRS", "").split(os.pathsep) if item]
    paths: list[Path] = []
    for item in raw:
        root = Path(item)
        if root.is_file() and root.suffix.lower() == ".xprt":
            paths.append(root)
        elif root.is_dir():
            paths.extend(sorted(root.rglob("*.xprt")))
    return paths


def _signature(obj: Any) -> tuple[tuple[int, str, str], ...]:
    return tuple((port.index, port.name, port.direction.value)
                 for port in sorted(obj.ports, key=lambda item: item.index))


def _split(signature: tuple[tuple[int, str, str], ...]) -> tuple[
        list[dict[str, Any]], list[dict[str, Any]]]:
    inputs = [{"index": index, "name": name, "direction": direction}
              for index, name, direction in signature
              if direction == "in"]
    outputs = [{"index": index, "name": name, "direction": direction}
               for index, name, direction in signature
               if direction == "out"]
    return inputs, outputs


def _ports(class_name: str, observed: list[tuple[tuple[int, str, str], ...]],
           submodel_classes: set[str]) -> dict[str, Any]:
    signatures = sorted(set(observed))
    inputs: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []
    if signatures:
        inputs, outputs = _split(signatures[0])
    name_status = ("missing" if signatures and not any(
        item[1] for item in signatures[0]) else
        ("measured" if signatures else "unknown"))
    if class_name in INSTANCE_NAME_CLASSES:
        name_status = "instance_defined"
    #: Условные порты вынимаются из образца: они есть не у каждого
    #: экземпляра, и модель контракта описывает их отдельно.
    variants: list[dict[str, Any]] = []
    optional = OPTIONAL_PORTS.get(class_name)
    if optional:
        port = dict(optional["port"])
        inputs = [item for item in inputs
                  if not (item["index"] == port["index"]
                          and item["name"] == port["name"])]
        variants.append({"property": optional["property"],
                         "add_inputs": [port]})
    if class_name in WEIGHT_CLASSES:
        return {
            "model": "weights", "inputs": [], "outputs": outputs,
            "weights_property": "a", "name_status": "weights",
            "provenance": "live 2026-10-30: число и имена входов из весов a",
        }
    if class_name in NPORT_INPUT_CLASSES:
        result = {
            "model": "nport", "inputs": inputs, "outputs": outputs,
            "nport_property": "nport", "name_status": name_status,
            "provenance": "rules.py: nport",
        }
        return _with_variants(result, variants)
    if class_name in NPORT_OTHER_CLASSES:
        result = {
            "model": "nport", "inputs": inputs, "outputs": outputs,
            "nport_property": "nport", "name_status": name_status,
            "reason": "nport не число входных контактов",
            "provenance": "rules.py: nport other",
        }
        return _with_variants(result, variants)
    if class_name in PORT_BLOCKS or class_name in MEMORY_CELLS:
        result = {
            "model": "portnames", "inputs": inputs, "outputs": outputs,
            "portnames_property": "PortNames", "name_status": name_status,
            "provenance": "constants.py: port block",
        }
        return _with_variants(result, variants)
    if class_name == SUB_MODEL or class_name in submodel_classes:
        result = {
            "model": "submodel", "inputs": inputs, "outputs": outputs,
            "name_status": name_status,
            "reason": "внешние порты задаются порт-блоками внутри",
            "provenance": "xprt corpus: submodel page",
        }
        return _with_variants(result, variants)
    if not signatures:
        return {"model": "unknown", "reason": "not_observed_in_corpus",
                "name_status": "unknown", "provenance": "corpus"}
    if not inputs and not outputs:
        return {"model": "unknown", "reason": "no_ports_in_corpus",
                "name_status": "unknown", "provenance": "corpus"}
    if len(signatures) > 1:
        result = {"model": "unknown", "reason": "varied_signatures",
                  "inputs": inputs, "outputs": outputs,
                  "name_status": name_status, "provenance": "corpus"}
        return _with_variants(result, variants)
    result = {
        "model": "fixed", "inputs": inputs, "outputs": outputs,
        "name_status": name_status, "provenance": "corpus",
    }
    return _with_variants(result, variants)


def _with_variants(ports: dict[str, Any],
                   variants: list[dict[str, Any]]) -> dict[str, Any]:
    """Добавить условные порты в запись, если они есть."""
    if variants:
        ports["variants"] = variants
    return ports


def _creation(class_name: str) -> dict[str, Any]:
    if class_name in UNSUPPORTED_COM_BLOCK_CLASSES:
        return {"paths": [{"path": "com_createblock", "status": "blocked",
                           "ref": "constants.py: UNSUPPORTED"}]}
    if class_name in FSM_BLOCK_RECORDS.values():
        return {"paths": [{"path": "com_createblock", "status": "derived",
                           "ref": "constants.py: FSM record"}]}
    if class_name in SUPPORTED_COM_BLOCK_CLASSES:
        return {"paths": [{"path": "com_createblock", "status": "derived",
                           "ref": "constants.py: SUPPORTED"}]}
    return {"paths": [{"path": "unknown", "status": "unknown",
                       "ref": "not measured"}]}


def _constraints(class_name: str, ports: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if ports["model"] == "nport":
        result.append({
            "code": ("nport-input-count"
                     if class_name in NPORT_INPUT_CLASSES
                     else "nport-other-semantics"),
            "description": (
                "число входов задаётся nport; высота 16 px на вход, "
                "ширина не уже 32"
                if class_name in NPORT_INPUT_CLASSES else
                "nport не задаёт число входных контактов"),
            "params": ({"height_per_input": 16, "width": 32}
                       if class_name in NPORT_INPUT_CLASSES else {}),
            "provenance": "rules.py",
        })
    if ports["model"] == "portnames":
        result.append({
            "code": "portnames-required",
            "description": "PortNames задаёт имена и число сигналов",
            "params": {},
            "provenance": "constants.py",
        })
    if ports["model"] == "submodel":
        result.append({
            "code": "submodel-port-match-by-name",
            "description": "внешний порт сопоставляется с порт-блоком по имени",
            "params": {},
            "provenance": "xprt corpus",
        })
    return result


def generate(catalog_path: Path, corpus_paths: list[Path],
             observed_at: str) -> dict[str, Any]:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    classes = catalog["classes"]
    readonly = catalog.get("readonly", {})
    catalog_sha = _sha(catalog_path)
    observed: dict[str, list[tuple[tuple[int, str, str], ...]]] = {}
    submodel_classes: set[str] = set()
    dump_hashes: set[str] = set()
    failed = 0
    for path in corpus_paths:
        try:
            model = parse_xprt_file(path)
        except Exception:  # noqa: BLE001 - корпус может содержать битые файлы
            failed += 1
            continue
        digest = model.meta.source_hashes.get("xprt")
        if digest:
            dump_hashes.add(digest)
        for obj in model.objects:
            if obj.kind in (ObjectKind.ANNOTATION, ObjectKind.DECORATION):
                continue
            if not obj.class_name:
                continue
            observed.setdefault(obj.class_name, []).append(_signature(obj))
            if obj.kind is ObjectKind.SUBMODEL:
                submodel_classes.add(obj.class_name)
    result: dict[str, dict[str, Any]] = {}
    unknown_classes: list[str] = []
    for class_name in sorted(classes):
        props = {
            name: {"default": str(value), "readonly": name in
                   (readonly.get(class_name) or []), "kind": "unknown",
                   "provenance": f"catalog:{catalog_sha[:12]}"}
            for name, value in classes[class_name].items()
        }
        ports = _ports(class_name, observed.get(class_name, []),
                       submodel_classes)
        if ports["model"] == "unknown":
            unknown_classes.append(class_name)
        status = ("measured" if class_name in observed
                  else "derived")
        result[class_name] = {
            "class": class_name,
            "status": status,
            "properties": props,
            "ports": ports,
            "creation": _creation(class_name),
            "constraints": _constraints(class_name, ports),
            "provenance": [
                f"catalog:{catalog_sha[:12]}",
                f"corpus:{len(observed.get(class_name, ()))}",
            ],
        }
    counts = Counter(item["ports"]["model"] for item in result.values())
    extra = sorted(set(observed) - set(classes))
    return {
        "version": 1,
        "schema": "block-contract/1",
        "meta": {
            "catalog_version": catalog.get("version"),
            "catalog_sha256": catalog_sha,
            "catalog_classes": len(classes),
            "product": "SimInTech64",
            "version": "not recorded in corpus",
            "observed_at": observed_at,
            "generator": f"simintech-api {__version__}",
            "dump_sha256": sorted(dump_hashes),
            "dumps_read": len(dump_hashes),
            "dumps_failed": failed,
            "port_model_counts": dict(sorted(counts.items())),
            "unknown_classes": unknown_classes,
            "observed_extra_classes": extra,
        },
        "classes": result,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parent.parent
    parser.add_argument("--catalog", type=Path,
                        default=root / "simintech_api" / "data"
                        / "block_catalog.json")
    parser.add_argument("--out", type=Path,
                        default=root / "simintech_api" / "data"
                        / "block_contracts.json")
    parser.add_argument("--corpus", type=Path, nargs="*", default=None)
    parser.add_argument("--observed-at", default=OBSERVED_AT_DEFAULT)
    args = parser.parse_args(list(argv) if argv is not None else None)
    data = generate(args.catalog, _corpus(args), args.observed_at)
    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=2,
                                   sort_keys=True) + "\n", encoding="utf-8")
    print(f"контрактов: {len(data['classes'])}; "
          f"портовые модели: {data['meta']['port_model_counts']}; "
          f"неизмеренных классов: {len(data['meta']['unknown_classes'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
