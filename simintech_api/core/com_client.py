"""COM-клиент: низкоуровневый доступ к серверу SimInTech (IMVTU_Server).

Работает только на Windows (COM). Обёртка над comtypes; TDataDescriptor
передаётся структурой (VT_RECORD), поэтому pywin32 не подходит.
"""

from __future__ import annotations

import sys
from enum import Enum
from typing import Any, List, Optional

from ..exceptions import ComCallError, ComConnectionError, PackError
from ..model import TDataDescriptor
from ..utils.job_object import (assign_kill_on_close, close_handle,
                                is_process_alive)
from ..utils.processes import get_mmain_pids, kill_pids as _kill_pids, wait_for_pid_exit


class SessionOwnership(str, Enum):
    """Lifecycle ownership of the process behind the current COM session."""

    UNKNOWN = "unknown"
    OWNED = "owned"
    EXTERNAL = "external"


class COMClient:
    """Подключение к SimInTech через COM и выполнение методов IMVTU_Server.

    Args:
        silent_mode: запустить SimInTech в скрытом режиме (без UI).
        com_progid: ProgID COM-объекта. Если None — пробуются стандартные
            ProgID и CLSID (mmain.MVTU_Server, MVTU.Server,
            {ACE730D7-1712-4C70-87C8-7E4C55622E91}).
    """

    # Реально зарегистрированные идентификаторы кокласса MVTU_Server
    # (библиотека mmain, см. mmain_TLB.pas / mmain.ridl):
    CLSID_MVTU_SERVER = "{ACE730D7-1712-4C70-87C8-7E4C55622E91}"
    DEFAULT_PROGIDS = (
        "mmain.MVTU_Server",   # стандартный ProgID (library.coclass)
        "MVTU.Server",         # псевдоним из simintech-connector
    )

    def __init__(self, silent_mode: bool = True,
                 com_progid: Optional[str] = None):
        self._server: Any = None
        self._connected = False
        self._silent_mode = silent_mode
        self._com_progid = com_progid
        # PID COM-сервера текущей сессии. Наличие PID само по себе не
        # доказывает, что процесс был запущен этим клиентом.
        self._session_pid: Optional[int] = None
        self._ownership = SessionOwnership.UNKNOWN
        # Хэндл job-объекта, удерживающего процесс OWNED-сессии
        # (`KILL_ON_JOB_CLOSE`): смерть этого процесса-клиента закрывает
        # хэндл, и ядро снимает сервер. None — защиты нет (сессия не OWNED,
        # назначение отказало — код в `job_error`, — или не Windows).
        self._job_handle: Optional[int] = None
        self._job_pid: Optional[int] = None
        self._job_error = 0

    # ─── Жизненный цикл ─────────────────────────────────────────────

    @property
    def is_available(self) -> bool:
        """COM доступен только на Windows."""
        return sys.platform == "win32"

    @property
    def connected(self) -> bool:
        """True, если клиент подключён к серверу."""
        return self._connected

    def connect(self) -> "COMClient":
        """Подключиться к COM-серверу SimInTech.

        Вызывает mmain.exe (out-of-proc). Требует зарегистрированного
        COM-объекта: `bin/mmain.exe /regserver`.

        Для OWNED-сессии процесс дополнительно назначается в job-объект с
        `KILL_ON_JOB_CLOSE` (`job_handle`): смерть процесса-клиента снимает
        сервер силами ядра. Отказ назначения сессию не ломает (`job_error`).
        """
        if not self.is_available:
            raise ComConnectionError(
                "COM API SimInTech работает только на Windows. "
                "Текущая платформа: " + sys.platform
            )

        try:
            import comtypes.client
        except ImportError as exc:  # pragma: no cover — только Windows
            raise ComConnectionError(
                "Библиотека comtypes не установлена: pip install comtypes"
            ) from exc

        # COM инициализируется ПО ПОТОКАМ. comtypes вызывает CoInitializeEx
        # при импорте, но только для импортировавшего потока. Асинхронные
        # серверы (например, MCP/FastMCP) выполняют синхронные инструменты в
        # рабочих потоках — там COM не инициализирован, и CreateObject падает
        # с «Не был произведён вызов CoInitialize» (CO_E_NOTINITIALIZED).
        _ensure_com_initialized()

        # Snapshot до COM-активации нужен, чтобы не принять
        # уже существующий GUI-экземпляр за управляемый процесс.
        before_pids = get_mmain_pids()

        # Список идентификаторов для перебора
        if self._com_progid:
            candidates = [self._com_progid]
        else:
            candidates = list(self.DEFAULT_PROGIDS) + [self.CLSID_MVTU_SERVER]

        last_error = None
        for ident in candidates:
            try:
                self._server = comtypes.client.CreateObject(ident)
                self._com_progid = ident
                break
            except Exception as exc:
                last_error = exc
                self._server = None

        if self._server is None:
            raise ComConnectionError(
                f"Не удалось создать COM-объект SimInTech "
                f"(пробовали: {', '.join(map(str, candidates))}). "
                f"Последняя ошибка: {last_error}. Убедитесь, что SimInTech "
                f"установлен и выполнен: bin\\mmain.exe /regserver"
            ) from last_error

        # PID нужен до любых session-wide настроек. При attach к GUI мы не
        # меняем Silent/NoClose: подключённая пользователем сессия не является
        # нашим управляемым процессом.
        self._session_pid = None
        self._ownership = SessionOwnership.UNKNOWN
        try:
            self._session_pid = _as_int(self._server.GetProcessID())
        except Exception:
            self._session_pid = None

        after_pids = get_mmain_pids()
        if (self._session_pid is not None and self._session_pid > 0
                and self._session_pid not in before_pids
                and self._session_pid not in after_pids):
            # Свежий процесс мог не попасть в снимок: сканеры (wmic/
            # tasklist/powershell) читают таблицу процессов не мгновенно.
            # Одна перепроверка снимает ложный UNKNOWN, не меняя критерий:
            # владение доказывается отсутствием PID ДО подключения и
            # присутствием после — перепроверяется только «после» (находка
            # ревью simintech-mcp#41: ложный UNKNOWN оставлял жить свой
            # процесс и отказывал в работе).
            after_pids = get_mmain_pids()
        if self._session_pid is not None and self._session_pid > 0:
            if self._session_pid in before_pids:
                self._ownership = SessionOwnership.EXTERNAL
            elif self._session_pid in after_pids:
                self._ownership = SessionOwnership.OWNED
            else:
                self._ownership = SessionOwnership.UNKNOWN

        # Для управляемой сессии сохраняем прежнюю защиту от автозавершения
        # и скрытый режим. Для external/unknown COM-сессию не перенастраиваем.
        if self._ownership is SessionOwnership.OWNED:
            self._safe_call("SetNoCloseAppFlag", 1)
            if self._silent_mode:
                self._safe_call("SetSilentMode", 1)
            self._attach_job_guard()

        self._connected = True
        return self

    @property
    def session_pid(self) -> Optional[int]:
        """PID COM-сервера текущей/последней сессии."""
        return self._session_pid

    @property
    def ownership(self) -> SessionOwnership:
        """Ownership текущей/последней COM-сессии."""
        return self._ownership

    @property
    def job_handle(self) -> Optional[int]:
        """Хэндл job-объекта, защищающего процесс OWNED-сессии (None — нет).

        Живой хэндл означает: умрёт процесс этого клиента — ядро снимет
        процесс сессии, в том числе при аварии клиента. None — защиты нет:
        сессия не OWNED, назначение отказало (код — `job_error`) или
        платформа не Windows.
        """
        return self._job_handle

    @property
    def job_error(self) -> int:
        """Код отказа последнего назначения в job (0 — отказа не было).

        Отказ не является отказом сессии: клиент работает без гарантии
        уборки, а код остаётся для диагностики (`OpenProcess`,
        `AssignProcessToJobObject`).
        """
        return self._job_error

    def disconnect(self) -> None:
        """Отсоединиться от сервера, не управляя процессом.

        `disconnect` — не завершение: отпущенный, но живой процесс сессии не
        трогается. Хэндл job-объекта закрывается, только если процесс уже
        завершился; у живого он остаётся у клиента — и это механизм уборки:
        умрёт процесс-клиент, и ядро снимет отпущенный процесс.
        """
        self._server = None
        self._connected = False
        self._release_job_if_process_dead()

    def shutdown(self, kill_pids=None) -> None:
        """Закрыть управляемую COM-сессию и адресно убрать её процесс.

        Для OWNED-сессии выполняется:
            disconnect -> wait exact PID -> kill exact PID, если он остался.

        EXTERNAL и UNKNOWN-сессии процесс не завершают. Явно переданный
        ``kill_pids`` сохраняет старый escape hatch для вызывающей стороны,
        которая сама отвечает за разрешённые PID'ы.

        Хэндл job-объекта (`job_handle`) закрывается по итогу завершения:
        закрытие последнего хэндла с `KILL_ON_JOB_CLOSE` само завершает
        процессы job'а, поэтому в managed-пути он закрывается после ожидания
        и `kill`, а при ``kill_pids`` — только если процесс уже мёртв (права
        на завершение здесь определяет вызывающая сторона).

        Args:
            kill_pids: необязательная итерация PID'ов, разрешённых вызывающей
                стороной к завершению. Если не задана, завершение выполняется
                автоматически только для OWNED session PID.
        """
        pid = self._session_pid
        ownership = self._ownership

        # disconnect попутно закрывает хэндл job'а, если процесс уже мёртв.
        self.disconnect()

        if sys.platform != "win32":
            self._reset_session_state()
            return

        if kill_pids is not None:
            if kill_pids:
                _kill_pids(kill_pids)
            self._release_job_if_process_dead()
            self._reset_session_state()
            return

        if ownership is not SessionOwnership.OWNED or not pid or pid <= 0:
            self._reset_session_state()
            return

        if not wait_for_pid_exit(pid, timeout=5.0):
            _kill_pids([pid])

        # Процесс завершён (или завершается этой строкой): закрытие job'а
        # больше ничего живого не задевает — и служит последней мерой.
        self._close_job()
        self._reset_session_state()

    def _reset_session_state(self) -> None:
        """Сбросить идентичность завершённой COM-сессии."""
        self._session_pid = None
        self._ownership = SessionOwnership.UNKNOWN

    # ─── Уборка процесса (job-объект) ───────────────────────────────

    def _attach_job_guard(self) -> None:
        """Назначить процесс OWNED-сессии в job с `KILL_ON_JOB_CLOSE`.

        Отказ назначения не является отказом сессии: клиент продолжает
        работать без гарантии уборки, а код отказа виден в `job_error`.
        Хэндл сессии, отпущенной живой, остаётся открытым до конца процесса
        клиента: закрыть его — значит завершить тот процесс, чего
        `disconnect` не делает.
        """
        self._release_job_if_process_dead()
        self._job_error = 0
        pid = self._session_pid
        if pid is None or pid <= 0:
            return
        handle, error = assign_kill_on_close(pid)
        self._job_handle = handle
        self._job_pid = pid if handle is not None else None
        self._job_error = error

    def _release_job_if_process_dead(self) -> None:
        """Закрыть хэндл job'а, если его процесс уже завершился.

        Закрытие последнего хэндла с `KILL_ON_JOB_CLOSE` завершает процессы
        job'а — поэтому живой процесс не трогаем (`disconnect` не является
        завершением), а мёртвый закрываем, чтобы хэндл не копился. Проба —
        `is_process_alive` (один `OpenProcess`), а не снимок
        `get_mmain_pids()` (три сканера процессов): дешевле и точнее.
        """
        if self._job_handle is None:
            return
        pid = self._job_pid
        if pid and is_process_alive(pid):
            return
        self._close_job()

    def _close_job(self) -> None:
        """Закрыть хэндл job'а и забыть его.

        Вызывается, когда процессы job'а завершены: тогда закрытие хэндла —
        чистка, а не завершение.
        """
        if self._job_handle is not None:
            close_handle(self._job_handle)
        self._job_handle = None
        self._job_pid = None

    # ─── Низкоуровневые вызовы ──────────────────────────────────────

    def call(self, method: str, *args: Any) -> Any:
        """Вызвать метод IMVTU_Server и вернуть результат.

        В comtypes [out]-параметры возвращаются в порядке объявления;
        [in]-параметры передаются как обычные аргументы.
        """
        if not self._connected or self._server is None:
            raise ComConnectionError(
                "COM-сервер не подключён. Вызовите connect() первым."
            )
        func = getattr(self._server, method, None)
        if func is None:
            raise ComCallError(
                method, message="метод не найден в интерфейсе IMVTU_Server")
        try:
            return func(*args)
        except Exception as exc:
            hr = getattr(exc, "hresult", None) or getattr(exc, "hr", None)
            raise ComCallError(method, hr=hr, message=str(exc)) from exc

    def _safe_call(self, method: str, *args: Any) -> Any:
        """Вызов без строгой обработки ошибок (для необязательных настроек)."""
        if self._server is None:
            return None
        func = getattr(self._server, method, None)
        if func is None:
            return None
        try:
            return func(*args)
        except Exception:
            return None

    # ─── Типизированные вспомогательные методы ──────────────────────

    def open_project(self, path: str) -> int:
        """Открыть проект (.prt/.xprt), вернуть ProjectId (i64)."""
        project_id = self.call("OpenProject", path)
        return _as_int(project_id)

    def new_project(self) -> int:
        """Создать новый проект, вернуть ProjectId.

        Проект получается **пустым**: без моделирующего слоя и настроек расчёта,
        поэтому он не считает. Для работоспособной модели используйте
        `open_template()` (см. `Project.from_template`).
        """
        project_id = self.call("NewProject")
        return _as_int(project_id)

    def open_template(self, template: str) -> int:
        """Создать проект из шаблона SimInTech, вернуть ProjectId.

        Шаблоны лежат в `<корень SimInTech>\\bin\\Template\\*.prt`; имя файла
        обязательно должно быть полным путём — по короткому имени (без пути)
        метод возвращает 0 и проект не создаётся.
        """
        return _as_int(self.call("OpenTemplate", template))

    def open_pack(self, path: str) -> int:
        """Открыть пакет проектов (`.pak`), вернуть PackId.

        Пакет — несколько связанных проектов с общим модельным временем:
        оно равно минимуму времён проектов, а обмен идёт через общую базу
        сигналов. Состав дают `Pack.project_ids()`. Возвращает 0, если пакет
        открыть не удалось.

        Повторное открытие **того же файла** создаёт второй пакет, а не
        возвращает прежний (живой замер 01.10.2026): один файл в двух
        пакетах — это два независимых состава, и закрывать надо оба.
        """
        return _as_int(self.call("OpenPack", path))

    def close_pack(self, pack_id: int) -> None:
        """Закрыть пакет.

        Идентификатор должен быть **положительным**: `ClosePack(-1)` роняет
        `mmain.exe` (Access violation, живой замер 01.10.2026), а `-1` —
        достижимое значение (`GetPackIdByFileName` для неоткрытого пакета).

        Отказ стоит **здесь**, а не только этажом выше (`Pack.close`): через
        этот метод проходит каждый путь закрытия пакета, и защита обязана
        стоять там, где id попадает в COM, — докстринг не защищает
        (ревью code#23).
        """
        if pack_id <= 0:
            raise PackError(
                f"ClosePack: идентификатор пакета {pack_id} недействителен — "
                f"неположительный id роняет mmain.exe (Access violation, замер "
                f"01.10.2026). Проверьте источник id: у неоткрытого пакета "
                f"`GetPackIdByFileName` возвращает -1.")
        self.call("ClosePack", pack_id)

    def get_pack_count(self) -> int:
        """Сколько пакетов открыто."""
        return _as_int(self.call("GetPackCount"))

    def set_layer_prop(self, project_id: int, layer_no: int,
                       name: str, value: Any) -> int:
        """Установить свойство расчётного слоя проекта, вернуть handle.

        Свойства слоя — это настройки расчёта из секции «Основные параметры»:
        `endtime`, `starttime`, `hmin`, `hmax`, `intmet` и т. п. Работает
        только у проекта с настоящим расчётным слоем (шаблон, а не `NewProject`);
        у пустого проекта возвращает 0 и ничего не меняет (проверено).
        """
        return _as_int(self.call("SetLayerProp", project_id, layer_no,
                                 name, str(value)))

    def get_process_id(self) -> int:
        """Вернуть PID процесса mmain.exe."""
        return _as_int(self.call("GetProcessID"))

    # ─── Перечисление открытых проектов ─────────────────────────────
    #
    # Группа адресуется номером или именем файла проекта, а не объектом:
    # она и нужна затем, чтобы получить ProjectId, когда объекта ещё нет.
    # Поэтому методы живут на клиенте, а не на `Project`.
    #
    # Ни один из них не проверен на живом SimInTech: по RIDL каждый отдаёт
    # единственный [out]-параметр, и значение берётся из кортежа-результата
    # (`_out_values`). Если в сборке сигнатура другая, обёртка откажет с
    # понятным сообщением, а не разберёт результат наугад.

    def get_project_count(self) -> int:
        """Сколько проектов открыто (COM `GetProjectCount`).

        На живом SimInTech не проверено. Ноль означает, что открытых проектов
        нет, а не ошибку.
        """
        return _as_int(_out_values(
            self.call("GetProjectCount"), "GetProjectCount")[0])

    def get_project_id_by_number(self, number: int) -> int:
        """Идентификатор проекта по его номеру среди открытых.

        COM `GetProjectIdByNumber`; нумерация, судя по `Pack`, с нуля.
        Возвращает 0, если проекта с таким номером нет. Нумерация и поведение
        на живом SimInTech не подтверждены.
        """
        return _as_int(_out_values(
            self.call("GetProjectIdByNumber", int(number)),
            "GetProjectIdByNumber")[0])

    def get_project_id_by_file_name(self, file_name: str) -> int:
        """Идентификатор проекта по имени файла (COM `GetProjectIdByFileName`).

        Возвращает 0, если проект с таким именем не открыт. Как именно
        сопоставляется имя (полный путь, только имя файла, регистр) — на живом
        SimInTech не подтверждено.
        """
        return _as_int(_out_values(
            self.call("GetProjectIdByFileName", file_name),
            "GetProjectIdByFileName")[0])

    def get_active_project(self) -> int:
        """Идентификатор активного проекта (COM `GetActiveProject`).

        Возвращает 0, если активного проекта нет. Что делает проект активным
        (последний открытый, последняя активированная страница) — на живом
        SimInTech не подтверждено.
        """
        return _as_int(_out_values(
            self.call("GetActiveProject"), "GetActiveProject")[0])

    def get_opened_file_name(self, project_id: int) -> str:
        """Путь к файлу, из которого открыт проект (`GetOpenedFileName`).

        **Полный путь** — подтверждено живым замером 01.10.2026 на участниках
        пакета (`C:\\…\\pak-demo\\Непрерывная часть.prt`). Пустая строка
        означает, что проект не связан с файлом (например, создан через
        `NewProject`) — это по-прежнему предположение, живым прогоном не
        проверялось.
        """
        return _as_str(_out_values(
            self.call("GetOpenedFileName", int(project_id)),
            "GetOpenedFileName")[0])

    def find_signal(self, name: str, project_id: int) -> Any:
        """Найти сигнал по имени в проекте; вернуть дескриптор.

        Возвращается дескриптор comtypes как есть — его нельзя подменять
        нашей одноимённой структурой (см. `_to_descriptor`).
        """
        return _to_descriptor(self.call("FindSignalData", name, project_id))


