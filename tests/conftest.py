"""Общие фикстуры pytest.

Integration-тесты (маркер integration) требуют Windows с зарегистрированным
COM-сервером SimInTech (mmain.exe /regserver). В другом окружении они
пропускаются.

Очистка процессов: session-фикстура запоминает PID'ы mmain.exe ДО прогона
и завершает ТОЛЬКО появившиеся после (процессы, порождённые тестами).
Предсуществующие процессы SimInTech (запущенные пользователем) НЕ трогаются.

Чтобы принудительно запустить тесты даже если авто-детект не сработал:
    pytest tests/integration -m integration --run-simintech
"""

import os
import sys

import pytest

# `scripts/` — инструменты репозитория (DLP-гейт публичных данных, генератор
# каталога). Тесты проверяют их наравне с пакетом, а в PYTHONPATH их никто не
# кладёт, поэтому путь добавляется здесь — до сбора тест-модулей.
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
    ),
)


def pytest_addoption(parser):
    parser.addoption(
        "--run-simintech",
        action="store_true",
        default=False,
        help="принудительно запускать integration-тесты, даже если "
             "авто-детект COM недоступен",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: тесты, требующие реального COM-сервера SimInTech на Windows",
    )
    config.addinivalue_line(
        "markers",
        "performance: бенчмарки производительности placer/router",
    )
    # Сплошные проверки по файлам поставки SimInTech: медленные (обход
    # 9p-каталога) и зависят от установленного SimInTech64. Объявление нужно
    # не только «для порядка»: pytest 9 не добавляет необъявленную метку в
    # ключевые слова теста, поэтому `pytest -m distribution` не выбрал бы
    # ничего, а сама метка ругалась бы предупреждением на каждом прогоне.
    config.addinivalue_line(
        "markers",
        "distribution: сплошные проверки по файлам поставки SimInTech"
        " (медленные, нужен её каталог)",
    )


@pytest.fixture(scope="session")
def simintech_available(pytestconfig) -> bool:
    """True, если COM-сервер SimInTech доступен."""
    if pytestconfig.getoption("--run-simintech"):
        return True
    if sys.platform != "win32":
        print("\n[simintech] COM недоступен: платформа != Windows. "
              "Запустите integration-тесты на Windows.", file=sys.stderr)
        return False
    try:
        from simintech_api import COMClient
        client = COMClient(silent_mode=True)
        client.connect()
        client.disconnect()
        return True
    except Exception as exc:
        print(f"\n[simintech] COM недоступен: {exc}", file=sys.stderr)
        return False


@pytest.fixture(scope="session", autouse=True)
def _cleanup_mmain_processes():
    """Завершить процессы mmain.exe, появившиеся в ходе тестов.

    Собирает PID'ы ДО прогона; после — убивает ТОЛЬКО разность
    (появившиеся). Предсуществующие процессы SimInTech не трогаются.

    Отключение очистки (если нужно сохранить процессы): переменная
    окружения SIMINTECH_KEEP_MMAIN=1.

    Полная очистка ВСЕХ процессов mmain.exe (включая предсуществующие,
    например накопленный мусор прошлых прогонов): переменная окружения
    SIMINTECH_KILL_ALL_MMAIN=1. Осторожно: убьёт и процессы, запущенные
    вручную.
    """
    if os.environ.get("SIMINTECH_KEEP_MMAIN") == "1":
        yield
        return
    if sys.platform != "win32":
        yield
        return
    from simintech_api.utils.processes import get_mmain_pids, kill_pids
    import time

    kill_all = os.environ.get("SIMINTECH_KILL_ALL_MMAIN") == "1"
    before = set(get_mmain_pids())
    print(f"\n[simintech] mmain.exe ДО тестов: "
          f"{sorted(before) if before else '(не обнаружены)'}", file=sys.stderr)
    yield
    time.sleep(1.0)  # дать процессам завершить работу
    after = set(get_mmain_pids())

    if kill_all:
        # Полная очистка: все процессы mmain.exe
        print(f"[simintech] SIMINTECH_KILL_ALL_MMAIN: завершаю ВСЕ: "
              f"{sorted(after) if after else '(нет)'}", file=sys.stderr)
        kill_pids(after)
        time.sleep(0.5)
        still = set(get_mmain_pids())
        if still:
            print(f"[simintech] ВНИМАНИЕ: не удалось завершить: "
                  f"{sorted(still)}", file=sys.stderr)
        return

    print(f"[simintech] mmain.exe ПОСЛЕ тестов: "
          f"{sorted(after) if after else '(не обнаружены)'}", file=sys.stderr)
    new = after - before
    if new:
        print(f"[simintech] Завершаю процессы, порождённые тестами: "
              f"{sorted(new)}", file=sys.stderr)
        kill_pids(new)
        time.sleep(0.5)
        # Повторная проверка — сообщаем, если что-то осталось
        still = set(get_mmain_pids()) - before
        if still:
            print(f"[simintech] ВНИМАНИЕ: не удалось завершить: "
                  f"{sorted(still)}", file=sys.stderr)
    else:
        print("[simintech] Новых процессов не обнаружено — очистка не требуется.",
              file=sys.stderr)


