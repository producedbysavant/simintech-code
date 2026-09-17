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

from .catalog import (DEFAULT_CATALOG_PATH, build_catalog_from_xprt,
                      generate_catalog)


def _class_names(bin_dir: Optional[Path],
                 profile: Optional[Path]) -> Optional[List[str]]:
    """Классы блоков из индекса библиотек, при наличии профиля — только его."""
    if bin_dir is None:
        return None
    from .csl_library import class_names, libraries_in_profile

    libraries = libraries_in_profile(profile) if profile else None
    return class_names(bin_dir, libraries)


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
    args = parser.parse_args(argv)

    if args.xprt is not None:
        from .catalog import merge_catalogs

        parts = []
        for path in args.xprt:
            text = path.read_bytes().decode("utf-8-sig", errors="replace")
            parts.append(build_catalog_from_xprt(text))
            print(f"  {path.name}: классов {len(parts[-1])}")
        catalog = merge_catalogs(parts) if len(parts) > 1 else parts[0]
    else:
        if sys.platform != "win32":
            print("Снятие каталога требует Windows и mmain.exe /regserver. "
                  "Готовую выгрузку можно разобрать через --xprt.",
                  file=sys.stderr)
            return 2
        from . import COMClient

        classes = _class_names(args.bin_dir, args.profile)
        client = COMClient(silent_mode=True).connect()
        try:
            catalog = generate_catalog(client, classes=classes,
                                       keep_project=args.keep_project,
                                       dump_path=args.dump)
        finally:
            client.disconnect()

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
