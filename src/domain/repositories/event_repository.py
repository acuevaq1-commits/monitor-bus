from datetime import datetime
from typing import Protocol


class EventRepository(Protocol):
    def search(self, start: datetime, end: datetime, filters: dict, limit: int, offset: int) -> tuple[list[dict], int]: ...
