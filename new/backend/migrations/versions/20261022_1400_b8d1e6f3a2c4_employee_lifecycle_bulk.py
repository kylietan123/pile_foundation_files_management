"""employee lifecycle fields and unique identity columns

Revision ID: b8d1e6f3a2c4
Revises: a7c2d9e4b6f1
Create Date: 2026-10-22 14:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8d1e6f3a2c4"
down_revision: Union[str, Sequence[str], None] = "a7c2d9e4b6f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _check_duplicates(bind, column: str, label: str) -> None:
    row = bind.execute(
        sa.text(
            f"SELECT {column} FROM app_user "
            f"WHERE {column} IS NOT NULL "
            f"GROUP BY {column} HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if row is not None:
        raise RuntimeError(
            f"无法添加{label}唯一约束：存在重复值 {row[0]!r}，请先人工合并重复账号"
        )


def upgrade() -> None:
    op.add_column(
        "app_user",
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("app_user", sa.Column("last_password_changed_at", sa.DateTime(timezone=True)))
    op.add_column("app_user", sa.Column("hire_date", sa.Date()))
    op.add_column("app_user", sa.Column("leave_date", sa.Date()))
    op.add_column("app_user", sa.Column("disabled_at", sa.DateTime(timezone=True)))
    op.add_column("app_user", sa.Column("disabled_by", sa.String(length=32)))
    op.add_column("app_user", sa.Column("disable_reason", sa.String(length=255)))

    bind = op.get_bind()
    # 历史数据先统一大小写和空白，唯一索引才能可靠防止重复。
    bind.execute(sa.text("UPDATE app_user SET email = lower(trim(email)) WHERE email IS NOT NULL"))
    bind.execute(sa.text("UPDATE app_user SET employee_no = upper(trim(employee_no)) WHERE employee_no IS NOT NULL"))
    bind.execute(sa.text("UPDATE app_user SET email = NULL WHERE email = ''"))
    bind.execute(sa.text("UPDATE app_user SET employee_no = NULL WHERE employee_no = ''"))

    _check_duplicates(bind, "employee_no", "工号")
    _check_duplicates(bind, "email", "邮箱")

    op.create_index(
        "uq_app_user_employee_no",
        "app_user",
        ["employee_no"],
        unique=True,
    )
    op.create_index(
        "uq_app_user_email",
        "app_user",
        ["email"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_app_user_email", table_name="app_user")
    op.drop_index("uq_app_user_employee_no", table_name="app_user")
    op.drop_column("app_user", "disable_reason")
    op.drop_column("app_user", "disabled_by")
    op.drop_column("app_user", "disabled_at")
    op.drop_column("app_user", "leave_date")
    op.drop_column("app_user", "hire_date")
    op.drop_column("app_user", "last_password_changed_at")
    op.drop_column("app_user", "must_change_password")
