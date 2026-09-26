"""Тесты разбора таблиц SimInTech (.tbl) — без COM.

Фикстуры повторяют реальные файлы поставки строка за строкой, а не выдуманы:
табуляции в матрице, пустая первая ячейка оси столбцов, многострочный
`$Script` с абзацами, CP1251 без BOM. Отдельные проверки (маркер
`distribution`) идут по всей поставке — они медленные и по умолчанию не
запускаются.
"""

import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest  # noqa: E402

from simintech_api.tbl import (  # noqa: E402
    NotATableError,
    TableFormatError,
    load_tables,
    parse_tables,
)

#: Каталог поставки для сплошной проверки. Переопределяется переменной
#: окружения: путь к установленному SimInTech64 у каждого свой.
DISTRIBUTION_ROOT = os.environ.get("SIMINTECH_DISTR", "/mnt/c/SimInTech64")

#: Сколько `.tbl` в поставке: 494 в `bin/DataBase` и 9 в `Demo`. Счётчик ловит
#: не только пропажу обхода, но и «нашли меньше, чем есть».
DISTRIBUTION_FILES = 503

#: Разложение поставки по кодировкам — зафиксировано переписью файлов:
#: CP1251 без BOM, UTF-8 с BOM, UTF-8/ASCII без BOM и четыре бинарных.
DISTRIBUTION_CP1251 = 305
DISTRIBUTION_UTF8_BOM = 171
DISTRIBUTION_PLAIN = 23
DISTRIBUTION_BINARY = 4

#: Сколько файлов разбирается и сколько отвергается. Отвергаются 24 файла без
#: единой `$`-директивы (23 голые матрицы старой формы и один файл языка) и
#: 4 бинарные таблицы свойств.
DISTRIBUTION_PARSED = 475
DISTRIBUTION_NO_DIRECTIVES = 24
DISTRIBUTION_LANGUAGE_FILES = 1

#: Всего таблиц и их типов: `$TabType=1` втрое больше, чем `$TabType=0`.
DISTRIBUTION_TABLES = 964
DISTRIBUTION_TWO_ARG = 747
DISTRIBUTION_ONE_ARG = 217

#: Таблицы, где объявленный размер разошёлся с матрицей: расхождение не
#: ошибка разбора, но и не молчание — оно обязано быть названо. Список
#: точный, потому что «сколько-то расхождений» ничего не проверяет.
DISTRIBUTION_MISMATCHED = frozenset({
    "bin/DataBase/HS/ENGINES/COMPRESSORS/Rotrex_с_высотностью.tbl",
    "bin/DataBase/HS/MATERIALS/Связующее вещество между стеклами"
    " (эпоксидная смола ЭД-5).tbl",
    "bin/DataBase/HS/MATERIALS/Ткань.tbl",
    "bin/DataBase/HS/MATERIALS/Человек.tbl",
    "bin/DataBase/KeRC/HPM/МПГ-7.tbl",
    "bin/DataBase/KeRC/HPM/УУКМ_26.tbl",
    "bin/DataBase/KeRC/HPM/сталь_31.tbl",
    "bin/DataBase/KeRC/HPM/стеклопластик_55.tbl",
    "bin/DataBase/KeRC/HPM/шаблон.tbl",
})

#: Повреждённый файл поставки: хвосты прилипли к строкам данных.
GLUED_TAILS = "bin/DataBase/K1000/TURBINA/st1_3.tbl"


def _tbl_bytes(text: str, *, bom: bool = True, encoding: str = "utf-8",
               crlf: bool = True) -> bytes:
    """Байты таблицы так, как их пишет среда: BOM и CRLF — по умолчанию."""
    if crlf:
        text = text.replace("\n", "\r\n")
    data = text.encode(encoding)
    return (b"\xef\xbb\xbf" + data) if bom else data


