import os

# Tests never use the PostgreSQL credentials from the developer's .env file.
os.environ["MONITOR_DATABASE_URL"] = "sqlite:///./monitor-test.sqlite3"
os.environ["MONITOR_SOURCE_DATABASE_URL"] = ""
os.environ["MONITOR_ADMIN_PASSWORD"] = "test-password"
os.environ["MONITOR_SESSION_SECRET"] = "test-secret"

from src.infrastructure.database.models.monitor import Base
from src.infrastructure.database.session import monitor_engine

Base.metadata.create_all(monitor_engine())
