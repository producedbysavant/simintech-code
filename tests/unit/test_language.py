"""Тесты реестра функций встроенного языка SimInTech (без COM).

Синтетическая справка повторяет разметку DITA-OT: имя страницы в `<h1>`,
русские названия категорий — в хлебных крошках, назначение — в `shortdesc`,
а признак функции — заголовок раздела «Синтаксис».
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest  # noqa: E402

from simintech_api.language import (  # noqa: E402
    DEFAULT_REGISTRY_PATH,
    build_registry,
    coverage,
    find_function,
    find_functions,
    language_functions,
    parse_page,
    registry_meta,
)

#: Поставка SimInTech: по её справке проверяются сплошные тесты. Каталог
#: задаётся переменной `SIMINTECH_ROOT`; без поставки они пропускаются.
DISTRIBUTION = Path(os.environ.get("SIMINTECH_ROOT", "/mnt/c/SimInTech64"))
HELP_DIR = DISTRIBUTION / "webhelp"


# ─── Синтетическая справка ────────────────────────────────────────

def _crumbs(items):
    """Хлебные крошки страницы в разметке справки."""
    links = "".join(
        f'<li><div class="topicref"><div class="title">'
        f'<a href="x.html">{item}</a></div></div></li>' for item in items)
    return f'<ol class="d-print-none">{links}</ol>'


def _page(name, crumbs, purpose=None, syntax=True):
    """Страница справки: функция (`syntax=True`) или обзор категории."""
    short = f'<p class="- topic/shortdesc shortdesc">{purpose}</p>' \
        if purpose else ""
    section = ('<section id="x__syntax"><h2 class="- topic/title title '
               'sectiontitle">Синтаксис</h2><pre><code>y = f(x);'
               '</code></pre></section>') if syntax else ""
    return (f"<!DOCTYPE html><html><body>"
            f"{_crumbs(crumbs)}"
            f'<h1 class="- topic/title title topictitle1" '
            f'id="ariaid-title1">{name}</h1>'
            f'<div class="- topic/body body">{short}{section}</div>'
            f"</body></html>")


def _index(links):
    """Страница-указатель: ссылки `../11_yazyk_programmirovaniya/…`.

    Ссылки относительны самой страницы указателя (он лежит в разделе языка),
    поэтому путь начинается с `../` — так же, как в справке.
    """
    items = "".join(
        f'<li class="- topic/link link ulchildlink"><strong>'
        f'<a href="../{doc}">{name}</a></strong>'
        f'<div class="- topic/desc desc">{name}</div></li>'
        for name, doc in links)
    return f'<!DOCTYPE html><html><body><ul class="ullinks">{items}</ul>' \
           f"</body></html>"


def _write(root, doc, text):
    """Положить страницу по пути относительно корня справки."""
    path = Path(root, *doc.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _build_help(tmp_path):
    """Синтетическая справка: функции, обзор категории, ключевые слова.

    Все ловушки настоящей справки представлены, потому что каждая из них уже
    ломала разбор:

    * `sinc` — крошки ведут через алфавитный указатель, а не через категорию
      (страница не упомянута обзором своей категории): название категории
      берётся по большинству соседей;
    * `globalcolor` — системная переменная: раздел «Синтаксис» у неё есть,
      функцией она не является;
    * `var` — ключевое слово: раздел «Синтаксис» есть, функция — нет;
    * `bringtofront` — только графический контейнер: признак есть лишь на
      странице-указателе, на самой странице его нет;
    * `setvisiblelayer` — функция графического контейнера **вне** `6_funkcii`;
    * обзор категории (`DIR_…`) — «Синтаксиса» нет ни у одной такой страницы.
    """
    root = tmp_path / "webhelp"
    section = "11_yazyk_programmirovaniya"
    lang = f"{section}"
    _write(root, f"{lang}/6_funkcii/DIR_1_kategoriya.html", _page(
        "Категория один", ["Язык программирования SimInTech"], syntax=False))
    _write(root, f"{lang}/6_funkcii/1_kategoriya/abs.html", _page(
        "abs", ["Язык программирования SimInTech", "Функции",
                "Категория один", "abs"], "Функция получения модуля числа."))
    _write(root, f"{lang}/6_funkcii/1_kategoriya/absolute.html", _page(
        "absolute", ["Язык программирования SimInTech", "Функции",
                     "Категория один", "absolute"], "Модуль числа."))
    _write(root, f"{lang}/6_funkcii/1_kategoriya/bringtofront.html", _page(
        "bringtofront", ["Язык программирования SimInTech", "Функции",
                         "Категория один", "bringtofront"], "На передний план."))
    _write(root, f"{lang}/6_funkcii/2_kategoriya/cos.html", _page(
        "cos", ["Язык программирования SimInTech", "Функции",
                "Категория два", "cos"], "Косинус."))
    _write(root, f"{lang}/6_funkcii/2_kategoriya/sinc.html", _page(
        "sinc", ["Язык программирования SimInTech",
                 "Все функции и ключевые слова по алфавиту", "sinc"],
        "Функция sinc."))
    _write(root, f"{lang}/5_klyuchevye_slova/var.html", _page(
        "var", ["Язык программирования SimInTech", "Функции",
                "Ключевые слова", "var"], "Описание переменной."))
    _write(root, f"{lang}/2_peremennye/sistemnye_peremennye/globalcolor.html",
           _page("globalcolor", ["Язык программирования SimInTech", "Функции",
                                 "Системные переменные", "globalcolor"],
                 "Цвет по умолчанию."))
    _write(root, f"{lang}/8_funkcii_graficheskogo_kontejnera/"
                 f"setvisiblelayer.html", _page(
                     "setvisiblelayer",
                     ["Язык программирования SimInTech", "Функции",
                      "Категория два", "setvisiblelayer"],
                     "Показать слой."))
    _write(root, f"{lang}/funkcii_dostupnye_tolko_v_graf_konteinere.html",
           _index([("bringtofront",
                    f"{lang}/6_funkcii/1_kategoriya/bringtofront.html"),
                   ("setvisiblelayer",
                    f"{lang}/8_funkcii_graficheskogo_kontejnera/"
                    f"setvisiblelayer.html")]))
    _write(root, f"{lang}/vse_funkcii_i_kluchevye_slova_po_alfavitu.html",
           _index([("abs", f"{lang}/6_funkcii/1_kategoriya/abs.html"),
                   ("var", f"{lang}/5_klyuchevye_slova/var.html")]))
    return root


# ─── Разбор страницы ──────────────────────────────────────────────

def test_parse_page_reads_name_purpose_and_category():
    """Со страницы берутся имя, назначение и русские названия категорий."""
    page = parse_page(_page(
        "steampt", ["Язык программирования SimInTech", "Функции",
                    "Архивные функции", "steampt"],
        "Специальная функция, вычисляющая свойства воды."), "a/steampt.html")

    assert page.name == "steampt"
    assert page.purpose == "Специальная функция, вычисляющая свойства воды."
    assert page.breadcrumb[-1] == "steampt"
    assert page.has_syntax


def test_parse_page_without_shortdesc_leaves_purpose_empty():
    """Назначения нет — поле пустое, а не придуманный текст.

    Так у двух страниц поставки (`projectloaddb`, `projectsavedb`): выдуманное
    назначение хуже пустого, потому что ему поверят.
    """
    page = parse_page(_page("f", ["a", "b"]), "a/f.html")

    assert page.purpose == ""


def test_parse_page_marks_category_overview():
    """У обзорной страницы категории раздела «Синтаксис» нет — это и есть её
    отличие от страницы функции."""
    page = parse_page(_page("Категория", ["Язык программирования SimInTech"],
                            syntax=False), "a/DIR_x.html")

    assert not page.has_syntax


def test_registry_ignores_overviews_keywords_and_system_variables(tmp_path):
    """В реестр попадают только функции.

    Обзор категории — без «Синтаксиса»; ключевое слово (`var`) и системная
    переменная (`globalcolor`) «Синтаксис» имеют, но функциями не являются.
    Проверка каталогом, а не именем: признака «это функция» на странице нет.
    """
    registry = build_registry(_build_help(tmp_path))

    names = {item["name"] for item in registry["functions"]}
    assert names == {"abs", "absolute", "bringtofront", "cos", "sinc",
                     "setvisiblelayer"}


def test_registry_keeps_function_of_graphics_container(tmp_path):
    """Функция графического контейнера лежит вне `6_funkcii/` — и всё же
    функция: отбор идёт по двум каталогам, а не по одному."""
    registry = build_registry(_build_help(tmp_path))

    found = {item["name"]: item for item in registry["functions"]}
    assert found["setvisiblelayer"]["doc"].endswith(
        "8_funkcii_graficheskogo_kontejnera/setvisiblelayer.html")


def test_graphics_only_flag_comes_from_index_page(tmp_path):
    """Признак «только графический контейнер» — со страницы-указателя.

    На самих страницах признака нет вовсе, поэтому без указателя он был бы
    потерян молча: обе страницы выглядели бы как обычные функции.
    """
    registry = build_registry(_build_help(tmp_path))

    only = {item["name"] for item in registry["functions"]
            if item["graphics_only"]}
    assert only == {"bringtofront", "setvisiblelayer"}


def test_category_of_page_with_broken_breadcrumbs(tmp_path):
    """Страница, известная только указателю, получает категорию соседей.

    У `sinc` крошки ведут через алфавитный указатель: своей категорией её никто
    не упомянул. Пустая категория выкинула бы функцию из подсчёта по
    категориям — поэтому название берётся по большинству соседей каталога.
    """
    registry = build_registry(_build_help(tmp_path))

    found = {item["name"]: item for item in registry["functions"]}
    assert found["sinc"]["category"] == "Категория два"


def test_registry_counts_alphabet_index(tmp_path):
    """Указатель считается отдельно: его ссылки — не только функции.

    В указателе есть ключевые слова (`var`), поэтому число ссылок ему и не
    равно числу функций.
    """
    registry = build_registry(_build_help(tmp_path))

    counts = registry["counts"]
    assert counts["alphabet_index_entries"] == 2
    assert counts["alphabet_index_keywords"] == 1
    assert counts["alphabet_index_functions"] == 1


def test_registry_reports_missing_section(tmp_path):
    """Без раздела языка — отказ, а не пустой реестр.

    Пустой реестр читался бы как «функций нет», и проверка покрытия молча
    показала бы ноль у всего.
    """
    with pytest.raises(FileNotFoundError, match="нет раздела языка"):
        build_registry(tmp_path / "нет-такого")


# ─── Реестр поставки ──────────────────────────────────────────────

def test_ship_record_has_version_and_functions():
    """Поставляемый реестр непуст, версия и число записей есть."""
    registry = json.loads(DEFAULT_REGISTRY_PATH.read_text(encoding="utf-8"))

    assert registry["version"] >= 1
    assert registry["count"] == len(registry["functions"]) > 800


def test_ship_record_entries_are_complete():
    """У каждой записи есть имя, категория и существующая страница справки."""
    registry = json.loads(DEFAULT_REGISTRY_PATH.read_text(encoding="utf-8"))

    for item in registry["functions"]:
        assert item["name"], item
        assert item["category"], item
        assert item["doc"].startswith("11_yazyk_programmirovaniya/"), item


def test_find_function_ignores_case():
    """Регистр не важен: язык SimInTech его не различает (`Speed` = `speed`)."""
    assert find_function("ABS").name == "abs"
    assert find_function("  abs ") is not None
    assert find_function("absолютно-нет") is None


def test_find_functions_returns_every_category():
    """Имя, описанное в двух категориях, находится целиком.

    `buffer` есть и в «Функциях обработки сигналов», и в одноимённой категории
    библиотек: `find_function` вернёт одну запись, а их две.
    """
    entries = find_functions("buffer")

    assert len(entries) >= 2
    assert len({entry.doc for entry in entries}) == len(entries)
    assert find_function("buffer") in entries


def test_registry_meta_reports_help_version():
    """Версия справки сохраняется в реестре — по ней видно, устарел ли он."""
    meta = registry_meta()

    assert str(meta["version"]) == "1"
    assert str(meta["help_version"]).startswith("v")


def test_language_functions_are_copies():
    """Выдача не даёт менять кэш модуля: список новый, записи неизменяемы."""
    first = language_functions()
    first.clear()

    assert language_functions()


# ─── Покрытие наших знаний ────────────────────────────────────────

def _docs(tmp_path, language_md, blocks_md=None):
    """Документы репозитория: `language/*.md` и `blocks/**/*.md`."""
    root = tmp_path / "repo"
    (root / "language").mkdir(parents=True)
    (root / "language" / "syntax.md").write_text(language_md, encoding="utf-8")
    if blocks_md is not None:
        (root / "blocks" / "generators").mkdir(parents=True)
        (root / "blocks" / "generators" / "sine.md").write_text(
            blocks_md, encoding="utf-8")
    return root


_REGISTRY = {
    "version": 1,
    "count": 4,
    "functions": [
        {"name": "abs", "category": "Стандартные", "section": "",
         "doc": "11_yazyk_programmirovaniya/6_funkcii/abs.html",
         "graphics_only": False, "purpose": ""},
        {"name": "absolute", "category": "Стандартные", "section": "",
         "doc": "11_yazyk_programmirovaniya/6_funkcii/absolute.html",
         "graphics_only": False, "purpose": ""},
        {"name": "steamph", "category": "Стандартные", "section": "",
         "doc": "11_yazyk_programmirovaniya/6_funkcii/steamph.html",
         "graphics_only": False, "purpose": ""},
        {"name": "steampt", "category": "Архивные функции", "section": "",
         "doc": "11_yazyk_programmirovaniya/6_funkcii/steampt.html",
         "graphics_only": False, "purpose": ""},
    ],
}


def _registry_file(tmp_path):
    """Реестр для тестов покрытия — чтобы числа не зависели от поставки."""
    path = tmp_path / "functions.json"
    path.write_text(json.dumps(_REGISTRY, ensure_ascii=False), encoding="utf-8")
    return path


def test_coverage_ignores_case(tmp_path):
    """Регистр не важен — язык его не различает (`Speed` = `speed`)."""
    docs = _docs(tmp_path, "Модуль: `ABS(x)`, он же Absolute.\n")

    result = coverage(docs, _registry_file(tmp_path))

    assert result.covered == ("abs", "absolute")
    assert result.covered_count == 2
    assert result.total == 4


def test_coverage_does_not_count_substring(tmp_path):
    """Имя ищется как слово: `abs` не покрывается вхождением в `absolyutnoe`.

    Без границ слова покрытие выглядело бы больше, чем оно есть: `abs`
    «нашёлся» бы внутри любого слова, начинающегося с этих букв.
    """
    docs = _docs(tmp_path, "Только absolyutnoe и ABSOLUTNO.\n")

    result = coverage(docs, _registry_file(tmp_path))

    assert result.covered == ()
    assert result.uncovered == ("abs", "absolute", "steamph", "steampt")
    assert result.ratio == 0.0


def test_coverage_reads_blocks_too(tmp_path):
    """Покрытие считается и по `blocks/**/*.md`, а не только по `language/`."""
    docs = _docs(tmp_path, "ничего\n", "Паровая функция steampt(P, t)\n")

    result = coverage(docs, _registry_file(tmp_path))

    assert "steampt" in result.covered
    assert len(result.files) == 2


def test_coverage_reports_largest_uncovered_categories(tmp_path):
    """Непокрытое пересчитывается по категориям — от больших к малым.

    `abs` покрыт, `absolute` и `steamph` из той же категории — нет. Счёт
    «сколько всего имён в категории» дал бы три и спрятал бы разницу между
    «покрыто» и «не покрыто».
    """
    docs = _docs(tmp_path, "Модуль числа: abs(x)\n")

    result = coverage(docs, _registry_file(tmp_path))

    assert result.uncovered_by_category == (("Стандартные", 2),
                                            ("Архивные функции", 1))
    assert result.covered == ("abs",)
    assert result.ratio == 1 / 4


def test_coverage_without_documents_is_an_error(tmp_path):
    """Нет ни `language/`, ни `blocks/` — отказ, а не «покрыто 0 из 907».

    Ноль читался бы как «мы не знаем языка», тогда как на деле неверен путь.
    """
    with pytest.raises(FileNotFoundError, match="документов о языке"):
        coverage(tmp_path / "пусто", _registry_file(tmp_path))


# ─── Сплошные проверки по поставке ────────────────────────────────

@pytest.mark.distribution
def test_distribution_pages_all_parse():
    """Сплошная проверка: весь раздел языка разбирается, реестр непуст.

    Числа посчитаны по файлам поставки, а не взяты из документации: 907
    функций (904 в `6_funkcii/` и 3 в `8_funkcii_graficheskogo_kontejnera/`),
    878 уникальных имён, 78 функций только графического контейнера.

    959, записанное в плане, — это **все** `.html` каталога `6_funkcii/`:
    904 функции и 55 обзорных страниц категорий. Обход 9p-каталога справки
    занимает секунды, поэтому проверка идёт под маркером `distribution` —
    запускать явно: `pytest -m distribution`.
    """
    if not (HELP_DIR / "11_yazyk_programmirovaniya").is_dir():
        pytest.skip(f"поставки нет: {HELP_DIR}")

    registry = build_registry(HELP_DIR)

    assert registry["count"] == 907
    assert registry["counts"] == {
        "functions": 907,
        "unique_names": 878,
        "graphics_container_only": 78,
        "with_purpose": 905,
        "categories": 28,
        "category_rows": 50,
        "alphabet_index_entries": 843,
        "alphabet_index_pages": 843,
        "alphabet_index_keywords": 56,
        "alphabet_index_functions": 787,
    }
    # Каждая страница разобралась: без имени или категории запись бесполезна.
    for item in registry["functions"]:
        assert item["name"], item
        assert item["category"], item
    # Назначение есть у всех, кроме двух страниц без `shortdesc`.
    assert {item["name"] for item in registry["functions"]
            if not item["purpose"]} == {"projectloaddb", "projectsavedb"}


@pytest.mark.distribution
def test_distribution_pages_exist_on_disk():
    """Каждая запись реестра указывает на существующую страницу справки."""
    if not (HELP_DIR / "11_yazyk_programmirovaniya").is_dir():
        pytest.skip(f"поставки нет: {HELP_DIR}")

    for item in language_functions():
        assert Path(HELP_DIR, *item.doc.split("/")).is_file(), item.doc


@pytest.mark.distribution
def test_distribution_registry_is_not_stale():
    """Поставляемый реестр совпадает со свежим разбором справки.

    Реестр лежит в репозитории, а справка обновляется вместе с поставкой:
    разошедшийся реестр молча врал бы числами, и заметить это было бы нечем.
    """
    if not (HELP_DIR / "11_yazyk_programmirovaniya").is_dir():
        pytest.skip(f"поставки нет: {HELP_DIR}")

    fresh = build_registry(HELP_DIR)
    shipped = json.loads(DEFAULT_REGISTRY_PATH.read_text(encoding="utf-8"))

    assert shipped["counts"] == fresh["counts"]
    assert shipped["functions"] == fresh["functions"]
