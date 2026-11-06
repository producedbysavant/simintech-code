"""Функциональная семантика Model IR: влияние входов на выход.

Модуль отвечает на вопрос «какие источники действительно влияют на выход»,
а не «какие объекты достижимы по проводам». Структурные рёбра ведут к
блоку, функциональные зависимости внутри блока берутся из контракта.
Неизвестность остаётся неизвестностью: структурный путь не повышает
статус цепочки до `contract`.
"""

from __future__ import annotations

from collections.abc import Mapping as MappingABC
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .codes import ObjectKind, PortDirection
from .contracts import (
    BlockContract,
    BlockContractRegistry,
    Dependency,
    KnownAbsence,
    load_default_contracts,
)
from .errors import ModelQueryError
from .experiments import (
    MAX_RECORDS,
    ExperimentRecord,
    parse_experiment_record,
)
from .graph import ModelIndex, QueryResult
from .ir import ModelIR, ModelObject

_STRUCTURAL_KINDS = frozenset({"wire", "branch", "boundary"})
_RUN_SCRIPT_SLOTS = ("script", "Script", "OnRunScript")
_INIT_SCRIPT_SLOTS = ("OnInitScript",)
_INCLUDE = frozenset({"contract", "not_established", "experiment"})
_MAX_UNKNOWN = 200
_MAX_LIMITATIONS = 50


@dataclass(frozen=True, slots=True)
class BehaviorScenario:
    id: str
    target: str
    inputs: tuple[str, ...] = ()
    checks: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class BehaviorSpec:
    schema: str
    model_hash: str
    scenarios: tuple[BehaviorScenario, ...] = ()


def parse_behavior_spec(data: Mapping[str, Any]) -> BehaviorSpec:
    """Разобрать сценарии поведения модели; `checks` не исполняются."""
    schema = str(data.get("schema", ""))
    if schema != "behavior-spec/1":
        raise ModelQueryError(
            f"behavior-spec: неизвестная схема {schema!r}")
    model_hash = str(data.get("model_hash", "")).strip()
    if not model_hash:
        raise ModelQueryError("behavior-spec: пустой model_hash")
    raw_scenarios = data.get("scenarios", [])
    if not isinstance(raw_scenarios, list):
        raise ModelQueryError("behavior-spec: scenarios не список")
    scenarios: list[BehaviorScenario] = []
    for pos, item in enumerate(raw_scenarios):
        where = f"behavior-spec.scenarios[{pos}]"
        if not isinstance(item, MappingABC):
            raise ModelQueryError(f"{where}: не объект")
        ident = str(item.get("id", "")).strip()
        target = str(item.get("target", "")).strip()
        if not ident or not target:
            raise ModelQueryError(f"{where}: нужны id и target")
        raw_inputs = item.get("inputs", [])
        if not isinstance(raw_inputs, list) or not all(
                isinstance(value, str) for value in raw_inputs):
            raise ModelQueryError(f"{where}: inputs не список строк")
        raw_checks = item.get("checks", [])
        if not isinstance(raw_checks, list) or not all(
                isinstance(value, MappingABC) for value in raw_checks):
            raise ModelQueryError(f"{where}: checks не список объектов")
        scenarios.append(BehaviorScenario(
            id=ident, target=target, inputs=tuple(raw_inputs),
            checks=tuple(dict(value) for value in raw_checks)))
    return BehaviorSpec(
        schema=schema, model_hash=model_hash,
        scenarios=tuple(scenarios))


def _item_addresses(item: Mapping[str, Any]) -> set[str]:
    values = {str(item.get("target", ""))}
    source = item.get("source", {})
    if isinstance(source, MappingABC):
        values.add(str(source.get("address", "")))
    values.update(str(value) for value in item.get("path", ()))
    for hop in item.get("hops", ()):
        values.add(str(hop.get("from", "")))
        values.add(str(hop.get("to", "")))
    return {value for value in values if value}


def _object_address(address: str) -> bool:
    """Адрес объекта, а не порта (`:0`) или свойства (`@name`)."""
    if "@" in address:
        return False
    return not address.rsplit(":", 1)[-1].isdigit()


def _matches_source(source: str, candidates: set[str]) -> bool:
    if source in candidates:
        return True
    if not _object_address(source):
        return False
    return any(candidate == source
               or candidate.startswith(source + ":")
               or candidate.startswith(source + "@")
               for candidate in candidates)


