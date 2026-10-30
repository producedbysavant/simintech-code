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
#: Классы, у которых имя порта не инвариантно: корпус дал один набор имён,
#: живая съёмка другой. «Оператор НЕ» и операции сравнения: корпус `inport`
#: и `inport_1`, приёмка 29.10.2026 - `U` и `U1`. «Интегратор»: корпус
#: `Port_0` и `Port_1` (блоки, созданные языком), живой COM и импорт
#: 30.10.2026 - `inport` и `outport`. Сверка имена не проверяет.
INSTANCE_NAME_CLASSES = ("Оператор НЕ", "Операция БОЛЬШЕ", "Операция МЕНЬШЕ",
                         "Интегратор")
#: Условные порты: появляются, когда свойство включено. Живой замер
#: 30.10.2026 - `T1` у «Задержки по включению» есть при `addport = 1` и
#: отсутствует при `addport = 0` и пустом значении.
OPTIONAL_PORTS: dict[str, dict[str, Any]] = {
    "Задержка по включению": {
        "property": "addport",
        "port": {"index": 2, "name": "T1", "direction": "in"},
    },
}
#: Классы, у которых число входов задаёт свойство с другим именем: у
#: «Временного графика» входов столько, сколько в `InPortCount` (живой
#: замер 30.10.2026: InPortCount=3 дал inport_1..inport_3).
NPORT_BY_PROPERTY = {"Временной график": "InPortCount"}
#: Классы, у которых число выходов задают веса `a`: у «Демультиплексора»
#: выходов столько, сколько весов (замер 30.10.2026: a=[1, 1, 1] дал три
#: выхода, a из шести элементов дал шесть).
WEIGHT_OUTPUT_CLASSES = ("Демультиплексор",)
#: Классы, чьи порты задаёт скрипт: сигнатура экземпляра ничего не говорит
#: о классе (замер 30.10.2026: у «Языка программирования» пины объявлены в
#: скрипте, и у двух экземпляров они разные).
SCRIPT_PORT_CLASSES = ("Язык программирования",)
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


def _structure(signature: tuple[tuple[int, str, str], ...]) -> tuple[
        tuple[int, str], ...]:
    """Структура подписи без имён: индексы и направления."""
    return tuple((index, direction) for index, _name, direction in signature)


def _sample_signature(signatures: list[tuple[
        tuple[int, str, str], ...]]) -> tuple[tuple[int, str, str], ...]:
    """Образец подписи: предпочтителен тот, где имена не автоимена среды.

    Блоки, созданные языком, несут `Port_0`/`PORT1`; такие имена не стоит
    печатать в реестре как образец, если рядом есть обычный (`inport`).
    """
    def auto(signature: tuple[tuple[int, str, str], ...]) -> bool:
        names = [name for _index, name, _direction in signature if name]
        return bool(names) and all(
            name.startswith("Port_") or name.startswith("PORT")
            for name in names)

    for signature in signatures:
        if not auto(signature):
            return signature
    return signatures[0]


def _ports(class_name: str, observed: list[tuple[tuple[int, str, str], ...]],
           submodel_classes: set[str]) -> dict[str, Any]:
    signatures = sorted(set(observed))
    inputs: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []
    if signatures:
        inputs, outputs = _split(_sample_signature(signatures))
    name_status = ("missing" if signatures and not any(
        item[1] for item in signatures[0]) else
        ("measured" if signatures else "unknown"))
    if class_name in SCRIPT_PORT_CLASSES:
        return {"model": "unknown", "reason": "script_defined_ports",
                "name_status": "unknown",
                "provenance": "live 2026-10-30: пины объявлены скриптом"}
    if class_name in NPORT_BY_PROPERTY:
        prop = NPORT_BY_PROPERTY[class_name]
        return {"model": "nport", "inputs": inputs, "outputs": outputs,
                "nport_property": prop, "name_status": "instance_defined",
                "provenance": f"live 2026-10-30: число входов по {prop}"}
    if class_name in WEIGHT_OUTPUT_CLASSES:
        return {"model": "weights", "weights_role": "outputs",
                "inputs": inputs, "outputs": outputs,
                "weights_property": "a", "name_status": "instance_defined",
                "provenance": "live 2026-10-30: число выходов по весам a"}
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
        # Подписи, различающиеся только именами портов (индексы и
        # направления совпадают), описывают класс с именем от экземпляра:
        # у «Усилителя» в одном корпусе `inport`/`outport`, в другом
        # `Port_0`/`PORT1` (живой снимок 30.10.2026).
        if len({_structure(item) for item in signatures}) == 1:
            result = {"model": "fixed", "inputs": inputs, "outputs": outputs,
                      "name_status": "instance_defined", "provenance": "corpus"}
            return _with_variants(result, variants)
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


def _observations(corpus_paths: list[Path]) -> tuple[
        dict[str, list[tuple[tuple[int, str, str], ...]]],
        set[str], set[str], int]:
    """Наблюдения корпуса: подписи по классам, классы-субмодели, хеши, сбои."""
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
    return observed, submodel_classes, dump_hashes, failed


