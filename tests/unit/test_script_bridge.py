"""Мост на фейковом клиенте: какие COM-вызовы он делает и в каком порядке.

Фейк моделирует **изменение состояния**, а не отдаёт удобный ответ:
`SetPageScript` перезаписывает скрипт **текущей** страницы, а `SaveProjectXML`
выгружает скрипты **всех** страниц в том же закодированном виде, в каком это
делает среда (сверено с поставкой). Иначе тесты подтверждали бы допущения
автора, а не поведение: первая версия фейка возвращала статический текст и не
замечала ни перестановки снимка и установки, ни потери скрипта.

Страниц минимум две и между ними есть переходы (`GetCurentPage`/
`SetCurrentPage`): на одной странице поведение из замера «стирается скрипт
неглавной страницы» невоспроизводимо, и тест его не поймал бы.
"""

import os
import sys
import tempfile
import warnings
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest  # noqa: E402

from simintech_api.core.script_bridge import ScriptBridge  # noqa: E402
from simintech_api.exceptions import (  # noqa: E402
    ScriptBridgeError,
    ScriptBridgeUnsafeStateError,
    SimInTechError,
)
from simintech_api.script_probe import BEGIN_MARKER, END_MARKER  # noqa: E402

MAIN = r"C:\work\model.prt"

#: Коды, которыми среда пишет символы внутри значения `<script>`. Набор — из
#: замера 8 спеки: кроме переводов строк и обратной кавычки среда кодирует
#: `<` `>` `&` и `'`, а кавычку — нет (она остаётся в значении буквально).
_SPECIAL = {"\r": 13, "\n": 10, "\t": 9, "<": 60, ">": 62, "&": 38, "'": 39,
            "`": 96}


def _encode_value(text: str) -> str:
    """Закодировать скрипт так, как это делает `SaveProjectXML`.

    Пустой скрипт пишется **без кавычек** — форма, которой не было в первой
    версии тестов и из-за которой разбор не совпадал ни с одной страницей.
    """
    if not text:
        return ""
    parts, buf = [], []
    for char in text:
        if char in _SPECIAL:
            if buf:
                parts.append("`" + "".join(buf) + "`")
                buf = []
            parts.append(f"#{_SPECIAL[char]}")
        else:
            buf.append(char)
    if buf:
        parts.append("`" + "".join(buf) + "`")
    return "".join(parts)


