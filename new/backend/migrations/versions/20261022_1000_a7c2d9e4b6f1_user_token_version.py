"""user token version

Revision ID: a7c2d9e4b6f1
Revises: c4e9a2b7d1f6
Create Date: 2026-10-22 10:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7c2d9e4b6f1"
down_revision: Union[str, Sequence[str], None] = "c4e9a2b7d1f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "app_user",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("app_user", "token_version")
