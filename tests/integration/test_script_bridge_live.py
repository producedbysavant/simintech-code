"""Живой прогон моста: SimInTech, реальный COM.

Проверяет то, что фейки подтвердить не могут: скрипт действительно исполняется
средой, результат доходит файлом, а прежний скрипт страницы возвращается на
место **таким, каким был** — включая операторы сравнения, которые среда хранит
кодами `#60` и `#62`.

Возврат сверяется по **сырым выгрузкам** проекта, а не чтением через мост:
`capture_script` убран — надёжного способа прочитать скрипт *текущей* страницы
у COM нет (`SetPageScript` пишет в текущую страницу и о прежнем содержимом не
сообщает ничего). Сверка «сам с собой» подтвердила бы успех при любой поломке.
"""

import pytest

from simintech_api.catalog import decode_xprt
from simintech_api.core.project import Project
from simintech_api.core.script_bridge import ScriptBridge
from simintech_api.exceptions import ScriptBridgeUnsafeStateError
from simintech_api.script_probe import (
    decode_xprt_value,
    parse_xprt_script_records,
)

pytestmark = pytest.mark.integration

#: Скрипт с операторами сравнения, табуляцией и кириллицей. Операторы здесь
#: критичнее прочего: в выгрузке они кодируются как `#60`/`#62`, и разбор,
#: знающий только про перевод строки, вернул бы скрипт нерабочим.
SCRIPT_WITH_OPERATORS = (
    "if firststep then begin\r\n"
    "\tif (a <= b) and (b <> 0) then\r\n"
    "\t\tx = a;\r\n"
    "end;\r\n"
)


def test_bridge_returns_page_object_count(client, tmp_path):
    """Проба читает число объектов страницы — и оно сходится с COM-счётчиком."""
    project = Project.from_template(client)
    project.set_calc_end_time(1.0)
    try:
        bridge = ScriptBridge(client, project.id)
        result = bridge.run_probe(
            'writelnutf8(fid, "objects=" + floattostr('
            "getobjcount(getcurrentcontainer)));",
            tmp_path / "probe.txt")

        assert result.complete, "скрипт не дошёл до маркера завершения"
        count_by_com = client.call("GetPageObjectCount", project.id)
        assert f"objects={count_by_com}" in result.lines, (
            f"язык и COM видят разное число объектов: {result.lines}")
    finally:
        # Уборка не зависит от исправления: на коде без остановки проект
        # остаётся инициализированным, а закрывать инициализированный проект
        # этим тестом не измерялось. Остановка безвредна при любом состоянии.
        try:
            client.call("ProjectStop", project.id)
        except Exception:                                             # noqa: BLE001
            pass
        project.close()


def _records(client, project, path) -> list:
    """Сырые скриптовые записи выгрузки — независимо от средств моста.

    Кодировку разбирает библиотечный `decode_xprt` (по байтам, с учётом BOM), а
    не `read_text`: подстановка U+FFFD скрыла бы порчу файла, ради обнаружения
    которой тест и написан. Копия, а не импорт из соседнего живого теста: живые
    тесты не должны зависеть друг от друга.
    """
    client.call("SaveProjectXML", project.id, str(path))
    return parse_xprt_script_records(decode_xprt(path.read_bytes()))


