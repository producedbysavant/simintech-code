"""Тесты разбора базы сигналов SimInTech (без COM)."""

import os
import sys
import textwrap

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest  # noqa: E402

from simintech_api.sdb import (  # noqa: E402
    SignalDatabase,
    export_db_via_macro,
)

# Реальный формат выгрузки: значения обёрнуты в бэктики
SDB_XML = textwrap.dedent("""\
    <?xml version="1.0" encoding="utf-8"?>
    <root>
      <database>
        <category>
          <name>`Управление`</name>
          <nametemplate>`%s`</nametemplate>
          <group>
            <name>`Регулятор`</name>
            <signals>
              <data>
                <name>`Kp`</name>
                <caption>`Пропорциональный коэффициент`</caption>
                <type>`0`</type>
                <mode>`1`</mode>
                <value>`1.5`</value>
              </data>
              <data>
                <name>`Ki`</name>
                <caption>`Интегральный коэффициент`</caption>
                <type>`0`</type>
                <mode>`1`</mode>
                <value>`0.5`</value>
              </data>
            </signals>
          </group>
        </category>
      </database>
    </root>
""")


# Та же структура, но значения в одинарных кавычках: так выглядят поставляемые
# каталоги оборудования. Раньше такой файл не разбирался вовсе — `int('0')`
# получал строку вместе с кавычками и падал.
SDB_XML_SINGLE_QUOTES = textwrap.dedent("""\
    <?xml version="1.0" encoding="utf-8"?>
    <root>
      <database>
        <category>
          <name>'Оборудование'</name>
          <nametemplate>'%s'</nametemplate>
          <group>
            <name>'Насос'</name>
            <signals>
              <data>
                <name>'wn'</name>
                <caption>'Номинальная скорость'</caption>
                <type>'0'</type>
                <mode>'1'</mode>
                <value>'3000'</value>
              </data>
            </signals>
          </group>
        </category>
      </database>
    </root>
""")


def _write(tmp_path):
    path = tmp_path / "signals.xml"
    path.write_text(SDB_XML, encoding="utf-8")
    return path


# Структура снята с поставляемого каталога `bin/DataBase/Catalog/pumps.xml`:
# шаблон лежит в категории, рядом с `<nametemplate>`, и группа повторяет его
# имена и значения.
SDB_XML_WITH_TEMPLATE = textwrap.dedent("""\
    <?xml version="1.0" encoding="utf-8"?>
    <Header>
    <database>
     <category>
      <name>'HS - Насос'</name>
      <nametemplate></nametemplate>
      <signalstemplate>
       <data>
        <name>'wn'</name>
        <caption>'Номинальная частота'</caption>
        <type>'0'</type>
        <mode>'1'</mode>
        <value>'12.3333333333333'</value>
        <textvalue>'740/60'</textvalue>
        <fconstant>'1'</fconstant>
        <script></script>
       </data>
       <data>
        <name>'Qnom'</name>
        <caption>'Номинальный расход'</caption>
        <type>'0'</type>
        <mode>'1'</mode>
        <value>'1000'</value>
        <textvalue></textvalue>
        <fconstant>'1'</fconstant>
        <script></script>
       </data>
      </signalstemplate>
      <group>
       <name>'Насос1'</name>
       <signals>
        <data>
         <name>'wn'</name>
         <caption>'Номинальная частота'</caption>
         <type>'0'</type>
         <mode>'1'</mode>
         <value>'12.3333333333333'</value>
        </data>
        <data>
         <name>'Qnom'</name>
         <caption>'Номинальный расход'</caption>
         <type>'0'</type>
         <mode>'1'</mode>
         <value>'1000'</value>
        </data>
       </signals>
      </group>
     </category>
    </database>
    </Header>
""")


def test_from_xml_loads_categories_and_signals(tmp_path):
    db = SignalDatabase.from_xml(_write(tmp_path))

    assert db.is_loaded is True
    assert [c["name"] for c in db.list_categories()] == ["Управление"]


def test_full_signal_name_is_group_underscore_name(tmp_path):
    """Полное имя сигнала — <группа>_<сигнал>, как его адресует SimInTech."""
    info = SignalDatabase.from_xml(_write(tmp_path)).get_signal_info("Регулятор_Kp")

    assert info is not None
    assert info["name"] == "Kp"
    assert info["group"] == "Регулятор"