def _write(tmp_path: Path, text: str, *, bom: bool = True,
           encoding: str = "utf-8", crlf: bool = True,
           name: str = "table.tbl") -> Path:
    path = tmp_path / name
    path.write_bytes(_tbl_bytes(text, bom=bom, encoding=encoding, crlf=crlf))
    return path


def _table(caption: str = "Таблица", table_type: int = 0, *,
           col_count: int = 3, row_count: int = 2, matrix_name: str = "M",
           graph_type: int = 0, matrix: str = "1\t0\t1\n2\t0.5\t0.8",
           scripts: str = "", globals_: str = "",
           omit: tuple = ()) -> str:
    """Текст одной таблицы в порядке, в каком его пишет среда.

    `omit` выбрасывает директивы по имени — так проверяются обязательные:
    без `$Caption` таблицы нет, без `$TabType` её не создаёт пак.
    """
    lines = []
    for value in globals_.split("\n"):
        if value or globals_:
            lines.append("$GlobalScript=" + value)
    if "Caption" not in omit:
        lines.append("$Caption=" + caption)
    if "TabType" not in omit:
        lines.append("$TabType=%d" % table_type)
    lines.append("$GraphType=%d" % graph_type)
    lines.append("$ColCount=%d" % col_count)
    lines.append("$RowCount=%d" % row_count)
    if "MatrixName" not in omit:
        lines.append("$MatrixName=" + matrix_name)
    for value in scripts.split("\n"):
        if value or scripts:
            lines.append("$Script=" + value)
    return "\n".join(lines) + "\n\n" + matrix + "\n"


# ─── Обычный разбор ──────────────────────────────────────────────────


def test_parses_one_arg_table():
    """`$TabType=0`: матрица `RowCount × ColCount`, меток у осей нет.

    Фикстура — «Тригонометрические» из `Demo/**/Пример таблиц.tbl`: скрипт
    таблицы заполняет `M[i, j]`, то есть первый столбец — аргумент, остальные —
    функции. Именно поэтому первые числа строк (1, 2, 3) остаются в матрице:
    для `TabType=0` строка — это все `ColCount` чисел, а не «метка+значения».
    """
    text = _table(
        caption="Тригонометрические", table_type=0, col_count=3, row_count=3,
        globals_="const\n\tN_points = 100,\n\tEps = 1E-12;",
        scripts="var\n\tFunSin[N_points];\n\nFunSin[i] = Sin(X);\nend;",
        matrix="1\t0\t1\n2\t0.20791169\t0.9781476\n3\t0.40673664\t0.91354546")

    tables = parse_tables(text)

    assert len(tables) == 1
    table = tables[0]
    assert table.caption == "Тригонометрические"
    assert table.table_type == 0
    assert (table.col_count, table.row_count) == (3, 3)
    assert table.matrix_name == "M"
    assert table.graph_type == 0
    assert table.rows == ((1.0, 0.0, 1.0),
                          (2.0, 0.20791169, 0.9781476),
                          (3.0, 0.40673664, 0.91354546))
    assert table.row_labels == () and table.col_labels == ()
    assert table.warnings == ()


def test_script_keeps_lines_and_paragraphs():
    """`$Script` — по строке на директиву; пустое значение остаётся абзацем.

    Склеивать строки нельзя: среда пишет скрипт построчно, и пустой `$Script=`
    — это пустая строка внутри текста, а не отсутствие значения.
    """
    text = _table(scripts="var\n\tFunSin[N_points];\n\nfor (i = 1,N_points) begin",
                  globals_="const\n\tEps = 1E-12;")

    table = parse_tables(text)[0]

    assert table.scripts == ("var", "\tFunSin[N_points];", "",
                             "for (i = 1,N_points) begin")
    assert table.global_scripts == ("const", "\tEps = 1E-12;")


