"""Тесты разбора пакета проектов (.pak) — без COM.

Фикстуры повторяют реальные файлы поставки, а не выдуманы: строка за строкой
так, как их пишет среда. Отдельная проверка (маркер `distribution`, по умолчанию
не запускается) идёт по всем 63 файлам `Demo/**/*.pak` — она же ловит регресс
кодировок счётчиком 62/1.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest  # noqa: E402

from simintech_api.exceptions import PackError  # noqa: E402
from simintech_api.pak import (  # noqa: E402
    decode_pack,
    load_pack,
    load_packs,
    parse_pack,
)

#: Каталог поставки для сплошной проверки. Переопределяется переменной
#: окружения: путь к установленному SimInTech64 у каждого свой.
DISTRIBUTION_ROOT = os.environ.get("SIMINTECH_DISTR", "/mnt/c/SimInTech64")

#: Кодировки, встреченные в поставке: 62 файла из 63 — UTF-8 с BOM, один
#: (`kba_with_safety.pak`) — CP1251 без BOM. Числа зафиксированы проверкой
#: поставки, а не предположением.
DISTRIBUTION_UTF8_BOM = 62
DISTRIBUTION_CP1251 = 1
DISTRIBUTION_PACKS = 63
DISTRIBUTION_RECORDS = 169

#: Пример записи `[Files]` из поставки: обратный слэш, кириллица.
RECORDED_PATH = "Схемы\\701.prt"

#: Файл поставки с абсолютными путями — единственный с отклонениями.
ABSOLUTE_PATHS_PACK = "Пример работы с TIMER.pak"

#: Условный путь к пакету для разбора из строки: `parse_pack` берёт от него
#: только каталог, в котором раскрываются относительные записи.
PACK = Path("Пакет.pak")


def _pak_bytes(text: str, *, bom: bool = True, encoding: str = "utf-8",
               crlf: bool = True) -> bytes:
    """Байты пакета так, как их пишет среда: BOM и CRLF — по умолчанию."""
    if crlf:
        text = text.replace("\n", "\r\n")
    data = text.encode(encoding)
    return (b"\xef\xbb\xbf" + data) if bom else data


def _pak_text(files=("Схемы\\701.prt", "Компоненты\\Компоненты.prt"),
              *, count=None, form=True, restart="", relative_path=1, common=None,
              active=None, time_sync=None) -> str:
    """Текст пакета; по умолчанию — обычный файл поставки целиком.

    `active`/`time_sync`: None — строки по умолчанию (все ``1``), False — секции
    нет вовсе, список строк — как задано (для пропусков и лишних номеров).
    `count=False` — ключа ``Count=`` нет.
    """
    lines = []
    if form:
        lines += [
            "[Form]",
            "Rect.L=1474", "Rect.T=129", "Rect.R=1927", "Rect.B=379",
            "ConsoleHeight=69", "WindowState=0", "ColCount=7",
            "ColWidth0=226", "ColWidth1=91", "ColWidth2=88", "ColWidth3=62",
            "ColWidth4=88", "ColWidth5=58", "ColWidth6=65",
        ]
    lines += ["[Common]"]
    lines += common if common is not None else [
        "Synchronize=1",
        f"RelativePath={relative_path}",
        "IsRealTime=1",
        "TimeMash=1",
        "fSimpleSignalLoad=2",
        "formstyle=0",
        f"restartname={restart}",
        "notqueryremoveforall=0",
    ]
    lines += ["[Files]"]
    if count is not False:
        lines.append(f"Count={len(files) if count is None else count}")
    lines += [f"{i}={p}" for i, p in enumerate(files)]
    for section, rows in (("Active", active), ("TimeSync", time_sync)):
        if rows is False:
            continue
        lines += [f"[{section}]"]
        if rows is None:
            lines += [f"{i}=1" for i in range(len(files))]
        else:
            lines += list(rows)
    return "\n".join(lines) + "\n"


def _write(tmp_path, text, name="Пакет.pak", **kwargs):
    path = tmp_path / name
    path.write_bytes(_pak_bytes(text, **kwargs))
    return path


def test_usual_pack_reads_composition_in_launch_order(tmp_path):
    """Обычный пакет: состав в порядке строк [Files], флаги и [Common] на месте."""
    path = _write(tmp_path, _pak_text())

    pack = load_pack(path)

    assert pack.path == path
    assert [p.path for p in pack.projects] == [
        "Схемы\\701.prt", "Компоненты\\Компоненты.prt"]
    assert [p.index for p in pack.projects] == [0, 1]
    assert pack.count == 2
    assert pack.project_count == 2
    assert pack.synchronize is True
    assert pack.relative_path is True
    assert pack.real_time is True
    assert pack.time_mash == 1.0
    assert pack.restart_name == ""
    assert pack.has_files_section is True
    assert pack.problems == ()


def test_project_name_is_the_file_name_only():
    pack = parse_pack(_pak_text(files=("Схемы\\701.prt",)), PACK)

    assert pack.projects[0].name == "701.prt"


def test_pages_are_crlf_but_lf_would_read_the_same(tmp_path):
    """В поставке CRLF (39 файлов из 63) и есть LF — разбор не зависит от этого."""
    crlf = parse_pack(_pak_text(), PACK)
    lf = parse_pack(_pak_text().replace("\r\n", "\n"), PACK)

    assert crlf.projects == lf.projects
    assert crlf.count == lf.count


def test_relative_paths_are_expanded_from_pack_dir_with_forward_slashes(tmp_path):
    """`Схемы\\701.prt` → `<каталог пакета>/Схемы/701.prt`; слэш — разделитель."""
    path = _write(tmp_path, _pak_text(files=("Схемы\\701.prt",)))
    (tmp_path / "Схемы").mkdir()
    (tmp_path / "Схемы" / "701.prt").write_bytes(b"")

    pack = load_pack(path)

    resolved = pack.resolved_paths()
    assert resolved[0] == (tmp_path / "Схемы" / "701.prt").resolve()
    assert pack.resolve(pack.projects[0]) == resolved[0]
    assert "\\" not in str(resolved[0])


def test_time_mash_is_a_float_not_a_flag():
    """`TimeMash=0.003` — число, а не флаг: в поставке встречаются 0.003 и 100."""
    def mash(value):
        return parse_pack(_pak_text(files=("a.prt",), common=[
            "Synchronize=1", "RelativePath=1", "IsRealTime=1",
            f"TimeMash={value}", "restartname=",
        ]), PACK).time_mash

    assert mash("0.003") == 0.003
    assert mash("100") == 100.0
    assert mash("1") == 1.0


def test_active_and_time_sync_are_independent():
    """В поставке `Active=1` у всех, а `TimeSync=0` — у трёх: флаги не связаны."""
    text = _pak_text(files=("a.prt", "b.prt"), active=["0=1", "1=1"],
                     time_sync=["0=1", "1=0"])

    pack = parse_pack(text, PACK)

    assert [p.active for p in pack.projects] == [True, True]
    assert [p.time_sync for p in pack.projects] == [True, False]
    assert pack.problems == ()


def test_flag_row_absent_gives_none_not_false():
    """Пропущенной строке `[Active]` соответствует «неизвестно», а не «выключено»."""
    text = _pak_text(files=("a.prt", "b.prt"), active=["0=1"], time_sync=False)

    pack = parse_pack(text, PACK)

    assert pack.projects[0].active is True
    assert pack.projects[1].active is None
    assert any("[Active]" in problem for problem in pack.problems)


def test_flag_value_outside_zero_and_one_is_not_a_guess():
    """`Synchronize=on` — не «включено»: значение, которого мы не знаем, — None."""
    text = _pak_text(files=("a.prt",), common=[
        "Synchronize=on", "RelativePath=1", "IsRealTime=0", "TimeMash=2",
    ])

    pack = parse_pack(text, PACK)

    assert pack.synchronize is None
    assert pack.real_time is False


def test_count_mismatch_is_reported_not_silently_resolved():
    """`Count=3` при двух строках: обе цифры сохранены, расхождение названо."""
    text = _pak_text(files=("a.prt", "b.prt"), count=3)

    pack = parse_pack(text, PACK)

    assert pack.count == 3
    assert pack.project_count == 2
    assert any("Count=3" in problem and "(2)" in problem
               for problem in pack.problems)


def test_count_absent_is_reported():
    text = _pak_text(files=("a.prt",), count=False)

    pack = parse_pack(text, PACK)

    assert pack.count is None
    assert pack.project_count == 1
    assert any("Count" in problem for problem in pack.problems)


def test_count_not_a_number_is_reported():
    text = _pak_text(files=("a.prt",), count="много")

    pack = parse_pack(text, PACK)

    assert pack.count is None
    assert any("не число" in problem for problem in pack.problems)


def test_numbering_gap_keeps_file_order_and_is_reported():
    """При дыре в нумерации порядок запуска задаёт позиция строки, а не номер."""
    text = _pak_text(files=("a.prt", "b.prt"), active=["0=1", "2=1"],
                     time_sync=["0=1", "2=1"]).replace("1=b.prt", "2=b.prt")

    pack = parse_pack(text, PACK)

    assert [p.index for p in pack.projects] == [0, 2]
    assert [p.path for p in pack.projects] == ["a.prt", "b.prt"]
    assert [p.active for p in pack.projects] == [True, True]
    assert any("0..1" in problem for problem in pack.problems)


def test_records_out_of_order_follow_the_file_not_the_numbers():
    """Порядок запуска задаёт строка файла: `1=` перед `0=` читается как есть.

    Нумерация при этом названа расхождением — обе стороны видны вызывающему,
    и выбирать между ними модуль не берётся.
    """
    text = _pak_text(files=("Первый.prt", "Второй.prt")).replace(
        "0=Первый.prt\n1=Второй.prt", "1=Второй.prt\n0=Первый.prt")

    pack = parse_pack(text, PACK)

    assert [p.path for p in pack.projects] == ["Второй.prt", "Первый.prt"]
    assert [p.index for p in pack.projects] == [1, 0]
    assert any("0..1" in problem for problem in pack.problems)


def test_path_collapsing_to_the_pack_dir_itself_is_allowed(tmp_path):
    """`Схемы\\..` сворачивается в сам каталог пакета — наружу не вышло.

    Граница та же, что у `resolve_paramset`: каталог пакета включается в
    дозволенное. Существование файла здесь не проверяется — это работа с
    путём, а не с диском.
    """
    text = _pak_text(files=("Схемы\\..",))

    pack = parse_pack(text, tmp_path / "Пакет.pak")

    assert pack.resolve(pack.projects[0]) == tmp_path.resolve()
    assert pack.problems == ()


def test_duplicated_number_is_not_swallowed():
    """Повтор `0=` меняет состав — обе записи сохраняются, повтор назван."""
    text = _pak_text(files=("a.prt", "b.prt")).replace("1=b.prt", "0=b.prt")

    pack = parse_pack(text, PACK)

    assert [p.path for p in pack.projects] == ["a.prt", "b.prt"]
    assert any("повтор" in problem.lower() for problem in pack.problems)


def test_path_escaping_the_pack_dir_is_refused(tmp_path):
    """`..` наружу не выпускается: путь из файла недоверенный."""
    text = _pak_text(files=(RECORDED_PATH, "..\\..\\secret.prt"))

    pack = parse_pack(text, tmp_path / "Пакет.pak")

    assert pack.projects[1].absolute is False
    assert pack.resolve(pack.projects[1]) is None
    assert pack.resolved_paths()[0] is not None
    assert pack.resolved_paths()[1] is None
    assert any("выходящие за каталог" in problem for problem in pack.problems)


def test_dotdot_staying_inside_the_pack_dir_is_allowed(tmp_path):
    """`Схемы\\..\\701.prt` остаётся внутри каталога — это не выход наружу."""
    text = _pak_text(files=("Схемы\\..\\701.prt",))

    pack = parse_pack(text, tmp_path / "Пакет.pak")

    assert pack.resolve(pack.projects[0]) == (tmp_path / "701.prt").resolve()
    assert pack.problems == ()


def test_absolute_path_is_not_expanded_into_the_pack_dir(tmp_path):
    """`E:\\!Work\\...` развернуть относительно пакета нечем — resolve() даёт None."""
    absolute = "E:\\!Work\\АЭС\\tim_init.prt"
    text = _pak_text(files=(RECORDED_PATH, absolute))

    pack = parse_pack(text, tmp_path / "Пакет.pak")

    assert pack.projects[1].absolute is True
    assert pack.projects[1].path == absolute
    assert pack.resolve(pack.projects[1]) is None
    assert pack.resolve(pack.projects[0]) is not None
    assert any("абсолютные пути" in problem for problem in pack.problems)


def test_absolute_path_is_recognised_by_record_not_by_platform(tmp_path):
    """`Path.is_absolute()` на Linux не признал бы `E:\\...` — правило по записи."""
    text = _pak_text(files=("E:\\!Work\\tim_init.prt", "\\\\server\\share\\a.prt",
                            "/opt/models/b.prt"))

    pack = parse_pack(text, tmp_path / "Пакет.pak")

    assert [p.absolute for p in pack.projects] == [True, True, True]
    assert pack.resolved_paths() == (None, None, None)


def test_empty_path_is_reported():
    text = _pak_text(files=("a.prt", "b.prt")).replace("1=b.prt", "1=")

    pack = parse_pack(text, PACK)

    assert pack.projects[1].path == ""
    assert pack.resolve(pack.projects[1]) is None
    assert any("пустые пути" in problem for problem in pack.problems)


def test_missing_time_sync_section_is_not_an_error():
    """Нет `[TimeSync]` — флаги неизвестны, но разбор состоялся."""
    text = _pak_text(files=("a.prt", "b.prt"), time_sync=False)

    pack = parse_pack(text, PACK)

    assert [p.time_sync for p in pack.projects] == [None, None]
    assert [p.active for p in pack.projects] == [True, True]
    assert any("[TimeSync]" in problem for problem in pack.problems)


def test_short_form_section_is_not_an_error():
    """Усечённый `[Form]` (только Rect.*) и нет `notqueryremoveforall` — норма.

    Так выглядит `kba_with_safety.pak` — единственный CP1251-файл поставки.
    """
    text = "\n".join([
        "[Form]", "Rect.L=4", "Rect.T=151", "Rect.R=280", "Rect.B=387",
        "[Common]", "Synchronize=1", "RelativePath=1", "IsRealTime=1",
        "TimeMash=2", "fSimpleSignalLoad=2", "formstyle=3", "restartname=",
        "[Files]", "Count=4", "0=KBA.prt", "1=Алгоритмы KBA.prt",
        "2=Блоки управления.prt", "3=kba_safety_controller.prt",
        "[Active]", "0=1", "1=1", "2=1", "3=1",
        "[TimeSync]", "0=1", "1=1", "2=1", "3=1",
    ]) + "\n"

    pack = parse_pack(text, Path("kba_with_safety.pak"))

    assert pack.project_count == 4
    assert pack.problems == ()


def test_col_count_is_not_the_project_count():
    """`ColCount=7` — ширина колонок окна; проектов в том же файле два."""
    text = _pak_text(files=("a.prt", "b.prt"))

    pack = parse_pack(text, PACK)

    assert "ColCount=7" in text
    assert pack.project_count == 2
    assert pack.count == 2


def test_missing_files_section_is_empty_composition_with_explanation():
    """Нет `[Files]` — не отказ, но и не «пакет без проектов»: причина названа."""
    text = "\n".join([
        "[Form]", "Rect.L=1", "Rect.T=1", "Rect.R=2", "Rect.B=2",
        "[Common]", "Synchronize=1", "RelativePath=1", "IsRealTime=1",
        "TimeMash=1", "restartname=",
        "[Active]", "[TimeSync]",
    ]) + "\n"

    pack = parse_pack(text, PACK)

    assert pack.projects == ()
    assert pack.count is None
    assert pack.has_files_section is False
    assert any("[Files] отсутствует" in problem for problem in pack.problems)


@pytest.mark.parametrize("text", [
    "",
    "\n\n",
    "[Foo]\nbar=1\n",
    "\x00\x01\x02\x03",
    "<?xml version='1.0'?><project/>",
])
def test_file_without_any_pack_section_is_refused(text):
    """Ни одной из пяти секций — это не пакет, и пустой состав был бы ложью."""
    with pytest.raises(PackError) as exc:
        parse_pack(text, Path("Чужое.pak"))

    assert "Чужое.pak" in str(exc.value)
    assert "не .pak" in str(exc.value)
    assert "Files" in str(exc.value)


def test_unknown_section_is_reported():
    text = _pak_text(files=("a.prt",)).replace(
        "[Files]", "[NewSection]\nx=1\n[Files]")

    pack = parse_pack(text, PACK)

    assert any("NewSection" in problem for problem in pack.problems)


def test_relative_path_zero_is_reported():
    """`RelativePath=0`: раскрытие от каталога пакета для такого файла не проверено."""
    text = _pak_text(files=("a.prt",), relative_path=0)

    pack = parse_pack(text, PACK)

    assert pack.relative_path is False
    assert any("RelativePath" in problem for problem in pack.problems)


def test_restart_name_read():
    """У двух файлов поставки рестарт задан: `restart1` и `res_2`."""
    pack = parse_pack(_pak_text(files=("a.prt",), restart="restart1"), PACK)

    assert pack.restart_name == "restart1"


def test_extra_flag_rows_are_reported():
    text = _pak_text(files=("a.prt",), time_sync=["0=1", "7=0"])

    pack = parse_pack(text, PACK)

    assert any("лишние строки" in problem for problem in pack.problems)


def test_decode_pack_reads_utf8_with_bom():
    data = _pak_bytes("[Files]\nCount=0\n")

    assert decode_pack(data).startswith("[Files]")


def test_decode_pack_falls_back_to_cp1251_without_bom():
    """`kba_with_safety.pak` — CP1251 без BOM; кириллица обязана уцелеть."""
    data = _pak_bytes("[Files]\nCount=1\n0=Блоки управления.prt\n",
                      bom=False, encoding="cp1251")

    pack = parse_pack(decode_pack(data), PACK)

    assert [p.path for p in pack.projects] == ["Блоки управления.prt"]


def test_load_pack_reads_bytes_so_encoding_is_decided_per_file(tmp_path):
    """`load_pack` читает байты: BOM и CP1251 разбираются там же, где файл."""
    path = _write(tmp_path, _pak_text(files=("Схемы\\701.prt",)),
                  encoding="cp1251", bom=False)

    pack = load_pack(path)

    assert pack.projects[0].path == "Схемы\\701.prt"


def test_load_packs_walks_the_tree(tmp_path):
    nested = tmp_path / "Demo" / "Теплогидравлика"
    nested.mkdir(parents=True)
    _write(tmp_path / "Demo", _pak_text(files=("a.prt",)), name="Первый.pak")
    _write(nested, _pak_text(files=("b.prt",)), name="Второй.pak")

    packs = load_packs(tmp_path / "Demo")

    assert [p.path.name for p in packs] == ["Первый.pak", "Второй.pak"]


# ─── Сплошная проверка поставки ─────────────────────────────────────
# Медленная (обход 9p-каталога) и зависит от установленного SimInTech64,
# поэтому вынесена под маркер: `pytest -m distribution`.


def _distribution_packs():
    root = Path(DISTRIBUTION_ROOT) / "Demo"
    if not root.is_dir():
        pytest.skip(f"поставка не найдена: {root} (задайте SIMINTECH_DISTR)")
    return sorted(root.rglob("*.pak"))


@pytest.mark.distribution
def test_distribution_pack_count():
    """63 файла — столько их в поставке; счётчик поймает пропажу обхода."""
    assert len(_distribution_packs()) == DISTRIBUTION_PACKS


@pytest.mark.distribution
def test_distribution_encodings_are_62_utf8_and_1_cp1251():
    """Кодировки поставки: 62 файла UTF-8 с BOM, ровно один CP1251 без BOM.

    Это не «на всякий случай»: формулы «BOM есть всегда» и «BOM нет никогда»
    уже приводили к неверному разбору, а счётчик поймает смену поставки.
    """
    utf8 = cp1251 = 0
    for path in _distribution_packs():
        data = path.read_bytes()
        if data.startswith(b"\xef\xbb\xbf"):
            data[3:].decode("utf-8")  # бросит, если это не UTF-8
            utf8 += 1
        else:
            data.decode("cp1251")
            cp1251 += 1
    assert (utf8, cp1251) == (DISTRIBUTION_UTF8_BOM, DISTRIBUTION_CP1251)


@pytest.mark.distribution
def test_every_distribution_pack_parses_and_is_consistent():
    """Все 63 пакета разбираются, `Count` сходится, флаги — по числу проектов.

    Расхождений `Count` с числом записей в поставке нет ни в одном файле;
    если появятся, они должны быть названы здесь точным списком.
    """
    mismatched = []
    flag_shifted = []
    records = 0
    for path in _distribution_packs():
        pack = load_pack(path)
        records += pack.project_count
        if pack.count != pack.project_count:
            mismatched.append((path, pack.count, pack.project_count))
        numbers = [p.index for p in pack.projects]
        assert numbers == list(range(len(numbers))), path
        for flags in ([p.active for p in pack.projects],
                      [p.time_sync for p in pack.projects]):
            if len(flags) != pack.project_count or any(f is None for f in flags):
                flag_shifted.append((path, flags))
        assert all(p.path.lower().endswith(".prt") for p in pack.projects)

    assert mismatched == []
    assert flag_shifted == []
    assert records == DISTRIBUTION_RECORDS


@pytest.mark.distribution
def test_distribution_problems_are_only_the_two_absolute_paths():
    """Отклонение в поставке ровно одно: два абсолютных пути в одном файле."""
    offenders = {p.path.name: p.problems for p in
                 (load_pack(path) for path in _distribution_packs())
                 if p.problems}

    assert list(offenders) == [ABSOLUTE_PATHS_PACK]
    for problem in offenders[ABSOLUTE_PATHS_PACK]:
        assert "абсолютные пути" in problem


@pytest.mark.distribution
def test_distribution_restart_names_and_time_mash():
    """Значения, которые в поставке редки и потому легко теряются при разборе."""
    packs = [load_pack(path) for path in _distribution_packs()]

    restarts = sorted(p.restart_name for p in packs if p.restart_name)
    assert restarts == ["res_2", "restart1"]
    assert all(p.time_mash is not None for p in packs)
    assert sorted({p.time_mash for p in packs}) == [
        0.003, 0.005, 1.0, 2.0, 5.0, 20.0, 100.0]
    assert sum(1 for p in packs if p.relative_path is True) == DISTRIBUTION_PACKS
