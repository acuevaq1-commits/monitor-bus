from datetime import datetime
from typing import Protocol


class RunRepository(Protocol):
    def search(self, start: datetime, end: datetime, filters: dict, limit: int, offset: int) -> tuple[list[dict], int]: ...
    def get(self, ts: datetime, run_id: str) -> dict | None: ...
