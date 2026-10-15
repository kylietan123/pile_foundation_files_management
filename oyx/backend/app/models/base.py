"""SQLAlchemy 声明式基类与通用混入。

三条全局约定（三方必须遵守）：
1. 主键 id 为 32 位 UUID hex 字符串（String(32)），不使用自增整数。
2. 所有时间字段统一用 UTC，字段名以 _at 结尾。
3. 业务表必须带 project_id；跨阶段共享的表还必须能按 stage_code 过滤。

**命名约定（naming_convention）为什么必须有**：
    SQLite 不支持 ALTER TABLE，改字段只能靠 batch 模式（重建表 + 复制数据）。
    重建表时要按名字删除旧约束 —— 如果约束是匿名的（数据库自动起名如
    "None" 或随机名），batch 操作就会报 `ValueError: Constraint must have a name`。
    加上统一命名约定后，所有约束都有确定的名字，
    迁移才能在 SQLite 和 PostgreSQL 上都正常工作。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, MetaData, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# 统一约束命名规则。改这里会影响所有迁移，务必谨慎。
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def new_id() -> str:
    """生成 32 位 UUID hex 字符串作为主键。"""
    return uuid.uuid4().hex


def utcnow() -> datetime:
    """带时区的 UTC 当前时间。"""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """所有模型的基类。"""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class IdMixin:
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
