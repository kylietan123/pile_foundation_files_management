"""字典模型。

**统一 ID 原则的载体**：同一实体在全平台只有一个 ID。
"钻孔灌注桩"在勘察、设计、施工、验收四个阶段必须是同一个字典项、同一个 ID。
各阶段不得自建桩型 / 土层 / 单位列表。

规则：字典项只允许停用（active=False），**不允许物理删除**，否则历史数据无法解析。
"""
from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.types import json_obj
from app.models.base import Base, IdMixin, TimestampMixin


class DictCategory(Base, IdMixin, TimestampMixin):
    """字典分类：STAGE / PILE_TYPE / SOIL_LAYER / DOC_TYPE / UNIT / ROLE / ISSUE_TYPE ..."""

    __tablename__ = "dict_category"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # 系统内置，不可删
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    items: Mapped[list["DictItem"]] = relationship(
        back_populates="category", cascade="all, delete-orphan", order_by="DictItem.sort"
    )


class DictItem(Base, IdMixin, TimestampMixin):
    """字典项。支持树形（parent_id），如土层分层、文档类型分类。

    id 就是全平台通用的业务 ID（如 pile_type_id 直接引用本表 id）。
    """

    __tablename__ = "dict_item"
    __table_args__ = (
        UniqueConstraint("category_id", "code", name="uq_dict_item_category_code"),
    )

    category_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("dict_category.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("dict_item.id", ondelete="SET NULL"), index=True
    )

    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # 附加属性，例如桩型的直径范围、单位符号
    extra: Mapped[dict | None] = mapped_column(json_obj())
    description: Mapped[str | None] = mapped_column(Text)

    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    category: Mapped[DictCategory] = relationship(back_populates="items")
    children: Mapped[list["DictItem"]] = relationship(
        back_populates="parent", remote_side="DictItem.parent_id", cascade="save-update"
    )
    parent: Mapped["DictItem | None"] = relationship(back_populates="children", remote_side="DictItem.id")


# 分类 code 常量（供 seed 与业务代码引用，避免到处写字符串字面量）
class DictCategoryCode:
    STAGE = "STAGE"
    PILE_TYPE = "PILE_TYPE"
    SOIL_LAYER = "SOIL_LAYER"
    DOC_TYPE = "DOC_TYPE"
    UNIT = "UNIT"
    ROLE = "ROLE"
    ISSUE_TYPE = "ISSUE_TYPE"
    CHANGE_CATEGORY = "CHANGE_CATEGORY"
    SECRET_LEVEL = "SECRET_LEVEL"
    ORG_TYPE = "ORG_TYPE"
    SPECIAL_ISSUE = "SPECIAL_ISSUE"   # 特殊问题库（穿越溶洞、软弱夹层、抗拔、负摩阻…）