def test_find_signal_by_pattern(tmp_path):
    found = SignalDatabase.from_xml(_write(tmp_path)).find_signal("K*")

    assert sorted(f["name"] for f in found) == ["Ki", "Kp"]


def test_signals_are_indexed_by_composite_key(tmp_path):
    """Составной ключ <категория>.<группа>.<имя> тоже в индексе."""
    info = SignalDatabase.from_xml(_write(tmp_path)).get_signal_info(
        "Управление.Регулятор.Kp")

    assert info is not None
    assert info["name"] == "Kp"


def test_signal_template_is_not_a_signal(tmp_path):
    """`<signalstemplate>` — прототип категории, а не её сигналы.

    В поставке каждый сигнал группы повторяет шаблон (то же имя, то же
    значение), поэтому разбор шаблона как сигналов удвоил бы счёт и добавил бы
    записи, которых в базе нет.
    """
    path = tmp_path / "signals.xml"
    path.write_text(SDB_XML_WITH_TEMPLATE, encoding="utf-8")

    db = SignalDatabase.from_xml(path)

    # В группе два сигнала; шаблон описывает те же два и в счёт не идёт.
    assert [c["signal_count"] for c in db.list_categories()] == [2]
    assert [c["template_signal_count"] for c in db.list_categories()] == [2]
    assert len(db.list_signals()) == 2
    assert [s["name"] for s in db.find_signal("*")] == ["wn", "Qnom"]


def test_category_template_exposes_prototype(tmp_path):
    """Шаблон доступен отдельно — с именами, значениями и типом."""
    path = tmp_path / "signals.xml"
    path.write_text(SDB_XML_WITH_TEMPLATE, encoding="utf-8")

    db = SignalDatabase.from_xml(path)

    assert db.category_template("HS - Насос") == [
        {"name": "wn", "caption": "Номинальная частота", "type": 0, "mode": 1,
         "value": "12.3333333333333"},
        {"name": "Qnom", "caption": "Номинальный расход", "type": 0, "mode": 1,
         "value": "1000"},
    ]
    assert db.category_template("Нет такой") == []


def test_category_without_template_parses(tmp_path):
    """Отсутствие `<signalstemplate>` — обычное состояние, а не ошибка."""
    db = SignalDatabase.from_xml(_write(tmp_path))

    assert [c["template_signal_count"] for c in db.list_categories()] == [0]
    assert db.category_template("Управление") == []


#: Каталоги оборудования поставки — по ним проверяется разбор на настоящих
#: файлах. Рукописная фикстура один раз уже скрыла падение `sdb.py`, поэтому
#: счёт сверяется там, где поставка есть. Каталог можно задать переменной
#: `SIMINTECH_BIN`; без него проверка пропускается (в CI поставки нет).
CATALOG_DIR = os.path.join(
    os.environ.get("SIMINTECH_BIN", "/mnt/c/SimInTech64/bin"),
    "DataBase", "Catalog")


@pytest.mark.parametrize("name, groups, signals, template", [
    ("pumps.xml", 3, 54, 18),
    ("valves.xml", 3, 15, 5),
])
def test_real_distribution_catalog(name, groups, signals, template):
    """Числа этих файлов посчитаны по байтам поставки, а не по документации."""
    path = os.path.join(CATALOG_DIR, name)
    if not os.path.exists(path):
        pytest.skip(f"поставки нет: {path}")

    db = SignalDatabase.from_xml(path)
    cats = db.list_categories()

    assert len(cats) == 1
    assert cats[0]["group_count"] == groups
    assert cats[0]["signal_count"] == signals
    assert cats[0]["template_signal_count"] == template
    # Ни одно имя шаблона не теряется: все они есть среди сигналов групп.
    names = {s["name"] for s in db.list_signals()}
    assert {s["name"] for s in db.category_template(cats[0]["name"])} <= names


