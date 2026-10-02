"""Тесты COMClient с фейковым сервером (без реального COM).

comtypes на Linux падает при импорте (COM доступен только на Windows),
поэтому модуль comtypes и comtypes.client подменяются фейками в sys.modules.
Проверяется логика клиента: connect, open_project, find_signal, обработка
ошибок, диспетчеризация Read/Write по DataType.
"""

import os
import sys
import types

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest

from simintech_api.exceptions import (ComCallError, ComConnectionError,
                                      PackError)
from simintech_api.model import TDataDescriptor


class FakeServer:
    """Фейковый IMVTU_Server с минимальным набором методов."""

    def __init__(self):
        self.calls = []
        self._project_id = 42
        self._next_signal_id = 1000

    def SetNoCloseAppFlag(self, v):
        self.calls.append(("SetNoCloseAppFlag", v))

    def SetSilentMode(self, v):
        self.calls.append(("SetSilentMode", v))

    def GetProcessID(self):
        self.calls.append(("GetProcessID",))
        return 12345

    def OpenProject(self, path):
        self.calls.append(("OpenProject", path))
        return self._project_id

    def NewProject(self):
        self.calls.append(("NewProject",))
        return self._project_id

    def FindSignalData(self, name, project_id):
        self.calls.append(("FindSignalData", name, project_id))
        desc = TDataDescriptor()
        desc.DataId = self._next_signal_id
        desc.DataType = 0  # double
        return desc

    def ReadAsFloat(self, desc):
        self.calls.append(("ReadAsFloat", desc.DataId, desc.DataType))
        return 7.5

    def WriteAsFloat(self, desc, value):
        self.calls.append(("WriteAsFloat", desc.DataId, desc.DataType, value))

    def CloseProject(self, project_id):
        self.calls.append(("CloseProject", project_id))

    def ClosePack(self, pack_id):
        self.calls.append(("ClosePack", pack_id))

    def OpenTemplate(self, template):
        self.calls.append(("OpenTemplate", template))
        return self._project_id

    def SetLayerProp(self, project_id, layer_no, name, value):
        self.calls.append(("SetLayerProp", project_id, layer_no, name, value))
        return 777

    # Перечисление проектов: [out]-параметры comtypes отдаёт кортежем.
    def GetProjectCount(self):
        self.calls.append(("GetProjectCount",))
        return (2,)

    def GetProjectIdByNumber(self, number):
        self.calls.append(("GetProjectIdByNumber", number))
        return (42,)

    def GetProjectIdByFileName(self, file_name):
        self.calls.append(("GetProjectIdByFileName", file_name))
        return (43,)

    def GetActiveProject(self):
        self.calls.append(("GetActiveProject",))
        return (42,)

    def GetOpenedFileName(self, project_id):
        self.calls.append(("GetOpenedFileName", project_id))
        return (FakeVariant(r"C:\models\m.prt"),)


class FakeVariant:
    """VARIANT-значение comtypes: настоящий ответ приходит обёрнутым в `.value`."""

    def __init__(self, value):
        self.value = value


def test_connect_initializes_com_for_current_thread(monkeypatch):
    """connect() инициализирует COM в текущем потоке.

    COM привязан к потоку. Серверы, выполняющие обработчики в пуле потоков
    (MCP/FastMCP), без этого падают с CO_E_NOTINITIALIZED («Не был произведён
    вызов CoInitialize»). Проверено на реальном SimInTech.
    """
    fake = FakeServer()
    calls = []
    client = _make_client(monkeypatch, fake)
    fake_comtypes = sys.modules["comtypes"]
    fake_comtypes.CoInitializeEx = lambda mode: calls.append(mode)

    client.connect()

    assert calls == [fake_comtypes.COINIT_APARTMENTTHREADED]