def test_parses_two_arg_table_with_axis():
    """`$TabType=1`: строка оси столбцов, затем «метка строки + значения».

    Фикстура — первая таблица `K1000/TURBINA/st1_3.tbl`. Пустая первая ячейка
    оси отдельной веткой не обрабатывается: при разборе по разделителям её
    просто нет, и это правильно — числа оси идут подряд.
    """
    text = _table(
        caption="Относительное сопротивление канала", table_type=1,
        col_count=6, row_count=2,
        matrix=("\t0.0\t348.3698\t764.9443\t1114.573\t1426.351\t1.0e+9\n"
                "000.0\t1.04\t1.04\t1.022\t1.010\t1.005\t1.005\n"
                "1.0e+9\t1.04\t1.04\t1.022\t1.010\t1.005\t1.005"))

    table = parse_tables(text)[0]

    assert table.table_type == 1
    assert table.col_labels == (0.0, 348.3698, 764.9443, 1114.573, 1426.351,
                                1.0e+9)
    assert table.row_labels == (0.0, 1.0e+9)
    assert table.rows == ((1.04, 1.04, 1.022, 1.010, 1.005, 1.005),
                          (1.04, 1.04, 1.022, 1.010, 1.005, 1.005))


def test_axis_without_empty_cell_and_space_separators():
    """В 56 файлах поставки столбцы разделены пробелами, а ось — без «пустой» ячейки.

    Фикстура — `HS/COOLANTS/air_lib/Аммиак.tbl`: `$ColCount=3`, экспонента с
    ведущими нулями (`E+0005`) и несколько пробелов подряд. Пустой первой
    ячейки тут не видно вовсе, и это не отличает её от отсутствующей — числа
    оси всё равно читаются подряд, как в `TTable2.FromString`.
    """
    text = _table(
        caption="Температура", table_type=1, col_count=3, row_count=2,
        matrix=("   -1.47811990218295E+0005   -1.30638841368589E+0005   -1.1E+0005\n"
                "1.00000000000000E+0003   -7.68E+0001  -6.83E+0001  -5.4E+0001\n"
                "1.10000000000000E+0004   -6.99E+0001  -6.69E+0001  -5.3E+0001"))

    table = parse_tables(text)[0]

    assert table.col_labels == (-1.47811990218295e5, -1.30638841368589e5,
                                -1.1e5)
    assert table.row_labels == (1.0e3, 1.1e4)
    assert table.rows == ((-76.8, -68.3, -54.0), (-69.9, -66.9, -53.0))


def test_several_tables_split_by_hashes():
    """Таблиц в файле бывает несколько; делит их строка из решёток.

    Длина разделителя не важна: в поставке встречаются 37 и 40 решёток
    (`TABLE_SEP` в `tbls.pas` — 37), поэтому обе формы должны работать.
    """
    text = (_table(caption="Первая", matrix="1\t0\t1")
            + "#" * 37 + "\n"
            + _table(caption="Вторая", table_type=1, col_count=1, row_count=1,
                     matrix="\t0\t1\n0\t1\t2")
            + "#" * 40 + "\n"
            + _table(caption="Третья", matrix="3\t0\t1"))

    tables = parse_tables(text)

    assert [t.caption for t in tables] == ["Первая", "Вторая", "Третья"]
    assert [t.table_type for t in tables] == [0, 1, 0]


def test_matrix_name_is_optional_and_not_always_m():
    """`$MatrixName` необязательна, и значение у неё не всегда `M`.

    В поставке `M` встречается 884 раза, но есть и `kpd`, `h`, `KSI`, `Hn`,
    `m` — поэтому имя берётся из директивы, а не подставляется литералом.
    """
    text = (_table(caption="КПД", matrix_name="kpd") + "#" * 37 + "\n"
            + _table(caption="Без имени", omit=("MatrixName",),
                     matrix="1\t2\t3"))

    first, second = parse_tables(text)

    assert first.matrix_name == "kpd"
    assert second.matrix_name == ""


# ─── Кодировки и переводы строк ──────────────────────────────────────


