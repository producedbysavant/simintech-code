# 05. Топология, порты, линии и ветвление

Раздел базы знаний (индекс — `README.md`). О связях модели: как они читаются,
адресуются и что о них нельзя утверждать. Модель колонок/каналов — в разделе 07
(`simintech-mcp`), канон укладки — `simintech_api/layout/canon.py`.

## Как читается связность

- **COM концов линий не отдаёт** (`wires-have-no-ends-via-com`): доступны
  количество и идентификаторы. Пара «откуда → куда» восстанавливается только
  выгрузкой контейнера (`savemodeltofile`): записи `type = "wire"`, адреса
  `src = "block:out:N"` / `dst = "block:in:N"`, ветвь — `src = "wire:K"`
  (`savemodeltofile-describes-current-container`).
- **Скриптовая проба топологии** (`read_topology`) читает контейнер тремя
  фазами (object → port → conn) и сверяется с вендорским эталоном; линии из
  объектов отсеивает критерий допустимости
  (`ELIGIBLE_OBJECT_TYPES = 100, 102, 104, 106`), а `conn` описывает концы
  линии **попарно** (`conn-describes-wire-ends-pairwise`: развилка даёт
  звезду по вендорскому правилу кратности `min(1, …)` для входного порта).

| id | Факт | Статус |
|---|---|---|
| `savemodeltofile-describes-current-container` | Выгрузка описывает **текущий** контейнер: объекты, провода, свойство `script` страницы | live-verified |
| `savemodeltofile-understands-absolute-path` | Абсолютный путь выгрузки понимается; относительный разрешается от рабочего каталога приложения | live-verified |
| `conn-describes-wire-ends-pairwise` | `conn` — попарные рёбра (для k концов — C(k,2)), а не физические провода | live-verified |
| `port-index-identity-holds-for-blocks-only` | `getportindex(getblockportid(obj, i)) = i` — для блоков; на линиях не держится | live-verified |

## Порты и координаты

| id | Факт | Статус |
|---|---|---|
| `block-ports-at-center-row` | Порты стоят на высоте центра: выход `(cx+16, cy)`, вход `(cx−16, cy)`; печать точки — «x+yi» | live-verified |
| `block-points-first-is-center` | `Points` — не контур: первая точка = центр блока, вторая = выходной порт; min/max полилинии габаритом не является | live-verified |
| `block-set-center-is-exact` | `set_center`/`set_position` ставят координаты точно, без снапа; `create_block(x, y)` — левый верхний угол | live-verified |
| `constlabel-objects-are-anchors` | Подписи (`constLabel`) — не блоки: `Points` — якорь, `size` — карточка 60×40, портов нет | live-verified |
| `object-type-constants-are-named` | Типы объектов: `otBlock`=100 … `otImageFrameBlock`=114 (имена и числа — вендорские) | vendor-confirmed |

Потребитель габарита строит его как центр ± `size/2` (MCP: `geometry.rect_of`);
расстановка кладёт центры на сетку 8 px (раздел 07).

## Ветвление

| id | Факт | Статус |
|---|---|---|
| `branch-point-is-not-a-separate-object` | Точка ветвления — не отдельный объект: её роль играет линия-родитель | vendor-confirmed |
| `getparentwire-functions-describe-branching` | `getparentwireid` — родительская линия, `getparentwirenodeindex` — номер точки (с 1) | vendor-confirmed |
| `getparentwire-functions-return-zero-without-branching` | Без ветвления обе функции возвращают 0 («ветвления нет», а не «неизвестно») | vendor-confirmed |
| `wire-node-number-is-point-nmb-plus-one` | Узел = `point_nmb` + 1 (нумерация createwire с нуля, чтения — с единицы); в выгрузке `wire:K`, K = узел − 1 | live-verified |
| `branch-k-outside-points-silently-collapses` | K вне существующих точек среда **молча** сворачивает к первой — диапазон проверяется до вызова | code-confirmed |
| `empty-branch-pair-0-0i` | Ветвь рождает пару — линию без приёмника (`0+0i`): невидима, в счёте узла не участвует | live-verified |
| `node-limit-three-lines` | Правило оформления: в точку не больше трёх линий («плюс» из четырёх лучей — это 3 линии, норма) | live-verified |
| `traceallports-second-arg-crosses-container` | `traceallports(port, 1)` проходит границу контейнера; с `0` — нет | live-verified |
| `traceallports-second-arg-defaults-true` | Default второго аргумента — включён (`aWithCoPorts:=True`); одноаргументную форму живым прогоном не звали | vendor-confirmed |
| `traceallports-order-is-not-a-contract` | Порядок в ответе `traceallports` — не контракт для сложных топологий | vendor-confirmed |
| `tracestartportwires-walks-service-blocks` | `tracestartportwires` учитывает служебные блоки (память, порты субмоделей, шины) | vendor-confirmed |
| `container-traversal-functions-are-used-by-vendor` | Обход контейнеров вендором: `getobj` (с 1), `getobjcount`, `getsubmodelid`, `getownercontainer`, `submodelbypageid`, `findstartport`, `getportblockid`, `getfullname` | live-verified |

**`findstartport` — не оракул:** `findstartport-is-a-signal-resolver`
(contradicted) — на спорных портах он вернул порт другого контейнера, и
вендорский экспортёр его не вызывает вовсе. В MCP он используется только как
подтверждение «линия идёт из этого выхода» при снятии, а не как источник истины.

## Изменение связей и последствия

| id | Факт | Статус |
|---|---|---|
| `wire-removal-keeps-calculation-start` | Удаление **линии** (removeprimitiv/removeobject по id) старт расчёта не роняет; id переиспользуется; снятие без воссоздания оставляет висячий вход — расчёт стоит | live-verified |
| `removeprimitiv-breaks-calculation-start` | Удаление **блока** — роняет следующий `ProjectStart` (AV в `mbtylib.dll`) | live-verified |
| `topology-goes-blind-after-removals` | После серии `removeprimitiv` по id `getportwireid` может отдавать 0 при живой линии; снимается save + переоткрытием | live-verified |

Следствия для инструментов (MCP): блок удаляется только отдельным прогоном
(`remove_block`); снятие линии проверяет концы и подтверждается перечислением;
слепота топологии лечится `reload_project`.

## Субмодели

| id | Факт | Статус |
|---|---|---|
| `submodel-ports-are-created-on-its-page` | Внешние порты субмодели создаются на её странице (`getsubmodelid` → `createblock(contid, "Порт входа"/"Порт выхода")`) | live-verified |
| `initsubmodelports-makes-ports-immediately-visible` | `initsubmodelports(sub)` делает порты видимыми сразу в `initialization` (без него `getblockportcount` = 0) | live-verified |
| Пробелы | `load_submodel`/`assign_submodel` и `Wire.branch_to` живьём не проверены | unknown (раздел 10) |
