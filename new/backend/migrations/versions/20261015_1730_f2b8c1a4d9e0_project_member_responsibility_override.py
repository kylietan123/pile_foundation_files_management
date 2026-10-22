"""project member responsibility override

Revision ID: f2b8c1a4d9e0
Revises: 40b8b18edab8
Create Date: 2026-10-15 17:30:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b8c1a4d9e0"
down_revision: Union[str, Sequence[str], None] = "40b8b18edab8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "project_member",
        sa.Column("responsibility_override", sa.String(length=300), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("project_member", "responsibility_override")
