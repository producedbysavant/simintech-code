"""Интеграционные тесты: жизненный цикл проекта и сигналы.

Запускаются ТОЛЬКО на Windows с зарегистрированным COM-сервером:
    python -m pytest tests/integration -m integration
Требуется mmain.exe /regserver и файл-пример FSM-модели.

После прогона процессы SimInTech завершаются **адресно**: фикстура `client`
(`tests/conftest.py`) владеет точным PID своего процесса и завершает ровно его, а
тест ниже, поднимающий собственный клиент, доводит свой процесс до конца сам.
Чужие процессы не трогаются никогда — при них тест отказывается работать.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest

pytestmark = pytest.mark.integration

# Демо-модель с FSM-выходом (используется в Temp-скриптах прошлых сессий).
# Путь на Windows: C:\\SimInTech64\\Temp\\fsm_demo.prt
FSM_DEMO = os.environ.get(
    "SIMINTECH_FSM_DEMO",
    r"C:\SimInTech64\Temp\fsm_demo.prt",
)


def test_connect_disconnect():
    """Подключение/отключение COM-клиента — и завершение **своего** процесса.

    Клиент поднимает собственный `mmain.exe`, а `disconnect()` его не завершает
    (измерено), поэтому тест обязан убедиться, что процесс ушёл. Иначе он
    остаётся висеть, и следующий живой тест либо подключится к чужому
    экземпляру, либо (по контракту фикстуры `client`) откажется работать —
    причём отказ сработал бы на ровном месте, из-за этого процесса.
    """
    import time

    from simintech_api import COMClient
    from simintech_api.utils.processes import get_mmain_pids, kill_pids

    c = COMClient(silent_mode=True)
    c.connect()
    assert c.connected
    pid = c.get_process_id()
    assert pid > 0
    c.disconnect()
    assert not c.connected
    c.shutdown()
    deadline = time.monotonic() + 5.0
    while pid in set(get_mmain_pids()) and time.monotonic() < deadline:
        time.sleep(0.1)
    if pid in set(get_mmain_pids()):
        kill_pids([pid])
        time.sleep(0.5)
    assert pid not in set(get_mmain_pids()), (
        f"процесс {pid}, поднятый этим тестом, остался жив: следующий живой тест "
        "подключился бы к нему как к чужому")


def test_new_project_save_close(client):
    """Создание нового проекта, сохранение в XML, закрытие."""
    from simintech_api import Project
    import tempfile

    prj = Project.new(client)
    assert prj.id != 0
    page = prj.get_main_page()
    assert page.id != 0

    tmp = os.path.join(tempfile.gettempdir(), "siminapi_new_test.xprt")
    prj.save_xml(tmp)
    assert os.path.exists(tmp)

    prj.close()


def test_open_project_signals(client):
    """Открытие демо-проекта и чтение списка внешних сигналов.

    GetProjectSignalList возвращает список ОБМЕННЫХ сигналов (блоки
    «Вход/Выход алгоритма»). Демо-модель может не иметь внешних сигналов —
    тогда список пуст (это корректное поведение, не ошибка). Тест проверяет
    механизм: вызовы выполняются и валидный дескриптор создаётся, если
    сигналы есть.
    """
    from simintech_api import Project

    if not os.path.exists(FSM_DEMO):
        pytest.skip(f"Демо-модель не найдена: {FSM_DEMO}")

    prj = Project.open(client, FSM_DEMO)
    sim = prj.simulation()
    sim.start()
    signals = prj.list_signals()
    # Модель без внешних интерфейсных сигналов даёт пустой список — не ошибка.
    if not signals:
        pytest.skip("Демо-модель не имеет внешних (обменных) сигналов — "
                    "список пуст, пропускаем проверку содержимого")
    for info in signals[:10]:
        assert info.name, "Сигнал без имени"
        # Сигналы из XML-представления не имеют COM-дескриптора
        # (descriptor=None) — их нужно запрашивать через signal(name).
        if info.descriptor is not None:
            assert info.descriptor.is_valid
    sim.stop()
    prj.close()


def test_signal_by_name_refuses_without_signal_base(client):
    """Сигнал по имени без базы сигналов — отказ, а не пропуск.

    **Что измерено в этой среде (2026-09-22).** Читаемых сигналов нет ни в одной
    модели: у демо `fsm_demo.prt` в списке 1009 имён и **все** с `source='xml'`
    (это имена блоков, читать их нельзя), у проекта из шаблона список состоит из
    имён блоков. Поэтому прежний тест «прочитать и записать сигнал» ничего не
    утверждал и заканчивался `pytest.skip` — то есть **прятал отсутствие
    данных**, а не проверял поведение; ещё раньше он строил модель через
    `Project.new()` и получал от среды «Номер решателя блока задан неверно».

    Здесь закреплено проверяемое и документированное: запрос сигнала по имени в
    проекте без базы отвергается `SignalError`, и текст отказа обязан называть
    причину — записи `source='xml'` читателю не помогут, и это единственная
    подсказка, которую он получит.

    **Когда база сигналов появится**, тест упадёт с прямым указанием переписать
    его на настоящее чтение и запись. Это признак, ради которого он и написан, а
    не помеха: молчаливый `skip` такого момента не заметил бы.
    """
    from simintech_api import Project
    from simintech_api.exceptions import SignalError

    prj = Project.from_template(client)
    prj.set_calc_end_time(1.0)
    sim = prj.simulation()
    try:
        page = prj.get_main_page()
        konst = page.create_block("Константа", 0, 0)
        konst.set_property("a", 5.0)   # у «Константы» параметр `a`, не `y0`
        konst.init()
        gain = page.create_block("Усилитель", 200, 0)
        gain.set_property("a", 2.0)
        gain.init()
        konst.connect(gain)
        sim.start()
        sim.step()

        readable = [info for info in prj.list_signals()
                    if info.descriptor is not None]
        assert not readable, (
            f"в среде появилась база сигналов ({len(readable)} читаемых "
            "записей) — тест надо вернуть к чтению и записи сигнала, а не "
            "проверять отказ")

        names = prj.get_signal_names_from_xml()
        assert names, "выгрузка не дала имён — проверять нечего"
        with pytest.raises(SignalError) as exc:
            prj.signal(names[0])
        assert "не найден в проекте" in str(exc.value)
        assert "source='xml'" in str(exc.value), (
            "текст отказа обязан объяснять, что записи с source='xml' — имена "
            "блоков и не читаются")
    finally:
        try:
            sim.stop()
        finally:
            prj.close()


def test_build_simple_model(client):
    """Сборка простой модели через COM: Константа -> Усилитель."""
    from simintech_api import Project

    prj = Project.new(client)
    page = prj.get_main_page()

    b1 = page.create_block("Константа", 0, 0, width=60, height=40)
    b1.set_property("a", 5.0)    # значение константы (параметр `a`, не `y0`)
    b2 = page.create_block("Усилитель", 200, 0, width=60, height=40)
    b2.set_property("a", 2.0)    # коэффициент усиления

    wire = b1.connect(b2)
    assert wire.id != 0

    prj.close()
