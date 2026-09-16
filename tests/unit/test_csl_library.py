"""Тесты разбора индекса библиотек блоков (.csl) — без COM."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from simintech_api.csl_library import (  # noqa: E402
    LibraryRecord,
    class_names,
    libraries_in_profile,
    load_library,
    missing_paramsets,
    parse_csl_index,
    resolve_paramset,
)


def _csl(*strings: str, pad: bytes = b"\x01\x02\x03\x04\x00\x00\x00\x00") -> bytes:
    """Синтетический `.csl`: строки UTF-16LE, разделённые двоичным мусором.

    Так устроен настоящий файл: индекс лежит вперемешку с числами и флагами,
    и брать из него можно только печатаемые последовательности.
    """
    out = bytearray(pad)
    for s in strings:
        out += pad
        out += s.encode("utf-16-le")
    return bytes(out)


def test_parses_record_and_paramset_pair():
    """Пара «имя записи → файл набора» — то, ради чего индекс и читается."""
    records = parse_csl_index(_csl(
        "Конечные автоматы", "Конечные автоматы - Состояние автомата",
        "kon_avt/kon_avt_sostoyanie_avtomata.ps"))

    assert LibraryRecord("Конечные автоматы - Состояние автомата",
                         "kon_avt/kon_avt_sostoyanie_avtomata.ps") in records


def test_pairs_pick_only_rows_followed_by_ps():
    """Записью считается только строка, за которой идёт путь к `.ps`."""
    records = parse_csl_index(_csl(
        "Конечные автоматы на языке программирования",
        "Конечные автоматы - Состояние автомата",
        "kon_avt/kon_avt_sostoyanie_avtomata.ps"))

    names = [r.name for r in records]
    assert names == ["Конечные автоматы - Состояние автомата"]
    assert "Конечные автоматы на языке программирования" not in names


def test_record_without_paramset_is_not_invented():
    """Запись без набора параметров не выдумывается.

    «Конечные автоматы - Коммутатор структуры автомата» объявлена в палитре,
    но файла набора у неё нет — в списке записей её быть не должно, иначе
    агент решит, что блок можно создать с параметрами.
    """
    records = parse_csl_index(_csl(
        "Конечные автоматы - Коммутатор структуры автомата",
        "Конечные автоматы - Состояние автомата",
        "kon_avt/kon_avt_sostoyanie_avtomata.ps"))

    assert [r.name for r in records] == ["Конечные автоматы - Состояние автомата"]


def test_two_paths_in_a_row_are_not_a_pair():
    """Пара — это имя и путь, а не два пути подряд.

    В индексе имена и пути идут вперемешку с числами; если считать парой
    любые две строки, где вторая оканчивается на `.ps`, в записи попадёт путь,
    и «блоком» окажется имя файла.
    """
    records = parse_csl_index(_csl(
        "a.ps", "b.ps",
        "Блок", "c.ps"))

    assert [r.name for r in records] == ["Блок"]


def test_duplicate_pairs_collapse():
    """Одна и та же пара, объявленная дважды, даёт одну запись."""
    records = parse_csl_index(_csl(
        "Блок", "block.ps",
        "Блок", "block.ps"))

    assert len(records) == 1


def test_empty_file_gives_no_records():
    """Пустой файл — пустой список, а не исключение."""
    assert parse_csl_index(b"") == []


def test_load_library_reads_file(tmp_path):
    path = tmp_path / "LIB_Test.csl"
    path.write_bytes(_csl("Блок", "block.ps"))

    lib = load_library(path)

    assert lib.name == "LIB_Test.csl"
    assert [r.name for r in lib.records] == ["Блок"]


def test_resolve_paramset_finds_existing_file(tmp_path):
    ps_dir = tmp_path / "ParamSet_mvtu"
    (ps_dir / "kon_avt").mkdir(parents=True)
    target = ps_dir / "kon_avt" / "a.ps"
    target.write_bytes(b"\x00" * 8)

    found = resolve_paramset(
        ps_dir, LibraryRecord("Блок", "kon_avt\\a.ps"))

    assert found == target


def test_resolve_paramset_returns_none_when_file_absent(tmp_path):
    ps_dir = tmp_path / "ParamSet_mvtu"
    ps_dir.mkdir()

    assert resolve_paramset(ps_dir, LibraryRecord("Блок", "нет.ps")) is None


def test_resolve_paramset_refuses_escape(tmp_path):
    """Путь наружу каталога наборов не принимается.

    В поставке встречается путь в сборочное дерево разработчика
    (`..\\..\\..\\HomeGit\\digcomm\\...`) — он указывает за пределы установки,
    и отдавать его наружу нельзя, даже если файл там когда-то был.
    """
    ps_dir = tmp_path / "ParamSet_mvtu"
    ps_dir.mkdir()
    outside = tmp_path / "outside.ps"
    outside.write_bytes(b"\x00" * 8)

    assert resolve_paramset(ps_dir, LibraryRecord("Блок", "..\\outside.ps")) is None


def test_resolve_paramset_without_paramset(tmp_path):
    assert resolve_paramset(tmp_path, LibraryRecord("Блок")) is None


def test_libraries_in_profile_reads_lowercased_names(tmp_path):
    """Профиль решает, какие библиотеки загружены; регистр не важен."""
    profile = tmp_path / "base.xml"
    profile.write_text(
        "<profile><libs><lib>CommonLib.xcsl</lib><lib>LIB_Mech.csl</lib></libs>"
        "</profile>", encoding="utf-8")

    assert libraries_in_profile(profile) == ["commonlib.xcsl", "lib_mech.csl"]


def test_class_names_skips_libraries_outside_profile(tmp_path):
    """Записи библиотек вне профиля в список не попадают.

    Файл на диске ещё не значит загруженную библиотеку: движок такие записи
    создать не может, и брать их в справочник — ошибка.
    """
    (tmp_path / "Loaded.csl").write_bytes(_csl("Блок A", "a.ps"))
    (tmp_path / "Skipped.csl").write_bytes(_csl("Блок B", "b.ps"))

    names = class_names(tmp_path, libraries=["loaded.csl"])

    assert names == ["Блок A"]


def test_class_names_without_filter_returns_all(tmp_path):
    (tmp_path / "Loaded.csl").write_bytes(_csl("Блок A", "a.ps"))
    (tmp_path / "Skipped.csl").write_bytes(_csl("Блок B", "b.ps"))

    assert sorted(class_names(tmp_path)) == ["Блок A", "Блок B"]


def test_class_names_deduplicates(tmp_path):
    """Одна запись в двух библиотеках попадает в список один раз."""
    (tmp_path / "A.csl").write_bytes(_csl("Общий", "a.ps"))
    (tmp_path / "B.csl").write_bytes(_csl("Общий", "b.ps"))

    assert class_names(tmp_path) == ["Общий"]


def test_missing_paramsets_lists_records_without_files(tmp_path):
    ps_dir = tmp_path / "ParamSet_mvtu"
    ps_dir.mkdir()
    (ps_dir / "есть.ps").write_bytes(b"\x00" * 8)

    class _Lib:
        records = (LibraryRecord("Есть", "есть.ps"),
                   LibraryRecord("Нет", "нет.ps"),
                   LibraryRecord("Без набора", ""))

    missing = missing_paramsets(ps_dir, [_Lib()])

    assert [r.name for r in missing] == ["Нет"]
