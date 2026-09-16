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

# defusedxml, а не stdlib: см. пояснение в simintech_api/sdb.py.
import defusedxml.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List

from ..catalog import decode_xprt
from ..exceptions import ProjectError

if TYPE_CHECKING:
    from ..core.project import Project


# Классы, которые НЕ являются сигнальными блоками (графика/оформление)
_NON_SIGNAL_CLASSES = {
    "Wire", "Arc", "Button", "FillCircle", "FillEllipseSector", "FillRect",
    "Line", "Point", "PolyLine", "PolyRound", "Polygon", "Rectangle",
    "RotatedText", "TextLabel", "constLabel", "Комментарий",
}


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

        Два прохода:
        1) быстрый regex по <name>..</name><class_name>..</class_name>;
        2) если regex не сработал — полноценный XML-парсинг.
        """
        names = self._names_by_regex()
        if not names:
            names = self._names_by_xml()
        return names

    def _names_by_regex(self) -> List[str]:
        result: List[str] = []
        pattern = re.compile(
            r"<name>`([^`]*)`</name>\s*<class_name>`([^`]*)`</class_name>"
        )
        for m in pattern.finditer(self._xml_text):
            name, cls = m.group(1), m.group(2)
            if cls in _NON_SIGNAL_CLASSES:
                continue
            if name.strip():
                result.append(name)
        return result

    def _names_by_xml(self) -> List[str]:
        """Полноценный XML-парсинг (запасной путь)."""
        try:
            # Содержимое — в бэктиках; кодировку снял `decode_xprt` выше
            root = ET.fromstring(self._xml_text)
        except ET.ParseError:
            return []
        result: List[str] = []
        for obj in root.iter("object"):
            cls = _get_child_text(obj, "class_name")
            name = _get_child_text(obj, "name")
            if cls in _NON_SIGNAL_CLASSES:
                continue
            if name.strip():
                result.append(name)
        return result


def _get_child_text(parent: "ET.Element", tag: str) -> str:
    node = parent.find(tag)
    if node is None or node.text is None:
        return ""
    return str(node.text).strip().strip("`")


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
