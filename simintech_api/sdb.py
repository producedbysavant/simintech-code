"""База сигналов SimInTech (SDB): разбор XML-выгрузки.

База трёхуровневая: Категория → Группа → Сигнал. Полное имя сигнала
собирается как ``<группа>_<сигнал>``; для поиска индексируется и составной
ключ ``<категория>.<группа>.<имя>``.

Поддерживается два режима: разбор готового XML-экспорта (не требует SimInTech)
и выгрузка базы в XML макросом (требует CLI или COM).

Структура XML и экспорт макросом описаны в `automation/signal-db.md`.
Перенесено из репозитория `simintech-connector` (заархивирован 2026-09-10).
"""
from __future__ import annotations

import re

# defusedxml, а не stdlib: обычный xml.etree разворачивает DTD-сущности, из-за
# чего документ вида «billion laughs» съедает память, а внешние сущности дают
# XXE. Выгрузки SimInTech DOCTYPE не содержат, поэтому строгий режим их не ломает.
import defusedxml.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class SDBSignalInfo:
    """Информация о сигнале в БД."""
    name: str
    caption: str
    category: str
    group: str
    data_type: int = 0
    mode: int = 0
    value: str = ""
    fconstant: str = "0"
    full_name: str = ""


@dataclass
class GroupInfo:
    """Информация о группе сигналов."""
    name: str
    category: str
    signals: list[SDBSignalInfo] = field(default_factory=list)


@dataclass
class CategoryInfo:
    """Информация о категории сигналов.

    ``template_signals`` — содержимое ``<signalstemplate>``: **прототип**
    сигналов категории, а не её сигналы. В поставке каждый сигнал группы
    повторяет шаблон (то же имя, то же значение): ``pumps.xml`` — 18 записей
    шаблона и 3 группы по 18 сигналов, ``valves.xml`` — 5 и 3×5, и ни одного
    имени, которого нет в группах. Поэтому шаблон читается отдельно и **не**
    попадает в карту сигналов: иначе счёт удвоился бы (54 → 72 в ``pumps.xml``),
    а поиск находил бы записи, которых в базе нет.
    """
    name: str
    template: str = ""
    template_signals: list[SDBSignalInfo] = field(default_factory=list)
    groups: list[GroupInfo] = field(default_factory=list)


def _strip_quotes(text: Optional[str]) -> str:
    """Убрать кавычки по краям значения из XML базы сигналов.

    Кавычки двух конвенций: одни выгрузки оборачивают значения в бэктики,
    другие — в одинарные кавычки; и то и другое встречается в поставке.
    Внутренние кавычки не трогаются. Раньше снимались только бэктики, и файл с
    одинарными кавычками не разбирался вовсе: ``int('0')`` падал.
    """
    if text is None:
        return ""
    return text.strip().strip("`'").strip()


def _as_int(text: str, default: int = 0) -> int:
    """Целое из значения поля; нечисловое даёт `default`, а не исключение.

    Поля ``type`` и ``mode`` — служебные: непонятное значение в них не повод
    ронять разбор всего файла, но и молчать о нём нельзя, поэтому вызывающий
    видит `default` и может отличить его от разобранного значения.
    """
    try:
        return int(text)
    except (TypeError, ValueError):
        return default


def _field(elem, tag, default: str = "") -> str:
    """Текст дочернего элемента с удалением кавычек обеих конвенций."""
    val = elem.findtext(tag, default)
    return _strip_quotes(val) if val else default


def _signal_from_element(elem, category: str, group: str,
                         name: str = "") -> "SDBSignalInfo":
    """Собрать запись сигнала из элемента ``<data>``.

    Один разбор на оба места, где встречается ``<data>``: в ``<signals>``
    группы и в ``<signalstemplate>`` категории. Поля у них одинаковые, а
    расхождение между двумя копиями разбора — как раз то, из-за чего шаблон
    раньше не читался вовсе.
    """
    sig_name = name or _field(elem, "name")
    return SDBSignalInfo(
        name=sig_name,
        caption=_field(elem, "caption"),
        category=category,
        group=group,
        data_type=_as_int(_field(elem, "type", "0") or "0"),
        mode=_as_int(_field(elem, "mode", "0") or "0"),
        value=_field(elem, "value"),
        fconstant=_field(elem, "fconstant", "0") or "0",
        full_name=f"{group}_{sig_name}" if group else sig_name,
    )