class FakeEnv:
    """Клиент, моделирующий состояние проекта, а не подставляющий ответы."""

    def __init__(self, *, pages=(MAIN, "Container"), installed="seterrorflag(0);",
                 other_scripts=None, current_index=0, time_grows=True,
                 initial_time=0.0, writes_result=True,
                 script_result=END_MARKER + "\n",
                 restore_raises=None, restore_is_ignored=False,
                 foreign_change_on_restore=False, page_moves_on_step=False,
                 restore_writes_other_text=False,
                 set_current_page_is_ignored=False,
                 probe_install_raises_after_apply=False,
                 dump_fails_after_install=False,
                 save_project_xml_writes_nothing=False,
                 page_scripts_not_serialized=False,
                 pages_added_by_run=0,
                 state_read_raises=None, start_raises=None,
                 stop_raises=None, stop_is_ignored=False,
                 state_read_raises_after_stop=None,
                 current_page_raises=False,
                 dump_fails_before_install=False):
        #: Имена страниц — как их пишет выгрузка; первая всегда главная.
        self.pages = list(pages)
        #: Скрипты страниц. Имя `installed` сохранено намеренно: на нём стоят
        #: шесть существующих тестов, и оно честно называет, что это — скрипт,
        #: лежавший в проекте до пробы.
        self.scripts = [installed] + list(
            other_scripts if other_scripts is not None
            else [""] * (len(self.pages) - 1))
        self.current_index = current_index
        self.time_grows = time_grows
        self.initial_time = initial_time
        self.writes_result = writes_result
        self.script_result = script_result
        #: Значение, при попытке поставить которое SetPageScript бросит —
        #: модель «возврат прежнего скрипта не прошёл».
        self.restore_raises = restore_raises
        #: Модель молчаливого отказа: вызов проходит, но ни на что не влияет.
        self.restore_is_ignored = restore_is_ignored
        #: Модель «возврат состоялся, но состояние проекта изменилось не только
        #: из-за пробы»: на возврате правится запись ЧУЖОЙ страницы. Выключено
        #: по умолчанию — иначе этот эффект подмешивался бы во все тесты.
        self.foreign_change_on_restore = foreign_change_on_restore
        #: Модель «расчёт увёл текущую страницу»: `gotopage` во встроенном языке
        #: существует, и после пробы страница может быть уже не та, с которой
        #: начинали. Выключено по умолчанию.
        self.page_moves_on_step = page_moves_on_step
        #: Модель «возврат записал не тот текст»: страница получает чужой
        #: скрипт, и прежнего текста записи в снимке не оказывается.
        self.restore_writes_other_text = restore_writes_other_text
        #: Модель «SetCurrentPage молча ничего не делает» — замеренный контракт
        #: среды. Без этого фейк повторял бы допущение кода, что переход идёт.
        self.set_current_page_is_ignored = set_current_page_is_ignored
        #: Модель «COM-вызов применился и упал после применения»: установка
        #: пробы выполняется, а исключение приходит от таймаута.
        self.probe_install_raises_after_apply = probe_install_raises_after_apply
        #: Модель «после установки пробы снимок снять нельзя»: SaveProjectXML
        #: перестаёт работать, как только проба в проекте.
        self.dump_fails_after_install = dump_fails_after_install
        #: Модель молчаливого SaveProjectXML: код возврата 1, файла нет.
        self.save_project_xml_writes_nothing = save_project_xml_writes_nothing
        #: Модель «скрипт этой страницы в выгрузку не попадает»: состояние
        #: меняется, а запись `<script>` остаётся прежней. Отличается от
        #: `writes_are_not_serialized` тем, что там не меняется и состояние.
        self.page_scripts_not_serialized = page_scripts_not_serialized
        #: Модель активации страниц расчётом: столько страниц (с записью
        #: скрипта) прибавляется к выгрузке за прогон. Множество страниц в
        #: реальном проекте не постоянно, и фейк, считающий его постоянным,
        #: повторяет допущение кода — вместе с ним и прячет ложный отказ.
        self.pages_added_by_run = pages_added_by_run
        #: Модель «установленный скрипт в выгрузку не попадает»: вызов
        #: проходит, состояние меняется, а выгрузка этого не отражает.
        self.writes_are_not_serialized = False
        #: Индексы страниц, чьи скрипты в выгрузке идут СЫРЫМ текстом, который
        #: кодек покрывает не весь. Модель повреждённой записи: установка пробы
        #: такую запись заменяет целиком, поэтому сырость снимается при записи.
        self.raw_scripts = {}
        self.calls = []
        self._stepped = False
        # ─── Состояние расчёта ────────────────────────────────────────
        # Флаг моделирует **переход**, а не константу: без перехода фейк не
        # различает «расчёт начали мы» и «он шёл до нас», и любая проверка
        # владения/остановки на нём слепа. Значения — из измеренной маски
        # (automation/com-api.md): 0 остановлен, 1 инициализирован, 7 пауза.
        self.state = 0
        #: Модель «состояние прочитать нельзя». Различать важно, ГДЕ оно
        #: нечитаемо: на входе это отказ до всякой работы (проба могла бы
        #: уничтожить чужой расчёт), после остановки — «подтвердить нечем».
        self.state_read_raises = state_read_raises
        #: Модель «после ProjectStop состояние стало нечитаемым».
        self.state_read_raises_after_stop = state_read_raises_after_stop
        self._stop_called = False
        #: Модель «ProjectStart упал»: был ли он применён — неизвестно.
        self.start_raises = start_raises
        #: Модель «ProjectStop упал»: отказ, а не молчание.
        self.stop_raises = stop_raises
        #: Модель молчаливого ProjectStop: вызов проходит, состояние не меняется.
        self.stop_is_ignored = stop_is_ignored
        #: Модель «входные пути преамбулы падают сырым исключением»:
        #: `GetCurentPage` и снимок «до» стоят до изменений в проекте, и сбой
        #: там обязан выходить ошибкой моста, а не сбоем клиента.
        self.current_page_raises = current_page_raises
        self.dump_fails_before_install = dump_fails_before_install

    def call(self, name, *args):
        self.calls.append((name, args))
        if name == "SaveProjectXML":
            if self.dump_fails_before_install and not self._probe_installed():
                raise OSError("COM недоступен")
            if self.dump_fails_after_install and self._probe_installed():
                raise OSError("COM недоступен")
            if self.save_project_xml_writes_nothing:
                return 1
            body = "".join(
                f"<page>\n <name>{'`' + page + '`' if page else ''}</name>\n"
                f" <script>{self._record(i)}</script>\n</page>\n"
                for i, page in enumerate(self.pages))
            Path(args[1]).write_text(body, encoding="utf-8")
            return 1
        if name == "SetPageScript":
            if self.restore_raises is not None and args[1] == self.restore_raises:
                raise OSError("COM недоступен")
            if self.foreign_change_on_restore and "createfile(" not in args[1]:
                # Правится чужая страница: снимок после возврата разойдётся с
                # прежним не в записи цели. Эффект независим от молчания самого
                # вызова, поэтому применяется до ранних возвратов ниже.
                self.raw_scripts[1 - self.current_index] = "`изменено вне пробы`"
            if self.restore_writes_other_text and "createfile(" not in args[1]:
                # Возврат записал не тот текст: прежней записи в снимке нет.
                self.raw_scripts.pop(self.current_index, None)
                self.scripts[self.current_index] = "`испорчено`"
                return 1
            if self.restore_is_ignored and "createfile(" not in args[1]:
                return 1
            if self.writes_are_not_serialized:
                return 1
            # запись, пришедшая сырой, установка заменяет целиком
            self.raw_scripts.pop(self.current_index, None)
            if (self.page_scripts_not_serialized
                    and "createfile(" in args[1]):
                # Состояние меняется, а выгрузка показывает прежнее значение
                # записи: по такому снимку судить о пробе нельзя.
                self.raw_scripts[self.current_index] = _encode_value(
                    self.scripts[self.current_index])
            self.scripts[self.current_index] = args[1]
            if (self.probe_install_raises_after_apply
                    and "createfile(" in args[1]):
                # Запись применена, а исключение пришло уже после — как от
                # таймаута COM: «не установлено» здесь была бы догадкой.
                raise OSError("COM недоступен")
            return 1
        if name == "GetCurentPage":
            if self.current_page_raises:
                raise OSError("COM недоступен")
            return 1000 + self.current_index
        if name == "SetCurrentPage":
            if not self.set_current_page_is_ignored:
                self.current_index = int(args[1]) - 1000
            return 1
        if name == "ProjectStart":
            if self.start_raises is not None:
                raise self.start_raises
            self._stepped = False
            self.state = 1
            return 1
        if name == "ProjectStop":
            if self.stop_raises is not None:
                raise self.stop_raises
            self._stop_called = True
            if not self.stop_is_ignored:
                self.state = 0
            return 1
        if name == "GetProjectStateFlag":
            if self.state_read_raises is not None:
                raise self.state_read_raises
            if (self.state_read_raises_after_stop is not None
                    and self._stop_called):
                raise self.state_read_raises_after_stop
            return self.state
        if name == "ProjectStep":
            self._stepped = True
            self.state = 7
            self._maybe_write_result()
            if self.page_moves_on_step:
                # Страница уходит ПОСЛЕ записи результата: иначе проба не
                # записала бы файл, и отказ пришёл бы раньше возврата.
                self.current_index = 1 - self.current_index
            for extra in range(self.pages_added_by_run):
                # Активация страницы расчётом: у неё своя запись скрипта, и
                # выгрузка становится длиннее, чем была до прогона.
                self.pages.append(f"Activated{extra}")
                self.scripts.append("`активировано`")
            return 1
        if name == "GetProjectTime":
            if self.time_grows and self._stepped:
                return self.initial_time + 0.1
            return self.initial_time
        return 1

    def _probe_installed(self):
        """Стоит ли в проекте пробный скрипт — по наличию `createfile(`."""
        return any("createfile(" in script for script in self.scripts)

    def _record(self, index):
        """Значение `<script>` для страницы: сырое, если помечена повреждённой."""
        if index in self.raw_scripts:
            return self.raw_scripts[index]
        return _encode_value(self.scripts[index])

    def _maybe_write_result(self):
        # Пробу исполняет **текущая** страница: скрипт в неё и ставится.
        script = self.scripts[self.current_index]
        if not self.writes_result or "createfile(" not in script:
            return
        start = script.index('createfile("') + len('createfile("')
        end = script.index('"', start)
        Path(script[start:end]).write_text(
            BEGIN_MARKER + "\n" + self.script_result, encoding="utf-8")

    def set_page_script_calls(self):
        return [args for name, args in self.calls if name == "SetPageScript"]


