"""Реестр функций встроенного языка SimInTech и мера покрытия наших знаний.

**Зачем.** Знаниевый контент репозитория (`language/*.md`, `blocks/**/*.md`)
описывает язык вручную и заведомо неполон. Чтобы сказать «покрыто N из M»,
нужен машинно-читаемый список самих функций — иначе оценка берётся из головы.
Справка поставки этот список содержит, но только как HTML: здесь он
извлекается из неё (`build_registry`) и кладётся в
`data/language_functions.json`, а этот модуль его читает и сверяет с нашими
документами (`coverage`). COM не нужен — работает и на Linux.

**Как считается число функций.** Разделом языка считается каталог
`webhelp/11_yazyk_programmirovaniya/`. Функция — это страница раздела, у
которой есть раздел «Синтаксис» (структурный признак — якорь `__syntax`:
он же несёт форму вызова), кроме страниц каталога ключевых слов
`5_klyuchevye_slova/` — там тоже «Синтаксис», но это `and`, `begin..end` или
`category` из языка запросов, а не функции. Всё, у чего «Синтаксиса» нет, —
обзорные страницы категорий (`DIR_*.html` и одноимённые им), их 55. Так
получается **907** функций: 904 в `6_funkcii/` и 3 в
`8_funkcii_graficheskogo_kontejnera/`.

Почему не 959: 959 — это **все** файлы `.html` каталога `6_funkcii/`
(904 функции + 55 обзорных страниц категорий). Число из плана
`simintech-mcp/docs/gap-closure-plan.md` («959 функций») — размер каталога, а не
число функций; три функции графического контейнера лежат вне `6_funkcii/`.

**Признак «только в графическом контейнере»** отдельного поля на странице не
имеет: он берётся со страницы-указателя
`funkcii_dostupnye_tolko_v_graf_konteinere.html` (78 ссылок).

**Назначение** — `shortdesc` страницы (одна строка, не длиннее 132 знаков на
поставке v15.05.2026), очищенный от разметки. Извлекается он не всегда: у двух
страниц (`projectloaddb`, `projectsavedb`) его нет — у них поле пустое, а не
выдумано.

**Синтаксис и аргументы** (схема 2) — разделы карточки «Синтаксис» (текст
`<pre>`, переводы строк сохранены: у `createwire` там две формы вызова) и
«Аргументы» (таблица «Имя / Тип данных / Описание», строка заголовка
отбрасывается). Без них реестр отвечал «имя есть», но не давал позвать
функцию — знание формы вызова жило только в справке. Разделы берутся по
якорям DITA (`__syntax`/`__args`), а не по заголовкам: якорь не переводится и
не меняется от разметки, — суффикс якоря не зависит от имени файла, хотя сам
якорь несёт его в префиксе. Отсутствие разделов — пустые значения, не выдумка.

**Пересборка** (нужна при обновлении поставки)::

    python -m simintech_api.language /mnt/c/SimInTech64/webhelp

Расхождение реестра с изменившейся справкой ловит тест
`test_distribution_registry_is_not_stale` (маркер `distribution`).
"""
from __future__ import annotations

import argparse
import html
import json
import posixpath
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import (Dict, Iterable, List, Optional, Sequence, Set, Tuple,
                    cast)

#: Каталог справки, в котором лежит раздел языка (аргумент `build_registry`).
#: Проверка поставки: `/mnt/c/SimInTech64/webhelp`.
HELP_SECTION = "11_yazyk_programmirovaniya"

#: Подкаталог раздела с функциями. Значения вне его — только у трёх функций
#: графического контейнера, поэтому список, а не константа.
FUNCTIONS_DIR = "6_funkcii"
GRAPHICS_CONTAINER_DIR = "8_funkcii_graficheskogo_kontejnera"

#: Каталог ключевых слов: страницы там тоже с «Синтаксисом», но это не функции.
KEYWORDS_DIR = "5_klyuchevye_slova"

#: Страница-указатель «только в графическом контейнере» — единственный источник
#: признака `graphics_only`; на самих страницах его нет.
GRAPHICS_ONLY_PAGE = "funkcii_dostupnye_tolko_v_graf_konteinere.html"

