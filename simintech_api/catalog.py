"""Каталог имён свойств блоков SimInTech.

В COM API **нет метода перечисления свойств блока** — ни `GetPropCount`, ни
`GetPropName`. Существуют только `GetBlockPropAsString(BlockId, PropName)` и
`SetBlockProp(BlockId, PropName, StrValue)`, которым имя нужно знать заранее.
Поэтому имена свойств хранятся отдельно — в этом каталоге.

Два источника каталога:

* ``generate_catalog()`` — создать по блоку каждого класса в реальном SimInTech,
  экспортировать проект в ``.xprt`` и вычитать фактические имена свойств
  (только Windows). Это достоверный источник.
* ``data/block_catalog.json`` — засеянный каталог, собранный из рабочего кода
  примеров. Может быть неполным.

**Имена свойств короткие** — ``a``, ``y0``, ``k``, а не читаемые ``value``,
``signs``, ``numInputs``. Справочник блоков (``blocks/`` в корне репозитория)
использует читаемые имена, которые с реальными **не совпадают**; опираться на
него как на источник имён нельзя.

**Почему ошибка в каталоге опасна.** `SetBlockProp` не отвергает неизвестное
имя свойства: параметр «устанавливается», ошибки не возникает, а расчёт идёт
по прежнему значению. Отказ молчаливый — модель считается неверно, и это
не видно по коду возврата. Поэтому каталог следует генерировать, а не
дописывать вручную.
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import (TYPE_CHECKING, Dict, Iterable, Iterator, List, Optional,
                    Tuple, TypedDict)

from .constants import SUPPORTED_COM_BLOCK_CLASSES
from .exceptions import SimInTechError

if TYPE_CHECKING:
    from .core.com_client import COMClient
    from .core.project import Project

# ─── Расположение каталога ────────────────────────────────────────

DATA_DIR = Path(__file__).parent / "data"
DEFAULT_CATALOG_PATH = DATA_DIR / "block_catalog.json"

# Свойства, присутствующие у любого блока
COMMON_PROPS = ("Name",)

CATALOG_VERSION = 1


# ─── Каталог ──────────────────────────────────────────────────────

class BlockCatalog:
    """Соответствие «класс блока → имена его свойств».

    Args:
        classes: {класс: {свойство: значение по умолчанию}}.
        common: свойства, общие для всех классов.
        meta: произвольные метаданные (источник, дата, версия).
    """

    def __init__(self, classes: Optional[Dict[str, Dict[str, str]]] = None,
                 common: Iterable[str] = COMMON_PROPS,
                 meta: Optional[Dict[str, object]] = None,
                 readonly: Optional[Dict[str, Iterable[str]]] = None):
        self._classes: Dict[str, Dict[str, str]] = dict(classes or {})
        self._common: Tuple[str, ...] = tuple(common)
        self._readonly: Dict[str, List[str]] = {
            cls: list(props) for cls, props in (readonly or {}).items()
        }
        self.meta: Dict[str, object] = dict(meta or {})

    # ─── Загрузка / сохранение ──────────────────────────────────────

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "BlockCatalog":
        """Загрузить каталог из JSON. Отсутствующий файл → пустой каталог."""
        target = Path(path) if path else DEFAULT_CATALOG_PATH
        if not target.exists():
            return cls(meta={"source": "empty", "path": str(target)})
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SimInTechError(
                f"Не удалось прочитать каталог блоков {target}: {exc}") from exc
        return cls(
            classes=raw.get("classes", {}),
            common=raw.get("common", COMMON_PROPS),
            meta=raw.get("meta", {}),
            readonly=raw.get("readonly", {}),
        )

    def save(self, path: Optional[Path] = None) -> Path:
        """Сохранить каталог в JSON и вернуть путь."""
        target = Path(path) if path else DEFAULT_CATALOG_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.as_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return target

    def as_dict(self) -> Dict[str, object]:
        """Представление для сериализации."""
        return {
            "version": CATALOG_VERSION,
            "common": list(self._common),
            "classes": self._classes,
            "readonly": self._readonly,
            "meta": self.meta,
        }

    # ─── Доступ ─────────────────────────────────────────────────────

    def classes(self) -> List[str]:
        """Классы, для которых известны свойства."""
        return sorted(self._classes)

    def has(self, class_name: str) -> bool:
        """Известен ли класс."""
        return class_name in self._classes

    def props_for(self, class_name: str) -> List[str]:
        """Известные имена свойств класса (общие + специфичные).

        Для неизвестного класса — только общие свойства. Дубликаты
        устраняются: каталог может явно перечислять и общее свойство.
        """
        specific = self._classes.get(class_name) or {}
        seen = set()
        result: List[str] = []
        for prop in (*self._common, *specific):
            if prop not in seen:
                seen.add(prop)
                result.append(prop)
        return result

    def defaults_for(self, class_name: str) -> Dict[str, str]:
        """Значения по умолчанию для свойств класса."""
        return dict(self._classes.get(class_name, {}))

    def readonly_for(self, class_name: str) -> List[str]:
        """Вычисляемые параметры класса — читать можно, задавать нельзя."""
        return list(self._readonly.get(class_name, ()))

    def is_readonly(self, class_name: str, prop: str) -> bool:
        """True, если параметр вычисляемый (запись в него ни на что не влияет)."""
        return prop in self._readonly.get(class_name, ())

    def __len__(self) -> int:
        return len(self._classes)

    def __repr__(self) -> str:  # pragma: no cover
        return f"BlockCatalog(classes={len(self._classes)})"


# ─── Разбор .xprt ─────────────────────────────────────────────────

# Элементы в .xprt двух видов: `<object>` в современных выгрузках и
# `<object_0>`, `<object_1>`, ... (с номером) в старых, где нумеруется всё
# содержимое контейнера. Обе формы встречаются в поставке, поэтому обе и
# принимаются; то же для `<data>` и `<data_N>`.
_OBJECT_RE = re.compile(
    r"<(?P<tag>object(?:_\d+)?)>(?P<body>.*?)</(?P=tag)>", re.S | re.I)
_CLASS_RE = re.compile(r"<class_name>(.*?)</class_name>", re.S | re.I)
_CUSTOM_RE = re.compile(r"<custom_props>(.*?)</custom_props>", re.S | re.I)
_DATA_RE = re.compile(
    r"<(?P<tag>data(?:_\d+)?)>(?P<body>.*?)</(?P=tag)>", re.S | re.I)
# Кавычки вокруг значений — тоже двух конвенций: бэктики в новых выгрузках,
# одинарные кавычки в старых. Принимаются обе; внутренние кавычки не трогаются.
_NAME_RE = re.compile(r"<name>\s*[`']?([^`<]*)[`']?\s*</name>", re.I)
_VALUE_RE = re.compile(r"<value>\s*[`']?([^`<]*)[`']?\s*</value>", re.I)
_MODE_RE = re.compile(r"<mode>\s*[`']?(\d+)[`']?\s*</mode>", re.I)

# Режим параметра (mode) в <custom_props>: 1 — задаваемый, 0 — вычисляемый.
MODE_EDITABLE = 1
MODE_COMPUTED = 0

# Классы-оформление: не блоки, свойств-параметров не несут

# Классы-оформление: не блоки, свойств-параметров не несут
NON_BLOCK_CLASSES = {
    "Wire", "Arc", "Button", "FillCircle", "FillEllipseSector", "FillRect",
    "Line", "Point", "PolyLine", "PolyRound", "Polygon", "Rectangle",
    "RotatedText", "TextLabel", "constLabel", "Комментарий",
}


def clean_value(text: Optional[str]) -> str:
    """Убрать кавычки и пробелы по краям значения из .xprt.

    Кавычки двух конвенций: новые выгрузки оборачивают значения в бэктики,
    старые — в одинарные кавычки, и то и другое есть в одной поставке. Снимаются
    только края, поэтому апостроф внутри значения («`don’t`») сохраняется.

    Раньше снимались только бэктики, и на старом файле параметр ``SortType``
    превращался в ``'SortType'`` — с кавычками внутри имени.
    """
    if not text:
        return ""
    return text.strip().strip("`'").strip()


def _iter_custom_props(obj: str) -> Iterator[Tuple[str, str, Optional[int]]]:
    """Пройти по параметрам расчёта блока (секция ``<custom_props>``).

    Возвращает ``(имя, значение, mode)`` для каждой записи.

    Параметры блока лежат именно в ``<custom_props>``. Секция
    ``<visual_props>`` содержит **оформление** (``Color``, ``Points``,
    ``LabelFont``, ...) — параметров расчёта там нет. Проверено на реальном
    ``.xprt`` (SimInTech64, 2026-09-10).
    """
    custom_match = _CUSTOM_RE.search(obj)
    if not custom_match:
        return
    for data in (m.group("body")
                 for m in _DATA_RE.finditer(custom_match.group(1))):
        name_match = _NAME_RE.search(data)
        if not name_match:
            continue
        prop = clean_value(name_match.group(1))
        if not prop:
            continue
        value_match = _VALUE_RE.search(data)
        value = clean_value(value_match.group(1)) if value_match else ""
        mode_match = _MODE_RE.search(data)
        mode = int(mode_match.group(1)) if mode_match else None
        yield prop, value, mode


def parse_xprt_block_props(xml_text: str) -> Dict[str, Dict[str, str]]:
    """Извлечь ``{класс: {параметр: значение}}`` из XML-проекта (.xprt).

    Возвращаются **только параметры расчёта** — из секции ``<custom_props>``.
    Оформление (``<visual_props>``: ``Color``, ``Points``, ``LabelFont``, ...)
    в каталог не попадает.

    Блоки без ``<custom_props>`` пропускаются — параметров у них нет
    (так выглядят графические объекты: ``Line``, ``PolyLine``, ``Arc``, ...).
    """
    result: Dict[str, Dict[str, str]] = {}

    for obj in (m.group("body") for m in _OBJECT_RE.finditer(xml_text)):
        cls_match = _CLASS_RE.search(obj)
        if not cls_match:
            continue
        class_name = clean_value(cls_match.group(1))
        if not class_name or class_name in NON_BLOCK_CLASSES:
            continue
        if not _CUSTOM_RE.search(obj):
            continue

        props = result.setdefault(class_name, {})
        for prop, value, _mode in _iter_custom_props(obj):
            props.setdefault(prop, value)

    return result


def parse_xprt_readonly(xml_text: str) -> Dict[str, List[str]]:
    """Извлечь ``{класс: [вычисляемые параметры]}`` из XML-проекта.

    Вычисляемые параметры (``mode 0``: например ``xdif``, ``fdif`` у
    «Интегратора») читаются, но не задаются. Их важно знать: запись в такой
    параметр не даёт ошибки и ни на что не влияет — отказ молчаливый.
    """
    result: Dict[str, List[str]] = {}

    for obj in (m.group("body") for m in _OBJECT_RE.finditer(xml_text)):
        cls_match = _CLASS_RE.search(obj)
        if not cls_match:
            continue
        class_name = clean_value(cls_match.group(1))
        if not class_name or class_name in NON_BLOCK_CLASSES:
            continue
        if not _CUSTOM_RE.search(obj):
            continue

        readonly = result.setdefault(class_name, [])
        for prop, _value, mode in _iter_custom_props(obj):
            if mode == MODE_COMPUTED and prop not in readonly:
                readonly.append(prop)

    return result


# ─── Генерация из реального SimInTech ─────────────────────────────

#: BOM UTF-8 — им SimInTech помечает свои экспорты.
_UTF8_BOM = b"\xef\xbb\xbf"


def decode_xprt(raw: bytes) -> str:
    """Декодировать байты .xprt в текст.

    SimInTech пишет `.xprt` в **UTF-8 с BOM** (проверено на настоящих
    экспортах: BOM `EF BB BF` и объявление `encoding="utf-8"` в самом XML), а не
    в cp1251. Чтение как cp1251 превращает русские имена классов в мусор —
    молча, без ошибки, потому что cp1251 декодирует любые байты.

    BOM решает: если он есть — декодируем **строго** UTF-8 и не прячем порчу
    файла за запасной кодировкой. Иначе один испорченный байт давал бы mojibake
    (`Усилитель` → `РЈСЃРёР»РёС‚РµР»СЊ`) вместо ошибки — то есть ровно тот
    молчаливый дефект, ради которого кодировка и выбирается по содержимому.
    cp1251 остаётся запасным для файлов **без** BOM — так писали старые версии.
    """
    if raw.startswith(_UTF8_BOM):
        return raw.decode("utf-8-sig")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode("cp1251")
    except UnicodeDecodeError as exc:                       # pragma: no cover
        # cp1251 не бросает ни на одном байте, поэтому сюда попасть нельзя.
        # Ветка — явный отказ вместо тихой подстановки U+FFFD: иначе о неудаче
        # декодирования никто не узнал бы.
        raise SimInTechError(
            f"Не удалось определить кодировку .xprt: файл не UTF-8 и не cp1251 "
            f"({exc})"
        ) from exc


def export_xprt_text(project: "Project", suffix: str = ".xprt") -> str:
    """Экспортировать проект в XML и вернуть текст."""
    tmp = Path(tempfile.gettempdir()) / f"siminapi_catalog_{project.id}{suffix}"
    try:
        project.save_xml(str(tmp))
        return decode_xprt(tmp.read_bytes())
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def generate_catalog(client: "COMClient",
                     classes: Optional[Iterable[str]] = None,
                     keep_project: bool = False,
                     dump_path: Optional[Path] = None) -> BlockCatalog:
    """Построить каталог по реальному SimInTech (только Windows).

    Создаёт по одному блоку каждого класса в новом проекте, экспортирует
    проект в ``.xprt`` и вычитывает фактические имена свойств. Классы, которые
    не удалось создать, пропускаются — их отсутствие видно в ``meta["failed"]``.

    Args:
        client: подключённый COM-клиент.
        classes: классы для обхода (по умолчанию — SUPPORTED_COM_BLOCK_CLASSES).
        keep_project: не закрывать проект (для отладки).
    """
    from .core.project import Project

    targets = list(classes or sorted(SUPPORTED_COM_BLOCK_CLASSES))
    project = Project.new(client)
    failed: List[str] = []
    try:
        page = project.get_main_page()
        for index, class_name in enumerate(targets):
            try:
                block = page.create_block(class_name, 0.0, float(index * 60))
                block.set_name(f"catalog_{index}")
            except Exception:
                failed.append(class_name)
        xml_text = export_xprt_text(project)
        if dump_path is not None:
            # Снятие выгрузки — долгая часть и единственная, которой нужен
            # Windows; сохранив её, каталог можно пересобрать где угодно.
            dump_path.write_text(xml_text, encoding="utf-8")
    finally:
        if not keep_project:
            try:
                project.close()
            except Exception:
                pass

    return build_catalog_from_xprt(xml_text, targets=targets, failed=failed)


#: Значение параметра по умолчанию в каталоге — справочное: нужны имена, а не
#: значения. У антенных решёток значение — матрица в сотни чисел, и тащить её
#: в файл нечего.
MAX_DEFAULT_LEN = 120


def _short_default(value: str) -> str:
    """Значение по умолчанию для каталога: длинные не сохраняются."""
    return value if len(value) <= MAX_DEFAULT_LEN else ""


def build_catalog_from_xprt(
        xml_text: str,
        targets: Optional[Iterable[str]] = None,
        failed: Optional[Iterable[str]] = None) -> BlockCatalog:
    """Собрать каталог из готовой выгрузки `.xprt` — **без COM**.

    Отделено от `generate_catalog`: снять выгрузку проекта с блоками всех
    классов долго и можно только на Windows, а разобрать её — где угодно,
    включая Linux. Благодаря этому каталог пересобирается из сохранённого
    файла и проверяется тестами без SimInTech.

    Args:
        xml_text: текст `.xprt`.
        targets: какие классы оставить; None — все найденные в выгрузке.
        failed: классы, которые среда создать не смогла (попадают в `meta`).
    """
    parsed = parse_xprt_block_props(xml_text)
    readonly = parse_xprt_readonly(xml_text)
    # В XML попадает и оформление, поэтому оставляем только запрошенные классы.
    # Имена из индекса библиотек приходят с хвостовыми пробелами («Миландр -
    # MILS - Инициализация МКИО »), а разбор выгрузки их обрезает — поэтому
    # сверка идёт по обрезанным именам. Без этого классы с пробелом в записи
    # молча выпадали бы из каталога, хотя среда их создаёт.
    wanted = {clean_value(name) for name in targets} if targets is not None \
        else set(parsed)
    classes_map = {k: {name: _short_default(value)
                       for name, value in params.items()}
                   for k, params in parsed.items() if k in wanted}
    readonly_map: Dict[str, Iterable[str]] = {
        k: v for k, v in readonly.items() if k in wanted}
    return BlockCatalog(
        classes=classes_map,
        readonly=readonly_map,
        meta={
            "source": "generated",
            "requested": sorted(wanted),
            "failed": sorted(clean_value(name) for name in (failed or ())),
        },
    )


def merge_catalogs(catalogs: Iterable[BlockCatalog]) -> BlockCatalog:
    """Слить каталоги в один: классы и их параметры объединяются.

    За один прогон охватить всё не выходит, и это свойство среды, а не
    недоделка: библиотечные записи берутся из индекса `.csl`, а базовый слой
    («Константа», «Ступенька», «Производная», ...) в индексе не значится — он
    подключается слоем `.lf` и известен только самому движку. Уже найденные
    параметры при слиянии не теряются: классы объединяются по имени.
    """
    classes: Dict[str, Dict[str, str]] = {}
    readonly: Dict[str, List[str]] = {}
    # `Dict` инвариантен по значению: `dict[str, list[str]]` не подходит там,
    # где объявлен `Dict[str, Iterable[str]]`, поэтому тип задаётся явно.
    readonly_map: Dict[str, Iterable[str]] = {}
    requested: List[str] = []
    failed: List[str] = []
    source = "generated"
    for catalog in catalogs:
        for class_name in catalog.classes():
            classes.setdefault(class_name, {}).update(
                catalog.defaults_for(class_name))
            found = readonly.setdefault(class_name, [])
            for prop in catalog.readonly_for(class_name):
                if prop not in found:
                    found.append(prop)
        asked = catalog.meta.get("requested")
        if isinstance(asked, list):
            requested.extend(str(name) for name in asked)
        missed = catalog.meta.get("failed")
        if isinstance(missed, list):
            failed.extend(str(name) for name in missed)
        source = str(catalog.meta.get("source") or source)
    readonly_map.update(readonly)
    # Класс, который в итоге попал в каталог, создать удалось — значит в списке
    # провалов он числиться не может. Это не косметика: провал, оставшийся
    # после того, как класс найден (например, при досборке через `--merge`),
    # искажает и счётчики покрытия, и вывод «среда не умеет создавать».
    still_failed = sorted({clean_value(name) for name in failed}
                          - set(classes))
    return BlockCatalog(
        classes=classes,
        readonly=readonly_map,
        meta={
            "source": source,
            "requested": sorted(set(requested)),
            "failed": still_failed,
        },
    )


# ─── Кэш каталога по умолчанию ────────────────────────────────────

_default_cache: Optional[BlockCatalog] = None


def load_default_catalog(reload: bool = False) -> BlockCatalog:
    """Каталог по умолчанию (кэшируется в памяти)."""
    global _default_cache
    if _default_cache is None or reload:
        _default_cache = BlockCatalog.load()
    return _default_cache


# ─── Покрытие: доля классов, для которых имена проверяются ─────────


class CoverageReport(TypedDict):
    """Отчёт о покрытии каталога (см. :func:`catalog_coverage`)."""
    libraries_total: int
    records_total: int
    records_without_paramset: int
    libraries_in_profile: Optional[int]
    classes_in_profile: int
    catalog_classes: int
    checked_classes: int
    fraction: float
    not_in_catalog: List[str]
    beyond_profile: List[str]


def catalog_coverage(catalog: BlockCatalog, bin_dir: Path,
                     profile: Optional[Path] = None) -> CoverageReport:
    """Измерить, для какой доли классов имена параметров вообще проверяются.

    Защита от опечатки в имени параметра работает только там, где класс есть
    в каталоге: иначе `_check_params` уходит в ветку «класса нет» и пропускает
    запись (`SetBlockProp` неизвестное имя не отвергает). Поэтому «сколько
    классов под проверкой» — не отчётная цифра, а свойство защиты, и его нужно
    уметь измерять, а не оценивать.

    Знаменатель — классы, которые грузит профиль: файл библиотеки на диске ещё
    не значит загруженную библиотеку, а класс из незагруженной библиотеки
    пользователь на схему не поставит.

    Args:
        catalog: проверяемый каталог.
        bin_dir: каталог поставки с библиотеками `.csl`.
        profile: `base.xml` профиля; без него берутся все библиотеки на диске.

    Returns:
        Числа и два списка имён: `not_in_catalog` (классы профиля без проверки)
        и `beyond_profile` (классы каталога вне профиля — например, из
        `SUPPORTED_COM_BLOCK_CLASSES`; они проверяются, но в знаменатель не
        входят).
    """
    from .csl_library import (PARAMSET_DIR, class_names, libraries_in_profile,
                              load_libraries, missing_paramsets)

    libraries = load_libraries(bin_dir)
    in_profile = libraries_in_profile(profile) if profile else None
    # Имена записей приходят из индекса `.csl` как есть, а в каталоге лежат
    # обрезанные (см. `build_catalog_from_xprt`). Сверять их без нормализации
    # нельзя: класс с хвостовым пробелом в записи («Миландр - MILS - …МКИО »)
    # выглядел бы непроверяемым, хотя в каталоге он есть.
    names = {clean_value(name) for name in class_names(bin_dir, in_profile)}
    catalog_classes = set(catalog.classes())
    checked = names & catalog_classes

    return {
        "libraries_total": len(libraries),
        "records_total": sum(len(lib.records) for lib in libraries),
        "records_without_paramset": len(
            missing_paramsets(bin_dir / PARAMSET_DIR, libraries)),
        "libraries_in_profile": None if in_profile is None else len(in_profile),
        "classes_in_profile": len(names),
        "catalog_classes": len(catalog_classes),
        "checked_classes": len(checked),
        "fraction": round(len(checked) / len(names), 4) if names else 0.0,
        "not_in_catalog": sorted(names - catalog_classes),
        "beyond_profile": sorted(catalog_classes - names),
    }