@pytest.fixture(scope="session")
def client(simintech_available):
    """Подключённый COMClient, который **владеет** своим процессом SimInTech.

    Владение — точный PID, как в измерительной оснастке: до подключения снимается
    список живых `mmain.exe`, после клиент называет свой (`get_process_id`), и
    завершается **ровно он**. Чужие процессы не трогаются никогда.

    Почему это не формальность. `disconnect()` процесс **не завершает**, а при
    живом экземпляре клиент к нему **подключается**, своего не поднимая —
    измерено 2026-09-23 (при двух чужих `mmain.exe` клиент своего не создал).
    Тогда «текущая страница» принадлежит чужому проекту, числа относятся не к
    нашей модели, а проба может застрять на модальном окне чужого расчёта: так
    2026-09-24 живой набор и **завис** на остатках прошлых прогонов, оставив
    семь процессов. Поэтому тест не «подключается как получится», а при чужом
    экземпляре отказывается работать с внятным текстом — вместо того чтобы
    выдать чужие числа за свои.

    Скоуп сессионный: один процесс на прогон, а не по одному на тест. Иначе
    процессы копятся все время прогона и завершаются только в конце — именно это
    и выглядело как «тесты не убирают за собой».

    Остатки прошлых прогонов убирает владелец: `SIMINTECH_KILL_ALL_MMAIN=1`
    (переменная документирована в `_cleanup_mmain_processes`).
    """
    if not simintech_available:
        pytest.skip("COM SimInTech недоступен (нужна Windows + mmain.exe /regserver)")
    import time

    from simintech_api import COMClient
    from simintech_api.utils.processes import get_mmain_pids, kill_pids

    before = set(get_mmain_pids())
    if before and os.environ.get("SIMINTECH_KILL_ALL_MMAIN") == "1":
        kill_pids(before)
        time.sleep(0.5)
        before = set(get_mmain_pids())
    if before:
        # Отсрочка на выход «соседа»: процесс, завершаемый прямо сейчас (свой
        # тест зовёт `shutdown()`), исчезает не мгновенно, и без этой паузы
        # фикстура отказала бы из-за него — то есть отказ срабатывал бы на
        # ровном месте. Проверка повторяется после паузы, а не вместо неё.
        time.sleep(1.0)
        before = set(get_mmain_pids())
    if before:
        pytest.skip(
            f"на машине уже запущен SimInTech (PID {sorted(before)}): клиент "
            "подключился бы к чужому экземпляру, и «текущая страница» была бы не "
            "нашей. Закройте SimInTech — или запустите с "
            "SIMINTECH_KILL_ALL_MMAIN=1, чтобы убрать остатки перед прогоном.")

    c = COMClient(silent_mode=True)
    c.connect()
    owned = c.get_process_id()
    if owned in before:
        c.disconnect()
        pytest.fail(
            f"клиент назвал своим PID {owned}, который жил до подключения: "
            "владение определено неверно, и завершать этот процесс нельзя")
    try:
        yield c
    finally:
        try:
            c.disconnect()
        except Exception:                                        # noqa: BLE001
            pass
        kill_pids([owned])
        time.sleep(0.5)
        if owned in set(get_mmain_pids()):
            print(f"[simintech] свой процесс {owned} завершить не удалось",
                  file=sys.stderr)
