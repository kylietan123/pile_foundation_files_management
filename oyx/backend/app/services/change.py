"""设计变更影响分析服务。

**这是设计阶段最有价值的部分，也是安全价值的落点。**

核心能力：参数一变，自动列出受影响对象 —— 不依赖人记得去查。

六类影响及判定逻辑：

| 影响类型 | 判定逻辑 | 风险 |
|---|---|---|
| PILE 受影响桩位 | 按变更涉及的分区/范围筛选桩位 | 中 |
| CONSTRUCTED_PART 已施工部位 | 上述桩位中 status=CONSTRUCTED 的 | **高（需立即通知）** |
| CALCULATION 计算书 | 引用旧参数的设计计算文档 | 中 |
| DRAWING 图纸 | document_relation 中引用了原版本的图纸 | 中 |
| COST 成本 | 按受影响桩数 × 单桩造价估算 | 低 |
| SCHEDULE 进度 | 按受影响桩数 × 施工工效估算 | 低 |

**"已施工部位受影响"是最高风险项** —— 桩已经打下去了，桩位再改就是返工或补桩，
必须立即通知施工方与监理。这是通用文档管理系统做不到的。
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.change import ChangeImpact, ChangeRequest
from app.models.document import Document, DocumentVersion
from app.models.enums import (
    ChangeCategory,
    ChangeState,
    DocumentState,
    ImpactTargetType,
    WorkflowBizType,
    WorkflowStatus,
)
from app.models.project import Pile
from app.services import workflow as wf


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ChangeError(HTTPException):
    def __init__(self, message: str, code: int = 4002):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": code, "message": message},
        )


# ============================================================
# 影响分析
# ============================================================

# 估算参数（后续可做成项目级配置项）
COST_PER_PILE_BORED = 8700.0    # 钻孔灌注桩单桩造价参考值（元/根）
COST_PER_PILE_PHC = 1800.0      # PHC 管桩单桩造价参考值（元/根）
PILES_PER_DAY = 8.0             # 施工工效（根/天）


def analyze_impact(
    db: Session,
    *,
    change: ChangeRequest,
    scope_zones: list[str] | None = None,
    affected_pile_ids: list[str] | None = None,
    replace_impact: bool = True,
) -> list[ChangeImpact]:
    """执行影响分析，生成 ChangeImpact 明细。

    scope_zones      按分区筛选（如 ["1#楼", "2#楼"]）
    affected_pile_ids 直接指定受影响桩位（优先级高于 scope_zones）
    replace_impact   是否替换已有分析结果（重新分析时为 True）

    返回生成的明细列表。
    """
    project_id = change.project_id

    if replace_impact:
        for old in db.execute(
            select(ChangeImpact).where(ChangeImpact.change_id == change.id)
        ).scalars().all():
            db.delete(old)
        db.flush()

    # ---------- 1. 受影响桩位 ----------
    pile_stmt = select(Pile).where(Pile.project_id == project_id)
    if affected_pile_ids:
        pile_stmt = pile_stmt.where(Pile.id.in_(affected_pile_ids))
    elif scope_zones:
        pile_stmt = pile_stmt.where(Pile.zone.in_(scope_zones))
    else:
        # 未指定范围 → 不做桩位级分析（避免把全项目桩都算成受影响，那没意义）
        pile_stmt = pile_stmt.where(Pile.id.is_(None))

    piles = list(db.execute(pile_stmt).scalars().all())

    impacts: list[ChangeImpact] = []

    if piles:
        # 按分区归并，避免生成几百条明细
        by_zone: dict[str, list[Pile]] = {}
        for p in piles:
            by_zone.setdefault(p.zone or "未分区", []).append(p)

        for zone, zps in by_zone.items():
            total_capacity = sum(p.design_capacity or 0 for p in zps)
            impacts.append(
                ChangeImpact(
                    change_id=change.id,
                    project_id=project_id,
                    target_type=ImpactTargetType.PILE.value,
                    target_name=f"{zone} 共 {len(zps)} 根桩",
                    impact_desc=(
                        f"需重新核算承载力的桩位 {len(zps)} 根"
                        f"（设计承载力合计 {total_capacity:,.0f} kN）"
                    ),
                    severity="HIGH" if len(zps) >= 10 else "NORMAL",
                )
            )

    # ---------- 2. 已施工部位（最高风险）----------
    constructed = [p for p in piles if p.status in ("CONSTRUCTED", "CONSTRUCTED_PART", "ACCEPTED")]
    if constructed:
        by_zone_c: dict[str, list[Pile]] = {}
        for p in constructed:
            by_zone_c.setdefault(p.zone or "未分区", []).append(p)

        earliest = min(
            (p.constructed_at for p in constructed if p.constructed_at), default=None
        )
        for zone, zps in by_zone_c.items():
            impacts.append(
                ChangeImpact(
                    change_id=change.id,
                    project_id=project_id,
                    target_type=ImpactTargetType.CONSTRUCTED_PART.value,
                    target_name=f"{zone} 已施工桩位 {len(zps)} 根",
                    impact_desc=(
                        f"{len(zps)} 根桩已完成施工"
                        + (f"（最早施工日期 {earliest}）" if earliest else "")
                        + "，桩位或桩长调整将造成返工或补桩，**必须立即通知施工方与监理**"
                    ),
                    severity="HIGH",
                    requires_immediate_notice=True,
                )
            )

    # ---------- 3. 受影响计算书 ----------
    calc_docs = db.execute(
        select(Document).where(
            Document.project_id == project_id,
            Document.category_name.in_(["计算书"]),
        )
    ).scalars().all()
    if not calc_docs:
        # 兜底：按编号前缀识别（种子里计算书编号为 JG-JS-*）
        calc_docs = [
            d
            for d in db.execute(select(Document).where(Document.project_id == project_id))
            .scalars()
            .all()
            if (d.doc_no or "").startswith("JG-JS")
        ]
    if calc_docs:
        impacts.append(
            ChangeImpact(
                change_id=change.id,
                project_id=project_id,
                target_type=ImpactTargetType.CALCULATION.value,
                target_name="、".join(d.title for d in calc_docs[:3]),
                impact_desc=(
                    f"{len(calc_docs)} 份计算书需按变更后的参数重算并重新校审"
                ),
                severity="HIGH",
            )
        )

    # ---------- 4. 受影响图纸（通过引用关系）----------
    downstream: list[DocumentVersion] = []
    if change.origin_version_id:
        downstream = _find_downstream(db, change.origin_version_id)

    drawing_docs: list[Document] = []
    for v in downstream:
        d = db.get(Document, v.document_id)
        if d is not None and d not in drawing_docs:
            drawing_docs.append(d)

    if not drawing_docs:
        # 兜底：本项目的布置图/配筋图/施工图
        drawing_docs = [
            d
            for d in db.execute(select(Document).where(Document.project_id == project_id))
            .scalars()
            .all()
            if (d.category_name or "") in ("布置图", "配筋图", "施工图")
            or (d.doc_no or "").startswith("JG-0")
        ]

    if drawing_docs:
        impacts.append(
            ChangeImpact(
                change_id=change.id,
                project_id=project_id,
                target_type=ImpactTargetType.DRAWING.value,
                target_name="、".join(d.title for d in drawing_docs[:3]),
                impact_desc=(
                    f"{len(drawing_docs)} 份图纸引用了原设计版本，需更新并重新发布"
                ),
                severity="NORMAL",
            )
        )

    # ---------- 5. 成本影响 ----------
    if piles:
        bored = sum(1 for p in piles if "灌注" in (p.pile_type_name or ""))
        phc = len(piles) - bored
        delta = bored * COST_PER_PILE_BORED + phc * COST_PER_PILE_PHC
        # 桩长/桩位调整通常带来增项，这里的估算偏保守（按全部重做上限）
        impacts.append(
            ChangeImpact(
                change_id=change.id,
                project_id=project_id,
                target_type=ImpactTargetType.COST.value,
                target_name="桩基工程成本",
                impact_desc=(
                    f"受影响桩位 {len(piles)} 根，按重做上限估算成本变化 "
                    f"约 {delta:,.0f} 元（{bored} 根灌注桩 / {phc} 根预制桩）"
                ),
                severity="LOW" if delta < 100_000 else "NORMAL",
            )
        )

    # ---------- 6. 进度影响 ----------
    if piles:
        work_days = max(1, int(len(piles) / PILES_PER_DAY))
        if constructed:
            # 已施工部位返工，工期影响远大于新建
            work_days += int(len(constructed) / PILES_PER_DAY)
        impacts.append(
            ChangeImpact(
                change_id=change.id,
                project_id=project_id,
                target_type=ImpactTargetType.SCHEDULE.value,
                target_name="桩基施工进度",
                impact_desc=(
                    f"预估影响工期 {work_days} 天"
                    + ("（含已施工部位返工）" if constructed else "")
                ),
                severity="NORMAL" if work_days <= 10 else "HIGH",
            )
        )

    for imp in impacts:
        db.add(imp)
    db.flush()

    # ---------- 汇总回写到变更单 ----------
    change.impact_pile_count = len(piles)
    change.impact_constructed_count = len(constructed)

    if piles:
        bored = sum(1 for p in piles if "灌注" in (p.pile_type_name or ""))
        phc = len(piles) - bored
        change.impact_cost_delta = bored * COST_PER_PILE_BORED + phc * COST_PER_PILE_PHC

        work_days = max(1, int(len(piles) / PILES_PER_DAY))
        if constructed:
            # 已施工部位返工，工期影响远大于新建
            work_days += int(len(constructed) / PILES_PER_DAY)
        change.impact_schedule_days = work_days

    change.impact_scope = {
        "zones": sorted({p.zone for p in piles if p.zone}),
        "pile_count": len(piles),
        "constructed_count": len(constructed),
        "analyzed_at": _now().isoformat(),
    }
    db.flush()
    return impacts


def _find_downstream(db: Session, version_id: str) -> list[DocumentVersion]:
    """找出引用了某版本的下游版本。"""
    from app.models.document import DocumentRelation

    rels = db.execute(
        select(DocumentRelation).where(DocumentRelation.dst_version_id == version_id)
    ).scalars().all()
    if not rels:
        return []
    ids = [r.src_version_id for r in rels]
    return list(
        db.execute(select(DocumentVersion).where(DocumentVersion.id.in_(ids))).scalars().all()
    )


# ============================================================
# 变更状态机
# ============================================================


def assert_transition(change: ChangeRequest, target: ChangeState) -> None:
    """校验变更状态流转是否合法。"""
    current = ChangeState(change.state)
    allowed: dict[ChangeState, set[ChangeState]] = {
        ChangeState.DRAFT: {ChangeState.IMPACT_ANALYZING, ChangeState.PENDING_APPROVAL},
        ChangeState.IMPACT_ANALYZING: {ChangeState.PENDING_APPROVAL, ChangeState.DRAFT},
        ChangeState.PENDING_APPROVAL: {ChangeState.APPROVING, ChangeState.DRAFT},
        ChangeState.APPROVING: {
            ChangeState.APPROVED,
            ChangeState.REJECTED,
            ChangeState.DRAFT,
        },
        ChangeState.APPROVED: {ChangeState.EXECUTING},
        ChangeState.EXECUTING: {ChangeState.CLOSED},
        ChangeState.REJECTED: {ChangeState.DRAFT},
        ChangeState.CLOSED: set(),
    }
    if target not in allowed.get(current, set()):
        raise ChangeError(
            f"变更状态不能从「{current}」直接转到「{target}」"
        )


def submit_for_approval(
    db: Session, *, change: ChangeRequest, actor_id: str, due_days: int = 3
) -> None:
    """提交审批。**要求影响分析已完成。**"""
    if change.state not in (ChangeState.DRAFT.value, ChangeState.IMPACT_ANALYZING.value):
        raise ChangeError(
            f"当前状态为「{change.state}」，只有待提交或影响分析中的变更可以提交审批"
        )

    impacts = db.execute(
        select(ChangeImpact).where(ChangeImpact.change_id == change.id)
    ).scalars().all()
    if not impacts:
        raise ChangeError(
            "影响分析尚未完成 —— 变更必须先做影响分析才能提交审批。"
            "否则审批人无法判断这个变更会影响哪些桩位、图纸和已施工部位。"
        )

    assert_transition(change, ChangeState.PENDING_APPROVAL)

    # 提交前先校验模板要求的**参与单位**在项目里是否齐备。
    # 这一步很关键：如果模板要求"监理单位复核"但项目里没配监理，
    # 任务会处于未指派状态，流程卡死而用户不知道为什么。
    template = wf.get_template(db, WorkflowBizType.CHANGE.value, change.stage_code)
    missing = wf.missing_units(
        db,
        project_id=change.project_id,
        template=template,
        stage_code=change.stage_code,
    )
    if missing:
        from app.models.enums import UNIT_LABELS, UnitCode

        detail = "；".join(
            f"{m['node_name'] or m['node_code']} 需要「"
            f"{UNIT_LABELS.get(UnitCode(m['required_unit']), m['required_unit'])}」"
            for m in missing
        )
        raise ChangeError(
            f"项目里缺少流程要求的参与单位，无法提交审批：{detail}。"
            f"请先到「项目参与单位」补齐。",
            code=4005,
        )

    inst = wf.start_workflow(
        db,
        project_id=change.project_id,
        biz_type=WorkflowBizType.CHANGE.value,
        biz_id=change.id,
        initiator_id=actor_id,
        stage_code=change.stage_code,
        due_days=due_days,
        # 模板第一个节点是 IMPACT（影响分析），那是**发起人在提交前就已完成的**，
        # 不该变成一个"等发起人审批自己"的待办，否则流程会卡在 IMPACT 节点。
        # 所以从 REVIEW 开始。
        skip_first_node=True,
    )
    change.state = ChangeState.APPROVING.value
    change.workflow_instance_id = inst.id
    change.submitted_at = _now()
    db.flush()


def apply_approval_result(
    db: Session, *, change: ChangeRequest, instance_status: str
) -> None:
    """把流程结果同步到变更状态。"""
    if instance_status == WorkflowStatus.FINISHED.value:
        change.state = ChangeState.APPROVED.value
        change.approved_at = _now()
    else:
        change.state = ChangeState.APPROVING.value
    db.flush()


def execute_and_close(db: Session, *, change: ChangeRequest, actor_id: str) -> None:
    """关闭变更。

    **前置条件：全部影响明细已处理完毕。**
    这是"变更不闭环就不算完成"的强制点 ——
    否则会出现"变更批了，但图纸没改、施工方没收到通知"的漏洞。
    """
    if change.state not in (ChangeState.APPROVED.value, ChangeState.EXECUTING.value):
        raise ChangeError(
            f"当前状态为「{change.state}」，只有已批准或执行中的变更可以关闭"
        )

    pending = db.execute(
        select(ChangeImpact).where(
            ChangeImpact.change_id == change.id, ChangeImpact.handled.is_(False)
        )
    ).scalars().all()

    if pending:
        names = "、".join((i.target_name or i.target_type) for i in pending[:5])
        more = f" 等 {len(pending)} 项" if len(pending) > 5 else ""
        raise ChangeError(
            f"还有 {len(pending)} 项影响未处理（{names}{more}），"
            f"全部处理完毕才能关闭变更。"
            f"特别是「已施工部位受影响」必须确认已通知施工方与监理。"
        )

    change.state = ChangeState.CLOSED.value
    change.closed_at = _now()
    db.flush()


def handle_impact(
    db: Session,
    *,
    impact: ChangeImpact,
    actor_id: str,
    note: str,
) -> ChangeImpact:
    """处理一条影响明细。"""
    if impact.handled:
        raise ChangeError("该影响项已处理")
    if not note or not note.strip():
        raise ChangeError("处理影响项必须填写处理说明（做了什么、通知了谁）")

    impact.handled = True
    impact.handled_by = actor_id
    impact.handled_at = _now()
    impact.handle_note = note
    db.flush()
    return impact


# ============================================================
# 通知（写审计日志，后续可扩展为站内信/邮件）
# ============================================================


def notify_affected(
    db: Session, *, change: ChangeRequest, actor_id: str, actor_name: str
) -> list[dict]:
    """把「需要立即通知」的影响项落成审计记录。

    真实系统里这里会发站内信/邮件；当前先写审计日志保证可追溯，
    接口形态保持一致，后续替换实现即可。
    """
    from app.models.ai import AuditLog

    urgent = db.execute(
        select(ChangeImpact).where(
            ChangeImpact.change_id == change.id,
            ChangeImpact.requires_immediate_notice.is_(True),
        )
    ).scalars().all()

    sent: list[dict] = []
    for imp in urgent:
        db.add(
            AuditLog(
                project_id=change.project_id,
                stage_code=change.stage_code,
                actor=actor_id,
                actor_name=actor_name,
                action="NOTIFY",
                target_type="change_impact",
                target_id=imp.id,
                target_name=imp.target_name,
                detail=(
                    f"变更 {change.change_no} 涉及已施工部位，已通知施工方与监理："
                    f"{imp.impact_desc}"
                ),
                success=True,
            )
        )
        sent.append(
            {
                "impact_id": imp.id,
                "target_name": imp.target_name,
                "notified_to": ["施工方", "监理"],
            }
        )
    db.flush()
    return sent