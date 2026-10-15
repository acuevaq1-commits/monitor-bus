from typing import Protocol


class TemplateRepository(Protocol):
    def list(self, limit: int = 100) -> list[dict]: ...
