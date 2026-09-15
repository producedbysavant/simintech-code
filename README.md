# SimInTech Code

Открытая библиотека и база знаний по **SimInTech** — российской среде
моделирования динамических систем.

Репозиторий содержит две части:

- **`simintech-api`** — Python-библиотека управления SimInTech через внешний
  COM API (`IMVTU_Server`, сервер `mmain.exe`): создание проектов, блоки,
  связи, параметры, чтение и запись сигналов, расстановка блоков;
- **справочный контент** — встроенный язык, блоки, типовые схемы, туториалы,
  автоматизация.

## Состав

| Раздел | Описание |
|--------|----------|
| `simintech_api/` | Python-библиотека `simintech-api` (COM API SimInTech) |
| `examples/` | Примеры: сборка моделей, запуск макроса и `.pak` |
| `tests/unit/` | Unit-тесты библиотеки (без COM, идут и на Linux) |
| `tests/integration/` | Интеграционные тесты (нужен Windows и SimInTech) |
| `docs/` | Руководство, API, алгоритмы, архитектура, Sphinx, карта COM API |
| `language/` | Справочник встроенного языка программирования |
| `blocks/` | Документация по блокам с реальными именами свойств |
| `patterns/` | Типовые схемы: ПИД, пространство состояний, обратная связь |
| `tutorials/` | Пошаговые руководства для начинающих |
| `automation/` | Управление SimInTech извне: командная строка, макросы, COM, форматы файлов |

## Установка

```bash
pip install -e ".[test]"        # библиотека + pytest
```

Зависимость `comtypes` объявлена с маркером `sys_platform == 'win32'`: **COM
работает только на Windows**, там же нужен зарегистрированный COM-объект
(`C:\SimInTech64\bin\mmain.exe /regserver`). На Linux библиотека ставится и
проходят unit-тесты; COM-вызовы недоступны.

Консольные команды: `simintech-cli` и `simintech-generate-catalog`.

## Быстрый старт (библиотека)

```python
from simintech_api import COMClient, Project

client = COMClient().connect()          # Windows + mmain.exe /regserver
project = Project.from_template(client)  # проект с расчётным слоем
project.set_calc_end_time(1.0)
page = project.get_main_page()

const = page.create_block("Константа", 100.0, 100.0)
const.set_property("a", 2.0)            # у «Константы» параметр называется `a`
const.init()
gain = page.create_block("Усилитель", 300.0, 100.0)
gain.set_property("a", 3.0)
gain.init()
const.connect(gain)

project.save_xml(r"C:\Temp\model.xprt")
```

Обратите внимание: проект создаётся **из шаблона**. `Project.new()` даёт пустой
проект — в нём нет расчётного слоя и настроек расчёта, поэтому он не считает
(модельное время не растёт, хотя вызовы возвращают успех). Полный пример с
расчётом и выводом результата в файл — `examples/run_to_file.py`.

Проверка:

```bash
python3.11 -m pytest tests/unit -q     # 153 теста, без COM
flake8 simintech_api/ --max-line-length=88 --extend-ignore=E203,W503
```

Интеграционные тесты (Windows, реальный COM):

```bash
python -m pytest tests/integration -m integration -q
```

## Быстрый старт (язык SimInTech)

Простейшая программа для блока «Язык программирования»:

```simintech
input u: double;
output y: double;

begin
    y = u * 2.5;
end;
```

Переменные объявляются с явным типом, шаг расчёта — встроенная переменная
`stepsize`, цикл записывается как `for (idx = 1, N) do`. Полный свод правил —
в `language/syntax.md`.

## С чего начать

- **Никогда не работали с SimInTech** — `tutorials/01-first-model.md`.
- **Нужен конкретный блок** — `blocks/`.
- **Нужен готовый контур управления** — `patterns/`.
- **Пишете код в блоке** — `language/` (и обязательно `language/pitfalls.md`
  перед кодогенерацией).
- **Автоматизируете расчёт или правку схем** — `automation/`.
- **Управляете SimInTech из Python** — `docs/guide.md`, `docs/api.md`.

## Смежные репозитории

- [`simintech-mcp`](https://github.com/producedbysavant/simintech-mcp) —
  MCP-сервер: оборачивает эту библиотеку инструментами для ИИ-агента.
- [`simintech-skill`](https://github.com/producedbysavant/simintech-skill) —
  скиллы с доменными знаниями; ссылаются на контент этого репозитория по URL.

## Участие

Изменения принимаются только через pull request — прямой push в `main`
запрещён правилами репозитория. Начните с issue: шаблоны открываются
автоматически.

Перед отправкой PR прочитайте `CONTRIBUTING.md`: там и правила для
документации блоков, и требования к правкам библиотеки (тесты, линтер).
Примеры кода на языке SimInTech сверяйте с `language/syntax.md` — это
источник истины по синтаксису.

## Официальная документация

**<https://help.simintech.ru/>** — справочная система SimInTech от разработчика.

Этот репозиторий дополняет её, а не заменяет: здесь собраны примеры, типовые
схемы и грабли из практики. Всё, что касается встроенного поведения среды —
точных названий пунктов меню, горячих клавиш, свойств блоков, — сверяйте
со справкой: она обновляется вместе с продуктом, а этот репозиторий может
отставать.

## Лицензия

MIT
