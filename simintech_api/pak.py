"""Пакет проектов SimInTech (`.pak`): состав — без COM.

`.pak` — плоский INI-файл (Delphi TIniFile): его пишет сама среда. Здесь
разбирается **только состав пакета** — какие проекты в него входят и в каком
порядке они запускаются. Сами проекты (`.prt`) — zlib-сжатые бинарники, и этот
модуль их не открывает: чтобы получить содержимое, проект надо открыть через
COM (`COMClient.open_project`) или выгрузить в `.xprt`.

Формат разобран по байтам поставки (`Demo/**/*.pak` в SimInTech64), а не по
документации; всё, что ниже, — результат переписи 63 файлов. Смысл ключей взят
из структуры ``TPackStruct`` (`source/RootDelphi/InterfaceUnit.pas`): её поля
называются теми же словами, что и ключи INI, а методы — в ``bin/mmain.ridl``.
Неподтверждённое помечено прямо в тексте.

Секции — ровно пять, и все пять есть во всех 63 файлах поставки:

* ``[Files]`` — состав: ``Count=N``, затем ``0=``, ``1=``, … — пути к ``.prt``.
  **Порядок строк — порядок запуска.** В поставке 169 записей, и все до одной
  указывают на ``.prt``; ``.xprt`` не встречается ни разу, хотя в
  ``automation/file-formats.md`` пример приведён именно с ним. Соответствует
  ``fPackProjectList``.
* ``[Common]`` — ``Synchronize``, ``RelativePath``, ``IsRealTime``, ``TimeMash``,
  ``fSimpleSignalLoad``, ``formstyle``, ``restartname``,
  ``notqueryremoveforall``. Из них в поля разобраны пять; смысл остальных
  известен, но к составу пакета они не относятся:

  * ``Synchronize`` = ``fSyncSignal`` — «синхронизировать **списки сигналов**
    проектов», то есть объединение баз сигналов, а не модельное время.
  * ``RelativePath`` = ``fRelative`` — «сохранять относительные пути к файлам
    проектов». Это **режим записи**, а не свойство содержимого, и именно
    поэтому при ``RelativePath=1`` абсолютные записи в ``[Files]`` всё равно
    встречаются.
  * ``IsRealTime`` = флаг синхронизации с реальным временем для пакета
    (``SetRealTimeDelayPack``), ``TimeMash`` = коэффициент ускорения реального
    времени (``aRTDelayScale`` того же метода) — тип **double**, в
    ``InterfaceUnit.pas`` объявлено ``GetTimeMash: function:double``.
  * ``restartname`` = ``fRestartName`` — «базовое имя рестарта» (ср.
    ``PackSaveRestart``/``PackLoadRestart``).
  * ``notqueryremoveforall`` = ``fNotQueryRemoveForAllProjects`` — «удалять
    любые (а не только динамически загруженные) проекты из пакета без
    вопросов».
  * ``fSimpleSignalLoad`` — способ загрузки списка сигналов: 0 — полное
    объединение, 1 — объединение по первому проекту, 2 — не объединять
    (значение 1 в поставке не встречается).
  * ``formstyle`` и ``WindowState`` сопоставлены с ``TFormStyle`` и
    ``TWindowState`` **гипотетически**: структуры, которая это подтверждала бы,
    не найдено.
* ``[Active]`` и ``[TimeSync]`` — по строке на проект (``0=``, ``1=``, …). Это
  разные настройки: ``[Active]`` — ``aActive`` проекта в пакете
  (``AddProject``), ``[TimeSync]`` — его пер-проектный флаг синхронизации с
  реальным временем (``SetProjectRealTimeDelay``, ``aDelayFlag``). Поэтому они
  **независимы**: в ``KBA_CTL - генерация кода для АЭС/kba.pak`` все шесть
  проектов ``Active=1``, но у трёх из них ``TimeSync=0``.
* ``[Form]`` — геометрия окна (``Rect.*``, ``ConsoleHeight``, ``WindowState``,
  ``ColCount`` — число колонок списка проектов, ``ColWidth0``…``ColWidth6`` —
  их ширины). К составу пакета отношения не имеет и не разбирается.

Ловушки, из-за которых формат читают неверно:

* **Кодировка не одна.** 62 файла из 63 — UTF-8 **с BOM** (``EF BB BF``), и
  ровно один — CP1251 **без** BOM: ``Интеграция со сторонним ПО/Теплогидравлика
  TPP/KBA - промконтур охлаждения ядерного реактора/kba_with_safety.pak``
  (начинается с ``5B 46 6F``, то есть сразу с ``[Fo``). «BOM есть всегда» и
  «BOM нет никогда» — обе формулы неверны; :func:`decode_pack` пробует UTF-8 и
  откатывается на CP1251.
* **``TimeMash`` — не флаг, а double.** В поставке встречаются ``1``, ``2``,
  ``5``, ``20``, ``100``, ``0.003``, ``0.005``, и 26 значений из 63 не равны
  единице. Это коэффициент ускорения реального времени (``aRTDelayScale`` у
  ``SetRealTimeDelayPack``), так что чтение «0/1» потеряло бы их молча.
* **``Count`` — объявление, а не истина.** Число строк ``i=`` может с ним не
  сойтись, и тогда верны обе цифры по-своему. Поэтому :class:`ProjectPack`
  хранит обе (``count`` и ``project_count``), а расхождение называет
  :attr:`ProjectPack.problems` — молча взять одну из двух значило бы отдать
  клиенту неверный состав.
* **``ColCount`` в ``.pak`` и ``$ColCount`` в ``.tbl`` — разные вещи.** Здесь
  это ширина колонок окна среды, в ``.tbl`` — число столбцов матрицы.
  К составу пакета не относится ни то, ни другое.
* **Путь из файла недоверенный.** Пакет можно скачать, а ``..`` в записи
  ``[Files]`` увёл бы разбор за каталог пакета. Правила ровно те же, что у
  :func:`simintech_api.csl_library.resolve_paramset`: путь раскрывается и
  проверяется на принадлежность каталогу, а непрошедший не выдаётся вовсе.
* **Отсутствие ключа — не ошибка.** В поставке есть файл без
  ``notqueryremoveforall`` и без ``WindowState``/``ConsoleHeight``/``ColCount``
  (тот же CP1251: в нём ``[Form]`` — только ``Rect.*``). Разбор обязан
  переживать такие файлы: усечённый файл — не то же самое, что испорченный.
* **Перевод строки тоже не один.** У 39 файлов из 63 строки кончаются ``CRLF``,
  у 24 — только ``LF``; смешанных нет. Разбор от этого не зависит
  (``str.splitlines``), но проверка на это есть.

Отсутствие секции ``[Files]`` — **не отказ**: пакет разбирается в пустой состав,
а ``problems`` объясняет, что данных нет. Отказ был бы непоследователен: то же
расхождение ``Count`` с числом строк здесь сообщается, а не выбрасывается
исключением. Отказ оставлен ровно для одного случая — файла, в котором нет ни
одной из пяти секций: это не «пакет без проектов», а не пакет (обрезанный,
пустой или чужой файл), и тихо вернуть по нему пустой состав значило бы
выдать провал разбора за пустую модель.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .exceptions import PackError

#: Порядок секций, который пишет среда. Файл без единой из них — не пакет.
KNOWN_SECTIONS: Tuple[str, ...] = (
    "Form", "Common", "Files", "Active", "TimeSync",
)

#: BOM UTF-8. Его нет только у CP1251-файла из поставки — искать BOM
#: обязательно, иначе первый ключ ``[Form]`` склеится с маркером.
_BOM = b"\xef\xbb\xbf"

#: Абсолютный путь, как его пишет Windows: ``E:\...``, ``E:/...``, ``\...`` или
#: ``/...``. Проверяется по записи, а не через ``Path.is_absolute()``: разбор
#: идёт и на Linux, где ``D:\project\x.prt`` абсолютным не считается, и запись
#: молча превратилась бы в относительную.
_ABSOLUTE_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|[\\/])")


def decode_pack(data: bytes) -> str:
    """Текст `.pak` из байтов: UTF-8 (с BOM или без), иначе CP1251.

    Одной кодировки у формата нет. В поставке 62 файла из 63 — UTF-8 с BOM,
    а ``kba_with_safety.pak`` — CP1251 без BOM. Поэтому UTF-8 пробуется первым
    (он строгий: сбой на любом байте означает «это не UTF-8»), а CP1251 —
    откат, в котором недопустимые байты замещаются: уцелеть важнее, чем
    отказать на одном испорченном символе. Файл, который после этого не
    распознаётся как пакет, отвергается в :func:`parse_pack`.
    """
    if data.startswith(_BOM):
        data = data[len(_BOM):]
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1251", "replace")


def _split_sections(text: str) -> Tuple[Dict[str, List[str]], List[str]]:
    """Секции файла и строки вне секций.

    Значения собираются построчно, а не в словарь: в ``[Files]`` повтор номера
    (``0=`` дважды) меняет состав, и потерять его при разборе нельзя.
    """
    sections: Dict[str, List[str]] = {}
    orphan: List[str] = []
    current: Optional[str] = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].strip()
            sections.setdefault(current, [])
            continue
        if current is None:
            orphan.append(line)
            continue
        sections[current].append(line)
    return sections, orphan


def _pairs(lines: Sequence[str]) -> List[Tuple[str, str]]:
    """Пары «ключ=значение» строк секции.

    Делится по **первому** ``=``: путь вида ``E:\\a=b\\c.prt`` встречается, и
    ``split("=")`` потерял бы хвост пути молча.
    """
    out: List[Tuple[str, str]] = []
    for line in lines:
        key, sep, value = line.partition("=")
        if sep:
            out.append((key.strip(), value.strip()))
    return out


def _last(pairs: Sequence[Tuple[str, str]], key: str) -> Optional[str]:
    """Последнее значение ключа; `None`, если ключа нет.

    Именно последнее: в INI-файле поздняя строка перекрывает раннюю.
    """
    found: Optional[str] = None
    for name, value in pairs:
        if name == key:
            found = value
    return found


def _as_bool(value: Optional[str]) -> Optional[bool]:
    """Флаг SimInTech: ``1`` — включено, ``0`` — выключено, иное — неизвестно.

    Третье состояние (`None`) здесь не формальность: молча прочитать
    ``Synchronize=on`` как «включено» значило бы выдать догадку за данные.
    """
    if value is None:
        return None
    if value == "1":
        return True
    if value == "0":
        return False
    return None


def _as_float(value: Optional[str]) -> Optional[float]:
    """`TimeMash` как число; нечисловое значение — `None`.

    Разделитель — точка: в поставке только она (``0.003``). Десятичная запятая
    не поддержана — проверять её не на чем.
    """
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _as_index(key: str) -> Optional[int]:
    """Номер записи из ключа ``0=``/``1=``/…; нечисловой ключ — `None`.

    Не ``str.isdigit()``: он истинен и для ``²``, на котором ``int()`` падает.
    """
    try:
        return int(key)
    except ValueError:
        return None


def _is_absolute(recorded: str) -> bool:
    """Записан ли путь абсолютным (``E:\\...``, ``\\\\сервер\\...``, ``/...``)."""
    return bool(_ABSOLUTE_RE.match(recorded))


def _resolve_in(base: Path, project: PackProject) -> Optional[Path]:
    """Путь проекта внутри каталога пакета; `None`, если его там нет.

    Разворачиваются только относительные записи: ``Схемы\\701.prt`` →
    ``<каталог пакета>/Схемы/701.prt``. Абсолютной записи разворачивать нечего
    — она указывает туда, где лежит (например, ``D:\\project\\...`` в поставке),
    и «приведение» её к каталогу пакета дало бы путь, которого нет.

    Путь приходит из файла, который мог быть скачан, поэтому результат
    проверяется на принадлежность каталогу — как в
    :func:`simintech_api.csl_library.resolve_paramset`. В поставке выходов
    вверх нет; правило существует для чужих файлов.
    """
    if project.absolute or not project.path:
        return None
    root = base.resolve()
    candidate = (base / project.path.replace("\\", "/")).resolve()
    if candidate != root and root not in candidate.parents:
        return None
    return candidate


@dataclass(frozen=True)
class PackProject:
    """Проект в составе пакета.

    Args:
        index: номер, которым запись помечена в ``[Files]`` (``0=``, ``1=``, …).
            Обычно совпадает с позицией, но при дырах и повторах нумерации —
            нет. Порядок запуска задаёт позиция в ``ProjectPack.projects``.
        path: путь так, как он записан в файле (``Схемы\\701.prt`` или
            ``D:\\project\\...\\tim_init.prt``).
        absolute: путь записан абсолютным (см. :func:`_is_absolute`).
        active: флаг ``[Active]`` — ``aActive`` проекта в пакете
            (``AddProject``); `None` — строки для этого номера нет, и что
            среда подставит вместо неё, не проверено.
        time_sync: флаг ``[TimeSync]`` — пер-проектная синхронизация с
            реальным временем (``SetProjectRealTimeDelay``, ``aDelayFlag``);
            `None` — строки нет. От ``active`` не зависит.
    """

    index: int
    path: str
    absolute: bool = False
    active: Optional[bool] = None
    time_sync: Optional[bool] = None

    @property
    def name(self) -> str:
        """Имя файла проекта без каталога (``701.prt``)."""
        return self.path.replace("\\", "/").rsplit("/", 1)[-1]


@dataclass(frozen=True)
class ProjectPack:
    """Разобранный пакет проектов.

    Args:
        path: путь к самому ``.pak`` — он же каталог, относительно которого
            раскрываются относительные записи.
        projects: проекты **в порядке запуска** (то есть в порядке строк
            ``[Files]``), а не в порядке номеров.
        count: объявленный ``Count=N``; `None` — ключа нет или он не число.
            Не путать с :attr:`project_count` — фактическим числом записей.
        relative_path: ``RelativePath`` = ``fRelative`` — «сохранять
            относительные пути к файлам проектов», то есть режим **записи**, а
            не свойство содержимого: при ``RelativePath=1`` абсолютные записи
            в ``[Files]`` всё равно встречаются.
        synchronize: ``Synchronize`` = ``fSyncSignal`` — «синхронизировать
            списки сигналов проектов» (объединение баз сигналов, не модельное
            время).
        real_time: ``IsRealTime`` — синхронизация с реальным временем для
            пакета (``SetRealTimeDelayPack``, ``aRTDelayFlag``).
        time_mash: ``TimeMash`` — коэффициент ускорения реального времени
            (``aRTDelayScale``), double; `None` — ключа нет или значение не
            число.
        restart_name: ``restartname``; пустая строка — рестарта нет.
        has_files_section: была ли секция ``[Files]``. Отсутствие — не отказ,
            но и не «пустой пакет»: об этом говорит :attr:`problems`.
        problems: расхождения, найденные при разборе, — текстом, по одному на
            строку. Пустой кортеж означает «файл без отклонений»; в поставке
            так у всех файлов, кроме одного (см. тесты).

    Неразобранные ключи ``[Common]`` (``fSimpleSignalLoad``, ``formstyle``,
    ``notqueryremoveforall``) наружу не отдаются: состав пакета они не
    описывают — это объединение баз сигналов, вопросы при удалении проекта и
    стиль формы. ``[Form]`` не разбирается вовсе — это геометрия окна.
    """

    path: Path
    projects: Tuple[PackProject, ...] = ()
    count: Optional[int] = None
    relative_path: Optional[bool] = None
    synchronize: Optional[bool] = None
    real_time: Optional[bool] = None
    time_mash: Optional[float] = None
    restart_name: str = ""
    has_files_section: bool = False
    problems: Tuple[str, ...] = ()

    @property
    def project_count(self) -> int:
        """Сколько проектов в пакете фактически — число записей ``[Files]``.

        Объявленному ``Count`` доверять нельзя: он может расходиться с
        строками, и тогда верны обе цифры по-своему (см. :attr:`problems`).
        """
        return len(self.projects)

    def resolve(self, project: PackProject) -> Optional[Path]:
        """Полный путь проекта или `None`, если его нельзя построить.

        `None` — не «файла нет», а «путь не выводится внутри каталога пакета»:
        запись абсолютная (``D:\\project\\...``), пустая или уводит вверх за
        каталог. Существование файла здесь не проверяется — это работа с
        путём, а не с диском; в поставке 167 путей из 169 существуют, и ровно
        два недостающих — абсолютные.
        """
        return _resolve_in(self.path.parent, project)

    def resolved_paths(self) -> Tuple[Optional[Path], ...]:
        """Пути всех проектов, по порядку запуска; `None` — см. :meth:`resolve`."""
        return tuple(self.resolve(p) for p in self.projects)


def _section_problems(name: str, numbers: Sequence[int],
                      project_numbers: Sequence[int]) -> List[str]:
    """Расхождение номеров секции флагов с составом пакета.

    ``[Active]`` и ``[TimeSync]`` адресуются номерами проектов, поэтому лишняя
    строка или пропущенная — это либо флаг неизвестно у кого, либо неизвестный
    флаг у кого-то. И то и другое надо назвать, а не додумать.
    """
    out: List[str] = []
    present = set(project_numbers)
    seen = set(numbers)
    missing = sorted(present - seen)
    extra = sorted(seen - present)
    if missing:
        out.append(f"[{name}]: нет строк для номеров проектов "
                   f"{', '.join(str(n) for n in missing)}")
    if extra:
        out.append(f"[{name}]: лишние строки для номеров "
                   f"{', '.join(str(n) for n in extra)} — таких проектов нет")
    if len(numbers) != len(seen):
        out.append(f"[{name}]: повторяющиеся номера строк")
    return out


def _collect_problems(base: Path, sections: Dict[str, List[str]],
                      orphan: Sequence[str], projects: Sequence[PackProject],
                      count: Optional[int], count_raw: Optional[str],
                      relative_path: Optional[bool]) -> Tuple[str, ...]:
    """Всё, что в файле разошлось с ожидаемым, — текстом.

    Проверки идут от состава к частностям: если состав неизвестен, сообщать о
    нумерации флагов нечего.
    """
    out: List[str] = []

    unknown = sorted(set(sections) - set(KNOWN_SECTIONS))
    if unknown:
        out.append(f"неизвестные секции: {', '.join(unknown)} — их содержимое "
                   "не разобрано")
    if orphan:
        out.append(f"строк вне секций: {len(orphan)} — пропущены")

    has_files = "Files" in sections
    if not has_files:
        out.append("секция [Files] отсутствует — состав пакета неизвестен; "
                   "пустой projects здесь означает «данных нет», а не "
                   "«проектов нет»")
    else:
        if count_raw is None:
            out.append("в [Files] нет ключа Count= — объявленное число "
                       "проектов неизвестно")
        elif count is None:
            out.append(f"Count={count_raw} не число — объявленное число "
                       "проектов неизвестно")
        elif count != len(projects):
            out.append(f"Count={count} не совпадает с числом записей "
                       f"[Files] ({len(projects)}): состав читается по строкам "
                       "i=, объявленному Count доверять нельзя")

        numbers = [p.index for p in projects]
        if numbers != list(range(len(numbers))):
            out.append(f"номера записей [Files] не образуют 0.."
                       f"{len(numbers) - 1}: "
                       f"{', '.join(str(n) for n in numbers)} — при дырах и "
                       "повторах порядок запуска задаёт позиция строки")

        empty = [p.index for p in projects if not p.path]
        if empty:
            out.append("пустые пути в [Files] у номеров: "
                       f"{', '.join(str(n) for n in empty)}")

        for name in ("Active", "TimeSync"):
            out.extend(_section_problems(name, _numbers(sections.get(name, [])),
                                         numbers))

    absolute = [p for p in projects if p.absolute]
    if absolute:
        out.append("абсолютные пути (развернуть относительно каталога пакета "
                   "нельзя, resolve() для них None): "
                   + ", ".join(f"{p.index}={p.path}" for p in absolute))

    escaped = [p for p in projects if not p.absolute and p.path
               and _resolve_in(base, p) is None]
    if escaped:
        out.append("пути, выходящие за каталог пакета (не выданы): "
                   + ", ".join(f"{p.index}={p.path}" for p in escaped))

    if relative_path is not True:
        out.append("RelativePath не 1 (fRelative — «сохранять относительные "
                   "пути к файлам проектов»): файл сохранён с абсолютными "
                   "путями, относительных записей в нём быть не должно, и "
                   "раскрытие их от каталога пакета здесь не проверено")
    return tuple(out)


def _numbers(lines: Sequence[str]) -> List[int]:
    """Номера строк секции (``0=``, ``1=``, …) в порядке появления."""
    out: List[int] = []
    for key, _ in _pairs(lines):
        number = _as_index(key)
        if number is not None:
            out.append(number)
    return out


def parse_pack(text: str, path: Path) -> ProjectPack:
    """Разобрать пакет из текста; `path` — путь к самому файлу.

    Raises:
        PackError: в тексте нет ни одной из пяти секций пакета. Это не «пакет
            без проектов», а не пакет: обрезанный, пустой или чужой файл.
            Отдельной ошибки на отсутствие ``[Files]`` нет намеренно — такой
            пакет разбирается в пустой состав, а причина видна в
            :attr:`ProjectPack.problems`.
    """
    sections, orphan = _split_sections(text)
    if not any(name in sections for name in KNOWN_SECTIONS):
        raise PackError(
            f"{path}: нет ни одной секции пакета "
            f"({', '.join(KNOWN_SECTIONS)}) — это не .pak "
            "(файл обрезан, пуст или принадлежит другому формату)")

    common = _pairs(sections.get("Common", []))
    files = _pairs(sections.get("Files", []))
    active = _pairs(sections.get("Active", []))
    time_sync = _pairs(sections.get("TimeSync", []))

    active_map: Dict[int, Optional[bool]] = {}
    for key, value in active:
        number = _as_index(key)
        if number is not None:
            active_map[number] = _as_bool(value)
    sync_map: Dict[int, Optional[bool]] = {}
    for key, value in time_sync:
        number = _as_index(key)
        if number is not None:
            sync_map[number] = _as_bool(value)

    projects: List[PackProject] = []
    for key, value in files:
        number = _as_index(key)
        if number is None:
            continue
        projects.append(PackProject(
            index=number,
            path=value,
            absolute=_is_absolute(value),
            active=active_map.get(number),
            time_sync=sync_map.get(number),
        ))

    count_raw = _last(files, "Count")
    count: Optional[int] = None
    if count_raw is not None:
        try:
            count = int(count_raw)
        except ValueError:
            count = None

    relative_path = _as_bool(_last(common, "RelativePath"))

    return ProjectPack(
        path=path,
        projects=tuple(projects),
        count=count,
        relative_path=relative_path,
        synchronize=_as_bool(_last(common, "Synchronize")),
        real_time=_as_bool(_last(common, "IsRealTime")),
        time_mash=_as_float(_last(common, "TimeMash")),
        restart_name=_last(common, "restartname") or "",
        has_files_section="Files" in sections,
        problems=_collect_problems(path.parent, sections, orphan, projects,
                                   count, count_raw, relative_path),
    )


def load_pack(path: Path) -> ProjectPack:
    """Прочитать пакет проектов из файла (без COM)."""
    return parse_pack(decode_pack(path.read_bytes()), path)


def load_packs(root: Path) -> List[ProjectPack]:
    """Все пакеты каталога — рекурсивно, по порядку имён.

    Обход нужен для сплошной проверки поставки: ``Demo`` — дерево каталогов, и
    пакеты лежат вперемешку с проектами и библиотеками.
    """
    return [load_pack(p) for p in sorted(root.rglob("*.pak"))]