def _has_branch(item: Mapping[str, Any]) -> bool:
    return any(str(hop.get("kind", "")) in ("conditional", "control")
               for hop in item.get("hops", ()))


def _cap_limitations(items: list[dict[str, str]]) -> list[dict[str, str]]:
    if len(items) <= _MAX_LIMITATIONS:
        return items
    extra = len(items) - _MAX_LIMITATIONS
    return items[:_MAX_LIMITATIONS] + [{
        "kind": "limitations_truncated",
        "text": f"ещё {extra} ограничений не показаны",
    }]


class _ExperimentSet:
    """Применимые, отрицательные и неприменимые свидетельства."""

    def __init__(self, index: ModelIndex,
                 records: Iterable[ExperimentRecord]) -> None:
        records = tuple(records)
        self.supplied = len(records)
        self.applicable: list[ExperimentRecord] = []
        self.negative: list[ExperimentRecord] = []
        self.inapplicable: list[dict[str, str]] = []
        self.applied: list[ExperimentRecord] = []
        self.blocked: list[ExperimentRecord] = []
        self.limitations: list[dict[str, str]] = []
        self._notes: set[tuple[str, str, str]] = set()
        self._limit_hit = False
        self._by_target: dict[str, list[ExperimentRecord]] = {}
        structure_hash = index.model.meta.structure_hash
        content_hash = index.model.meta.content_hash
        for record in records:
            if record.status == "unknown":
                self._reject(record, "status_unknown")
            elif record.structure_hash != structure_hash:
                self._reject(record, "structure_hash_mismatch")
            elif record.content_hash != content_hash:
                self._reject(record, "content_hash_mismatch")
            elif not record.observed:
                self.negative.append(record)
            else:
                self.applicable.append(record)
                self._by_target.setdefault(record.target, []).append(record)

    def _note(self, kind: str, ref: str, text: str) -> None:
        key = (kind, ref, text)
        if key in self._notes:
            return
        self._notes.add(key)
        if len(self.limitations) >= _MAX_LIMITATIONS:
            self._limit_hit = True
            return
        item = {"kind": kind, "text": text}
        if ref:
            item["ref"] = ref
        self.limitations.append(item)

    def _reject(self, record: ExperimentRecord, reason: str) -> None:
        self.inapplicable.append({"id": record.id, "reason": reason})
        self._note("experiment_inapplicable", record.id,
                   f"свидетельство неприменимо: {reason}")

    def apply(self, items: list[dict[str, Any]],
              include: frozenset[str]) -> None:
        used: set[str] = set()
        supported: set[str] = set()
        for item in items:
            target = str(item.get("target", ""))
            candidates = _item_addresses(item)
            for record in self._by_target.get(target, ()):
                if not _matches_source(record.source, candidates):
                    continue
                used.add(record.id)
                evidence = item["evidence"]
                status = str(evidence.get("status", ""))
                reason = str(evidence.get("reason", ""))
                if status in ("contract", "experiment"):
                    supported.add(record.id)
                elif reason == "unapproved":
                    evidence["status"] = "experiment"
                    evidence["ref"] = f"experiment:{record.id}"
                    evidence["contract_status"] = status
                    evidence["contract_reason"] = reason
                    evidence.pop("reason", None)
                    supported.add(record.id)
                else:
                    self.blocked.append(record)
                    self._note(
                        "experiment_not_applicable", record.id,
                        f"свидетельство не отменяет причину "
                        f"{reason or status}")
                    continue
                evidence.setdefault("experiments", []).append(record.id)
                self._note(
                    "experiment_scope", record.id,
                    "наблюдение относится к одному сценарию; вывод не "
                    "переносится на другие входы и модели")
                if _object_address(record.source):
                    self._note(
                        "experiment_object_address", record.id,
                        "адрес источника задан объектом; совпадение шире "
                        "конкретного порта")
                if _has_branch(item):
                    self._note(
                        "experiment_branch_ambiguous", record.id,
                        "цепочка содержит условный или управляющий хоп; "
                        "один сценарий не фиксирует ветвь")
                for text in record.limitations:
                    self._note("experiment_record", record.id, text)
        self.applied = [record for record in self.applicable
                        if record.id in supported]
        for record in self.applicable:
            if record.id not in used:
                self._note("experiment_unmatched", record.id,
                           "свидетельство не сопоставлено с цепочкой")
        for record in self.negative:
            self._note(
                "experiment_negative", record.id,
                "эффект не наблюдался; это не доказывает отсутствие влияния")
            for text in record.limitations:
                self._note("experiment_record", record.id, text)
        if self.applied and "experiment" not in include:
            self._note("experiment_filtered", "",
                       "экспериментальные цепочки скрыты фильтром include")

    def summary(self) -> dict[str, int]:
        return {
            "supplied": self.supplied,
            "applied": len(self.applied),
            "blocked": len(self.blocked),
            "negative": len(self.negative),
            "inapplicable": len(self.inapplicable),
        }


