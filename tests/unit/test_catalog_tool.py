"""Тесты точки входа генератора каталога (без COM)."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from simintech_api import catalog_tool  # noqa: E402
from simintech_api.catalog import BlockCatalog  # noqa: E402

# Минимальная выгрузка: один блок с русским именем класса в бэктиках.
XPRT_ONE_BLOCK = """<?xml version="1.0" encoding="utf-8"?>
<project>
  <object>
    <name>`Gain1`</name>
    <class_name>`Усилитель`</class_name>
    <custom_props>
      <data><name>`a`</name><mode>`1`</mode><value>`2.5`</value></data>
    </custom_props>
  </object>
</project>
"""


def test_main_refuses_on_non_windows(monkeypatch, capsys):
    """Вне Windows генерация невозможна — понятный отказ, код возврата 2."""
    monkeypatch.setattr(sys, "platform", "linux")

    code = catalog_tool.main([])

    assert code == 2
    assert "Windows" in capsys.readouterr().err


def test_main_accepts_out_argument(monkeypatch, tmp_path):
    """--out принимается и передаётся в сохранение каталога."""
    monkeypatch.setattr(sys, "platform", "linux")

    code = catalog_tool.main(["--out", str(tmp_path / "c.json")])

    assert code == 2  # отказ по платформе, но аргумент разобран


def test_xprt_legacy_cp1251_decoded_without_replacement(monkeypatch, tmp_path):
    """Старый .xprt без BOM (cp1251) разбирается без U+FFFD.

    Прежде байты декодировались как ``utf-8-sig`` с ``errors="replace"``: русские
    имена классов превращались в ``U+FFFD``, каталог сохранялся, код возврата
    был 0. Порча поставляемого каталога выглядела успехом.
    """
    monkeypatch.setattr(sys, "platform", "linux")
    legacy = tmp_path / "old.xprt"
    legacy.write_bytes(XPRT_ONE_BLOCK.encode("cp1251"))
    out = tmp_path / "catalog.json"

    code = catalog_tool.main(["--xprt", str(legacy), "--out", str(out)])

    assert code == 0
    names = BlockCatalog.load(out).classes()
    assert "Усилитель" in names
    assert not any(chr(0xFFFD) in name for name in names)


def test_traversal_classes_keeps_classes_of_known_catalog():
    """Классы уже собранного каталога входят в обход, а не теряются.

    Индекс `.csl` не знает базового слоя движка («Операция РАВНО», «Оператор
    И», «Интегратор с ограничением»), поэтому без этого дополнения полный
    прогон выбрасывал бы такие классы из каталога целиком. Проверка падает,
    если дополнение убрать.
    """
    names = catalog_tool._traversal_classes(["Константа"], ["Операция РАВНО"])

    assert "Константа" in names
    assert "Операция РАВНО" in names


def test_traversal_classes_without_index_keeps_default_set():
    """Индекса нет — обход всё равно полон: стандартные классы плюс каталог."""
    names = catalog_tool._traversal_classes(None, ["Операция РАВНО"])

    assert "Операция РАВНО" in names
    assert "Константа" in names


def test_known_classes_of_missing_catalog_is_empty(tmp_path):
    """Пропавший каталог — пустой список, а не ошибка."""
    assert catalog_tool._known_classes(tmp_path / "нет.json") == []


def test_known_classes_reads_catalog(tmp_path):
    """Классы каталога читаются из файла и идут в обход."""
    shipped = tmp_path / "shipped.json"
    BlockCatalog(classes={"Операция РАВНО": {"eps": "1E-14"}}).save(shipped)

    assert catalog_tool._known_classes(shipped) == ["Операция РАВНО"]


def test_main_traverses_classes_of_shipped_catalog(monkeypatch, tmp_path):
    """Полный прогон обходит классы поставляемого каталога.

    Это и есть проверка «класс не потеряется»: базовая «Операция РАВНО» не
    значится ни в индексе `.csl`, ни в `SUPPORTED_COM_BLOCK_CLASSES`, и
    попадает в обход только из каталога. Падает, если связку убрать.
    """
    shipped = tmp_path / "shipped.json"
    BlockCatalog(classes={"Операция РАВНО": {"eps": "1E-14"}}).save(shipped)
    monkeypatch.setattr(catalog_tool, "DEFAULT_CATALOG_PATH", shipped)
    monkeypatch.setattr(sys, "platform", "win32")

    class _FakeClient:
        def __init__(self, **kwargs):
            pass

        def connect(self):
            return self

        def disconnect(self):
            pass

    seen = {}

    def _fake_generate(client, classes=None, keep_project=False,
                       dump_path=None):
        seen["classes"] = list(classes or ())
        return BlockCatalog(classes={}, meta={"failed": []})

    monkeypatch.setattr("simintech_api.COMClient", _FakeClient)
    monkeypatch.setattr(catalog_tool, "generate_catalog", _fake_generate)

    code = catalog_tool.main(["--out", str(tmp_path / "catalog.json")])

    assert code == 0
    assert "Операция РАВНО" in seen["classes"]


def test_main_skips_classes_library_refuses(monkeypatch, tmp_path, capsys):
    """Классы, которые библиотека отвергает, не идут в обход и в `failed`.

    `Page.create_block` бросает `UnsupportedBlockError` для классов из
    `UNSUPPORTED_COM_BLOCK_CLASSES` детерминированно. Пока обход брал их из
    каталога, прогон без `--merge` клал их в `meta["failed"]` и возвращал 1 —
    успешный прогон был невозможен. Проверка идёт через **настоящий**
    `generate_catalog` и настоящий отказ `Page.create_block`; подменены только
    COM-клиент и `Project`.
    """
    from simintech_api.core.page import Page

    shipped = tmp_path / "shipped.json"
    BlockCatalog(classes={"Из памяти": {"a": "1"},
                          "Порт выхода": {},
                          "Операция РАВНО": {"eps": "1E-14"}}).save(shipped)
    monkeypatch.setattr(catalog_tool, "DEFAULT_CATALOG_PATH", shipped)
    monkeypatch.setattr(sys, "platform", "win32")

    class _FakeClient:
        def __init__(self, **kwargs):
            pass

        def connect(self):
            return self

        def disconnect(self):
            pass

        def call(self, *args):
            return 1

    class _FakeProject:
        def __init__(self, client):
            self.client = client
            self.id = 1

        @classmethod
        def new(cls, client):
            return cls(client)

        def get_main_page(self):
            return Page(self, 1)

        def save_xml(self, path):
            with open(path, "w", encoding="utf-8") as stream:
                stream.write("<project/>")

        def close(self):
            pass

    monkeypatch.setattr("simintech_api.COMClient", _FakeClient)
    monkeypatch.setattr("simintech_api.core.project.Project", _FakeProject)

    out = tmp_path / "catalog.json"
    code = catalog_tool.main(["--out", str(out)])

    assert code == 0
    failed = BlockCatalog.load(out).meta["failed"]
    assert "Из памяти" not in failed
    assert "Порт выхода" not in failed
    assert "пропущены" not in capsys.readouterr().err


def test_xprt_corrupted_bom_refused_without_catalog(monkeypatch, tmp_path, capsys):
    """Испорченный файл с BOM — отказ, а не каталог из мусора."""
    monkeypatch.setattr(sys, "platform", "linux")
    raw = XPRT_ONE_BLOCK.encode("utf-8-sig")
    broken = tmp_path / "broken.xprt"
    broken.write_bytes(raw[:-1] + b"\xff")
    out = tmp_path / "catalog.json"

    code = catalog_tool.main(["--xprt", str(broken), "--out", str(out)])

    assert code == 2
    assert not out.exists()
    assert "декодировать" in capsys.readouterr().err
