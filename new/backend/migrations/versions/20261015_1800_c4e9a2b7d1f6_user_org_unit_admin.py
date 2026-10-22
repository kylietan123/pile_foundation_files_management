"""user org unit admin

Revision ID: c4e9a2b7d1f6
Revises: f2b8c1a4d9e0
Create Date: 2026-10-15 18:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4e9a2b7d1f6"
down_revision: Union[str, Sequence[str], None] = "f2b8c1a4d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_org",
        sa.Column("is_unit_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("user_org", "is_unit_admin")
