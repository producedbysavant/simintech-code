"""Тесты каталога свойств блоков (без COM)."""

import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest  # noqa: E402

from simintech_api.catalog import (  # noqa: E402
    BlockCatalog,
    catalog_coverage,
    merge_catalogs,
    build_catalog_from_xprt,
    clean_value,
    decode_xprt,
    load_default_catalog,
    parse_xprt_block_props,
    parse_xprt_readonly,
)

# ─── Фикстуры .xprt ───────────────────────────────────────────────

# Основной формат: параметры блока в <custom_props>, значения в бэктиках
XPRT_BACKTICK = """<?xml version="1.0" encoding="utf-8"?>
<project>
  <object>
    <name>`Gain1`</name>
    <class_name>`Усилитель`</class_name>
    <visual_props>
      <data><name>`Color`</name><value>`16777215`</value></data>
    </visual_props>
    <custom_props>
      <data><name>`a`</name><mode>`1`</mode><value>`2.5`</value></data>
    </custom_props>
  </object>
  <object>
    <name>`Sum1`</name>
    <class_name>`Сумматор`</class_name>
    <visual_props>
      <data><name>`Points`</name><value>`[(30 , 20)]`</value></data>
    </visual_props>
    <custom_props>
      <data><name>`a`</name><mode>`1`</mode><value>`[1 , -1]`</value></data>
    </custom_props>
  </object>
</project>
"""

# Тот же смысл, но без бэктиков — парсер должен быть терпимым
XPRT_PLAIN = """<project>
  <object>
    <name>Gain1</name>
    <class_name>Усилитель</class_name>
    <custom_props>
      <data><name>a</name><value>2.5</value></data>
    </custom_props>
  </object>
</project>
"""

# Параметры лежат в custom_props, а не в visual_props: оформление игнорируется
XPRT_COLOR_IS_NOT_PARAM = """<project>
  <object>
    <name>`Gain1`</name>
    <class_name>`Усилитель`</class_name>
    <visual_props>
      <data><name>`Color`</name><value>`16777215`</value></data>
      <data><name>`Points`</name><value>`[(30 , 20),(60 , 20)]`</value></data>
      <data><name>`LabelFont`</name><value>`Cambria`</value></data>
    </visual_props>
    <custom_props>
      <data><name>`a`</name><value>`1`</value></data>
    </custom_props>
  </object>
</project>
"""

# Графические объекты параметров не несут — в каталог не попадают
XPRT_WITH_DECOR = """<project>
  <object>
    <name>`Line1`</name>
    <class_name>`Line`</class_name>
    <visual_props>
      <data><name>`Points`</name><value>`[(0,0),(10,10)]`</value></data>
    </visual_props>
  </object>
  <object>
    <name>`Text1`</name>
    <class_name>`RotatedText`</class_name>
    <visual_props>
      <data><name>`Text`</name><value>`подпись`</value></data>
    </visual_props>
  </object>
</project>
"""

# Блок без custom_props — параметров восстановить нельзя
XPRT_NO_CUSTOM = """<project>
  <object>
    <name>`X`</name>
    <class_name>`Интегратор`</class_name>
    <visual_props>
      <data><name>`Color`</name><value>`1`</value></data>
    </visual_props>
  </object>
</project>
"""

# Вычисляемый параметр (mode 0) не задаётся
XPRT_WITH_COMPUTED = """<project>
  <object>
    <name>`Gain1`</name>
    <class_name>`Усилитель`</class_name>
    <custom_props>
      <data><name>`a`</name><mode>`1`</mode><value>`1`</value></data>
      <data><name>`formula_visible`</name><mode>`0`</mode><value>`0`</value></data>
    </custom_props>
  </object>
</project>
"""

# Старая конвенция кавычек: значения обёрнуты в одинарные кавычки, а не в
# бэктики. Встречается и в поставляемых образцах, и в файлах 2022 года.
XPRT_SINGLE_QUOTES = """<project>
  <object>
    <name>'Gain1'</name>
    <class_name>'Усилитель'</class_name>
    <custom_props>
      <data><name>'a'</name><mode>'1'</mode><value>'2.5'</value></data>
      <data><name>'formula_visible'</name><mode>'0'</mode><value>'0'</value></data>
    </custom_props>
  </object>
</project>
"""

