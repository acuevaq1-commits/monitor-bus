from datetime import datetime
from src.infrastructure.database.repositories.source import runs


def search_runs(start: datetime, end: datetime, filters: dict, limit: int = 50, offset: int = 0):
    if end <= start:
        raise ValueError("El fin debe ser posterior al inicio")
    return runs.search(start, end, filters, limit, offset)