class SignalDatabase:
    """База данных сигналов SimInTech, загруженная из XML-экспорта.

    Пример:
        >>> db = SignalDatabase.from_xml("signals.xml")
        >>> cats = db.list_categories()
        >>> signals = db.find_signal("M*")
    """

    def __init__(self):
        self.categories: list[CategoryInfo] = []
        self._signal_map: dict[str, SDBSignalInfo] = {}  # full_name -> SDBSignalInfo
        self._loaded: bool = False
        self._source: str = ""

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @classmethod
    def from_xml(cls, xml_path: str | Path) -> "SignalDatabase":
        """Загрузить БД из XML-файла, экспортированного через dbexporttoxml."""
        db = cls()
        db._source = str(xml_path)
        tree = ET.parse(str(xml_path))
        root = tree.getroot()

        database = root.find("database")
        if database is None:
            database = root

        for cat_elem in database.findall("category"):
            cat_name = _field(cat_elem, "name")
            cat_template = _field(cat_elem, "nametemplate")

            cat = CategoryInfo(name=cat_name, template=cat_template)

            # <signalstemplate> — прототип сигналов категории (см. CategoryInfo),
            # поэтому он читается, но в _signal_map не попадает.
            tmpl_elem = cat_elem.find("signalstemplate")
            if tmpl_elem is not None:
                cat.template_signals = [
                    _signal_from_element(elem, cat_name, "", "")
                    for elem in tmpl_elem.findall("data")
                ]

            for group_elem in cat_elem.findall("group"):
                group_name = _field(group_elem, "name")
                group = GroupInfo(name=group_name, category=cat_name)

                signals_elem = group_elem.find("signals")
                if signals_elem is not None:
                    for signal_elem in signals_elem.findall("data"):
                        sig_name = _field(signal_elem, "name")
                        sig = _signal_from_element(
                            signal_elem, cat_name, group_name, sig_name)
                        group.signals.append(sig)
                        db._signal_map[sig.full_name] = sig
                        db._signal_map[f"{cat_name}.{group_name}.{sig_name}"] = sig

                cat.groups.append(group)
            db.categories.append(cat)

        db._loaded = True
        return db

    def list_categories(self) -> list[dict]:
        """Список всех категорий."""
        return [
            {
                "name": c.name,
                "template": c.template,
                "group_count": len(c.groups),
                "signal_count": sum(len(g.signals) for g in c.groups),
                "template_signal_count": len(c.template_signals),
            }
            for c in self.categories
        ]

    def category_template(self, category: str) -> list[dict]:
        """Прототип сигналов категории (``<signalstemplate>``), не её сигналы.

        Возвращает схему, по которой в редакторе набираются сигналы группы;
        в базе таких сигналов может и не быть, поэтому их нет ни в
        ``list_signals``, ни в ``find_signal``. Пустой список — у категории
        шаблона нет (это обычное состояние, а не ошибка).
        """
        for cat in self.categories:
            if cat.name == category:
                return [
                    {
                        "name": s.name,
                        "caption": s.caption,
                        "type": s.data_type,
                        "mode": s.mode,
                        "value": s.value,
                    }
                    for s in cat.template_signals
                ]
        return []

    def list_groups(self, category: Optional[str] = None) -> list[dict]:
        """Список групп. Опционально — фильтр по категории."""
        result = []
        for cat in self.categories:
            if category and cat.name != category:
                continue
            for g in cat.groups:
                result.append({
                    "name": g.name,
                    "category": cat.name,
                    "signal_count": len(g.signals),
                })
        return result

    def list_signals(
        self,
        category: Optional[str] = None,
        group: Optional[str] = None,
    ) -> list[dict]:
        """Список сигналов с опциональной фильтрацией."""
        result = []
        for cat in self.categories:
            if category and cat.name != category:
                continue
            for g in cat.groups:
                if group and g.name != group:
                    continue
                for s in g.signals:
                    result.append({
                        "name": s.name,
                        "full_name": s.full_name,
                        "group": g.name,
                        "category": cat.name,
                        "caption": s.caption,
                        "type": s.data_type,
                        "value": s.value,
                    })
        return result

    def find_signal(self, pattern: str) -> list[dict]:
        """Поиск сигналов по имени/полному имени (поддерживает *).

        Безопасен к ReDoS: * конвертируется в [^.]*, а не в .*.
        """
        if len(pattern) > 200:
            pattern = pattern[:200]
        pattern = pattern.lower()
        # * -> [^.]* предотвращает catastrophic backtracking
        safe = "".join("[^.]*" if c == "*" else re.escape(c) for c in pattern)
        try:
            regex = re.compile(safe)
        except re.error:
            regex = re.compile(re.escape(pattern))

        seen: set[str] = set()
        result = []
        for full_name, sig in self._signal_map.items():
            if regex.search(full_name.lower()):
                if sig.full_name in seen:
                    continue
                seen.add(sig.full_name)
                result.append({
                    "name": sig.name,
                    "full_name": sig.full_name,
                    "group": sig.group,
                    "category": sig.category,
                    "caption": sig.caption,
                    "type": sig.data_type,
                    "value": sig.value,
                })
        return result

    def get_signal_info(self, full_name: str) -> Optional[dict]:
        """Получить детальную информацию о сигнале по полному имени."""
        sig = self._signal_map.get(full_name)
        if sig is None:
            # Try searching
            for fn, s in self._signal_map.items():
                if s.name == full_name or fn.endswith(f".{full_name}"):
                    sig = s
                    break
        if sig is None:
            return None

        return {
            "name": sig.name,
            "full_name": sig.full_name,
            "group": sig.group,
            "category": sig.category,
            "caption": sig.caption,
            "type": sig.data_type,
            "mode": sig.mode,
            "value": sig.value,
            "fconstant": sig.fconstant,
        }

    def get_signals_by_type(self, data_type: int) -> list[dict]:
        """Получить все сигналы определённого типа."""
        result = []
        for sig in self._signal_map.values():
            if sig.data_type == data_type:
                result.append({
                    "name": sig.name,
                    "full_name": sig.full_name,
                    "group": sig.group,
                    "category": sig.category,
                    "caption": sig.caption,
                    "type": sig.data_type,
                    "value": sig.value,
                })
        return result

    def get_statistics(self) -> dict:
        """Статистика по БД."""
        categories = len(self.categories)
        groups = sum(len(c.groups) for c in self.categories)
        # Уникальные сигналы через full_name (каждый сигнал хранится
        # под двумя ключами: group_name и category.group.name)
        unique: set[str] = set()
        types: dict[int, int] = {}
        for sig in self._signal_map.values():
            if sig.full_name not in unique:
                unique.add(sig.full_name)
                types[sig.data_type] = types.get(sig.data_type, 0) + 1
        signals = len(unique)

        return {
            "categories": categories,
            "groups": groups,
            "signals": signals,
            "types": types,
            "source": self._source,
        }


