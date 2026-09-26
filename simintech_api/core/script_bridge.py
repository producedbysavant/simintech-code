"""Скриптовый мост: выполнить код встроенного языка внутри проекта и забрать результат.

Зачем. В COM-интерфейсе нет ни удаления блока, ни чтения концов линий, а во
встроенном языке всё это есть. Мост доставляет скрипт в проект и забирает то,
что скрипт записал в файл.

Контракт измерен 2026-09-21 на SimInTech64 (см.
`docs/superpowers/specs/2026-09-21-script-bridge-design.md`):

* `SetPageScript` возвращает `1` всегда — и при синтаксически неверном скрипте
  тоже, поэтому код возврата как признак успеха бесполезен;
* `SetPageScript` пишет в **текущую** страницу и **перезаписывает** её прежний
  скрипт, поэтому прежний скрипт надо вернуть именно в ту страницу, которую
  изменили (её COM ID сообщает `GetCurentPage`);
* ошибка скрипта наружу не сообщается: синтаксическая молча останавливает
  расчёт (`ProjectStart`/`ProjectStep` успешны, модельное время стоит на нуле),
  ошибка времени выполнения молча обрывает остаток скрипта.

Отсюда три обязательные проверки, и ни одну нельзя опустить: маркер завершения
в файле результата, рост модельного времени и возврат прежнего скрипта.
"""

from __future__ import annotations

import math
import tempfile
import time
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Tuple

from ..catalog import decode_xprt
from ..exceptions import ScriptBridgeError, ScriptBridgeUnsafeStateError
from ..script_probe import (
    ProbeResult,
    TARGET_TOKEN_PREFIX,
    build_probe_script,
    decode_xprt_value,
    find_changed_script_record,
    leftover_of,
    new_target_token,
    parse_probe_result,
    parse_xprt_script_records,
    token_present_in,
)

if TYPE_CHECKING:
    from .com_client import COMClient


