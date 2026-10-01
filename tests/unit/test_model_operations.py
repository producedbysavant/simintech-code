"""Тела трёх операций языкового слоя — чистые строки без COM."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from simintech_api.model_operations import (  # noqa: E402
    build_export_model_text_body,
    build_import_model_text_body,
    build_inject_submodel_script_body,
    to_language_literal,
)


def test_literal_escapes_quotes_and_newlines_the_measured_way():
    """Кавычка — через chr(34), перевод строки — через CLRF.

    Измерено 2026-09-29: удвоение `""` в этой сборке даёт пустую строку, а
    обратный слэш не экранирует; рабочая форма — chr(34). Переводы строк
    задаются константой CLRF.

    Обе кавычки текста восстанавливаются **поровну**: в ожидании плана
    `chr(34)` стоял один раз, и текст `type = "Усилитель"` вернулся бы без
    закрывающей кавычки — то есть сломанным. Разбор по кавычке нечётной
    кратности ловится этим ожиданием.
    """
    literal = to_language_literal('type = "Усилитель"\nконец')

    assert literal == (
        '"type = " + chr(34) + "Усилитель" + chr(34) + CLRF + "конец"')


def test_export_body_names_the_artifact_path():
    body = build_export_model_text_body("C:/out/model.txt")
    assert body == 'savemodeltofile(getcurrentprojectid, "C:/out/model.txt");'


def test_import_body_declares_model_as_const_and_calls_createmodel():
    body = build_import_model_text_body('block0: (type = "Ступенька")')

    assert body.startswith("const model : (")
    assert "createmodel(getcurrentprojectid, model);" in body


def test_inject_body_creates_submodel_assigns_script_and_reinits():
    """Рецепт измерен 2026-09-29: без reinitsubmodel скрипт не компилируется."""
    body = build_inject_submodel_script_body(
        'inj_result = createfile("C:/out/data.txt", -1);', submodel_code=102)

    assert "createprimitiv(102," in body
    assert 'setprop(objid, "script",' in body
    assert body.index("reinitsubmodel(objid);") > body.index('setprop(objid, "script"')