def _bridge(**kwargs):
    """Мост с коротким таймаутом: тест не должен ждать заводскую минуту."""
    env = FakeEnv(**kwargs)
    return env, ScriptBridge(env, project_id=42, time_growth_timeout_s=0.2)


def test_dump_records_uses_temporary_directory_and_removes_it():
    """Выгрузка идёт во временный каталог и удаляется вместе с ним."""
    env, bridge = _bridge()
    bridge._dump_records()

    name, args = [(n, a) for n, a in env.calls if n == "SaveProjectXML"][0]
    assert args[0] == 42
    exported = args[1]
    assert exported.startswith(tempfile.gettempdir())
    assert not os.path.exists(exported)


def test_run_probe_does_not_touch_project_when_token_already_present(tmp_path):
    """Метка из прошлого запуска (или коллизия) — отказ ДО установки пробы."""
    env, bridge = _bridge()
    env.scripts[0] = "//SCRIPT_BRIDGE_TARGET_deadbeefdeadbeef"
    with pytest.raises(ScriptBridgeUnsafeStateError):
        bridge.run_probe('writelnutf8(fid, "x");', tmp_path / "probe.txt")
    assert env.set_page_script_calls() == [], "проект тронут до проверки метки"


def test_run_probe_does_not_touch_script_of_another_page(tmp_path):
    """Та самая регрессия: проба уходит в текущую страницу, а не в главную.

    Измерено на поставке: `SetPageScript` пишет в **текущую** страницу, а
    прежний скрипт мост читал с главной, поэтому чтение внутри контейнера
    стирало скрипт этого контейнера и рапортовало об успешном восстановлении.
    """
    env, bridge = _bridge(installed="", other_scripts=["STAYS_HERE"],
                          current_index=1)
    bridge.run_probe('writelnutf8(fid, "x");', tmp_path / "probe.txt")
    assert env.scripts[1] == "STAYS_HERE", "скрипт текущей страницы потерян"
    assert env.scripts[0] == "", "тронули главную страницу, хотя проба шла не в ней"


def test_run_probe_restores_empty_script_of_the_page(tmp_path):
    """Пустой прежний скрипт — это скрипт, а не «нечего возвращать».

    Измерено ревью: мутация `if target is not None and original is not None`
    → `... and original:` выживает весь набор, а поведение теряет скрипт молча —
    страница с пустым прежним скриптом остаётся с пробой, `run_probe` сообщает
    об успехе. Пустой скрипт не редкость: на поставке таких 1006 из 1534
    страничных значений.
    """
    env, bridge = _bridge(installed="", other_scripts=["STAYS"], current_index=0)
    bridge.run_probe('writelnutf8(fid, "x");', tmp_path / "probe.txt")
    assert env.scripts[0] == "", "пустой прежний скрипт не вернулся — проба осталась"
    assert len(env.set_page_script_calls()) == 2, (
        "ожидались установка и возврат; один вызов означает, что возврат пропущен")


def test_run_probe_raises_unsafe_when_no_record_changed(tmp_path):
    """Скрипт текущей страницы не попал в выгрузку → цель не установлена.

    Модель: у страницы нет записи `<script>`, поэтому установка пробы в
    выгрузке ничего не меняет — вернуть прежний скрипт нечем.
    """
    env, bridge = _bridge()
    env.writes_are_not_serialized = True
    with pytest.raises(ScriptBridgeUnsafeStateError) as exc:
        bridge.run_probe('writelnutf8(fid, "x");', tmp_path / "probe.txt")
    assert "ни одна скриптовая запись" in str(exc.value)
    assert "считать пробу отсутствующей по нему нельзя" in str(exc.value), (
        "отказ выдал за факт то, чего снимок не показывает: записи этой "
        "страницы в выгрузке нет вовсе")


def test_run_probe_never_restores_partially_decoded_record(tmp_path):
    """Запись цели, которую кодек покрывает не весь, — отказ, а не «как выйдет».

    `decode_xprt_value` разбирает куски и коды, но не проверяет покрытие: если
    в записи есть текст вне кусков и кодов, разбор теряет символы и вернул бы на
    место **усечённый** скрипт. Ровно против этого в модуле есть `leftover_of`,
    и здесь проверяется, что мост им пользуется: цель найдена, но восстанавливать
    нечем — и повторной записи не происходит.
    """
    env, bridge = _bridge(installed="", other_scripts=["STAYS_HERE"],
                          current_index=1)
    env.raw_scripts = {1: "abc`не покрыто`"}   # текст вне кусков и кодов
    with pytest.raises(ScriptBridgeUnsafeStateError) as exc:
        bridge.run_probe('writelnutf8(fid, "x");', tmp_path / "probe.txt")
    assert "нераспознанный текст" in str(exc.value)
    assert "осталась проба" in str(exc.value), (
        "отказ не назвал состояние проекта: проба к этому моменту уже стоит "
        "в текущей странице, и метка это доказывает")
    assert len(env.set_page_script_calls()) == 1, (
        "после отказа восстановление всё равно писало скрипт")


