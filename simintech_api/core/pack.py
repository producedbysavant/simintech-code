"""Пакет проектов SimInTech (`.pak`)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List

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

    def _call(self, method: str, *args: Any) -> Any:
        """COM-вызов с идентификатором пакета — и проверкой, что он открыт.

        Единственная точка, где id пакета попадает в COM. Проверка здесь
        делает `require_open` настоящим общим контрактом операций, а не
        утверждением в докстринге (ревью code#23), и не даёт подать в COM
        id ≤ 0 — неположительный id роняет `mmain.exe` (замер 01.10.2026).
        """
        self.require_open()
        return self._client.call(method, self._id, *args)

    def close(self) -> None:
        """Закрыть пакет.

        Идентификатор ≤ 0 не подаётся в COM (см. `require_open`), а после
        удачного закрытия он **обнуляется**: повторный `close` — отказ, а не
        второй `ClosePack` по тому же id — ровно та форма вызова, от которой
        защищает замер 01.10.2026 (ревью code#23).
        """
        self.require_open()
        self._client.close_pack(self._id)
        self._id = 0

    # ─── Состав ─────────────────────────────────────────────────────

    def project_count(self) -> int:
        """Сколько проектов в пакете."""
        return int(self._call("PackGetProjCount"))

    def project_ids(self) -> List[int]:
        """Идентификаторы проектов пакета по порядку."""
        count = self.project_count()
        return [int(self._call("PackGetProjectIdByIndex", i))
                for i in range(count)]

    # ─── Расчёт ─────────────────────────────────────────────────────

    def start(self) -> "Pack":
        """Инициализировать пакет."""
        self._call("PackStart")
        return self

    def run(self) -> "Pack":
        """Запустить расчёт пакета."""
        self._call("PackRun")
        return self

    def step(self) -> "Pack":
        """Один шаг расчёта пакета."""
        self._call("PackStep")
        return self

    def pause(self) -> "Pack":
        """Пауза."""
        self._call("PackPause")
        return self

    def stop(self) -> "Pack":
        """Остановить расчёт пакета."""
        self._call("PackStop")
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
        self._call("RunToPack", float(target_time))
        wait = self._call("WaitForTimePack", float(target_time))
        return int(wait) != 0

    def require_open(self) -> "Pack":
        """Проверить, что пакет открыт, и вернуть себя.

        Проверка `<= 0`, а не `не _id`: в COM идентификаторы пакета
        положительны, но у неоткрытого пакета `GetPackIdByFileName` возвращает
        `-1` (живой замер 01.10.2026), а `ClosePack(-1)` роняет `mmain.exe`
        (Access violation, там же). Ноль при этом тоже отвергается — им
        помечен «не открылся» у `OpenPack`.

        Raises:
            PackError: пакет закрыт или идентификатор недействителен
                (обнулён либо отрицателен).
        """
        if self._id <= 0:
            raise PackError(
                f"пакет закрыт или не был открыт (идентификатор {self._id})")
        return self

    def __repr__(self) -> str:  # pragma: no cover
        return f"Pack(id={self._id})"
