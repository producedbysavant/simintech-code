"""Таблицы SimInTech (`.tbl`): разбор файлов без COM.

`.tbl` — текстовый файл, в котором лежит одна или несколько таблиц. Таблица
состоит из `$`-директив и следующей за ними числовой матрицы; таблицы
разделены строкой из решёток (`#`). Разбор здесь — чистый Python: COM не
нужен, на Linux работает так же, как на Windows.

Структура одной таблицы::

    $GlobalScript=…     ×N    глобальный скрипт (идёт до $Caption)
    $Caption=…                подпись таблицы
    $TabType=…                0 — функция одного аргумента, 1 — двух
    $GraphType=…              тип графика (смысл не проверен)
    $ColCount=…               объявленное число столбцов
    $RowCount=…               объявленное число строк
    $MatrixName=…             имя матрицы; директива необязательна
    $Script=…           ×N    скрипт таблицы; значение — остаток строки
    <пустая строка>
    <матрица>

Матрица `$TabType=0` — `RowCount` строк по `ColCount` чисел. Матрица
`$TabType=1` — сперва строка оси столбцов (пустая первая ячейка и `ColCount`
чисел), затем `RowCount` строк вида «метка строки + `ColCount` чисел».

Строковых подписей у осей не бывает: подписи только числовые, а текст живёт
в `$Caption` и в комментариях `$Script=//…`.

**Размеры берутся из данных, а не из директив.** `$ColCount`/`$RowCount`
пишет только редактор: в `mmain.exe` (проверено переписью строк бинарника,
UTF-16LE) есть ровно `$Caption=` и `$TabType=`, а `$ColCount=`, `$RowCount=`,
`$Script=`, `$GlobalScript=`, `$MatrixName=`, `$GraphType=` встречаются лишь в
`MiniExcel.exe`. При расчёте среда восстанавливает матрицу по фактическим
строкам (`TTable1/TTable2.FromString` в `tbls.pas`: число строк — по числу
строк текста, число столбцов — по числу чисел в первой строке), поэтому
директивы — это *то, что объявлено*, и расхождение с данными возможно. В
поставке такое есть: `HS/ENGINES/COMPRESSORS/Rotrex_с_высотностью.tbl`
объявляет `$ColCount=1`, а матрица у него 2×2 — таблицу разбираем по данным, а
расхождение возвращаем в `Table.warnings`, потому что молчаливая подмена
одного размера другим — это ровно тот случай, когда читатель врёт.

**`$TabType` вне {0, 1} — отказ.** В `tbls.pas` тип таблицы — элемент
перечисления `TTableTypes = (tbtNoType, tbtFunOfOneArg, tbtFunOfTwoArg,
tbtFunOfNArg, tbtIsoLines)`, и в коде стоит `TTableTypes(BufTableType + 1)`,
то есть значение в файле на единицу меньше номера элемента: 0 — функция одного
аргумента, 1 — двух. Средства создания есть только для этих двух, поэтому 2 и
3 (N-мерная таблица и изолинии) отвергаются: разбирать их как матрицу значило
бы выдумать формат.

**`$Caption` и `$TabType` обязательны.** Без подписи `TCustomTable.LoadMetaInfo`
ставит `TableErr_FileFormatNotSupported`, а `TTabPack.LoadMetaInfo` вообще не
заводит таблицу; без `$TabType` пак не создать (`TableErr_CantCreateTablesByMeta`).
В поставке эти три директивы (`$Caption`, `$TabType`, `$GraphType`) есть у всех
964 таблиц — ни одной без них нет.

Кодировка — по BOM с откатом на ANSI (`LoadTextStreamWithEncoding`), отсюда
смешанность поставки: 171 файл UTF-8 с BOM, 305 CP1251 без BOM, 23 чистый
ASCII/UTF-8 без BOM. Читается UTF-8 с BOM, иначе UTF-8, иначе CP1251; UTF-16
не поддерживается (в поставке нет — **не проверено**).

Числа — в обычной записи с точкой и любым регистром экспоненты
(`-5.507e-4`, `2.53490000000000E+0005`). **Десятичной запятой быть не может**:
перед разбором среда заменяет `,`, `;`, `|`, TAB на пробелы, поэтому `1,5`
распалось бы на два числа — здесь такое отвергается как нечисловая ячейка.
Нечисловая ячейка не превращается в 0.0 молча: разбор отказывает с номером
строки файла и номером столбца (`TableFormatError`), потому что 0.0 в таблице
свойств — это правдоподобное значение, и подмена неотличима от настоящего нуля.

Разделитель таблиц — строка, первый символ которой `#` (`TTabPack.FromString`;
константа `TABLE_SEP` — 37 решёток, в файлах встречается и 40, поэтому длина
не важна). В поставке есть один повреждённый файл
(`K1000/TURBINA/st1_3.tbl`), где к строкам данных прилипли хвосты: решётки
разделителя (`…3.00000E-01####…`) и директивы следующей таблицы
(`…6.00000E-01$Caption=Момент`). Такие хвосты срезаются — среда их не
замечает (читает из строки ровно `ColCount + 1` чисел), а здесь они стали бы
«нечисловыми ячейками». За пределами этого файла строк данных с `#` или `$`
в поставке нет, поэтому срезание ничего не прячет.

`.tbl` бывает **не таблицей**, и это не ошибка разбора, а свойство файла: 22
файла без единой `$`-директивы — голые матрицы старой формы (`Насосы РАСНАР/`),
один — файл языка SimInTech (`Материалы_РАСНАР/ПТ7М.tbl`: `//комментарий`,
`const CM=0.5,…;`), один — восемь голых матриц
(`K1000/GAS_TABLES/Воздух.tbl`). Возвращать для них «таблицу из 0 строк»
нельзя — это выглядело бы как пустая, но исправная таблица, поэтому
`load_tables` отказывает (`NotATableError`) и говорит, чем файл оказался.

Отдельно отвергаются 4 бинарных `.tbl` (17…191 МБ,
`HS/COOLANTS/voda_lib/water_iapws_tables_PH1..4.tbl`): первые 8 байт — счётчик
(uint64 little-endian: 200, 200, 10000, 1000 — что он считает, **не проверено**),
дальше плоский массив IEEE-754 double (проверено: размер файла минус 8 делится
на 8 без остатка). Проверка на бинарность — по NUL в первых 8 КиБ: текстовые
`.tbl` поставки NUL не содержат, а читать 191 МБ ради отказа незачем.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Dict,
    Iterator,
    List,
    NoReturn,
    Optional,
    Sequence,
    Tuple,
    Union,
)

from .exceptions import SimInTechError

__all__ = [
    "NotATableError",
    "Table",
    "TableFormatError",
    "TblError",
    "load_tables",
    "parse_tables",
]

#: Директивы формата — ровно эти имена (`META_*` в `tbls.pas` плюс те, что
#: знает редактор таблиц). Имя сверяется целиком: `$Caption` и `$GlobalScript`
#: различаются, и по префиксу их путать нельзя.
DIRECTIVE_NAMES = (
    "Caption", "TabType", "GraphType", "ColCount", "RowCount", "MatrixName",
    "Script", "GlobalScript",
)

#: Типы таблиц, которые среда умеет создавать (`tbtFunOfOneArg`,
#: `tbtFunOfTwoArg`). Значение в файле — номер в перечислении минус один.
TABLE_TYPE_ONE_ARG = 0
TABLE_TYPE_TWO_ARG = 1

#: Сколько байт читается до чтения всего файла — этого хватает, чтобы отличить
#: бинарную таблицу от текстовой, не поднимая в память все 191 МБ.
_PREFIX_BYTES = 8192

#: Номер строки, в которой парсер видит директиву. `$` в начале строки —
#: комментарий и для среды (`MatrFromString` удаляет такие строки), поэтому
#: строка с `$`, не похожая на директиву, — повод сказать, а не молчать.
_DIRECTIVE_RE = re.compile(r"^\s*\$([A-Za-z][A-Za-z0-9_]*)\s*=(.*)$")

#: Число в том виде, в каком его пишет среда. `float()` сам по себе принимает
#: `nan`, `inf` и `1_0` — здесь такие записи отвергаются вместе с прочим
#: мусором, иначе в таблице появилось бы значение, которого в файле нет.
_NUMBER_RE = re.compile(r"^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$")

_BOMS = (b"\xff\xfe", b"\xfe\xff")

#: Признак файла языка SimInTech (`.tbl` бывает и им): объявления `const`/`var`
#: и тела процедур. Одних комментариев `//` мало — с них начинаются и голые
#: матрицы (`K1000/GAS_TABLES/Воздух.tbl`).
_LANGUAGE_RE = re.compile(
    r"^\s*(const|var|begin|end[.;]|procedure|function)\b", re.MULTILINE)

#: Директива, прилипшая к концу строки данных, — повреждение `st1_3.tbl`.
#: Ищем последнее вхождение: среда такой хвост не заметила бы (она читает
#: ровно `ColCount + 1` чисел строки), а здесь он стал бы «нечисловой ячейкой».
_GLUED_DIRECTIVE_RE = re.compile(r"\$[A-Za-z][A-Za-z0-9_]*=")

#: Директивы, значение которых — текст скрипта, а не скаляр.
_SCRIPT_NAMES = ("Script", "GlobalScript")


class TblError(SimInTechError):
    """Ошибка разбора файла таблиц (`.tbl`)."""


class NotATableError(TblError):
    """Файл `.tbl` не является таблицей этого формата.

    Так выглядят файл языка SimInTech, голая матрица старой формы (без
    `$`-директив) и бинарная таблица свойств.
    """


class TableFormatError(TblError):
    """Структура таблицы нарушена: нет обязательной директивы, нечисловая
    ячейка, не сходится число столбцов."""


@dataclass(frozen=True)
class Table:
    """Одна таблица файла.

    Args:
        caption: значение `$Caption`.
        table_type: `$TabType` (0 — функция одного аргумента, 1 — двух).
        col_count: объявленное `$ColCount`; `None` — директивы нет.
        row_count: объявленное `$RowCount`; `None` — директивы нет.
        rows: значения матрицы. Для `table_type=1` — только значения, метка
            строки лежит отдельно, в `row_labels`.
        row_labels: первые числа строк (ось строк) для `table_type=1`.
        col_labels: числа строки оси столбцов для `table_type=1`.
        matrix_name: значение `$MatrixName` или пустая строка.
        graph_type: значение `$GraphType` или `None`. Смысл значений не
            проверен: в файлах встречаются 0 и 1, что они значат для
            отрисовки — **не проверено**.
        scripts: значения `$Script` по одному на директиву, включая пустые
            (пустое значение — абзац скрипта). Так многострочный скрипт
            остаётся построчным, а не склеивается в одну строку: склеивание
            потеряло бы разбиение, которое среда пишет по строкам. Текст
            возвращается как записан, вместе с ведущими отступами.
        global_scripts: значения `$GlobalScript`, так же построчно.
        warnings: расхождения, о которых читатель обязан сказать, но из-за
            которых не отказывает: объявленный размер не совпал с данными,
            встретилась неизвестная `$`-директива.
    """

    caption: str
    table_type: int
    rows: Tuple[Tuple[float, ...], ...]
    col_count: Optional[int] = None
    row_count: Optional[int] = None
    row_labels: Tuple[float, ...] = ()
    col_labels: Tuple[float, ...] = ()
    matrix_name: str = ""
    graph_type: Optional[int] = None
    scripts: Tuple[str, ...] = ()
    global_scripts: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()


def load_tables(path: Union[str, Path]) -> List[Table]:
    """Прочитать все таблицы файла `.tbl`.

    Args:
        path: путь к файлу `.tbl`.

    Returns:
        Таблицы в порядке появления в файле. Пустым список быть не может:
        файл без единой `$`-директивы — это отказ, а не «ноль таблиц».

    Raises:
        NotATableError: файл бинарный, не читается или не содержит ни одной
            `$`-директивы (файл языка SimInTech, голая матрица старой формы).
        TableFormatError: таблица есть, но её структура нарушена.
    """
    file_path = Path(path)
    try:
        with file_path.open("rb") as handle:
            head = handle.read(_PREFIX_BYTES)
            if b"\x00" in head:
                raise NotATableError(_binary_reason(file_path))
            raw = head + handle.read()
    except OSError as exc:
        raise NotATableError(f"{file_path}: файл не читается: {exc}") from exc

    return parse_tables(_decode(raw, file_path), source=str(file_path))


def parse_tables(text: str, source: str = "<текст>") -> List[Table]:
    """Разобрать таблицы из готового текста `.tbl`.

    Отдельная точка входа нужна там, где текст уже прочитан (например, при
    разборе ответа или в тестах) — декодирование и проверка на бинарность
    остаются на `load_tables`.

    Args:
        text: содержимое файла `.tbl` как строка.
        source: имя источника для сообщений об ошибках.
    """
    tables: List[Table] = []
    for lines in _segments(text.splitlines()):
        table = _parse_table(lines, source)
        if table is not None:
            tables.append(table)
    if not tables:
        raise NotATableError(_not_a_table_reason(text, source))
    return tables


def _decode(raw: bytes, source: Path) -> str:
    """Текст файла: BOM — UTF-8, иначе UTF-8, иначе CP1251.

    Порядок — из `LoadTextStreamWithEncoding` («таблицы ансишные»): с BOM
    берётся UTF-8, без BOM — системная кодировка, то есть CP1251. UTF-16 не
    поддерживается: в поставке таких файлов нет — **не проверено**.
    """
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    if raw.startswith(_BOMS):
        raise NotATableError(
            f"{source}: UTF-16 в таблицах не поддерживается (в поставке таких "
            f"файлов нет — не проверено); BOM {raw[:2].hex()}")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode("cp1251")
    except UnicodeDecodeError as exc:
        raise NotATableError(
            f"{source}: не текстовая таблица — не UTF-8 и не CP1251: {exc}"
        ) from exc


def _binary_reason(path: Path) -> str:
    """Почему бинарный `.tbl` отвергается — с числами, а не общими словами."""
    size = path.stat().st_size
    tail = ""
    if (size - 8) % 8 == 0 and size > 8:
        tail = (f"; размер минус 8 байт делится на 8 — похоже на плоский "
                f"массив double ({(size - 8) // 8} значений)")
    return (f"{path}: бинарная таблица свойств ({size} байт) — это не текстовая "
            f"таблица, текстовые правила к ней неприменимы{tail}")


def _not_a_table_reason(text: str, source: str) -> str:
    """Чем файл оказался вместо таблицы.

    Разница существенная: «файл языка SimInTech» и «голая матрица без
    директив» — разные вещи, и лечится с ними по-разному.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    head = lines[0][:60] if lines else ""
    names = ", ".join("$" + name for name in DIRECTIVE_NAMES)
    if _LANGUAGE_RE.search(text):
        return (f"{source}: похоже на файл языка SimInTech, а не на таблицу: "
                f"нет ни одной директивы ({names}); первая строка: {head!r}")
    return (f"{source}: таблиц формата .tbl нет — ни одной $-директивы "
            f"({names}); первая строка: {head!r}; так выглядят голые матрицы "
            f"старой формы, которые среда читает другим классом")


