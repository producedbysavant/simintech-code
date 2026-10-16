# 02. Подтверждённые ограничения COM API

Раздел базы знаний (индекс — `README.md`). Здесь только то, что **меняет
способ работы**: каждая строка — либо ловушка молчаливого отказа, либо место,
где COM принципиально бессилен и нужен другой путь (язык, выгрузка, снимок).
Полная карта методов — `docs/reference/com_api_inventory.md`.

## Молчаливые отказы (опаснее явных)

| id | Ограничение | Статус | Почему это ловушка |
|---|---|---|---|
| `setblockprop-ignores-unknown-name` | `SetBlockProp` принимает неизвестное имя параметра молча: значение не меняется, отказа нет | live-verified | Агент считает параметр заданным. Лечение — сверка имён по каталогу **до** записи (раздел 04) |
| `blocks-are-not-renamed-via-com` | `SetBlockProp("Name")` не переименовывает блок — имя остаётся автоматическим (`k_0`, `kx_0`) | live-verified | Следующий `connect` по «заданному» имени не найдёт блок |
| `setpagescript-returns-one-always` | `SetPageScript` возвращает 1 и при синтаксически неверном скрипте; прежний скрипт затирается, пустая строка стирает | live-verified | Возврат нельзя использовать как признак успеха (раздел 06) |
| `script-compile-errors-are-silent-via-com` | Ошибки компиляции скрипта через COM не читаются: текст — только в окне сообщений редактора | live-verified | Единственный различимый признак — нерастущее модельное время |
| `openproject-succeeds-on-missing-path` | `OpenProject` на несуществующем пути «успешен»: `GetOpenedFileName` вернёт тот же путь | live-verified | Работа шла бы с пустым проектом-фантомом. Оба пути (MCP и библиотека) проверяют существование до COM |
| `floating-input-stops-calculation` | Неподключённый вход блока молча останавливает расчёт **всей** модели | live-verified | Первая причина «расчёт не идёт». У порт-блоков правило не действует (раздел 05) |
| `new-project-does-not-calculate` | Проект из `Project.new()` не считает: нет расчётного слоя, время не растёт ничем | live-verified | `ProjectRun`/`ProjectStep` при этом «успешны». Работать — только из шаблона |
| `closepack-invalid-id-crashes-server` | `ClosePack(-1)` роняет `mmain.exe` (Access violation) | live-verified | Библиотека отвергает id ≤ 0 до COM — не подавайте произвольные id в пакетные вызовы |
| `runto-is-not-blocking` | `RunTo` не блокирующий, хотя в карте помечен блокирующим | live-verified | Достижение отметки подтверждается опросом `GetProjectTime` |

## Чего COM не умеет вовсе

| id | Ограничение | Статус | Чем закрывается |
|---|---|---|---|
| `no-block-deletion-in-com-api` | Метода удаления блока нет | code-confirmed | Только язык (`removeprimitiv`) — и только отдельным прогоном у блока (раздел 06) |
| `wires-have-no-ends-via-com` | Концы линий не читаются: нет методов портов связи, `Points` пуст даже после нормализации | live-verified | Выгрузка контейнера `savemodeltofile` (раздел 05) |
| `no-getpagescript-in-com-api` | Чтения скрипта страницы нет (`GetPageScript` отсутствует) | code-confirmed | Механизм `read_page_script`: снимки + уникальная метка (раздел 06) |
| `com-cannot-list-block-properties` | Свойства блока не перечисляются | code-confirmed | Каталог имён, собранный генератором по живому SimInTech (раздел 04) |

## Управление процессом и ресурсами

| id | Факт | Статус | Следствие |
|---|---|---|---|
| `com-createobject-attaches-to-manual-instance` | `CreateObject` подключается к запущенному вручную (GUI) экземпляру; `-Embedding`-экземпляры не переиспользует | live-verified | Нужен гейт владения: инструменты закрывают проекты и завершают процессы — в чужой сессии это разрушительно |
| `com-session-ownership-and-managed-shutdown` | Владение — по снимкам PID до/после connect; `shutdown()` завершает только свой процесс | live-verified | Основа `SessionOwnership` и MCP-гейта (`mcp-ownership-gate-fail-closed`) |
| `job-object-reaps-owned-process-on-owner-death` | Процесс OWNED-сессии в job-объекте с `KILL_ON_JOB_CLOSE`: смерть клиента снимает mmain силами ядра | live-verified | Не остаётся сирот `mmain.exe` после аварий клиента |
| `com-release-does-not-terminate-server` | Отпускание последней COM-ссылки завершает сервер ненадёжно (9 из 22 без проекта; 6 из 6 с закрытым проектом) | live-verified | Управляемое завершение — по точному PID, а не «пусть отпустится» |
| `com-shutdown-on-last-release-is-not-a-mechanism` | `SetShutdownOnLastRelease(1)` — не механизм: поведение остаётся случайным и клиента-смерть не обрабатывает | live-verified | Библиотека флаг не выставляет |
| `findstartport-is-a-signal-resolver` | `findstartport` — не оракул электрической смежности: вернул порт другого контейнера, вендорский экспортёр его не зовёт | contradicted | Не строить на нём «откуда идёт линия»; в MCP он — лишь подтверждение при снятии (раздел 05) |
| `packrun-does-not-advance-in-embedding` | `PackStart`+`PackRun` в COM-инстансе: плато после первого синхрошага; `WaitForTimePack` ожидания не завершает | live-verified | Продвижение пакета — только `PackStep` (MCP: `pack_step`) |
| `projmacros-does-not-run-macro-and-keeps-process-alive` | `mmain.exe /projmacros` макрос не исполняет и процесс оставляет живым | live-verified | Рабочие формы запуска макроса — `macros`, `/macros`, `mstarter macros` (`mstarter-macros-runs-macro-in-a-new-instance`) |

## Как пользоваться разделом

Перед написанием кода, трогающего COM, — прочитать эту таблицу целиком: почти
каждая строка здесь однажды стоила отладки. Если факт отсутствует — значит,
он не проверялся: так и считайте (раздел 10).