# RPC_E_CHANGED_MODE: поток уже инициализирован COM в другом режиме.
# Это не ошибка — работать можно, просто режим другой.
_RPC_E_CHANGED_MODE = -2147417850


def _ensure_com_initialized() -> None:
    """Инициализировать COM для ТЕКУЩЕГО потока (идемпотентно).

    COM инициализируется по потокам. `comtypes` вызывает `CoInitializeEx`
    при импорте, но только для импортировавшего потока. Серверы, выполняющие
    синхронные обработчики в пуле потоков (MCP/FastMCP, любые async-обёртки),
    попадают в поток без инициализации — `CreateObject` там падает с
    `CO_E_NOTINITIALIZED` («Не был произведён вызов CoInitialize»).

    Повторный вызов на уже инициализированном потоке безопасен: `CoInitializeEx`
    увеличивает счётчик и не переключает режим. `CoUninitialize` намеренно не
    вызывается — потоки пула переиспользуются, и разбалансировка счётчика
    опаснее, чем неизрасходованный ресурс на время жизни процесса.
    """
    try:
        import comtypes
    except ImportError:  # pragma: no cover — только Windows
        return
    try:
        comtypes.CoInitializeEx(comtypes.COINIT_APARTMENTTHREADED)
    except OSError as exc:
        winerror = getattr(exc, "winerror", None)
        if winerror is None:
            winerror = getattr(exc, "args", [None])[0]
        if winerror != _RPC_E_CHANGED_MODE:
            raise