def test_connect_tolerates_changed_apartment_mode(monkeypatch):
    """RPC_E_CHANGED_MODE не считается ошибкой: поток уже инициализирован."""
    fake = FakeServer()
    _install_fake_comtypes(monkeypatch, fake)

    def raise_changed_mode(mode):
        exc = OSError("changed mode")
        exc.winerror = -2147417850
        raise exc

    sys.modules["comtypes"].CoInitializeEx = raise_changed_mode

    client = _make_client(monkeypatch, fake)
    client.connect()  # не должно бросить

    assert client.connected


def _install_fake_comtypes(monkeypatch, fake: FakeServer):
    """Подменить comtypes и comtypes.client в sys.modules фейками."""
    fake_comtypes = types.ModuleType("comtypes")
    fake_client = types.ModuleType("comtypes.client")
    fake_client.CreateObject = lambda progid: fake
    fake_comtypes.client = fake_client
    # Структуры для TDataDescriptor (model.py импортирует их из comtypes)
    from simintech_api import model as _model

    class FakeStructure:
        _fields_ = [("DataId", "int"), ("DataType", "int")]

        def __init__(self, data_id=0, data_type=0):
            self.DataId = data_id
            self.DataType = data_type

    fake_comtypes.Structure = FakeStructure
    fake_comtypes.c_int64 = "int"
    fake_comtypes.c_long = "int"
    # COM инициализируется по потокам; connect() вызывает CoInitializeEx.
    fake_comtypes.COINIT_APARTMENTTHREADED = 2
    fake_comtypes.COINIT_MULTITHREADED = 0
    fake_comtypes.CoInitializeEx = lambda mode: None

    monkeypatch.setitem(sys.modules, "comtypes", fake_comtypes)
    monkeypatch.setitem(sys.modules, "comtypes.client", fake_client)

    # Пересоздаём TDataDescriptor с фейковой структурой
    _model.TDataDescriptor = type("TDataDescriptor", (FakeStructure,), {})


def _make_client(monkeypatch, fake: FakeServer):
    from simintech_api.core import com_client as cc

    _install_fake_comtypes(monkeypatch, fake)
    monkeypatch.setattr(sys, "platform", "win32")
    # Job-объект (KILL_ON_JOB_CLOSE) — Win32-путь: на Linux настоящие
    # функции недоступны, поэтому по умолчанию подменяются фейками
    # («назначение удалось, процесс мёртв»). Тесты защиты и уборки
    # подменяют их сами.
    monkeypatch.setattr(cc, "assign_kill_on_close", lambda pid: (777, 0))
    monkeypatch.setattr(cc, "close_handle", lambda handle: None)
    monkeypatch.setattr(cc, "is_process_alive", lambda pid: False)
    return cc.COMClient(silent_mode=True)


# ─── Тесты ─────────────────────────────────────────────────────────


def test_connect_success(monkeypatch):
    fake = FakeServer()
    client = _make_client(monkeypatch, fake)

    snapshots = [set(), {12345}]
    monkeypatch.setattr(
        "simintech_api.core.com_client.get_mmain_pids",
        lambda: snapshots.pop(0),
    )

    client.connect()
    assert client.connected
    assert ("SetNoCloseAppFlag", 1) in fake.calls
    assert ("SetSilentMode", 1) in fake.calls


def test_connect_platform_restricted(monkeypatch):
    from simintech_api.core.com_client import COMClient

    monkeypatch.setattr(sys, "platform", "linux")
    client = COMClient()
    with pytest.raises(ComConnectionError):
        client.connect()


def test_close_pack_refuses_invalid_id(monkeypatch):
    """`ClosePack` с id ≤ 0 не доходит до COM: он роняет mmain (замер 01.10.2026).

    `-1` — достижимое значение: столько возвращает `GetPackIdByFileName` для
    неоткрытого пакета. Защита стоит здесь, где id попадает в COM (ревью
    code#23), а не только этажом выше, в `Pack.close`.
    """
    fake = FakeServer()
    client = _make_client(monkeypatch, fake)
    client.connect()

    with pytest.raises(PackError):
        client.close_pack(-1)
    with pytest.raises(PackError):
        client.close_pack(0)

    assert ("ClosePack", -1) not in fake.calls
    assert ("ClosePack", 0) not in fake.calls