def _segments(lines: Sequence[str]) -> Iterator[List[Tuple[int, str]]]:
    """Разбить файл на таблицы и пронумеровать строки.

    Разделитель — строка, начинающаяся с решётки (`TTabPack.FromString`);
    точная длина не важна, в поставке встречаются 37 и 40 решёток.
    """
    current: List[Tuple[int, str]] = []
    for number, line in enumerate(lines, start=1):
        if line.strip().startswith("#"):
            yield current
            current = []
            continue
        current.append((number, line))
    yield current


def _strip_glued_tail(line: str) -> str:
    """Срезать прилипший к строке данных хвост.

    Повреждение одно и локальное — `K1000/TURBINA/st1_3.tbl`, где директивы
    таблицы «Момент сопротивления» и решётки разделителя прилипли к строкам
    последней таблицы предыдущей (`…6.00000E-01$Caption=Момент`,
    `…3.00000E-01####…`). Среда такой хвост не замечает: она читает из строки
    ровно `ColCount + 1` чисел, — поэтому и здесь он не должен становиться
    «нечисловой ячейкой». За пределами этого файла строк данных с `#` или `$`
    в поставке нет, так что срезание не может спрятать настоящую ячейку.
    """
    stripped = line.rstrip()
    glued: Optional[re.Match[str]] = None
    for found in _GLUED_DIRECTIVE_RE.finditer(stripped):
        glued = found
    if glued is not None and glued.start() > 0:
        stripped = stripped[:glued.start()].rstrip()
    without_hashes = stripped.rstrip("#")
    if without_hashes:
        stripped = without_hashes.rstrip()
    return stripped