def influence(
        index: ModelIndex, registry: BlockContractRegistry, target: str,
        max_depth: int = 64,
        include: Iterable[str] = ("contract", "not_established", "experiment"),
        max_items: int = 200,
        experiments: Iterable[ExperimentRecord | Mapping[str, Any]] = ()
        ) -> QueryResult:
    """Цепочки влияния на выход `target`.

    `target` - порт (`объект:индекс`) или объект с одним выходом. Элемент
    ответа - цепочка от цели к терминальному источнику; `hops` хранят
    функциональные переходы, `path` - адреса пройденных узлов.
    Экспериментальные свидетельства применяются к цепочке целиком и не
    превращают отрицательный результат в известное отсутствие.
    """
    allowed = _include_filter(include)
    if isinstance(experiments, (ExperimentRecord, MappingABC)):
        experiments = (experiments,)
    records: list[ExperimentRecord] = []
    for item in experiments:
        if len(records) >= MAX_RECORDS:
            raise ModelQueryError(
                f"experiment: больше {MAX_RECORDS} записей")
        if isinstance(item, ExperimentRecord):
            records.append(item)
        elif isinstance(item, MappingABC):
            records.append(parse_experiment_record(item))
        else:
            raise ModelQueryError(
                "experiment: запись не ExperimentRecord и не объект")
    experiment_set = _ExperimentSet(index, records)
    limitations: list[dict[str, str]] = []
    items: list[dict[str, Any]] = []
    unknown: list[str] = []
    absences: list[dict[str, Any]] = []
    walker = _Walker(index, registry, items, unknown, absences, max_depth,
                     limitations)
    for port_id in _target_ports(index, target):
        walker.walk(port_id, [], [], 0, frozenset())
    experiment_set.apply(items, allowed)
    filtered = [item for item in items
                if item["evidence"]["status"] in allowed]
    total = len(filtered)
    unique_unknown = tuple(dict.fromkeys(unknown))
    truncated = (total > max_items
                 or len(unique_unknown) > _MAX_UNKNOWN)
    if not records:
        limitations.append({
            "kind": "experiments_absent",
            "text": "эксперименты не переданы: ответ основан только "
                    "на контрактах",
        })
    if unique_unknown:
        limitations.append({
            "kind": "unknown_present",
            "text": f"неизвестных участков: {len(unique_unknown)}",
        })
    if truncated:
        limitations.append({
            "kind": "truncated",
            "text": f"ответ усечён: показано {min(total, max_items)} "
                    f"из {total} цепочек",
        })
    return QueryResult(
        query="influence",
        scope="influence",
        model_hash=index.model.meta.structure_hash,
        items=tuple(filtered[:max_items]),
        unknown=unique_unknown[:_MAX_UNKNOWN],
        truncated=truncated,
        evidence={
            "known_absences": absences,
            "items_total": total,
            "limitations": _cap_limitations(
                limitations + experiment_set.limitations),
            "experiments": experiment_set.summary(),
        },
    )


_UNKNOWN_REASONS = (
    "class_unknown", "object_script_run", "rejected", "object_script_init",
    "script_defined", "external_submodel", "behavior_unknown", "unapproved",
)


