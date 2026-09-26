"""Разбор результата пробы: маркеры, полный и оборванный результат."""

import os
import pathlib
import random
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest  # noqa: E402

from simintech_api.exceptions import (  # noqa: E402
    ScriptBridgeError,
    ScriptBridgeUnsafeStateError,
)
from simintech_api.script_probe import (  # noqa: E402
    BEGIN_MARKER,
    BRIDGE_WRITE_PROCEDURE,
    DECOY_DESCRIPTOR_NAME,
    END_MARKER,
    TARGET_TOKEN_HEX_DIGITS,
    bridge_descriptor_name,
    build_probe_script,
    decode_xprt_value,
    find_changed_script_record,
    leftover_of,
    new_target_token,
    parse_probe_result,
    parse_xprt_script_records,
    token_present_in,
)


def test_target_token_is_a_comment_of_ascii_without_forbidden_chars():
    """Метка проходит через выгрузку обычным текстом.

    Это проверка **выборки**: запрещённый знак она поймает, только если тот
    выпал за 32 знака. Доказательством контракта она быть не может — 32 выбора
    из 17 знаков дают `(16/17)**32 ≈ 14%` на то, что добавленный знак не
    выпадет ни разу (измерено: мутация «добавить `#` в алфавит» проходила
    в 9 прогонах из 10). Детерминированную гарантию даёт тест пула ниже.
    """
    token = new_target_token()
    assert token.startswith("//SCRIPT_BRIDGE_TARGET_")
    assert len(token.split("_")[-1]) == TARGET_TOKEN_HEX_DIGITS
    assert set(token.split("_")[-1]) <= set("0123456789abcdef"), (
        "знак вне hex-набора и вне списка запрещённых (например `g`) цикл ниже "
        "не поймает вовсе — эта строка ловит, но тоже вероятностно")
    assert all(32 <= ord(char) < 127 for char in token)
    for char in "\"'`# \t\r\n":
        assert char not in token, f"в метке недопустимый символ {char!r}"


def test_target_token_differs_between_calls():
    assert new_target_token() != new_target_token()


def test_target_token_consumes_the_injected_random_stream():
    """Источник случайности — параметр, и он расходуется.

    Равенство двух вызовов с одинаковым seed этого не доказывает: его
    выполняет и функция, возвращающая константу. А два вызова на одном и том
    же потоке обязаны дать разные метки — иначе параметр не используется.
    """
    rng = random.Random(1)
    assert new_target_token(rng) != new_target_token(rng)


class _AlphabetRecordingRng(random.Random):
    """Источник случайности, запоминающий алфавит, из которого шёл выбор."""

    def __init__(self):
        super().__init__(0)
        self.alphabets = []

    def choice(self, seq):
        self.alphabets.append("".join(seq))
        return super().choice(seq)


def test_target_token_alphabet_is_only_hex_for_any_source():
    """Контракт держится **пулом**, а не выборкой — и это единственная гарантия.

    Проверять готовую метку бессмысленно как доказательство: она случайна.
    Здесь проверяется сам алфавит, из которого шёл выбор, и от случая это уже
    не зависит: мутация алфавита краснеет **всегда**.

    Тест сцеплён со способом расхода источника (`choice`): если
    `new_target_token` переписать на `randrange`, он покраснеет на
    `assert rng.alphabets` — шумный отказ вместо тихого согласия, и это
    намеренный выбор в пользу шумного.
    """
    rng = _AlphabetRecordingRng()
    new_target_token(rng)
    assert rng.alphabets, "источник случайности не использован"
    alphabet = set("".join(rng.alphabets))
    extra = sorted(alphabet - set("0123456789abcdef"))
    missing = sorted(set("0123456789abcdef") - alphabet)
    assert not extra and not missing, (
        f"алфавит метки разошёлся с hex-набором: лишние {extra!r}, "
        f"недостающие {missing!r} — сужение алфавита ослабляет nonce "
        "(32 знака из двухсимвольного алфавита — 32 бита вместо 128)")