def _directives(lines: Sequence[Tuple[int, str]]) -> Dict[str, List[Tuple[int, str]]]:
    """Директивы таблицы: имя → значения с номерами строк, в порядке появления.

    Повторяемые `$Script` и `$GlobalScript` сохраняются целиком; остальные
    имена берутся по первому вхождению — так же, как `ReturnMetaStr` и
    `LoadMetaInfo` в `tbls.pas`, которые останавливаются на первом значении.

    Значение скрипта возвращается как есть, а скалярные значения обрезаются по
    краям. Это не мелочь: в поставке 1381 значение начинается с пробела, и все
    они — `$Script=  begin` и `$GlobalScript= var i:Integer;`, где отступ
    значим. Обрезать его значило бы испортить текст скрипта; для `$Caption` и
    размеров такое обрезание, наоборот, безопасно — пробелов там нет.
    """
    found: Dict[str, List[Tuple[int, str]]] = {}
    for number, line in lines:
        match = _DIRECTIVE_RE.match(line)
        if match is None:
            continue
        name = match.group(1)
        value = match.group(2)
        if name not in _SCRIPT_NAMES:
            value = value.strip()
        found.setdefault(name, []).append((number, value))
    return found


def _data_lines(lines: Sequence[Tuple[int, str]]) -> List[Tuple[int, str]]:
    """Строки матрицы: всё, что не пусто и не комментарий.

    Комментарием среда считает строку, начинающуюся с `/`, `\\`, `{`, `*` или
    `$` (`MatrFromString`); сюда же попадают и директивы. Хвост, прилипший к
    строке данных, срезается здесь — у директив `#` в значении встречается
    (`$Script=//#### ЛИНЕЙНАЯ ХАРАКТЕРИСТИКА ####`), и трогать их нельзя.
    """
    return [(number, _strip_glued_tail(line)) for number, line in lines
            if line.strip() and line.strip()[0] not in "\\/{*$"]