def semantic_coverage(
        model: ModelIR,
        registry: BlockContractRegistry | None = None) -> dict[str, Any]:
    """Сводка семантической известности модели.

    Локальная неизвестность остаётся в ответах `influence`; здесь только
    счётчики, по которым видно, где структура разобрана, а семантика нет.
    """
    registry = registry or load_default_contracts()
    objects = [obj for obj in model.objects
               if obj.kind in (ObjectKind.BLOCK, ObjectKind.SUBMODEL,
                               ObjectKind.MEMORY_CELL, ObjectKind.UNKNOWN)]
    unknown = {reason: 0 for reason in _UNKNOWN_REASONS}
    by_class: dict[str, dict[str, Any]] = {}
    total = with_behavior = approved = known_ports = with_init = 0
    deps_total = deps_known = absences_total = 0
    for obj in objects:
        total += 1
        contract = registry.get(obj.class_name)
        entry = by_class.setdefault(obj.class_name, {
            "objects": 0,
            "with_behavior": 0,
            "approved": 0,
            "with_init_script": 0,
            "pilot_scope": contract.pilot_scope if contract else "",
            "review_status": (contract.review.effective_status
                              if contract else ""),
            "review_ref": _review_ref(contract) if contract else "",
        })
        entry["objects"] += 1
        if _object_init_script(obj):
            with_init += 1
            entry["with_init_script"] += 1
        if contract is not None and not contract.ports.unknown:
            known_ports += 1
        if contract is not None and _behavior_known(contract):
            with_behavior += 1
            entry["with_behavior"] += 1
            if contract.review.approved:
                approved += 1
                entry["approved"] += 1
        reason = _unknown_reason(obj, contract)
        if reason:
            unknown[reason] += 1
        if contract is not None:
            try:
                dependencies = registry.dependencies_for(
                    obj.class_name, _props(obj))
            except ModelQueryError:
                dependencies = ()
            deps_total += len(dependencies)
            deps_known += sum(
                1 for dependency in dependencies
                if _dependency_known(contract, dependency, obj))
            absences_total += sum(
                1 for absence in contract.known_absences
                if _absence_known(contract, absence))
    scopes: dict[str, int] = {}
    review_counts = {"approved": 0, "preliminary": 0, "rejected": 0}
    preliminary_classes: list[str] = []
    review_refs: dict[str, str] = {}
    for name in registry.classes():
        item = registry.get(name)
        scope = item.pilot_scope if item is not None else ""
        if scope:
            scopes[scope] = scopes.get(scope, 0) + 1
        if item is None or not item.pilot_scope:
            continue
        status = item.review.effective_status
        review_counts[status] = review_counts.get(status, 0) + 1
        if status == "preliminary":
            preliminary_classes.append(name)
        if item.review.ref:
            review_refs[name] = item.review.ref
    return {
        "objects_total": total,
        "objects_with_behavior": with_behavior,
        "objects_with_approved_behavior": approved,
        "objects_with_known_ports": known_ports,
        "objects_with_init_script": with_init,
        "objects_unknown": unknown,
        "dependencies_total": deps_total,
        "dependencies_known": deps_known,
        "known_absences_total": absences_total,
        "pilot_scope_counts": scopes,
        "review_counts": review_counts,
        "preliminary_classes": preliminary_classes,
        "review_refs": review_refs,
        "by_class": by_class,
    }


def _behavior_known(contract: BlockContract) -> bool:
    if contract.review.rejected:
        return False
    if contract.behavior.operation == "unknown":
        return False
    return _has_contract_semantics(contract)


def _absence_known(contract: BlockContract, absence: KnownAbsence) -> bool:
    """Отсутствие установлено, если оно измерено или строка утверждена.

    Claim/derived из предварительной строки не становится известным
    отсутствием: иначе предварительная таблица выдала бы утверждение.
    Отвергнутая строка не участвует в семантике даже при `measured`.
    """
    if contract.review.rejected:
        return False
    status = absence.provenance.status
    if status == "measured":
        return True
    return (status in ("claim", "derived")
            and contract.review.approved)


def _unknown_reason(obj: ModelObject,
                    contract: BlockContract | None) -> str:
    if contract is None:
        return "class_unknown"
    if _object_run_script(obj):
        return "object_script_run"
    if contract.review.rejected:
        return "rejected"
    if contract.ports.reason == "script_defined_ports":
        return "script_defined"
    if obj.kind is ObjectKind.SUBMODEL and obj.filename:
        return "external_submodel"
    if not _behavior_known(contract):
        if _object_init_script(obj):
            return "object_script_init"
        return "behavior_unknown"
    if not contract.review.approved:
        return "unapproved"
    return ""


def _no_dependency_reason(obj: ModelObject, contract: BlockContract) -> str:
    """Причина для выхода без объявленных зависимостей."""
    if contract.review.rejected:
        return "rejected"
    if contract.ports.reason == "script_defined_ports":
        return "script_defined"
    if obj.kind is ObjectKind.SUBMODEL and obj.filename:
        return "external_submodel"
    if _object_init_script(obj) and not _has_contract_semantics(contract):
        return "object_script_init"
    return "behavior_unknown"