def test_parse_complete_result():
    text = f"{BEGIN_MARKER}\nстрока 1\nстрока 2\n{END_MARKER}\n"
    result = parse_probe_result(text)
    assert result.complete is True
    assert result.lines == ["строка 1", "строка 2"]


def test_parse_result_without_end_marker_is_incomplete():
    """Частичные строки не отдаются: неполный результат использовать нельзя."""
    text = f"{BEGIN_MARKER}\nстрока 1\n"
    result = parse_probe_result(text)
    assert result.complete is False
    assert result.lines == []


def test_parse_empty_file_is_incomplete():
    result = parse_probe_result("")
    assert result.complete is False
    assert result.lines == []


def test_parse_result_without_begin_marker_is_incomplete():
    result = parse_probe_result("мусор\nещё мусор\n")
    assert result.complete is False
    assert result.lines == []


def test_end_marker_before_begin_is_incomplete():
    """Конечный маркер раньше начального — полным результат не делает."""
    text = f"{END_MARKER}\nстрока\n{BEGIN_MARKER}\nхвост\n"
    result = parse_probe_result(text)
    assert result.complete is False
    assert result.lines == []


def test_marker_inside_data_does_not_make_result_complete():
    """Строка данных, совпавшая с маркером, не закрывает протокол.

    Раньше брался первый конечный маркер, поэтому оборванная проба выглядела
    полной, а хвост после ложного маркера отбрасывался молча.
    """
    text = f"{BEGIN_MARKER}\nobjects=7\n{END_MARKER}\nхвост\n{END_MARKER}\n"
    result = parse_probe_result(text)
    assert result.complete is False
    assert result.lines == []


def test_marker_twice_is_ambiguous_and_incomplete():
    """Две пары маркеров — границу протокола провести нельзя."""
    text = (f"{BEGIN_MARKER}\nпервые\n{END_MARKER}\n"
            f"{BEGIN_MARKER}\nвторые\n{END_MARKER}\n")
    result = parse_probe_result(text)
    assert result.complete is False


#: Метка, которой тесты помечают пробный скрипт. Формат — как у настоящей.
PROBE_TOKEN = "//SCRIPT_BRIDGE_TARGET_0011223344556677"


def test_build_wraps_body_with_markers_and_file():
    script = build_probe_script('writelnutf8(fid, "привет");',
                                r"C:\tmp\out.txt", PROBE_TOKEN)
    name = bridge_descriptor_name(PROBE_TOKEN)
    assert 'createfile("C:/tmp/out.txt", -1)' in script
    assert f'writelnutf8({name}, "{BEGIN_MARKER}")' in script
    assert f'writelnutf8({name}, "{END_MARKER}")' in script
    assert 'writelnutf8(fid, "привет");' in script
    order = (script.index(BEGIN_MARKER), script.index("привет"),
             script.index(END_MARKER))
    assert order == tuple(sorted(order))
    assert f"freeobject({name});" in script


def test_bridge_descriptor_name_comes_from_the_run_token():
    """Имя дескриптора моста порождается меткой запуска, а не берётся из кода.

    Имя — не константа и не «достаточно редкая строка»: оно целиком зависит от
    случайной части метки, а та проверена на отсутствие в проекте
    (`token_present_in`). Поэтому два запуска дают два разных имени, и чужой
    текст не может ни назвать имя дескриптора, ни присвоить его — отдельной
    области видимости у языка для этого нет (измерено 2026-09-24).
    """
    other_token = "//SCRIPT_BRIDGE_TARGET_ffeeddccbbaa9988"
    assert bridge_descriptor_name(PROBE_TOKEN) != bridge_descriptor_name(other_token)
    assert PROBE_TOKEN.rsplit("_", 1)[-1] in bridge_descriptor_name(PROBE_TOKEN)
    first = build_probe_script("", r"C:\tmp\out.txt", PROBE_TOKEN)
    second = build_probe_script("", r"C:\tmp\out.txt", other_token)
    assert f"var {bridge_descriptor_name(PROBE_TOKEN)}: integer;" in first
    assert f"var {bridge_descriptor_name(other_token)}: integer;" in second