#: Алфавитный указатель. Служит сверкой: его ссылки неполны, и часть из них —
#: ключевые слова, а не функции.
ALPHABET_PAGE = "vse_funkcii_i_kluchevye_slova_po_alfavitu.html"

#: Версия формата `data/language_functions.json`.
REGISTRY_VERSION = 2

DATA_DIR = Path(__file__).parent / "data"
DEFAULT_REGISTRY_PATH = DATA_DIR / "language_functions.json"

#: Раздел «Синтаксис» — признак страницы функции. Берётся по якорю, а не по
#: заголовку (`sectiontitle`): сплошная проверка 03.10.2026 показала, что у
#: пяти страниц **системных переменных** (`globalcolor`, `container_name`, …)
#: заголовок «Синтаксис» есть, а якоря нет, — заголовком они выглядели бы
#: функциями без синтаксиса. Так признак функции и извлечение формы вызова —
#: один и тот же якорь, и «функция без синтаксиса» структурно невозможна.
_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S)
_SHORTDESC_RE = re.compile(
    r'<p class="- topic/shortdesc shortdesc">(.*?)</p>', re.S)
_BREADCRUMB_RE = re.compile(r'<ol class="d-print-none">(.*?)</ol>', re.S)
_CRUMB_ITEM_RE = re.compile(r'<div class="title"><a href="[^"]*">([^<]*)</a>')
_CHILD_LINK_RE = re.compile(r'<strong><a href="([^"]+)">([^<]*)</a></strong>')
_HELP_VERSION_RE = re.compile(r"Справочная система SimInTech \(([^)]+)\)")

#: Разделы карточки по суффиксу якоря DITA (`id<имя>__syntax`, `__args`).
#: Суффикс выбран намеренно: префикс — имя файла страницы, а оно у части
#: страниц с кириллическим двойником (`arсsin`) или спецсимволом (`@`) в
#: идентификатор так просто не превращается.
#:
#: Захват нежадный до первого `</section>`: **вложенных секций в справке нет**
#: (сплошная проверка 03.10.2026: 0 из 970 у `__syntax`). Если вендор их
#: заведёт, строка синтаксиса оборвётся молча — тогда разбор надо дополнить
#: счётчиком вложенности (граница названа здесь, чтобы не искать её заново).
_SYNTAX_ID_RE = re.compile(
    r'(?s)<section[^>]*id="[^"]*__syntax"[^>]*>(.*?)</section>')
_ARGS_ID_RE = re.compile(
    r'(?s)<section[^>]*id="[^"]*__args"[^>]*>(.*?)</section>')
_PRE_RE = re.compile(r"(?s)<pre[^>]*>(.*?)</pre>")
_ROW_RE = re.compile(r"(?s)<tr[^>]*>(.*?)</tr>")
_CELL_RE = re.compile(r"(?s)<t[hd][^>]*>(.*?)</t[hd]>")

#: Границы слова при поиске имени в документах. Только ASCII: имена функций
#: латинские, а соседство с кириллицей («функцияabs») — уже не имя функции.
_WORD_CLASS = "A-Za-z0-9_"


# ─── Разбор страниц справки ───────────────────────────────────────

def _text(raw: str) -> str:
    """Разметка → текст: теги убраны, сущности раскрыты, пробелы схлопнуты."""
    return html.unescape(re.sub(r"\s+", " ", re.sub("<[^>]+>", "", raw))).strip()


def _pre_text(raw: str) -> str:
    """Текст блока `<pre>`: построчно, без тегов; пустые строки убраны.

    Отличие от `_text` — сохранённые переводы строк: в «Синтаксисе»
    `createwire` две формы вызова, и схлопывание склеило бы их в одну.
    """
    text = html.unescape(re.sub("<[^>]+>", "", raw)).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


