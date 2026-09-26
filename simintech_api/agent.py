"""SimInTechAgent — единая точка входа для ИИ-агента.

Принимает команды на русском (и частично английском) языке, парсит их и
выполняет через simintech_api. Предназначен для цепочек ИИ-агента:
«спланировать модель → создать → разместить → соединить → запустить → верифицировать».

Примеры команд:
    create project "MyModel"
    add block "Константа" as k1 at (10, 20) with a=5
    add block "Усилитель" as g1 at (200, 20) with a=2
    connect k1.out to g1.in
    run for 10 seconds
    get signal "g1.out"
    save project "MyModel.xprt"
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .catalog import load_default_catalog
from .core.com_client import COMClient
from .core.project import Project


class CommandResult:
    """Результат выполнения команды агентом."""

    def __init__(self, ok: bool, message: str, data: Any = None):
        self.ok = ok
        self.message = message
        self.data = data

    def __repr__(self) -> str:  # pragma: no cover
        status = "OK" if self.ok else "ERROR"
        return f"[{status}] {self.message}"

    def __bool__(self) -> bool:
        return self.ok


class SimInTechAgent:
    """Управление SimInTech через текстовые команды.

    Args:
        client: COM-клиент (уже подключённый) или None для авто-подключения.
        auto_connect: подключиться автоматически при первой команде.
    """

    def __init__(self, client: Optional[COMClient] = None,
                 auto_connect: bool = True):
        self._client = client
        self._auto_connect = auto_connect
        self._project: Optional[Project] = None
        # Реестр созданных блоков по имени: {alias: (block, page)}
        self._blocks: Dict[str, Any] = {}
        # Список созданных линий
        self._wires: List[Any] = []

    # ─── Инфраструктура ─────────────────────────────────────────────

    @property
    def client(self) -> COMClient:
        """COM-клиент (автоподключение при первом обращении)."""
        if self._client is None or not self._client.connected:
            if not self._auto_connect:
                raise RuntimeError(
                    "COM-клиент не подключён. Выполните connect() сначала."
                )
            self._client = COMClient(silent_mode=True).connect()
        return self._client

    def execute(self, command: str) -> CommandResult:
        """Выполнить текстовую команду и вернуть результат."""
        command = command.strip()
        if not command:
            return CommandResult(False, "Пустая команда")

        handlers = [
            (r"^(?:create|new)\s+project\s+(.+)$", self._cmd_new_project),
            (r"^open\s+project\s+(.+)$", self._cmd_open_project),
            (r"^close\s+project$", self._cmd_close_project),
            (r"^save\s+project\s+(\S+\.xprt)$", self._cmd_save_project),
            (r"^add\s+block\s+\"([^\"]+)\"(?:\s+as\s+(\w+))?"
             r"(?:\s+at\s+\((-?[\d.]+)\s*,\s*(-?[\d.]+)\))?"
             r"(?:\s+with\s+(.+))?$", self._cmd_add_block),
            (r"^connect\s+([\w.]+)\s+to\s+([\w.]+)$", self._cmd_connect),
            (r"^run(?:\s+for\s+([\d.]+)\s+seconds?)?$", self._cmd_run),
            (r"^step(?:\s+(\d+))?$", self._cmd_step),
            (r"^stop$", self._cmd_stop),
            (r"^get\s+signal\s+\"([^\"]+)\"$", self._cmd_get_signal),
            (r"^set\s+signal\s+\"([^\"]+)\"\s+to\s+(-?[\d.]+)$",
             self._cmd_set_signal),
            (r"^(?:list|show)\s+blocks$", self._cmd_list_blocks),
            (r"^(?:list|show)\s+signals$", self._cmd_list_signals),
            (r"^help$", self._cmd_help),
        ]

        for pattern, handler in handlers:
            m = re.match(pattern, command, re.IGNORECASE)
            if m:
                try:
                    return handler(*m.groups())
                except Exception as exc:
                    return CommandResult(False, f"{type(exc).__name__}: {exc}")
        return CommandResult(
            False,
            f"Не распознана команда: '{command}'. Наберите 'help'.",
        )

    # ─── Команды ────────────────────────────────────────────────────

    def _replace_project(self, project: Project) -> Optional[str]:
        """Сделать `project` текущим, закрыв предыдущий.

        Без закрытия проекты копятся внутри `mmain.exe` — у каждого свой
        расчётный слой и база сигналов, — и `CloseProject` для прежнего уже
        некому вызвать. Возвращает примечание, если предыдущий не закрылся:
        неудача закрытия не должна отменять уже созданный проект.
        """
        previous = self._project
        self._project = project
        self._blocks.clear()
        self._wires.clear()
        if previous is None:
            return None
        try:
            previous.close()
        except Exception as exc:
            return (f"предыдущий проект (id={previous.id}) не закрыт: "
                    f"{type(exc).__name__}: {exc}")
        return None

    def _cmd_new_project(self, name: str) -> CommandResult:
        # Не `Project.new`: он даёт пустой проект без моделирующего слоя и
        # настроек расчёта, поэтому расчёт в нём не идёт — модельное время
        # стоит, хотя вызовы сообщают об успехе. Шаблон из поставки даёт
        # проект с расчётным слоем «Автоматика».
        project = Project.from_template(self.client)
        note = self._replace_project(project)
        message = f"Проект '{name}' создан (id={project.id})"
        if note:
            message = f"{message} ({note})"
        return CommandResult(True, message)

    def _cmd_open_project(self, path: str) -> CommandResult:
        project = Project.open(self.client, path.strip().strip('"'))
        note = self._replace_project(project)
        message = f"Проект открыт (id={project.id})"
        if note:
            message = f"{message} ({note})"
        return CommandResult(True, message)

    def _cmd_close_project(self) -> CommandResult:
        if not self._project:
            return CommandResult(False, "Нет открытого проекта")
        self._project.close()
        self._project = None
        return CommandResult(True, "Проект закрыт")

    def _cmd_save_project(self, path: str) -> CommandResult:
        if not self._project:
            return CommandResult(False, "Нет открытого проекта")
        self._project.save_xml(path)
        return CommandResult(True, f"Проект сохранён в '{path}'")

    def _cmd_add_block(self, class_name, alias, x, y, props) -> CommandResult:
        if not self._project:
            return CommandResult(
                False, "Нет открытого проекта. Сначала: create project")
        pairs: List[Tuple[str, Any]] = []
        if props:
            for pair in _split_props(props):
                key, _, value = pair.partition("=")
                pairs.append((key.strip(), _parse_value(value.strip())))
        # Сверка с каталогом **до** создания блока: `SetBlockProp` не
        # отвергает неизвестное имя, и без неё запись была бы потеряна молча.
        problem = _check_props(class_name, [key for key, _ in pairs])
        if problem:
            return CommandResult(False, problem)
        cx = float(x) if x else 0.0
        cy = float(y) if y else 0.0
        page = self._project.get_main_page()
        block = page.create_block(class_name, cx, cy)
        for key, value in pairs:
            block.set_property(key, value)
        if pairs:
            # Уже инициализированные блоки («Константа») считают по старому
            # значению, пока не вызван `InitBlock` (com_api_inventory.md §17).
            block.init()
        actual = block.get_name()
        name = alias or actual
        if alias:
            block.set_name(alias)
        self._blocks[name] = block
        if alias and alias != actual:
            # `SetBlockProp("Name")` не переименовывает блок: имя остаётся
            # автоматическим, поэтому в ответе — фактическое, а алиас назван
            # тем, чем он и является, — ключом реестра агента.
            return CommandResult(
                True,
                f"Блок '{class_name}' добавлен как '{actual}' (id={block.id}); "
                f"'{alias}' — алиас внутри агента: переименование через COM "
                f"недоступно",
            )
        return CommandResult(
            True, f"Блок '{class_name}' добавлен как '{actual}' (id={block.id})"
        )

    def _cmd_connect(self, source: str, target: str) -> CommandResult:
        if not self._project:
            return CommandResult(False, "Нет открытого проекта")
        src_block, src_port = _split_ref(source)
        dst_block, dst_port = _split_ref(target)
        b1 = self._blocks.get(src_block)
        b2 = self._blocks.get(dst_block)
        if b1 is None:
            return CommandResult(False, f"Блок '{src_block}' не найден")
        if b2 is None:
            return CommandResult(False, f"Блок '{dst_block}' не найден")
        wire = b1.connect(b2, out_index=src_port, in_index=dst_port)
        self._wires.append(wire)
        return CommandResult(True, f"Соединено: {source} -> {target} (wire={wire.id})")

    def _cmd_run(self, seconds: Optional[str]) -> CommandResult:
        if not self._project:
            return CommandResult(False, "Нет открытого проекта")
        sim = self._project.simulation()
        sim.start()
        if seconds is not None:
            target = float(seconds)
            # `run_to` возвращает True, только если время **дошло** до отметки
            # (опросом `GetProjectTime`, с ожиданием и детекцией простоя).
            # Проверять вместо этого «время сдвинулось» нельзя: расчёт может
            # пойти и встать, не дойдя до цели, — тогда любой рост времени был
            # бы выдан за достижение запрошенного.
            reached = sim.run_to(target)
            t = sim.get_time()
            if not reached:
                return CommandResult(
                    False,
                    f"Расчёт не дошёл до {target} с: модельное время {t:.3f}. "
                    f"Частые причины: не соединён вход какого-то блока — это "
                    f"молча останавливает расчёт всей модели; цель дальше "
                    f"`endtime` проекта; расчёт не идёт вовсе.",
                )
            return CommandResult(
                True,
                f"Расчёт выполнен до {target} с (модельное время={t:.3f})",
            )
        sim.run()
        return CommandResult(True, "Расчёт запущен")

    def _cmd_step(self, steps: Optional[str]) -> CommandResult:
        if not self._project:
            return CommandResult(False, "Нет открытого проекта")
        sim = self._project.simulation()
        sim.start()
        n = int(steps) if steps else 1
        before = sim.get_time()
        for _ in range(n):
            sim.step()
        t = sim.get_time()
        if t <= before:
            # `ProjectStep` сообщает об успехе и на проекте, где расчёт стоит:
            # шаги, которых не было, — не успех, как и недостигнутая отметка
            # в `run`.
            return CommandResult(
                False,
                f"Модельное время не сдвинулось после {n} шагов ({t:.3f} с) — "
                f"расчёт не идёт. Проверьте, соединены ли входы блоков.",
            )
        return CommandResult(
            True, f"Выполнено шагов: {n} (время: {before:.3f} → {t:.3f})")

    def _cmd_stop(self) -> CommandResult:
        if not self._project:
            return CommandResult(False, "Нет открытого проекта")
        self._project.simulation().stop()
        return CommandResult(True, "Расчёт остановлен")

    def _cmd_get_signal(self, name: str) -> CommandResult:
        if not self._project:
            return CommandResult(False, "Нет открытого проекта")
        sig = self._project.signal(name)
        value = sig.read()
        return CommandResult(True, f"{name} = {value}", value)

    def _cmd_set_signal(self, name: str, value: str) -> CommandResult:
        if not self._project:
            return CommandResult(False, "Нет открытого проекта")
        sig = self._project.signal(name)
        sig.write(_parse_value(value))
        return CommandResult(True, f"{name} = {value}")

    def _cmd_list_blocks(self) -> CommandResult:
        if not self._blocks:
            return CommandResult(True, "Нет созданных блоков")
        lines = [
            f"  {name}: {b.class_name} (id={b.id})"
            for name, b in self._blocks.items()
        ]
        return CommandResult(True, "Блоки:\n" + "\n".join(lines))

    def _cmd_list_signals(self) -> CommandResult:
        if not self._project:
            return CommandResult(False, "Нет открытого проекта")
        signals = self._project.list_signals()
        lines = [f"  {s.name}" for s in signals[:50]]
        more = "" if len(signals) <= 50 else f"\n  ... и ещё {len(signals) - 50}"
        return CommandResult(True, "Сигналы:\n" + "\n".join(lines) + more)

    def _cmd_help(self) -> CommandResult:
        help_text = """Доступные команды:
  create project "Имя"
  open project "путь.prt"
  add block "Класс" [as имя] [at (x, y)] [with prop=value, prop2=value]
  connect имя1.out to имя2.in          (индексы: имя.out0, имя.in1)
  run [for N seconds]
  step [N steps]
  stop
  get signal "имя_сигнала"
  set signal "имя_сигнала" to value
  list blocks / list signals
  save project "путь.xprt"
  close project