def test_cp1251_without_bom(tmp_path):
    """305 файлов поставки — CP1251 без BOM; подпись читается, а не портится."""
    path = _write(tmp_path, _table(caption="Свойства материала, 25 °C"),
                  bom=False, encoding="cp1251")

    table = load_tables(path)[0]

    assert table.caption == "Свойства материала, 25 °C"


def test_utf8_with_bom(tmp_path):
    """171 файл — UTF-8 с BOM; BOM не должен попасть в первую директиву."""
    path = _write(tmp_path, _table(caption="Температура"), bom=True)

    table = load_tables(path)[0]

    assert table.caption == "Температура"
    assert "﻿" not in table.caption


def test_crlf_and_lf_parse_the_same(tmp_path):
    """Перевод строки внутри файла единообразен, но сам по себе не значим."""
    crlf = load_tables(_write(tmp_path, _table(caption="Таблица"), crlf=True,
                              name="crlf.tbl"))[0]
    lf = load_tables(_write(tmp_path, _table(caption="Таблица"), crlf=False,
                            name="lf.tbl"))[0]

    assert crlf == lf


# ─── Числа ───────────────────────────────────────────────────────────


def test_non_numeric_cell_is_refused_with_coordinates():
    """Нечисловая ячейка — отказ с номером строки файла и столбца, не 0.0.

    Ноль вместо мусора был бы неотличим от настоящего нуля таблицы свойств:
    «0.0» — правдоподобное значение, и подмена не видна ни вызывающему, ни
    расчёту. Поэтому отказ, и в сообщении — координаты, чтобы не искать
    ячейку по всему файлу.
    """
    text = _table(caption="Таблица", matrix="1\t0\t1\n2\tн/д\t0.8")

    with pytest.raises(TableFormatError) as excinfo:
        parse_tables(text, source="broken.tbl")

    message = str(excinfo.value)
    assert "broken.tbl" in message
    assert "строка 9, столбец 2" in message
    assert "'н/д'" in message


def test_decimal_comma_is_refused_not_split():
    """`1,5` — не число: десятичной запятой в формате быть не может.

    Среда перед разбором заменяет `,` на пробел (`MatrFromString`), поэтому
    `1,5` распалось бы на два числа. Здесь такое отвергается: «два числа там,
    где написано одно» — это уже выдумывание данных.
    """
    text = _table(caption="Таблица", matrix="1,5\t0\t1")

    with pytest.raises(TableFormatError) as excinfo:
        parse_tables(text)

    assert "'1,5'" in str(excinfo.value)


def test_exponential_with_leading_zeros_parses():
    """`2.53490000000000E+0005` — обычная запись среды, а не ошибка."""
    text = _table(caption="Таблица", matrix="2.53490000000000E+0005\t-5.507e-4\t1.")

    table = parse_tables(text)[0]

    assert table.rows == ((253490.0, -0.0005507, 1.0),)


def test_nan_and_underscores_are_refused():
    """`float()` принял бы `nan` и `1_0`; такие записи средой не пишутся."""
    for token in ("nan", "inf", "1_0"):
        with pytest.raises(TableFormatError):
            parse_tables(_table(caption="Таблица", matrix="1\t%s\t3" % token))


# ─── Структура: отказы ───────────────────────────────────────────────


def test_unknown_table_type_is_refused():
    """`$TabType` вне {0, 1} — отказ, а не разбор «как получится».

    В `tbls.pas` тип — элемент перечисления `(tbtNoType, tbtFunOfOneArg,
    tbtFunOfTwoArg, tbtFunOfNArg, tbtIsoLines)`, и значение в файле на единицу
    меньше номера элемента. Средства создания есть только у двух первых,
    поэтому 2 и 3 (N-мерная таблица и изолинии) читать нечем.
    """
    for table_type in (2, 3, 9):
        with pytest.raises(TableFormatError) as excinfo:
            parse_tables(_table(table_type=table_type), source="t.tbl")
        assert "не поддержан" in str(excinfo.value)