@dataclass(frozen=True)
class HelpArg:
    """Аргумент функции из раздела «Аргументы» справки.

    Args:
        name: имя аргумента, как в таблице справки.
        type: тип данных («integer», «строка»); пустая строка, если колонки нет.
        description: описание из третьей колонки; пусто, если её нет.
    """

    name: str
    type: str
    description: str

    def as_dict(self) -> Dict[str, str]:
        """Представление для JSON."""
        return {"name": self.name, "type": self.type,
                "description": self.description}

    @classmethod
    def from_dict(cls, raw: Dict[str, object]) -> "HelpArg":
        """Запись из JSON; недостающие поля — пустые строки."""
        return cls(
            name=str(raw.get("name", "")),
            type=str(raw.get("type", "")),
            description=str(raw.get("description", "")),
        )


def _syntax_of(source: str) -> str:
    """Синтаксис карточки: `<pre>` раздела `__syntax`; пусто, если разделов нет."""
    section = _SYNTAX_ID_RE.search(source)
    if not section:
        return ""
    pre = _PRE_RE.search(section.group(1))
    return _pre_text(pre.group(1)) if pre else _text(section.group(1))


def _args_of(source: str) -> Tuple[HelpArg, ...]:
    """Аргументы карточки: строки таблицы `__args`; строка заголовка отброшена.

    Ячейки разбираются по отдельности, а не одним `_text`: по тексту всей
    секции колонки слились бы, и «имя» от «описания» стало бы неотличимо.

    Строка берётся и с одной ячейкой: таблица без колонок типа/описания —
    всё ещё аргументы, и потерять их целиком было бы хуже, чем показать имя
    без подробностей (тип и описание тогда пустые — так же честно, как
    пустое назначение у двух страниц справки).
    """
    section = _ARGS_ID_RE.search(source)
    if not section:
        return ()
    args: List[HelpArg] = []
    for row in _ROW_RE.findall(section.group(1)):
        cells = [_text(cell) for cell in _CELL_RE.findall(row)]
        if not cells or not cells[0] or cells[0] == "Имя":
            continue
        args.append(HelpArg(
            name=cells[0],
            type=cells[1] if len(cells) > 1 else "",
            description=cells[2] if len(cells) > 2 else "",
        ))
    return tuple(args)


@dataclass(frozen=True)
class HelpPage:
    """Разобранная страница раздела языка.

    Args:
        doc: путь страницы относительно корня справки, в нотации POSIX
            (`11_yazyk_programmirovaniya/6_funkcii/11_standartnye/abs.html`).
        name: заголовок `<h1>` — имя функции (`@`, `~`, `abs`).
        purpose: `shortdesc` одной строкой; пустая строка, если его нет.
        breadcrumb: заголовки хлебных крошек по порядку, включая имя страницы.
        has_syntax: есть ли раздел «Синтаксис».
        syntax: текст раздела «Синтаксис» (может быть многострочным); пусто,
            если раздела нет.
        args: аргументы из раздела «Аргументы» по порядку; пусто, если раздела
            нет или таблица не разобралась.
    """

    doc: str
    name: str
    purpose: str
    breadcrumb: Tuple[str, ...]
    has_syntax: bool
    syntax: str = ""
    args: Tuple[HelpArg, ...] = ()


def parse_page(source: str, doc: str = "") -> HelpPage:
    """Разобрать HTML-страницу справки.

    Отсутствующие элементы не ошибка: у обзорной страницы категории нет ни
    `shortdesc`, ни раздела «Синтаксис», и это ровно то, чем она отличается от
    страницы функции.
    """
    h1 = _H1_RE.search(source)
    short = _SHORTDESC_RE.search(source)
    crumbs = _BREADCRUMB_RE.search(source)
    return HelpPage(
        doc=doc,
        name=_text(h1.group(1)) if h1 else "",
        purpose=_text(short.group(1)) if short else "",
        breadcrumb=tuple(_CRUMB_ITEM_RE.findall(crumbs.group(1)))
        if crumbs else (),
        has_syntax=bool(_SYNTAX_ID_RE.search(source)),
        syntax=_syntax_of(source),
        args=_args_of(source),
    )


def _is_function(page: HelpPage) -> bool:
    """Страница функции.

    Два условия, и оба нужны. Раздел «Синтаксис» отличает функцию от обзорной
    страницы категории. Каталог отличает её от **системных переменных**
    (`2_peremennye/sistemnye_peremennye/`): у них раздел тоже назван
    «Синтаксис» (заголовком — якоря нет), но это не функции, и в реестре
    функций им не место.
    """
    if not page.has_syntax:
        return False
    return any(_in_dir(page.doc, name)
               for name in (FUNCTIONS_DIR, GRAPHICS_CONTAINER_DIR))