def _escape_macro_str(s: str) -> str:
    """Экранировать строку для вставки в макрос SimInTech.

    В макроязыке строки в двойных кавычках, кавычка внутри —
    удваивается (как в Pascal).
    """
    return s.replace('"', '""')


def export_db_via_macro(
    project_file: str,
    output_path: str,
    mmain_path: Optional[str] = None,
) -> str:
    """Экспортировать БД сигналов в XML через макрос SimInTech.

    Args:
        project_file: Путь к проекту (.prt) или пакету (.pak)
        output_path: Путь для сохранения XML
        mmain_path: Путь к mmain.exe (опционально)

    Returns:
        Путь к созданному XML-файлу
    """
    # CLIAdapter живёт в `cli_runner`: модуля `cli_adapter` в пакете нет, и
    # импорт из него не давал импортировать эту функцию вообще.
    from .cli_runner import CLIAdapter

    cli = CLIAdapter(mmain_path=mmain_path)

    macro = (
        f"initialization\n"
        f'    prjid = openproject("{_escape_macro_str(project_file)}", 0);\n'
        f'    initproject(prjid, 0);\n'
        f'    dbexporttoxml(prjid, "{_escape_macro_str(output_path)}");\n'
        f"    closeapp;\n"
        f"end;\n"
    )

    result = cli.run_macro(macro)
    if not result.success:
        raise RuntimeError(f"Ошибка экспорта БД: {result.message}")

    return output_path