def test_probe_survives_a_foreign_procedure_that_assigns_fid(client, tmp_path):
    """Чужое присваивание `fid` не уводит дескриптор моста — проба доходит.

    Форма взята у вендорской процедуры `export_1layer_topology` из поставки: она
    присваивает `fid = createfile(...)`, **не объявляя** имя, и освобождает
    дескриптор в конце. Пока мост писал через то же имя, это присваивание уводило
    **его** дескриптор: конечный маркер уходил в чужой уже освобождённый файл,
    скрипт обрывался, и мост сообщал «нет ровно одной пары маркеров». Измерено
    2026-09-24 на поставке — и на этой форме, и на настоящей вендорской процедуре.

    Проверяются три вещи, и ни одну нельзя опустить:

    * проба **полна** — дескриптор моста пережил чужой вызов;
    * чужой файл создан и заполнен — процедура действительно выполнилась, а не
      была пропущена (иначе тест зеленел бы на скрипте, который её не позвал);
    * строка, записанная телом **после** чужого вызова через `br_writeln`, попала
      в результат: безопасный путь записи работает, а не только маркеры моста.

    Строка до вызова пишется через `fid` намеренно: она доказывает, что приманка
    связана с дескриптором моста, то есть прежние тела проб работают без правок.
    """
    project = Project.from_template(client)
    project.set_calc_end_time(1.0)
    foreign = tmp_path / "foreign.txt"
    foreign_literal = str(foreign).replace("\\", "/")
    body = (
        "procedure vendor_like;\n"
        f'  fid = createfile("{foreign_literal}", -1);\n'
        '  writelnutf8(fid, "foreign-line");\n'
        "  freeobject(fid);\n"
        "end;\n"
        'writelnutf8(fid, "before-foreign=ok");\n'
        "vendor_like;\n"
        'br_writeln("after-foreign=ok");\n'
    )
    try:
        bridge = ScriptBridge(client, project.id)
        result = bridge.run_probe(body, tmp_path / "probe.txt")

        assert result.complete, "скрипт не дошёл до маркера завершения"
        assert "before-foreign=ok" in result.lines, (
            f"тело потеряло результат до чужого вызова — приманка `fid` не "
            f"связана с дескриптором моста: {result.lines}")
        assert "after-foreign=ok" in result.lines, (
            f"безопасный путь записи не дошёл: {result.lines}")
        assert foreign.exists(), (
            "чужой файл не создан: чужая процедура не выполнилась, и проверять "
            "устойчивость моста не на чем")
        assert "foreign-line" in foreign.read_text(encoding="utf-8"), (
            "чужой файл пуст — процедура не записала в него")
    finally:
        project.close()


def test_probe_restores_page_script(client, tmp_path):
    """Прежний скрипт страницы возвращается — сверка по сырой выгрузке.

    Сверяются **все** скриптовые записи проекта, а не одна текущая: это тот же
    уровень, на котором измерено «`SetPageScript` меняет ровно одну запись», и
    он ловит возврат в чужую страницу — то, чем и был дефект 2026-09-22.

    Непустота снимка проверяется до сверки, хотя `capture_script` и убран: иначе
    на двух пустых записях `before == after` истинно при любой поломке, и тест
    не измерял бы ничего. Скрипт с операторами сравнения (`#60`/`#62` в выгрузке)
    стоит здесь именно ради этого: он и доказывает, что в снимке есть что
    сверять.
    """
    project = Project.from_template(client)
    project.set_calc_end_time(1.0)
    page = project.get_main_page()
    page.activate()
    client.call("SetPageScript", project.id, SCRIPT_WITH_OPERATORS, 1)
    try:
        bridge = ScriptBridge(client, project.id)
        before = _records(client, project, tmp_path / "b.xprt")
        assert any(decode_xprt_value(record) == SCRIPT_WITH_OPERATORS
                   for record in before), (
            "поставленного скрипта в выгрузке нет — сверять нечего: до и после "
            "были бы две пустые записи, и тест прошёл бы, ничего не проверив")
        bridge.run_probe('writelnutf8(fid, "x");', tmp_path / "probe.txt")
        after = _records(client, project, tmp_path / "a.xprt")
        lost = [i for i in range(len(before)) if before[i] != after[i]]
        assert lost == [], (
            f"скрипт страницы после пробы не совпал с прежним — изменились "
            f"записи {lost}; в записи {lost[0]} было {before[lost[0]][:60]!r}, "
            f"стало {after[lost[0]][:60]!r}")
    finally:
        # Уборка не зависит от исправления: на коде без остановки проект
        # остаётся инициализированным, а закрывать инициализированный проект
        # этим тестом не измерялось. Остановка безвредна при любом состоянии.
        try:
            client.call("ProjectStop", project.id)
        except Exception:                                             # noqa: BLE001
            pass
        project.close()


# ─── Жизненный цикл расчёта ──────────────────────────────────────────
#
# Замерено (automation/lifecycle-probe/03f, 05, 11, 12): пока проект
# инициализирован (`GetProjectStateFlag != 0`), среда отвергает добавление блока
# к схеме, и отказ приходит модальным окном, которое внешний COM-клиент снять
# не может — вызов стоит, пока окно не закроет человек. Проба запускает расчёт
# сама, поэтому обязана и остановить его.

WM_CLOSE = 0x0010
DIALOG_CLASS = "#32770"