def _parse_table(lines: Sequence[Tuple[int, str]], source: str) -> Optional[Table]:
    """Таблица из сегмента файла; `None` — сегмент не таблица.

    `None` возвращается для сегмента без единой директивы: перед первой
    таблицей и после последней разделитель не ставится, поэтому пустые
    сегменты — норма, а не ошибка. Отсутствие директив во **всём** файле
    разбирает `parse_tables`: там это отказ.
    """
    directives = _directives(lines)
    if not directives:
        return None

    warnings: List[str] = []
    for name, values in directives.items():
        if name not in DIRECTIVE_NAMES:
            warnings.append(
                f"строка {values[0][0]}: неизвестная директива ${name} — "
                f"пропущена")

    caption = _required(directives, "Caption", source)
    table_type = _table_type(directives, source)
    matrix_name = _first(directives, "MatrixName")

    rows, row_labels, col_labels = _matrix(
        _data_lines(lines), table_type, source)
    col_count = _declared(directives, "ColCount", source)
    row_count = _declared(directives, "RowCount", source)

    actual_cols = len(col_labels) if table_type == TABLE_TYPE_TWO_ARG else (
        len(rows[0]) if rows else 0)
    if col_count is not None and col_count != actual_cols:
        warnings.append(
            f"$ColCount={col_count}, а столбцов в матрице {actual_cols} — "
            f"размер взят из данных")
    if row_count is not None and row_count != len(rows):
        warnings.append(
            f"$RowCount={row_count}, а строк в матрице {len(rows)} — "
            f"размер взят из данных")

    return Table(
        caption=caption,
        table_type=table_type,
        rows=tuple(rows),
        col_count=col_count,
        row_count=row_count,
        row_labels=tuple(row_labels),
        col_labels=tuple(col_labels),
        matrix_name=matrix_name,
        graph_type=_declared(directives, "GraphType", source),
        scripts=tuple(value for _, value in directives.get("Script", [])),
        global_scripts=tuple(
            value for _, value in directives.get("GlobalScript", [])),
        warnings=tuple(warnings),
    )


