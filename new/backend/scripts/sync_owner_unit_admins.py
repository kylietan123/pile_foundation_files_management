"""把建设单位管理员补入本单位所有项目。

用于修复历史项目：普通建设单位员工创建项目时，管理员尚未自动加入。
脚本幂等，可以重复执行。
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import select

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import SessionLocal  # noqa: E402
from app.models.enums import DataScope, OrgType, UnitCode  # noqa: E402
from app.models.org import Organization, UserOrg  # noqa: E402
from app.models.project import Project, ProjectMember  # noqa: E402


def main() -> int:
    added = 0
    with SessionLocal() as db:
        owner_orgs = db.execute(
            select(Organization).where(Organization.org_type == OrgType.OWNER.value)
        ).scalars().all()
        for org in owner_orgs:
            admins = db.execute(
                select(UserOrg).where(
                    UserOrg.org_id == org.id,
                    UserOrg.is_unit_admin.is_(True),
                )
            ).scalars().all()
            projects = db.execute(select(Project).where(Project.owner_org_id == org.id)).scalars().all()
            for project in projects:
                for link in admins:
                    exists = db.execute(
                        select(ProjectMember).where(
                            ProjectMember.project_id == project.id,
                            ProjectMember.user_id == link.user_id,
                            ProjectMember.role_code == UnitCode.OWNER.value,
                        )
                    ).scalar_one_or_none()
                    if exists is None:
                        db.add(
                            ProjectMember(
                                project_id=project.id,
                                user_id=link.user_id,
                                org_id=org.id,
                                role_code=UnitCode.OWNER.value,
                                stage_scope="ALL",
                                data_scope=DataScope.PROJECT.value,
                            )
                        )
                        added += 1
        db.commit()
    print(f"已补充建设单位管理员项目成员关系：{added} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
