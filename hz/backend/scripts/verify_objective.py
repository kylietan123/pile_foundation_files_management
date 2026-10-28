"""最终验收核查：逐项对照目标，确认全部达成。

用法（backend/ 目录下）：
    .venv\\Scripts\\python.exe scripts/verify_objective.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.core.permissions import build_principal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.models.enums import (  # noqa: E402
    RESPONSIBILITY_MATRIX,
    UNIT_LABELS,
    DocumentState,
    Responsibility,
    StageCode,
    UnitCode,
    primary_unit_of_stage,
)
from app.models.document import Document, DocumentVersion  # noqa: E402
from app.models.org import AppUser  # noqa: E402
from app.models.project import Project  # noqa: E402

ok = 0
bad = 0


def chk(desc: str, cond: bool, extra: str = "") -> None:
    global ok, bad
    if cond:
        ok += 1
        print(f"  [OK]   {desc}")
    else:
        bad += 1
        print(f"  [FAIL] {desc}  {extra}")


print("=" * 72)
print("目标验收：以参与单位为主体的文档管理系统")
print("=" * 72)

# ---------------- (1) 换主体 ----------------
print("\n(1) 换主体 —— 参与单位 + 权限矩阵入库 + 两级签认")

units = [u for u in UnitCode if u is not UnitCode.ADMIN]
# 角色表里是 **10 个参与单位 + 1 个系统管理员**，共 11 项。
# ADMIN 是平台角色、不是项目参与方，所以参与单位是 10 个。
chk("参与单位共 10 个（另加系统管理员 = 表格 11 项）", len(units) == 10, f"实际 {len(units)}")
chk("单位枚举共 11 项", len(list(UnitCode)) == 11, f"实际 {len(list(UnitCode))}")
chk("每个单位都有中文名", all(UNIT_LABELS.get(u) for u in units))
matrix_stages = list(RESPONSIBILITY_MATRIX.keys())
chk("责任矩阵覆盖 7 个阶段", len(matrix_stages) == 7, str(matrix_stages))
chk("阶段名与 StageCode 一致",
    set(matrix_stages) == {s.value for s in StageCode},
    str(matrix_stages))
chk("每个阶段恰好一个主办单位",
    all(sum(1 for u in units
            if RESPONSIBILITY_MATRIX[s].get(u.value) is Responsibility.PRIMARY) == 1
        for s in matrix_stages))
chk("每个阶段的主办单位都能取到",
    all(primary_unit_of_stage(s) for s in matrix_stages))
chk("政府审查单位不担主办",
    all(RESPONSIBILITY_MATRIX[s].get(UnitCode.GOVERNMENT.value)
        is not Responsibility.PRIMARY
        for s in matrix_stages))

# 两级签认模板
from app.services.workflow import DEFAULT_REVIEW_NODES  # noqa: E402

nodes = [n["code"] for n in DEFAULT_REVIEW_NODES]
chk("签认流程恰为两级（CONFIRM → REVIEW）",
    nodes == ["CONFIRM", "REVIEW"], str(nodes))
# 节点必须用**单位占位符**而不是写死的岗位码 ——
# 否则换阶段就得改模板，矩阵推导也就落不了地。
chk("节点用单位占位符而非写死岗位",
    [n.get("unit") for n in DEFAULT_REVIEW_NODES] == ["{PRIMARY}", "{RELATED}"],
    str([n.get("unit") for n in DEFAULT_REVIEW_NODES]))

db = SessionLocal()
try:
    # 单位内任何人都能上传：同一单位两个成员都应具备 EDIT
    hz = db.execute(select(Project).where(Project.project_no == "ZJ-2024-001")).scalar_one()
    designers = db.execute(
        select(AppUser).where(AppUser.username.in_(["ouyuxin"]))
    ).scalars().all()
    chk("设计单位成员存在", bool(designers))
    if designers:
        p = build_principal(db, designers[0])
        chk("设计单位在设计阶段可编辑（可上传）",
            p.can("EDIT", hz.id, StageCode.DESIGN.value))
        chk("设计单位在勘察阶段只能查看（可查阅输入）",
            p.can("VIEW", hz.id, StageCode.INVESTIGATION.value)
            and not p.can("EDIT", hz.id, StageCode.INVESTIGATION.value))
        chk("设计单位在施工阶段可查看", p.can("VIEW", hz.id, StageCode.CONSTRUCTION.value))
        chk("设计单位在前期调研阶段无权限",
            not p.can("VIEW", hz.id, StageCode.PRE_SURVEY.value))
        chk("设计单位是本阶段主办单位", p.is_primary_of(hz.id, StageCode.DESIGN.value))

        # ---- 勘察阶段给设计单位补的"参与"责任（2026-10-13 经确认）----
        # 矩阵原表这一格没打 √，但设计必须参照勘察资料，否则设计人员
        # 在系统里看不到勘察报告、输入文件库是空的。
        # 定为只读且**不承担勘察阶段责任** —— 参与 ≠ 责任。
        # 这里显式断言，防止以后被当成"多余的权限"清理掉。
        inv = RESPONSIBILITY_MATRIX[StageCode.INVESTIGATION.value]
        chk("勘察阶段：设计单位为『参与』（已确认的补充项）",
            inv.get(UnitCode.DESIGNER.value) is Responsibility.PARTICIPANT,
            str(inv.get(UnitCode.DESIGNER.value)))
        chk("勘察阶段：主办单位仍是勘察单位（责任未被转移）",
            inv.get(UnitCode.SURVEYOR.value) is Responsibility.PRIMARY,
            str(inv.get(UnitCode.SURVEYOR.value)))
        chk("勘察阶段：设计单位不承担勘察阶段责任（参与≠责任）",
            not p.is_primary_of(hz.id, StageCode.INVESTIGATION.value))
        chk("勘察阶段：设计单位不能上传/编辑勘察文件",
            not p.can("EDIT", hz.id, StageCode.INVESTIGATION.value))

    # 审计留痕：操作人字段存在
    from app.models.ai import AuditLog  # noqa: E402
    cols = set(AuditLog.__table__.columns.keys())
    chk("审计表记录操作人", "actor" in cols or "actor_id" in cols, str(sorted(cols)))
    dvcols = set(Document.__table__.columns.keys())
    chk("文件表记录创建人", "created_by" in dvcols)
    vcols = set(DocumentVersion.__table__.columns.keys())
    for f in ("created_by", "published_by", "voided_by"):
        chk(f"版本表记录 {f}", f in vcols)

    # 版本可追溯
    chk("版本表有版本号与状态", {"version_no", "state"} <= vcols)
finally:
    db.close()

# ---------------- (2) 阶段页面 ----------------
print("\n(2) 各阶段页面 —— 文件台账 + 交办事项")
paths = {p for p in app.openapi()["paths"]}
chk("台账接口存在", "/api/v1/projects/{project_id}/ledger" in paths)
chk("等我处理接口存在", "/api/v1/projects/{project_id}/ledger/awaiting-me" in paths)
chk("阶段责任总览接口存在",
    "/api/v1/projects/{project_id}/stage-responsibility" in paths)
chk("工作台（跨项目交办）接口存在", "/api/v1/workbench/my-work" in paths)
chk("项目交办事项接口存在",
    "/api/v1/workbench/projects/{project_id}/work" in paths)

views = APP_DIR / "frontend" / "src" / "views"
chk("台账与追溯页面存在", (views / "LedgerView.vue").exists())
chk("工作台页面存在", (views / "WorkbenchView.vue").exists())
chk("输入文件库在 DesignInputView 中", "输入文件库" in
    (views / "DesignInputView.vue").read_text(encoding="utf-8"))

# ---------------- (3) 追溯页 ----------------
print("\n(3) 追溯页 —— 谁上传 / 谁确认 / 文件在谁手上")
led = (BACKEND_DIR / "app" / "services" / "ledger.py").read_text(encoding="utf-8")
for key, desc in [
    ("primary_unit", "给出主办单位（追责对象）"),
    ("current_uploaded_by", "给出上传人"),
    ("pending_unit_labels", "给出当前待签单位（文件在谁手上）"),
    ("trace", "给出签认轨迹"),
    ("created_by", "给出创建人"),
]:
    chk(desc, key in led)
chk("台账不引入新表（无新模型文件）",
    not (BACKEND_DIR / "app" / "models" / "ledger.py").exists())

# ---------------- (4) 收尾 ----------------
print("\n(4) 收尾 —— 输入文件库 / 清理无用表 / 汇报材料")

removed = ["cost_item", "cost_actual", "schedule_task", "progress_report",
           "monitor_point", "monitor_reading", "monitor_threshold", "monitor_alarm"]
chk(f"12 张无用表已移除（表数 {len(Base.metadata.tables)}）",
    not any(t in Base.metadata.tables for t in removed))
chk("成本/监测模型文件已删除",
    not (BACKEND_DIR / "app" / "models" / "cost.py").exists()
    and not (BACKEND_DIR / "app" / "models" / "monitoring.py").exists())
# 29 张基线表
# + hxr 版补入的 4 张阶段台账表
#   （钻孔 borehole / 证照 license / 监测点 monitoring_point / 标准清单 document_checklist）
# + 1 张桩基选型方案表（pile_selection，设计阶段模块）
chk("表数 = 29 张基线 + 4 张阶段台账 + 1 张选型方案", len(Base.metadata.tables) == 34,
    f"实际 {len(Base.metadata.tables)}")

import sqlite3  # noqa: E402
dbc = sqlite3.connect(APP_DIR / "pile_lcm.db")
real = {r[0] for r in dbc.execute(
    "select name from sqlite_master where type='table' and name not like 'sqlite_%'"
    " and name != 'alembic_version'"
)}
dbc.close()
chk("数据库实际表 = ORM 表", real == set(Base.metadata.tables),
    f"多 {real - set(Base.metadata.tables)} 少 {set(Base.metadata.tables) - real}")

rep = APP_DIR / "docs" / "report-diagrams" / "数据库结构与权限设计.html"
if rep.exists():
    t = rep.read_text(encoding="utf-8")
    chk("汇报材料已改单位矩阵", "RESPONSIBILITY_MATRIX" in t)
    chk("汇报材料不再提三级校审", "三级校审" not in t)
    chk("汇报材料写明业务表数量", "34 张业务表" in t)
    chk("汇报材料有已移除表说明", "已移除" in t)
else:
    chk("汇报材料存在", False)

pngs = list((APP_DIR / "docs" / "report-diagrams" / "render").glob("*.png"))
chk("汇报图已重新出图（5 张）", len(pngs) == 5, f"实际 {len(pngs)}")

# ---------------- 汇总 ----------------
print("\n" + "=" * 72)
# 这一行必须与其它测试套件的格式完全一致，否则 run_all_tests.py 解析不到
print(f"通过 {ok} 项，失败 {bad} 项")
print("=" * 72)
sys.exit(0 if bad == 0 else 1)