def test_close_pack_passes_valid_id(monkeypatch):
    """Положительный id уходит в COM как есть."""
    fake = FakeServer()
    client = _make_client(monkeypatch, fake)
    client.connect()

    client.close_pack(42)

    assert ("ClosePack", 42) in fake.calls


def test_open_project(monkeypatch):
    fake = FakeServer()
    client = _make_client(monkeypatch, fake)
    client.connect()
    pid = client.open_project("model.prt")
    assert pid == 42
    assert ("OpenProject", "model.prt") in fake.calls


def test_new_project(monkeypatch):
    fake = FakeServer()
    client = _make_client(monkeypatch, fake)
    client.connect()
    assert client.new_project() == 42


def test_get_process_id(monkeypatch):
    fake = FakeServer()
    client = _make_client(monkeypatch, fake)
    client.connect()
    assert client.get_process_id() == 12345


def test_find_signal_returns_descriptor(monkeypatch):
    fake = FakeServer()
    client = _make_client(monkeypatch, fake)
    client.connect()
    desc = client.find_signal("sig", 42)
    assert isinstance(desc, TDataDescriptor)
    assert desc.DataId == 1000
    assert desc.DataType == 0
    assert desc.is_valid


def test_call_before_connect_raises(monkeypatch):
    fake = FakeServer()
    client = _make_client(monkeypatch, fake)
    with pytest.raises(ComConnectionError):
        client.call("OpenProject", "x.prt")


def test_call_missing_method_raises(monkeypatch):
    fake = FakeServer()
    client = _make_client(monkeypatch, fake)
    client.connect()
    # Метода нет в фейковом сервере
    fake.__class__.__delattr__  # noqa — гарантируем отсутствие метода
    with pytest.raises(ComCallError):
        client.call("MissingMethod")


def test_typed_read_write_via_signal(monkeypatch):
    """Диспетчеризация Read/Write по DataType через Signal."""
    fake = FakeServer()
    client = _make_client(monkeypatch, fake)
    client.connect()

    from simintech_api import Project, Signal
    prj = Project(client, 42)
    desc = client.find_signal("sig", 42)
    sig = Signal(prj, desc, "sig")
    assert sig.read() == 7.5
    sig.write(3.0)
    assert ("ReadAsFloat", 1000, 0) in fake.calls
    assert ("WriteAsFloat", 1000, 0, 3.0) in fake.calls


def test_connect_classifies_new_pid_as_owned(monkeypatch):
    """PID, появившийся между snapshots, классифицируется как owned."""
    from simintech_api.core.com_client import SessionOwnership

    fake = FakeServer()
    client = _make_client(monkeypatch, fake)

    snapshots = [set(), {12345}]
    monkeypatch.setattr(
        "simintech_api.core.com_client.get_mmain_pids",
        lambda: snapshots.pop(0),
    )

    client.connect()

    assert client.session_pid == 12345
    assert client.ownership is SessionOwnership.OWNED


def test_connect_classifies_preexisting_pid_as_external(monkeypatch):
    """PID, существовавший до connect, не может быть убит клиентом."""
    from simintech_api.core.com_client import SessionOwnership

    fake = FakeServer()
    client = _make_client(monkeypatch, fake)

    snapshots = [{12345}, {12345}]
    monkeypatch.setattr(
        "simintech_api.core.com_client.get_mmain_pids",
        lambda: snapshots.pop(0),
    )

    client.connect()

    assert client.session_pid == 12345
    assert client.ownership is SessionOwnership.EXTERNAL
    assert ("SetNoCloseAppFlag", 1) not in fake.calls
    assert ("SetSilentMode", 1) not in fake.calls