class ScriptBridge:
    """Выполнить скрипт в проекте и получить результат файлом.

    Принимает пару «клиент + идентификатор проекта», как `Simulation`: у обоих
    объекты адресуются парой, а не ссылкой на `Project`, и это освобождает мост
    от владения проектом — он не открывает и не закрывает его.
    """

    #: Сколько ждать роста модельного времени, прежде чем признать, что расчёт
    #: не пошёл. Шаг на модели из демо занимает доли секунды; запас нужен на
    #: медленные и большие модели. Параметр конструктора, а не только
    #: константа: иначе тест на замороженное время ждал бы заводскую минуту.
    TIME_GROWTH_TIMEOUT_SECONDS = 60.0

    def __init__(self, client: "COMClient", project_id: int, *,
                 time_growth_timeout_s: float = TIME_GROWTH_TIMEOUT_SECONDS
                 ) -> None:
        # Таймаут проверяется сразу: нечисловое или неположительное значение
        # превратило бы ожидание либо в бесконечный цикл на единственном
        # COM-потоке (сервер после этого годен только до перезапуска
        # mmain.exe), либо в ложный диагноз «скрипт не скомпилировался».
        if not math.isfinite(time_growth_timeout_s) or time_growth_timeout_s <= 0:
            raise ValueError(
                "таймаут роста модельного времени должен быть конечным и "
                f"положительным, получено {time_growth_timeout_s!r}")
        self._client = client
        self._project_id = project_id
        self._time_growth_timeout_s = time_growth_timeout_s

    def _dump_records(self) -> List[str]:
        """Снять скриптовые записи проекта выгрузкой `.xprt`.

        Другого способа увидеть скрипты страниц у COM нет: идентификаторов
        страниц в выгрузке не бывает, а `SetPageScript` пишет в текущую
        страницу, ничего не сообщая о прежнем содержимом.

        Кодировку разбирает `decode_xprt` — **до** разбора разметки и по
        байтам: `read_text` с `errors="replace"` подменил бы испорченный байт
        на U+FFFD и превратил порчу файла в тихую правку скрипта.

        Молчаливый `SaveProjectXML` (сообщил об успехе, файла нет) — отказ, а
        не `FileNotFoundError` из недр: наружу из моста обязаны выходить только
        ошибки своей иерархии.
        """
        with tempfile.TemporaryDirectory(prefix="simintech-bridge-") as tmp:
            path = Path(tmp) / "page.xprt"
            self._client.call("SaveProjectXML", self._project_id, str(path))
            try:
                data = path.read_bytes()
            except OSError as exc:
                raise ScriptBridgeError(
                    f"выгрузка проекта не создана: SaveProjectXML сообщил об "
                    f"успехе, но файла {path} нет ({exc}). Состояние скриптов "
                    "неизвестно, а по коду возврата этой ошибки не увидеть."
                ) from exc
            text = decode_xprt(data)
        return parse_xprt_script_records(text)

    def _records_or_none(self) -> Optional[List[str]]:
        """Свежий снимок записей для диагностики отказа: `None` — «неизвестно».

        `None` здесь не «пусто»: снимок не снялся, и утверждать что-либо о
        состоянии проекта нечем. Отказ обязан различать эти вещи — иначе он
        выдаёт догадку за факт.
        """
        try:
            return self._dump_records()
        except Exception:  # noqa: BLE001
            return None

    def _unsafe(self, reason: str, records: Optional[List[str]] = None,
                token: Optional[str] = None,
                probe_error: Optional[BaseException] = None,
                snapshot_proves_absence: bool = True
                ) -> ScriptBridgeUnsafeStateError:
        """Отказ с честным описанием состояния проекта.

        Хвост строится **по метке**, а не по догадке: метка этой пробы
        уникальна, поэтому её наличие в снимке — факт, а не вывод. Догадка здесь
        стоит дорого: пользователь читает сообщение, когда решает, восстанавливать
        ли скрипт страницы из копии.

        `snapshot_proves_absence` — про отсутствие метки, и только про него:
        снимок свидетельствует об отсутствии пробы лишь тогда, когда в нём видна
        сама запись этой страницы. Там, где запись цели в снимке не опознана
        (установка или снимок упали, ни одна запись не изменилась), отсутствие
        метки означает «не видно», а не «нет»: скрипт страницы может в выгрузку
        не попадать вовсе, и тогда молчание снимка ничего не доказывает.
        """
        if records is None or token is None:
            tail = ("Состояние проекта неизвестно: снимок скриптовых записей "
                    "снять не удалось, поэтому осталась ли в текущей странице "
                    "проба — сказать нечем. Проверьте скрипт этой страницы по "
                    "копии проекта.")
        elif token_present_in(records, token):
            tail = ("В текущей странице осталась проба — вернуть прежний скрипт "
                    "нечем; если у вас есть копия проекта, скрипт этой страницы "
                    "надо взять оттуда.")
        elif snapshot_proves_absence:
            tail = "Пробы в проекте не осталось."
        else:
            tail = ("Метки в снимке нет, но и об этой странице он молчит: "
                    "записи её скрипта в выгрузке не видно, поэтому считать "
                    "пробу отсутствующей по нему нельзя — проверьте скрипт "
                    "этой страницы вручную.")
        message = f"{reason} {tail}"
        if probe_error is not None:
            message = f"проба уже завершилась отказом ({probe_error}), и " + message
        return ScriptBridgeUnsafeStateError(message)

    def install_script(self, script: str) -> None:
        """Поставить скрипт страницы. Прежний при этом теряется."""
        self._client.call("SetPageScript", self._project_id, script, 1)

    def run_probe(self, body: str, result_path: Path) -> ProbeResult:
        """Выполнить `body` в проекте и вернуть разобранный результат.

        Порядок продиктован замерами (спецификация 2026-09-22):

        1. запомнить **COM ID текущей страницы** и снять снимок скриптовых
           записей проекта;
        2. сгенерировать метку цели и убедиться, что её нет в снимке;
        3. поставить пробу с меткой; снять второй снимок и найти запись,
           которую изменила установка, — только она и есть цель;
        4. удалить прежний файл результата и запустить расчёт;
        5. вернуть прежний скрипт **в ту страницу, которую изменили**, и
           сверить снимки;
        6. если цель не установлена — не угадывать: `ScriptBridgeUnsafeStateError`
           прямо говорит, что в проекте остался пробный скрипт.
        """
        self._refuse_if_calculating()
        # Преамбула стоит до любых изменений в проекте, и это её главное
        # свойство: сбой здесь означает «проба не начата, проект не тронут» —
        # утверждение, которое обязано дойти до вызывающего дословно.
        #
        # Инвариант моста («наружу выходят только ошибки своей иерархии»)
        # назывался в `_dump_records`, но здесь не выполнялся: `GetCurentPage`
        # и первый снимок выпускали `ComCallError`, `ValueError` и `OSError`
        # как есть. Вызывающему — в том числе MCP-слою — это не давало отличить
        # отказ моста от отказа среды по типу, а разбирать текст вместо типа он
        # не должен. `_refuse_if_calculating` выше этой беды не знал: он и
        # раньше поднимал `ScriptBridgeUnsafeStateError`.
        try:
            target_page_id = int(self._client.call("GetCurentPage",
                                                   self._project_id))
        except ScriptBridgeError:
            raise
        except BaseException as exc:                              # noqa: BLE001
            raise ScriptBridgeError(
                f"не удалось определить текущую страницу проекта ({exc}). "
                "Проба не начата, проект не тронут.") from exc
        try:
            before = self._dump_records()
        except ScriptBridgeError:
            raise
        except BaseException as exc:                              # noqa: BLE001
            raise ScriptBridgeError(
                "не удалось снять снимок скриптовых записей проекта "
                f"({exc}). Проба не начата, проект не тронут.") from exc
        token = new_target_token()
        if token_present_in(before, TARGET_TOKEN_PREFIX):
            raise ScriptBridgeUnsafeStateError(
                "в скриптовых записях проекта уже есть метка моста: значит, в "
                "проекте остался пробный скрипт предыдущего запуска (возврат "
                "тогда не прошёл либо его не было вовсе). Проба не начата, "
                "проект не тронут. Номеров страниц в выгрузке нет, поэтому "
                "какой именно странице принадлежит метка — по ней не "
                "определить: проверьте скрипты страниц проекта.")
        script = build_probe_script(body, str(result_path), token=token)

        target = None
        original = None
        probe_error = None
        #: Был ли вызван `ProjectStart` — от этого зависит, обязана ли проба
        #: останавливать расчёт (и обязана, даже если вызов бросил).
        calculation_started = False
        try:
            try:
                self.install_script(script)
            except BaseException as exc:
                # Вызов мог примениться и упасть уже после применения (таймаут
                # на отпущенном COM-вызове), поэтому «не установлено» здесь —
                # догадка: состояние берём из свежего снимка.
                raise self._unsafe(
                    f"не удалось установить пробу: {exc}.",
                    self._records_or_none(), token,
                    snapshot_proves_absence=False) from exc
            try:
                after = self._dump_records()
            except BaseException as exc:
                raise self._unsafe(
                    "не удалось снять снимок скриптовых записей после "
                    f"установки пробы: {exc}.",
                    self._records_or_none(), token,
                    snapshot_proves_absence=False) from exc
            try:
                target = find_changed_script_record(before, after, token)
            except ScriptBridgeUnsafeStateError as exc:
                # Отказ приходит из чистой функции, которая о состоянии проекта
                # знать не может, а знать его обязан: проба к этому моменту уже
                # стоит в текущей странице, и молчание об этом оставило бы
                # пользователя с испорченной страницей и без предупреждения.
                raise self._unsafe(f"{exc}", after, token,
                                   snapshot_proves_absence=False) from exc
            raw_original = before[target]
            if leftover_of(raw_original):
                raise self._unsafe(
                    f"скриптовая запись {target} содержит нераспознанный текст "
                    "выгрузки: восстановление небезопасно — кодек покрывает не "
                    "весь текст, и на место вернулся бы усечённый скрипт.",
                    after, token)
            try:
                original = decode_xprt_value(raw_original)
            except ScriptBridgeError as exc:
                raise self._unsafe(
                    f"скриптовая запись {target} не разбирается: {exc}.",
                    after, token) from exc
            try:
                result_path.unlink(missing_ok=True)
            except OSError as exc:
                # Тот же инвариант: сбой файловой системы не должен выглядеть
                # сбоем среды. Проба к этому моменту уже стоит, поэтому
                # сообщение называет состояние прямо — уборку делает `finally`.
                raise ScriptBridgeError(
                    f"не удалось удалить прежний файл результата "
                    f"{result_path} ({exc}). Проба установлена, расчёт ещё не "
                    "запущен; остановка и возврат скрипта выполняются, но "
                    "старый файл результата надо удалить вручную.") from exc
            # С этого момента расчёт запущен нами, и вернуть проект в
            # «остановлен» обязана проба — на любом пути, включая тот, где сам
            # ProjectStart бросил (тогда состояние неизвестно, но остановка
            # безвредна в любом измеренном состоянии).
            calculation_started = True
            self._start_and_wait()
            result = self._read_result(result_path)
        except BaseException as exc:
            probe_error = exc
            raise
        finally:
            # Остановка идёт ПЕРВОЙ и в своей изоляции: при state=0 не запрещена
            # ни одна измеренная операция, поэтому возврат скрипта исполняется
            # на заведомо разрешённом состоянии. Порядок обязателен и в обратную
            # сторону: сбой возврата не отменяет остановку, сбой остановки не
            # отменяет возврат — иначе проект остаётся инициализированным ровно
            # там, где пользователь не поправит его и руками.
            stop_problem = self._stop_calculation(calculation_started)
            restore_problem = None
            if target is not None and original is not None:
                try:
                    self._restore_script(before, target, original,
                                         target_page_id, token, probe_error)
                except ScriptBridgeUnsafeStateError as exc:
                    restore_problem = exc
            if restore_problem is not None:
                if stop_problem is not None:
                    # Уровни не смешиваются: первичная причина (потеря скрипта)
                    # остаётся началом текста, сбой режима дописывается —
                    # и наоборот, сбой остановки не выдаётся за потерю скрипта.
                    restore_problem = ScriptBridgeUnsafeStateError(
                        f"{restore_problem} Дополнительно: {stop_problem}")
                raise restore_problem
            if stop_problem is not None:
                raise self._unsafe(stop_problem, self._records_or_none(), token,
                                   probe_error=probe_error)
        return result

    def _refuse_if_calculating(self) -> None:
        """Отказать, если проект не остановлен: проба уничтожит расчёт.

        `ProjectStart` — не «пуск», а **инициализация** (вендорский
        `helpstring`), и модельное время при ней сбрасывается: измерено
        `0.02 → 0.001` на считающем проекте. Поэтому проба на уже запущенном
        расчёте не «докручивает» его, а молча убивает — вместе со всем, что
        вызывающий успел посчитать.

        Отказ, а не предупреждение, выбран сознательно: данные терялись бы
        молча для того, кто предупреждений не читает, а исход необратим.
        Обход прост и назван в тексте: остановить расчёт (`ProjectStop`) и
        повторить.

        Состояние читается **до** любых изменений в проекте, поэтому отказ
        действительно ничего не трогает. Нечитаемое состояние — тоже отказ:
        «не знаю» здесь неотличимо от «идёт расчёт», а цена ошибки —
        уничтоженный расчёт вызывающего.
        """
        try:
            state = int(self._client.call("GetProjectStateFlag",
                                          self._project_id))
        except BaseException as exc:                                  # noqa: BLE001
            raise ScriptBridgeUnsafeStateError(
                f"состояние расчёта прочитать не удалось ({exc}), а проба "
                "начинается с инициализации проекта и обнулила бы модельное "
                "время. Остановите расчёт явно и повторите: без этого отличить "
                "«расчёт идёт» от «проект остановлен» нечем."
            ) from exc
        if state != 0:
            raise ScriptBridgeUnsafeStateError(
                f"проект не находится в остановленном состоянии (состояние "
                f"{state}, тогда как остановленному соответствует 0; 1 — "
                "инициализирован, 3 — идёт расчёт, 7 — пауза), и проба его "
                "уничтожила бы: она начинается с инициализации проекта, а та "
                "обнуляет модельное время. Проект не тронут — остановите "
                "расчёт (ProjectStop) и повторите.")

    def _stop_calculation(self, attempted: bool) -> Optional[str]:
        """Остановить расчёт и **подтвердить** остановку. Никогда не бросает.

        Зачем. Пока проект инициализирован (`GetProjectStateFlag != 0`), среда
        отвергает добавление блока, и отказ приходит модальным окном, которое
        внешний COM-клиент снять не может: вызов стоит, пока окно не закроет
        человек (измерено 2026-09-22). Проба запускает расчёт сама, поэтому
        обязана и остановить — иначе следующая же правка модели у вызывающего
        повиснет.

        Почему не бросает. Сбой поздней уборки не смеет подменить первичную
        причину и не смеет отменить возврат скрипта: и то, и другое — потеря
        данных. Проблема возвращается текстом, а решение о ней принимает
        вызывающий (`run_probe`), который один знает про первичную ошибку.

        Почему перечитывается флаг. `ProjectStop` сообщает об успехе и тогда,
        когда ничего не изменил: код возврата доказательством выполнения не
        является (как и у `SetPageScript`). Подтверждение — только чтение
        состояния; если прочитать его не удалось, честный ответ — «неизвестно»,
        а не «остановлено».
        """
        if not attempted:
            return None
        try:
            self._client.call("ProjectStop", self._project_id)
        except BaseException as exc:                                  # noqa: BLE001
            return (f"остановить расчёт не удалось: {exc}. Проект мог остаться "
                    "инициализированным, а в этом состоянии добавление блока "
                    "отвергается — на головной машине модальным окном.")
        try:
            state = int(self._client.call("GetProjectStateFlag",
                                          self._project_id))
        except BaseException as exc:                                  # noqa: BLE001
            return ("остановлен ли расчёт — неизвестно: состояние проекта "
                    f"прочитать не удалось ({exc}).")
        if state != 0:
            return (f"расчёт не остановлен: состояние проекта {state}, тогда "
                    "как остановленному соответствует 0. Пока проект "
                    "инициализирован, добавление блока отвергается.")
        return None

    def _read_result(self, result_path: Path) -> ProbeResult:
        """Прочитать файл результата и проверить пару маркеров."""
        if not result_path.exists():
            raise ScriptBridgeError(
                "скрипт не создал файл результата: расчёт шёл, но скрипт "
                f"оборвался до записи в {result_path}. Ошибка времени "
                "выполнения прерывает скрипт молча, поэтому причину придётся "
                "искать по телу пробы.")
        try:
            text = result_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ScriptBridgeError(
                f"файл результата не читается как UTF-8: {exc}. Скрипт пишет "
                "через writelnutf8, поэтому испорченный файл означает потерю "
                "данных — подставлять замены вместо символов нельзя.") from exc
        result = parse_probe_result(text)
        if not result.complete:
            raise ScriptBridgeError(
                "в результате нет ровно одной пары маркеров начала и конца: "
                "скрипт оборвался или записал маркер сам. Данные неполны или "
                "неоднозначны — как результат их использовать нельзя.")
        return result

    def _restore_script(self, before: List[str], target: int, original: str,
                        target_page_id: int, token: str,
                        probe_error: Optional[BaseException]) -> None:
        """Вернуть прежний скрипт в **ту самую** страницу и сверить снимки.

        `SetPageScript` пишет в текущую страницу, поэтому целевая страница
        сначала выставляется, а потом **перечитывается**: её могла увести и
        сама модель (`gotopage` существует). Если после установки текущая
        страница не стала целевой, запись **не выполняется вовсе** — молчаливый
        отказ `SetCurrentPage` иначе увёл бы прежний скрипт в чужую страницу и
        уничтожил бы её скрипт. Размен осознанный: невосстановленная проба с
        громким отказом лучше чужого скрипта, уничтоженного молча.

        Сверка идёт по снимку, а не по собственному чтению: прежняя проверка
        сравнивала главную страницу саму с собой и потому не видела потери.
        """
        problem = None
        warning: Optional[str] = None
        verify: Optional[List[str]] = None
        try:
            self._client.call("SetCurrentPage", self._project_id, target_page_id)
            current = int(self._client.call("GetCurentPage", self._project_id))
            if current != target_page_id:
                problem = (f"текущая страница не стала целевой ({current} вместо "
                           f"{target_page_id}), и запись отменена: писать в неё "
                           "значило бы уничтожить скрипт чужой страницы")
            else:
                self.install_script(original)
                verify = self._dump_records()
                mismatch, warning = self._describe_mismatch(before, verify, target,
                                                            token)
                if mismatch:
                    problem = "; ".join(mismatch)
        except Exception as exc:  # noqa: BLE001
            problem = f"вызов не прошёл: {exc}"
        if problem is None:
            self._warn_after_the_fact(warning)
            return
        # Хвост строится по факту — по метке в снимке, а не по типу расхождения:
        # расхождение длин и чужие записи говорят, что снимки разошлись, но не
        # говорят, осталась ли проба. Знает это только метка, и если снимок
        # снять не удалось (verify is None), честный ответ — «неизвестно».
        records = verify if verify is not None else self._records_or_none()
        raise self._unsafe(f"прежний скрипт страницы не восстановлен: {problem}.",
                           records, token, probe_error=probe_error
                           ) from probe_error

    def _warn_after_the_fact(self, warning: Optional[str]) -> None:
        """Выдать предупреждение о терпимом расхождении — **после** сверки.

        Зовётся, только когда отказа нет. Внутри `try` этого делать нельзя: при
        фильтре `error` на `UserWarning` (обычная практика в CI, `-W error`)
        исключение из `warnings.warn` попало бы в `except Exception` и стало бы
        ложным «прежний скрипт страницы не восстановлен» — при том что возврат
        состоялся, и текст утверждал бы несуществующее.

        Исключение самого предупреждения (тот же фильтр `error`) возврат не
        отменяет: починка уже сделана, а политика вызывающего в отношении
        предупреждений не может превращать её в несделанную.
        """
        if warning is None:
            return
        try:
            # stacklevel=4 — кадр вызывающего `run_probe`: warn → этот помощник
            # → `_restore_script` → `run_probe` → вызывающий. Проверено
            # захватом (`catch_warnings(record=True)`), а не на глаз.
            warnings.warn(warning, stacklevel=4)
        except Warning:  # noqa: BLE001
            pass

    def _describe_mismatch(self, before: List[str], verify: List[str],
                           target: int, token: str
                           ) -> Tuple[List[str], Optional[str]]:
        """**Все** расхождения снимка после возврата со снимком до установки.

        Сравниваются **скриптовые записи**, а не выгрузки: между установкой и
        возвратом шёл расчёт, и он переписывает вычисленные значения свойств
        (измерено: 21 запись из 67, 5.8 млн символов), а скрипты не трогает.

        Возвращается пара «расхождения + текст предупреждения»: расхождения —
        список, а не первое найденное, потому что диагноз «дело не только в
        записи цели» нужен ровно в том сценарии, ради которого сверка и
        делается, а первый выход его скрывал. Предупреждение **не выдаётся
        здесь**: его выдаёт вызывающий и только тогда, когда отказа не было.

        Изменение **числа** записей отказом само по себе не является. Наш
        собственный write ограничен одной страницей, и её мы проверили перед
        записью; рост числа записей — поведение среды (расчёт активирует
        страницы, и их скрипты создают новые), а не наше действие, и отказывать
        в нём значило бы делать пробу неприменимой на моделях, чьи скрипты
        создают страницы. Позиционное сопоставление при этом невозможно, поэтому
        сверка переходит на факты, **не зависящие от позиций** (см.
        `_describe_length_change`).
        """
        if len(verify) != len(before):
            return self._describe_length_change(before, verify, target, token)
        problems = []
        if verify[target] != before[target]:
            problems.append(f"скрипт записи {target} не совпал с прежним")
        others = [i for i in range(len(before))
                  if i != target and before[i] != verify[i]]
        if others:
            problems.append(f"изменились чужие скриптовые записи: {others}")
        return problems, None

    def _describe_length_change(self, before: List[str], verify: List[str],
                                target: int, token: str
                                ) -> Tuple[List[str], Optional[str]]:
        """Сверка при изменившемся числе записей — по фактам, не по позициям.

        Два факта, и оба от позиций не зависят:

        1. метки пробы нет ни в одной записи — значит пробы в проекте не
           осталось (метка уникальна, это факт, а не вывод);
        2. прежний текст записи цели есть в снимке (`before[target] in verify`) —
           кодек обратим, и при возврате запись восстанавливается байт в байт
           (замер 7).

        Оба на месте — сверка пройдена, но о расхождении длин сообщается
        предупреждением: молча пропустить его нельзя, это признак того, что
        проект живёт своей жизнью и в нём появились страницы, которых при
        установке пробы не было. Текст предупреждения **возвращается**, а не
        выдаётся здесь: выдаёт его `_warn_after_the_fact`, уже после того, как
        стало известно, что отказа нет. Иначе — отказ: неизвестно, что именно
        вернулось в запись цели.
        """
        if token_present_in(verify, token):
            return [f"число скриптовых записей изменилось: {len(before)} -> "
                    f"{len(verify)}",
                    "метка пробы осталась в скриптовых записях: прежний скрипт "
                    "страницы не вернулся"], None
        if before[target] not in verify:
            return [f"число скриптовых записей изменилось: {len(before)} -> "
                    f"{len(verify)}",
                    f"прежнего текста скриптовой записи {target} в снимке нет: "
                    "сопоставить по позициям нельзя, а по тексту он не найден"], None
        return [], (f"число скриптовых записей изменилось во время расчёта "
                    f"({len(before)} -> {len(verify)}): сопоставление по позициям "
                    "невозможно, сверка выполнена по наличию текста записи цели и "
                    "отсутствию метки пробы")

    def _start_and_wait(self) -> None:
        """Запустить расчёт и дождаться, пока модельное время сдвинется.

        Неподвижное время — **признак, а не диагноз.** Так выглядят по
        меньшей мере два разных состояния, и различить их мост не умеет:

        * скрипт не собрался — `ProjectStart` и `ProjectStep` сообщают об
          успехе, среда об ошибке молчит;
        * модель структурно не считает — блок с неподключённым входом молча
          останавливает расчёт всей модели, модельное время стоит.

        Второе измерено 2026-09-23 живым прогоном пробы топологии: скрипт был
        синтаксически верен, а время не росло
        (`docs/superpowers/specs/2026-09-21-topology-probe-design.md`). Поэтому
        отказ называет **состояние**, а не причину: независимого признака
        причины у моста нет, а выбирать между версиями по одному и тому же
        симптому — значит выдать догадку за измерение.
        """
        self._client.call("ProjectStart", self._project_id)
        initial_time = float(self._client.call("GetProjectTime", self._project_id))
        deadline = time.monotonic() + self._time_growth_timeout_s
        while True:
            self._client.call("ProjectStep", self._project_id)
            current_time = float(self._client.call("GetProjectTime", self._project_id))
            if current_time > initial_time:
                return
            if time.monotonic() >= deadline:
                raise ScriptBridgeError(
                    "расчёт не подтвердил рост модельного времени за "
                    f"{self._time_growth_timeout_s:g} с. По этому признаку "
                    "причину определить нельзя: так выглядят и скрипт, "
                    "который не собрался (среда об этом молчит), и модель, "
                    "которая структурно не считает — например, блок с "
                    "неподключённым входом останавливает расчёт всей модели. "
                    "Проверьте и скрипт, и соединения модели.")
            time.sleep(0.05)