def _in_dir(doc: str, name: str) -> bool:
    """Лежит ли страница (или ссылка) внутри каталога `name` раздела."""
    rest = doc[len(HELP_SECTION) + 1:] if doc.startswith(HELP_SECTION + "/") \
        else doc
    return rest == name or rest.startswith(name + "/")


def _child_links(source: str, doc: str) -> List[str]:
    """Ссылки со страницы-указателя → пути относительно корня справки.

    Ссылки относительны самой страницы (`../11_yazyk_programmirovaniya/…`),
    поэтому приводятся к одному виду — `normpath` в нотации POSIX. Иначе
    `..` остался бы в пути и страница не совпала бы с записью реестра.
    """
    base = posixpath.dirname(doc)
    result: List[str] = []
    for href, _title in _CHILD_LINK_RE.findall(source):
        if href.startswith("#") or "://" in href:
            continue
        result.append(posixpath.normpath(posixpath.join(base, href)))
    return result


def _iter_pages(help_dir: Path) -> List[Tuple[str, str]]:
    """Все страницы раздела языка: [(путь от корня справки, содержимое)]."""
    root = help_dir / HELP_SECTION
    if not root.is_dir():
        raise FileNotFoundError(
            f"нет раздела языка справки: {root} — укажите каталог webhelp "
            f"поставки SimInTech")
    found: List[Tuple[str, str]] = []
    for path in sorted(root.rglob("*.html")):
        doc = path.relative_to(help_dir).as_posix()
        found.append((doc, path.read_text(encoding="utf-8", errors="replace")))
    return found


# ─── Построение реестра ───────────────────────────────────────────

@dataclass(frozen=True)
class LanguageFunction:
    """Функция встроенного языка.

    Args:
        name: имя так, как его пишут в коде (`abs`, `@`, `new~`).
        category: категория справки первого уровня («Векторные и матричные»).
        section: подкатегория («Преобразования координат») или пустая строка.
        doc: страница справки (путь от корня справки), источник записи.
        graphics_only: True, если функция доступна только в графическом
            контейнере — со страницы-указателя справки.
        purpose: назначение одной строкой из справки; пустая строка, если его
            на странице нет.
        syntax: форма вызова из раздела «Синтаксис» (может быть многострочной);
            пустая строка, если раздела на странице нет (схема 2).
        args: аргументы из раздела «Аргументы» по порядку (схема 2).
    """

    name: str
    category: str
    section: str
    doc: str
    graphics_only: bool
    purpose: str
    syntax: str = ""
    args: Tuple[HelpArg, ...] = ()

    def as_dict(self) -> Dict[str, object]:
        """Представление для JSON."""
        return {
            "name": self.name,
            "category": self.category,
            "section": self.section,
            "doc": self.doc,
            "graphics_only": self.graphics_only,
            "purpose": self.purpose,
            "syntax": self.syntax,
            "args": [arg.as_dict() for arg in self.args],
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, object]) -> "LanguageFunction":
        """Запись из JSON.

        Поля схемы 2 (`syntax`, `args`) необязательны: реестр схемы 1
        читается без них — пустыми, а не отказом: иначе обновление читателя
        раньше писателя роняло бы чтение.
        """
        raw_args = raw.get("args")
        return cls(
            name=str(raw.get("name", "")),
            category=str(raw.get("category", "")),
            section=str(raw.get("section", "")),
            doc=str(raw.get("doc", "")),
            graphics_only=bool(raw.get("graphics_only", False)),
            purpose=str(raw.get("purpose", "")),
            syntax=str(raw.get("syntax", "")),
            args=tuple(HelpArg.from_dict(item)
                       for item in raw_args
                       if isinstance(item, dict))
            if isinstance(raw_args, list) else (),
        )

    @property
    def full_category(self) -> str:
        """Полная категория: `Графические и системные / Системные`."""
        if self.section:
            return f"{self.category} / {self.section}"
        return self.category

    def __str__(self) -> str:
        return self.name