def _own_dialogs(pid: int) -> list:
    """Видимые модальные окна ПРОЦЕССА `pid`. Чужие не трогаются.

    Сторож нужен только тесту и только затем, чтобы сломанное состояние дало
    **красный** результат, а не зависание до таймаута: без него отказ среды
    выглядит как «тест не закончился». Снимать окна в библиотеке нельзя — это
    подавление диагностики среды, а не починка.
    """
    import ctypes
    import ctypes.wintypes as wt

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    found: list = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _lp):
        owner = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if (int(owner.value) == pid and cls.value == DIALOG_CLASS
                and user32.IsWindowVisible(hwnd)):
            found.append(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    return found


def test_probe_leaves_project_stopped_and_editable(client, tmp_path):
    """После пробы расчёт остановлен, и модель действительно правится.

    Утверждается **симптом** (правку можно внести), а не только флаг: флаг —
    объяснение симптома. Тест двусторонний и потому не может позеленеть даром:
    `время > 0` доказывает, что расчёт шёл (иначе тест удовлетворялся бы
    проектом, который ничего не делал), а успешная правка — что состояние
    вернулось в «остановлен». На коде без остановки красно ровно здесь.
    """
    import ctypes
    import threading
    import time

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    pid = client.get_process_id()

    project = Project.from_template(client)
    project.set_calc_end_time(5.0)
    try:
        page = project.get_main_page()
        page.activate()
        bridge = ScriptBridge(client, project.id)

        assert int(client.call("GetProjectStateFlag", project.id)) == 0, (
            "предусловие теста: проект обязан быть остановлен до пробы")
        result = bridge.run_probe('writelnutf8(fid, "x");',
                                  tmp_path / "probe.txt")
        assert result.complete, "проба не дошла до маркера завершения"

        advanced = float(client.call("GetProjectTime", project.id))
        assert advanced > 0, (
            "модельное время не сдвинулось — значит расчёт и не запускался, и "
            "проверять жизненный цикл не на чем")

        state = int(client.call("GetProjectStateFlag", project.id))
        assert state == 0, (
            f"после пробы проект остался инициализированным (состояние {state}): "
            "в этом состоянии среда отвергает добавление блока к схеме")

        stop_flag = threading.Event()

        def watchdog():
            """Закрыть СВОЁ окно, если оно появится: иначе тест повиснет."""
            deadline = time.monotonic() + 20.0
            while not stop_flag.is_set() and time.monotonic() < deadline:
                for hwnd in _own_dialogs(pid):
                    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                time.sleep(0.2)

        thread = threading.Thread(target=watchdog, daemon=True)
        thread.start()
        try:
            block = page.create_block("Константа", 0, 0, width=60, height=40)
            assert block.id != 0
        finally:
            stop_flag.set()
            thread.join(timeout=1.0)
    finally:
        # Уборка не зависит от исправления: на коде без остановки проект
        # остаётся инициализированным, а закрывать инициализированный проект
        # этим тестом не измерялось. Остановка безвредна при любом состоянии.
        try:
            client.call("ProjectStop", project.id)
        except Exception:                                             # noqa: BLE001
            pass
        project.close()


def test_probe_refuses_to_destroy_a_running_calculation(client, tmp_path):
    """Идущий расчёт не уничтожается: проба отказывает, ничего не тронув.

    `ProjectStart` — инициализация, и модельное время при ней сбрасывается
    (замер 8: 0.02 -> 0.001). Проба на уже считающем проекте молча убила бы
    расчёт вызывающего, поэтому она обязана отказать ДО любых изменений.

    Проверяется наблюдаемое: время и состояние до и после отказа совпадают, и
    расчёт продолжает двигаться — то есть он не «остановлен отказом», а
    оставлен как был.
    """
    project = Project.from_template(client)
    project.set_calc_end_time(5.0)
    sim = project.simulation()
    try:
        page = project.get_main_page()
        page.activate()
        sim.start()
        sim.step()
        before_time = float(client.call("GetProjectTime", project.id))
        before_state = int(client.call("GetProjectStateFlag", project.id))
        assert before_state != 0, "предусловие: расчёт обязан идти"

        bridge = ScriptBridge(client, project.id)
        with pytest.raises(ScriptBridgeUnsafeStateError) as exc:
            bridge.run_probe('writelnutf8(fid, "x");', tmp_path / "probe.txt")
        assert "не находится в остановленном состоянии" in str(exc.value), (
            f"отказ не назвал причину: {exc.value!r}")

        assert float(client.call("GetProjectTime", project.id)) == before_time, (
            "модельное время изменилось — проба тронула чужой расчёт вопреки "
            "обещанию «проект не тронут»")
        assert int(client.call("GetProjectStateFlag", project.id)) == before_state

        sim.step()
        assert float(client.call("GetProjectTime", project.id)) > before_time, (
            "расчёт не двигается после отказа — его не «оставили как был», "
            "а сломали")
    finally:
        try:
            sim.stop()
        except Exception:                                             # noqa: BLE001
            pass
        project.close()
