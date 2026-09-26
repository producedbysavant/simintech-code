"""Тесты SimInTechAgent: парсер команд и работа с фейковым сервером."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest

from simintech_api.agent import SimInTechAgent, _parse_value, _split_props, _split_ref


# ─── Утилиты парсинга ──────────────────────────────────────────────


def test_split_ref():
    assert _split_ref("k1.out") == ("k1", 0)
    assert _split_ref("k1.out2") == ("k1", 2)
    assert _split_ref("g1.in") == ("g1", 0)
    assert _split_ref("g1.in3") == ("g1", 3)
    assert _split_ref("plain") == ("plain", 0)


def test_split_props():
    assert _split_props("a=2, y0=5") == ["a=2", "y0=5"]
    assert _split_props("coeff=[1,2,3], name=test") == ["coeff=[1,2,3]", "name=test"]
    assert _split_props("k=2.5") == ["k=2.5"]


def test_parse_value():
    assert _parse_value("5") == 5
    assert _parse_value("2.5") == 2.5
    assert _parse_value("true") is True
    assert _parse_value("ложь") is False
    assert _parse_value("text") == "text"
    assert _parse_value("'quoted'") == "quoted"
    assert _parse_value("[1,2,3]") == [1, 2, 3]
    assert _parse_value("1e3") == 1000.0


# ─── Агент с фейковым сервером ─────────────────────────────────────


def _known_props(class_name):
    """Имена параметров класса — по тому же каталогу, что у живого COM."""
    from simintech_api.catalog import load_default_catalog

    return set(load_default_catalog().props_for(class_name))


class FakeBlock:
    """Фейк блока, повторяющий поведение среды там, где это важно тесту.

    Живой `SetBlockProp` не отвергает неизвестное имя (параметр просто не
    применяется) и не переименовывает блок: `Name` — документированный no-op,
    имя остаётся автоматическим (`k_0`). Фейк, хранивший любое имя и умевший
    переименование, скрывал оба дефекта — ни один юнит-тест не мог поймать
    ложный успех.
    """

    def __init__(self, bid, class_name):
        self.id = bid
        self.class_name = class_name
        self.props = {}
        # Имя автоматическое — его даёт SimInTech, а не вызывающий.
        self.name = f"{class_name[:2]}_{bid}"
        self.inited = 0

    def set_property(self, k, v):
        # Как `SetBlockProp`: неизвестное имя теряется молча, `Name` не
        # переименовывает.
        if k == "Name" or k not in _known_props(self.class_name):
            return self
        self.props[k] = v
        return self

    def get_name(self):
        return self.name

    def set_name(self, n):
        # Переименование через COM недоступно — no-op, а не запись имени.
        return self

    def init(self):
        self.inited += 1
        return self

    def connect(self, other, out_index=0, in_index=0):
        return FakeWire(900 + self.id + other.id)


class FakeWire:
    def __init__(self, wid):
        self.id = wid


class FakePage:
    def __init__(self, pid):
        self.pid = pid
        self.blocks = []

    def create_block(self, cls, x, y, **kw):
        b = FakeBlock(1000 + len(self.blocks), cls)
        self.blocks.append(b)
        return b


class FakeProject:
    #: Какая фабрика вызвана. Нужна, чтобы тест различал `new` и `from_template`:
    #: первый даёт проект, в котором расчёт не идёт, и проверка «создан» без
    #: этого прошла бы при любой из них.
    used_factory = None

    def __init__(self, pid=1):
        self.id = pid
        self.page = FakePage(50)
        self.sim = FakeSim()
        #: Закрыт ли проект: смену проекта без закрытия предыдущего иначе
        #: не отличить — она никак себя не проявляет.
        self.closed = False

    @classmethod
    def new(cls, client):
        cls.used_factory = "new"
        return cls(1)

    @classmethod
    def from_template(cls, client, template=None):
        cls.used_factory = "from_template"
        return cls(1)

    def get_main_page(self):
        return self.page

    def simulation(self):
        return self.sim

    def save_xml(self, path):
        self.saved_to = path

    def close(self):
        self.closed = True


class FakeSim:
    def __init__(self):
        #: Модельное время: `get_time` возвращает именно его, а `run_to` двигает.
        #: Без этого проверка «время сдвинулось» была бы неотличима.
        self.time = 0.0

    def start(self):
        self.started = True
        return self

    def run(self):
        self.ran = True
        return self

    def run_to(self, t):
        self.ran_to = t
        self.time = float(t)
        return True

    def step(self):
        self.steps = getattr(self, "steps", 0) + 1
        # Шаг двигает модельное время: без этого проверка «время сдвинулось»
        # в `_cmd_step` была бы неотличима.
        self.time += 0.001
        return self

    def stop(self):
        self.stopped = True
        return self

    def get_time(self):
        return self.time


class FakeClient:
    def __init__(self):
        self.connected = True
        self.silent = 1

    def set_silent_mode(self, v):
        self.silent = v


@pytest.fixture()
def agent():
    a = SimInTechAgent(client=FakeClient(), auto_connect=False)
    # Подменяем Project фабрики фейками
    a._project = FakeProject()
    # След фабрики — атрибут классовый, поэтому сбрасываем его здесь: без
    # сброса проверка `used_factory == "from_template"` зависела бы от того,
    # какие тесты успели выполниться раньше в том же процессе.
    FakeProject.used_factory = None
    return a


def test_create_project_ok(agent):
    agent._project = None
    import simintech_api.agent as ag
    orig = ag.Project
    ag.Project = FakeProject
    try:
        r = agent.execute('create project "MyModel"')
    finally:
        ag.Project = orig
    assert r.ok
    assert "MyModel" in r.message
    # Именно шаблон: `Project.new` дал бы проект, в котором расчёт не идёт.
    assert FakeProject.used_factory == "from_template"


def test_create_project_closes_previous(agent):
    """Новый проект закрывает предыдущий — иначе они копятся в mmain.exe.

    У каждого брошенного проекта остаётся свой расчётный слой и база сигналов,
    а `CloseProject` для него уже некому вызвать: счётчик проектов растёт, и
    ошибки при этом нет.
    """
    previous = agent._project
    import simintech_api.agent as ag
    orig = ag.Project
    ag.Project = FakeProject
    try:
        r = agent.execute('create project "B"')
    finally:
        ag.Project = orig

    assert r.ok
    assert previous.closed is True
    assert agent._project is not previous


def test_previous_project_close_failure_is_reported(agent):
    """Неудача закрытия предыдущего — примечание в успешном ответе.

    Новый проект уже создан, и отменять его нельзя: отказ закрытия сообщается,
    но результатом команды остаётся новый проект.
    """
    def boom():
        raise RuntimeError("COM занят")

    agent._project.close = boom
    import simintech_api.agent as ag
    orig = ag.Project
    ag.Project = FakeProject
    try:
        r = agent.execute('create project "C"')
    finally:
        ag.Project = orig

    assert r.ok
    assert "не закрыт" in r.message
    assert "COM занят" in r.message


def test_run_reports_failure_when_target_not_reached(agent):
    """Недостижение отметки — неудача, даже если время тронулось.

    `run_to` возвращает True, только если время **дошло** до цели. Проверять
    вместо этого «время сдвинулось» мало: расчёт может пойти и встать на 3 с
    при цели 10 с — тогда любой рост времени был бы выдан за достижение
    запрошенного, то есть за ложный успех.
    """
    def stalls(target):
        agent._project.sim.time = 3.0        # тронулось, но до 10 не дошло
        return False

    agent._project.sim.run_to = stalls

    r = agent.execute("run for 10 seconds")

    assert not r.ok
    assert "не дошёл до 10" in r.message
    assert "3.000" in r.message


def test_run_reports_failure_when_time_did_not_move(agent):
    """Совсем стоящий расчёт — тоже отказ, а не «выполнено»."""
    agent._project.sim.run_to = lambda target: False

    r = agent.execute("run for 10 seconds")

    assert not r.ok
    assert "не дошёл" in r.message


def test_run_for_zero_is_success(agent):
    """`run for 0 seconds` — не отказ: цель уже достигнута.

    Проверка «время сдвинулось» отвергала такую команду, потому что двигаться
    времени было некуда, — хотя делать было нечего и расчёт тут ни при чём.
    """
    r = agent.execute("run for 0 seconds")

    assert r.ok


def test_step_reports_stalled_time(agent):
    """`step` — тот же класс, что `run`: шаги без продвижения не успех.

    `ProjectStep` сообщает об успехе и на проекте, где расчёт стоит.
    """
    agent._project.sim.step = lambda: None      # время не двигает

    r = agent.execute("step 5")

    assert not r.ok
    assert "не сдвинулось" in r.message


def test_add_block(agent):
    """Параметр из каталога применяется, блок инициализируется.

    `a` у «Константы» есть, а `y0` — нет; запись в существующее имя должна
    доходить до блока и сопровождаться `InitBlock` (иначе блок считает по
    старому значению). Имя при этом остаётся автоматическим: сообщение
    называет фактическое, а алиас — ключом реестра агента.
    """
    r = agent.execute('add block "Константа" as k1 at (0, 0) with a=5')
    assert r.ok
    block = agent._blocks["k1"]
    assert block.props.get("a") == 5
    assert block.inited == 1
    assert block.get_name() in r.message
    assert "k1" in r.message


def test_add_block_rejects_unknown_param(agent):
    """Неизвестный параметр — отказ со списком известных, а не молчание.

    Живой `SetBlockProp` не отвергает неизвестное имя: у «Константы» нет
    `y0`, запись была бы потеряна молча, а ответ — успешным. Ошибку видно
    только по расчёту, поэтому проверка обязана стоять до создания блока.
    """
    r = agent.execute('add block "Константа" as k1 at (10, 20) with y0=5')

    assert not r.ok
    assert "y0" in r.message
    assert "a" in r.message              # список известных имён
    assert agent._blocks == {}           # ни блока, ни записи параметра
    assert agent._project.page.blocks == []


def test_fake_block_matches_com(agent):
    """Фейк не должен «уметь больше» среды: иначе юнит-тесты слепы.

    Живой `SetBlockProp` молча отбрасывает неизвестное имя и не
    переименовывает блок. Пока фейк хранил любое имя и умел `set_name`,
    ни один тест не мог поймать ложный успех агента.
    """
    agent.execute('add block "Константа" as k1 with a=5')
    block = agent._blocks["k1"]

    block.set_property("y0", 7)            # у «Константы» такого имени нет
    block.set_name("переименован")

    assert "y0" not in block.props
    assert block.get_name() != "переименован"


def test_add_block_default_name(agent):
    r = agent.execute('add block "Усилитель" at (10, 10) with a=2')
    assert r.ok
    assert any(b.class_name == "Усилитель" for b in agent._blocks.values())


def test_connect(agent):
    agent.execute('add block "Константа" as k1 with a=5')
    agent.execute('add block "Усилитель" as g1 with a=2')
    r = agent.execute("connect k1.out to g1.in")
    assert r.ok
    assert "Соединено" in r.message
    assert len(agent._wires) == 1


def test_connect_unknown_block(agent):
    r = agent.execute("connect k1.out to g1.in")
    assert not r.ok
    assert "не найден" in r.message.lower()


def test_run(agent):
    r = agent.execute("run for 10 seconds")
    assert r.ok
    assert agent._project.sim.ran_to == 10.0


def test_step(agent):
    r = agent.execute("step 5")
    assert r.ok
    assert agent._project.sim.steps == 5


def test_unknown_command(agent):
    r = agent.execute("фывапрокд")
    assert not r.ok
    assert "Не распознана" in r.message


def test_help(agent):
    r = agent.execute("help")
    assert r.ok
    assert "create project" in r.message


def test_no_project(agent):
    agent._project = None
    r = agent.execute("add block \"Константа\" as k1")
    assert not r.ok
    assert "проекта" in r.message.lower()