#: Хлебные крошки начинаются с раздела справки и его страницы «Функции»;
#: категории — то, что между ними и именем страницы.
_CRUMB_PREFIX = ("Язык программирования SimInTech", "Функции")


def _category_of(page: HelpPage) -> Tuple[str, str]:
    """Категория и подкатегория страницы функции.

    Источник — хлебные крошки: они дают русские названия, а не имена каталогов.
    Крошки **не всегда** ведут через «Функции»: страница, на которую ссылается
    только алфавитный указатель (а не обзор своей категории), показывает
    родителем сам указатель. Для таких страниц имя категории берётся из
    каталога — по большинству соседей (`_fallback_categories`).
    """
    crumbs = page.breadcrumb
    if len(crumbs) >= 3 and crumbs[:2] == _CRUMB_PREFIX:
        middle = crumbs[2:-1]
        if middle:
            return middle[0], (middle[1] if len(middle) > 1 else "")
    return "", ""


def _fallback_categories(pages: Sequence[HelpPage]) -> Dict[str, Tuple[str, str]]:
    """Категории по каталогам: {каталог: (категория, подкатегория)}.

    Строится по большинству страниц каталога, у которых крошки нормальные;
    затем применяется к страницам с испорченными крошками. Выбор по большинству
    нужен из-за дублей: одни и те же `waterps` лежат и в `9_svojstva_veshchestv`,
    и в `9_svojstva_vody_i_vodyanogo_para`, где крошки теряются.
    """
    votes: Dict[str, Dict[Tuple[str, str], int]] = {}
    for page in pages:
        known = _category_of(page)
        if not known[0]:
            continue
        directory = _directory(page.doc)
        votes.setdefault(directory, {})
        votes[directory][known] = votes[directory].get(known, 0) + 1
    return {directory: max(counts, key=lambda key: counts[key])
            for directory, counts in votes.items()}


def _directory(doc: str) -> str:
    """Каталог страницы относительно корня справки."""
    parts = doc.split("/")
    return "/".join(parts[:-1])


def build_registry(help_dir: Path) -> Dict[str, object]:
    """Собрать реестр функций из раздела справки.

    Args:
        help_dir: каталог `webhelp` поставки SimInTech.

    Returns:
        Словарь для записи в `data/language_functions.json`.

    Raises:
        FileNotFoundError: если раздела языка в `help_dir` нет.
    """
    raw = _iter_pages(help_dir)
    pages = [parse_page(source, doc) for doc, source in raw]
    by_doc = {doc: source for doc, source in raw}

    graphics_doc = f"{HELP_SECTION}/{GRAPHICS_ONLY_PAGE}"
    graphics_source = by_doc.get(graphics_doc)
    graphics_only = set(_child_links(graphics_source, graphics_doc)) \
        if graphics_source else set()

    alphabet_doc = f"{HELP_SECTION}/{ALPHABET_PAGE}"
    alphabet_source = by_doc.get(alphabet_doc)
    alphabet_links = _child_links(alphabet_source, alphabet_doc) \
        if alphabet_source else []

    fallback = _fallback_categories(pages)
    functions: List[LanguageFunction] = []
    for page in pages:
        if not _is_function(page):
            continue
        category, section = _category_of(page)
        if not category:
            category, section = fallback.get(_directory(page.doc), ("", ""))
        functions.append(LanguageFunction(
            name=page.name,
            category=category,
            section=section,
            doc=page.doc,
            graphics_only=page.doc in graphics_only,
            purpose=page.purpose,
            syntax=page.syntax,
            args=page.args,
        ))
    functions.sort(key=lambda f: (f.name, f.doc))

    categories = _categories(functions)
    help_version = _help_version(raw)
    return {
        "version": REGISTRY_VERSION,
        "section": HELP_SECTION,
        "help_version": help_version,
        "meta": {
            "observation": _observation(help_version),
        },
        "graphics_only_page": graphics_source is not None,
        "alphabet_page": alphabet_source is not None,
        "count": len(functions),
        "counts": {
            "functions": len(functions),
            "unique_names": len({f.name for f in functions}),
            "graphics_container_only": sum(
                1 for f in functions if f.graphics_only),
            "with_purpose": sum(1 for f in functions if f.purpose),
            "with_syntax": sum(1 for f in functions if f.syntax),
            "with_args": sum(1 for f in functions if f.args),
            "categories": len({str(row["category"]) for row in categories}),
            "category_rows": len(categories),
            "alphabet_index_entries": len(alphabet_links),
            "alphabet_index_pages": len(set(alphabet_links)),
            "alphabet_index_keywords": sum(
                1 for link in alphabet_links
                if _in_keywords(link)),
            "alphabet_index_functions": sum(
                1 for link in alphabet_links
                if not _in_keywords(link)),
        },
        "categories": categories,
        "functions": [f.as_dict() for f in functions],
    }


