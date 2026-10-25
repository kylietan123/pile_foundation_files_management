"""可移植字段类型辅助。

统一用 MutableDict / MutableList 包装 JSON 字段，使得
`obj.extra["k"] = v` 这种原地修改也能被正确 persist。

注意：**不要引入 PostgreSQL 专有类型**（JSONB / ARRAY / CITEXT），
否则开发期的 SQLite 与生产的 PostgreSQL 行为会不一致。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON
from sqlalchemy.ext.mutable import MutableDict, MutableList


def json_obj() -> Any:
    """可原地修改的 JSON 对象字段类型（用于 mapped_column 的第一个参数）。"""
    return MutableDict.as_mutable(JSON)


def json_arr() -> Any:
    """可原地修改的 JSON 数组字段类型。"""
    return MutableList.as_mutable(JSON)


def as_utc(dt: datetime | None) -> datetime | None:
    """把可能缺失时区的时间统一成 UTC-aware。

    **为什么必须有这个函数**：
        SQLite 不保存时区信息，DateTime(timezone=True) 的字段读回来是
        naive datetime。一旦拿它和 utcnow()（aware）比较就会抛
        `TypeError: can't compare offset-naive and offset-aware datetimes`。

        开发期 SQLite、生产 PostgreSQL，两边行为不同 ——
        所以**任何时间比较前都要先过这个函数**，不能直接比较。
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def is_overdue(due_at: datetime | None, now: datetime | None = None) -> bool:
    """判断是否逾期。内部已处理时区问题，调用方不必再关心。"""
    d = as_utc(due_at)
    if d is None:
        return False
    ref = as_utc(now) or datetime.now(timezone.utc)
    return d < ref