def _first(directives: Dict[str, List[Tuple[int, str]]], name: str) -> str:
    """Первое значение директивы или пустая строка."""
    values = directives.get(name)
    return values[0][1] if values else ""


def _required(directives: Dict[str, List[Tuple[int, str]]], name: str,
              source: str) -> str:
    """Значение обязательной директивы.

    `$Caption` обязательна не по прихоти читателя: без неё среда ставит
    `TableErr_FileFormatNotSupported` (одиночная таблица) или вовсе не заводит
    таблицу (пак).
    """
    if name not in directives:
        return _fail(source, f"нет ${name}=: без неё среда таблицу не создаёт")
    return directives[name][0][1]


def _declared(directives: Dict[str, List[Tuple[int, str]]], name: str,
              source: str) -> Optional[int]:
    """Целое из директивы; `None` — директивы нет.

    Нечисловое значение — отказ, а не `None`: `None` здесь значит «директивы
    нет», и смешивать эти случаи нельзя, иначе испорченная директива выглядела
    бы как её отсутствие.
    """
    if name not in directives:
        return None
    number, value = directives[name][0]
    try:
        return int(value)
    except ValueError:
        return _fail(source, f"строка {number}: ${name}={value!r} — не целое")


def _table_type(directives: Dict[str, List[Tuple[int, str]]], source: str) -> int:
    """`$TabType` с проверкой: средство создания есть только для 0 и 1."""
    if "TabType" not in directives:
        return _fail(
            source, "$TabType= отсутствует: тип таблицы неизвестен, а пак без "
                    "него среда не создаёт")
    number, value = directives["TabType"][0]
    allowed = (TABLE_TYPE_ONE_ARG, TABLE_TYPE_TWO_ARG)
    try:
        table_type = int(value)
    except ValueError:
        return _fail(source, f"строка {number}: $TabType={value!r} — не целое")
    if table_type not in allowed:
        return _fail(source, (
            f"строка {number}: $TabType={table_type} — тип не поддержан: "
            f"таблицы создаются только для 0 (функция одного аргумента) и "
            f"1 (функция двух аргументов); 2 и 3 (N-мерная, изолинии) среда "
            f"создать не может, и разбирать их как матрицу нельзя"))
    return table_type


