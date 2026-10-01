"""Тела операций языкового слоя — сборка строк встроенного языка, без COM.

Здесь только текст: как собрать скрипт для выгрузки модели, её загрузки и
инжектирования субмодели. Доставка и проверка — `core/script_bridge.py`
(`run_page_script`), разбор исхода — `script_probe.classify_page_result`.

Правила экранирования измерены 2026-09-29 на поставке 2.26.6.23:
кавычка задаётся `chr(34)` (удвоение `""` даёт пустую строку, обратный слэш не
экранирует), перевод строки — константой `CLRF`.
"""

from __future__ import annotations

#: Код типа объекта «Субмодель» в `createprimitiv` (`otSubModel`).
SUBMODEL_OBJECT_CODE = 102

#: Точки пустой субмодели — те же, что в демонстрационном примере вендора.
EMPTY_SUBMODEL_POINTS = "[(0, 0), (-16, 0), (0, -16), (0, 16)]"


def to_language_literal(text: str) -> str:
    """Собрать строковый литерал встроенного языка из произвольного текста.

    Кавычка внутри литерала недопустима как есть, поэтому текст режется по
    кавычкам, а сами кавычки подставляются `chr(34)`. Перевод строки — `CLRF`:
    строковый литерал в языке не может занимать несколько строк.

    Пустые куски выбрасываются: `"" + ...` язык примет, но лишние склейки
    прячут настоящую длину выражения при отладке.
    """
    chunks: list[str] = []
    for line_index, line in enumerate(text.split("\n")):
        if line_index:
            chunks.append("CLRF")
        for piece_index, piece in enumerate(line.split('"')):
            if piece_index:
                chunks.append("chr(34)")
            if piece:
                chunks.append(f'"{piece}"')
    return " + ".join(chunks)


def build_export_model_text_body(artifact_path: str) -> str:
    """Тело выгрузки модели: `savemodeltofile` в файл-артефакт."""
    return f'savemodeltofile(getcurrentprojectid, "{_path(artifact_path)}");'


def build_import_model_text_body(model_text: str) -> str:
    """Тело загрузки модели: объявление кортежа и `createmodel`.

    Форма взята из демонстрационных проектов вендора: `const model : ( … );` —
    это не строка, а запись языка, введённая в текст скрипта.

    **Текст из `savemodeltofile` приходит уже обёрнутым** в `( … )` — это
    выгрузка контейнера целиком. Двойная обёртка (`const model : ( ( … ) );`)
    не компилируется, причём среда об этом молчит: замер 2026-09-29 показал
    именно это — выгрузка как есть не собиралась, а она же без внешней скобки
    собиралась и создавала объекты. Поэтому внешняя скобка распознаётся и
    повторно не добавляется.
    """
    text = model_text.strip()
    if text.startswith("(") and text.endswith(")"):
        return (f"const model : {text};\n"
                "createmodel(getcurrentprojectid, model);")
    return (f"const model : (\n{text}\n);\n"
            "createmodel(getcurrentprojectid, model);")


def build_inject_submodel_script_body(injected_script: str,
                                      submodel_code: int = SUBMODEL_OBJECT_CODE
                                      ) -> str:
    """Тело инжектирования: пустая субмодель, скрипт и переинициализация.

    Порядок обязателен и измерен 2026-09-29: без `reinitsubmodel` присвоенный
    скрипт **не компилируется**, и снаружи это выглядит как «присвоили — и
    ничего не происходит», без сообщений.
    """
    return (
        f"objid = createprimitiv({submodel_code}, {EMPTY_SUBMODEL_POINTS});\n"
        f'setprop(objid, "script", {to_language_literal(injected_script)});\n'
        "reinitsubmodel(objid);"
    )


def _path(path: str) -> str:
    """Путь внутри литерала: прямые слэши, без кавычек и переводов строки."""
    if '"' in path or "\n" in path or "\r" in path:
        raise ValueError(
            f"путь не может содержать кавычку или перевод строки: {path!r}")
    return path.replace("\\", "/")