# Старый формат нумерует элементы контейнера: <object_0>, <data_1>, ... Раньше
# такие файлы разбирались в ноль классов — молча, неотличимо от пустой модели.
XPRT_NUMBERED = """<project>
  <object_0>
    <name>'Gain1'</name>
    <class_name>'Усилитель'</class_name>
    <custom_props>
      <data_0><name>'a'</name><mode>'1'</mode><value>'3'</value></data_0>
      <data_1><name>'formula_visible'</name><mode>'0'</mode><value>'0'</value></data_1>
    </custom_props>
  </object_0>
</project>
"""


# ─── Разбор .xprt ─────────────────────────────────────────────────

def test_clean_value_strips_backticks():
    assert clean_value("`2.5`") == "2.5"
    assert clean_value("  `abc`  ") == "abc"
    assert clean_value(None) == ""
    assert clean_value("") == ""


def test_parse_backtick_format():
    """Основной формат .xprt: параметры в <custom_props>, значения в бэктиках."""
    parsed = parse_xprt_block_props(XPRT_BACKTICK)

    assert set(parsed) == {"Усилитель", "Сумматор"}
    assert parsed["Усилитель"]["a"] == "2.5"
    assert parsed["Сумматор"]["a"] == "[1 , -1]"


def test_parse_plain_format():
    """Формат без бэктиков разбирается тем же кодом."""
    parsed = parse_xprt_block_props(XPRT_PLAIN)

    assert parsed["Усилитель"]["a"] == "2.5"


def test_parse_ignores_visual_props():
    """Оформление из <visual_props> в параметры не попадает.

    Это ключевое различие: Color/Points/LabelFont лежат в <visual_props>
    и параметрами расчёта не являются.
    """
    parsed = parse_xprt_block_props(XPRT_COLOR_IS_NOT_PARAM)

    props = parsed["Усилитель"]
    assert props == {"a": "1"}
    for graphical in ("Color", "Points", "LabelFont"):
        assert graphical not in props


def test_parse_skips_decor_classes():
    """Графические объекты в каталог не попадают."""
    parsed = parse_xprt_block_props(XPRT_WITH_DECOR)

    assert parsed == {}


def test_parse_skips_objects_without_custom_props():
    """Без <custom_props> параметров нет — блок пропускается."""
    assert parse_xprt_block_props(XPRT_NO_CUSTOM) == {}


def test_parse_readonly_marks_computed_params():
    """mode 0 — вычисляемый параметр, mode 1 — задаваемый."""
    readonly = parse_xprt_readonly(XPRT_WITH_COMPUTED)

    assert readonly["Усилитель"] == ["formula_visible"]
    assert "a" not in readonly["Усилитель"]


def test_clean_value_strips_single_quotes():
    """Одинарные кавычки снимаются так же, как бэктики."""
    assert clean_value("'2.5'") == "2.5"
    assert clean_value("  'abc'  ") == "abc"


def test_clean_value_keeps_inner_apostrophe():
    """Внутренний апостроф не трогается — снимаются только края."""
    assert clean_value("`don't`") == "don't"
    assert clean_value("'don't'") == "don't"


def test_parse_single_quote_format():
    """Файл с одинарными кавычками разбирается без кавычек в именах.

    Раньше снимались только бэктики, и имя выходило как ``'a'`` — то есть
    каталог, собранный из такого файла, отвергал правильное имя параметра.
    """
    parsed = parse_xprt_block_props(XPRT_SINGLE_QUOTES)

    assert set(parsed) == {"Усилитель"}
    assert parsed["Усилитель"] == {"a": "2.5", "formula_visible": "0"}


def test_parse_numbered_elements():
    """Старый формат с <object_0>/<data_0> разбирается, а не даёт ноль классов."""
    parsed = parse_xprt_block_props(XPRT_NUMBERED)

    assert set(parsed) == {"Усилитель"}
    assert parsed["Усилитель"]["a"] == "3"


def test_computed_param_in_single_quotes_is_marked():
    """`mode` в одинарных кавычках распознаётся как вычисляемый.

    Иначе вычисляемые параметры попали бы в каталог задаваемыми, а запись в них
    COM принимает и молча игнорирует — отказ без ошибки.
    """
    assert parse_xprt_readonly(XPRT_SINGLE_QUOTES)["Усилитель"] == ["formula_visible"]


