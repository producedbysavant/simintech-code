"""Живой тест: пакет, собранный писателем, открывается средой (OpenPack).

Самодостаточно: два проекта создаются из шаблона и сохраняются нативным
`.prt` рядом с будущим `.pak` (голые имена в `[Files]` — штатный режим, так
пишет и сама среда), затем `write_pack` кладёт пакет, а среда его открывает.
Проверка — состав, прочитанный **средой**, а не своим разборщиком.

Уборка — своя, а не на процесс: созданные из шаблона проекты закрываются, а
каталог даёт `tmp_path`. Иначе повторные прогоны копили бы в `mmain.exe`
открытые проекты (замечание ревью 01.10.2026: закрывался только пакет, а
каталог `pack-writer-*` в `%TEMP%` оставался на диске).

Процесс принадлежит фикстуре `client` (tests/conftest.py): чужой `mmain.exe`
не трогается.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest

pytestmark = pytest.mark.integration


def test_written_pack_opens_in_simintech(client, tmp_path):
    """Текст, собранный `write_pack`, среда принимает: OpenPack и состав."""
    from simintech_api import Pack, Project
    from simintech_api.pak import write_pack

    workdir = str(tmp_path)
    created = [Project.from_template(client) for _ in range(2)]
    try:
        for project, name in zip(created, ("alpha.prt", "beta.prt")):
            project.save_binary(os.path.join(workdir, name))
        target = os.path.join(workdir, "Сборка.pak")

        written = write_pack(target, ["alpha.prt", "beta.prt"])
        assert written.problems == ()

        pack_id = client.open_pack(target)
        assert pack_id > 0, "среда не открыла пакет, собранный текстом"
        opened = Pack(client, pack_id)
        try:
            assert opened.project_count() == 2
            assert len(opened.project_ids()) == 2
        finally:
            opened.close()
    finally:
        for project in created:
            project.close()