def test_single_quotes_are_stripped(tmp_path):
    """Файл с одинарными кавычками разбирается, а не падает на `int('0')`.

    Такая конвенция есть в поставляемых каталогах оборудования; раньше разбор
    останавливался на первом же сигнале, и вместо базы получалось исключение.
    """
    path = tmp_path / "signals.xml"
    path.write_text(SDB_XML_SINGLE_QUOTES, encoding="utf-8")

    info = SignalDatabase.from_xml(path).get_signal_info("Насос_wn")

    assert info is not None
    assert info["name"] == "wn"
    assert info["caption"] == "Номинальная скорость"
    assert info["type"] == 0


def test_non_numeric_type_does_not_break_parsing(tmp_path):
    """Мусор в служебном поле не роняет разбор целого файла."""
    path = tmp_path / "signals.xml"
    path.write_text(SDB_XML.replace("<type>`0`</type>", "<type>`n/a`</type>"),
                    encoding="utf-8")

    info = SignalDatabase.from_xml(path).get_signal_info("Регулятор_Kp")

    assert info is not None
    assert info["type"] == 0


# ─── Защита от XXE ────────────────────────────────────────────────

# «Мяч» из сущностей: без защиты разворачивается в гигабайты
BILLION_LAUGHS = """<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
]>
<root>
  <database>
    <category>
      <name>&lol3;</name>
      <group><name>`G`</name><signals/></group>
    </category>
  </database>
</root>
"""

# Классический XXE: попытка прочитать локальный файл через сущность
XXE_FILE_READ = """<?xml version="1.0"?>
<!DOCTYPE foo [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<root><database><category><name>&xxe;</name></category></database></root>
"""


def test_dtd_is_rejected(tmp_path):
    """Документ с DOCTYPE не должен разбираться: это вектор XXE."""
    path = tmp_path / "evil.xml"
    path.write_text(BILLION_LAUGHS, encoding="utf-8")

    with pytest.raises(Exception):
        SignalDatabase.from_xml(path)


def test_external_entity_is_rejected(tmp_path):
    """Внешняя сущность (чтение файла) не должна раскрываться."""
    path = tmp_path / "xxe.xml"
    path.write_text(XXE_FILE_READ, encoding="utf-8")

    with pytest.raises(Exception):
        SignalDatabase.from_xml(path)


def test_normal_document_still_parses(tmp_path):
    """Защита не ломает обычные выгрузки SimInTech — в них нет DOCTYPE."""
    db = SignalDatabase.from_xml(_write(tmp_path))

    assert db.is_loaded is True


# ─── Экспорт БД через макрос ──────────────────────────────────────


class _FakeCLIResult:
    def __init__(self, success: bool, message: str = "ок"):
        self.success = success
        self.message = message


def _install_fake_cli(monkeypatch, success: bool, calls: dict):
    """Подменить CLIAdapter в `cli_runner` — оттуда его берёт экспорт."""
    import simintech_api.cli_runner as cli_runner

    class FakeCLIAdapter:
        def __init__(self, mmain_path=None):
            calls["mmain_path"] = mmain_path

        def run_macro(self, macro):
            calls["macro"] = macro
            return _FakeCLIResult(success, "ошибка макроса")

    monkeypatch.setattr(cli_runner, "CLIAdapter", FakeCLIAdapter)


def test_export_db_via_macro_uses_cli_runner(monkeypatch, tmp_path):
    """Экспорт идёт через `CLIAdapter` из `cli_runner`.

    Импорт был из `cli_adapter` — модуля с таким именем в пакете нет, поэтому
    функция не импортировалась вообще. Импорт стоит **внутри** функции, так что
    и `import simintech_api.sdb` проходил: поймать это мог только вызов.
    """
    calls: dict = {}
    _install_fake_cli(monkeypatch, True, calls)
    out = tmp_path / "db.xml"

    result = export_db_via_macro("model.prt", str(out))

    assert result == str(out)
    assert "dbexporttoxml" in calls["macro"]
    assert "model.prt" in calls["macro"]


def test_export_db_via_macro_reports_failure(monkeypatch, tmp_path):
    """Неудача макроса — исключение, а не путь к файлу, которого нет."""
    calls: dict = {}
    _install_fake_cli(monkeypatch, False, calls)

    with pytest.raises(RuntimeError):
        export_db_via_macro("model.prt", str(tmp_path / "db.xml"))