def _in_keywords(doc: str) -> bool:
    """Ссылка указателя ведёт в каталог ключевых слов, а не к функции."""
    return _in_dir(doc, KEYWORDS_DIR)


def _observation(help_version: str) -> Dict[str, object]:
    """Чем и когда снят реестр — привязка снапшота к версии справки.

    Обязательные поля снапшота — `docs/knowledge-snapshot.md`: без
    `observation` пересборка теряла бы привязку к версии, и реестр следующей
    поставки выглядел бы как старый. Поле обязано проставляться **сборщиком**
    (так же устроен каталог блоков): иначе оно живёт только в лежащем файле,
    и первая же пересборка его роняет — так и случилось с реестром, который
    собирался вне репозитория.

    `version` — версия **справки** (она прочитана со страниц), а версия
    продукта здесь не спрашивается: её знает человек, и догадка хуже
    `unknown`. `observed_at` — день пересборки: он и есть дата наблюдения.
    """
    # Импорт ленивый: `__version__` объявлен в конце `__init__.py` (как в
    # `catalog._observation` — иначе цикл импорта).
    from . import __version__ as package_version

    return {
        "product": "SimInTech",
        "version": help_version or "unknown",
        "observed_at": date.today().isoformat(),
        "source": "справка поставки (help.simintech.ru)",
        "generator": f"simintech-api {package_version}",
    }


def _help_version(raw: Sequence[Tuple[str, str]]) -> str:
    """Версия справки из её шапки (`v15.05.2026`); пусто, если не нашлась.

    Версия проставлена в логотипе каждой страницы (`alt` картинки), а не в
    отдельном файле, поэтому берётся с первой же страницы.
    """
    for _doc, source in raw:
        found = _HELP_VERSION_RE.search(source)
        if found:
            return found.group(1)
    return ""


def _categories(
        functions: Iterable[LanguageFunction]) -> List[Dict[str, object]]:
    """Список категорий с числом функций, по убыванию числа."""
    counts: Dict[Tuple[str, str], int] = {}
    for function in functions:
        key = (function.category, function.section)
        counts[key] = counts.get(key, 0) + 1
    ordered = sorted(counts.items(),
                     key=lambda item: (-item[1], item[0][0], item[0][1]))
    return [{"category": category, "section": section, "count": count}
            for (category, section), count in ordered]


# ─── Чтение реестра ───────────────────────────────────────────────

_registry: Optional[List[LanguageFunction]] = None
_registry_meta: Dict[str, object] = {}


def _load(path: Optional[Path] = None) -> List[LanguageFunction]:
    """Прочитать реестр из JSON (один раз на процесс)."""
    global _registry, _registry_meta
    if _registry is not None and path is None:
        return _registry
    target = Path(path) if path else DEFAULT_REGISTRY_PATH
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FileNotFoundError(
            f"не читается реестр функций языка {target}: {exc} — "
            f"пересоберите его: python -m simintech_api.language <webhelp>"
        ) from exc
    functions = [LanguageFunction.from_dict(item)
                 for item in raw.get("functions", [])]
    if path is not None:
        return functions
    _registry = functions
    _registry_meta = {"version": raw.get("version"),
                      "help_version": raw.get("help_version", ""),
                      "count": raw.get("count"), "counts": raw.get("counts", {})}
    return _registry


