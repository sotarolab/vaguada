"""Journal and day summary (decision 0006).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-30
"""

from __future__ import annotations

from alembic import op
from camanchaca_demo.config import settings
from camanchaca_demo.store.tables import build_tables

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    t = build_tables(settings().db_schema)
    t.journal.create(op.get_bind(), checkfirst=True)
    t.day_summary.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    t = build_tables(settings().db_schema)
    t.day_summary.drop(op.get_bind(), checkfirst=True)
    t.journal.drop(op.get_bind(), checkfirst=True)
