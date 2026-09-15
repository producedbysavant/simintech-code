"""Тесты создания проекта из шаблона и задания времени расчёта (без COM).

`NewProject` создаёт пустой проект: без моделирующего слоя и настроек расчёта,
поэтому он не считает. Рабочий путь — `OpenTemplate` по шаблону поставки
(«Схема модели общего вида.prt»), а конечное время расчёта задаётся свойством
`endtime` расчётного слоя через `SetLayerProp`. Проверено на SimInTech64
2026-09-15: проект из шаблона считает, `endtime` меняет момент остановки.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest  # noqa: E402

from simintech_api.constants import (  # noqa: E402
    CALC_LAYER, MODEL_TEMPLATE_NAME, find_model_template)
from simintech_api.core import project as project_module  # noqa: E402
from simintech_api.core.project import Project  # noqa: E402
from simintech_api.exceptions import ProjectError  # noqa: E402


class FakeClient:
    """Минимальный клиент: только то, что нужен Project."""

    def __init__(self, project_id=77, layer_handle=1234):
        self.calls = []
        self._project_id = project_id
        self._layer_handle = layer_handle

    def open_template(self, path):
        self.calls.append(("open_template", path))
        return self._project_id

    def set_layer_prop(self, project_id, layer_no, name, value):
        self.calls.append(("set_layer_prop", project_id, layer_no, name, value))
        return self._layer_handle

    def call(self, name, *args):
        self.calls.append((name, *args))
        return 0


# ─── find_model_template ───────────────────────────────────────────


def test_find_model_template_uses_env_file(monkeypatch, tmp_path):
    """SIMINTECH_TEMPLATE задаёт шаблон напрямую."""
    tpl = tmp_path / MODEL_TEMPLATE_NAME
    tpl.write_text("x", encoding="utf-8")
    monkeypatch.setenv("SIMINTECH_TEMPLATE", str(tpl))

    assert find_model_template() == str(tpl)


def test_find_model_template_explicit_broken_path_is_authoritative(
        monkeypatch, tmp_path):
    """Явно заданный, но несуществующий шаблон не подменяется умолчанием.

    Иначе опечатка в SIMINTECH_TEMPLATE молча привела бы к другому шаблону.
    """
    monkeypatch.setenv("SIMINTECH_TEMPLATE", str(tmp_path / "нет-такого.prt"))

    assert find_model_template() is None


def test_find_model_template_uses_root(monkeypatch, tmp_path):
    """SIMINTECH_PATH указывает корень установки."""
    monkeypatch.delenv("SIMINTECH_TEMPLATE", raising=False)
    tpl_dir = tmp_path / "bin" / "Template"
    tpl_dir.mkdir(parents=True)
    tpl = tpl_dir / MODEL_TEMPLATE_NAME
    tpl.write_text("x", encoding="utf-8")
    monkeypatch.setenv("SIMINTECH_PATH", str(tmp_path))

    assert find_model_template() == str(tpl)


# ─── Project.from_template ─────────────────────────────────────────


def test_from_template_explicit_path():
    """Явный путь передаётся в OpenTemplate без поиска."""
    client = FakeClient()
    prj = Project.from_template(client, template=r"C:\TPL\model.prt")

    assert prj.id == 77
    assert client.calls == [("open_template", r"C:\TPL\model.prt")]


def test_from_template_uses_finder(monkeypatch, tmp_path):
    """Без явного пути шаблон ищется через find_model_template."""
    tpl = tmp_path / MODEL_TEMPLATE_NAME
    tpl.write_text("x", encoding="utf-8")
    monkeypatch.setenv("SIMINTECH_TEMPLATE", str(tpl))

    client = FakeClient()
    Project.from_template(client)

    assert client.calls == [("open_template", str(tpl))]


def test_from_template_without_template_raises(monkeypatch):
    """Если шаблон не найден — понятная ошибка, а не нулевой проект."""
    monkeypatch.setattr(project_module, "find_model_template", lambda: None)

    with pytest.raises(ProjectError, match="Не найден шаблон"):
        Project.from_template(FakeClient())


def test_from_template_zero_id_raises():
    """OpenTemplate вернул 0 — проект не создан."""
    with pytest.raises(ProjectError, match="OpenTemplate"):
        Project.from_template(FakeClient(project_id=0), template=r"C:\TPL.prt")


# ─── set_calc_end_time ─────────────────────────────────────────────


def test_set_calc_end_time_sets_layer_property():
    """endtime уходит в расчётный слой как строка."""
    client = FakeClient()
    prj = Project(client, 42)
    prj.set_calc_end_time(2.5)

    assert client.calls == [("set_layer_prop", 42, CALC_LAYER, "endtime", 2.5)]


def test_set_calc_end_time_returns_self():
    """Метод возвращает проект — удобно для цепочки вызовов."""
    prj = Project(FakeClient(), 42)

    assert prj.set_calc_end_time(1.0) is prj


def test_set_calc_end_time_rejects_non_positive():
    """Нулевое/отрицательное время расчёта — ошибка вызывающего."""
    prj = Project(FakeClient(), 42)

    with pytest.raises(ValueError):
        prj.set_calc_end_time(0)


def test_set_calc_end_time_without_calc_layer_raises():
    """Слой не принял свойство (проект без расчётного слоя) — явная ошибка."""
    prj = Project(FakeClient(layer_handle=0), 42)

    with pytest.raises(ProjectError, match="расчётного слоя"):
        prj.set_calc_end_time(1.0)


# ─── Видимость формы проекта ───────────────────────────────────────


def test_show_form_sends_formshow():
    """show_form() шлёт FormShow именно текущему проекту.

    Без этого вызова в сохранённый файл уходит ``<visible>0</visible>`` —
    состояние окна из сессии без формы. COM такой проект открывает и считает,
    а GUI восстанавливает сохранённое состояние окна и окна модели не
    показывает: выглядит как «проект не открылся». Проверено на SimInTech64
    2026-09-15.
    """
    client = FakeClient(project_id=77)

    Project(client, 77).show_form()

    assert client.calls == [("FormShow", 77)]


def test_show_form_returns_self():
    """Метод возвращает проект — удобно для цепочки вызовов."""
    prj = Project(FakeClient(), 42)

    assert prj.show_form() is prj


# ─── Перерисовка редактора ─────────────────────────────────────────


def test_repaint_sends_repaiteditor():
    """repaint() шлёт RepaintEditor именно текущему проекту.

    Вызывать между перемещением блоков и трассировкой линий: без перерисовки
    SimInTech прокладывает провода по прежним прямоугольникам блоков и
    оставляет в геометрии точки вроде (-160,-1056). Проверено на SimInTech64
    2026-09-15.
    """
    client = FakeClient(project_id=77)

    Project(client, 77).repaint()

    assert client.calls == [("RepaintEditor", 77)]


def test_repaint_returns_self():
    """Метод возвращает проект — удобно для цепочки вызовов."""
    prj = Project(FakeClient(), 42)

    assert prj.repaint() is prj
