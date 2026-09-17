"""Генерация каталога свойств блоков из реального SimInTech.

Точка входа пакета (`simintech-generate-catalog`). В COM API нет перечисления
свойств блока, а `SetBlockProp` не отвергает неизвестное имя — ошибка в
каталоге приводит к молчаливому отказу (параметр «установлен», а расчёт идёт по
прежнему значению). Поэтому каталог генерируется, а не пишется вручную.

Два способа:

**Снять выгрузку (Windows).** Создать по блоку на каждый класс, экспортировать
проект в `.xprt` и разобрать его::

    simintech-generate-catalog --bin-dir /mnt/c/SimInTech64/bin \\
        --profile /mnt/c/SimInTech64/bin/profiles/simintech_rus_64/base.xml \\
        --dump /tmp/all-blocks.xprt --out /tmp/catalog.json

Список классов берётся из индекса библиотек `.csl` и ограничивается теми
библиотеками, которые грузит профиль: файл на диске ещё не значит загруженную
библиотеку, и записи из неподхваченных библиотек среда создать не может.

**Пересобрать из готовой выгрузки (где угодно, включая Linux).** Долгая часть —
снятие выгрузки — отделена от разбора::

    simintech-generate-catalog --xprt /tmp/all-blocks.xprt --out catalog.json

Только этот способ доступен без Windows; он же используется тестами.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from .catalog import (DEFAULT_CATALOG_PATH, BlockCatalog,
                      build_catalog_from_xprt, generate_catalog)


def _class_names(bin_dir: Optional[Path],
                 profile: Optional[Path]) -> Optional[List[str]]:
    """Классы для обхода: записи библиотек профиля плюс стандартные.

    Индекс `.csl` знает не все классы, которые среда умеет создавать. «В файл» —
    живой пример: `CreateBlock("В файл")` работает (проверено на SimInTech64),
    а записью библиотеки он не объявлен, и в индекс не попадает. Без этого
    дополнения такие классы остаются без проверки имён — а именно в них запись
    в несуществующее имя и происходит молча.
    """
    if bin_dir is None:
        return None
    from .constants import (SUPPORTED_COM_BLOCK_CLASSES,
                            UNSUPPORTED_COM_BLOCK_CLASSES)
    from .csl_library import class_names, libraries_in_profile

    libraries = libraries_in_profile(profile) if profile else None
    names = set(class_names(bin_dir, libraries))
    names.update(SUPPORTED_COM_BLOCK_CLASSES - UNSUPPORTED_COM_BLOCK_CLASSES)
    return sorted(names)


def _print_coverage(args: argparse.Namespace) -> int:
    """Напечатать покрытие каталога и вернуть код возврата."""
    if args.bin_dir is None:
        print("Для измерения покрытия нужен --bin-dir (каталог поставки).",
              file=sys.stderr)
        return 2
    from .catalog import BlockCatalog, catalog_coverage

    catalog = BlockCatalog.load(args.out)
    report = catalog_coverage(catalog, args.bin_dir, args.profile)
    checked = report["checked_classes"]
    total = report["classes_in_profile"]
    fraction = report["fraction"]

    print(f"Каталог: {args.out}")
    print(f"Библиотек на диске: {report['libraries_total']}"
          f", из них грузит профиль: {report['libraries_in_profile']}")
    print(f"Записей в библиотеках: {report['records_total']}"
          f", без файла набора параметров: {report['records_without_paramset']}")
    print(f"Классов в каталоге: {report['catalog_classes']}")
    print(f"Классов грузит профиль: {total}")
    print(f"Под проверкой имён: {checked} из {total} ({fraction:.1%})")
    beyond = report["beyond_profile"]
    if beyond:
        print(f"Сверх профиля (проверяются, в долю не входят): {len(beyond)}")
    not_in = report["not_in_catalog"]
    if not_in:
        print(f"Без проверки: {len(not_in)}; например: {', '.join(not_in[:5])}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """Точка входа. Возвращает код возврата процесса."""
    parser = argparse.ArgumentParser(
        prog="simintech-generate-catalog",
        description="Сгенерировать каталог свойств блоков из SimInTech.",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_CATALOG_PATH,
                        help="куда сохранить каталог")
    parser.add_argument("--xprt", type=Path, nargs="+",
                        help="собрать каталог из готовых выгрузок (без COM); "
                             "несколько файлов сливаются в один каталог")
    parser.add_argument("--dump", type=Path,
                        help="куда сохранить снятую выгрузку блоков")
    parser.add_argument("--bin-dir", type=Path,
                        help="каталог поставки с библиотеками .csl")
    parser.add_argument("--profile", type=Path,
                        help="base.xml профиля: какие библиотеки загружены")
    parser.add_argument("--keep-project", action="store_true",
                        help="не закрывать проект SimInTech после обхода")
    parser.add_argument("--coverage", action="store_true",
                        help="только измерить, для какой доли классов имена "
                             "параметров проверяются (нужен --bin-dir)")
    parser.add_argument("--merge", type=Path,
                        help="существующий каталог: слить результат с ним и "
                             "создавать только те классы, которых в нём нет")
    args = parser.parse_args(argv)

    if args.coverage:
        return _print_coverage(args)

    existing = BlockCatalog.load(args.merge) if args.merge else None

    if args.xprt is not None:
        from .catalog import merge_catalogs

        parts = []
        for path in args.xprt:
            text = path.read_bytes().decode("utf-8-sig", errors="replace")
            parts.append(build_catalog_from_xprt(text))
            print(f"  {path.name}: классов {len(parts[-1])}")
        catalog = merge_catalogs(parts) if len(parts) > 1 else parts[0]
        if existing is not None:
            catalog = merge_catalogs([existing, catalog])
    else:
        if sys.platform != "win32":
            print("Снятие каталога требует Windows и mmain.exe /regserver. "
                  "Готовую выгрузку можно разобрать через --xprt.",
                  file=sys.stderr)
            return 2
        from . import COMClient
        from .catalog import clean_value, merge_catalogs

        classes = _class_names(args.bin_dir, args.profile)
        if classes is not None and existing is not None:
            # Обход — самая долгая часть (по блоку на класс), и повторять его
            # ради десятка новых классов незачем: уже известные пропускаются,
            # а результат сливается с существующим каталогом. Сверка идёт по
            # обрезанным именам: запись с хвостовым пробелом уже покрыта, а
            # без нормализации она снова попадала в обход и снова «падала»,
            # оказываясь и в каталоге, и в списке провалов.
            known = {clean_value(name) for name in existing.classes()}
            missing = [name for name in classes
                       if clean_value(name) not in known]
            print(f"Уже в каталоге: {len(known)}; к обходу: {len(missing)}")
            classes = missing
        client = COMClient(silent_mode=True).connect()
        try:
            catalog = generate_catalog(client, classes=classes,
                                       keep_project=args.keep_project,
                                       dump_path=args.dump)
        finally:
            client.disconnect()
        if existing is not None:
            catalog = merge_catalogs([existing, catalog])

    path = catalog.save(args.out)
    print(f"Каталог сохранён: {path}")
    print(f"Классов с известными свойствами: {len(catalog)}")
    print(f"Из них с вычисляемыми параметрами: "
          f"{sum(1 for c in catalog.classes() if catalog.readonly_for(c))}")

    failed = catalog.meta.get("failed")
    failed_list = failed if isinstance(failed, list) else []
    if failed_list:
        print(f"\nНе удалось создать (пропущены): {len(failed_list)}",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