def test_connect_classifies_unobserved_pid_as_unknown(monkeypatch):
    """Без before/after подтверждения ownership остаётся неизвестным."""
    from simintech_api.core.com_client import SessionOwnership

    fake = FakeServer()
    client = _make_client(monkeypatch, fake)

    snapshots = [set(), set()]
    monkeypatch.setattr(
        "simintech_api.core.com_client.get_mmain_pids",
        lambda: snapshots.pop(0),
    )

    client.connect()

    assert client.session_pid == 12345
    assert client.ownership is SessionOwnership.UNKNOWN


def test_shutdown_owned_session_waits_then_kills_exact_pid(monkeypatch):
    """Managed shutdown ждёт PID и убивает его, если он всё ещё жив."""
    from simintech_api.core import com_client as cc
    from simintech_api.core.com_client import SessionOwnership

    fake = FakeServer()
    client = _make_client(monkeypatch, fake)

    snapshots = [set(), {12345}]
    monkeypatch.setattr(cc, "get_mmain_pids", lambda: snapshots.pop(0))

    waited = []
    monkeypatch.setattr(
        cc,
        "wait_for_pid_exit",
        lambda pid, timeout=5.0: waited.append((pid, timeout)) or False,
    )
    killed = []
    monkeypatch.setattr(
        cc,
        "_kill_pids",
        lambda pids: killed.append(list(pids)),
    )

    client.connect()
    assert client.ownership is SessionOwnership.OWNED

    client.shutdown()

    assert waited == [(12345, 5.0)]
    assert killed == [[12345]]
    assert not client.connected


def test_shutdown_owned_session_does_not_kill_after_graceful_exit(monkeypatch):
    """Если exact PID ушёл после release, fallback terminate не вызывается."""
    from simintech_api.core import com_client as cc
    from simintech_api.core.com_client import SessionOwnership

    fake = FakeServer()
    client = _make_client(monkeypatch, fake)

    snapshots = [set(), {12345}]
    monkeypatch.setattr(cc, "get_mmain_pids", lambda: snapshots.pop(0))
    monkeypatch.setattr(
        cc,
        "wait_for_pid_exit",
        lambda pid, timeout=5.0: True,
    )

    killed = []
    monkeypatch.setattr(cc, "_kill_pids", lambda pids: killed.append(list(pids)))

    client.connect()
    assert client.ownership is SessionOwnership.OWNED

    client.shutdown()

    assert killed == []


def test_shutdown_external_session_never_kills(monkeypatch):
    """Attached/external session не завершается managed shutdown."""
    from simintech_api.core import com_client as cc
    from simintech_api.core.com_client import SessionOwnership

    fake = FakeServer()
    client = _make_client(monkeypatch, fake)

    snapshots = [{12345}, {12345}]
    monkeypatch.setattr(cc, "get_mmain_pids", lambda: snapshots.pop(0))

    waited = []
    monkeypatch.setattr(
        cc,
        "wait_for_pid_exit",
        lambda pid, timeout=5.0: waited.append((pid, timeout)) or False,
    )
    killed = []
    monkeypatch.setattr(cc, "_kill_pids", lambda pids: killed.append(list(pids)))

    client.connect()
    assert client.ownership is SessionOwnership.EXTERNAL

    client.shutdown()

    assert waited == []
    assert killed == []
    assert not client.connected


def test_shutdown_unknown_session_does_not_kill_by_default(monkeypatch):
    """UNKNOWN-сессия не даёт shutdown права завершать процесс."""
    from simintech_api.core.com_client import SessionOwnership
    from simintech_api.utils import processes as proc

    fake = FakeServer()
    client = _make_client(monkeypatch, fake)
    snapshots = [set(), set()]
    monkeypatch.setattr(
        "simintech_api.core.com_client.get_mmain_pids",
        lambda: snapshots.pop(0),
    )
    client.connect()
    assert client.ownership is SessionOwnership.UNKNOWN

    killed = []
    monkeypatch.setattr(proc, "_pids_wmic", lambda: set())
    monkeypatch.setattr(proc, "_pids_tasklist", lambda: set())
    monkeypatch.setattr(proc, "_pids_powershell", lambda: set())
    monkeypatch.setattr(
        proc.subprocess,
        "run",
        lambda *a, **k: killed.append(a[0]) or None,
    )

    client.shutdown()
    assert killed == []


