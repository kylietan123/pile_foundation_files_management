"""工作台 —— 跨项目的"我的工作"。

用户场景是**一个人同时参与多个项目**，所以工作台必须跨项目聚合，
不能让人一个项目一个项目点进去找。

分三类（按处理紧迫度排序）：

    1 等我签认     别人提交了，卡在我这里 —— **最要紧，别人在等我**
    2 被退回       我提交的被打回，需要我修改后重交
    3 我经手在途   我参与提交、目前还在流转（知悉用，不必动手）

为什么把"等我签认"排最前：它是唯一一类**不动手就会拖住别人**的事。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.types import is_overdue
from app.models.ai import AuditLog
from app.models.document import Document, DocumentVersion
from app.models.enums import (
    DOCUMENT_STATE_LABELS,
    STAGE_LABELS,
    TaskAction,
    UnitCode,
    UNIT_LABELS,
    DocumentState,
    StageCode,
    WorkflowBizType,
    WorkflowStatus,
)
from app.models.org import AppUser
from app.models.project import Project
from app.models.workflow import WorkflowInstance, WorkflowTask


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stage_label(code: str | None) -> str:
    """阶段码 → 中文名。查不到就原样返回，不抛异常。"""
    if not code:
        return "未知阶段"
    try:
        return STAGE_LABELS[StageCode(code)]
    except (ValueError, KeyError):
        return code


def _days_left(due_at: datetime | None) -> int | None:
    if due_at is None:
        return None
    d = due_at if due_at.tzinfo else due_at.replace(tzinfo=timezone.utc)
    return (d - _now()).days


def my_work(db: Session, *, user_id: str, limit: int = 300) -> dict[str, Any]:
    """跨项目的我的工作台。"""
    # ---------- 1. 等我签认 ----------
    my_tasks = list(
        db.execute(
            select(WorkflowTask)
            .where(WorkflowTask.assignee == user_id, WorkflowTask.action.is_(None))
            .order_by(WorkflowTask.due_at.is_(None), WorkflowTask.due_at)
            .limit(limit)
        ).scalars().all()
    )

    # 批量取上下文（项目、流程、版本、文件）
    proj_ids = {t.project_id for t in my_tasks}
    inst_ids = {t.instance_id for t in my_tasks}
    projects = {
        p.id: p
        for p in (
            db.execute(select(Project).where(Project.id.in_(proj_ids))).scalars().all()
            if proj_ids
            else []
        )
    }
    insts = {
        i.id: i
        for i in (
            db.execute(select(WorkflowInstance).where(WorkflowInstance.id.in_(inst_ids)))
            .scalars()
            .all()
            if inst_ids
            else []
        )
    }
    ver_ids = {i.biz_id for i in insts.values() if i.biz_type == WorkflowBizType.REVIEW.value}
    versions = {
        v.id: v
        for v in (
            db.execute(select(DocumentVersion).where(DocumentVersion.id.in_(ver_ids)))
            .scalars()
            .all()
            if ver_ids
            else []
        )
    }
    doc_ids = {v.document_id for v in versions.values()}
    docs = {
        d.id: d
        for d in (
            db.execute(select(Document).where(Document.id.in_(doc_ids))).scalars().all()
            if doc_ids
            else []
        )
    }

    # **草稿态版本不该有待签任务。**
    # 退回后流程会新建一轮并回到首节点，于是给提交人自己派了"主办单位确认" ——
    # 等于让他自己签自己；而且文件还没重新提交，别人也不该看到它。
    # 所以这里把"版本已回到草稿/修订中"的待办滤掉，它们属于「被退回」那一类。
    draft_ver_ids = {
        v.id for v in versions.values()
        if v.state in (DocumentState.DRAFT.value, DocumentState.REVISING.value)
    }
    my_tasks = [
        t for t in my_tasks
        if not (
            (inst := insts.get(t.instance_id)) is not None
            and inst.biz_type == WorkflowBizType.REVIEW.value
            and inst.biz_id in draft_ver_ids
        )
    ]

    # 提交人（谁提交的，我去签谁的东西）
    submitter_ids = {v.created_by for v in versions.values()}
    users = {
        u.id: u
        for u in (
            db.execute(select(AppUser).where(AppUser.id.in_(submitter_ids))).scalars().all()
            if submitter_ids
            else []
        )
    }

    awaiting: list[dict] = []
    for t in my_tasks:
        inst = insts.get(t.instance_id)
        proj = projects.get(t.project_id)
        ver = versions.get(inst.biz_id) if inst else None
        doc = docs.get(ver.document_id) if ver else None
        submitter = users.get(ver.created_by) if ver else None
        awaiting.append(
            {
                "kind": "AWAITING_ME",
                "task_id": t.id,
                "project_id": t.project_id,
                "project_name": proj.name if proj else None,
                "project_short_name": (proj.short_name if proj else None) or (proj.name if proj else None),
                "stage_code": (doc.stage_code if doc else None) or (inst.stage_code if inst else None),
                "node_code": t.node_code,
                "node_name": t.node_name,
                "my_unit": t.assignee_role,
                "my_unit_label": UNIT_LABELS.get(UnitCode(t.assignee_role), t.assignee_role)
                if t.assignee_role
                else None,
                "document_id": doc.id if doc else None,
                "doc_no": doc.doc_no if doc else None,
                "title": doc.title if doc else None,
                "version_no": ver.version_no if ver else None,
                "version_state": ver.state if ver else None,
                "version_state_label": (
                    DOCUMENT_STATE_LABELS.get(DocumentState(ver.state), ver.state)
                    if ver
                    else None
                ),
                "submitted_by": submitter.name if submitter else None,
                "submitted_by_no": submitter.employee_no if submitter else None,
                "submitted_at": ver.submitted_at if ver else None,
                "due_at": t.due_at,
                "days_left": _days_left(t.due_at),
                "overdue": is_overdue(t.due_at),
                "round": t.round,
            }
        )

    # ---------- 2. 被退回：我提交的，被退回需要我改 ----------
    #
    # 判定方式：版本当前是草稿/修订中，**但存在轮次 > 1 的流程实例**
    # —— 说明它提交过、被退回过，现在要等提交人修改后重交。
    #
    # 不能用审计日志找 "RETURN"：那条日志的操作人是**退回人**而不是我，
    # 按 actor=me 查不到（踩过这个坑）。
    # 也不能只看 created_by：那是"谁建的版本"，不等于"谁提交的"。
    returned_ver_ids: set[str] = {
        row[0]
        for row in db.execute(
            select(WorkflowInstance.biz_id).where(
                WorkflowInstance.biz_type == WorkflowBizType.REVIEW.value,
                WorkflowInstance.round > 1,
            )
        ).all()
    }

    returned: list[dict] = []
    if returned_ver_ids:
        draft_versions = list(
            db.execute(
                select(DocumentVersion)
                .where(
                    DocumentVersion.id.in_(returned_ver_ids),
                    DocumentVersion.state.in_(
                        [DocumentState.DRAFT.value, DocumentState.REVISING.value]
                    ),
                )
                .order_by(DocumentVersion.submitted_at.desc())
                .limit(limit)
            ).scalars().all()
        )
    else:
        draft_versions = []

    for ver in draft_versions:
        doc = db.get(Document, ver.document_id)
        proj = db.get(Project, ver.project_id)

        # 只列"我经手过"的：我建的版本，或我提交过它
        submitted_by_me = ver.created_by == user_id or bool(
            db.execute(
                select(AuditLog.id)
                .where(
                    AuditLog.actor == user_id,
                    AuditLog.action == "SUBMIT",
                    AuditLog.target_id == ver.id,
                )
                .limit(1)
            ).scalar_one_or_none()
        )
        if not submitted_by_me:
            continue

        returned.append(
            {
                "kind": "RETURNED_TO_ME",
                "task_id": None,
                "project_id": ver.project_id,
                "project_name": proj.name if proj else None,
                "project_short_name": (proj.short_name if proj else None)
                or (proj.name if proj else None),
                "stage_code": doc.stage_code if doc else None,
                "node_code": None,
                "node_name": "退回修改",
                "my_unit": None,
                "my_unit_label": None,
                "document_id": doc.id if doc else None,
                "doc_no": doc.doc_no if doc else None,
                "title": doc.title if doc else None,
                "version_no": ver.version_no,
                "version_state": ver.state,
                "version_state_label": DOCUMENT_STATE_LABELS.get(
                    DocumentState(ver.state), ver.state
                ),
                "submitted_by": None,
                "submitted_by_no": None,
                "submitted_at": ver.submitted_at,
                "due_at": None,
                "days_left": None,
                "overdue": False,
                "round": None,
            }
        )

    # ---------- 3. 我经手、仍在流转的（知悉用） ----------
    my_versions = list(
        db.execute(
            select(DocumentVersion)
            .where(
                DocumentVersion.created_by == user_id,
                DocumentVersion.state.in_(
                    [DocumentState.CHECKING.value, DocumentState.REVIEWING.value]
                ),
            )
            .order_by(DocumentVersion.submitted_at.desc())
            .limit(50)
        ).scalars().all()
    )
    inflight: list[dict] = []
    for ver in my_versions:
        doc = db.get(Document, ver.document_id)
        proj = db.get(Project, ver.project_id)
        inst = db.execute(
            select(WorkflowInstance)
            .where(
                WorkflowInstance.biz_type == WorkflowBizType.REVIEW.value,
                WorkflowInstance.biz_id == ver.id,
                WorkflowInstance.status == WorkflowStatus.RUNNING.value,
            )
            .order_by(WorkflowInstance.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        pending_units: list[str] = []
        if inst is not None:
            pend = db.execute(
                select(WorkflowTask.assignee_role).where(
                    WorkflowTask.instance_id == inst.id, WorkflowTask.action.is_(None)
                )
            ).scalars().all()
            pending_units = sorted({u for u in pend if u})
        inflight.append(
            {
                "kind": "INFLIGHT",
                "task_id": None,
                "project_id": ver.project_id,
                "project_name": proj.name if proj else None,
                "project_short_name": (proj.short_name if proj else None) or (proj.name if proj else None),
                "stage_code": doc.stage_code if doc else None,
                "node_code": None,
                "node_name": "在途",
                "my_unit": None,
                "my_unit_label": None,
                "document_id": doc.id if doc else None,
                "doc_no": doc.doc_no if doc else None,
                "title": doc.title if doc else None,
                "version_no": ver.version_no,
                "version_state": ver.state,
                "version_state_label": DOCUMENT_STATE_LABELS.get(
                    DocumentState(ver.state), ver.state
                ),
                "submitted_by": None,
                "submitted_by_no": None,
                "submitted_at": ver.submitted_at,
                "due_at": None,
                "days_left": None,
                "overdue": False,
                "round": None,
                "pending_units": pending_units,
                "pending_unit_labels": [
                    UNIT_LABELS.get(UnitCode(u), u) for u in pending_units
                ],
            }
        )

    return {
        "user_id": user_id,
        "generated_at": _now().isoformat(),
        "awaiting_count": len(awaiting),
        "returned_count": len(returned),
        "inflight_count": len(inflight),
        "overdue_count": sum(1 for a in awaiting if a["overdue"]),
        "awaiting": awaiting,
        "returned": returned,
        "inflight": inflight,
    }


def project_work(db: Session, *, project_id: str, user_id: str) -> dict[str, Any]:
    """单个项目的"交办事项"—— 阶段页与项目总览用。

    与工作台的区别：这里只看一个项目，但**把七个阶段的待办都收进来**，
    便于回答"这个项目现在有哪些事压在人身上"。
    """
    all_work = my_work(db, user_id=user_id)
    in_proj = lambda x: x["project_id"] == project_id  # noqa: E731

    awaiting = [x for x in all_work["awaiting"] if in_proj(x)]
    returned = [x for x in all_work["returned"] if in_proj(x)]
    inflight = [x for x in all_work["inflight"] if in_proj(x)]

    # 按阶段聚合，便于阶段页显示"本阶段有什么要我处理"
    by_stage: dict[str, dict] = {}
    for item in awaiting + returned:
        st = item.get("stage_code") or "UNKNOWN"
        bucket = by_stage.setdefault(
            st,
            {
                "stage_code": st,
                "stage_label": _stage_label(st),
                "awaiting": [],
                "returned": [],
            },
        )
        bucket["awaiting" if item["kind"] == "AWAITING_ME" else "returned"].append(item)

    return {
        "project_id": project_id,
        "generated_at": _now().isoformat(),
        "awaiting_count": len(awaiting),
        "returned_count": len(returned),
        "inflight_count": len(inflight),
        "awaiting": awaiting,
        "returned": returned,
        "inflight": inflight,
        "by_stage": sorted(by_stage.values(), key=lambda x: x["stage_code"]),
    }