def test_markers_and_closing_never_use_the_foreign_name():
    """Маркеры и `freeobject` пишутся только через дескриптор моста.

    Это страж мутации «вернуть мост на общее имя `fid`»: такая правка краснеет
    здесь, не дожидаясь живого стенда. На стенде она уже измерена — чужое
    присваивание `fid` уводит дескриптор моста, конечный маркер уходит в чужой
    освобождённый файл, и проба обрывается, оставив один начальный маркер.
    """
    script = build_probe_script('writelnutf8(fid, "тело");',
                                r"C:\tmp\out.txt", PROBE_TOKEN)
    critical = [line for line in script.splitlines()
                if BEGIN_MARKER in line or END_MARKER in line
                or "freeobject" in line]
    assert len(critical) == 3, f"ожидались два маркера и закрытие: {critical}"
    for line in critical:
        assert DECOY_DESCRIPTOR_NAME not in line, (
            f"маркер или закрытие идут через чужое имя: {line}")
        assert bridge_descriptor_name(PROBE_TOKEN) in line


def test_the_foreign_name_stays_declared_and_bound_to_the_bridge():
    """`fid` остаётся объявленным и связанным с дескриптором моста.

    Это условие работоспособности чужого кода, а не удобство: вендорская
    процедура присваивает `fid`, **не объявляя** имя. Убери имя — чужой скрипт
    перестанет компилироваться, расчёт молча не пойдёт, и проба не выполнится
    вовсе. Привязка к дескриптору моста заодно сохраняет тела, которые пишут
    результат через `fid`.
    """
    script = build_probe_script("", r"C:\tmp\out.txt", PROBE_TOKEN)
    name = bridge_descriptor_name(PROBE_TOKEN)
    assert f"var {DECOY_DESCRIPTOR_NAME}: integer;" in script
    assert f"{DECOY_DESCRIPTOR_NAME} = {name};" in script
    assert script.index(f"{DECOY_DESCRIPTOR_NAME} = {name};") < script.index(END_MARKER)


def test_safe_write_procedure_writes_to_the_bridge_descriptor():
    """`br_writeln` — путь записи, которого присваивание не касается.

    Телу он нужен после чужого вызова: приманка `fid` к тому моменту указывает
    на чужой (возможно, уже освобождённый) файл, и запись через неё обрывает
    скрипт.
    """
    script = build_probe_script("", r"C:\tmp\out.txt", PROBE_TOKEN)
    assert f"procedure {BRIDGE_WRITE_PROCEDURE}(s: string);" in script
    assert f"writelnutf8({bridge_descriptor_name(PROBE_TOKEN)}, s);" in script


def test_build_puts_token_on_first_line_before_the_body():
    """Метка идёт ПЕРВОЙ строкой, до исполняемого тела.

    Так она остаётся в скрипте, даже если тело не скомпилировалось: иначе
    опознать свою запись было бы нечем, и прежний скрипт не вернулся бы.
    """
    script = build_probe_script('writelnutf8(fid, "тело");',
                                r"C:\tmp\out.txt", PROBE_TOKEN)
    assert script.splitlines()[0] == PROBE_TOKEN
    assert script.index(PROBE_TOKEN) < script.index("if firststep then")


def test_build_uses_firststep_not_initialization():
    """Обход топологии — на первом шаге: порты субмоделей на инициализации
    могут быть ещё не установлены (сказано в демо поставки)."""
    script = build_probe_script("", r"C:\tmp\out.txt", PROBE_TOKEN)
    lines = script.splitlines()
    assert lines[0] == PROBE_TOKEN
    assert lines[1] == "if firststep then begin"
    assert "initialization" not in script


