"""Пакет проектов SimInTech (`.pak`)."""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from ..exceptions import PackError

if TYPE_CHECKING:
    from .com_client import COMClient


class Pack:
    """Пакет проектов: несколько связанных проектов с общим модельным временем.

    Пакет считает несколько проектов вместе: модельное время у них общее (равно
    минимуму времён проектов), синхрошаг одинаков, а обмен идёт через общую базу
    сигналов. Состав (какие проекты в пакете) даёт `project_ids()`.

    Создаётся через `COMClient.open_pack`, а не напрямую.

    **Почему отдельный класс, а не методы `Simulation`.** Операции пакета
    адресуются идентификатором **пакета**, а `Simulation` привязан к проекту.
    Раньше `Simulation.pack_*` передавали в COM идентификатор проекта — то есть
    обращались не туда, и путь пакетов был недостижим: открыть пакет было нечем.
    Теперь эти методы отказывают, а работа с пакетом живёт здесь.
    """

    def __init__(self, client: "COMClient", pack_id: int):
        self._client = client
        self._id = pack_id

    @property
    def id(self) -> int:
        """Идентификатор пакета (PackId)."""
        return self._id

    @property
    def client(self) -> "COMClient":
        """Клиент, через который открыт пакет."""
        return self._client

    def close(self) -> None:
        """Закрыть пакет."""
        self._client.close_pack(self._id)

    # ─── Состав ─────────────────────────────────────────────────────

    def project_count(self) -> int:
        """Сколько проектов в пакете."""
        return int(self._client.call("PackGetProjCount", self._id))

    def project_ids(self) -> List[int]:
        """Идентификаторы проектов пакета по порядку."""
        count = self.project_count()
        return [int(self._client.call("PackGetProjectIdByIndex", self._id, i))
                for i in range(count)]

    # ─── Расчёт ─────────────────────────────────────────────────────

    def start(self) -> "Pack":
        """Инициализировать пакет."""
        self._client.call("PackStart", self._id)
        return self

    def run(self) -> "Pack":
        """Запустить расчёт пакета."""
        self._client.call("PackRun", self._id)
        return self

    def step(self) -> "Pack":
        """Один шаг расчёта пакета."""
        self._client.call("PackStep", self._id)
        return self

    def pause(self) -> "Pack":
        """Пауза."""
        self._client.call("PackPause", self._id)
        return self

    def stop(self) -> "Pack":
        """Остановить расчёт пакета."""
        self._client.call("PackStop", self._id)
        return self

    def run_to(self, target_time: float) -> bool:
        """Расчёт пакета до заданного времени; `True`, если время дошло.

        Возвращается результат `WaitForTimePack` **как есть**, а подтвердить
        достижение опросом нельзя: модельное время пакета отдельным методом не
        читается (у проекта это `GetProjectTime`, см. `Simulation.run_to`).
        Поэтому `False` здесь означает «не подтверждено», а не «не дошло»:
        опираться на этот `bool` как на доказательство нельзя, пока поведение
        не проверено на живом SimInTech.
        """
        self._client.call("RunToPack", self._id, float(target_time))
        wait = self._client.call("WaitForTimePack", self._id, float(target_time))
        return int(wait) != 0

    def require_open(self) -> "Pack":
        """Проверить, что пакет открыт, и вернуть себя.

        Raises:
            PackError: пакет уже закрыт (идентификатор обнулён).
        """
        if not self._id:
            raise PackError("пакет закрыт или не был открыт")
        return self

    def __repr__(self) -> str:  # pragma: no cover
        return f"Pack(id={self._id})"