def _dependency_known(contract: BlockContract, dependency: Dependency,
                      obj: ModelObject) -> bool:
    if _object_run_script(obj):
        return False
    if contract.review.rejected:
        return False
    if dependency.kind in ("script", "unknown"):
        return False
    if dependency.kind == "conditional" and dependency.condition is None:
        return False
    if dependency.provenance.status == "measured":
        return True
    return (dependency.provenance.status in ("claim", "derived")
            and contract.review.approved)


def _include_filter(include: Iterable[str]) -> frozenset[str]:
    if isinstance(include, str):
        include = (include,)
    values = frozenset(include)
    if not values or values - _INCLUDE:
        raise ModelQueryError(
            f"include={sorted(values)}: допустимы contract, experiment "
            f"и not_established")
    return values


def _target_ports(index: ModelIndex, target: str) -> list[str]:
    try:
        return [index.port(target).id]
    except ModelQueryError:
        pass
    obj = index.object(target)
    outputs = [port.id for port in obj.ports
               if port.direction in (PortDirection.OUT,
                                     PortDirection.UNDIRECTED)]
    if not outputs:
        raise ModelQueryError(
            f"{target}: у объекта нет выхода для influence")
    return outputs


def _props(obj: ModelObject) -> dict[str, str]:
    return {name: prop.value for name, prop in obj.props.items()}


def _review_ref(contract: BlockContract) -> str:
    """Ссылка на строку эталона, к которой относится контракт."""
    if contract.review.ref:
        return contract.review.ref
    for dependency in contract.dependencies:
        if dependency.provenance.ref:
            return dependency.provenance.ref
    for absence in contract.known_absences:
        if absence.provenance.ref:
            return absence.provenance.ref
    return contract.behavior.provenance.ref


def _object_run_script(obj: ModelObject) -> str:
    """Слот поведения, исполняемого на каждом шаге."""
    for slot in _RUN_SCRIPT_SLOTS:
        info = obj.scripts.get(slot)
        if info is not None and info.present:
            return slot
    return ""


def _object_init_script(obj: ModelObject) -> str:
    """Слот инициализации: начальное состояние, не поведение."""
    for slot in _INIT_SCRIPT_SLOTS:
        info = obj.scripts.get(slot)
        if info is not None and info.present:
            return slot
    return ""


def _has_contract_semantics(contract: BlockContract) -> bool:
    """Контракт описывает поведение, а не только порты."""
    return bool(contract.dependencies) or any(
        _absence_known(contract, absence)
        for absence in contract.known_absences)