def test_build_rejects_quote_and_newline_in_path():
    """Путь подставляется в литерал встроенного языка — кавычка сломает скрипт."""
    with pytest.raises(ValueError):
        build_probe_script("", 'C:\\tmp\\bad"name.txt', PROBE_TOKEN)
    with pytest.raises(ValueError):
        build_probe_script("", "C:\\tmp\\bad\nname.txt", PROBE_TOKEN)


def test_build_translates_backslashes_of_result_path():
    """Обратных слэшей в литерале не остаётся: путь печатается прямыми.

    Разбирает ли встроенный язык `\\t` и `\\r` в строковом литерале как
    управляющие последовательности — **не измерено**. Если разбирает,
    `C:\\tmp\\result.txt` стал бы `C:<TAB>mp<CR>esult.txt`, `createfile` ушёл бы
    не туда, а проба отработала бы штатно — и отказ выглядел бы как обычный
    сбой скрипта («нет ровно одной пары маркеров»). Прямые слэши безопасны при
    **обоих** прочтениях: Windows их принимает, а экранировать в них нечего.
    """
    script = build_probe_script("", r"C:\tmp\result.txt", PROBE_TOKEN)
    assert 'createfile("C:/tmp/result.txt", -1)' in script
    assert "\\" not in script


def test_build_keeps_already_forward_slashes_without_doubling():
    """Путь, уже записанный прямыми слэшами, не получает двойных."""
    script = build_probe_script("", "C:/tmp/result.txt", PROBE_TOKEN)
    assert 'createfile("C:/tmp/result.txt", -1)' in script


FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "script_values"


def test_decode_xprt_value_decodes_real_value_without_backticks_or_codes():
    """Дословное значение из поставки: операторы < и > закодированы как #60/#62.

    Перевод строки остаётся `\\r\\n`: коды раскодируются в свои символы, и
    скрипт возвращается на место таким, каким был. Схлопывание в `\\n` было бы
    удобнее читать, но это уже правка чужого скрипта.

    Проверка переехала сюда с `read_page_script`: декодируется **та самая**
    запись, которую мост возвращает на место, и ошибка в разборе означала бы
    правку чужого скрипта — молча.
    """
    raw = (FIXTURES / "with_operators.txt").read_text(encoding="utf-8")
    assert decode_xprt_value(raw) == ("Line2.Visible = u < 0.5\r\n"
                                      "Line3.Visible = u > 0.5")


def test_decode_xprt_value_decodes_any_code_not_only_line_endings():
    """Коды — не только перевод строки и табуляция: любой #NN это chr(NN)."""
    assert decode_xprt_value("`a `#60` b`") == "a < b"
    assert decode_xprt_value("`x`#9`y`") == "x\ty"
    assert decode_xprt_value("`x`#13#10`y`") == "x\r\ny"


@pytest.mark.parametrize("raw, fragment", [
    ("`a`#1114112`b`", "вне диапазона Unicode"),
    ("`a`#55296`b`", "одиночный суррогат"),
    ("`a`#57343`b`", "одиночный суррогат"),
])
def test_decode_xprt_value_refuses_codes_that_give_no_symbol(raw, fragment):
    """Код без символа — отказ, хотя `leftover_of` запись считает покрытой.

    «Покрыта» и «разбирается» — разные вещи: первая говорит, что текст не
    теряется по краям, вторая — что из кода получается символ. Два вида кодов
    символа не дают: вне диапазона Unicode (`chr()` бросает `ValueError` прямо
    в разборе) и одиночный суррогат (`chr()` его принимает, а падает запись —
    сырым `UnicodeEncodeError` уже вне иерархии ошибок моста).
    """
    assert leftover_of(raw) == "", "предпосылка: остатка кодек не видит"
    with pytest.raises(ScriptBridgeError) as exc:
        decode_xprt_value(raw)
    assert fragment in str(exc.value)


