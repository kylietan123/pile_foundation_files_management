"""工作流服务 —— 两级签认。

    CONFIRM   主办单位确认  →  提交人代表本单位负责
    REVIEW    相关单位复核  →  次要责任单位过一遍，可确认也可提意见

**为什么从三级（校核/审核/批准）降为两级**：
    主体改为「单位」之后，校核人与审核人往往同属设计院，
    平台无法也不该管到单位内部分工。两级正好对应
    《管理流程》矩阵里每列的 ** 与 *，责任落点更清楚 ——
    文件丢了，找主办单位。

**单位内不区分岗位**：节点按**单位**派任务，
该单位在项目里的任何人都能处理，谁处理就记谁的名字。
所以相关单位有多个时，会生成多条并列任务（各签各的）。

退回语义：
    退回**不覆盖历史意见**，而是新建一轮任务（round + 1），
    这样"这份文件被退回过几次、每次谁提了什么意见"完全可追溯。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import (
    RESPONSIBILITY_MATRIX,
    DocumentState,
    Responsibility,
    TaskAction,
    UnitCode,
    WorkflowBizType,
    WorkflowNodeCode,
    WorkflowStatus,
    primary_unit_of_stage,
    responsibility_of,
    stages_of_unit,
)
from app.models.project import ProjectMember
from app.models.workflow import WorkflowInstance, WorkflowTask, WorkflowTemplate

logger = logging.getLogger("app.workflow")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class WorkflowError(HTTPException):
    def __init__(self, message: str, code: int = 4002):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": code, "message": message},
        )


# ============================================================
# 默认流程模板定义（种子数据与迁移用）
# ============================================================

#: 两级签认模板。unit 为占位符时按下表解析：
#:   {PRIMARY}  = 该阶段的主办单位
#:   {RELATED}  = 该阶段的全部次要责任单位（可能多个，各生成一条任务）
DEFAULT_REVIEW_NODES: list[dict] = [
    {
        "code": WorkflowNodeCode.CONFIRM.value,
        "name": "主办单位确认",
        "unit": "{PRIMARY}",
        "sort": 1,
        "desc": "主办单位确认文件内容，代表本单位负责",
    },
    {
        "code": WorkflowNodeCode.REVIEW.value,
        "name": "相关单位复核",
        "unit": "{RELATED}",
        "sort": 2,
        "desc": "次要责任单位复核，确认或提出意见",
    },
]


# ============================================================
# 模板
# ============================================================


def get_template(
    db: Session, biz_type: str, stage_code: str | None = None
) -> WorkflowTemplate:
    """取适用的流程模板。优先匹配具体阶段，退回到 stage_code 为空的通用模板。"""
    candidates = list(
        db.execute(
            select(WorkflowTemplate).where(
                WorkflowTemplate.biz_type == biz_type,
                WorkflowTemplate.active.is_(True),
            )
        ).scalars().all()
    )
    if not candidates:
        raise WorkflowError(f"未找到 biz_type={biz_type} 的流程模板", code=4004)

    if stage_code:
        for t in candidates:
            if t.stage_code == stage_code:
                return t
    for t in candidates:
        if not t.stage_code:
            return t
    return candidates[0]


def _nodes_of(template: WorkflowTemplate) -> list[dict]:
    return sorted(template.nodes or [], key=lambda n: n.get("sort", 0))


# ============================================================
# 按单位解析处理人
# ============================================================


def _members_of_unit(db: Session, project_id: str, unit_code: str) -> list[str]:
    """取项目内某单位的全部在册成员。

    返回列表而不是单个 —— 因为**单位内任何人都能处理**，
    由谁处理由"谁先点"决定，不预先指派到个人。
    """
    return list(
        db.execute(
            select(ProjectMember.user_id)
            .where(
                ProjectMember.project_id == project_id,
                ProjectMember.role_code == unit_code,
                ProjectMember.revoked_at.is_(None),
            )
            .order_by(ProjectMember.granted_at)
        ).scalars().all()
    )


def units_for_node(node: dict, stage_code: str | None) -> list[str]:
    """把节点上的单位占位符解析成具体单位码列表。

    支持三种写法：
        "DESIGNER"     固定单位
        "{PRIMARY}"    该阶段主办单位（主要责任）
        "{RELATED}"    该阶段**需要过一遍**的单位 ——
                       次要责任单位 + 政府审查单位

    为什么 {RELATED} 要包含审查单位：
        政府审查单位在矩阵里是 VERIFIER（只读 + 留审查意见），
        它不承担阶段管理责任，但**必须有一道审查**。
        如果复核节点只要 RELATED，政府审查就没有落地的入口，
        "只读 + 审查意见"就成了空话。
        两者的区别体现在动作上：RELATED 能"签认"，VERIFIER 只能"提意见"。
    """
    spec = (node.get("unit") or "").strip()
    if not spec:
        return []
    if spec == "{PRIMARY}":
        u = primary_unit_of_stage(stage_code or "")
        return [u] if u else []
    if spec == "{RELATED}":
        units = RESPONSIBILITY_MATRIX.get(stage_code or "", {})
        return [
            u
            for u, r in units.items()
            if r in (Responsibility.RELATED, Responsibility.VERIFIER)
        ]
    return [spec]


def _assign_node(
    db: Session,
    inst: WorkflowInstance,
    template: WorkflowTemplate,
    node: dict,
    *,
    round_no: int,
    due_days: int,
) -> list[WorkflowTask]:
    """为节点生成待办任务，按**单位**派发。

    一个节点可能对应多个单位（如"相关单位复核"），
    此时生成多条并列任务，各单位各签各的。
    """
    units = units_for_node(node, inst.stage_code)
    if not units:
        logger.warning(
            "节点 %s 未解析出任何单位（stage=%s, spec=%s），流程可能卡住",
            node.get("code"), inst.stage_code, node.get("unit"),
        )

    created: list[WorkflowTask] = []
    for unit in units:
        members = _members_of_unit(db, inst.project_id, unit)
        if not members:
            logger.warning(
                "阶段 %s 的节点「%s」要求单位 %s，但该项目里没有该单位的成员 —— "
                "任务将处于未指派状态，提交人应先补齐参与单位。",
                inst.stage_code, node.get("name"), unit,
            )
            members = [None]  # 生成未指派任务，界面可见、可提醒，而不是静默消失

        for uid in members:
            task = WorkflowTask(
                instance_id=inst.id,
                project_id=inst.project_id,
                node_code=node["code"],
                node_name=node.get("name"),
                round=round_no,
                assignee=uid,
                assignee_role=unit,          # 语义：承办单位
                due_at=_now() + timedelta(days=due_days),
                is_self_check=False,
            )
            db.add(task)
            created.append(task)

    db.flush()
    return created


def missing_units(
    db: Session, *, project_id: str, template: WorkflowTemplate, stage_code: str | None
) -> list[dict]:
    """检查模板要求的单位在项目里是否都有人。

    返回缺失项。**空列表表示流程可以正常流转。**

    这个检查必须在提交前做 —— 否则任务会派给"空单位"，
    流程卡住而用户不知道原因（这是踩过的坑）。
    """
    missing: list[dict] = []
    for node in _nodes_of(template):
        for unit in units_for_node(node, stage_code):
            if not _members_of_unit(db, project_id, unit):
                missing.append(
                    {
                        "node_code": node["code"],
                        "node_name": node.get("name"),
                        "required_unit": unit,
                    }
                )
    return missing


def check_units_staffed(
    db: Session, *, project_id: str, template: WorkflowTemplate, stage_code: str | None
) -> list[dict]:
    """兼容旧名（原 check_roles_staffed）。"""
    return missing_units(db, project_id=project_id, template=template, stage_code=stage_code)


# ============================================================
# 启动流程
# ============================================================


def start_workflow(
    db: Session,
    *,
    project_id: str,
    biz_type: str,
    biz_id: str,
    initiator_id: str,
    stage_code: str | None = None,
    due_days: int = 3,
    skip_first_node: bool = False,
) -> WorkflowInstance:
    """启动流程并为当前节点创建待办任务。"""
    template = get_template(db, biz_type, stage_code)
    nodes = _nodes_of(template)
    if not nodes:
        raise WorkflowError("流程模板未定义任何节点")

    start_idx = 1 if (skip_first_node and len(nodes) > 1) else 0

    inst = WorkflowInstance(
        template_id=template.id,
        project_id=project_id,
        biz_type=biz_type,
        biz_id=biz_id,
        stage_code=stage_code,
        status=WorkflowStatus.RUNNING.value,
        current_node=nodes[start_idx]["code"],
        round=1,
        initiator=initiator_id,
        started_at=_now(),
    )
    db.add(inst)
    db.flush()

    _assign_node(db, inst, template, nodes[start_idx], round_no=1, due_days=due_days)
    return inst


def current_task(db: Session, instance_id: str) -> WorkflowTask | None:
    """取一条当前待处理任务（action 为空）。"""
    return db.execute(
        select(WorkflowTask)
        .where(WorkflowTask.instance_id == instance_id, WorkflowTask.action.is_(None))
        .order_by(WorkflowTask.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def pending_tasks_of_node(db: Session, instance_id: str, node_code: str) -> list[WorkflowTask]:
    """当前节点下**全部**未处理任务。

    用于"相关单位有多个"的场景：必须**全部处理完**才推进到下一节点。
    """
    return list(
        db.execute(
            select(WorkflowTask).where(
                WorkflowTask.instance_id == instance_id,
                WorkflowTask.node_code == node_code,
                WorkflowTask.action.is_(None),
            )
        ).scalars().all()
    )


# ============================================================
# 处理任务
# ============================================================


def decide(
    db: Session,
    *,
    task_id: str,
    actor_id: str,
    action: str,
    comment: str | None = None,
    allow_self_check: bool = False,
    max_rounds: int = 5,
) -> WorkflowInstance:
    """处理当前节点任务。

    关键差异（相对旧的三级校审）：
      **不再要求"节点由不同人完成"** —— 因为主体是单位，
      同一单位的经办人可能经手多个节点，这是正常的。
      责任由"任务上记录了承办单位 + 操作人"来落实。
      但**同一流程内同一人签认两次**仍会被拦（除非显式自校），
      防止"一个人把主办和相关都签了"。
    """
    task = db.get(WorkflowTask, task_id)
    if task is None:
        raise WorkflowError("任务不存在", code=4004)
    if task.action is not None:
        raise WorkflowError("该任务已处理，不能重复处理")
    if task.assignee and task.assignee != actor_id:
        raise WorkflowError("该任务由其他成员处理，你无权代替", code=3003)

    inst = db.get(WorkflowInstance, task.instance_id)
    if inst is None:
        raise WorkflowError("流程实例不存在", code=4004)
    if inst.status != WorkflowStatus.RUNNING.value:
        raise WorkflowError(f"流程已{inst.status}，不能继续处理")

    if action not in {a.value for a in TaskAction}:
        raise WorkflowError(f"非法的处理动作 {action}")

    template = db.get(WorkflowTemplate, inst.template_id)
    nodes = _nodes_of(template)
    node_codes = [n["code"] for n in nodes]

    # ---- 防"一个人签完全流程" ----
    prev = db.execute(
        select(WorkflowTask).where(
            WorkflowTask.instance_id == inst.id, WorkflowTask.action.is_not(None)
        )
    ).scalars().all()
    if any(t.acted_by == actor_id for t in prev):
        if not (template.allow_self_check and allow_self_check):
            raise WorkflowError(
                "同一人在本流程中已签认过。如确需一人处理全部节点，"
                "请走自校流程（前台会显著标注并留痕）。",
                code=4003,
            )
        task.is_self_check = True

    # ---- 记录处理结果 ----
    task.action = action
    task.comment = comment
    task.acted_at = _now()
    task.acted_by = actor_id

    # **必须先 flush**：下面要查"本节点还有没有未处理任务"，
    # 而这个刚改过的任务还在 session 里没落库，不 flush 会把它自己
    # 也算成"未处理"，节点永远推不动（踩过的坑）。
    db.flush()

    # ---- 退回 / 驳回：新建一轮回到首节点 ----
    if action != TaskAction.APPROVE.value:
        if inst.round >= max_rounds:
            raise WorkflowError(
                f"已退回 {inst.round} 轮，超过上限，请线下处理后再提交", code=4003
            )
        # 作废本轮剩余未处理任务，避免悬挂
        for t in pending_tasks_of_node(db, inst.id, task.node_code):
            t.action = TaskAction.RETURN.value
            t.comment = "（本轮退回，自动结束）"
            t.acted_at = _now()
        inst.round += 1
        first = nodes[0]
        inst.current_node = first["code"]
        _assign_node(db, inst, template, first, round_no=inst.round, due_days=3)
        db.flush()
        return inst

    # ---- 通过：本节点是否还有其他单位未处理 ----
    remaining = pending_tasks_of_node(db, inst.id, task.node_code)
    if remaining:
        # 并列任务，等其他单位签完再推进
        db.flush()
        return inst

    # ---- 推进到下一节点 ----
    idx = node_codes.index(task.node_code)
    if idx + 1 < len(nodes):
        next_node = nodes[idx + 1]
        inst.current_node = next_node["code"]
        _assign_node(db, inst, template, next_node, round_no=inst.round, due_days=3)
    else:
        inst.status = WorkflowStatus.FINISHED.value
        inst.current_node = None
        inst.finished_at = _now()

    db.flush()
    return inst


def instance_tasks(db: Session, instance_id: str) -> list[WorkflowTask]:
    """流程全部任务记录（含历轮退回意见，用于展示签认轨迹）。"""
    return list(
        db.execute(
            select(WorkflowTask)
            .where(WorkflowTask.instance_id == instance_id)
            .order_by(WorkflowTask.created_at)
        ).scalars().all()
    )


def my_pending_tasks(
    db: Session, user_id: str, project_id: str | None = None, limit: int = 200
) -> list[WorkflowTask]:
    """我的待办（可按项目过滤）。"""
    stmt = select(WorkflowTask).where(
        WorkflowTask.assignee == user_id, WorkflowTask.action.is_(None)
    )
    if project_id:
        stmt = stmt.where(WorkflowTask.project_id == project_id)
    return list(
        db.execute(
            stmt.order_by(WorkflowTask.due_at.is_(None), WorkflowTask.due_at).limit(limit)
        ).scalars().all()
    )


def progress_of(db: Session, instance_id: str) -> dict:
    """流程进度概览 —— 界面显示"现在卡在哪个单位"。

    这是文档管理最需要的信息：文件现在在谁手上。
    """
    inst = db.get(WorkflowInstance, instance_id)
    if inst is None:
        return {}
    tasks = instance_tasks(db, instance_id)
    pending = [t for t in tasks if t.action is None]
    return {
        "instance_id": instance_id,
        "status": inst.status,
        "current_node": inst.current_node,
        "round": inst.round,
        "pending_count": len(pending),
        "pending_units": sorted({t.assignee_role for t in pending if t.assignee_role}),
        "waiting_on": (
            "已完成" if inst.status == WorkflowStatus.FINISHED.value
            else "、".join(
                sorted(
                    {
                        (t.node_name or t.node_code)
                        + (f"（{t.assignee_role}）" if t.assignee_role else "")
                        for t in pending
                    }
                )
            )
        ),
    }
