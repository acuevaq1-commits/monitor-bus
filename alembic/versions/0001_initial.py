"""Monitor-owned tables; source logging tables stay untouched."""
from alembic import op
from sqlalchemy import MetaData
from src.infrastructure.database.models.monitor import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    schema = Base.metadata.schema
    if schema:
        op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    Base.metadata.create_all(bind=op.get_bind())


def downgrade():
    Base.metadata.drop_all(bind=op.get_bind())