def test_computed_param_in_numbered_format_is_marked():
    assert parse_xprt_readonly(XPRT_NUMBERED)["Усилитель"] == ["formula_visible"]


def test_parse_empty_text():
    assert parse_xprt_block_props("") == {}
    assert parse_xprt_block_props("не xml вовсе") == {}
    assert parse_xprt_readonly("") == {}


def test_decode_xprt_handles_utf8_bom():
    """SimInTech пишет .xprt в UTF-8 с BOM, а не в cp1251.

    Чтение как cp1251 превращает русские имена классов в мусор — молча, без
    ошибки. Именно на этом ломалась генерация каталога.
    """
    text = ('<?xml version="1.0" encoding="utf-8"?>'
            "<class_name>`Усилитель`</class_name>")
    raw = text.encode("utf-8-sig")

    assert decode_xprt(raw) == text
    assert "Усилитель" in decode_xprt(raw)


def test_decode_xprt_falls_back_to_cp1251():
    """Старые версии с cp1251 читаются запасным путём."""
    haystack = "выдуманный текст, не UTF-8"
    raw = haystack.encode("cp1251") + b"\xff\xfe\xfd"

    assert "выдуманный" in decode_xprt(raw)


def test_decode_xprt_refuses_corrupted_bom_file():
    """BOM обязывает: испорченный байт — ошибка, а не mojibake.

    Запасной cp1251 декодирует любые байты, поэтому порча файла с BOM раньше
    проходила молча: «Усилитель» превращался в «РЈСЃРёР»РёС‚РµР»СЊ», и отличить
    такой мусор от настоящих имён было нельзя — а каталог, собранный из него,
    выглядел пустым, но исправным.
    """
    raw = ('<?xml version="1.0" encoding="utf-8"?>'
           "<class_name>`Усилитель`</class_name>").encode("utf-8-sig")
    broken = raw[:-1] + b"\xff"

    with pytest.raises(UnicodeDecodeError):
        decode_xprt(broken)


# ─── BlockCatalog ─────────────────────────────────────────────────

def test_catalog_roundtrip(tmp_path):
    """Сохранение и загрузка не теряют данные."""
    original = BlockCatalog(
        classes={"Усилитель": {"a": "1", "Name": ""}},
        meta={"source": "test"},
    )
    path = tmp_path / "catalog.json"
    original.save(path)

    loaded = BlockCatalog.load(path)

    assert loaded.classes() == ["Усилитель"]
    assert loaded.props_for("Усилитель") == ["Name", "a"]
    assert loaded.defaults_for("Усилитель") == {"a": "1", "Name": ""}
    assert loaded.meta["source"] == "test"


def test_catalog_load_missing_file_is_empty(tmp_path):
    """Отсутствующий файл — пустой каталог, а не исключение."""
    catalog = BlockCatalog.load(tmp_path / "нет.json")

    assert len(catalog) == 0
    assert catalog.props_for("Усилитель") == ["Name"]


def test_catalog_props_for_unknown_class_returns_common():
    """Для неизвестного класса доступны только общие свойства."""
    catalog = BlockCatalog(classes={"Усилитель": {"a": "1"}})

    assert catalog.has("Усилитель") is True
    assert catalog.has("НетТакого") is False
    assert catalog.props_for("НетТакого") == ["Name"]


def test_catalog_save_is_utf8_json(tmp_path):
    """Каталог пишется читаемым UTF-8 (русские имена классов)."""
    catalog = BlockCatalog(classes={"Константа": {"y0": "0"}})
    path = catalog.save(tmp_path / "c.json")

    raw = json.loads(path.read_text(encoding="utf-8"))

    assert "Константа" in raw["classes"]
    assert path.read_text(encoding="utf-8").count("\\u") == 0


# ─── Конвейер генерации (поддельный COM) ──────────────────────────