def test_run_probe_returns_script_to_the_page_it_changed(tmp_path):
    """Возврат идёт в **изменённую** страницу, а не в текущую на тот момент.

    `SetPageScript` пишет в текущую страницу, а расчёт мог её увести
    (`gotopage` во встроенном языке существует). Возврат «куда стоим сейчас»
    положил бы прежний скрипт чужой странице, а свою оставил бы с пробой —
    то есть потерял бы сразу два скрипта.
    """
    env, bridge = _bridge(installed="// пользовательский",
                          other_scripts=["чужой"], page_moves_on_step=True)
    bridge.run_probe("", tmp_path / "out.txt")
    assert env.scripts[0] == "// пользовательский", "прежний скрипт не вернулся"
    assert env.scripts[1] == "чужой", "прежний скрипт попал в чужую страницу"


def test_run_probe_returns_complete_result(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    env, bridge = _bridge()
    result = bridge.run_probe('writelnutf8(fid, "ok");', tmp_path / "out.txt")
    assert result.complete is True


def test_run_probe_snapshots_before_installing(tmp_path):
    """Порядок «сначала снимок, потом подстановка» проверяется состоянием.

    Если поменять шаги местами, снимок возьмёт уже подставленный пробный
    скрипт, и вернуть будет нечего: скрипт пользователя потеряется.
    """
    env, bridge = _bridge(installed="// пользовательский")
    bridge.run_probe("", tmp_path / "out.txt")
    assert env.scripts[0] == "// пользовательский"


def test_run_probe_restores_script_and_verifies_it(tmp_path):
    env, bridge = _bridge(installed="// пользовательский")
    bridge.run_probe("", tmp_path / "out.txt")
    assert env.set_page_script_calls()[-1] == (42, "// пользовательский", 1)


def test_run_probe_restores_script_even_on_failure(tmp_path):
    env, bridge = _bridge(time_grows=False, installed="// пользовательский")
    with pytest.raises(ScriptBridgeError):
        bridge.run_probe("", tmp_path / "out.txt")
    assert env.set_page_script_calls()[-1] == (42, "// пользовательский", 1)


def test_run_probe_reports_restore_failure_without_masking_probe_error(tmp_path):
    """Сбой возврата не подменяет исходную причину — в тексте обе."""
    env, bridge = _bridge(time_grows=False, installed="// пользовательский",
                          restore_raises="// пользовательский")
    with pytest.raises(ScriptBridgeError) as exc:
        bridge.run_probe("", tmp_path / "out.txt")
    message = str(exc.value)
    assert "модельного времени" in message
    assert "не восстановлен" in message


def test_run_probe_detects_silently_failed_restore(tmp_path):
    """`SetPageScript` возвращает 1 всегда, поэтому возврат проверяется чтением.

    Здесь вызов проходит, но ни на что не влияет — ровно то, чего не поймать по
    коду возврата.
    """
    env, bridge = _bridge(installed="// пользовательский",
                          restore_is_ignored=True)
    with pytest.raises(ScriptBridgeError) as exc:
        bridge.run_probe("", tmp_path / "out.txt")
    assert "не восстановлен" in str(exc.value)


def test_run_probe_verifies_by_snapshot_not_by_reading_main_page(tmp_path):
    """Возврат сверяется снимком: смолчавший `SetPageScript` обязан быть замечен."""
    env, bridge = _bridge(restore_is_ignored=True)
    with pytest.raises(ScriptBridgeUnsafeStateError) as exc:
        bridge.run_probe('writelnutf8(fid, "x");', tmp_path / "probe.txt")
    assert "не восстановлен" in str(exc.value)


def test_run_probe_does_not_blame_probe_when_foreign_record_changed(tmp_path):
    """«Изменились чужие записи» — возврат состоялся, и обвинять в нём пробу нельзя.

    Ветка защитная: расчёт скриптовые записи не трогает (переписываются
    значения свойств), но если снимок разошёлся не в записи цели, хвост про
    оставшуюся пробу соврал бы — скрипт-то как раз вернулся. Хвост здесь идёт
    не по типу расхождения, а по метке: её в снимке нет, значит пробы нет.
    """
    env, bridge = _bridge(installed="// пользовательский",
                          foreign_change_on_restore=True)
    with pytest.raises(ScriptBridgeUnsafeStateError) as exc:
        bridge.run_probe("", tmp_path / "out.txt")
    message = str(exc.value)
    assert "изменились чужие скриптовые записи" in message
    assert "Пробы в проекте не осталось" in message
    assert "осталась проба" not in message


def test_restore_reports_all_mismatches_not_only_the_first(tmp_path):
    """Диагноз перечисляет все расхождения: первое скрывало «дело не только в цели».

    Ровно тот сценарий, ради которого сверка и писалась: запись цели не
    вернулась И разошлась чужая. Раньше второе до сообщения не доходило.
    """
    env, bridge = _bridge(installed="// пользовательский",
                          other_scripts=["ЧУЖОЙ"],
                          restore_is_ignored=True,
                          foreign_change_on_restore=True)
    with pytest.raises(ScriptBridgeUnsafeStateError) as exc:
        bridge.run_probe("", tmp_path / "out.txt")
    message = str(exc.value)
    assert "не совпал с прежним" in message
    assert "изменились чужие скриптовые записи" in message


def test_run_probe_says_state_unknown_when_snapshot_cannot_be_taken(tmp_path):
    """Снимок не снялся — «пробы не осталось» утверждать нечем."""
    env, bridge = _bridge(dump_fails_after_install=True)
    with pytest.raises(ScriptBridgeUnsafeStateError) as exc:
        bridge.run_probe('writelnutf8(fid, "x");', tmp_path / "probe.txt")
    message = str(exc.value)
    assert "Состояние проекта неизвестно" in message
    assert "Пробы в проекте не осталось" not in message


def test_run_probe_reports_leftover_when_install_fails_after_applying(tmp_path):
    """Вызов упал ПОСЛЕ применения: «не установлено» было бы догадкой.

    Таймаут COM не отменяет уже сделанного, поэтому о состоянии проекта
    спрашивают свежий снимок, а не код возврата вызова.
    """
    env, bridge = _bridge(probe_install_raises_after_apply=True)
    with pytest.raises(ScriptBridgeUnsafeStateError) as exc:
        bridge.run_probe('writelnutf8(fid, "x");', tmp_path / "probe.txt")
    message = str(exc.value)
    assert "не удалось установить пробу" in message
    assert "осталась проба" in message


def test_run_probe_reports_unsafe_when_target_record_is_not_decodable(tmp_path):
    """Запись цели не разбирается кодеком — отказ, а не ValueError из `chr()`."""
    env, bridge = _bridge(installed="", other_scripts=["ЧУЖОЙ"],
                          current_index=1)
    env.raw_scripts = {1: "`x`#1114112"}
    with pytest.raises(ScriptBridgeUnsafeStateError) as exc:
        bridge.run_probe('writelnutf8(fid, "x");', tmp_path / "probe.txt")
    message = str(exc.value)
    assert "не разбирается" in message
    assert "осталась проба" in message
    assert len(env.set_page_script_calls()) == 1


def test_run_probe_does_not_claim_absence_when_page_script_not_in_dump(tmp_path):
    """Установка упала, а записи этой страницы в выгрузке не видно.

    Метки в снимке нет — и всё же «пробы не осталось» сказать нельзя: скрипт
    этой страницы в выгрузку не попадает, поэтому снимок о ней не
    свидетельствует, а вызов мог примениться до отказа.
    """
    env, bridge = _bridge(probe_install_raises_after_apply=True,
                          page_scripts_not_serialized=True)
    with pytest.raises(ScriptBridgeUnsafeStateError) as exc:
        bridge.run_probe('writelnutf8(fid, "x");', tmp_path / "probe.txt")
    message = str(exc.value)
    assert "Метки в снимке нет, но и об этой странице он молчит" in message
    assert "Пробы в проекте не осталось" not in message


def test_run_probe_refuses_silent_save_project_xml(tmp_path):
    """SaveProjectXML сообщил об успехе, файла нет — отказ, а не FileNotFoundError."""
    env, bridge = _bridge(save_project_xml_writes_nothing=True)
    with pytest.raises(ScriptBridgeError) as exc:
        bridge.run_probe("", tmp_path / "out.txt")
    assert "выгрузка проекта не создана" in str(exc.value)


def test_run_probe_entry_failure_is_a_bridge_error(tmp_path):
    """Сбой `GetCurentPage` — ошибка моста, а не сырой сбой клиента.

    Преамбула стоит до любых изменений в проекте, поэтому сбой здесь означает
    ровно «проба не начата, проект не тронут» — и это утверждение обязано
    дойти до вызывающего дословно. Инвариант «наружу из моста выходят только
    ошибки своей иерархии» (назван в `_dump_records`) на входных путях не
    выполнялся: `ComCallError`/`ValueError`/`OSError` уходили как есть, и
    вызывающий — в том числе MCP-слой — не мог отличить отказ моста от отказа
    среды по типу, а разбирать текст вместо типа не должен.
    """
    env, bridge = _bridge(current_page_raises=True)
    with pytest.raises(ScriptBridgeError) as exc:
        bridge.run_probe("", tmp_path / "out.txt")
    message = str(exc.value)
    assert "Проба не начата, проект не тронут" in message, message
    assert not isinstance(exc.value, ScriptBridgeUnsafeStateError), (
        "сбой среды выдан за небезопасное состояние проекта")
    assert env.set_page_script_calls() == [], "проект тронут вопреки отказу"


def test_run_probe_entry_snapshot_failure_is_a_bridge_error(tmp_path):
    """Сбой первого снимка — та же граница ошибок, что и у `GetCurentPage`."""
    env, bridge = _bridge(dump_fails_before_install=True)
    with pytest.raises(ScriptBridgeError) as exc:
        bridge.run_probe("", tmp_path / "out.txt")
    message = str(exc.value)
    assert "снимок скриптовых записей" in message, message
    assert "Проба не начата, проект не тронут" in message, message
    assert env.set_page_script_calls() == [], "проект тронут вопреки отказу"


def test_run_probe_wraps_result_path_removal_failure(tmp_path, monkeypatch):
    """Сбой удаления прежнего файла результата — тоже ошибка моста.

    Здесь преамбула уже позади, поэтому «проект не тронут» сказать нельзя:
    проба стоит, и уборку делает `finally`. Сообщение обязано это называть —
    иначе вызывающий решит, что проект чист, и не станет проверять скрипт
    страницы. Ровно этот путь и назван третьим в дорожной карте MCP.
    """
    env, bridge = _bridge()
    real_unlink = Path.unlink

    def failing_unlink(self, *args, **kwargs):
        if self.name == "out.txt":
            raise OSError("файл занят другим процессом")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", failing_unlink)
    with pytest.raises(ScriptBridgeError) as exc:
        bridge.run_probe("", tmp_path / "out.txt")
    message = str(exc.value)
    assert "не удалось удалить прежний файл результата" in message, message
    assert "Проба установлена" in message, message
    assert not any("createfile(" in s for s in env.scripts), (
        "проба осталась в проекте после отказа: уборка не сработала")


def test_run_probe_does_not_write_to_a_foreign_page(tmp_path):
    """Молчаливый `SetCurrentPage`: запись отменяется вместо порчи чужой страницы.

    Измерено атакой: если переход молча не состоится, запись уйдёт в **чужую**
    страницу и уничтожит её скрипт, а сообщение обвинит только пробу. Размен
    осознанный: невосстановленная проба с громким отказом лучше уничтоженного
    чужого скрипта с молчанием.
    """
    env, bridge = _bridge(installed="// пользовательский",
                          other_scripts=["ЧУЖОЙ"],
                          page_moves_on_step=True,
                          set_current_page_is_ignored=True)
    with pytest.raises(ScriptBridgeUnsafeStateError) as exc:
        bridge.run_probe("", tmp_path / "out.txt")
    message = str(exc.value)
    assert env.scripts[1] == "ЧУЖОЙ", "скрипт чужой страницы уничтожен"
    assert len(env.set_page_script_calls()) == 1, (
        "после отказа всё равно писали — в чужую страницу")
    assert "не стала целевой" in message
    assert "осталась проба" in message


def test_tolerated_length_change_survives_warnings_as_errors(tmp_path):
    """Терпимое расхождение длин не должно становиться отказом от фильтра.

    Ревью измерило: с `simplefilter("error", UserWarning)` предупреждение,
    выданное внутри `try`, попадало в `except Exception` и превращалось в ложное
    «прежний скрипт страницы не восстановлен» — при том что возврат состоялся.
    `pytest.warns` такой случай не поймает: он подменяет фильтры.
    """
    env, bridge = _bridge(page_moves_on_step=True, pages_added_by_run=1)
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        result = bridge.run_probe('writelnutf8(fid, "x");', tmp_path / "probe.txt")
    assert result.complete
    assert env.scripts[0] != "" and "SCRIPT_BRIDGE_TARGET" not in env.scripts[0], (
        "прежний скрипт не вернулся — предупреждение сорвало возврат")


def test_tolerated_length_change_warns_at_the_caller_frame(tmp_path):
    """Предупреждение указывает на вызывающего, а не на внутренность моста.

    `stacklevel` считает кадры от самого `warnings.warn`, и внутренние помощники
    моста в них входят: с неверным числом предупреждение «указывает» на строку
    `self._restore_script(...)`, где вызывающему делать нечего. Число измерено
    захватом, а не выведено на глаз.
    """
    env, bridge = _bridge(page_moves_on_step=True, pages_added_by_run=1)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        bridge.run_probe('writelnutf8(fid, "x");', tmp_path / "probe.txt")
    ours = [w for w in caught if "число скриптовых записей" in str(w.message)]
    assert len(ours) == 1, f"предупреждений о расхождении длин: {len(ours)}"
    assert Path(ours[0].filename).name == Path(__file__).name, (
        f"предупреждение указывает на {ours[0].filename}:{ours[0].lineno}, "
        "а не на кадр вызывающего — stacklevel посчитан неверно")


def test_run_probe_tolerates_pages_activated_by_run(tmp_path):
    """Расчёт активировал страницу — это поведение среды, а не отказ.

    Наш write ограничен одной страницей, и её мы проверили перед записью; рост
    числа записей создаёт расчёт, и отказывать в нём значило бы делать пробу
    неприменимой на моделях, чьи скрипты создают страницы. Позиционное
    сопоставление при этом невозможно, поэтому сверка идёт по фактам, не
    зависящим от позиций, а о расхождении длин сообщается предупреждением.
    """
    env, bridge = _bridge(installed="// пользовательский",
                          other_scripts=["ЧУЖОЙ"], page_moves_on_step=True,
                          pages_added_by_run=1)
    with pytest.warns(UserWarning, match="число скриптовых записей"):
        result = bridge.run_probe("", tmp_path / "out.txt")
    assert result.complete, "проба не доехала до результата"
    assert env.scripts[0] == "// пользовательский", "возврат не состоялся"
    assert env.scripts[1] == "ЧУЖОЙ", "испорчен скрипт чужой страницы"


def test_run_probe_refuses_when_target_record_is_missing_from_snapshot(tmp_path):
    """Записей стало больше, а прежнего текста записи цели в снимке нет — отказ.

    Второй из двух фактов, на которых держится сверка при расхождении длин:
    вернулся не тот текст, и по позициям это не проверить.
    """
    env, bridge = _bridge(installed="// пользовательский",
                          other_scripts=["ЧУЖОЙ"],
                          restore_writes_other_text=True,
                          pages_added_by_run=1)
    with pytest.raises(ScriptBridgeUnsafeStateError) as exc:
        bridge.run_probe("", tmp_path / "out.txt")
    message = str(exc.value)
    assert "прежнего текста скриптовой записи" in message
    assert "число скриптовых записей изменилось" in message


def test_run_probe_refuses_when_marker_survives_grown_snapshot(tmp_path):
    """Записей стало больше и метка на месте — отказ, проба осталась.

    Первый из двух фактов: метка уникальна, поэтому её наличие в снимке — факт,
    а не вывод, и никакое изменение числа записей его не отменяет.
    """
    env, bridge = _bridge(installed="// пользовательский",
                          other_scripts=["ЧУЖОЙ"],
                          restore_is_ignored=True,
                          pages_added_by_run=1)
    with pytest.raises(ScriptBridgeUnsafeStateError) as exc:
        bridge.run_probe("", tmp_path / "out.txt")
    message = str(exc.value)
    assert "метка пробы осталась в скриптовых записях" in message
    assert "осталась проба" in message


def test_run_probe_reports_frozen_model_time(tmp_path):
    """Неподвижное время — отказ, и он не выдаёт себя за диагноз.

    Синтаксическая ошибка молча останавливает расчёт: `ProjectStart` и
    `ProjectStep` «успешны», а модельное время стоит. Но это **одна из**
    причин, а не признак: см. соседний тест про контрпример.
    """
    env, bridge = _bridge(time_grows=False)
    with pytest.raises(ScriptBridgeError) as exc:
        bridge.run_probe("", tmp_path / "out.txt")
    assert "модельного времени" in str(exc.value)


#: Формулировки, опровергнутые живым прогоном 2026-09-23: неподвижное время
#: **не** доказывает, что скрипт не собрался.
REFUTED_TIME_GROWTH_CLAIMS = ("не скомпилировался", "синтаксис пробы")

#: Что отказ обязан сказать вместо диагноза, которого у моста нет.
REQUIRED_TIME_GROWTH_PHRASE = "причину определить нельзя"


def test_frozen_time_message_does_not_claim_compile_failure(tmp_path):
    """Неподвижное время — не доказательство несобравшегося скрипта.

    Контрпример получен живым прогоном: проба топологии на модели из
    несоединённых блоков дала ровно этот отказ при **синтаксически верном**
    скрипте — блок с неподключённым входом молча останавливает расчёт всей
    модели, и модельное время стоит так же, как при несобирающемся скрипте
    (`docs/superpowers/specs/2026-09-21-topology-probe-design.md`).

    Разница для агента принципиальна: текст «проверьте синтаксис пробы»
    отправляет чинить то, что не сломано, и уводит от настоящей причины —
    структуры модели. Мост обязан назвать признак признаком, а не диагнозом:
    независимого источника причины у него пока нет.
    """
    env, bridge = _bridge(time_grows=False)
    with pytest.raises(ScriptBridgeError) as exc:
        bridge.run_probe("", tmp_path / "out.txt")
    message = str(exc.value)
    for claim in REFUTED_TIME_GROWTH_CLAIMS:
        assert claim not in message, (
            f"отказ утверждает «{claim}» — опровергнуто контрпримером: "
            "модель может не считать и с верным скриптом")
    assert REQUIRED_TIME_GROWTH_PHRASE in message, (
        f"отказ не говорит, что причина не определена: {message!r}")


def test_run_probe_requires_growth_from_existing_time(tmp_path):
    """Положительное, но неподвижное время не считается успехом.

    Сравнение с нулём вместо времени до запуска пропускало бы этот случай:
    проект, стоящий на 5.0 с неработающим скриптом, выглядел бы успешным.
    """
    env, bridge = _bridge(time_grows=False, initial_time=5.0)
    with pytest.raises(ScriptBridgeError) as exc:
        bridge.run_probe("", tmp_path / "out.txt")
    assert "модельного времени" in str(exc.value)


def test_run_probe_reports_incomplete_result(tmp_path):
    env, bridge = _bridge(script_result="")
    with pytest.raises(ScriptBridgeError) as exc:
        bridge.run_probe("", tmp_path / "out.txt")
    assert "маркер" in str(exc.value).lower()


def test_run_probe_reports_missing_result_file(tmp_path):
    env, bridge = _bridge(writes_result=False)
    with pytest.raises(ScriptBridgeError) as exc:
        bridge.run_probe("", tmp_path / "out.txt")
    assert "файл результата" in str(exc.value)


def test_run_probe_removes_previous_result_file(tmp_path):
    """Старый файл не должен быть принят за новый.

    Скрипт здесь файла НЕ пишет, а полный результат на диске лежит заранее:
    если убрать удаление, проба сочтёт старый файл своим и вернёт успех.
    """
    out = tmp_path / "out.txt"
    out.write_text(f"{BEGIN_MARKER}\nстарое\n{END_MARKER}\n", encoding="utf-8")
    env, bridge = _bridge(writes_result=False)
    with pytest.raises(ScriptBridgeError):
        bridge.run_probe("", out)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), 0.0, -1.0])