def test_shutdown_kills_explicit_pids(monkeypatch):
    """shutdown(kill_pids=...) завершает ТОЛЬКО переданные PID'ы."""
    from simintech_api.utils import processes as proc

    fake = FakeServer()
    client = _make_client(monkeypatch, fake)
    client.connect()

    killed = []
    monkeypatch.setattr(proc, "_pids_wmic", lambda: set())
    monkeypatch.setattr(proc, "_pids_tasklist", lambda: set())
    monkeypatch.setattr(proc, "_pids_powershell", lambda: set())
    monkeypatch.setattr(proc.subprocess, "run",
                        lambda *a, **k: killed.append(a[0]) or None)
    client.shutdown(kill_pids=[999, 888])
    # Каждый PID убивается отдельным taskkill
    assert killed
    assert all(args and args[0] == "taskkill" for args in killed)
    assert ["taskkill", "/F", "/PID", "999"] in killed
    assert ["taskkill", "/F", "/PID", "888"] in killed


def test_process_scanners_survive_undecodable_output(monkeypatch):
    """Скан процессов переживает недекодируемый вывод (cp866 под PYTHONUTF8).

    Живой случай 01.10.2026: под `PYTHONUTF8=1` текстовый режим `subprocess`
    декодирует вывод как UTF-8, а `tasklist`/`wmic` на русской консоли пишут
    в cp866 — поток-читатель падал `UnicodeDecodeError`, и фикстура владения
    процессами срывалась в setup. Лечение — `errors="replace"` у всех трёх
    сканеров; тест держит флаг (находка ревью: ветка была без сторожа).
    """
    import sys

    from simintech_api.utils import processes as proc

    monkeypatch.setattr(sys, "platform", "win32")
    seen = []

    def fake_run(argv, **kwargs):
        seen.append(kwargs)
        payload = "Имя образа: mmain.exe 1234\r\n".encode("cp866")
        # Строгий декодер на этом выводе падает — как падал поток-читатель.
        text = payload.decode(kwargs.get("encoding") or "utf-8",
                              errors=kwargs.get("errors", "strict"))

        class _Completed:
            stdout = text

        return _Completed()

    monkeypatch.setattr(proc.subprocess, "run", fake_run)
    pids = proc.get_mmain_pids()

    assert len(seen) == 3, "опрошены не все три сканера"
    assert pids == set(), (
        "подделка не изображает mmain — проверяется только устойчивость кода")


def test_open_template_passes_path_and_returns_id(monkeypatch):
    """open_template() — тонкая обёртка: путь уходит в COM как есть."""
    fake = FakeServer()
    client = _make_client(monkeypatch, fake)
    client.connect()

    assert client.open_template(r"C:\TPL\Схема.prt") == 42
    assert ("OpenTemplate", r"C:\TPL\Схема.prt") in fake.calls


def test_set_layer_prop_stringifies_value(monkeypatch):
    """Значение свойства слоя уходит строкой: COM ждёт BSTR.

    Число без преобразования comtypes отверг бы, поэтому контракт «строка»
    надо удерживать явно.
    """
    fake = FakeServer()
    client = _make_client(monkeypatch, fake)
    client.connect()

    handle = client.set_layer_prop(42, 0, "endtime", 2.5)

    assert handle == 777
    assert ("SetLayerProp", 42, 0, "endtime", "2.5") in fake.calls


