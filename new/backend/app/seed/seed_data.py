"""种子数据 —— 三方统一的演示数据集。

**重要：三个人的演示数据必须是同一套项目，数字要自洽。**
跨阶段联合演示时数据口径不一致，一眼就能看出是假数据。

用法（backend/ 目录下）：
    .venv\\Scripts\\python.exe -m app.seed.seed_all          # 幂等，可重复执行
    .venv\\Scripts\\python.exe -m app.seed.seed_all --reset  # 清空后重建
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.ai import AuditLog
from app.models.base import utcnow
from app.models.change import ChangeImpact, ChangeRequest
from app.models.dict import DictCategory, DictCategoryCode, DictItem
from app.models.document import Document, DocumentVersion, FileObject
from app.models.enums import (
    ChangeCategory,
    ChangeState,
    DataScope,
    DocumentState,
    ImpactTargetType,
    IssueActionType,
    IssueStatus,
    OrgType,
    ProjectStatus,
    StageCode,
    StageStatus,
    UnitCode,
    WorkflowBizType,
    WorkflowNodeCode,
)
from app.models.issue import Issue, IssueAction
from app.models.org import AppUser, Organization, UserOrg
from app.models.project import (
    DesignParam,
    Pile,
    Project,
    ProjectMember,
    ProjectStage,
    SoilLayer,
    SoilProperty,
)
from app.models.workflow import WorkflowTemplate

# ============================================================
# 账号常量：三人各一个，另外几个用于演示权限差异
# ============================================================

DEMO_PASSWORD = "Tjad@2026"

USERS = [
    # username,      姓名,     单位key,          职称,                    是否超管
    #
    # **除系统管理员外都不设超管** —— 超管会绕过全部权限校验，
    # 如果演示账号都是超管，就完全看不出"单位 × 阶段 × 责任等级"的差异了。
    # 权限模型只有在普通账号上才真正生效。
    #
    # 覆盖全部 11 个参与单位，这样七个阶段都有人在，签认流程能完整跑通。
    ("ouyuxin", "欧雨欣", "TJAD", "结构工程师", False),           # 设计单位（代表）
    ("chenkaili", "陈铠俐", "OWNER", "项目负责人", False),         # 建设单位
    ("haoxirui", "郝兮睿", "TJAD", "岩土工程师", False),           # 兼勘察与设计试桩
    ("ligong", "李工", "SURVEY", "注册岩土工程师", False),         # 勘察单位
    ("zhaosi", "赵四", "DESIGN_TEST_PILE_UNIT", "试桩负责人", False),
    ("sunqi", "孙七", "GENERAL_CONTRACTOR", "项目总工", False),     # 总包单位
    ("zhouba", "周八", "SUBCONTRACTOR", "分包负责人", False),
    ("wangwu", "王五", "SUPERVISION", "总监理工程师", False),       # 监理单位
    ("wujiu", "吴九", "ACCEPT_TEST_PILE_UNIT", "验收试桩负责人", False),
    ("zhengshi", "郑十", "INSPECTION_MONITORING", "检测负责人", False),
    ("gongwu", "龚武", "GOVERNMENT", "审查员", False),              # 政府审查单位
    # 平台管理员：唯一超管，用于系统配置与跨项目查看
    ("admin", "系统管理员", "TJAD", "平台管理员", True),
]

ORGS = [
    # key,      名称,                           类型,                 是否院内
    ("TJAD", "同济大学建筑设计研究院", OrgType.DESIGN, True),
    ("OWNER", "杭州城投置业有限公司", OrgType.OWNER, False),
    ("SURVEY", "浙江华东岩土工程勘察院", OrgType.SURVEY, False),
    ("DESIGN_TEST_PILE_UNIT", "浙江省地矿建设有限公司", OrgType.DESIGN_TEST_PILE, False),
    ("GENERAL_CONTRACTOR", "中建八局第一建设有限公司", OrgType.GENERAL_CONTRACTOR, False),
    ("SUBCONTRACTOR", "杭州宏基桩基工程有限公司", OrgType.SUBCONTRACTOR, False),
    ("SUPERVISION", "杭州求是工程监理有限公司", OrgType.SUPERVISION, False),
    ("ACCEPT_TEST_PILE_UNIT", "浙江省建筑科学设计研究院", OrgType.ACCEPT_TEST_PILE, False),
    ("INSPECTION_MONITORING", "浙江省建设工程质量检测站", OrgType.INSPECTION_MONITORING, False),
    ("GOVERNMENT", "杭州市城乡建设委员会", OrgType.GOVERNMENT, False),
]

# 4 个演示项目：与交互稿完全一致（一人多项目场景）
PROJECTS = [
    {
        "project_no": "ZJ-2024-001",
        "name": "杭州某商业综合体项目",
        "short_name": "杭州商业综合体",
        "province": "浙江省",
        "city": "杭州市",
        "location": "杭州市拱墅区",
        "project_type": "商业综合体",
        "scale_desc": "桩数 860 根，钻孔灌注桩为主",
        "status": ProjectStatus.IN_PROGRESS,
        "current_stage_code": StageCode.DESIGN,
        "plan_start": date(2026, 3, 1),
        "plan_end": date(2026, 12, 31),
        "actual_start": date(2026, 3, 1),
        "//": "当前阶段设计进度 68%，与交互稿页 2 一致",
        "current_progress": 68,
    },
    {
        "project_no": "ZJ-2024-007",
        "name": "苏州工业园区某超高层项目",
        "short_name": "苏州超高层",
        "province": "江苏省",
        "city": "苏州市",
        "location": "苏州工业园区",
        "project_type": "超高层",
        "scale_desc": "桩数 1240 根，超长灌注桩",
        "status": ProjectStatus.IN_PROGRESS,
        "current_stage_code": StageCode.INVESTIGATION,
        "plan_start": date(2026, 6, 1),
        "plan_end": date(2027, 8, 31),
        "actual_start": date(2026, 6, 1),
        "current_progress": 45,
    },
    {
        "project_no": "ZJ-2025-003",
        "name": "上海某住宅组团桩基工程",
        "short_name": "上海住宅组团",
        "province": "上海市",
        "city": "上海市",
        "location": "上海市闵行区",
        "project_type": "住宅",
        "scale_desc": "桩数 1520 根，PHC 管桩为主",
        "status": ProjectStatus.IN_PROGRESS,
        "current_stage_code": StageCode.DESIGN,
        "plan_start": date(2026, 1, 15),
        "plan_end": date(2026, 11, 30),
        "actual_start": date(2026, 1, 20),
        "current_progress": 52,
    },
    {
        "project_no": "ZJ-2023-018",
        "name": "宁波某产业园桩基工程",
        "short_name": "宁波产业园",
        "province": "浙江省",
        "city": "宁波市",
        "location": "宁波市北仑区",
        "project_type": "产业园",
        "scale_desc": "桩数 640 根",
        "status": ProjectStatus.ARCHIVED,
        "current_stage_code": StageCode.MONITORING,
        "plan_start": date(2023, 5, 1),
        "plan_end": date(2025, 4, 30),
        "actual_start": date(2023, 5, 6),
        "actual_end": date(2025, 4, 18),
        "current_progress": 100,
    },
]

# ============================================================
# 项目参与单位（主体）—— 权限的最小单元
# ============================================================
#
# (项目号, 用户名, 参与单位, 单位key, 阶段覆盖)
#
# **阶段覆盖一般为 None** —— 表示"按《管理流程》矩阵来"。
# 矩阵里这个单位负责哪些阶段，他就自动有哪些阶段的权限，
# 不需要在这里一列一列地写。只有个别项目责任划分与标准矩阵
# 不同时才填，属于例外。
#
# 这份数据刻意演示三件事：
#   1. 一个人可以在同一项目下有**多个参与单位身份**（郝兮睿：
#      设计院 + 设计试桩单位），权限取并集；
#   2. 同一个人在不同项目身份不同（欧雨欣在杭州是设计单位，
#      在苏州是勘察单位）；
#   3. 每份文件的"主办单位"能从矩阵直接查出来。
MEMBERSHIPS = [
    # --- 杭州商业综合体（主演示项目，七个阶段的单位尽量配齐）---
    ("ZJ-2024-001", "chenkaili", UnitCode.OWNER, "OWNER", None),
    ("ZJ-2024-001", "ligong", UnitCode.SURVEYOR, "SURVEY", None),
    ("ZJ-2024-001", "haoxirui", UnitCode.SURVEYOR, "TJAD", None),
    ("ZJ-2024-001", "zhaosi", UnitCode.DESIGN_TEST_PILE, "DESIGN_TEST_PILE_UNIT", None),
    ("ZJ-2024-001", "ouyuxin", UnitCode.DESIGNER, "TJAD", None),
    ("ZJ-2024-001", "haoxirui", UnitCode.DESIGN_TEST_PILE, "DESIGN_TEST_PILE_UNIT", None),
    ("ZJ-2024-001", "sunqi", UnitCode.GENERAL_CONTRACTOR, "GENERAL_CONTRACTOR", None),
    ("ZJ-2024-001", "zhouba", UnitCode.SUBCONTRACTOR, "SUBCONTRACTOR", None),
    ("ZJ-2024-001", "wangwu", UnitCode.SUPERVISOR, "SUPERVISION", None),
    ("ZJ-2024-001", "wujiu", UnitCode.ACCEPT_TEST_PILE, "ACCEPT_TEST_PILE_UNIT", None),
    ("ZJ-2024-001", "zhengshi", UnitCode.INSPECTOR, "INSPECTION_MONITORING", None),
    ("ZJ-2024-001", "gongwu", UnitCode.GOVERNMENT, "GOVERNMENT", None),
    # --- 苏州超高层：欧雨欣在这里是勘察单位（身份随项目变化）---
    ("ZJ-2024-007", "ouyuxin", UnitCode.SURVEYOR, "TJAD", None),
    ("ZJ-2024-007", "chenkaili", UnitCode.OWNER, "OWNER", None),
    ("ZJ-2024-007", "haoxirui", UnitCode.SURVEYOR, "TJAD", None),
    ("ZJ-2024-007", "wangwu", UnitCode.SUPERVISOR, "SUPERVISION", None),
    # --- 上海住宅组团：欧雨欣回到设计单位 ---
    ("ZJ-2025-003", "ouyuxin", UnitCode.DESIGNER, "TJAD", None),
    ("ZJ-2025-003", "chenkaili", UnitCode.OWNER, "OWNER", None),
    ("ZJ-2025-003", "haoxirui", UnitCode.SURVEYOR, "TJAD", None),
    ("ZJ-2025-003", "sunqi", UnitCode.GENERAL_CONTRACTOR, "GENERAL_CONTRACTOR", None),
    # --- 宁波产业园：已归档，用于演示归档项目 ---
    ("ZJ-2023-018", "ouyuxin", UnitCode.DESIGNER, "TJAD", None),
    ("ZJ-2023-018", "chenkaili", UnitCode.OWNER, "OWNER", None),
    ("ZJ-2023-018", "haoxirui", UnitCode.SURVEYOR, "TJAD", None),
    ("ZJ-2023-018", "zhengshi", UnitCode.INSPECTOR, "INSPECTION_MONITORING", None),
]

STAGE_PLAN = [
    # (stage_code, 相对开工日的天数偏移天数)
    (StageCode.PRE_SURVEY, 0, 30),
    (StageCode.INVESTIGATION, 30, 75),
    (StageCode.DESIGN_TEST_PILE, 75, 105),
    (StageCode.DESIGN, 105, 180),
    (StageCode.CONSTRUCTION, 180, 300),
    (StageCode.ACCEPT_TEST_PILE, 270, 330),
    (StageCode.MONITORING, 330, 400),
]


# ============================================================
# 字典
# ============================================================

def seed_dicts(db) -> dict[str, DictItem]:
    """字典分类与字典项。返回 {(category_code, item_code): DictItem}。"""
    categories = [
        (DictCategoryCode.STAGE, "管理阶段", True, 1),
        (DictCategoryCode.PILE_TYPE, "桩型", True, 2),
        (DictCategoryCode.SOIL_LAYER, "土层", True, 3),
        (DictCategoryCode.DOC_TYPE, "文档类型", True, 4),
        (DictCategoryCode.UNIT, "单位", True, 5),
        (DictCategoryCode.ROLE, "角色", True, 6),
        (DictCategoryCode.ISSUE_TYPE, "问题类型", True, 7),
        (DictCategoryCode.CHANGE_CATEGORY, "变更原因分类", True, 8),
        (DictCategoryCode.SECRET_LEVEL, "敏感等级", True, 9),
        (DictCategoryCode.ORG_TYPE, "单位类型", True, 10),
        (DictCategoryCode.SPECIAL_ISSUE, "特殊问题库", False, 11),
    ]
    cat_map: dict[str, DictCategory] = {}
    for code, name, is_system, sort in categories:
        c = db.execute(select(DictCategory).where(DictCategory.code == code)).scalar_one_or_none()
        if c is None:
            c = DictCategory(code=code, name=name, is_system=is_system, sort=sort)
            db.add(c)
            db.flush()
        cat_map[code] = c

    # (分类, code, name, extra, sort)
    items = [
        # ---- 阶段 ----
        *[(DictCategoryCode.STAGE, s.value, label, None, i + 1) for i, (s, label) in enumerate([
            (StageCode.PRE_SURVEY, "前期调研"),
            (StageCode.INVESTIGATION, "勘察"),
            (StageCode.DESIGN_TEST_PILE, "设计试桩"),
            (StageCode.DESIGN, "设计"),
            (StageCode.CONSTRUCTION, "施工"),
            (StageCode.ACCEPT_TEST_PILE, "验收试桩"),
            (StageCode.MONITORING, "运维监测"),
        ])],
        # ---- 桩型（统一 ID，各阶段共用）----
        (DictCategoryCode.PILE_TYPE, "BORED_1200", "钻孔灌注桩 φ1200",
         {"category": "灌注桩", "diameter_mm": 1200, "typical_length_m": "20-60"}, 1),
        (DictCategoryCode.PILE_TYPE, "BORED_1000", "钻孔灌注桩 φ1000",
         {"category": "灌注桩", "diameter_mm": 1000, "typical_length_m": "20-50"}, 2),
        (DictCategoryCode.PILE_TYPE, "PHC_600", "PHC 管桩 φ600",
         {"category": "预制桩", "diameter_mm": 600, "typical_length_m": "10-35"}, 3),
        (DictCategoryCode.PILE_TYPE, "PHC_500", "PHC 管桩 φ500",
         {"category": "预制桩", "diameter_mm": 500, "typical_length_m": "10-30"}, 4),
        (DictCategoryCode.PILE_TYPE, "PRECAST_SQ_500", "预制方桩 500×500",
         {"category": "预制桩", "side_mm": 500, "note": "挤土效应明显，邻近地铁慎用"}, 5),
        (DictCategoryCode.PILE_TYPE, "MANUAL_1000", "人工挖孔桩 φ1000",
         {"category": "灌注桩", "diameter_mm": 1000, "note": "地下水位高时不适用"}, 6),
        # ---- 土层（通用分层命名）----
        (DictCategoryCode.SOIL_LAYER, "L1", "①杂填土", {"typical": "松散"}, 1),
        (DictCategoryCode.SOIL_LAYER, "L2", "②粉质黏土", {"typical": "可塑"}, 2),
        (DictCategoryCode.SOIL_LAYER, "L3", "③淤泥质黏土", {"typical": "流塑，高压缩性"}, 3),
        (DictCategoryCode.SOIL_LAYER, "L4", "④粉砂", {"typical": "中密"}, 4),
        (DictCategoryCode.SOIL_LAYER, "L5", "⑤强风化岩", {"typical": "较破碎"}, 5),
        (DictCategoryCode.SOIL_LAYER, "L6", "⑥中风化岩", {"typical": "较完整，桩端持力层"}, 6),
        # ---- 文档类型（设计阶段分类树）----
        (DictCategoryCode.DOC_TYPE, "DESIGN_SPEC", "设计说明", None, 1),
        (DictCategoryCode.DOC_TYPE, "CALC_BOOK", "计算书", None, 2),
        (DictCategoryCode.DOC_TYPE, "LAYOUT_DWG", "布置图", None, 3),
        (DictCategoryCode.DOC_TYPE, "REBAR_DWG", "配筋图", None, 4),
        (DictCategoryCode.DOC_TYPE, "CONSTR_DWG", "施工图", None, 5),
        (DictCategoryCode.DOC_TYPE, "SURVEY_REPORT", "勘察报告", None, 6),
        (DictCategoryCode.DOC_TYPE, "TEST_PILE_REPORT", "试桩报告", None, 7),
        (DictCategoryCode.DOC_TYPE, "REVIEW_OPINION", "审查意见", None, 8),
        # ---- 单位 ----
        (DictCategoryCode.UNIT, "kN", "kN", None, 1),
        (DictCategoryCode.UNIT, "kPa", "kPa", None, 2),
        (DictCategoryCode.UNIT, "MPa", "MPa", None, 3),
        (DictCategoryCode.UNIT, "m", "m", None, 4),
        (DictCategoryCode.UNIT, "mm", "mm", None, 5),
        (DictCategoryCode.UNIT, "%", "%", None, 6),
        (DictCategoryCode.UNIT, "度", "度", None, 7),
        # ---- 问题类型 ----
        (DictCategoryCode.ISSUE_TYPE, "PARAM", "参数取值", None, 1),
        (DictCategoryCode.ISSUE_TYPE, "DRAWING", "图纸问题", None, 2),
        (DictCategoryCode.ISSUE_TYPE, "CAPACITY", "承载力不足", None, 3),
        (DictCategoryCode.ISSUE_TYPE, "SETTLEMENT", "沉降超限", None, 4),
        (DictCategoryCode.ISSUE_TYPE, "CLASH", "专业冲突", None, 5),
        (DictCategoryCode.ISSUE_TYPE, "SPECIAL", "特殊地质", None, 6),
        # ---- 变更原因分类（对应 ChangeCategory 枚举）----
        (DictCategoryCode.CHANGE_CATEGORY, ChangeCategory.SURVEY_DATA.value, "勘察资料变化", None, 1),
        (DictCategoryCode.CHANGE_CATEGORY, ChangeCategory.OWNER_REQUEST.value, "业主要求", None, 2),
        (DictCategoryCode.CHANGE_CATEGORY, ChangeCategory.CODE_UPDATE.value, "规范更新", None, 3),
        (DictCategoryCode.CHANGE_CATEGORY, ChangeCategory.SITE_CONDITION.value, "施工条件", None, 4),
        (DictCategoryCode.CHANGE_CATEGORY, ChangeCategory.DESIGN_OPTIMIZE.value, "设计优化", None, 5),
        # ---- 敏感等级 ----
        (DictCategoryCode.SECRET_LEVEL, "PUBLIC", "公开", None, 1),
        (DictCategoryCode.SECRET_LEVEL, "INTERNAL", "内部", None, 2),
        (DictCategoryCode.SECRET_LEVEL, "RESTRICTED", "受限", None, 3),
        (DictCategoryCode.SECRET_LEVEL, "SECRET", "保密", None, 4),
        # ---- 参与单位类型（与《管理流程》矩阵的单位一一对应）----
        (DictCategoryCode.ORG_TYPE, OrgType.OWNER.value, "建设单位", None, 1),
        (DictCategoryCode.ORG_TYPE, OrgType.SURVEY.value, "勘察单位", None, 2),
        (DictCategoryCode.ORG_TYPE, OrgType.DESIGN_TEST_PILE.value, "设计试桩单位", None, 3),
        (DictCategoryCode.ORG_TYPE, OrgType.DESIGN.value, "设计单位", None, 4),
        (DictCategoryCode.ORG_TYPE, OrgType.GENERAL_CONTRACTOR.value, "总包单位", None, 5),
        (DictCategoryCode.ORG_TYPE, OrgType.SUBCONTRACTOR.value, "分包单位", None, 6),
        (DictCategoryCode.ORG_TYPE, OrgType.SUPERVISION.value, "监理单位", None, 7),
        (DictCategoryCode.ORG_TYPE, OrgType.ACCEPT_TEST_PILE.value, "验收试桩单位", None, 8),
        (DictCategoryCode.ORG_TYPE, OrgType.INSPECTION_MONITORING.value, "检测监测单位", None, 9),
        (DictCategoryCode.ORG_TYPE, OrgType.GOVERNMENT.value, "政府审查单位", None, 10),
        (DictCategoryCode.ORG_TYPE, OrgType.PLATFORM.value, "平台方", None, 11),
        # ---- 特殊问题库（不做自动计算，用问题库 + 案例推荐）----
        (DictCategoryCode.SPECIAL_ISSUE, "KARST", "穿越溶洞", {"approach": "问题库+相似案例推荐"}, 1),
        (DictCategoryCode.SPECIAL_ISSUE, "WEAK_LAYER", "软弱夹层", {"approach": "问题库+相似案例推荐"}, 2),
        (DictCategoryCode.SPECIAL_ISSUE, "UPLIFT", "抗拔桩设计", {"approach": "问题库+相似案例推荐"}, 3),
        (DictCategoryCode.SPECIAL_ISSUE, "NEGATIVE_FRICTION", "负摩阻力", {"approach": "问题库+相似案例推荐"}, 4),
        (DictCategoryCode.SPECIAL_ISSUE, "SQUEEZING", "挤土效应", {"approach": "问题库+相似案例推荐"}, 5),
    ]

    item_map: dict[tuple[str, str], DictItem] = {}
    for cat_code, code, name, extra, sort in items:
        cat = cat_map[cat_code]
        existing = db.execute(
            select(DictItem).where(DictItem.category_id == cat.id, DictItem.code == code)
        ).scalar_one_or_none()
        if existing is None:
            existing = DictItem(
                category_id=cat.id, code=code, name=name, extra=extra, sort=sort, active=True
            )
            db.add(existing)
            db.flush()
        else:
            # 定义改了要能生效 —— 只做 insert 会让旧名称/旧排序一直留着
            existing.name = name
            existing.extra = extra
            existing.sort = sort
        item_map[(cat_code, code)] = existing

    # **删掉定义里已不存在的内置字典项**。
    # 只做 upsert 是不够的：定义里删掉一项，库里那条还在，
    # 结果"代码说 65 项、库里有 69 项"，而且下拉框里会出现废弃选项
    # （例如旧的角色字典项）。与流程模板是同一类坑。
    # 只清理 is_system 分类下的项，各阶段自建的字典项不动。
    wanted = {(cat_code, code) for cat_code, code, *_ in items}
    for cat_code, cat in cat_map.items():
        if not cat.is_system:
            continue
        for old in db.execute(
            select(DictItem).where(DictItem.category_id == cat.id)
        ).scalars().all():
            if (cat_code, old.code) not in wanted:
                db.delete(old)

    db.flush()
    return item_map


# ============================================================
# 组织与用户
# ============================================================

def seed_orgs(db) -> dict[str, Organization]:
    org_map: dict[str, Organization] = {}
    for key, name, org_type, is_internal in ORGS:
        o = db.execute(select(Organization).where(Organization.name == name)).scalar_one_or_none()
        if o is None:
            o = Organization(name=name, org_type=org_type.value, is_internal=is_internal, active=True)
            db.add(o)
            db.flush()
        org_map[key] = o
    return org_map


def seed_users(db, org_map: dict[str, Organization]) -> dict[str, AppUser]:
    pwd_hash = hash_password(DEMO_PASSWORD)

    wanted_usernames = {u[0] for u in USERS}

    # 删掉不在定义里的旧账号（含测试临时建的 probe_*）。
    #
    # 为什么必须删：只做 upsert 会让**从定义里移除的账号一直留在库里**，
    # 结果"代码说 12 个账号、库里有 13 个"，而且多出来的账号还能登录 ——
    # 演示时会莫名其妙多出一个人。与流程模板、字典项是同一类坑。
    for stale in db.execute(
        select(AppUser).where(AppUser.username.not_in(wanted_usernames))
    ).scalars().all():
        db.delete(stale)
    db.flush()

    user_map: dict[str, AppUser] = {}
    for username, name, org_key, title, is_super in USERS:
        u = db.execute(select(AppUser).where(AppUser.username == username)).scalar_one_or_none()
        if u is None:
            u = AppUser(
                username=username,
                password_hash=pwd_hash,
                name=name,
                title=title,
                is_superuser=is_super,
                is_active=True,
                email=f"{username}@tjad.cn",
            )
            db.add(u)
            db.flush()
        else:
            # 重置密码，保证演示账号始终可用
            u.password_hash = pwd_hash
        user_map[username] = u

        org = org_map[org_key]
        link = db.execute(
            select(UserOrg).where(UserOrg.user_id == u.id, UserOrg.org_id == org.id)
        ).scalar_one_or_none()
        if link is None:
            db.add(UserOrg(user_id=u.id, org_id=org.id, is_primary=True, title_in_org=title))
            db.flush()
    return user_map


# ============================================================
# 项目、阶段、成员
# ============================================================

def seed_projects(
    db, user_map: dict[str, AppUser], org_map: dict[str, Organization]
) -> dict[str, Project]:
    proj_map: dict[str, Project] = {}
    for spec in PROJECTS:
        p = db.execute(
            select(Project).where(Project.project_no == spec["project_no"])
        ).scalar_one_or_none()
        if p is None:
            p = Project(
                project_no=spec["project_no"],
                name=spec["name"],
                short_name=spec["short_name"],
                province=spec["province"],
                city=spec["city"],
                location=spec["location"],
                project_type=spec["project_type"],
                scale_desc=spec["scale_desc"],
                status=spec["status"].value,
                current_stage_code=spec["current_stage_code"].value,
                plan_start=spec["plan_start"],
                plan_end=spec["plan_end"],
                actual_start=spec.get("actual_start"),
                actual_end=spec.get("actual_end"),
                owner_org_id=org_map["OWNER"].id,
                main_design_org_id=org_map["TJAD"].id,
                created_by=user_map["ouyuxin"].id,
            )
            db.add(p)
            db.flush()
        proj_map[spec["project_no"]] = p

        # 7 个阶段实例
        base = spec["plan_start"]
        cur_code = spec["current_stage_code"]
        cur_idx = [s for s, _, _ in STAGE_PLAN].index(cur_code)
        for idx, (stage_code, off_start, off_end) in enumerate(STAGE_PLAN):
            st = db.execute(
                select(ProjectStage).where(
                    ProjectStage.project_id == p.id, ProjectStage.stage_code == stage_code.value
                )
            ).scalar_one_or_none()
            if st is not None:
                continue

            if idx < cur_idx:
                status, prog = StageStatus.COMPLETED, 100
            elif idx == cur_idx:
                status, prog = StageStatus.IN_PROGRESS, spec.get("current_progress", 50)
                if spec["status"] == ProjectStatus.ARCHIVED:
                    status, prog = StageStatus.COMPLETED, 100
            else:
                status, prog = StageStatus.NOT_STARTED, 0

            ps = ProjectStage(
                project_id=p.id,
                stage_code=stage_code.value,
                status=status.value,
                progress=prog,
                sort=idx + 1,
                plan_start=base + timedelta(days=off_start),
                plan_end=base + timedelta(days=off_end),
                actual_start=(base + timedelta(days=off_start)) if status != StageStatus.NOT_STARTED else None,
                actual_end=(base + timedelta(days=off_end)) if status == StageStatus.COMPLETED else None,
            )
            # 阶段负责人（三方分工）
            if stage_code in (
                StageCode.PRE_SURVEY, StageCode.INVESTIGATION,
                StageCode.DESIGN_TEST_PILE, StageCode.ACCEPT_TEST_PILE, StageCode.MONITORING,
            ):
                ps.owner_user_id = user_map["haoxirui"].id
            elif stage_code == StageCode.DESIGN:
                ps.owner_user_id = user_map["ouyuxin"].id
            else:
                ps.owner_user_id = user_map["chenkaili"].id
            db.add(ps)
        db.flush()

    # 项目成员
    for project_no, username, role, org_key, stage_scope in MEMBERSHIPS:
        p = proj_map[project_no]
        u = user_map[username]
        exists = db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == p.id,
                ProjectMember.user_id == u.id,
                ProjectMember.role_code == role.value,
            )
        ).scalar_one_or_none()
        if exists is None:
            db.add(
                ProjectMember(
                    project_id=p.id,
                    user_id=u.id,
                    org_id=org_map[org_key].id,
                    role_code=role.value,
                    stage_scope=stage_scope,
                    data_scope=DataScope.PROJECT.value,
                    valid_from=p.plan_start,
                    granted_by=user_map["chenkaili"].id,
                    granted_at=utcnow(),
                )
            )
    db.flush()
    return proj_map


# ============================================================
# 流程模板
# ============================================================

def seed_workflows(db) -> None:
    templates = [
        {
            # 一套模板管全部阶段 —— 节点按**单位占位符**派发，
            # 具体是哪个单位由《管理流程》矩阵按阶段解析。
            # 这样七个阶段不需要各配一套模板，矩阵一改就全都跟着改。
            "code": "STAGE_SIGNOFF_2LEVEL",
            "name": "阶段文件两级签认",
            "biz_type": WorkflowBizType.REVIEW.value,
            "stage_code": None,
            "allow_self_check": True,
            "nodes": [
                {
                    "code": WorkflowNodeCode.CONFIRM.value,
                    "name": "主办单位确认",
                    "unit": "{PRIMARY}",
                    "sort": 1,
                    "required": True,
                },
                {
                    "code": WorkflowNodeCode.REVIEW.value,
                    "name": "相关单位复核",
                    "unit": "{RELATED}",
                    "sort": 2,
                    "required": True,
                },
            ],
            "description": (
                "阶段文件的两级签认：先由主办单位确认（该阶段主要责任单位），"
                "再由全部次要责任单位复核。相关单位有多个时并行派任务，"
                "全部签完才进入已批准，可发布。"
                "**不设发布节点** —— 发布是主办单位的独立动作，"
                "做成审批节点会导致同一单位连做两个节点而卡死。"
            ),
        },
        {
            "code": "CHANGE_APPROVAL",
            "name": "变更审批",
            "biz_type": WorkflowBizType.CHANGE.value,
            "stage_code": None,
            "allow_self_check": False,
            "nodes": [
                {
                    "code": "IMPACT",
                    "name": "影响分析",
                    "unit": "{PRIMARY}",
                    "sort": 1,
                    "required": True,
                },
                {
                    "code": "REVIEW",
                    "name": "相关单位复核",
                    "unit": "{RELATED}",
                    "sort": 2,
                    "required": True,
                },
            ],
            "description": (
                "变更由主办单位做影响分析并提交，次要责任单位复核。"
                "启动时 skip_first_node=True，跳过发起人自己的影响分析节点。"
            ),
        },
    ]
    wanted = {t["code"] for t in templates}

    # **先删掉不再使用的系统模板** —— 只做 upsert 是不够的：
    # 定义里删掉一个模板，库里那条还在，而 get_template 会优先匹配
    # 阶段专属模板，结果"新模板明明写好了却永远选不上"。
    # 这是真实踩过的坑（旧的三级校审模板残留，导致两级签认不生效）。
    # 只删 is_system=True 的，自建模板不动。
    for old in db.execute(
        select(WorkflowTemplate).where(WorkflowTemplate.is_system.is_(True))
    ).scalars().all():
        if old.code not in wanted:
            db.delete(old)

    for t in templates:
        exists = db.execute(
            select(WorkflowTemplate).where(WorkflowTemplate.code == t["code"])
        ).scalar_one_or_none()
        if exists is None:
            db.add(
                WorkflowTemplate(
                    code=t["code"],
                    name=t["name"],
                    biz_type=t["biz_type"],
                    stage_code=t["stage_code"],
                    nodes=t["nodes"],
                    allow_self_check=t["allow_self_check"],
                    is_system=True,
                    active=True,
                    description=t["description"],
                )
            )
        elif exists.is_system:
            # 系统内置模板以代码为准：定义改了要能生效，否则改模板后
            # 已有数据库里的旧节点会继续用，出现"代码说两个节点、库里三个节点"。
            exists.name = t["name"]
            exists.biz_type = t["biz_type"]
            exists.stage_code = t["stage_code"]
            exists.nodes = t["nodes"]
            exists.allow_self_check = t["allow_self_check"]
            exists.description = t["description"]
    db.flush()