def test_generate_catalog_pipeline(tmp_path, monkeypatch):
    """Создание блоков → .xprt → разбор → каталог.

    Клиент и проект поддельные: проверяется логика обхода классов и разбора
    XML, а не COM. Реальный прогон возможен только на Windows.
    """
    import simintech_api.core.project as project_module
    from simintech_api.catalog import generate_catalog

    source_xprt = tmp_path / "source.xprt"
    # Как настоящий SaveProjectXML: UTF-8 с BOM (в фикстуре объявлено utf-8).
    source_xprt.write_text(XPRT_BACKTICK, encoding="utf-8-sig")

    created = []

    class FakeBlock:
        def __init__(self, class_name):
            self.class_name = class_name

        def set_name(self, name):
            created.append((self.class_name, name))
            return self

    class FakePage:
        def create_block(self, class_name, x, y):
            return FakeBlock(class_name)

    class FakeProject:
        id = 1

        def get_main_page(self):
            return FakePage()

        def save_xml(self, path):
            pathlib.Path(path).write_text(
                source_xprt.read_text(encoding="utf-8-sig"),
                encoding="utf-8-sig")

        def close(self):
            pass

    monkeypatch.setattr(
        project_module.Project, "new",
        classmethod(lambda cls, client: FakeProject()),
    )

    catalog = generate_catalog(client=object(),
                               classes=["Усилитель", "Сумматор"])

    assert created, "блоки не создавались"
    assert catalog.has("Усилитель")
    assert "a" in catalog.props_for("Усилитель")
    assert catalog.meta["source"] == "generated"
    assert catalog.meta["failed"] == []


def test_generate_catalog_records_failures(tmp_path, monkeypatch):
    """Класс, который не удалось создать, попадает в meta['failed']."""
    import simintech_api.core.project as project_module
    from simintech_api.catalog import generate_catalog

    source_xprt = tmp_path / "source.xprt"
    # Как настоящий SaveProjectXML: UTF-8 с BOM (в фикстуре объявлено utf-8).
    source_xprt.write_text(XPRT_BACKTICK, encoding="utf-8-sig")

    class FakeBlock:
        def set_name(self, name):
            return self

    class FakePage:
        def create_block(self, class_name, x, y):
            if class_name == "Плохой":
                raise RuntimeError("CreateBlock не сработал")
            return FakeBlock()

    class FakeProject:
        id = 1

        def get_main_page(self):
            return FakePage()

        def save_xml(self, path):
            pathlib.Path(path).write_text(
                source_xprt.read_text(encoding="utf-8-sig"),
                encoding="utf-8-sig")

        def close(self):
            pass

    monkeypatch.setattr(
        project_module.Project, "new",
        classmethod(lambda cls, client: FakeProject()),
    )

    catalog = generate_catalog(client=object(),
                               classes=["Усилитель", "Плохой"])

    assert catalog.meta["failed"] == ["Плохой"]


# ─── Засеянный каталог ────────────────────────────────────────────

def test_default_catalog_loads_generated_data():
    """Каталог читается и содержит классы, сгенерированные из SimInTech."""
    catalog = load_default_catalog(reload=True)

    assert len(catalog) > 0
    for class_name in ("Константа", "Усилитель", "Сумматор", "Интегратор"):
        assert catalog.has(class_name), f"нет класса {class_name}"


def test_default_catalog_uses_real_property_names():
    """Имена параметров — фактические, а не читаемые из docs/ или примеров.

    Проверка-ограничитель на проверенные на реальном SimInTech данные
    (SimInTech64, 2026-09-10): у «Константы» параметр `a`, а НЕ `y0`;
    у «Сумматора» только `a`, а `xn` не существует. Запись в несуществующее
    имя не даёт ошибки, поэтому такая ошибка в каталоге была бы молчаливой.
    """
    catalog = load_default_catalog(reload=True)
    invented = {"value", "signs", "numInputs", "reset"}

    all_props = set()
    for class_name in catalog.classes():
        all_props.update(catalog.props_for(class_name))

    assert not (all_props & invented), (
        f"в каталоге выдуманные имена: {all_props & invented}"
    )
    assert "a" in catalog.props_for("Константа")
    assert "y0" not in catalog.props_for("Константа")
    assert "a" in catalog.props_for("Усилитель")
    assert "xn" not in catalog.props_for("Сумматор")


