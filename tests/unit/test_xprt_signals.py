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

# Старая конвенция кавычек (значения в одинарных кавычках) и объект без класса —
# так в выгрузке выглядят подпись, комментарий и заливка (в реальном `.xprt`
# таких объектов пять: у них пуст `class_name`).
SAMPLE_XPRT_SINGLE_QUOTES = """<project>
  <object>
    <name>'LangBlock22'</name>
    <class_name>'Язык программирования'</class_name>
  </object>
  <object>
    <name>'Подпись_ТКМ'</name>
    <class_name></class_name>
  </object>
</project>
"""

# Старый формат нумерует объекты контейнера: `<object_0>`, `<object_1>`, ...
SAMPLE_XPRT_NUMBERED = """<project>
  <object_0>
    <name>'LangBlock22'</name>
    <class_name>'Язык программирования'</class_name>
  </object_0>
  <object_1>
    <name>`Macro_1`</name>
    <class_name>`Субмодель`</class_name>
  </object_1>
</project>
"""

# Вложенный объект: страница субмодели лежит внутри своего блока, и блок на
# ней — такой же сигнал, как блок на основной странице.
SAMPLE_XPRT_NESTED = """<project>
  <object>
    <name>`Macro_0`</name>
    <class_name>`Субмодель`</class_name>
    <containerblock>
      <object>
        <name>`k_0`</name>
        <class_name>`Константа`</class_name>
      </object>
    </containerblock>
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


def test_values_without_quotes_are_accepted():
    """Значения без кавычек — та же терпимость, что и в разборе каталога."""
    xml = '<?xml version="1.0"?><project><object><name>k0</name>' \
          '<class_name>Константа</class_name></object></project>'
    reader = XprtSignalReader(xml)
    names = reader.parse()
    assert "k0" in names


def test_single_quotes_stripped_and_objects_without_class_dropped():
    """Имена — без кавычек, объект без класса сигналом не считается.

    Прежде снимались только бэктики: на файле со одинарными кавычками имена
    возвращались как ``'LangBlock22'`` — по такому имени не найдётся ни блок,
    ни сигнал. Тот же корень оживлял фильтр графики: класс приходил в кавычках
    и ни с одним классом не совпадал, поэтому объект без ``class_name``
    (подпись, заливка) попадал в список «сигналов».
    """
    assert XprtSignalReader(SAMPLE_XPRT_SINGLE_QUOTES).parse() == ["LangBlock22"]


def test_numbered_objects_are_parsed():
    """Обе формы тега объекта: ``<object>`` и ``<object_N>``.

    Прежде нумерованный объект виден не был, а запасной XML-разбор запускался
    только при полном промахе regex: частичное совпадение теряло остальное
    молча — здесь оставалось одно ``Macro_1`` из двух имён.
    """
    assert XprtSignalReader(SAMPLE_XPRT_NUMBERED).parse() == \
        ["LangBlock22", "Macro_1"]


def test_nested_object_names_are_kept():
    """Блок на странице субмодели — тот же сигнал, что и блок основной страницы.

    Границы объектов считаются по глубине: на нежадном ``<object>…</object>``
    вложенный блок из списка выпадал, а его имя и класс попадали в разбор
    контейнера (проверено на реальных выгрузках: без счётчика глубины список
    терял ``LangBlock_0``, ``Macro_0``, ``PortConnector_1``).
    """
    assert XprtSignalReader(SAMPLE_XPRT_NESTED).parse() == ["Macro_0", "k_0"]


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