def test_decode_xprt_value_keeps_literal_backtick_encoded_as_code():
    """Обратная кавычка внутри скрипта приходит кодом и не путается с обёрткой."""
    assert decode_xprt_value("`a`#96`b`") == "a`b"


@pytest.mark.distribution
def test_every_real_script_value_decodes_without_leftovers():
    """Сплошная проверка по поставке: разбор покрывает значение целиком.

    Единичный фрагмент доказывает мало; здесь перебираются все значения
    `<script>` во всех `.xprt` поставки. Непокрытый остаток означал бы, что
    часть скрипта при возврате потеряется.
    """
    import re as _re

    from simintech_api.catalog import decode_xprt

    root = pathlib.Path(os.environ.get("SIMINTECH_ROOT", "/mnt/c/SimInTech64")) / "Temp"
    if not root.is_dir():
        pytest.skip(f"нет каталога выгрузок поставки: {root}")
    checked = leftovers = 0
    for path in sorted(root.glob("*.xprt")):
        text = decode_xprt(path.read_bytes())
        for match in _re.finditer(r"<script>(.*?)</script>", text, _re.S):
            raw = match.group(1)
            if not raw.strip():
                continue
            checked += 1
            if leftover_of(raw):
                leftovers += 1
    assert checked > 100, (
        f"проверено всего {checked} скриптов — выборка подозрительно мала")
    assert leftovers == 0, f"{leftovers} значений разобраны не полностью"


#: Выгрузка из трёх страниц: главная с путём в имени, страница субмодели с
#: ПУСТЫМ именем, и страница-контейнер. Форма записи — как в поставке: значение
#: в обратных кавычках и кодах, пустой скрипт — без кавычек вовсе.
def _dump(pages):
    body = "".join(
        f"<page>\n <name>{name}</name>\n <script>{value}</script>\n"
        f" <visible>`1`</visible>\n</page>\n"
        for name, value in pages)
    return "<project>\n" + body + "</project>\n"


def test_parse_script_records_returns_raw_values_in_document_order():
    """Записи возвращаются **сырыми**: сравнение снимков идёт по тексту файла."""
    text = _dump([("`C:\\work\\model.prt`", "`a`#10`b`"),
                  ("", "`sentinel`"),
                  ("`Container`", "")])
    assert parse_xprt_script_records(text) == ["`a`#10`b`", "`sentinel`", ""]


def test_parse_script_records_accepts_empty_name_without_backticks():
    """`<name></name>` — не аномалия, а форма страницы субмодели (измерено).

    Прежний разбор требовал кавычек вокруг имени и такую запись пропускал —
    вместе с ней пропадала и страница.
    """
    assert parse_xprt_script_records(_dump([("", "`x`")])) == ["`x`"]


def test_parse_script_records_refuses_dump_with_unparsed_page():
    """Число записей обязано сойтись с числом страниц: пропуск — не «меньше».

    Разбор, молча пропустивший страницу, сдвинул бы нумерацию записей, и
    возврат положил бы чужой скрипт. Поэтому расхождение — отказ.
    """
    text = _dump([("`a`", "`x`")]) + "<page>\n <script>no name</script>\n</page>\n"
    with pytest.raises(ScriptBridgeError) as exc:
        parse_xprt_script_records(text)
    assert "страниц" in str(exc.value)


def test_parse_script_records_does_not_take_data_script_for_page_script():
    """Скрипт свойства внутри объекта — не скрипт страницы.

    У объектов в выгрузке есть `<data><script>` (скрипты свойств). Разбор ищет
    скрипт сразу за `<name>` страницы, поэтому чужой `<script>` в середину не
    попадает.
    """
    text = ("<project>\n<page>\n <name>`p`</name>\n <script>`page`</script>\n"
            " <object>\n  <data>\n   <script>`prop`</script>\n  </data>\n"
            " </object>\n</page>\n</project>\n")
    assert parse_xprt_script_records(text) == ["`page`"]