class _Walker:
    def __init__(self, index: ModelIndex, registry: BlockContractRegistry,
                 items: list[dict[str, Any]], unknown: list[str],
                 absences: list[dict[str, Any]], max_depth: int,
                 limitations: list[dict[str, str]] | None = None) -> None:
        self.index = index
        self.registry = registry
        self.items = items
        self.unknown = unknown
        self.absences = absences
        self.max_depth = max_depth
        self.limitations = limitations if limitations is not None else []
        self._init_seen: set[str] = set()

    def _note_init(self, obj: ModelObject) -> None:
        slot = _object_init_script(obj)
        if not slot:
            return
        ref = f"{obj.address}@script:{slot}"
        if ref in self._init_seen:
            return
        self._init_seen.add(ref)
        self.limitations.append({
            "kind": "init_script",
            "ref": ref,
            "text": "начальное состояние задано OnInitScript; зависимости "
                    "контракта не понижены",
        })

    def walk(self, port_id: str, hops: list[dict[str, Any]],
             path: list[str], depth: int,
             visited: frozenset[str]) -> None:
        name = self.index.node_name(port_id)
        if depth > self.max_depth:
            self.unknown.append(f"{name}: depth_limit")
            return
        if port_id in visited:
            self.unknown.append(f"{name}: cycle")
            return
        visited = visited | {port_id}
        path = path + [name]
        port = self.index.ports.get(port_id)
        obj = self.index.node_object(port_id)
        if port is None or obj is None:
            self.unknown.append(f"{name}: unresolved_port")
            return
        if port.direction in (PortDirection.IN, PortDirection.UNDIRECTED):
            self._walk_input(port_id, hops, path, depth, visited)
            return
        self._walk_output(port, obj, name, hops, path, depth, visited)

    def _walk_input(self, port_id: str, hops: list[dict[str, Any]],
                    path: list[str], depth: int,
                    visited: frozenset[str]) -> None:
        incoming = self.index.reverse.get(port_id, ())
        memory = [edge for edge in incoming if edge.kind == "memory"]
        for edge in memory:
            hop = {
                "from": self.index.node_name(port_id),
                "to": self.index.node_name(edge.src),
                "kind": "stateful",
                "condition": None,
                "state": {"kind": "memory"},
                "evidence": {"status": "contract", "ref": edge.wire_id},
            }
            self.walk(edge.src, hops + [hop], path, depth + 1, visited)
        structural = [edge for edge in incoming
                      if edge.kind in _STRUCTURAL_KINDS]
        if structural:
            for edge in structural:
                self.walk(edge.src, hops, path, depth + 1, visited)
            return
        if not memory:
            self._emit({"kind": "port",
                        "address": self.index.node_name(port_id)},
                       hops, path)

    def _walk_output(self, port: Any, obj: ModelObject, name: str,
                     hops: list[dict[str, Any]], path: list[str],
                     depth: int, visited: frozenset[str]) -> None:
        self._note_init(obj)
        self._collect_absences(obj, port.index, name)
        memory = [edge for edge in self.index.reverse.get(port.id, ())
                  if edge.kind == "memory"]
        if memory:
            for edge in memory:
                hop = {
                    "from": name,
                    "to": self.index.node_name(edge.src),
                    "kind": "stateful",
                    "condition": None,
                    "state": {"kind": "memory"},
                    "evidence": {"status": "contract", "ref": edge.wire_id},
                }
                self.walk(edge.src, hops + [hop], path, depth + 1, visited)
            return
        contract = self.registry.get(obj.class_name)
        if contract is None:
            self.unknown.append(f"{name}: class_unknown")
            return
        start = len(self.items)
        dependencies = [dependency for dependency in
                        self.registry.dependencies_for(
                            obj.class_name, _props(obj))
                        if dependency.output == port.index]
        if not dependencies:
            script = _object_run_script(obj)
            if script:
                address = _source_address(
                    obj, {"kind": "script", "name": script})
                hop = {
                    "from": name,
                    "to": address,
                    "kind": "script",
                    "condition": None,
                    "state": None,
                    "evidence": _evidence(
                        "not_established", "", "object_script_run"),
                }
                self._emit({"kind": "script", "address": address},
                           hops + [hop], path)
                self.unknown.append(f"{name}: object_script_run")
            else:
                reason = _no_dependency_reason(obj, contract)
                self.unknown.append(f"{name}: {reason}")
            self._detail_and_downgrade(port, start)
            return
        for dependency in dependencies:
            self._walk_dependency(
                dependency, contract, obj, name, port, hops, path, depth,
                visited)
        self._detail_and_downgrade(port, start)

    def _detail_and_downgrade(self, port: Any, start: int) -> None:
        """Детализировать субмодель внутри страницы, не поднимая статус.

        Внешний контракт даёт функциональные хопы; переход по boundary
        показывает внутреннюю цепочку. Если внутри есть неизвестный блок,
        условные ветви понижаются, а управляющая зависимость остаётся
        отдельной.
        """
        details = self._detail_unknown(port)
        if not details:
            return
        self.unknown.extend(details)
        reason = details[0]
        for item in self.items[start:]:
            if not any(hop["kind"] == "conditional"
                       for hop in item["hops"]):
                continue
            item["evidence"]["status"] = "not_established"
            item["evidence"]["reason"] = reason
            for hop in item["hops"]:
                if hop["kind"] == "conditional":
                    hop["evidence"]["status"] = "not_established"
                    hop["evidence"]["reason"] = reason

    def _detail_unknown(self, port: Any) -> list[str]:
        obj = self.index.node_object(port.id)
        if obj is None or obj.kind is not ObjectKind.SUBMODEL:
            return []
        details: list[str] = []
        for edge in self.index.reverse.get(port.id, ()):
            if edge.kind != "boundary":
                continue
            walker = _Walker(self.index, self.registry, [], details, [],
                             self.max_depth, self.limitations)
            walker.walk(edge.src, [], [], 0, frozenset())
        return details

    def _walk_dependency(
            self, dependency: Dependency, contract: BlockContract,
            obj: ModelObject, name: str, port: Any,
            hops: list[dict[str, Any]], path: list[str], depth: int,
            visited: frozenset[str]) -> None:
        status, ref, reason, review_ref = _dependency_evidence(
            contract, dependency, obj)
        run_script = _object_run_script(obj)
        hop_kind = "script" if run_script else dependency.kind
        source = dependency.source
        source_port = None
        if source.get("kind") == "port":
            raw_index = source.get("index")
            if isinstance(raw_index, int):
                source_port = obj.port(raw_index)
        if source_port is not None:
            to_address = self.index.node_name(source_port.id)
        else:
            to_address = _source_address(obj, source)
        hop = {
            "from": name,
            "to": to_address,
            "kind": hop_kind,
            "condition": (dict(dependency.condition)
                          if dependency.condition is not None else None),
            "state": (dict(dependency.state)
                      if dependency.state is not None else None),
            "evidence": _evidence(status, ref, reason, review_ref),
        }
        if source.get("kind") in ("property", "state"):
            self._emit(
                {"kind": str(source.get("kind")),
                 "address": _source_address(obj, source)},
                hops + [hop], path)
            return
        if source.get("kind") == "port":
            if source_port is None:
                self.unknown.append(f"{name}: source_port_missing")
                return
            self.walk(source_port.id, hops + [hop], path, depth + 1,
                      visited)
            return
        self.unknown.append(
            f"{name}: unsupported_source_{source.get('kind')}")

    def _collect_absences(self, obj: ModelObject, output: int,
                          target: str) -> None:
        contract = self.registry.get(obj.class_name)
        if contract is None:
            return
        for absence in contract.known_absences:
            if absence.output != output:
                continue
            if not _absence_known(contract, absence):
                continue
            self.absences.append({
                "target": target,
                "source": dict(absence.source),
                "provenance": _evidence(
                    absence.provenance.status, absence.provenance.ref, "",
                    _review_ref(contract)),
            })

    def _emit(self, source: Mapping[str, Any],
              hops: list[dict[str, Any]], path: list[str]) -> None:
        status, reason, review_ref = _chain_status(hops)
        self.items.append({
            "target": path[0] if path else "",
            "source": dict(source),
            "path": list(path),
            "hops": list(hops),
            "evidence": _evidence(status, "chain", reason, review_ref),
            "unknown": None,
        })