def test_set_layer_prop_reports_zero_when_layer_rejects(monkeypatch):
    """Возврат 0 означает, что свойство не принято (нет расчётного слоя)."""
    fake = FakeServer()
    client = _make_client(monkeypatch, fake)
    client.connect()
    monkeypatch.setattr(fake, "SetLayerProp", lambda *a: 0)

    assert client.set_layer_prop(42, 0, "endtime", "1") == 0


# ─── Перечисление открытых проектов ────────────────────────────────
#
# Методы адресуются номером или именем файла проекта, а не объектом, и живут
# на клиенте. На живом SimInTech не проверены: тесты фиксируют имя метода,
# порядок аргументов и разбор [out]-результата.


def test_get_project_count_reads_out_value(monkeypatch):
    fake = FakeServer()
    client = _make_client(monkeypatch, fake)
    client.connect()

    assert client.get_project_count() == 2
    assert ("GetProjectCount",) in fake.calls


def test_get_project_id_by_number_passes_number(monkeypatch):
    fake = FakeServer()
    client = _make_client(monkeypatch, fake)
    client.connect()

    assert client.get_project_id_by_number(1) == 42
    assert ("GetProjectIdByNumber", 1) in fake.calls


def test_get_project_id_by_file_name_passes_name(monkeypatch):
    fake = FakeServer()
    client = _make_client(monkeypatch, fake)
    client.connect()

    assert client.get_project_id_by_file_name("model.prt") == 43
    assert ("GetProjectIdByFileName", "model.prt") in fake.calls


def test_get_active_project_reads_out_value(monkeypatch):
    fake = FakeServer()
    client = _make_client(monkeypatch, fake)
    client.connect()

    assert client.get_active_project() == 42
    assert ("GetActiveProject",) in fake.calls


def test_get_opened_file_name_unwraps_variant(monkeypatch):
    """`[out] VARIANT*` приходит обёрнутым в `.value` — разворачиваем."""
    fake = FakeServer()
    client = _make_client(monkeypatch, fake)
    client.connect()

    assert client.get_opened_file_name(42) == r"C:\models\m.prt"
    assert ("GetOpenedFileName", 42) in fake.calls


def test_get_opened_file_name_returns_empty_string_for_none(monkeypatch):
    """`None` в VARIANT — пустая строка: проект не связан с файлом."""
    fake = FakeServer()
    client = _make_client(monkeypatch, fake)
    client.connect()
    monkeypatch.setattr(fake, "GetOpenedFileName", lambda *a: (None,))

    assert client.get_opened_file_name(42) == ""


@pytest.mark.parametrize("method,attr", [
    ("get_project_count", "GetProjectCount"),
    ("get_active_project", "GetActiveProject"),
])
@pytest.mark.parametrize("answer", [None, ()])
def test_project_enumeration_refuses_without_out_value(monkeypatch, method, attr,
                                                       answer):
    """Пустой результат — понятный отказ с именем метода, а не TypeError."""
    fake = FakeServer()
    client = _make_client(monkeypatch, fake)
    client.connect()
    monkeypatch.setattr(fake, attr, lambda *a: answer)

    with pytest.raises(ComCallError) as exc:
        getattr(client, method)()

    assert attr in str(exc.value)


# ─── Job-объект: уборка процесса OWNED-сессии ──────────────────────
#
# Процесс OWNED-сессии назначается в job с KILL_ON_JOB_CLOSE (живой замер
# 02.10.2026: назначение существующего -Embedding-процесса и снятие ядром
# при смерти держателя, n=2). Контракт клиента: OWNED защищается,
# EXTERNAL/UNKNOWN — никогда; отказ назначения не ломает сессию;
# disconnect живой процесс не убивает (закрывает хэндл только у мёртвого).