def _matrix(data: Sequence[Tuple[int, str]], table_type: int, source: str
            ) -> Tuple[List[Tuple[float, ...]], List[float], List[float]]:
    """Матрица сегмента: строки, метки строк, ось столбцов.

    Для `table_type=1` первая строка — ось столбцов, дальше «метка + значения»:
    так же читает `TTable2.FromString` (первое число строки — аргумент `px1`,
    остальные `Nx2` — значения). Пустая первая ячейка оси отдельно не
    обрабатывается — при разборе по разделителям её просто нет.
    """
    if not data:
        return _fail(source, "директивы есть, а матрицы нет: ни одной строки "
                             "данных (среда в этом случае даёт "
                             "TableErr_IncorrectFileStructure)")
    if table_type == TABLE_TYPE_ONE_ARG:
        flat: List[Tuple[float, ...]] = []
        for number, line in data:
            values = _numbers(line, number, source)
            if flat and len(values) != len(flat[0]):
                return _fail(source, (
                    f"строка {number}: {len(values)} чисел, а в первой строке "
                    f"матрицы {len(flat[0])} — матрица должна быть "
                    f"прямоугольной"))
            flat.append(values)
        return flat, [], []

    if len(data) < 2:
        return _fail(source, "для $TabType=1 нужны ось столбцов и хотя бы одна "
                             "строка данных")
    axis = _numbers(data[0][1], data[0][0], source)
    if not axis:
        return _fail(source, f"строка {data[0][0]}: ось столбцов пуста")
    rows: List[Tuple[float, ...]] = []
    row_labels: List[float] = []
    for number, line in data[1:]:
        values = _numbers(line, number, source)
        if len(values) != len(axis) + 1:
            return _fail(source, (
                f"строка {number}: {len(values)} чисел, а для $TabType=1 нужно "
                f"{len(axis) + 1} (метка строки и {len(axis)} значений по оси)"))
        row_labels.append(values[0])
        rows.append(values[1:])
    return rows, row_labels, list(axis)


def _numbers(line: str, number: int, source: str) -> Tuple[float, ...]:
    """Числа строки; нечисловая ячейка — отказ с её координатами.

    Ноль вместо нечисловой ячейки не подставляется: 0.0 — правдоподобное
    значение таблицы свойств, и подмена была бы неотличима от настоящего нуля.
    """
    tokens = line.split()
    values: List[float] = []
    for column, token in enumerate(tokens, start=1):
        if not _NUMBER_RE.match(token):
            return _fail(source, f"строка {number}, столбец {column}: "
                                 f"{token!r} — не число")
        values.append(float(token))
    return tuple(values)


def _fail(source: str, message: str) -> NoReturn:
    """Отказ разбора: сообщение начинается с источника.

    Возврат `NoReturn` — не украшение: вызывающие пишут `return _fail(...)`
    там, где обязаны вернуть значение, и без этого типа проверка типов не
    знала бы, что после отказа исполнение не продолжается.
    """
    raise TableFormatError(f"{source}: {message}")
