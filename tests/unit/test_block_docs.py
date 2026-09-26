"""Сверка таблиц «Параметры» в `blocks/**/*.md` с каталогом имён свойств.

Дрейф имён в документации случался дважды (`y0` у «Константы» вместо `a`,
`xn` у «Сумматора»), и оба раза проходил незамеченным. Цена ошибки высока:
`SetBlockProp` неизвестное имя **не отвергает** — запись уходит в никуда
молча, модель считается с дефолтным значением, и признака отказа нет.

Правило то же, что и в MCP-слое: источник истины — каталог
`simintech_api/data/block_catalog.json`. Имена в таблице «Параметры» обязаны
ему принадлежать. Исключение одно: если раздел прямо предупреждает (знак
«⚠»), что имена взяты из справки и работой через COM не подтверждены, —
таблица не проверяется. Это осознанная конвенция репозитория, а не пропуск
(см. `blocks/generators/sine.md`, `blocks/converters/transfer-function.md`).
"""

import os
import pathlib
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest  # noqa: E402

from simintech_api.catalog import load_default_catalog  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
BLOCKS_DIR = REPO_ROOT / "blocks"

# Заголовок файла: `# Блок «Константа» (Constant)`
TITLE_RE = re.compile(r"^#\s+Блок\s+«(?P<cls>[^»]+)»", re.MULTILINE)

# Знак предупреждения: имена не подтверждены
UNVERIFIED_MARKER = "⚠"

# Идентификаторы из «blocks/…» (первая колонка markdown-таблицы), для которых
# первая колонка — не имя параметра, а служебное слово
_NOT_PARAMETER = {"Параметр", "Формат"}


def _params_section(text: str) -> str:
    """Текст раздела «## Параметры» — до следующего заголовка «## »."""
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip() == "## Параметры":
            start = index + 1
            break
    if start is None:
        return ""
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return "\n".join(lines[start:end])


def _table_names(section: str) -> "list[str]":
    """Имена из первой колонки markdown-таблиц раздела."""
    names = []
    for line in section.splitlines():
        row = line.strip()
        if not row.startswith("|"):
            continue
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        first = cells[0] if cells else ""
        # Разделитель таблицы (`|---|---|`)
        if not first or set(first) <= set("-: "):
            continue
        first = first.strip("`")
        if first in _NOT_PARAMETER:
            continue
        names.append(first)
    return names


def _block_docs() -> "list[pathlib.Path]":
    return sorted(BLOCKS_DIR.glob("**/*.md"))


@pytest.mark.parametrize(
    "path", _block_docs(), ids=lambda p: p.relative_to(REPO_ROOT).as_posix()
)
def test_block_param_tables_match_catalog(path: pathlib.Path) -> None:
    text = path.read_text(encoding="utf-8")
    title = TITLE_RE.search(text)
    assert title, f"{path}: нет заголовка вида «# Блок «Класс» (…)]»"
    class_name = title.group("cls")

    section = _params_section(text)
    assert section.strip(), f"{path}: нет раздела «## Параметры»"

    names = _table_names(section)
    if not names:
        # Таблицы нет: либо имён не существует, либо их не с чем сверить.
        # Тогда раздел обязан сказать об этом прямо — иначе отсутствие
        # списка читается как «параметров нет».
        assert UNVERIFIED_MARKER in section, (
            f"{path}: раздел «Параметры» без таблицы и без предупреждения "
            f"«{UNVERIFIED_MARKER}»: непонятно, есть ли у класса свойства"
        )
        return
    if UNVERIFIED_MARKER in section:
        # Имена взяты из справки и не подтверждены — конвенция репозитория
        # требует в этом случае именно предупреждения, а не сверки.
        return

    catalog = load_default_catalog()
    assert catalog.has(class_name), (
        f"{path}: класса «{class_name}» нет в каталоге, а таблица "
        f"«Параметры» перечисляет имена ({names}) как достоверные — "
        f"сверить их не с чем, поставьте «{UNVERIFIED_MARKER}»"
    )
    allowed = set(catalog.props_for(class_name))
    unknown = [name for name in names if name not in allowed]
    assert not unknown, (
        f"{path}: имена {unknown} не принадлежат классу «{class_name}». "
        f"Каталог знает {sorted(allowed)}. SetBlockProp неизвестное имя "
        f"не отвергает — запись уйдёт в никуда молча"
    )
