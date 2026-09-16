"""Тесты извлечения имён сигналов из XML-проекта (.xprt)."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from simintech_api.utils.xprt_signals import XprtSignalReader

# Минимальный xprt с двумя блоками (Константа + Усилитель) и проводом.
# Кодировка в объявлении — как у настоящих выгрузок (см. `catalog.decode_xprt`).
SAMPLE_XPRT = """<?xml version="1.0" encoding="utf-8" ?>
<Header></Header>
<project>
  <object>
    <name>`const_sig`</name>
    <class_name>`Константа`</class_name>
    <visual_props></visual_props>
  </object>
  <object>
    <name>`Gain`</name>
    <class_name>`Усилитель`</class_name>
    <visual_props></visual_props>
  </object>
  <object>
    <name>`Wire1`</name>
    <class_name>`Wire`</class_name>
  </object>
  <object>
    <name>`Label`</name>
    <class_name>`TextLabel`</class_name>
  </object>
</project>
"""


def test_extract_block_names_filters_graphics():
    reader = XprtSignalReader(SAMPLE_XPRT)
    names = reader.parse()
    assert "const_sig" in names
    assert "Gain" in names
    # Wire и TextLabel — не сигнальные блоки
    assert "Wire1" not in names
    assert "Label" not in names


def test_signal_map():
    reader = XprtSignalReader(SAMPLE_XPRT)
    reader.parse()
    mapping = reader.get_signal_map()
    assert mapping == {"const_sig": "const_sig", "Gain": "Gain"}


def test_empty_xml():
    reader = XprtSignalReader("")
    assert reader.parse() == []


def test_xml_fallback():
    """Без regex-формата (другие отступы) — XML-путь."""
    xml = '<?xml version="1.0"?><project><object><name>k0</name>' \
          '<class_name>Константа</class_name></object></project>'
    reader = XprtSignalReader(xml)
    names = reader.parse()
    assert "k0" in names


def test_extract_decodes_utf8_bom():
    """Экспорт проекта читается как UTF-8 с BOM, а не как cp1251.

    Чтение как cp1251 превращает «Усилитель» в мусор **молча**: cp1251
    декодирует любые байты, ошибки не будет. Поэтому проверка смотрит на
    русское имя — «исключения не было» здесь ничего не доказывает.
    """
    from simintech_api.utils.xprt_signals import (
        extract_signal_names_from_project,
    )

    xml = ('<?xml version="1.0" encoding="utf-8"?>'
           "<project>"
           "<object><name>`Усилитель_1`</name>"
           "<class_name>`Усилитель`</class_name></object>"
           "</project>")

    class FakeProject:
        id = 7

        def save_xml(self, path):
            # Именно байты с BOM: так пишет SaveProjectXML.
            with open(path, "wb") as fh:
                fh.write(xml.encode("utf-8-sig"))

    names = extract_signal_names_from_project(FakeProject())

    assert "Усилитель_1" in names
