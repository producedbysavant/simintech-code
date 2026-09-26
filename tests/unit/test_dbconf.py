"""Тесты разбора настроек базы сигналов (`.dbconf`, `.dblocalconf`) — без COM."""

import os
import sys
import textwrap

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest  # noqa: E402

from simintech_api.dbconf import (  # noqa: E402
    load_db_config,
    parse_db_config,
)
from simintech_api.exceptions import SimInTechError  # noqa: E402

#: Профиль сервера — так выглядит файл демо-примера синхронной записи сигналов.
SERVER_BACKTICKS = textwrap.dedent("""\
    <?xml version="1.0" encoding="utf-8"?>
    <Header>
    <dbconfig>
     <dbsettingsplace>`0`</dbsettingsplace>
     <srvport>`19000`</srvport>
     <host>`127.0.0.1`</host>
     <port>`19000`</port>
     <priority>`0`</priority>
     <srvenable>`1`</srvenable>
     <sync>`1`</sync>
     <remenable>`0`</remenable>
     <senddatatosrv>`1`</senddatatosrv>
     <recievedatafromsrv>`1`</recievedatafromsrv>
    </dbconfig>
    </Header>
""")

#: Файлы с одинарными кавычками — вторая конвенция поставки (40 файлов из 77).
CLIENT_SINGLE_QUOTES = textwrap.dedent("""\
    <?xml version="1.0" encoding="utf-8"?>
    <Header>
    <dbconfig>
     <srvport></srvport>
     <host>'10.0.0.5'</host>
     <port>'19003'</port>
     <srvenable>'0'</srvenable>
     <sync>'0'</sync>
     <remenable>'1'</remenable>
     <senddatatosrv>'1'</senddatatosrv>
     <recievedatafromsrv>'0'</recievedatafromsrv>
    </dbconfig>
    </Header>
""")


def test_server_role_is_read_from_flags():
    """Роль узла определяется флагами, а не расширением файла."""
    config = parse_db_config(SERVER_BACKTICKS)

    assert config.role == "сервер"
    assert config.server_enabled is True
    assert config.remote_enabled is False
    assert config.sync_time is True
    assert config.server_port == 19000


def test_single_quotes_and_client_role():
    """Одинарные кавычки снимаются: иначе флаг читался бы как строка с ними."""
    config = parse_db_config(CLIENT_SINGLE_QUOTES)

    assert config.role == "клиент"
    assert config.host == "10.0.0.5"
    assert config.port == 19003
    assert config.receives_from_server is False


def test_node_can_be_server_and_client_at_once():
    """Узел бывает и сервером, и клиентом — так у демо `video.dblocalconf`."""
    config = parse_db_config(
        SERVER_BACKTICKS.replace("<remenable>`0`", "<remenable>`1`"))

    assert config.role == "сервер и клиент"


def test_empty_values_mean_not_set_and_not_error():
    """Пустое поле — «не задано»: у 4 файлов поставки так устроены порт и хост."""
    config = parse_db_config(CLIENT_SINGLE_QUOTES.replace("'10.0.0.5'", ""))

    assert config.host == ""
    assert config.port == 19003

    empty = parse_db_config("<Header><dbconfig><port></port></dbconfig></Header>")
    assert empty.port is None
    assert empty.server_port is None
    assert empty.role == "не настроен"


def test_broken_document_is_refused_not_read_as_empty_settings(tmp_path):
    """Испорченный файл — отказ; «пустые настройки» и «провал разбора» нельзя путать."""
    with pytest.raises(SimInTechError):
        parse_db_config("<Header><dbconfig>")
    with pytest.raises(SimInTechError):
        parse_db_config("<Header><other/></Header>")


def test_line_breaks_are_decoded(tmp_path):
    """`#13#10` внутри значения — перевод строки, а не литерал."""
    config = parse_db_config(
        "<Header><dbconfig><catfiltercaps>`Все (* )`#13#10</catfiltercaps>"
        "</dbconfig></Header>")

    assert config.raw("catfiltercaps") == "Все (* )\n"


def test_load_reads_utf8_bom(tmp_path):
    """Файлы поставки записаны в UTF-8 с BOM — чтение обязано его переносить."""
    path = tmp_path / "project.dblocalconf"
    path.write_text(SERVER_BACKTICKS, encoding="utf-8-sig")

    assert load_db_config(path).role == "сервер"


def test_unknown_tags_are_kept_as_is():
    """Незнакомый тег не теряется: в файле их 100, разбирать их поимённо не надо."""
    config = parse_db_config(
        "<Header><dbconfig><formleft>`576`</formleft>"
        "<somefuturetag>`1`</somefuturetag></dbconfig></Header>")

    assert config.raw("somefuturetag") == "1"
    assert config.raw("нет-такого") == ""


#: Поставка: по её файлам проверяется, что разбор не падает и что роли читаются.
#: Каталог задаётся переменной `SIMINTECH_ROOT`; без поставки проверки
#: пропускаются (в CI её нет).
DISTRIBUTION = os.environ.get("SIMINTECH_ROOT", "/mnt/c/SimInTech64")


def _distribution_files():
    """Все `.dbconf` и `.dblocalconf` поставки."""
    found = []
    for root, dirs, files in os.walk(DISTRIBUTION):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        for name in files:
            if name.endswith((".dbconf", ".dblocalconf")):
                found.append(os.path.join(root, name))
    return sorted(found)


@pytest.mark.distribution
def test_all_distribution_files_parse():
    """Сплошная проверка: 77 файлов поставки разбираются все.

    Число берётся подсчётом, а не из текста: 39 `.dblocalconf` и 38 `.dbconf`.
    Обход 9p-каталога поставки занимает больше минуты, поэтому проверка идёт
    под маркером `distribution` — запускать явно: `pytest -m distribution`.
    """
    files = _distribution_files()
    if not files:
        pytest.skip(f"поставки нет: {DISTRIBUTION}")

    configs = [load_db_config(path) for path in files]
    assert len(configs) == 77
    assert sum(1 for p in files if p.endswith(".dblocalconf")) == 39
    # Роли заданы ровно в шести файлах — в двух демонстрационных разделах;
    # остальные 71 не настроены на сетевой обмен.
    configured = [c for c in configs if c.role != "не настроен"]
    assert len(configured) == 6
    # Дефолтный порт поставки — 19000; три демо-файла переопределяют приём.
    assert sorted({c.port for c in configs if c.port is not None}) == [19000]
