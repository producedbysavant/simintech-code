"""Извлечение имён сигналов из XML-проекта SimInTech (.xprt).

В SimInTech внутренние сигналы блоков НЕ попадают в GetProjectSignalList
(он возвращает только обменные сигналы блоков «Вход/Выход алгоритма»).
Имена сигналов блоков совпадают с именами блоков (Name) и могут быть
извлечены из XML-представления проекта.

Формат .xprt: кодировка UTF-8 с BOM (`catalog.decode_xprt`), блок —
<object><name>..</name><class_name>..</class_name><visual_props><data><name>Name
</name><value>..</value>
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Iterator, List, Optional, Tuple

from ..catalog import NON_BLOCK_CLASSES, clean_value, decode_xprt
from ..exceptions import ProjectError

if TYPE_CHECKING:
    from ..core.project import Project


# Объекты .xprt двух видов: `<object>` в современных выгрузках и `<object_0>`,
# `<object_1>`, ... в старых; значения — в бэктиках или в одинарных кавычках.
# Разбор терпим к обеим конвенциям, как в `catalog.py`: самодельная пара
# «<name>`…`</name><class_name>`…`</class_name>`» на старом файле не совпадала
# ни с чем, отдавала имена в кавычках и не давала отсеять графику.
_OBJECT_TAG_RE = re.compile(r"<(?P<close>/)?object(?:_\d+)?>", re.I)
_CLASS_RE = re.compile(
    r"<class_name>\s*[`']?([^`<]*)[`']?\s*</class_name>", re.S | re.I)
_NAME_RE = re.compile(r"<name>\s*[`']?([^`<]*)[`']?\s*</name>", re.S | re.I)


class XprtSignalReader:
    """Парсер имён сигналов из XML-проекта SimInTech."""

    def __init__(self, xml_text: str):
        self._xml_text = xml_text
        # Имена блоков, извлечённые из XML
        self._block_names: List[str] = []

    # ─── Основной API ───────────────────────────────────────────────

    def parse(self) -> List[str]:
        """Извлечь имена блоков-кандидатов в сигналы из XML.

        Возвращает список имён блоков (их же используют как имена сигналов).
        """
        self._block_names = self._extract_block_names()
        return list(self._block_names)

    def get_signal_map(self) -> Dict[str, str]:
        """Вернуть {имя_блока: имя_сигнала} (пока имя = имя блока)."""
        return {name: name for name in self._block_names}

    # ─── Внутреннее ─────────────────────────────────────────────────

    def _extract_block_names(self) -> List[str]:
        """Извлечь имена блоков из XML-текста.

        Один терпимый проход по объектам: обе конвенции кавычек, обе формы
        тега, порядок ``<name>`` и ``<class_name>`` внутри объекта не важен.
        Запасного XML-разбора рядом нет намеренно: он не отсеивал объекты без
        класса (у подписей и заливок ``class_name`` пуст), а включался только
        при полном промахе regex — то есть объединение веток добавляло бы в
        список имён оформление.
        """
        result: List[str] = []
        for body in _iter_object_bodies(self._xml_text):
            name_match = _NAME_RE.search(body)
            if not name_match:
                continue
            cls_match = _CLASS_RE.search(body)
            cls = clean_value(cls_match.group(1)) if cls_match else ""
            # Пустой класс — оформление (подпись, заливка, комментарий): имени
            # блока у него нет, и в сигналы ему попадать нечем.
            if not cls or cls in NON_BLOCK_CLASSES:
                continue
            name = clean_value(name_match.group(1))
            if name:
                result.append(name)
        return result


def _iter_object_bodies(xml_text: str) -> Iterator[str]:
    """Своя часть каждого объекта — с учётом вложенности.

    Объекты бывают вложенными (страница субмодели лежит внутри своего блока),
    а нежадное ``<object>…</object>`` обрывается на первом вложенном: блок
    внутри субмодели пропадал из списка, а его имя и класс попадали в разбор
    контейнера. Границы считает счётчик глубины, а «своя» часть объекта
    кончается там, где начинается вложенный объект, — поэтому имя и класс
    всегда из одного объекта.
    """
    stack: List[Tuple[int, Optional[int]]] = []
    bodies: List[Tuple[int, int]] = []
    for m in _OBJECT_TAG_RE.finditer(xml_text):
        if m.group("close"):
            if not stack:
                continue
            start, own_end = stack.pop()
            bodies.append((start, own_end if own_end is not None else m.start()))
        else:
            if stack:
                start, _ = stack.pop()
                stack.append((start, m.start()))
            stack.append((m.end(), None))
    # Порядок документа, а не закрытия тегов: список сигналов читают глазами,
    # и вложенный блок не должен вставать перед своим контейнером.
    for start, end in sorted(bodies):
        yield xml_text[start:end]


# ─── Удобная функция для Project ───────────────────────────────────

def extract_signal_names_from_project(project: "Project",
                                      temp_suffix: str = ".xprt") -> List[str]:
    """Экспортировать проект в .xprt и извлечь имена сигналов.

    Использует временный файл (SaveProjectXML) и разбирает имена блоков —
    кандидатов в сигналы. Кодировка определяется по содержимому
    (`catalog.decode_xprt`): SimInTech пишет `.xprt` в UTF-8 с BOM, а чтение
    как cp1251 превращает русские имена в мусор **молча**, без ошибки —
    cp1251 декодирует любые байты.
    """
    tmp = Path(tempfile.gettempdir()) / f"siminapi_signals_{project.id}{temp_suffix}"
    try:
        project.save_xml(str(tmp))
    except Exception as exc:
        raise ProjectError(f"Не удалось экспортировать проект в XML: {exc}") from exc
    try:
        text = decode_xprt(tmp.read_bytes())
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
    return XprtSignalReader(text).parse()