def language_functions(path: Optional[Path] = None) -> List[LanguageFunction]:
    """Все функции встроенного языка из реестра.

    Args:
        path: путь к JSON реестра; по умолчанию — поставляемый
            `data/language_functions.json`. Указанный путь не кэшируется.
    """
    return list(_load(path))


def registry_meta() -> Dict[str, object]:
    """Метаданные поставки реестра: версия формата, версия справки, числа."""
    _load()
    return dict(_registry_meta)


#: Кириллические буквы, неотличимые на вид от латинских. В справке SimInTech они
#: встречаются **внутри имён функций**: страницы называются `arсsin` и `arсtg`,
#: где третья буква — `U+0441` (кириллическая «с»), а не латинская `c`.
#: Это дефект справки, а не разбора: проверено по байтам заголовка страницы.
#: Ловушка практическая — имя, скопированное из справки, в скрипт не встанет, а
#: набранное руками латиницей не находилось в реестре.
_HOMOGLYPHS = str.maketrans({
    "а": "a", "с": "c", "е": "e", "о": "o", "р": "p", "х": "x", "у": "y",
    "к": "k", "м": "m", "т": "t", "в": "b", "н": "h", "ѕ": "s", "і": "i",
})


def _fold_homoglyphs(text: str) -> str:
    """Привести кириллические двойники к латинице (для поиска, не для вывода)."""
    return text.translate(_HOMOGLYPHS)


def find_function(name: str,
                  path: Optional[Path] = None) -> Optional[LanguageFunction]:
    """Найти функцию по имени.

    Регистр не важен: язык SimInTech регистр не различает (`Speed` = `speed`).
    Если имя описано в нескольких категориях (`buffer` есть и в
    `22_funkcii_obrabotki_signalov`, и в `funkcii_raboty_s_bibliotekami`) —
    возвращается первая запись; обо всех расскажет `find_functions`.

    Поиск терпим к кириллическим двойникам латинских букв: имя берётся из
    справки как есть, поэтому `find_function("arcsin")`, набранный латиницей,
    находит `arсsin` (см. `_HOMOGLYPHS`). Настоящее имя видно в поле `name`
    результата — по нему и надо судить, что писать в скрипте.
    """
    exact = find_functions(name, path)
    if exact:
        return exact[0]
    folded = _fold_homoglyphs(name.strip().lower())
    for function in language_functions(path):
        if _fold_homoglyphs(function.name.lower()) == folded:
            return function
    return None


def find_functions(name: str,
                   path: Optional[Path] = None) -> List[LanguageFunction]:
    """Все записи реестра с таким именем (их бывает больше одной).

    Сверка точная, без приведения двойников: здесь важно не ошибиться именем,
    которое пойдёт в скрипт.
    """
    key = name.strip().lower()
    return [f for f in language_functions(path) if f.name.lower() == key]


# ─── Покрытие наших знаний ────────────────────────────────────────

#: Каталоги наших документов о языке относительно `docs_dir`.
DOC_DIRS = ("language", "blocks")


@dataclass(frozen=True)
class Coverage:
    """Что из реестра встречается в наших документах.

    Args:
        total: уникальных имён функций в реестре (дубли категорий — за одно).
        covered: имена, найденные в документах (отсортированы).
        uncovered: имена, не найденные (отсортированы).
        uncovered_by_category: [(категория, непокрытых), …] по убыванию.
        files: документы, по которым шла сверка.
    """

    total: int
    covered: Tuple[str, ...]
    uncovered: Tuple[str, ...]
    uncovered_by_category: Tuple[Tuple[str, int], ...]
    files: Tuple[Path, ...]

    @property
    def covered_count(self) -> int:
        """Сколько имён покрыто."""
        return len(self.covered)

    @property
    def ratio(self) -> float:
        """Доля покрытых имён, 0.0 … 1.0."""
        return self.covered_count / self.total if self.total else 0.0

    def summary(self) -> str:
        """Строка для ответа человеку."""
        return (f"покрыто {self.covered_count} из {self.total} "
                f"({self.ratio:.1%}) по {len(self.files)} документам")