def test_missing_tab_type_is_refused():
    """Без `$TabType` тип таблицы неизвестен, и пак её не создаёт."""
    with pytest.raises(TableFormatError) as excinfo:
        parse_tables(_table(omit=("TabType",)))

    assert "$TabType" in str(excinfo.value)


def test_missing_caption_is_refused():
    """Без `$Caption` среда ставит `TableErr_FileFormatNotSupported`."""
    with pytest.raises(TableFormatError) as excinfo:
        parse_tables(_table(omit=("Caption",)))

    assert "$Caption" in str(excinfo.value)


def test_table_without_matrix_is_refused():
    """Директивы есть, матрицы нет — отказ, а не таблица из нуля строк."""
    with pytest.raises(TableFormatError) as excinfo:
        parse_tables(_table(matrix=""))

    assert "матрицы нет" in str(excinfo.value)


def test_ragged_one_arg_matrix_is_refused():
    """Строка другой длины ломает прямоугольность матрицы."""
    with pytest.raises(TableFormatError) as excinfo:
        parse_tables(_table(matrix="1\t0\t1\n2\t0.5"))

    assert "прямоугольной" in str(excinfo.value)


def test_row_of_wrong_width_in_two_arg_table_is_refused():
    """Для `$TabType=1` в строке должно быть «метка + столько же, сколько в оси»."""
    with pytest.raises(TableFormatError) as excinfo:
        parse_tables(_table(table_type=1, col_count=2, row_count=1,
                            matrix="\t0\t1\n0\t1\t2\t3"))

    assert "нужно 3" in str(excinfo.value)


def test_two_arg_table_without_rows_is_refused():
    """Ось без строк — не таблица: функция двух аргументов пустой не бывает."""
    with pytest.raises(TableFormatError):
        parse_tables(_table(table_type=1, col_count=2, row_count=0,
                            matrix="\t0\t1"))


def test_file_without_directives_is_not_a_table(tmp_path):
    """Файл без `$`-директив — отказ, а не таблица из нуля строк.

    Фикстура повторяет `Насосы РАСНАР/CN3K.tbl` — голую матрицу старой формы,
    которую среда читает другим классом (`TTable1`/`MatrFromString`, без
    метаинформации). Отвечать на такой файл «таблица из 0 строк» нельзя:
    пустая, но исправная таблица выглядит так же.
    """
    path = _write(tmp_path, "11      21\n-1.  -0.5  -0.3\n2.   1.5   1.3\n",
                  bom=False)

    with pytest.raises(NotATableError) as excinfo:
        load_tables(path)

    message = str(excinfo.value)
    assert "голые матрицы" in message or "ни одной $-директивы" in message
    assert "11      21" in message


def test_language_file_is_named_as_such(tmp_path):
    """`.tbl` бывает файлом языка SimInTech, и это надо назвать прямо.

    Фикстура — `Материалы_РАСНАР/ПТ7М.tbl` целиком (56 байт): комментарий и
    `const`. Отличить его от голой матрицы важно: «не таблица» и «таблица
    другой формы» — разные ответы.
    """
    path = _write(tmp_path, "//Материал ПТ7М\nconst CM=0.5,RM=4800.0;\n\n",
                  bom=False, encoding="cp1251")

    with pytest.raises(NotATableError) as excinfo:
        load_tables(path)

    assert "файл языка SimInTech" in str(excinfo.value)


def test_binary_table_is_refused_before_reading_it_all(tmp_path):
    """Бинарная таблица свойств отвергается как «не текстовая», а не как мусор.

    Структура файлов `water_iapws_tables_PH*.tbl` (17…191 МБ): счётчик uint64,
    дальше плоский массив double. Читать такой файл целиком незачем — NUL в
    первых килобайтах уже отвечает на вопрос.
    """
    path = tmp_path / "binary.tbl"
    path.write_bytes(struct.pack("<Q", 200) + struct.pack("<3d", 1.0, 2.0, 3.0))

    with pytest.raises(NotATableError) as excinfo:
        load_tables(path)

    message = str(excinfo.value)
    assert "бинарная таблица свойств" in message
    assert "32 байт" in message
    assert "массив double" in message


