"""Настройки базы сигналов и распределённого расчёта (`.dbconf`, `.dblocalconf`).

Файлы лежат рядом с базой сигналов или с проектом и хранят настройки обмена:
роль узла (сервер/клиент), порт, синхронизацию модельного времени. Разбор
чистый — COM не нужен, работает и на Linux.

Формат один и тот же у обоих расширений: XML из двух уровней,
``<Header><dbconfig>`` и плоский список элементов; атрибутов нет ни в одном из
77 файлов поставки. Различие расширений — не в схеме, а в том, с чем хранятся
настройки: ``.dbconf`` — совместно с базой, ``.dblocalconf`` — с проектом (так
это названо в справке SimInTech, раздел «База данных сигналов»).

Известные ловушки формата, проверенные на файлах поставки:

* **Кавычки двух конвенций** — 40 файлов целиком в одинарных, 37 в бэктиках;
  внутри файла смешения нет. Разбор обязан снимать обе (как ``CorrectXMLText``
  в ``uXMLSave.pas``), иначе значения сравниваются с кавычками и роль узла
  читается неверно.
* **Переводы строк внутри значения** кодируются ``#13#10``, ``#13``, ``#10``.
* **Пустая строка — валидное «не задано»**, а не ошибка: у 4 файлов пусты
  ``host``/``port``/``srvport``/``priority``.
* **Порт 19000 — не из справки.** В справке SimInTech числа нет вовсе; это
  фактический дефолт поставки (все непустые ``port``, кроме трёх намеренных
  демонстрационных переопределений).

Ключи ролей, которые читает :class:`DatabaseConfig`: ``srvenable`` (сервер),
``remenable`` (удалённый обмен), ``sync`` (синхронизация модельного времени),
``srvport``/``host``/``port``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

# defusedxml, а не stdlib: файл может прийти извне, а обычный xml.etree
# разворачивает DTD-сущности (billion laughs, XXE). Поставляемые `.dbconf`
# DOCTYPE не содержат, поэтому строгий режим их не ломает.
import defusedxml.ElementTree as ET

#: Последовательности-заменители переводов строк внутри значения.
_ESCAPES = (("#13#10", "\n"), ("#10", "\n"), ("#13", "\n"))


def _decode(value: str) -> str:
    """Значение тега: переводы строк и кавычки обеих конвенций.

    Поля-списки записаны как **цитаты, соединённые** ``#13#10``: в поставке
    встречается ``<catfiltervals>'*'#13#10</catfiltervals>``. Поэтому кавычки
    снимаются построчно: снятие по краям всего значения оставило бы кавычку
    перед переводом строки (`"Все (* )`\\n"` вместо `"Все (* )\\n"`).
    """
    for escaped, char in _ESCAPES:
        value = value.replace(escaped, char)
    return "\n".join(line.strip().strip("`'").strip()
                     for line in value.split("\n"))


def _text(elem: ET.Element, tag: str) -> str:
    """Значение дочернего элемента, разобранное :func:`_decode`."""
    value = elem.findtext(tag)
    return "" if value is None else _decode(value)


def _as_int(value: str) -> Optional[int]:
    """Целое из значения; пустое и нечисловое — ``None``, а не исключение.

    Пустое поле в этих файлах означает «не задано» (так у четырёх файлов
    поставки), и это не повод ронять разбор всего файла.
    """
    if not value:
        return None
    match = re.match(r"^[+-]?\d+$", value)
    return int(match.group(0)) if match else None


def _as_flag(value: str) -> bool:
    """Флаг из значения: ненулевое целое — включено, всё прочее — выключено."""
    return _as_int(value) not in (None, 0)


@dataclass
class DatabaseConfig:
    """Настройки базы сигналов и сетевого обмена одного проекта.

    Args:
        path: откуда прочитано (пустая строка, если собрано вручную).
        values: все элементы ``<dbconfig>`` как есть — по имени тега.
    """

    path: str = ""
    values: Dict[str, str] = field(default_factory=dict)
    nested: Dict[str, Dict[str, str]] = field(default_factory=dict)

    def raw(self, tag: str) -> str:
        """Значение тега как есть (пустая строка, если тега нет)."""
        return self.values.get(tag, "")

    @property
    def server_enabled(self) -> bool:
        """Узел принимает данные от клиентов (``srvenable``)."""
        return _as_flag(self.raw("srvenable"))

    @property
    def remote_enabled(self) -> bool:
        """Узел участвует в удалённом обмене как клиент (``remenable``)."""
        return _as_flag(self.raw("remenable"))

    @property
    def sync_time(self) -> bool:
        """Синхронизировать модельное время с сервером (``sync``)."""
        return _as_flag(self.raw("sync"))

    @property
    def host(self) -> str:
        """Адрес удалённого сервера обмена (``host``); пусто — не задан."""
        return self.raw("host")

    @property
    def port(self) -> Optional[int]:
        """Порт удалённого сервера (``port``); ``None`` — не задан."""
        return _as_int(self.raw("port"))

    @property
    def server_port(self) -> Optional[int]:
        """Порт приёма данных от клиентов (``srvport``)."""
        return _as_int(self.raw("srvport"))

    @property
    def sends_to_server(self) -> bool:
        """Передавать данные на сервер (``senddatatosrv``)."""
        return _as_flag(self.raw("senddatatosrv"))

    @property
    def receives_from_server(self) -> bool:
        """Принимать данные от сервера (``recievedatafromsrv``)."""
        return _as_flag(self.raw("recievedatafromsrv"))

    @property
    def role(self) -> str:
        """Роль узла словами: чем этот проект является в сетевом расчёте.

        Возможные значения: «сервер», «клиент», «сервер и клиент», «не
        настроен». Роль определяется флагами, а не расширением файла: у 12 из
        39 `.dblocalconf` стоит ``dbsettingsplace=0`` (наследство смены места
        хранения), и по нему роль не угадывается.
        """
        if self.server_enabled and self.remote_enabled:
            return "сервер и клиент"
        if self.server_enabled:
            return "сервер"
        if self.remote_enabled:
            return "клиент"
        return "не настроен"

    def as_dict(self) -> Dict[str, object]:
        """Сводка для инструментов и ресурсов MCP."""
        return {
            "path": self.path,
            "role": self.role,
            "sync_time": self.sync_time,
            "host": self.host,
            "port": self.port,
            "server_port": self.server_port,
            "sends_to_server": self.sends_to_server,
            "receives_from_server": self.receives_from_server,
        }


def parse_db_config(xml_text: str, path: str = "") -> DatabaseConfig:
    """Разобрать настройки из текста XML.

    Raises:
        SimInTechError: документ не разобран (это не «пустые настройки», а
            испорченный файл — их нельзя путать).
    """
    from .exceptions import SimInTechError

    try:
        root = ET.fromstring(xml_text)
    except Exception as exc:  # defusedxml кидает свои типы — ловим все
        raise SimInTechError(f"настройки базы не разобраны: {exc}") from exc

    config_elem = root.find("dbconfig")
    if config_elem is None:
        raise SimInTechError(
            "настройки базы не разобраны: нет элемента <dbconfig>")

    config = DatabaseConfig(path=path)
    for child in config_elem:
        tag = child.tag
        if len(child):
            config.nested[tag] = {sub.tag: _text(child, sub.tag)
                                  for sub in child}
        config.values[tag] = _text(config_elem, tag)
    return config


def load_db_config(path: str | Path) -> DatabaseConfig:
    """Прочитать настройки базы из файла `.dbconf`/`.dblocalconf`.

    Кодировка — UTF-8 с BOM (так записаны все файлы поставки); чтение терпимо
    и к UTF-8 без BOM.
    """
    source = Path(path)
    text = source.read_bytes().decode("utf-8-sig", errors="replace")
    return parse_db_config(text, path=str(source))