def test_bridge_rejects_useless_timeout(bad):
    """NaN дал бы бесконечный цикл на COM-потоке, а ноль — ложный диагноз."""
    with pytest.raises(ValueError):
        ScriptBridge(FakeEnv(), project_id=42, time_growth_timeout_s=bad)


def test_unsafe_state_error_is_script_bridge_error():
    """Дочерний, а не независимый: `except ScriptBridgeError` обязан ловить."""
    assert issubclass(ScriptBridgeUnsafeStateError, ScriptBridgeError)
    assert issubclass(ScriptBridgeUnsafeStateError, SimInTechError)


# ─── Жизненный цикл расчёта ──────────────────────────────────────────
#
# Проба обязана вернуть проект в состояние «остановлен» на КАЖДОМ пути, где
# она запускала расчёт. Замерено (automation/lifecycle-probe/03f, 05, 11):
# пока проект инициализирован, среда отвергает добавление блока, причём отказ
# приходит модальным окном, которое внешний клиент снять не может.

def _stop_calls(env):
    return [args for name, args in env.calls if name == "ProjectStop"]


def _index_of(env, name, predicate=lambda args: True):
    """Индекс первого вызова `name`, удовлетворяющего предикату, иначе None."""
    for i, (call_name, args) in enumerate(env.calls):
        if call_name == name and predicate(args):
            return i
    return None