def test_unknown_directive_is_reported_not_hidden():
    """Незнакомая `$`-директива не роняет разбор, но и не исчезает молча."""
    text = _table(caption="Таблица").replace(
        "$ColCount=3", "$ColCount=3\n$NewField=7")

    table = parse_tables(text)[0]

    assert "$NewField" in " ".join(table.warnings)


# ─── Расхождения объявленного и фактического ─────────────────────────


def test_declared_size_mismatch_is_reported_and_data_wins():
    """Размер берётся из данных, а расхождение с директивой — в `warnings`.

    Фикстура повторяет `KeRC/HPM/шаблон.tbl`: `$ColCount=1`, а в строках по два
    числа (в скрипте таблицы так и написано: «столбец 1 — нумерация строк,
    столбец 2 — параметры»). Среда при расчёте восстанавливает матрицу по
    тексту, поэтому правы данные; но промолчать о расхождении нельзя, иначе
    читатель не отличит исправленную таблицу от испорченной директивы.
    """
    text = _table(caption="MAIN", col_count=1, row_count=2,
                  matrix="1\t0.76\n2\t0.8")

    table = parse_tables(text)[0]

    assert table.rows == ((1.0, 0.76), (2.0, 0.8))
    assert table.col_count == 1
    assert len(table.warnings) == 1
    assert "$ColCount=1" in table.warnings[0] and "2" in table.warnings[0]


def test_matching_sizes_produce_no_warnings():
    """Когда объявленное совпадает с данными, предупреждать не о чем."""
    table = parse_tables(_table(col_count=3, row_count=2))[0]

    assert table.warnings == ()


def test_missing_size_directives_are_not_invented():
    """Без `$ColCount`/`$RowCount` размеры неизвестны — и это `None`, не 0.

    Ноль означал бы «таблица без столбцов», то есть утверждение о файле,
    которого в файле нет.
    """
    text = _table(caption="Таблица").replace("$ColCount=3\n", "").replace(
        "$RowCount=2\n", "")

    table = parse_tables(text)[0]

    assert table.col_count is None and table.row_count is None
    assert table.warnings == ()


# ─── Повреждённый файл поставки ──────────────────────────────────────


def test_glued_tails_do_not_become_cells():
    """Прилипшие хвосты срезаются: решётки разделителя и директива.

    Фикстура — `K1000/TURBINA/st1_3.tbl`, где к строкам таблицы «КПД» прилипли
    решётки разделителя (`…3.00000E-01####…`) и директивы следующей таблицы
    (`…6.00000E-01$Caption=Момент`). Среда их не замечает: она читает из
    строки ровно `ColCount + 1` чисел. Здесь они тоже не должны становиться
    «нечисловыми ячейками», иначе настоящий файл поставки не разбирается.
    """
    text = _table(
        caption="КПД", table_type=1, col_count=3, row_count=3,
        matrix=("\t0\t1\t2\n"
                "0\t0.1\t0.2\t0.3" + "#" * 37 + "\n"
                "1\t0.4\t0.5\t0.6$Caption=Момент\n"
                "1\t0.7\t0.8\t0.9$TabType=1\n"))

    table = parse_tables(text)[0]

    assert table.rows == ((0.1, 0.2, 0.3), (0.4, 0.5, 0.6), (0.7, 0.8, 0.9))
    assert table.warnings == ()


# ─── Сплошная проверка поставки ──────────────────────────────────────
# Медленная (обход 9p-каталога) и зависит от установленного SimInTech64,
# поэтому вынесена под маркер: `pytest -m distribution`. Пока в объявлении
# маркеров нет исключения, фикстура сама пропускает проверки без явного
# `-m distribution` — иначе обычный прогон тянул бы обход всей поставки.


