"""种子数据执行入口。

用法（backend/ 目录下）：
    .venv\\Scripts\\python.exe -m app.seed.seed_all              # 幂等，可重复执行
    .venv\\Scripts\\python.exe -m app.seed.seed_all --reset      # 先清空业务数据再重建

演示账号（密码统一 Tjad@2026）：
    ouyuxin    欧雨欣   设计阶段负责人（设计人 / 在苏州项目是审核人）
    chenkaili  陈铠俐   施工阶段 + 架构
    haoxirui   郝兮睿   其余 5 个阶段
    zhangwei   张伟     业主项目经理
    ligong     李工     勘察
    wangwu     王五     监理

**演示数据集三方共用，不要各自另造。**
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.base import utcnow
from app.models.dict import DictCategory, DictItem
from app.models.enums import StageCode
from app.models.org import AppUser, Organization, UserOrg
from app.models.project import DesignParam, Project, SoilLayer, SoilProperty
from app.seed.seed_content import (
    DESIGN_PARAMS,
    HANZHOU,
    SOIL_LAYERS,
    SOIL_PROPS,
    _now,
    seed_changes,
    seed_documents,
    seed_issues,
    seed_piles,
)
from app.seed.seed_data import (
    PROJECTS,
    seed_dicts,
    seed_orgs,
    seed_projects,
    seed_users,
    seed_workflows,
)


def seed_soil(db, project: Project, user_id: str, survey_version_id: str | None) -> None:
    """土层与土层参数。全部标注来源（勘察报告页码表号）。"""
    for layer_no, name, top, bottom, desc in SOIL_LAYERS:
        layer = db.execute(
            select(SoilLayer).where(
                SoilLayer.project_id == project.id, SoilLayer.layer_no == layer_no
            )
        ).scalar_one_or_none()
        if layer is None:
            layer = SoilLayer(
                project_id=project.id,
                layer_no=layer_no,
                name=name,
                top_elev=top,
                bottom_elev=bottom,
                thickness=round(top - bottom, 2),
                source_version_id=survey_version_id,
                source_locator="详勘 V1 P.10~P.14",
                description=desc,
            )
            db.add(layer)
            db.flush()

        for code, pname, value, unit, locator in SOIL_PROPS.get(layer_no, []):
            exists = db.execute(
                select(SoilProperty).where(
                    SoilProperty.layer_id == layer.id, SoilProperty.prop_code == code
                )
            ).scalar_one_or_none()
            if exists is None:
                db.add(
                    SoilProperty(
                        project_id=project.id,
                        layer_id=layer.id,
                        prop_code=code,
                        prop_name=pname,
                        value=value,
                        unit=unit,
                        source_version_id=survey_version_id,
                        source_locator=locator,
                        verified_by=user_id,
                        verified_at=utcnow(),
                    )
                )
    db.flush()


def seed_design_params(db, project: Project, user_id: str, survey_version_id: str | None) -> None:
    """设计输入参数清单。**参数溯源链的演示数据。**"""
    for code, name, group, value, unit, locator, verify_status, required, note in DESIGN_PARAMS:
        exists = db.execute(
            select(DesignParam).where(
                DesignParam.project_id == project.id, DesignParam.param_code == code
            )
        ).scalar_one_or_none()
        if exists is not None:
            continue

        is_num = isinstance(value, (int, float))
        db.add(
            DesignParam(
                project_id=project.id,
                stage_code=StageCode.DESIGN.value,
                param_code=code,
                param_name=name,
                param_group=group,
                value_num=float(value) if is_num else None,
                value_text=None if is_num else str(value),
                unit=unit,
                source_type="DOCUMENT",
                source_version_id=survey_version_id,
                source_locator=locator,
                verify_status=verify_status,
                required=required,
                verified_by=user_id if verify_status == "VERIFIED" else None,
                verified_at=utcnow() if verify_status == "VERIFIED" else None,
                verify_note=note,
            )
        )
    db.flush()


def clear_business_data(db) -> None:
    """--reset 时清空业务数据（保留字典与流程模板）。"""
    from app.models.ai import AICitation, AIConversation, AIMessage, AuditLog, KnowledgeChunk
    from app.models.change import ChangeImpact, ChangeRequest
    from app.models.document import (
        Document,
        DocumentAccess,
        DocumentRelation,
        DocumentVersion,
        FileObject,
    )
    from app.models.issue import Issue, IssueAction
    from app.models.pile_selection import PileSelection
    from app.models.project import DesignParam, Pile, ProjectMember, ProjectStage, SoilLayer, SoilProperty
    from app.models.workflow import WorkflowInstance, WorkflowTask

    # 已移除成本/进度/监测共 12 张表（方向调整，详见 models/__init__.py 顶部说明）
    order = [
        AICitation, AIMessage, AIConversation, KnowledgeChunk, AuditLog,
        IssueAction, Issue,
        ChangeImpact, ChangeRequest,
        # 桩基选型方案（设计阶段）：必须在 Project 之前清，否则外键挡住项目删除
        PileSelection,
        DocumentAccess, DocumentRelation, DocumentVersion, Document,
        FileObject,
        WorkflowTask, WorkflowInstance,
        DesignParam, Pile, SoilProperty, SoilLayer,
        ProjectMember, ProjectStage, Project,
        UserOrg, AppUser, Organization,
    ]
    for model in order:
        db.query(model).delete()
    db.commit()

    # **storage/ 也要一起清。**
    # 只清数据库会把磁盘上的物理文件留下 —— 测试套件每上传一次就落一个文件，
    # 反复跑测试/重建数据后 storage/ 里会积一堆数据库已无记录的孤儿文件。
    # 内容寻址存储下这些文件永远不会再被引用（新 seed 用不同内容），
    # 所以重建演示数据时应当一并清掉，保证 storage 与 file_object 始终一致。
    _clear_storage()


def _clear_storage() -> None:
    """清空内容寻址存储目录（保留目录本身）。"""
    import shutil
    from pathlib import Path as _Path

    from app.config import settings

    root = _Path(settings.STORAGE_ROOT)
    if not root.exists():
        return
    n = 0
    for child in root.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)
        n += 1
    if n:
        print(f"清空文件存储 ...（{n} 个顶层项）")


def main() -> int:
    parser = argparse.ArgumentParser(description="写入演示种子数据")
    parser.add_argument("--reset", action="store_true", help="先清空业务数据再重建")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.reset:
            print("清空业务数据 ...")
            clear_business_data(db)

        print("1/7 字典 ...")
        item_map = seed_dicts(db)

        print("2/7 组织与用户 ...")
        org_map = seed_orgs(db)
        users = seed_users(db, org_map)

        print("3/7 流程模板 ...")
        seed_workflows(db)

        print("4/7 项目、阶段、成员 ...")
        proj_map = seed_projects(db, users, org_map)

        print("5/7 文件与版本 ...")
        hz = proj_map[HANZHOU]
        docs = seed_documents(db, hz, users, item_map)

        # 设计输入参数的溯源目标：详勘 V2 的已发布版本
        survey_v2_version_id = docs["survey_v2"].current_version_id

        print("6/7 土层、土层参数与设计输入参数 ...")
        seed_soil(db, hz, users["ligong"].id, survey_v2_version_id)
        seed_design_params(db, hz, users["ouyuxin"].id, survey_v2_version_id)

        print("7/7 桩位、变更、问题 ...")
        seed_piles(db, hz, item_map)
        seed_changes(db, hz, users, docs)
        seed_issues(db, hz, users)

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    # ---- 汇总 ----
    db = SessionLocal()
    try:
        counts = {
            "字典分类": db.query(DictCategory).count(),
            "字典项": db.query(DictItem).count(),
            "单位": db.query(Organization).count(),
            "用户": db.query(AppUser).count(),
            "项目": db.query(Project).count(),
            "土层": db.query(SoilLayer).count(),
            "设计参数": db.query(DesignParam).count(),
        }
        print()
        print("=" * 52)
        print("种子数据写入完成")
        print("=" * 52)
        for k, v in counts.items():
            print(f"  {k:<10} {v}")
        print()
        print("演示账号（密码统一 Tjad@2026）：")
        for u in db.query(AppUser).order_by(AppUser.username).all():
            print(f"  {u.username:<12} {u.name}")
        print()
        print("登录测试：")
        print("  curl -X POST http://127.0.0.1:8000/api/v1/auth/login \\")
        print('       -H "Content-Type: application/json" \\')
        print('       -d \'{"username":"ouyuxin","password":"Tjad@2026"}\'')
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