def test_probe_stops_the_calculation_after_success(tmp_path):
    """После успешной пробы расчёт остановлен — и остановка подтверждена."""
    env, bridge = _bridge()
    bridge.run_probe("", tmp_path / "out.txt")

    assert len(_stop_calls(env)) == 1, (
        f"ProjectStop вызван {len(_stop_calls(env))} раз, а проба запускает "
        "расчёт сама и обязана его остановить")
    assert env.state == 0, "проект остался инициализированным"


def test_stop_goes_after_probe_script_and_restore_is_verified(tmp_path):
    """Порядок: проба → остановка → возврат скрипта.

    Проверяется по индексам в журнале вызовов, а не по факту вызова: мутация
    «переставить Stop до установки пробы» иначе не краснеет ничем.
    """
    env, bridge = _bridge()
    bridge.run_probe("", tmp_path / "out.txt")

    probe_i = _index_of(env, "SetPageScript", lambda a: "createfile(" in a[1])
    stop_i = _index_of(env, "ProjectStop")
    restore_i = _index_of(env, "SetPageScript",
                          lambda a: "createfile(" not in a[1])
    assert probe_i is not None and stop_i is not None and restore_i is not None
    assert probe_i < stop_i < restore_i, (
        f"порядок нарушен: проба {probe_i}, остановка {stop_i}, "
        f"возврат {restore_i}")


