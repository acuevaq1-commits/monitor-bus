from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="MONITOR_", extra="ignore")
    database_url: str = "sqlite:///./monitor.db"
    source_database_url: str | None = None
    session_secret: str = "development-only-change-me"
    admin_user: str = "admin"
    admin_password: str = ""
    environment: str = "Desarrollo"
    timezone: str = "America/Lima"
    inactivity_hours: int = 24


@lru_cache
def get_settings() -> Settings:
    return Settings()