@pytest.fixture(scope="module")
def distribution(request):
    """Разбор всех `.tbl` поставки — один обход на все проверки.

    Возвращает список `(путь относительно корня, таблицы или исключение)`:
    обход 9p-каталога идёт минуты, и повторять его в каждой проверке нельзя.
    """
    if "distribution" not in (request.config.getoption("markexpr") or ""):
        pytest.skip("сплошная проверка поставки: pytest -m distribution")
    root = Path(DISTRIBUTION_ROOT)
    if not root.is_dir():
        pytest.skip(f"поставка не найдена: {root} (задайте SIMINTECH_DISTR)")

    found = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() != ".tbl":
            continue
        relative = path.relative_to(root).as_posix()
        try:
            found.append((relative, load_tables(path)))
        except (NotATableError, TableFormatError) as exc:
            found.append((relative, exc))
    return found


def _reasons(distribution):
    """Файлы, на которых разбор отказал: путь → исключение."""
    return {name: value for name, value in distribution
            if isinstance(value, Exception)}


def _parsed(distribution):
    """Файлы, которые разобрались: путь → список таблиц."""
    return {name: value for name, value in distribution
            if not isinstance(value, Exception)}


@pytest.mark.distribution
def test_distribution_file_count(distribution):
    """503 `.tbl` — столько их в поставке; счётчик ловит пропажу обхода."""
    assert len(distribution) == DISTRIBUTION_FILES


@pytest.mark.distribution
def test_distribution_encodings(distribution):
    """Кодировки поставки: 305 CP1251, 171 UTF-8 с BOM, 23 без BOM, 4 бинарных.

    Не «на всякий случай»: формулы «BOM есть всегда» и «BOM нет никогда» уже
    приводили к неверному разбору, а счётчик поймает смену поставки.
    """
    counts = {"cp1251": 0, "utf-8-bom": 0, "plain": 0, "binary": 0}
    for name, value in distribution:
        if isinstance(value, NotATableError) and "бинарная" in str(value):
            counts["binary"] += 1
            continue
        # Бинарные файлы (до 191 МБ) уже отсеяны выше: их байты не читаются.
        raw = (Path(DISTRIBUTION_ROOT) / name).read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            raw[3:].decode("utf-8")  # бросит, если это не UTF-8
            counts["utf-8-bom"] += 1
        elif b"\x00" in raw[:8192]:
            raise AssertionError(f"{name}: бинарный, но разбор не отказал")
        else:
            try:
                raw.decode("utf-8")
                counts["plain"] += 1
            except UnicodeDecodeError:
                raw.decode("cp1251")
                counts["cp1251"] += 1

    assert counts == {"cp1251": DISTRIBUTION_CP1251,
                      "utf-8-bom": DISTRIBUTION_UTF8_BOM,
                      "plain": DISTRIBUTION_PLAIN,
                      "binary": DISTRIBUTION_BINARY}


@pytest.mark.distribution
def test_distribution_every_file_parses_or_is_rejected(distribution):
    """Все 503 файла: 475 разбираются, 28 отвергаются — и с названной причиной.

    Отказов «структура нарушена» нет ни одного: в поставке нет таблиц с
    нечисловой ячейкой или несошедшимся числом столбцов, и если такие
    появятся, они должны быть перечислены здесь точно.
    """
    parsed = _parsed(distribution)
    reasons = _reasons(distribution)
    binary = [name for name, exc in reasons.items() if "бинарная" in str(exc)]
    language = [name for name, exc in reasons.items()
                if "файл языка SimInTech" in str(exc)]

    assert len(parsed) == DISTRIBUTION_PARSED
    assert len(reasons) == DISTRIBUTION_FILES - DISTRIBUTION_PARSED
    assert len(binary) == DISTRIBUTION_BINARY
    assert (len(language), language) == (
        DISTRIBUTION_LANGUAGE_FILES,
        ["bin/DataBase/Материалы_РАСНАР/ПТ7М.tbl"])
    assert len(reasons) - len(binary) - len(language) == \
        DISTRIBUTION_NO_DIRECTIVES - DISTRIBUTION_LANGUAGE_FILES


