"""种子数据（第二部分）：设计输入、文件版本、变更、问题。

这一部分是**演示可信度的关键**：
参数必须能溯源到具体勘察报告的页码表号，文件必须有真实的状态流转，
变更必须体现"涉及已施工桩位"这个最高风险项。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.base import utcnow
from app.models.change import ChangeImpact, ChangeRequest
from app.models.dict import DictItem
from app.models.document import Document, DocumentRelation, DocumentVersion, FileObject
from app.models.enums import (
    ChangeCategory,
    ChangeState,
    DocumentState,
    ImpactTargetType,
    IssueActionType,
    IssueStatus,
    SecretLevel,
)
from app.models.issue import Issue, IssueAction
from app.models.org import AppUser
from app.models.project import DesignParam, Pile, Project, SoilLayer, SoilProperty
from app.services import storage as svc_storage

HANZHOU = "ZJ-2024-001"

# ============================================================
# 土层（杭州商业综合体）
# 层顶/层底标高相对 ±0.000，向下为负
# ============================================================

SOIL_LAYERS = [
    # 层号, 名称,      层顶,   层底,   描述
    ("①", "杂填土", 3.20, 0.80, "松散，含建筑垃圾，不宜作持力层"),
    ("②", "粉质黏土", 0.80, -3.50, "可塑，中等压缩性"),
    ("③", "淤泥质黏土", -3.50, -12.80, "流塑，高压缩性，需注意桩身稳定"),
    ("④", "粉砂", -12.80, -22.40, "中密，可作摩擦桩持力层"),
    ("⑤", "强风化岩", -22.40, -28.60, "较破碎，qpk 待定"),
    ("⑥", "中风化岩", -28.60, -45.00, "较完整，桩端持力层，嵌岩深度建议 1.5m"),
]

# 每层物理力学参数：prop_code, prop_name, value, unit, locator
SOIL_PROPS = {
    "①": [("gamma", "重度", 17.5, "kN/m3", "P.10 表4-1"), ("fak", "承载力特征值", 60, "kPa", "P.10 表4-1")],
    "②": [("gamma", "重度", 18.6, "kN/m3", "P.11 表4-2"), ("c", "黏聚力", 22.5, "kPa", "P.11 表4-2"),
           ("phi", "内摩擦角", 12.8, "度", "P.11 表4-2"), ("Es", "压缩模量", 5.6, "MPa", "P.11 表4-2"),
           ("fak", "承载力特征值", 130, "kPa", "P.11 表4-2"), ("qsik", "桩侧阻力特征值", 38, "kPa", "P.15 表5-2")],
    "③": [("gamma", "重度", 17.2, "kN/m3", "P.12 表4-3"), ("c", "黏聚力", 11.0, "kPa", "P.12 表4-3"),
           ("phi", "内摩擦角", 8.5, "度", "P.12 表4-3"), ("Es", "压缩模量", 2.8, "MPa", "P.12 表4-3"),
           ("fak", "承载力特征值", 70, "kPa", "P.12 表4-3"), ("qsik", "桩侧阻力特征值", 20, "kPa", "P.15 表5-2")],
    "④": [("gamma", "重度", 19.4, "kN/m3", "P.13 表4-4"), ("c", "黏聚力", 6.0, "kPa", "P.13 表4-4"),
           ("phi", "内摩擦角", 30.5, "度", "P.13 表4-4"), ("Es", "压缩模量", 11.5, "MPa", "P.13 表4-4"),
           ("fak", "承载力特征值", 240, "kPa", "P.13 表4-4"), ("qsik", "桩侧阻力特征值", 62, "kPa", "P.15 表5-2")],
    "⑤": [("gamma", "重度", 21.0, "kN/m3", "P.14 表4-5"), ("fak", "承载力特征值", 650, "kPa", "P.14 表4-5"),
           ("qsik", "桩侧阻力特征值", 130, "kPa", "P.15 表5-2"), ("qpk", "桩端阻力特征值", 2500, "kPa", "P.15 表5-3")],
    "⑥": [("gamma", "重度", 23.5, "kN/m3", "P.14 表4-5"), ("fak", "承载力特征值", 2200, "kPa", "P.14 表4-5"),
           ("qsik", "桩侧阻力特征值", 220, "kPa", "P.15 表5-2"), ("qpk", "桩端阻力特征值", 6500, "kPa", "P.15 表5-3")],
}

# ============================================================
# 设计输入参数清单（三层结构，与《设计阶段-落地版》§2 第 5 页一致）
# 参数名 / 数值 / 单位 / 来源文件与位置 / 核验状态
# ============================================================

GROUP_SITE = "场地与地层"
GROUP_LOAD = "荷载与上部结构"
GROUP_BOUND = "边界与约束"

# (param_code, 名称, 分组, 数值, 单位, 来源定位, 核验状态, 是否必填, 备注)
DESIGN_PARAMS = [
    # ---- 场地与地层 ----
    ("SITE_PILE_TOP_ELEV", "桩顶标高", GROUP_SITE, "+3.200", "m", "详勘 V2 P.12 表4-3", "PENDING", True,
     "详勘 V2 刚更新，需重新核验"),
    ("SITE_GWL", "地下水位", GROUP_SITE, -2.5, "m", "详勘 V1 P.8 §3.2", "VERIFIED", True, None),
    ("SITE_LAYER3_FAK", "③层承载力特征值", GROUP_SITE, 320.0, "kPa", "详勘 V1 P.15 表5-2", "VERIFIED", True, None),
    ("SITE_LAYER4_ES", "④层压缩模量 Es", GROUP_SITE, 8.2, "MPa", "详勘 V1 P.16 表5-3", "VERIFIED", True, None),
    ("SITE_BEARING_LAYER", "桩端持力层", GROUP_SITE, "⑥中风化岩", None, "详勘 V1 P.14 表4-5", "VERIFIED", True, None),
    ("SITE_ROCK_SOCKET", "建议嵌岩深度", GROUP_SITE, 1.5, "m", "详勘 V1 P.20 §6.3", "VERIFIED", False, None),
    ("SITE_CORROSION", "地下水腐蚀性", GROUP_SITE, "微腐蚀", None, "详勘 V1 P.22 表7-1", "VERIFIED", True, None),
    # ---- 荷载与上部结构 ----
    ("LOAD_SINGLE_PILE", "单桩荷载标准值", GROUP_LOAD, 2200.0, "kN", "上部结构提资 V2 P.3", "VERIFIED", True, None),
    ("LOAD_TOTAL", "基础总荷载", GROUP_LOAD, 1_890_000.0, "kN", "上部结构提资 V2 P.3", "VERIFIED", True, None),
    ("LOAD_COLUMN_GRID", "柱网间距", GROUP_LOAD, "8.4×8.4", "m", "上部结构提资 V2 P.5", "VERIFIED", True, None),
    ("LOAD_FOUND_DEPTH", "基础埋深", GROUP_LOAD, 4.5, "m", "建筑图 V3 P.2", "VERIFIED", True, None),
    ("LOAD_PILE_CAP_TOP", "承台顶标高", GROUP_LOAD, "+2.800", "m", "建筑图 V3 P.2", "VERIFIED", False, None),
    ("LOAD_SETTLE_LIMIT", "沉降敏感性要求", GROUP_LOAD, "邻近地铁，沉降限值 20mm", None,
     "业主要求文件 P.4", "DOUBTFUL", True, "限值来源需业主书面确认"),
    # ---- 边界与约束 ----
    ("BOUND_SEISMIC", "抗震设防烈度", GROUP_BOUND, 6, "度", "岩土报告 P.2 §1.3", "VERIFIED", True, None),
    ("BOUND_SITE_CLASS", "场地类别", GROUP_BOUND, "Ⅲ类", None, "岩土报告 P.24 表8-1", "VERIFIED", True, None),
    ("BOUND_SAFETY_LEVEL", "桩基安全等级", GROUP_BOUND, "二级", None, "GB 50007-2011 §3.0.1", "VERIFIED", True, None),
    ("BOUND_LOCAL_CODE", "地方标准", GROUP_BOUND, "DB33/T 1136-2017", None, "浙江省地方标准", "VERIFIED", False, None),
    ("BOUND_SQUEEZE_LIMIT", "挤土效应限制", GROUP_BOUND, "邻近地铁 30m 内禁用挤土桩", None,
     "地铁保护要求 P.2", "VERIFIED", True, "直接决定预制方桩被淘汰"),
    ("BOUND_SITE_SPACE", "施工场地条件", GROUP_BOUND, "场地狭小，无预制桩堆放空间", None,
     "现场踏勘纪要 P.1", "VERIFIED", False, None),
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================
# 文件与版本
# ============================================================

def _make_file(db, name: str, content: str, mime: str, ext: str, uploader: str) -> FileObject:
    """构造一个内容寻址的 FileObject，**并把演示文件真实写入 storage/**。

    早期版本这里只写数据库记录、不落盘，而且自己编了个 `demo/...` 当 storage_key ——
    但 `storage.read_bytes()` 是按 `_storage_key()` 的规则
    （`{file_id[:2]}/{file_id[2:4]}/{file_id}{ext}`）去找文件的。
    两边规则不一致，导致**演示文件的下载一律 404**：
    点"下载"报"文件内容不存在（可能已被清理）"。

    现在改为走 `services.storage.save_bytes()`，落盘与读取用同一套规则，
    演示数据的下载按钮才真的能用。
    """
    content_bytes = content.encode("utf-8")
    fo = svc_storage.save_bytes(
        db,
        content=content_bytes,
        filename=name,
        mime=mime,
        uploader_id=uploader,
    )
    # 种子重建时每次都把引用计数归位，避免反复 seed 把 ref_count 越加越大
    fo.ref_count = 1
    db.flush()
    return fo


def seed_documents(db, project: Project, users: dict[str, AppUser], item_map: dict) -> dict[str, Document]:
    """种入 4 份文件，覆盖 已发布 / 待校审 / 修订中 三种状态。"""
    ou = users["ouyuxin"]
    li = users["ligong"]
    docs: dict[str, Document] = {}

    specs = [
        # key, 标题, 图号, 类型code, 敏感等级, 上传者
        ("survey_v2", "岩土工程勘察报告（详细勘察）", "KC-2026-018", "SURVEY_REPORT", SecretLevel.RESTRICTED, li),
        ("survey_v1", "岩土工程勘察报告（初勘）", "KC-2025-092", "SURVEY_REPORT", SecretLevel.RESTRICTED, li),
        ("layout", "桩基平面布置图", "JG-01", "LAYOUT_DWG", SecretLevel.INTERNAL, ou),
        ("calc", "单桩承载力计算书", "JG-JS-01", "CALC_BOOK", SecretLevel.INTERNAL, ou),
        ("spec", "桩基设计总说明", "JG-SM-01", "DESIGN_SPEC", SecretLevel.INTERNAL, ou),
    ]

    for key, title, doc_no, type_code, secret, uploader in specs:
        d = db.execute(
            select(Document).where(Document.project_id == project.id, Document.doc_no == doc_no)
        ).scalar_one_or_none()
        if d is None:
            cat = item_map.get(("DOC_TYPE", type_code))
            d = Document(
                project_id=project.id,
                stage_code="DESIGN" if type_code not in ("SURVEY_REPORT",) else "INVESTIGATION",
                category_id=cat.id if cat else None,
                category_name=cat.name if cat else None,
                title=title,
                doc_no=doc_no,
                discipline="岩土" if type_code == "SURVEY_REPORT" else "结构",
                secret_level=secret.value,
                created_by=uploader.id,
            )
            db.add(d)
            db.flush()
        docs[key] = d

    # ---- 版本 ----
    # 只有三种状态是"稳定可停留"的：DRAFT（草稿）、PUBLISHED（已发布）、
    # REVIEWING/CHECKING（有流程实例支撑）。
    # **审批中的状态必须由服务层产生**（提交时同时建流程），
    # 手写 REVIEWING 而没有 workflow_instance 会让版本永远卡住 ——
    # 既无法继续审批，也无法发布或作废。这是踩过的坑。
    version_specs = [
        # doc_key, 版本号, 状态, 变更说明, 创建者, 是否走审批流程
        ("survey_v1", "V1.0", DocumentState.PUBLISHED, "初勘报告发布", li, False),
        ("survey_v2", "V2.0", DocumentState.PUBLISHED, "详勘报告，补充③层参数与嵌岩建议", li, False),
        ("layout", "V1.0", DocumentState.PUBLISHED, "初版布置图", ou, False),
        ("layout", "V1.1", DocumentState.PUBLISHED, "根据详勘 V2 调整 12 根桩位", ou, False),
        ("calc", "V1.0", DocumentState.PUBLISHED, "初版计算书", ou, False),
        # 计算书 V1.1 走真实流程停在「校核中」，这样演示时它有流程实例、
        # 审批人能在待办里看到它，也能继续推进 —— 而不是一个死状态。
        ("calc", "V1.1", DocumentState.CHECKING, "按详勘 V2 参数重算", ou, True),
        ("spec", "V1.0", DocumentState.DRAFT, "设计总说明草稿", ou, False),
    ]

    for doc_key, ver_no, state, summary, creator, start_flow in version_specs:
        d = docs[doc_key]
        exists = db.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id == d.id, DocumentVersion.version_no == ver_no
            )
        ).scalar_one_or_none()
        if exists is not None:
            continue

        fo = _make_file(
            db,
            f"{d.doc_no}_{ver_no}.pdf",
            f"演示文件内容：{d.title} {ver_no} — {summary}",
            "application/pdf",
            ".pdf",
            creator.id,
        )
        rev = int(ver_no.strip("V").split(".")[-1])
        v = DocumentVersion(
            document_id=d.id,
            project_id=d.project_id,
            version_no=ver_no,
            revision=rev,
            file_id=fo.file_id,
            state=state.value,
            change_summary=summary,
            created_by=creator.id,
            submitted_at=_now() - timedelta(days=3) if state != DocumentState.DRAFT else None,
            published_at=_now() - timedelta(days=1) if state == DocumentState.PUBLISHED else None,
            published_by=creator.id if state == DocumentState.PUBLISHED else None,
        )
        db.add(v)
        db.flush()

        if state == DocumentState.PUBLISHED:
            # 关键：发布新版本时必须把旧的有效版本置为 VOID，
            # 否则会出现"同一文件两个已发布版本"，违反铁律 4。
            # 这里刻意复刻 services/documents.py publish() 的语义，
            # 保证演示数据本身就符合平台规则 —— 否则演示会自相矛盾。
            prev = db.execute(
                select(DocumentVersion).where(
                    DocumentVersion.document_id == d.id,
                    DocumentVersion.state == DocumentState.PUBLISHED.value,
                    DocumentVersion.id != v.id,
                )
            ).scalar_one_or_none()
            if prev is not None:
                prev.state = DocumentState.VOID.value
                prev.voided_at = _now()
                prev.voided_by = creator.id
                prev.void_reason = f"被新版本 {ver_no} 替代"
                v.supersedes_version_id = prev.id
                db.add(
                    DocumentRelation(
                        project_id=d.project_id,
                        src_version_id=v.id,
                        dst_version_id=prev.id,
                        rel_type="SUPERSEDE",
                        note=f"{ver_no} 替代 {prev.version_no}",
                    )
                )
                db.flush()

            d.current_version_id = v.id
            d.published_version_no = ver_no

        # ---- 走审批流程的版本：必须建立流程实例，否则状态是死的 ----
        # 只改 state 不建流程，会让版本卡在"审批中"永远出不来：
        # 既无法继续审批（没有待办任务），也无法发布或作废。
        if start_flow:
            _start_review_flow(db, version=v, initiator=creator)

    db.flush()
    return docs


def _start_review_flow(db, *, version, initiator) -> None:
    """为版本建立两级签认流程实例，并派发首个节点的任务。

    直接调服务层 start_workflow —— 流程引擎已经按**单位**派任务，
    种子数据不需要再自己复刻一遍（以前复刻过，结果引擎改了种子就跟着坏）。
    """
    from app.models.document import Document
    from app.services import workflow as wfsvc

    doc = db.get(Document, version.document_id)
    stage_code = doc.stage_code if doc else None

    inst = wfsvc.start_workflow(
        db,
        project_id=version.project_id,
        biz_type='REVIEW',
        biz_id=version.id,
        initiator_id=initiator.id,
        stage_code=stage_code,
        due_days=3,
    )
    # 把开始时间往前挪，演示时看起来像早就提交了
    inst.started_at = _now() - timedelta(days=3)
    db.flush()


# ============================================================
# 桩与变更
# ============================================================

def seed_piles(db, project: Project, item_map: dict) -> None:
    """种入桩位。部分已施工 —— 这是变更影响分析的关键数据。"""
    existing = db.execute(select(Pile).where(Pile.project_id == project.id)).scalars().first()
    if existing is not None:
        return

    bored = item_map.get(("PILE_TYPE", "BORED_1200"))
    phc = item_map.get(("PILE_TYPE", "PHC_600"))

    zones = [("1#楼", 8, 120), ("2#楼", 8, 200), ("商业裙房", 6, 280)]
    for zone_name, rows, base_x in zones:
        for r in range(1, rows + 1):
            for c in range(1, 5):
                # 前 2 个分区已施工，商业裙房未施工 —— 变更影响分析用
                constructed = zone_name in ("1#楼", "2#楼")
                db.add(
                    Pile(
                        project_id=project.id,
                        pile_no=f"{zone_name}-{c}{r:02d}",
                        pile_type_id=bored.id if bored else None,
                        pile_type_name=bored.name if bored else None,
                        x=float(base_x + c * 8.4),
                        y=float(r * 8.4),
                        z=3.2,
                        design_length=45.0,
                        design_diameter=1200.0,
                        design_capacity=2600.0,
                        zone=zone_name,
                        status="CONSTRUCTED" if constructed else "DESIGNED",
                        constructed_at=(date(2026, 9, 1) + timedelta(days=r)) if constructed else None,
                    )
                )
    # 少量 PHC 备选桩（未施工）
    for i in range(1, 9):
        db.add(
            Pile(
                project_id=project.id,
                pile_no=f"试桩-PHC-{i:02d}",
                pile_type_id=phc.id if phc else None,
                pile_type_name=phc.name if phc else None,
                x=float(400 + i * 6),
                y=50.0,
                z=3.2,
                design_length=32.0,
                design_diameter=600.0,
                design_capacity=900.0,
                zone="试桩区",
                status="DESIGNED",
                is_test_pile=True,
            )
        )
    db.flush()


def seed_changes(db, project: Project, users: dict[str, AppUser], docs: dict[str, Document]) -> None:
    """种入 3 个变更，覆盖不同阶段状态。

    **注意：状态必须用服务层产生，不能手写。**
    曾经踩过：手写 state=PENDING_APPROVAL 但没有 workflow_instance，
    而这个状态是**系统自身到达不了的**（提交时会同时建流程），
    结果变更永远卡住、无法提交也无法关闭。
    """
    from app.services import change as chgsvc

    ou = users["ouyuxin"]
    chen = users["chenkaili"]

    specs = [
        {
            "change_no": "BG-2026-001",
            "title": "③层参数按详勘 V2 修正引起的桩长调整",
            "category": ChangeCategory.SURVEY_DATA,
            "reason": "详勘 V2 报告将③层淤泥质黏土承载力特征值由 320kPa 修正为 280kPa，"
                      "原设计桩长不满足承载力要求，需整体加长 2.5m。",
            "status": ChangeState.CLOSED,
            "origin": docs["layout"],
            # 桩长调整影响全项目所有桩：1#楼 32 + 2#楼 32 + 商业裙房 24 = 88 根，
            # 其中前两个分区已施工（64 根）。数字必须与桩位表一致。
            "pile_count": 88,
            "constructed_count": 64,
            "cost_delta": 765_600.0,   # 88 根 × 8700 元
            "schedule_days": 19,       # 88/8 施工 + 64/8 返工
            # 全项目桩长调整，影响所有分区
            "zones": ["1#楼", "2#楼", "商业裙房"],
            # 明细按真实影响分析的结构写全（六类里的五类），
            # 否则会出现"汇总说 64 根已施工，明细里却没有对应的风险项"这种自相矛盾。
            "impacts": [
                (ImpactTargetType.PILE.value, "全项目 88 根桩",
                 "需按新参数重新核算承载力的桩位 88 根（设计承载力合计 228,800 kN）",
                 "HIGH", False),
                (ImpactTargetType.CONSTRUCTED_PART.value, "1#楼、2#楼已施工桩位 64 根",
                 "64 根桩已完成施工（最早施工日期 2026-09-02），"
                 "桩长加长将造成补桩或加固，必须立即通知施工方与监理",
                 "HIGH", True),
                (ImpactTargetType.CALCULATION.value, "单桩承载力计算书",
                 "1 份计算书需按变更后的参数重算并重新校审", "HIGH", False),
                (ImpactTargetType.DRAWING.value, "桩基平面布置图",
                 "1 份图纸引用了原设计版本，需更新并重新发布", "NORMAL", False),
                (ImpactTargetType.COST.value, "桩基工程成本",
                 "受影响桩位 88 根，按重做上限估算成本变化约 765,600 元", "NORMAL", False),
                (ImpactTargetType.SCHEDULE.value, "桩基施工进度",
                 "预估影响工期 19 天（含已施工部位返工）", "NORMAL", False),
            ],
        },
        {
            "change_no": "BG-2026-002",
            "title": "1#楼局部桩位避让地下管线调整",
            "category": ChangeCategory.SITE_CONDITION,
            "reason": "现场发现 1#楼东南角存在未标识的市政雨水管线，需将该区域桩位平移 1.8m 避让。",
            "status": ChangeState.APPROVING,
            "origin": docs["layout"],
            # 与 seed_piles 保持一致：1#楼为 8 行 × 4 列 = 32 根，且全部已施工。
            # 数字必须对得上，否则演示时"受影响桩位清单"列出的数量与汇总不符。
            "pile_count": 32,
            "constructed_count": 32,
            "cost_delta": 278_400.0,   # 32 根 × 8700 元（钻孔灌注桩）
            "schedule_days": 8,        # 32/8 施工 + 32/8 返工
            # 与 affected-piles 接口联动：这里填了分区，前端才能列出桩位明细
            "zones": ["1#楼"],
            "impacts": [
                (ImpactTargetType.PILE.value, "1#楼 32 根桩", "桩位平移 1.8m，需重新放线", "HIGH", True),
                (ImpactTargetType.CONSTRUCTED_PART.value, "1#楼已施工桩位 32 根",
                 "32 根桩已完成施工，桩位调整将造成返工或补桩，需立即通知施工方与监理", "HIGH", True),
                (ImpactTargetType.COST.value, "桩基工程成本", "预估增加 27.84 万元（补桩+返工）", "NORMAL", False),
                (ImpactTargetType.SCHEDULE.value, "1#楼施工进度", "预估影响 8 天（含返工）", "NORMAL", False),
            ],
        },
        {
            "change_no": "BG-2026-003",
            "title": "承台配筋按新版地方标准优化",
            "category": ChangeCategory.CODE_UPDATE,
            "reason": "浙江省地方标准 DB33/T 1136-2017 更新条文，承台最小配筋率要求调整，"
                      "借此优化配筋降低用钢量。",
            "status": ChangeState.EXECUTING,
            "origin": docs["calc"],
            "pile_count": 0,
            "constructed_count": 0,
            "cost_delta": -145_000.0,
            "schedule_days": 0,
            # 承台配筋涉及全部桩位，但属于构造优化，不做桩位级明细
            "zones": [],
            "impacts": [
                (ImpactTargetType.DRAWING.value, "承台配筋图", "按新标准调整配筋", "NORMAL", False),
                (ImpactTargetType.COST.value, "钢筋用量", "预估节省 14.5 万元", "LOW", False),
            ],
        },
    ]

    for spec in specs:
        exists = db.execute(
            select(ChangeRequest).where(
                ChangeRequest.project_id == project.id, ChangeRequest.change_no == spec["change_no"]
            )
        ).scalar_one_or_none()
        if exists is not None:
            continue

        c = ChangeRequest(
            project_id=project.id,
            stage_code="DESIGN",
            change_no=spec["change_no"],
            title=spec["title"],
            category=spec["category"].value,
            reason=spec["reason"],
            # 先用最初始的状态建立记录，随后由服务层推进到目标状态。
            # 这样能保证"状态 + 流程实例 + 影响明细"三者始终一致。
            state=ChangeState.DRAFT.value,
            origin_version_id=spec["origin"].current_version_id,
            impact_pile_count=spec["pile_count"],
            impact_constructed_count=spec["constructed_count"],
            impact_cost_delta=spec["cost_delta"],
            impact_schedule_days=spec["schedule_days"],
            initiator=ou.id,
            approver=chen.id,
            submitted_at=_now() - timedelta(days=10),
            approved_at=(
                _now() - timedelta(days=5)
                if spec["status"] in (ChangeState.APPROVED, ChangeState.EXECUTING, ChangeState.CLOSED)
                else None
            ),
            # 影响范围：必须写 zones，否则 affected-piles 接口拿不到分区，
            # 前端「受影响桩位清单」会显示"暂无数据"，演示时看起来像功能没做完。
            impact_scope={
                "zones": spec.get("zones", []),
                "pile_count": spec["pile_count"],
                "constructed_count": spec["constructed_count"],
                "analyzed_at": (_now() - timedelta(days=10)).isoformat(),
            },
        )
        db.add(c)
        db.flush()

        for target_type, target_name, desc, severity, immediate in spec["impacts"]:
            db.add(
                ChangeImpact(
                    change_id=c.id,
                    project_id=project.id,
                    target_type=target_type,
                    target_name=target_name,
                    impact_desc=desc,
                    severity=severity,
                    requires_immediate_notice=immediate,
                    handled=spec["status"] in (ChangeState.APPROVED, ChangeState.CLOSED),
                    handled_by=chen.id if spec["status"] in (ChangeState.APPROVED, ChangeState.CLOSED) else None,
                    handled_at=(
                        _now() - timedelta(days=4)
                        if spec["status"] in (ChangeState.APPROVED, ChangeState.CLOSED)
                        else None
                    ),
                )
            )
        db.flush()

        # ---- 用服务层推进到目标状态（保证流程实例被正确创建）----
        target = spec["status"]
        if target in (ChangeState.APPROVING, ChangeState.APPROVED, ChangeState.EXECUTING,
                      ChangeState.CLOSED):
            # 提交审批 —— 会同时建立 workflow_instance
            chgsvc.submit_for_approval(db, change=c, actor_id=ou.id)
            c.submitted_at = _now() - timedelta(days=10)

        if target in (ChangeState.APPROVED, ChangeState.EXECUTING, ChangeState.CLOSED):
            c.state = ChangeState.APPROVED.value
            c.approved_at = _now() - timedelta(days=5)

        if target in (ChangeState.EXECUTING, ChangeState.CLOSED):
            c.state = ChangeState.EXECUTING.value

        if target == ChangeState.CLOSED:
            c.state = ChangeState.CLOSED.value
            c.closed_at = _now() - timedelta(days=1)

        db.flush()


def seed_issues(db, project: Project, users: dict[str, AppUser]) -> None:
    """种入问题，覆盖 待处理 / 处理中 / 已闭环，并演示完整处理链路。"""
    ou = users["ouyuxin"]
    chen = users["chenkaili"]

    specs = [
        {
            "issue_no": "IS-2026-021",
            "title": "详情勘察报告中③层承载力取值与区域经验值偏差较大",
            "description": "详勘 V2 给出③层 fak=280kPa，但相邻同类型项目实测约 320kPa，"
                           "差异达 14%，需核实是否为取样扰动所致。",
            "issue_type": "PARAM",
            "severity": "HIGH",
            "status": IssueStatus.IN_PROGRESS,
            "actions": [
                (IssueActionType.DESCRIBE, "提出问题并附详勘 V2 相关页", ou, False, None),
                (IssueActionType.QUERY, "检索浙江省类似地质条件项目的③层取值区间：280~340kPa", ou, True,
                 "浙江省建筑地基基础设计规范 DB33/T 1136-2017 附录C"),
                (IssueActionType.ANALYZE, "初步判断可能为③层取样扰动导致指标偏低，"
                                          "建议补充原状土取样复验", ou, True, "详勘 V2 P.12 表4-3"),
                (IssueActionType.SUGGEST, "建议：①要求勘察单位补充 3 组原状土样复验；"
                                          "②复验前暂按 280kPa 保守设计；③复验结果若上调，走变更流程",
                 ou, True, "JGJ 94-2008 §5.3.5；详勘 V2 P.12"),
            ],
        },
        {
            "issue_no": "IS-2026-022",
            "title": "承台配筋图与结构专业标注标高不一致",
            "description": "承台顶标高在建筑图 V3 中为 +2.800，桩基布置图标注为 +3.000，需统一。",
            "issue_type": "CLASH",
            "severity": "NORMAL",
            "status": IssueStatus.PENDING_VERIFY,
            "actions": [
                (IssueActionType.DESCRIBE, "校审发现标高不一致", chen, False, None),
                (IssueActionType.ANALYZE, "确认以建筑图 V3 的 +2.800 为准，桩基图需修改", chen, False, None),
                (IssueActionType.EXECUTE, "已修改桩基平面布置图 V1.1，提交校核", ou, False, None),
                (IssueActionType.VERIFY, "待校核人确认标高已统一", chen, False, None),
            ],
        },
        {
            "issue_no": "IS-2026-023",
            "title": "邻近地铁侧桩型选择需复核挤土效应",
            "description": "原方案拟采用部分预制方桩，但场地东南侧 28m 处有地铁区间隧道。",
            "issue_type": "SPECIAL",
            "severity": "HIGH",
            "status": IssueStatus.CLOSED,
            "actions": [
                (IssueActionType.DESCRIBE, "提出挤土效应风险", ou, False, None),
                (IssueActionType.QUERY, "检索地铁保护区桩基施工限制要求", ou, True,
                 "地铁保护要求 P.2；GB 50497-2019"),
                (IssueActionType.ANALYZE, "预制方桩挤土效应显著，30m 内不宜采用", ou, True,
                 "地铁保护要求 P.2"),
                (IssueActionType.SUGGEST, "建议全部改为钻孔灌注桩，取消预制方桩方案", ou, True,
                 "JGJ 94-2008 §3.3.1"),
                (IssueActionType.EXECUTE, "已按建议调整选型，预制方桩从方案中剔除", ou, False, None),
                (IssueActionType.VERIFY, "经审核确认，选型调整合理，风险已消除", chen, False, None),
                (IssueActionType.CLOSE, "问题闭环", ou, False, None),
                (IssueActionType.KNOWLEDGE, "沉淀知识：地铁保护区 30m 内桩型选择应排除挤土桩，"
                                            "优先钻孔灌注桩。适用于后续同类项目。", ou, False, None),
            ],
        },
    ]

    for spec in specs:
        exists = db.execute(
            select(Issue).where(Issue.project_id == project.id, Issue.issue_no == spec["issue_no"])
        ).scalar_one_or_none()
        if exists is not None:
            continue

        iss = Issue(
            project_id=project.id,
            stage_code="DESIGN",
            issue_no=spec["issue_no"],
            title=spec["title"],
            description=spec["description"],
            source="REVIEW",
            severity=spec["severity"],
            status=spec["status"].value,
            raise_by=ou.id,
            raise_at=_now() - timedelta(days=14),
            assignee=ou.id,
            due_date=date(2026, 10, 20),
            is_knowledge=spec["status"] == IssueStatus.CLOSED,
            knowledge_summary=(
                "【问题】邻近地铁侧原方案拟采用部分预制方桩，但场地东南侧 28m 处有"
                "地铁区间隧道，存在挤土效应风险。\n"
                "【分析】预制方桩挤土效应显著，地铁保护区 30m 范围内不宜采用；"
                "依据《地铁保护要求》P.2 及 GB 50497-2019。\n"
                "【处理办法】全部改为钻孔灌注桩，取消预制方桩方案；"
                "施工期间对地铁隧道增加变形监测点。\n"
                "【验证结果】经审核确认，选型调整合理，挤土效应风险已消除。\n"
                "【可复用结论】地铁保护区 30m 内桩型选择应排除挤土桩（预制方桩），"
                "优先采用钻孔灌注桩；同类项目在方案阶段即应核查地铁保护区范围。"
                if spec["status"] == IssueStatus.CLOSED
                else None
            ),
            closed_at=_now() - timedelta(days=2) if spec["status"] == IssueStatus.CLOSED else None,
            closed_by=chen.id if spec["status"] == IssueStatus.CLOSED else None,
        )
        db.add(iss)
        db.flush()

        for i, (action_type, content, actor, is_ai, citation) in enumerate(spec["actions"]):
            db.add(
                IssueAction(
                    issue_id=iss.id,
                    project_id=project.id,
                    action_type=action_type.value,
                    content=content,
                    actor=actor.id,
                    is_ai_generated=is_ai,
                    ai_citation=citation,
                    acted_at=_now() - timedelta(days=13 - i),
                    sort=i + 1,
                )
            )
    db.flush()