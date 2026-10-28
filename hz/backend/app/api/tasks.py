"""工作流待办与审批轨迹。

这些接口填上了首页"待我处理 / 逾期"和"跨项目待办"的数据源。

权限：待办只返回指派给当前用户的；审批轨迹返回给项目可见成员。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentPrincipal, DbSession, require_project_view
from app.core.types import is_overdue
from app.models.base import utcnow
from app.models.document import Document, DocumentVersion
from app.models.enums import STAGE_LABELS, StageCode, WorkflowBizType
from app.models.org import AppUser
from app.models.project import Project
from app.models.workflow import WorkflowInstance, WorkflowTask
from app.schemas import ApiResponse, WorkflowTaskOut, WorkflowTraceOut
from app.services import workflow as wf

router = APIRouter(prefix="/tasks", tags=["工作流待办"])


def _task_out(db, t: WorkflowTask) -> WorkflowTaskOut:
    assignee_name = None
    if t.assignee:
        u = db.get(AppUser, t.assignee)
        assignee_name = u.name if u else None
    return WorkflowTaskOut(
        id=t.id,
        instance_id=t.instance_id,
        project_id=t.project_id,
        node_code=t.node_code,
        node_name=t.node_name,
        round=t.round,
        assignee=t.assignee,
        assignee_name=assignee_name,
        assignee_role=t.assignee_role,
        action=t.action,
        comment=t.comment,
        due_at=t.due_at,
        acted_at=t.acted_at,
        acted_by=t.acted_by,
        is_self_check=t.is_self_check,
    )


def _enrich(db, tasks: list[WorkflowTask]) -> list[dict]:
    """给待办补上"这是什么文件/项目/阶段"，否则用户看不懂待办是什么。

    前端待办表格要显示"桩型选型方案复核 / 杭州商业综合体 · 设计"这类信息。
    """
    if not tasks:
        return []

    inst_ids = {t.instance_id for t in tasks}
    insts = {
        i.id: i
        for i in db.execute(select(WorkflowInstance).where(WorkflowInstance.id.in_(inst_ids)))
        .scalars()
        .all()
    }

    # 业务对象标题
    version_ids = {
        i.biz_id for i in insts.values() if i.biz_type == WorkflowBizType.REVIEW.value
    }
    version_map: dict[str, DocumentVersion] = {}
    doc_map: dict[str, Document] = {}
    if version_ids:
        for v in db.execute(
            select(DocumentVersion).where(DocumentVersion.id.in_(version_ids))
        ).scalars().all():
            version_map[v.id] = v
        doc_ids = {v.document_id for v in version_map.values()}
        if doc_ids:
            for d in db.execute(select(Document).where(Document.id.in_(doc_ids))).scalars().all():
                doc_map[d.id] = d

    project_ids = {t.project_id for t in tasks}
    proj_map = {
        p.id: p
        for p in db.execute(select(Project).where(Project.id.in_(project_ids))).scalars().all()
    }

    now = utcnow()
    out: list[dict] = []
    for t in tasks:
        inst = insts.get(t.instance_id)
        biz_title = None
        stage_code = inst.stage_code if inst else None

        if inst and inst.biz_type == WorkflowBizType.REVIEW.value:
            v = version_map.get(inst.biz_id)
            if v:
                d = doc_map.get(v.document_id)
                biz_title = f"{d.title} {v.version_no}" if d else f"文件版本 {v.version_no}"
                if d and not stage_code:
                    stage_code = d.stage_code
        elif inst:
            biz_title = f"{inst.biz_type} {inst.biz_id[:8]}"

        proj = proj_map.get(t.project_id)
        stage_label = None
        if stage_code:
            try:
                stage_label = STAGE_LABELS[StageCode(stage_code)]
            except (ValueError, KeyError):
                stage_label = stage_code

        item = _task_out(db, t).model_dump()
        item.update(
            {
                "biz_title": biz_title,
                "project_name": proj.name if proj else None,
                "project_short_name": (proj.short_name if proj else None) or (proj.name if proj else None),
                "stage_code": stage_code,
                "stage_label": stage_label,
                # 用 is_overdue() 而不是直接比较 —— SQLite 读回的时间是 naive
                "overdue": is_overdue(t.due_at, now),
                "biz_type": inst.biz_type if inst else None,
                "biz_id": inst.biz_id if inst else None,
            }
        )
        out.append(item)
    return out


@router.get("/my", response_model=ApiResponse[list[dict]], summary="我的待办（可跨项目）")
def my_tasks(
    db: DbSession,
    principal: CurrentPrincipal,
    project_id: str | None = None,
    overdue_only: bool = False,
) -> ApiResponse[list[dict]]:
    """我的待办。

    **不传 project_id 时跨全部项目** —— 这是"一人多项目"场景的刚需：
    设计师不会逐个点进项目去看有没有活干。
    """
    if project_id:
        require_project_view(project_id, principal)

    tasks = wf.my_pending_tasks(db, principal.user_id, project_id)
    items = _enrich(db, tasks)

    if overdue_only:
        items = [i for i in items if i["overdue"]]

    # 逾期优先，其次按截止时间
    items.sort(key=lambda i: (not i["overdue"], i["due_at"] or "9999"))
    return ApiResponse(data=items)


@router.get("/instances/{instance_id}", response_model=ApiResponse[WorkflowTraceOut],
            summary="审批轨迹")
def instance_trace(
    instance_id: str, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[WorkflowTraceOut]:
    """完整审批轨迹。

    历轮退回的记录**全部保留** —— 可以回答
    "这份图纸被退回过几次、每次是谁提了什么意见"。
    """
    inst = db.get(WorkflowInstance, instance_id)
    if inst is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": 4004, "message": "流程实例不存在"},
        )
    require_project_view(inst.project_id, principal)

    tasks = wf.instance_tasks(db, instance_id)
    initiator_name = None
    if inst.initiator:
        u = db.get(AppUser, inst.initiator)
        initiator_name = u.name if u else None

    return ApiResponse(
        data=WorkflowTraceOut(
            instance_id=inst.id,
            biz_type=inst.biz_type,
            status=inst.status,
            current_node=inst.current_node,
            round=inst.round,
            initiator=initiator_name or inst.initiator,
            started_at=inst.started_at,
            finished_at=inst.finished_at,
            tasks=[_task_out(db, t) for t in tasks],
        )
    )


@router.get("/versions/{version_id}/trace", response_model=ApiResponse[WorkflowTraceOut | None],
            summary="按版本查审批轨迹")
def version_trace(
    version_id: str, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[WorkflowTraceOut | None]:
    """前端版本详情抽屉用：直接按 version_id 拿审批轨迹。"""
    v = db.get(DocumentVersion, version_id)
    if v is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": 4004, "message": "文件版本不存在"},
        )
    require_project_view(v.project_id, principal)

    inst = db.execute(
        select(WorkflowInstance)
        .where(
            WorkflowInstance.biz_type == WorkflowBizType.REVIEW.value,
            WorkflowInstance.biz_id == version_id,
        )
        .order_by(WorkflowInstance.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    if inst is None:
        return ApiResponse(data=None, message="该版本尚未提交审批")

    return instance_trace(inst.id, db, principal)