def test_default_catalog_is_generated_not_handwritten():
    """Каталог помечен как сгенерированный из реального SimInTech."""
    catalog = load_default_catalog(reload=True)

    assert catalog.meta.get("source") == "generated"
    # «failed» — записи, которые CreateBlock не создал. Список целей берётся из
    # индекса библиотек `.csl`, а он содержит и устаревшие записи, которые
    # среда отвергает (например, с пропавшим файлом набора параметров), поэтому
    # пустым он быть не обязан. Проверяем не пустоту, а согласованность:
    # отвергнутая запись не должна оказаться в каталоге.
    failed = catalog.meta.get("failed") or []
    assert isinstance(failed, list)
    assert not (set(failed) & set(catalog.classes()))


def test_default_catalog_records_computed_params():
    """Вычисляемые параметры (mode 0) отмечены как readonly."""
    catalog = load_default_catalog(reload=True)

    assert catalog.is_readonly("Усилитель", "formula_visible") is True
    assert catalog.is_readonly("Усилитель", "a") is False
    assert "formula_visible" in catalog.readonly_for("Усилитель")


# ─── Сборка каталога из выгрузки (без COM) ────────────────────────

def test_build_catalog_from_xprt_keeps_all_classes():
    """Без списка целей в каталог попадают все классы выгрузки."""
    catalog = build_catalog_from_xprt(XPRT_BACKTICK)

    assert set(catalog.classes()) == {"Сумматор", "Усилитель"}
    assert "a" in catalog.props_for("Усилитель")


def test_build_catalog_from_xprt_filters_targets():
    """Со списком целей остаются только запрошенные классы.

    В выгрузку попадает и оформление, поэтому «всё подряд» каталогом быть не
    может: проверка имён должна знать про блоки, а не про линии и подписи.
    """
    catalog = build_catalog_from_xprt(XPRT_BACKTICK, targets=["Усилитель"])

    assert set(catalog.classes()) == {"Усилитель"}


def test_build_catalog_from_xprt_normalizes_target_names():
    """Имя записи с хвостовым пробелом не теряет класс.

    В индексе `.csl` встречаются записи с пробелом в конце («Миландр - MILS -
    Инициazation МКИО »), а разбор выгрузки имя обрезает. Пока цели сверялись
    как есть, такие классы молча выпадали из каталога — среда их создаёт, а
    проверки имён у них нет. На живом SimInTech64 так терялось 14 классов.
    """
    catalog = build_catalog_from_xprt(XPRT_BACKTICK,
                                      targets=["Усилитель ", " Сумматор"])

    assert set(catalog.classes()) == {"Усилитель", "Сумматор"}
    assert catalog.meta["requested"] == ["Сумматор", "Усилитель"]


def test_build_catalog_from_xprt_normalizes_failed_names():
    """Провалы записываются так же нормализованно — иначе счётчики расходятся."""
    catalog = build_catalog_from_xprt(XPRT_PLAIN, failed=["Класс "])

    assert catalog.meta["failed"] == ["Класс"]


def test_build_catalog_from_xprt_carries_readonly():
    catalog = build_catalog_from_xprt(XPRT_WITH_COMPUTED)

    assert catalog.readonly_for("Усилитель") == ["formula_visible"]
    assert catalog.is_readonly("Усилитель", "formula_visible") is True
    assert catalog.is_readonly("Усилитель", "a") is False


def test_build_catalog_from_xprt_remembers_failed():
    catalog = build_catalog_from_xprt(XPRT_PLAIN, failed=["НетТакогоКласса"])

    assert catalog.meta["failed"] == ["НетТакогоКласса"]


def test_build_catalog_from_xprt_drops_huge_defaults():
    """Огромные значения по умолчанию в каталог не тянем.

    У антенных решёток значение — матрица в сотни чисел; каталогу нужны имена
    параметров, а не их значения.
    """
    long_value = "[" + ", ".join("1111" for _ in range(50)) + "]"
    xml = ("<project><object><class_name>`Класс`</class_name><custom_props>"
           f"<data><name>`big`</name><value>`{long_value}`</value></data>"
           "<data><name>`small`</name><value>`1`</value></data>"
           "</custom_props></object></project>")

    props = build_catalog_from_xprt(xml).defaults_for("Класс")

    assert props["big"] == ""
    assert props["small"] == "1"