def _as_int(value: Any) -> int:
    """Привести результат COM-вызова к int (comtypes ctypes-значения)."""
    if value is None:
        return 0
    if hasattr(value, "value"):
        return int(value.value)
    return int(value)


def _as_str(value: Any) -> str:
    """Привести результат COM-вызова к str (BSTR, VARIANT или None)."""
    if value is None:
        return ""
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _out_values(result: Any, method: str, count: int = 1) -> List[Any]:
    """Разобрать результат COM-вызова на [out]-значения.

    comtypes отдаёт [out]-параметры одним кортежем в порядке объявления (для
    одного параметра — кортежем из одного элемента). Разбирать результат
    «наугад» нельзя: у метода, которого в этой сборке нет или у которого
    другая сигнатура, результат будет `None` или пустым, и `TypeError` из
    распаковки ничего не объясняет. Поэтому такой результат превращается в
    `ComCallError` с именем метода — иначе неверная сигнатура выглядела бы
    как ошибка в коде вызывающего.

    Args:
        result: то, что вернул `COMClient.call`.
        method: имя COM-метода — попадает в сообщение об отказе.
        count: сколько [out]-значений ожидается по RIDL.

    Raises:
        ComCallError: результат пуст (`None`) или значений не столько, сколько
            объявлено.
    """
    if result is None:
        raise ComCallError(method, message=(
            f"метод не вернул [out]-значений (получено None), а по RIDL "
            f"ожидалось {count}. Проверьте сигнатуру метода в этой сборке "
            f"SimInTech."))
    # Значение без кортежа — это [out, retval]: comtypes отдаёт его напрямую,
    # и отличить его от одиночного [out] по результату нельзя.
    values = list(result) if isinstance(result, (tuple, list)) else [result]
    if len(values) != count:
        raise ComCallError(method, message=(
            f"метод вернул {len(values)} значений вместо {count} ожидаемых "
            f"по RIDL. Проверьте сигнатуру метода в этой сборке SimInTech."))
    return values


def _to_descriptor(value: Any) -> Any:
    """Нормализовать дескриптор из результата comtypes-вызова.

    Родной дескриптор comtypes возвращается как есть — см.
    `utils.converters._to_descriptor`: подмена его нашим одноимённым классом
    ломает Read*/Write* («expected TDataDescriptor instance instead of
    TDataDescriptor»).
    """
    from ..utils.converters import is_descriptor

    if value is None:
        return TDataDescriptor()
    if is_descriptor(value):
        return value
    if isinstance(value, (tuple, list)):
        data_id = value[0] if len(value) > 0 else 0
        data_type = value[1] if len(value) > 1 else 0
        return TDataDescriptor(_as_int(data_id), _as_int(data_type))
    return TDataDescriptor()