def test_connect_owned_assigns_kill_on_close_job(monkeypatch):
    """OWNED-сессия назначается в job сразу при connect."""
    from simintech_api.core import com_client as cc

    fake = FakeServer()
    client = _make_client(monkeypatch, fake)
    snapshots = [set(), {12345}]
    monkeypatch.setattr(cc, "get_mmain_pids", lambda: snapshots.pop(0))
    assigned = []
    monkeypatch.setattr(cc, "assign_kill_on_close",
                        lambda pid: assigned.append(pid) or (777, 0))

    client.connect()

    assert assigned == [12345]
    assert client.job_handle == 777
    assert client.job_error == 0


def test_connect_external_session_never_assigns_job(monkeypatch):
    """Чужой (EXTERNAL) процесс в job не назначается никогда."""
    from simintech_api.core import com_client as cc

    fake = FakeServer()
    client = _make_client(monkeypatch, fake)
    snapshots = [{12345}, {12345}]
    monkeypatch.setattr(cc, "get_mmain_pids", lambda: snapshots.pop(0))
    assigned = []
    monkeypatch.setattr(cc, "assign_kill_on_close",
                        lambda pid: assigned.append(pid) or (777, 0))

    client.connect()

    assert assigned == []
    assert client.job_handle is None


def test_connect_survives_job_refusal(monkeypatch):
    """Отказ назначения не является отказом сессии (работа без уборки)."""
    from simintech_api.core import com_client as cc

    fake = FakeServer()
    client = _make_client(monkeypatch, fake)
    snapshots = [set(), {12345}]
    monkeypatch.setattr(cc, "get_mmain_pids", lambda: snapshots.pop(0))
    monkeypatch.setattr(cc, "assign_kill_on_close", lambda pid: (None, 5))

    client.connect()

    assert client.connected
    assert client.job_handle is None
    assert client.job_error == 5


def test_disconnect_keeps_job_while_process_alive(monkeypatch):
    """disconnect не завершает живой процесс: хэндл job'а — у клиента."""
    from simintech_api.core import com_client as cc

    fake = FakeServer()
    client = _make_client(monkeypatch, fake)
    snapshots = [set(), {12345}]
    monkeypatch.setattr(cc, "get_mmain_pids", lambda: snapshots.pop(0))
    closed = []
    monkeypatch.setattr(cc, "close_handle",
                        lambda handle: closed.append(handle))
    monkeypatch.setattr(cc, "is_process_alive", lambda pid: True)

    client.connect()
    client.disconnect()

    assert closed == []
    assert client.job_handle == 777


def test_disconnect_closes_job_when_process_dead(monkeypatch):
    """Мёртвый процесс: хэндл job'а закрывается (закрытие ничего не завершает)."""
    from simintech_api.core import com_client as cc

    fake = FakeServer()
    client = _make_client(monkeypatch, fake)
    snapshots = [set(), {12345}]
    monkeypatch.setattr(cc, "get_mmain_pids", lambda: snapshots.pop(0))
    closed = []
    monkeypatch.setattr(cc, "close_handle",
                        lambda handle: closed.append(handle))
    monkeypatch.setattr(cc, "is_process_alive", lambda pid: False)

    client.connect()
    client.disconnect()

    assert closed == [777]
    assert client.job_handle is None


def test_shutdown_closes_job_after_termination(monkeypatch):
    """После завершения процесса сессии хэндл job'а закрывается."""
    from simintech_api.core import com_client as cc

    fake = FakeServer()
    client = _make_client(monkeypatch, fake)
    snapshots = [set(), {12345}]
    monkeypatch.setattr(cc, "get_mmain_pids", lambda: snapshots.pop(0))
    monkeypatch.setattr(cc, "wait_for_pid_exit", lambda pid, timeout=5.0: True)
    killed = []
    monkeypatch.setattr(cc, "_kill_pids", lambda pids: killed.append(list(pids)))
    closed = []
    monkeypatch.setattr(cc, "close_handle",
                        lambda handle: closed.append(handle))
    monkeypatch.setattr(cc, "is_process_alive", lambda pid: False)

    client.connect()
    client.shutdown()

    assert killed == []
    assert closed == [777]
    assert client.job_handle is None