def test_probe_stops_the_calculation_when_time_does_not_grow(tmp_path):
    """Отказ по неподвижному времени тоже оставляет расчёт инициализированным."""
    env, bridge = _bridge(time_grows=False)
    with pytest.raises(ScriptBridgeError):
        bridge.run_probe("", tmp_path / "out.txt")

    assert len(_stop_calls(env)) == 1, "расчёт не остановлен на пути отказа"
    assert env.state == 0


def test_probe_stops_the_calculation_when_start_raises(tmp_path):
    """ProjectStart упал — состояние неизвестно, и остановка всё равно нужна.

    Проверить нечего: вызов мог примениться и упасть после применения. Stop
    безвреден в любом измеренном состоянии, поэтому пробуется всегда.
    """
    env, bridge = _bridge(start_raises=OSError("COM недоступен"))
    with pytest.raises(OSError):
        bridge.run_probe("", tmp_path / "out.txt")

    assert len(_stop_calls(env)) == 1, (
        "на пути «ProjectStart упал» остановка не предпринята: состояние "
        "расчёта неизвестно, а проект мог остаться инициализированным")


def test_stop_runs_even_when_restore_raises(tmp_path):
    """Сбой возврата скрипта не отменяет остановку — операции изолированы."""
    env, bridge = _bridge(installed="// пользовательский",
                          restore_raises="// пользовательский")
    with pytest.raises(ScriptBridgeUnsafeStateError):
        bridge.run_probe("", tmp_path / "out.txt")

    assert len(_stop_calls(env)) == 1, (
        "возврат скрипта бросил, и остановка не исполнилась: именно в этом "
        "сценарии пользователь не поправит модель и руками")