def generate(catalog_path: Path, corpus_paths: list[Path],
             observed_at: str) -> dict[str, Any]:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    classes = catalog["classes"]
    readonly = catalog.get("readonly", {})
    catalog_sha = _sha(catalog_path)
    observed, submodel_classes, dump_hashes, failed = _observations(corpus_paths)
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


def _data_structure(ports: dict[str, Any]) -> list[tuple[int, str]]:
    """Структура записи реестра: индексы и направления без имён."""
    return [(int(item.get("index", -1)), str(item.get("direction", "")))
            for item in ports.get("inputs", ())] + \
        [(int(item.get("index", -1)), str(item.get("direction", "")))
         for item in ports.get("outputs", ())]


def _merge_ports(old: dict[str, Any],
                 new: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    """Слить новое наблюдение с записью реестра: (запись, решение).

    Правила намеренно узкие: реестр не переписывается целиком, потому что
    полного корпуса под рукой может не быть. Неизмеренная запись заменяется
    наблюдением; измеренная уточняется только по именам; расхождение
    структуры не трогается и называется конфликтом.
    """
    old_model = str(old.get("model", "unknown"))
    new_model = str(new.get("model", "unknown"))
    if old_model == "unknown":
        if new_model != "unknown":
            if old.get("reason") == "varied_signatures" and new_model == "fixed":
                # Исторически подписи различались: имена задаёт экземпляр.
                merged = dict(new)
                merged["name_status"] = "instance_defined"
                return merged, f"unknown -> {new_model} (имена от экземпляра)"
            return dict(new), f"unknown -> {new_model}"
        if new.get("reason") and new.get("reason") != old.get("reason"):
            merged = dict(old)
            merged["reason"] = new["reason"]
            return merged, f"причина: {new['reason']}"
        return None, "оставлено"
    if old_model == "fixed" and new_model == "fixed":
        if _data_structure(old) == _data_structure(new):
            if new.get("name_status") == "instance_defined" and \
                    old.get("name_status") != "instance_defined":
                merged = dict(old)
                merged["name_status"] = "instance_defined"
                return merged, "имена от экземпляра"
            return None, "оставлено"
        return None, "конфликт структуры"
    return None, "оставлено"


def merge(existing: dict[str, Any], catalog_path: Path,
          corpus_paths: list[Path], observed_at: str) -> dict[str, Any]:
    """Дописать наблюдения корпуса в существующий реестр.

    Полная пересборка (`generate`) требует всего корпуса, а он не хранится
    рядом с реестром. Здесь обновляются только классы, встреченные в новом
    корпусе; прочие записи не трогаются. Итог проверяется тем же
    `validate_contract_data`, что и полная сборка.
    """
    import copy

    existing = copy.deepcopy(existing)
    observed, submodel_classes, _hashes, _failed = _observations(corpus_paths)
    decisions: list[tuple[str, str]] = []
    for class_name in sorted(observed):
        entry = existing.get("classes", {}).get(class_name)
        if entry is None:
            continue
        new_ports = _ports(class_name, observed[class_name], submodel_classes)
        ports, decision = _merge_ports(entry.get("ports", {}), new_ports)
        decisions.append((class_name, decision))
        if ports is None:
            continue
        entry["ports"] = ports
        provenance = list(entry.get("provenance", ()))
        mark = f"merged:{observed_at}"
        if mark not in provenance:
            provenance.append(mark)
        entry["provenance"] = provenance
        entry["constraints"] = _constraints(class_name, ports)
    counts = Counter(item["ports"]["model"]
                     for item in existing["classes"].values())
    existing["meta"]["port_model_counts"] = dict(sorted(counts.items()))
    existing["meta"]["unknown_classes"] = sorted(
        name for name, item in existing["classes"].items()
        if item["ports"]["model"] == "unknown")
    existing["meta"]["merged_at"] = observed_at
    existing["meta"]["merged_decisions"] = [
        f"{name}: {decision}" for name, decision in decisions
        if decision not in ("оставлено",)]
    return existing


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
    parser.add_argument(
        "--merge", action="store_true",
        help="дописать наблюдения корпуса в существующий --out, а не "
             "пересобирать реестр целиком (полного корпуса может не быть)")
    args = parser.parse_args(list(argv) if argv is not None else None)
    corpus = _corpus(args)
    if args.merge:
        if not args.out.exists():
            print(f"слияние: файла {args.out} нет, сливать не с чем")
            return 1
        existing = json.loads(args.out.read_text(encoding="utf-8"))
        data = merge(existing, args.catalog, corpus, args.observed_at)
    else:
        data = generate(args.catalog, corpus, args.observed_at)
    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=2,
                                   sort_keys=True) + "\n", encoding="utf-8")
    print(f"контрактов: {len(data['classes'])}; "
          f"портовые модели: {data['meta']['port_model_counts']}; "
          f"неизмеренных классов: {len(data['meta']['unknown_classes'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