def _source_address(obj: ModelObject, source: Mapping[str, Any]) -> str:
    kind = str(source.get("kind", "source"))
    if kind in ("property", "state"):
        return f"{obj.address}@{kind}:{source.get('name', '')}"
    return (f"{obj.address}@{kind}:"
            f"{source.get('name', source.get('index', ''))}")


def _dependency_evidence(
        contract: BlockContract, dependency: Dependency,
        obj: ModelObject) -> tuple[str, str, str, str]:
    ref = dependency.provenance.ref
    review_ref = _review_ref(contract)
    if _object_run_script(obj):
        return "not_established", ref, "object_script_run", review_ref
    if contract.review.rejected:
        return "not_established", ref, "rejected", review_ref
    if dependency.kind == "script":
        return ("not_established", ref, dependency.reason or "script",
                review_ref)
    if dependency.kind == "unknown":
        return ("not_established", ref, dependency.reason or "unknown",
                review_ref)
    if dependency.kind == "conditional" and dependency.condition is None:
        return ("not_established", ref,
                dependency.reason or "condition_unknown", review_ref)
    status = dependency.provenance.status
    if status == "measured":
        return "contract", ref, "", review_ref
    if status in ("claim", "derived") and contract.review.approved:
        return "contract", ref, "", review_ref
    return "not_established", ref, "unapproved", review_ref


def _chain_status(hops: list[dict[str, Any]]) -> tuple[str, str, str]:
    if not hops:
        return "not_established", "no_hops", ""
    for hop in hops:
        evidence = hop["evidence"]
        if evidence["status"] != "contract":
            return ("not_established", str(evidence.get("reason", "")),
                    str(evidence.get("review_ref", "")))
    return "contract", "", ""


def _evidence(status: str, ref: str, reason: str,
              review_ref: str = "") -> dict[str, str]:
    result = {"status": status}
    if ref:
        result["ref"] = ref
    if reason:
        result["reason"] = reason
    if review_ref:
        result["review_ref"] = review_ref
    return result