def test_restore_runs_even_when_stop_fails(tmp_path):
    """Сбой остановки не отменяет возврат скрипта: данные важнее режима."""
    env, bridge = _bridge(installed="// пользовательский",
                          stop_raises=OSError("COM недоступен"))
    with pytest.raises(ScriptBridgeUnsafeStateError):
        bridge.run_probe("", tmp_path / "out.txt")

    restored = [a for a in env.set_page_script_calls()
                if a[1] == "// пользовательский"]
    assert len(restored) == 1, "прежний скрипт страницы не вернулся"


def test_unconfirmed_stop_is_reported_and_not_as_script_loss(tmp_path):
    """Остановка не подтверждена — так и сказано, без выдуманной потери скрипта.

    `ProjectStop` здесь молчаливый (как и бывает у COM-вызова, «применившегося
    без эффекта»), поэтому единственная опора — перечитанный флаг состояния.
    """
    env, bridge = _bridge(installed="// пользовательский", stop_is_ignored=True)
    with pytest.raises(ScriptBridgeUnsafeStateError) as exc:
        bridge.run_probe("", tmp_path / "out.txt")

    text = str(exc.value)
    assert "не остановлен" in text, f"отказ не назвал причину: {text!r}"
    assert "не восстановлен" not in text, (
        f"скрипт вернулся, а текст говорит о его потере: {text!r}")
    assert env.state != 0


def test_unreadable_state_is_reported_as_unknown(tmp_path):
    """Прочитать состояние нельзя — это «неизвестно», а не «остановлено»."""
    env, bridge = _bridge(
        state_read_raises_after_stop=OSError("COM недоступен"))
    with pytest.raises(ScriptBridgeUnsafeStateError) as exc:
        bridge.run_probe("", tmp_path / "out.txt")

    text = str(exc.value)
    assert "неизвестно" in text, f"состояние выдано за известное: {text!r}"
    assert "не восстановлен" not in text


def test_restore_failure_keeps_its_place_when_stop_also_fails(tmp_path):
    """Оба сбоя сразу: первичная причина остаётся, вторичная не теряется.

    Размен, который здесь проверяется, — не косметика. Если поздний сбой
    остановки вытеснит текст о потере скрипта, пользователь узнает про режим
    проекта и НЕ узнает, что скрипт его страницы не вернулся, — то есть
    потеряет данные молча.
    """
    env, bridge = _bridge(installed="// пользовательский",
                          restore_raises="// пользовательский",
                          stop_is_ignored=True)
    with pytest.raises(ScriptBridgeUnsafeStateError) as exc:
        bridge.run_probe("", tmp_path / "out.txt")

    text = str(exc.value)
    assert "не восстановлен" in text, f"первичная причина потеряна: {text!r}"
    assert "не остановлен" in text, f"вторичный сбой не назван: {text!r}"


# ─── Отказ на входе (L1) ─────────────────────────────────────────────
#
# Проба начинается с инициализации проекта, а та обнуляет модельное время
# (измерено: 0.02 -> 0.001). Значит на уже считающем проекте проба не
# «докручивает» расчёт, а уничтожает его — молча и необратимо.

def test_probe_refuses_when_calculation_already_runs(tmp_path):
    """Идёт расчёт — отказ, и проект не тронут ни одним вызовом."""
    env, bridge = _bridge()
    env.state = 7  # расчёт уже идёт: значение из измеренной маски

    with pytest.raises(ScriptBridgeUnsafeStateError) as exc:
        bridge.run_probe("", tmp_path / "out.txt")

    text = str(exc.value)
    assert "не находится в остановленном состоянии" in text, (
        f"отказ не назвал причину: {text!r}")
    assert "не тронут" in text, "отказ не сказал, что проект не изменён"
    assert env.set_page_script_calls() == [], "проект тронут до проверки"
    assert "ProjectStart" not in [name for name, _ in env.calls], (
        "на уничтожение чужого расчёта ушёл ProjectStart: отказ обязан "
        "наступать ДО любых изменений")
    assert env.state == 7, "состояние расчёта изменилось при отказе"


def test_probe_refuses_when_state_unreadable_at_entry(tmp_path):
    """Состояние не прочитать — тоже отказ: «не знаю» неотличимо от «идёт»."""
    env, bridge = _bridge(state_read_raises=OSError("COM недоступен"))

    with pytest.raises(ScriptBridgeUnsafeStateError) as exc:
        bridge.run_probe("", tmp_path / "out.txt")

    text = str(exc.value)
    assert "прочитать не удалось" in text, f"причина не названа: {text!r}"
    assert env.set_page_script_calls() == []
    assert "ProjectStart" not in [name for name, _ in env.calls]


def test_probe_runs_when_project_is_stopped(tmp_path):
    """Обратная сторона: остановленный проект пробе не мешает.

    Без этого теста отказ на входе можно было бы сделать безусловным, и все
    прочие тесты остались бы зелёными.
    """
    env, bridge = _bridge()
    assert env.state == 0
    result = bridge.run_probe("", tmp_path / "out.txt")
    assert result.complete
    assert env.state == 0