def test_merge_catalogs_unions_classes():
    """Слияние объединяет классы: за один прогон охватить всё не выходит."""
    first = BlockCatalog(classes={"А": {"p": "1"}}, readonly={"А": ["r"]},
                         meta={"source": "generated", "requested": ["А"],
                               "failed": []})
    second = BlockCatalog(classes={"Б": {"q": "2"}},
                          meta={"source": "generated", "requested": ["Б"],
                                "failed": ["В"]})

    merged = merge_catalogs([first, second])

    assert set(merged.classes()) == {"А", "Б"}
    assert merged.readonly_for("А") == ["r"]
    assert merged.meta["failed"] == ["В"]


def test_merge_catalogs_keeps_params_of_same_class():
    """Параметры класса, найденного в обеих выгрузках, не теряются."""
    first = BlockCatalog(classes={"А": {"p": "1"}})
    second = BlockCatalog(classes={"А": {"q": "2"}})

    merged = merge_catalogs([first, second])

    assert merged.defaults_for("А") == {"p": "1", "q": "2"}


# ─── Покрытие: доля классов под проверкой имён ────────────────────

def _csl(*strings: str) -> bytes:
    """Синтетический `.csl`: строки UTF-16LE вперемешку с двоичным мусором."""
    pad = b"\x01\x02\x03\x04\x00\x00\x00\x00"
    out = bytearray(pad)
    for s in strings:
        out += pad
        out += s.encode("utf-16-le")
    return bytes(out)


def _distribution(tmp_path, libraries=("Loaded.csl",), with_profile=True):
    """Поставка в миниатюре: библиотеки, наборы параметров и профиль."""
    for name in libraries:
        (tmp_path / name).write_bytes(
            _csl(f"Блок {name[0]}", f"{name[0].lower()}.ps"))
    ps_dir = tmp_path / "ParamSet_mvtu"
    ps_dir.mkdir(exist_ok=True)
    for name in libraries:
        (ps_dir / f"{name[0].lower()}.ps").write_bytes(b"\x00" * 8)
    if not with_profile:
        return None
    profile = tmp_path / "base.xml"
    profile.write_text(
        "<profile>" + "".join(f"<lib>{n}</lib>" for n in libraries)
        + "</profile>", encoding="utf-8")
    return profile


def test_coverage_counts_classes_with_checked_names(tmp_path):
    """Покрытие — доля классов профиля, для которых имена есть в каталоге.

    Это свойство защиты, а не отчётная цифра: для класса вне каталога
    `_check_params` уходит в ветку «класса нет» и пропускает запись.
    """
    profile = _distribution(tmp_path, libraries=("Loaded.csl", "Skipped.csl"))
    catalog = BlockCatalog(classes={"Блок L": {"a": "1"}, "Вне профиля": {}})

    report = catalog_coverage(catalog, tmp_path, profile)

    assert report["classes_in_profile"] == 2
    assert report["checked_classes"] == 1
    assert report["fraction"] == 0.5
    assert report["not_in_catalog"] == ["Блок S"]
    assert report["beyond_profile"] == ["Вне профиля"]
    assert report["libraries_in_profile"] == 2


def test_coverage_without_profile_counts_every_library(tmp_path):
    """Без профиля знаменатель — все библиотеки на диске (их и грузит среда).

    Числа берутся из индекса, а не из каталога: иначе доля была бы всегда
    100% — каталог сравнивался бы сам с собой.
    """
    _distribution(tmp_path, with_profile=False)
    catalog = BlockCatalog(classes={"Блок L": {"a": "1"}})

    report = catalog_coverage(catalog, tmp_path, None)

    assert report["libraries_in_profile"] is None
    assert report["classes_in_profile"] == 1
    assert report["checked_classes"] == 1
    assert report["fraction"] == 1.0
    assert report["records_without_paramset"] == 0


def test_coverage_of_empty_distribution_is_zero_not_error(tmp_path):
    """Пустая поставка даёт 0.0, а не деление на ноль."""
    report = catalog_coverage(BlockCatalog(classes={"А": {}}), tmp_path, None)

    assert report["classes_in_profile"] == 0
    assert report["fraction"] == 0.0