"""
        return CommandResult(True, help_text)


# ─── Утилиты парсинга ──────────────────────────────────────────────


def _check_props(class_name: str, names: List[str]) -> Optional[str]:
    """Сверить имена параметров с каталогом: текст отказа или ``None``.

    `SetBlockProp` не отвергает неизвестное имя: параметр «устанавливается»,
    ошибки не возникает, а расчёт идёт по прежнему значению. Поэтому имя
    проверяется по ``data/block_catalog.json`` **до** записи — иначе отличить
    применённый параметр от потерянного по ответу нельзя.

    Класс вне каталога не проверяется: сверить нечем, и об этом нечего
    сказать — таково же поведение защитного слоя MCP.
    """
    catalog = load_default_catalog()
    if not catalog.has(class_name):
        return None
    known = catalog.props_for(class_name)
    unknown = [name for name in names if name not in known]
    if unknown:
        return (
            f"Неизвестные параметры блока '{class_name}': "
            f"{', '.join(unknown)}. Известные имена: {', '.join(known)}."
        )
    computed = [name for name in names
                if catalog.is_readonly(class_name, name)]
    if computed:
        return (
            f"Параметры блока '{class_name}' вычисляемые — запись в них "
            f"ничего не меняет: {', '.join(computed)}."
        )
    return None


def _split_ref(ref: str) -> Tuple[str, int]:
    """Разобрать ссылку 'block.out0' -> (block, индекс=0)."""
    if "." not in ref:
        return ref, 0
    name, _, idx = ref.partition(".")
    m = re.match(r"(in|out)(\d*)", idx, re.IGNORECASE)
    if not m:
        return name, 0
    return name, int(m.group(2) or 0)


def _split_props(props: str) -> List[str]:
    """Разбить строку 'a=2, y0=5' на пары (корректно с запятыми в скобках)."""
    parts: List[str] = []
    buf = ""
    depth = 0
    for ch in props:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(buf)
            buf = ""
        else:
            buf += ch
    if buf.strip():
        parts.append(buf)
    return [p.strip() for p in parts]


def _parse_value(text: str) -> Any:
    """Разобрать значение свойства: число, bool, строка, массив."""
    text = text.strip()
    if text.lower() in ("true", "истина"):
        return True
    if text.lower() in ("false", "ложь"):
        return False
    if text.startswith("[") and text.endswith("]"):
        return [_parse_value(v.strip()) for v in text[1:-1].split(",")]
    try:
        if "." in text or "e" in text.lower():
            return float(text)
        return int(text)
    except ValueError:
        return text.strip("'\"")