def test_parse_script_records_refuses_page_without_its_own_script():
    """Правило «`<script>` сразу за `</name>`» — не украшение, и оно проверяется.

    Форма синтетическая: в поставке страницы без собственного скрипта не
    встречается (0 из 1534 — у каждой ровно один страничный `<script>`, и он
    всегда идёт сразу за `</name>`). Но именно она отделяет верный разбор от
    ослабленного: если снять примыкание к `</name>`, разбор вернёт **скрипт
    свойства** под видом скрипта страницы, а самопроверка по числу записей этого
    не увидит — числа сойдутся. Возврат же чужого скрипта в текущую страницу и
    есть та порча, ради запрета которой всё делается.

    Измерено ревью: без этого теста ослабленные формы
    (`<name>.*?</name>.*?<script>`, `</name>.*?<script>`) проходят все тесты и
    на всех 1534 страницах поставки неотличимы от верного разбора.
    """
    text = ("<project>\n<page>\n <name>`p`</name>\n <object>\n  <data>\n"
            "   <script>`prop`</script>\n  </data>\n </object>\n</page>\n"
            "</project>\n")
    with pytest.raises(ScriptBridgeError) as exc:
        parse_xprt_script_records(text)
    assert "страниц" in str(exc.value)


def test_token_present_in_finds_token_in_any_record():
    records = ["`a`", "`//SCRIPT_BRIDGE_TARGET_deadbeef`", "`b`"]
    assert token_present_in(records, "SCRIPT_BRIDGE_TARGET_deadbeef")
    assert not token_present_in(records, "SCRIPT_BRIDGE_TARGET_00000000")


#: Матрица безопасности опознания цели. Во всех строках сравниваются СНИМКИ:
#: списки сырых скриптовых записей. Метка — та, что стоит в установленном
#: скрипте; «до нас её не было» — отдельное условие, а не украшение.
TOKEN = "//SCRIPT_BRIDGE_TARGET_aabbccdd"


def test_find_changed_script_record_accepts_single_changed_with_token():
    before = ["`main`", "`sub`"]
    after = ["`main`", f"`{TOKEN}`#10`probe`"]
    assert find_changed_script_record(before, after, TOKEN) == 1


@pytest.mark.parametrize("after, fragment", [
    (["`main`", "`sub`"], "ни одна"),                         # ноль изменившихся
    (["`a`", "`b`"], "больше одной"),                         # изменились обе
    (["`main`", "`changed but no token`"], "метки"),          # чужая запись
    (["`main`", "`sub`", "`лишняя`"], "число"),               # записей больше
])
def test_find_changed_script_record_refuses_anything_but_unique_token(
        after, fragment):
    """Всё, кроме «ровно одна изменившаяся и в ней метка», — отказ.

    Третий случай — тот, ради которого метка и существует: единственная
    изменившаяся запись **без** метки означает, что изменилась чужая страница, и
    взять её значит положить в текущую страницу чужой скрипт.
    """
    before = ["`main`", "`sub`"]
    with pytest.raises(ScriptBridgeUnsafeStateError) as exc:
        find_changed_script_record(before, after, TOKEN)
    assert fragment in str(exc.value)


def test_find_changed_script_record_refuses_token_that_was_already_there():
    """Метка, встречавшаяся ДО нас, ничего не доказывает.

    Это случай «предыдущий запуск оставил пробный скрипт» либо совпадение
    nonce. Метка в записи доказывает авторство, только если её не было в
    снимке до установки, — иначе «метка есть» превращается в поиск подстроки.
    """
    token = "//SCRIPT_BRIDGE_TARGET_aabbccdd"
    before = [f"`{token}`", "`sub`"]
    after = ["`main`", f"`{token}`#10`probe`"]
    with pytest.raises(ScriptBridgeUnsafeStateError) as exc:
        find_changed_script_record(before, after, token)
    assert "до установки" in str(exc.value)
