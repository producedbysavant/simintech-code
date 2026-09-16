"""Библиотеки блоков SimInTech: разбор индекса `.csl` без COM.

Библиотека блоков (`bin/*.csl`, `bin/*.xcsl`) — сериализованный TStream-документ
Delphi: строки лежат в UTF-16LE, а **в хвосте файла** лежит индекс палитры —
сперва список имён записей, затем пары «имя записи → файл набора параметров»
(`ParamSet_mvtu/<путь>.ps`). Здесь разбирается именно индекс: он даёт перечень
классов блоков, которые среда умеет создавать, — то, чего не хватало, чтобы
отличить «класса нет в поставке» от «класса нет в каталоге».

Формат разобран по файлам поставки, а не по документации: проверка — каждый
извлечённый путь обязан указывать на существующий `.ps`. На поставке
SimInTech64 из 1153 путей существуют 1139; остальные отсутствуют и в самом
дистрибутиве (один из них, например, ведёт в сборочное дерево разработчика,
`..\\..\\..\\HomeGit\\digcomm\\...`).

Наборы параметров (`ParamSet_mvtu/*.ps`) здесь **не разбираются**: у них
последовательная бинарная грамматика (имя, подпись, тип, значение по
умолчанию, привязка к DLL, класс, код), и подписи бывают латиницей — отличить
имя параметра от подписи без полной грамматики нельзя. Это следующий шаг;
здесь — только имена записей и их привязка к файлам наборов.

**Ограничение:** разбирается только индекс с внешними наборами параметров.
Часть библиотек (`Aircraft_dynamics`, `LIB_FC`, `LIB_Kinetika_Nejtronov`,
`LIB_Vodorod`, `Viewer3DLib`, `interfejs`, `library_MK17`, `CommonLib.xcsl`,
`HS.xcsl`, ...) объявляет записи **внутри** себя, без файла `.ps`; такие
библиотеки дают ноль записей. Это не «библиотека пуста», а «записи объявлены
иным способом» — и об этом надо говорить явно, иначе ноль читается как
отсутствие блоков. На поставке SimInTech64 разбор даёт 1296 записей в 51
библиотеке, из них 1282 с существующим файлом набора.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Sequence, Tuple

#: Каталог наборов параметров относительно `bin/`.
PARAMSET_DIR = "ParamSet_mvtu"

#: Строки в `.csl` — UTF-16LE. Берём печатаемые последовательности; всё
#: остальное (числа, флаги, геометрия) пропускается.
_STRING_RE = re.compile(r"[ -~Ѐ-ӿ\\/\.\(\)@$_+-]{2,}")

#: Смещения, с которых пробуем читать: часть файлов имеет нечётную длину и
#: внутренний сдвиг на байт, поэтому «в лоб» от нуля даёт меньше пар.
_OFFSETS = (0, 1)

#: Имена файлов библиотек в описании профиля (`bin/profiles/<профиль>/base.xml`).
_LIBRARY_FILE_RE = re.compile(r"[A-Za-z0-9_]+\.(?:csl|xcsl)")


@dataclass(frozen=True)
class LibraryRecord:
    """Запись палитры блоков.

    Args:
        name: имя записи так, как его принимает `CreateBlock`
            («Конечные автоматы - Состояние автомата»).
        paramset: путь к файлу набора параметров относительно `ParamSet_mvtu`
            (`kon_avt\\kon_avt_sostoyanie_avtomata.ps`) или пустая строка,
            если набора у записи нет.
    """

    name: str
    paramset: str = ""

    @property
    def paramset_path(self) -> Optional[Path]:
        """Путь к набору параметров в нотации текущей ОС, если он есть."""
        if not self.paramset:
            return None
        return Path(self.paramset.replace("\\", "/"))


@dataclass(frozen=True)
class BlockLibrary:
    """Одна библиотека блоков (`bin/*.csl` или `bin/*.xcsl`)."""

    path: Path
    records: Tuple[LibraryRecord, ...]

    @property
    def name(self) -> str:
        return self.path.name


def _strings(data: bytes, offset: int) -> List[str]:
    """Печатаемые строки файла, прочитанного как UTF-16LE со сдвигом."""
    return _STRING_RE.findall(data[offset:].decode("utf-16-le", "replace"))


def _pairs(strings: Sequence[str]) -> List[Tuple[str, str]]:
    """Пары «имя записи → путь к `.ps`» из хвоста индекса.

    Пара — это строка, за которой идёт строка, оканчивающаяся на `.ps`.
    Путь сам на `.ps` не оканчивается (иначе это была бы пара путей).
    """
    return [(strings[i], strings[i + 1]) for i in range(len(strings) - 1)
            if strings[i + 1].lower().endswith(".ps")
            and not strings[i].lower().endswith(".ps")]


def parse_csl_index(data: bytes) -> List[LibraryRecord]:
    """Записи библиотеки с их наборами параметров — по содержимому `.csl`.

    Читается со двух смещений, берётся вариант с большим числом пар: файлы
    поставки попадаются как с чётной длиной, так и со сдвигом на байт.
    Повторяющиеся пары схлопываются — в индексе одна запись может быть
    объявлена дважды (например, под двумя именами палитры).
    """
    best: List[Tuple[str, str]] = []
    for offset in _OFFSETS:
        found = _pairs(_strings(data, offset))
        if len(found) > len(best):
            best = found

    records: List[LibraryRecord] = []
    seen = set()
    for name, paramset in best:
        if (name, paramset) in seen:
            continue
        seen.add((name, paramset))
        records.append(LibraryRecord(name=name, paramset=paramset))
    return records


def load_library(path: Path) -> BlockLibrary:
    """Прочитать одну библиотеку блоков."""
    return BlockLibrary(path=path, records=tuple(parse_csl_index(path.read_bytes())))


def iter_library_files(root: Path) -> Iterator[Path]:
    """Файлы библиотек в каталоге `bin/` — и `.csl`, и `.xcsl`."""
    for pattern in ("*.csl", "*.xcsl"):
        yield from sorted(root.glob(pattern))


def load_libraries(root: Path) -> List[BlockLibrary]:
    """Все библиотеки блоков каталога `bin/`."""
    return [load_library(p) for p in iter_library_files(root)]


def resolve_paramset(paramset_dir: Path, record: LibraryRecord) -> Optional[Path]:
    """Файл набора параметров записи, если он есть и лежит внутри каталога.

    Путь приходит из бинарного файла поставки, и в нём встречается выход
    вверх (`..\\..\\..\\HomeGit\\...`): такой путь указывает на сборочное дерево
    разработчика и наружу выпускать не должен. Поэтому результат проверяется
    на принадлежность каталогу наборов, а не просто склеивается.
    """
    rel = record.paramset_path
    if rel is None:
        return None
    root = paramset_dir.resolve()
    candidate = (paramset_dir / rel).resolve()
    if root != candidate and root not in candidate.parents:
        return None
    return candidate if candidate.is_file() else None


def libraries_in_profile(profile_xml: Path) -> List[str]:
    """Имена библиотек, которые загружает профиль, — в нижнем регистре.

    Профиль (`bin/profiles/<имя>/base.xml`) решает, какие библиотеки вообще
    доступны: файл на диске ещё не значит загруженную библиотеку. На поставке
    SimInTech64 шесть `.csl` лежат, но профилем не подхвачены (`AC.csl`,
    `LIB_FC.csl`, `PHS_LPM.csl`, `SPT.csl`, `visionLib.csl`,
    `MatchPortsPlugin.xcsl`) — записи из них создать нельзя, и в справочник
    они попадать не должны.
    """
    text = profile_xml.read_text(encoding="utf-8", errors="replace")
    return sorted({name.lower() for name in _LIBRARY_FILE_RE.findall(text)})


def class_names(bin_dir: Path,
                libraries: Optional[Iterable[str]] = None) -> List[str]:
    """Имена записей блоков, уникальные и в порядке появления.

    Args:
        bin_dir: каталог поставки с `.csl`.
        libraries: имена файлов библиотек (в нижнем регистре); None — все,
            что есть на диске. Обычно список берут из `libraries_in_profile`.
    """
    allowed = None if libraries is None else {name.lower() for name in libraries}
    names: List[str] = []
    seen = set()
    for library in load_libraries(bin_dir):
        if allowed is not None and library.name.lower() not in allowed:
            continue
        for record in library.records:
            if record.name not in seen:
                seen.add(record.name)
                names.append(record.name)
    return names


def missing_paramsets(paramset_dir: Path,
                      libraries: Iterable[BlockLibrary]) -> List[LibraryRecord]:
    """Записи, у которых набор параметров объявлен, но файла нет.

    Такие расхождения есть в самой поставке, поэтому это не ошибка разбора,
    а сведения о дистрибутиве.
    """
    return [rec for lib in libraries for rec in lib.records
            if rec.paramset and resolve_paramset(paramset_dir, rec) is None]
