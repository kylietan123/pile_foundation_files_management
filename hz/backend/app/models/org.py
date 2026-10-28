"""组织、用户、任职关系。

设计要点：
1. 认证信息（密码哈希）与业务信息放在同一张 app_user 表里但职责分离，
   注释明确标出哪些字段属于认证域。
2. 一个人可以在多个单位任职 —— user_org 支持多对多，is_primary 标记主单位。
3. **用户与项目的关联只能通过 project_member**（见 project.py），不得在业务表里直接写 user_id 做权限判断。
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin


class Organization(Base, IdMixin, TimestampMixin):
    """参与单位。"""

    __tablename__ = "organization"

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    short_name: Mapped[str | None] = mapped_column(String(64))
    # OrgType 枚举值
    org_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    parent_org_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("organization.id", ondelete="SET NULL"), index=True
    )

    credit_code: Mapped[str | None] = mapped_column(String(64), comment="统一社会信用代码")
    contact_person: Mapped[str | None] = mapped_column(String(64))
    contact_phone: Mapped[str | None] = mapped_column(String(32))
    address: Mapped[str | None] = mapped_column(String(300))
    remark: Mapped[str | None] = mapped_column(Text)

    is_internal: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="是否为本院（设计院）内部单位"
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    users: Mapped[list["UserOrg"]] = relationship(back_populates="org", cascade="all, delete-orphan")
    children: Mapped[list["Organization"]] = relationship(
        back_populates="parent", remote_side="Organization.parent_org_id"
    )
    parent: Mapped["Organization | None"] = relationship(
        back_populates="children", remote_side="Organization.id"
    )


class AppUser(Base, IdMixin, TimestampMixin):
    """用户账号。

    ---- 认证域字段 ----（改这些字段要谨慎，涉及安全）
    username / password_hash / is_superuser / last_login_at / is_active

    ---- 业务域字段 ----
    name / phone / email / title / employee_no
    """

    __tablename__ = "app_user"

    # ---- 认证域 ----
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    last_login_at: Mapped[datetime | None] = mapped_column()
    # 预留 LDAP/AD 对接：为空表示本地账号
    external_id: Mapped[str | None] = mapped_column(String(128), index=True)
    auth_source: Mapped[str] = mapped_column(
        String(16), default="LOCAL", nullable=False, comment="LOCAL / LDAP / AD"
    )

    # ---- 业务域 ----
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    employee_no: Mapped[str | None] = mapped_column(String(64), index=True)
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(128))
    title: Mapped[str | None] = mapped_column(String(64), comment="职称，如注册结构工程师")
    avatar: Mapped[str | None] = mapped_column(String(300))

    orgs: Mapped[list["UserOrg"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserOrg(Base, IdMixin, TimestampMixin):
    """用户在某单位的任职关系。"""

    __tablename__ = "user_org"
    __table_args__ = (
        UniqueConstraint("user_id", "org_id", name="uq_user_org"),
    )

    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    org_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("organization.id", ondelete="CASCADE"), nullable=False, index=True
    )

    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_unit_admin: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="部门管理员（领导），负责本部门账号与项目权限管理"
    )
    title_in_org: Mapped[str | None] = mapped_column(String(64))
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)

    user: Mapped[AppUser] = relationship(back_populates="orgs")
    org: Mapped[Organization] = relationship(back_populates="users")