@pytest.mark.distribution
def test_distribution_table_counts(distribution):
    """964 таблицы, из них 747 двумерных и 217 одномерных.

    Число таблиц сходится с числом директив `$TabType` в поставке (964), а
    разбиение по типам — с переписью: `$TabType=1` втрое больше.
    """
    tables = [table for value in _parsed(distribution).values() for table in value]
    two_arg = [t for t in tables if t.table_type == 1]

    assert len(tables) == DISTRIBUTION_TABLES
    assert len(two_arg) == DISTRIBUTION_TWO_ARG
    assert len(tables) - len(two_arg) == DISTRIBUTION_ONE_ARG


@pytest.mark.distribution
def test_distribution_matrix_shapes_are_consistent(distribution):
    """Матрицы поставки прямоугольны, оси и метки сходятся с числом значений."""
    for name, tables in _parsed(distribution).items():
        for table in tables:
            assert table.rows, f"{name}: {table.caption} — матрица пуста"
            width = len(table.col_labels) if table.table_type else len(table.rows[0])
            assert width > 0, f"{name}: {table.caption} — ноль столбцов"
            for row in table.rows:
                assert len(row) == width, f"{name}: {table.caption}"
            if table.table_type == 1:
                assert len(table.row_labels) == len(table.rows), name
                assert len(table.col_labels) == width, name


@pytest.mark.distribution
def test_distribution_mismatches_are_only_these(distribution):
    """Расхождения объявленного размера — ровно в девяти файлах поставки.

    Это не ошибка разбора: в `HS/MATERIALS/*.tbl` объявлен `$RowCount=1` при
    двух строках, в `KeRC/HPM/*.tbl` — `$ColCount=1` при двух столбцах, а в
    `Rotrex_с_высотностью.tbl` оба сразу. Список точный: «есть расхождения»
    ничего не проверяет, а пропажа одного из них — регресс.
    """
    mismatched = {
        name for name, tables in _parsed(distribution).items()
        if any(table.warnings for table in tables)
    }

    assert mismatched == set(DISTRIBUTION_MISMATCHED)


@pytest.mark.distribution
def test_distribution_glued_tails_file(distribution):
    """Единственный повреждённый файл разбирается на три исправные таблицы.

    В `K1000/TURBINA/st1_3.tbl` к строкам прилипли решётки и директивы, но
    размеры всех трёх таблиц сходятся с данными — значит, хвосты срезаны
    верно, а не «повезло с числами».
    """
    tables = _parsed(distribution)[GLUED_TAILS]

    assert [(t.caption, t.col_count, t.row_count) for t in tables] == [
        ("Относительное сопротивление канала", 6, 2),
        ("КПД", 8, 7),
        ("Момент сопротивления", 3, 3)]
    assert all(t.warnings == () for t in tables)


@pytest.mark.distribution
def test_distribution_known_files(distribution):
    """Размеры известных файлов поставки — контрольные точки разбора.

    Газы и теплоносители — самые большие матрицы поставки, ст1_3 — самый
    крупный пак таблиц, «Пример таблиц» — единственный файл с `$GlobalScript`.
    """
    parsed = _parsed(distribution)
    ammonia = parsed["bin/DataBase/HS/COOLANTS/air_lib/Аммиак.tbl"][0]
    example = parsed[
        "Demo/Язык программирования/Функции/Функции работы с таблицами "
        "инструмента Редактор таблиц/Пример таблиц.tbl"]

    assert (len(ammonia.rows), len(ammonia.col_labels)) == (199, 200)
    assert ammonia.caption == "Температура"
    assert example[0].global_scripts == ("const", "\tN_points = 100,",
                                         "\tEps = 1E-12;")
    assert [t.caption for t in example] == ["Тригонометрические", "Параболоид"]
    assert [t.table_type for t in example] == [0, 1]
