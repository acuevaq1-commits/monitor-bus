from functools import lru_cache
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.infrastructure.settings import get_settings


@lru_cache
def monitor_engine():
    url = get_settings().database_url
    return create_engine(url, pool_pre_ping=True, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})


@lru_cache
def source_engine():
    url = get_settings().source_database_url
    return create_engine(url, pool_pre_ping=True) if url else None


def monitor_session():
    with sessionmaker(monitor_engine())() as session:
        yield session
