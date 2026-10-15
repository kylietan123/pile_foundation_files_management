"""文档台账与追溯服务。

**这是整个平台最核心的一屏** —— 回答三个问题：

    1. 这个项目现在有哪些文件、是什么版本、生效了没有？
    2. 每份文件是谁上传的、谁签认的？
    3. **文件现在在谁手上**（卡在哪个单位）？

用户提出的痛点是"工程干了几年，文件找不到了不知道谁负责"，
所以这一屏的重点不是"展示文件"，而是**让责任一直看得见**：

    - 每份文件都写明**主办单位**（该阶段矩阵里的主要责任单位）
    - 每次流转都记下**操作人姓名 + 工号**（用户明确要求）
    - 当前待签单位直接列出来 —— 这就是"文件在谁手上"

不引入新表：全部由 document / document_version / workflow_task /
audit_log 推导，保证与版本状态机、流程引擎的判定永远一致。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentVersion
from app.models.enums import (
    DOCUMENT_STATE_LABELS,
    RESPONSIBILITY_LABELS,
    STAGE_LABELS,
    UNIT_LABELS,
    DocumentState,
    Responsibility,
    StageCode,
    UnitCode,
    WorkflowBizType,
    WorkflowStatus,
    primary_unit_of_stage,
)
from app.models.org import AppUser
from app.models.workflow import WorkflowInstance, WorkflowTask


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _user_brief(users: dict[str, AppUser], uid: str | None) -> dict | None:
    """操作人简要信息 —— **姓名 + 工号**，用户要求"谁做的要看得见"。"""
    if not uid:
        return None
    u = users.get(uid)
    if u is None:
        return {"id": uid, "name": None, "employee_no": None}
    return {"id": u.id, "name": u.name, "employee_no": u.employee_no}


def _load_users(db: Session, ids: set[str]) -> dict[str, AppUser]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    rows = db.execute(select(AppUser).where(AppUser.id.in_(ids))).scalars().all()
    return {u.id: u for u in rows}


def build_ledger(
    db: Session,
    *,
    project_id: str,
    stage_code: str | None = None,
    only_awaiting_me: str | None = None,
    max_secret_level: int = 2,
) -> dict[str, Any]:
    """生成项目文档台账。

    参数：
        stage_code       只看某阶段
        only_awaiting_me 只列"等我处理"的（传当前用户 id）
        max_secret_level 可查看的最高敏感等级（权限引擎给出）
    """
    # ---- 1. 取文件（在 SQL 层按阶段过滤）----
    stmt = select(Document).where(Document.project_id == project_id)
    if stage_code:
        stmt = stmt.where(Document.stage_code == stage_code)
    docs = list(db.execute(stmt.order_by(Document.created_at.desc())).scalars().all())

    # 敏感等级过滤
    secret_order = {"PUBLIC": 0, "INTERNAL": 1, "RESTRICTED": 2, "SECRET": 3}
    docs = [d for d in docs if secret_order.get(d.secret_level, 1) <= max_secret_level]

    if not docs:
        return {
            "project_id": project_id,
            "stage_code": stage_code,
            "generated_at": _now().isoformat(),
            "item_count": 0,
            "awaiting_count": 0,
            "items": [],
        }

    doc_ids = [d.id for d in docs]

    # ---- 2. 取这些文件的全部版本 ----
    versions = list(
        db.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id.in_(doc_ids))
            .order_by(DocumentVersion.created_at)
        ).scalars().all()
    )
    ver_by_doc: dict[str, list[DocumentVersion]] = {}
    for v in versions:
        ver_by_doc.setdefault(v.document_id, []).append(v)

    # ---- 3. 取这些版本的流程实例与任务 ----
    ver_ids = [v.id for v in versions]
    insts = (
        list(
            db.execute(
                select(WorkflowInstance).where(
                    WorkflowInstance.biz_type == WorkflowBizType.REVIEW.value,
                    WorkflowInstance.biz_id.in_(ver_ids),
                )
            ).scalars().all()
        )
        if ver_ids
        else []
    )
    inst_by_ver = {i.biz_id: i for i in insts}
    inst_ids = [i.id for i in insts]
    tasks = (
        list(
            db.execute(
                select(WorkflowTask)
                .where(WorkflowTask.instance_id.in_(inst_ids))
                .order_by(WorkflowTask.created_at)
            ).scalars().all()
        )
        if inst_ids
        else []
    )
    tasks_by_inst: dict[str, list[WorkflowTask]] = {}
    for t in tasks:
        tasks_by_inst.setdefault(t.instance_id, []).append(t)

    # ---- 4. 收集所有涉及的人，一次性查名字 ----
    uids: set[str] = set()
    for v in versions:
        uids |= {v.created_by, v.published_by, v.voided_by}
    for t in tasks:
        uids |= {t.assignee, t.acted_by}
    users = _load_users(db, uids)

    # ---- 5. 组装每一行 ----
    items: list[dict[str, Any]] = []
    for d in docs:
        vs = ver_by_doc.get(d.id, [])
        current = next((v for v in vs if v.id == d.current_version_id), None)
        latest = vs[-1] if vs else None

        # 主办单位：该阶段矩阵里的主要责任单位 —— 文件丢了找它
        primary_unit = primary_unit_of_stage(d.stage_code)

        # 当前在途版本的流转状态
        inflight = next(
            (
                v
                for v in vs
                if v.state
                in (
                    DocumentState.CHECKING.value,
                    DocumentState.REVIEWING.value,
                )
            ),
            None,
        )

        # **签认轨迹要取"最近一次流程"，不能只看在途版本** ——
        # 签完之后就没有在途版本了，若此时丢掉流程实例，
        # 轨迹（谁签的、什么时候）就查不到了，而这恰恰是追溯最需要的信息。
        recent_inst = None
        for v in reversed(vs):                      # 从最新版本往前找
            inst_i = inst_by_ver.get(v.id)
            if inst_i is not None:
                recent_inst = inst_i
                break
        # 有在途版本时优先显示它的流程（更贴合"现在在谁手上"）
        inst = inst_by_ver.get(inflight.id) if inflight else recent_inst
        trace_inst = inst or recent_inst

        pending = [
            t
            for t in (tasks_by_inst.get(inst.id, []) if inst else [])
            if t.action is None
        ]
        pending_units = sorted({t.assignee_role for t in pending if t.assignee_role})

        # 签认轨迹（只取已处理的，按时间）
        trace = [
            {
                "node_code": t.node_code,
                "node_name": t.node_name,
                "unit_code": t.assignee_role,
                "unit_label": UNIT_LABELS.get(UnitCode(t.assignee_role), t.assignee_role)
                if t.assignee_role
                else None,
                "action": t.action,
                "comment": t.comment,
                "actor": _user_brief(users, t.acted_by),
                "acted_at": t.acted_at,
                "round": t.round,
            }
            for t in (tasks_by_inst.get(trace_inst.id, []) if trace_inst else [])
            if t.action is not None
        ]
        # 流程是否已走完（用于界面显示"已签认完成"）
        workflow_finished = bool(
            trace_inst is not None and trace_inst.status == WorkflowStatus.FINISHED.value
        )

        awaiting_me = bool(
            only_awaiting_me
            and any(t.assignee == only_awaiting_me for t in pending)
        )
        if only_awaiting_me and not awaiting_me:
            continue

        # 这份文件"当前应该看的状态"：在途优先，其次已发布，最后最新版本
        _eff = inflight or current or latest

        items.append(
            {
                "document_id": d.id,
                "doc_no": d.doc_no,
                "title": d.title,
                "category_name": d.category_name,
                "stage_code": d.stage_code,
                "stage_label": STAGE_LABELS.get(StageCode(d.stage_code), d.stage_code)
                if d.stage_code
                else None,
                "discipline": d.discipline,
                "secret_level": d.secret_level,
                # ---- 版本情况 ----
                # effective = 这份文件"当前应该看的状态"：
                #   有在途版本 → 在途（正在签认，这才是有意义的状态）
                #   否则 → 已发布版本；都没有 → 最新版本
                # 只报 current（已发布）会让"还没发布过、正在签认"的文件
                # 状态显示为空 —— 那恰恰是最需要看到状态的时刻。
                "effective_version_no": _eff.version_no if _eff else None,
                "effective_state": _eff.state if _eff else None,
                "effective_state_label": (
                    DOCUMENT_STATE_LABELS.get(DocumentState(_eff.state), _eff.state)
                    if _eff
                    else None
                ),
                "current_version_no": current.version_no if current else None,
                "current_state": current.state if current else None,
                "current_state_label": (
                    DOCUMENT_STATE_LABELS.get(DocumentState(current.state), current.state)
                    if current
                    else None
                ),
                "latest_version_no": latest.version_no if latest else None,
                "latest_state": latest.state if latest else None,
                "version_count": len(vs),
                # ---- 责任落点 ----
                "primary_unit": primary_unit,
                "primary_unit_label": (
                    UNIT_LABELS.get(UnitCode(primary_unit), primary_unit)
                    if primary_unit
                    else None
                ),
                # ---- 谁做的 ----
                "created_by": _user_brief(users, d.created_by),
                "current_uploaded_by": _user_brief(users, current.created_by) if current else None,
                "current_uploaded_at": current.created_at if current else None,
                "published_by": _user_brief(users, current.published_by) if current else None,
                "published_at": current.published_at if current else None,
                # ---- 文件现在在谁手上 ----
                "inflight_version_no": inflight.version_no if inflight else None,
                "pending_units": pending_units,
                "pending_unit_labels": [
                    UNIT_LABELS.get(UnitCode(u), u) for u in pending_units
                ],
                "waits_on": (
                    "已完成"
                    if not pending
                    else "、".join(UNIT_LABELS.get(UnitCode(u), u) for u in pending_units)
                ),
                # 待签任务数：与"已签次数"分开返回。
                # 否则界面会把"这份文件还没提交"和"提交了在等人签"混为一谈 ——
                # 前者没有一个待办任务，后者有，必须能区分。
                "pending_count": len(pending),
                "awaiting_me": awaiting_me,
                "workflow_finished": workflow_finished,
                # ---- 签认轨迹 ----
                "trace": trace,
            }
        )

    awaiting_total = sum(1 for i in items if i["awaiting_me"]) if only_awaiting_me else 0

    return {
        "project_id": project_id,
        "stage_code": stage_code,
        "generated_at": _now().isoformat(),
        "item_count": len(items),
        "awaiting_count": awaiting_total,
        "items": items,
    }


def stage_responsibility_summary(db: Session, project_id: str) -> list[dict]:
    """七阶段的"谁负责 + 文件在谁手上"总览。

    这是给项目总览页用的：一眼看出每个阶段的主办单位，
    以及当前有没有文件卡在签认环节。
    """
    from app.core.permissions import stage_responsibility_board

    board = stage_responsibility_board()

    # 统计每阶段"卡住"的文件数（有在途版本等着签）
    rows = list(
        db.execute(
            select(DocumentVersion, Document)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(
                Document.project_id == project_id,
                DocumentVersion.state.in_(
                    [DocumentState.CHECKING.value, DocumentState.REVIEWING.value]
                ),
            )
        ).all()
    )
    inflight_by_stage: dict[str, int] = {}
    for ver, doc in rows:
        inflight_by_stage[doc.stage_code] = inflight_by_stage.get(doc.stage_code, 0) + 1

    out: list[dict] = []
    for row in board:
        st = row["stage_code"]
        out.append(
            {
                **row,
                "stage_label": STAGE_LABELS.get(StageCode(st), st),
                "inaround_count": inflight_by_stage.get(st, 0),
                "units_detail": [
                    {
                        **u,
                        "unit_label": UNIT_LABELS.get(UnitCode(u["unit_code"]), u["unit_code"]),
                        "responsibility_label": RESPONSIBILITY_LABELS.get(
                            Responsibility(u["responsibility"]), u["responsibility"]
                        ),
                    }
                    for u in row["units"]
                ],
            }
        )
    return out