def _doc_files(docs_dir: Path) -> List[Path]:
    """Документы `docs_dir/language/**/*.md` и `docs_dir/blocks/**/*.md`."""
    files: List[Path] = []
    for name in DOC_DIRS:
        root = docs_dir / name
        if root.is_dir():
            files.extend(sorted(root.rglob("*.md")))
    if not files:
        raise FileNotFoundError(
            f"в {docs_dir} нет документов о языке: ожидались каталоги "
            f"{' и '.join(DOC_DIRS)} с файлами .md — укажите корень репозитория")
    return files


def coverage(docs_dir: Path, path: Optional[Path] = None) -> Coverage:
    """Сверить наши документы о языке с реестром справки.

    Имя ищется **как слово**: `abs` не засчитывается по вхождению в `absolute`.
    Границы слова — ASCII (`[A-Za-z0-9_]`), регистр не важен (язык его не
    различает). Оговорка: имена-слова (`and`, `or`, `not`, `div`, `mod`) и
    знаки (`@`, `~`) могут встретиться в тексте не как функция — на поставке
    это единственный источник завышения, и он мал по сравнению с 878 именами.

    Args:
        docs_dir: корень репозитория с каталогами `language/` и `blocks/`.
        path: альтернативный JSON реестра (для тестов).

    Raises:
        FileNotFoundError: если в `docs_dir` нет ни `language/`, ни `blocks/`.
    """
    files = _doc_files(docs_dir)
    functions = language_functions(path)
    text = "\n".join(file.read_text(encoding="utf-8", errors="replace")
                     for file in files)

    names = sorted({f.name for f in functions if f.name}, key=len, reverse=True)
    found = _find_words(text, names)
    covered = tuple(sorted(name for name in names if name.lower() in found))
    uncovered = tuple(sorted(name for name in names if name.lower() not in found))
    return Coverage(
        total=len(names),
        covered=covered,
        uncovered=uncovered,
        uncovered_by_category=_uncovered_by_category(
            functions, {name.lower() for name in uncovered}),
        files=tuple(files),
    )


def _find_words(text: str, names: Sequence[str]) -> Set[str]:
    """Какие из `names` встречаются в `text` как отдельные слова (в нижнем)."""
    if not names:
        return set()
    pattern = "|".join(re.escape(name) for name in names)
    regex = re.compile(rf"(?<![{_WORD_CLASS}])({pattern})(?![{_WORD_CLASS}])",
                       re.IGNORECASE)
    return {match.group(1).lower() for match in regex.finditer(text)}


def _uncovered_by_category(
        functions: Sequence[LanguageFunction],
        uncovered: Set[str]) -> Tuple[Tuple[str, int], ...]:
    """Сколько непокрытых имён в каждой категории, по убыванию числа.

    Категория считается по первому уровню справки: имя, описанное в двух
    категориях, попадает в обе, поэтому сумма по столбцу больше числа
    непокрытых имён. Имена считаются множеством — дубль не удваивает число.
    """
    names: Dict[str, Set[str]] = {}
    for function in functions:
        if function.name:
            names.setdefault(function.category, set()).add(
                function.name.lower())
    rows = [(category, sum(1 for name in seen if name in uncovered))
            for category, seen in names.items()]
    rows.sort(key=lambda row: (-row[1], row[0]))
    return tuple(rows)


# ─── Пересборка реестра ───────────────────────────────────────────

def main(argv: Optional[Sequence[str]] = None) -> int:
    """Точка входа пересборки: `python -m simintech_api.language <webhelp>`."""
    parser = argparse.ArgumentParser(
        description="Собрать реестр функций языка из справки SimInTech")
    parser.add_argument("help_dir", type=Path,
                        help="каталог webhelp поставки (например, "
                             "/mnt/c/SimInTech64/webhelp)")
    parser.add_argument("--out", type=Path, default=DEFAULT_REGISTRY_PATH,
                        help=f"куда писать реестр (по умолчанию "
                             f"{DEFAULT_REGISTRY_PATH})")
    args = parser.parse_args(argv)

    registry = build_registry(args.help_dir)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    counts = cast(Dict[str, int], registry["counts"])
    print(f"{out}: функций {counts['functions']}, "
          f"уникальных имён {counts['unique_names']}, "
          f"только графический контейнер {counts['graphics_container_only']}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
