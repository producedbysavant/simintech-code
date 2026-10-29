"""Компактный паспорт Model IR.

Паспорт отвечает на вопрос «что это за модель и что в ней важно», а не
перечисляет все объекты. Полные данные остаются в IR и доступны запросами.
Бюджет жёсткий: не поместившееся называется в блоке Omitted, а не теряется
молча.
"""

from __future__ import annotations

from collections import Counter
from .codes import ContainerKind, ObjectKind
from .contracts import load_default_contracts
from .errors import ModelQueryError
from .graph import ModelIndex, coverage_dict
from .ir import Container, ModelIR

_FOCUS = frozenset({
    "containers", "classes", "signals", "contracts", "discrepancies",
    "geometry",
})


def _header(model: ModelIR) -> str:
    meta = model.meta
    return "\n".join([
        "# Model IR",
        f"model_hash: {meta.structure_hash}",
        f"content_hash: {meta.content_hash}",
        f"ir_schema: {meta.ir_schema}",
        f"primary_source: {meta.primary_source.value}",
        "sources: " + ", ".join(item.value for item in meta.source_set),
        f"source_name: {meta.source_name or '-'}",
        f"containers: {len(model.containers)}; "
        f"objects: {len(model.objects)}; "
        f"wires: {len(model.wires)}; "
        f"branches: {model.coverage.branches}",
    ])


def _coverage(model: ModelIR) -> str:
    data = coverage_dict(model.coverage)
    lines = ["## Coverage"]
    for key in ("unresolved_ends", "unconnected_ends",
                "unresolved_branches", "unknown_object_types",
                "external_submodels", "source_status"):
        lines.append(f"{key}: {data[key]}")
    if data["skipped"]:
        lines.append("skipped: " + ", ".join(
            f"{key}={value}" for key, value in sorted(data["skipped"].items())))
    if data["discrepancy_counts"]:
        lines.append("discrepancies: " + ", ".join(
            f"{key}={value}"
            for key, value in sorted(data["discrepancy_counts"].items())))
    return "\n".join(lines)


def _container_lines(index: ModelIndex, depth: int = 0,
                     max_depth: int = 3) -> list[str]:
    roots = [item for item in index.model.containers
             if item.kind is ContainerKind.PROJECT]
    lines: list[str] = ["## Structure"]
    children: dict[str, list[Container]] = {}
    for container in index.model.containers:
        if container.parent_object_id:
            obj = index.objects.get(container.parent_object_id)
            if obj is not None:
                children.setdefault(obj.container_id, []).append(container)

    def visit(container: Container, level: int) -> None:
        objects = index.objects_in.get(container.id, ())
        wires = index.wires_in.get(container.id, ())
        classes = Counter(item.class_name for item in objects)
        top = ", ".join(name for name, _ in classes.most_common(3))
        lines.append(
            f"{'  ' * level}- {container.address} "
            f"[{container.kind.value}] objects={len(objects)} "
            f"wires={len(wires)}"
            + (f" classes={top}" if top else ""))
        if level >= max_depth:
            nested = children.get(container.id, ())
            if nested:
                lines.append(f"{'  ' * (level + 1)}... "
                             f"ещё контейнеров: {len(nested)}")
            return
        for child in sorted(children.get(container.id, ()),
                            key=lambda item: item.address):
            visit(child, level + 1)

    for root in sorted(roots, key=lambda item: item.address):
        visit(root, depth)
    return lines


def _classes(index: ModelIndex) -> list[str]:
    counts = Counter(item.class_name for item in index.model.objects)
    lines = ["## Classes",
             f"classes: {len(counts)}"]
    for name, count in counts.most_common(20):
        lines.append(f"- {name}: {count}")
    return lines


def _signals(index: ModelIndex) -> list[str]:
    lines = ["## Signals"]
    links = index.model.memory_links
    lines.append(f"memory_links: {len(links)}")
    for link in links[:10]:
        lines.append(
            f"- {link.variable or '<без имени>'}: "
            f"writers={len(link.writers)} readers={len(link.readers)} "
            f"resolved={'yes' if link.resolved else 'no'}")
    submodels = [item for item in index.model.objects
                 if item.kind is ObjectKind.SUBMODEL]
    lines.append(f"submodels: {len(submodels)}")
    for obj in submodels[:5]:
        boundaries = [item for item in index.model.boundaries
                      if item.submodel_object_id == obj.id]
        resolved = sum(1 for item in boundaries if item.resolved)
        lines.append(
            f"- {obj.address}: boundary_ports={len(boundaries)} "
            f"resolved={resolved}")
    return lines


def _hot(index: ModelIndex) -> list[str]:
    degree: Counter[str] = Counter()
    for wire in index.model.wires:
        if wire.start.object_id:
            degree[wire.start.object_id] += 1
        if wire.end.object_id:
            degree[wire.end.object_id] += 1
    for obj in index.model.objects:
        degree[obj.id] += len(obj.ports)
    lines = ["## Hot nodes"]
    for object_id, count in degree.most_common(10):
        node_obj = index.objects.get(object_id)
        if node_obj is not None:
            lines.append(f"- {node_obj.address}: degree={count}")
    return lines


def _discrepancies(model: ModelIR) -> list[str]:
    lines = ["## Discrepancies"]
    for item in model.discrepancies[:10]:
        lines.append(f"- {item.severity.value} {item.code}: {item.subject}")
    return lines


def _contracts(model: ModelIR) -> list[str]:
    try:
        registry = load_default_contracts()
    except ModelQueryError as exc:
        return ["## Contracts", f"registry: unavailable ({exc})"]
    coverage = registry.coverage()
    lines = [
        "## Contracts",
        f"registry: {coverage.classes} classes, "
        f"measured={coverage.measured}, derived={coverage.derived}, "
        f"unknown={coverage.unknown}",
    ]
    if coverage.port_models:
        lines.append("port_models: " + ", ".join(
            f"{name}={count}"
            for name, count in sorted(coverage.port_models.items())))
    counts = Counter(item.class_name for item in model.objects)
    for name, _count in counts.most_common(10):
        contract = registry.get(name)
        if contract is None:
            lines.append(f"- {name}: нет в реестре")
            continue
        ports = contract.ports
        if ports.unknown:
            reason = f" ({ports.reason})" if ports.reason else ""
            described = f"unknown{reason}"
        else:
            described = (f"{ports.model} in={len(ports.inputs)} "
                         f"out={len(ports.outputs)}")
        lines.append(f"- {name}: ports={described} "
                     f"props={len(contract.properties)}")
    return lines


def _geometry(index: ModelIndex) -> list[str]:
    lines = ["## Geometry"]
    for container in index.model.containers:
        objects = index.objects_in.get(container.id, ())
        if not objects:
            continue
        xs = [point[0] for obj in objects for point in obj.points]
        ys = [point[1] for obj in objects for point in obj.points]
        if xs and ys:
            lines.append(
                f"- {container.address}: "
                f"bbox=({min(xs):g},{min(ys):g})-({max(xs):g},{max(ys):g})")
    return lines


def _join(blocks: list[list[str]]) -> str:
    return "\n".join(line for lines in blocks for line in lines)


def build_manifest(model: ModelIR, budget_tokens: int = 3000,
                   focus: str = "") -> str:
    """Собрать Markdown-паспорт в жёстком бюджете токенов."""
    if not 2000 <= budget_tokens <= 5000:
        raise ModelQueryError(
            f"budget_tokens={budget_tokens}: допустимо 2000..5000")
    if focus and focus not in _FOCUS:
        raise ModelQueryError(f"неизвестный focus {focus!r}")
    limit = budget_tokens * 3
    index = ModelIndex(model)
    sections: list[tuple[str, list[str]]] = [
        ("header", _header(model).splitlines()),
        ("coverage", _coverage(model).splitlines()),
    ]
    optional: list[tuple[str, list[str]]] = [
        ("containers", _container_lines(index)),
        ("classes", _classes(index)),
        ("signals", _signals(index)),
        ("contracts", _contracts(model)),
        ("hot", _hot(index)),
        ("discrepancies", _discrepancies(model)),
    ]
    if focus == "geometry":
        optional.append(("geometry", _geometry(index)))
    selected = [item for item in optional
                if not focus or item[0] == focus or (
                    focus in ("containers", "geometry")
                    and item[0] == "containers")]
    base = [sections[0][1], sections[1][1]]
    extra: list[list[str]] = []
    included: list[str] = []
    omitted: list[str] = []
    for name, lines in selected:
        if len(_join(base + extra + [lines])) <= limit:
            extra.append(lines)
            included.append(name)
        else:
            omitted.append(name)
    # Omitted - такое же обещание, как и секции: если он не помещается,
    # вытесняем последнюю добавленную секцию, пока не освободится место.
    while omitted:
        block = ("## Omitted\n" + ", ".join(omitted) +
                 "\nПолные данные: query_model.").splitlines()
        if len(_join(base + extra + [block])) <= limit:
            extra.append(block)
            break
        if not extra:
            raise ModelQueryError(
                "паспорт не помещается в бюджет: заголовок и покрытие "
                "занимают весь лимит")
        extra.pop()
        omitted.append(included.pop())
    return _join(base + extra)
