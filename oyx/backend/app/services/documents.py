"""文档与版本服务 —— 版本状态机的唯一权威。

状态机：
    DRAFT 草稿 → CHECKING 校核中 → REVIEWING 审核中 → APPROVED 已批准 → PUBLISHED 已发布
                                                                          ↓
                                                                      VOID 已作废
    修订循环：PUBLISHED --发起修订--> REVISING 修订中 --> CHECKING ...
    退回：任一审批节点退回 → 回到 DRAFT（流程 round + 1）

四条铁律（**后端强制拦截，不依赖前端**）：
  1. 未发布（PUBLISHED 之外）的版本不可被下游引用。
     → assert_published()，任何"引用文件"的地方都必须先调它。
  2. 同一 document 不允许同时存在两个处于审批中的版本（防版本分叉）。
  3. PUBLISHED 不可回退，要改就发新版本。
  4. 同一 document 同一时刻最多一个 PUBLISHED 版本；
     作废必须填原因，且不允许物理删除。
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentRelation, DocumentVersion
from app.models.enums import (
    DOCUMENT_STATE_LABELS,
    DocumentState,
    NON_PUBLISHABLE_STATES,
    WorkflowBizType,
    WorkflowStatus,
)
from app.models.workflow import WorkflowInstance
from app.services import workflow as wf


def _now() -> datetime:
    return datetime.now(timezone.utc)


class VersionRuleError(HTTPException):
    """业务规则错误（4000 段）。"""

    def __init__(self, message: str, code: int = 4001):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": code, "message": message},
        )


# ============================================================
# 铁律 1：未发布版本不可被下游引用
# ============================================================


def assert_published(db: Session, version_id: str | None, purpose: str = "引用") -> DocumentVersion:
    """断言某版本已发布，否则拒绝。

    **任何"引用文件"的接口都必须先调用它。**
    purpose 用于给出人话错误提示（例如"施工"、"变更"、"成果交付"）。
    """
    if not version_id:
        raise VersionRuleError(f"{purpose}时必须指定文件版本", code=1001)

    v = db.get(DocumentVersion, version_id)
    if v is None:
        raise VersionRuleError("指定的文件版本不存在", code=4004)

    if v.state != DocumentState.PUBLISHED.value:
        label = DOCUMENT_STATE_LABELS.get(DocumentState(v.state), v.state)
        raise VersionRuleError(
            f"该版本当前为「{label}」，不能用于{purpose}。"
            f"只有「已发布」版本才可被下游引用 —— 请先完成校审并发布。",
            code=4001,
        )
    return v


def published_version_of(db: Session, document_id: str) -> DocumentVersion | None:
    """取某文档当前的有效（已发布）版本。"""
    return db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.state == DocumentState.PUBLISHED.value,
        )
    ).scalar_one_or_none()


# ============================================================
# 铁律 2：不允许同时存在两个审批中的版本
# ============================================================

# 视为"审批中"的状态
IN_REVIEW_STATES = {
    DocumentState.CHECKING.value,
    DocumentState.REVIEWING.value,
    DocumentState.APPROVED.value,
}


def assert_no_inflight(db: Session, document_id: str) -> None:
    """断言该文档没有正在审批中的版本。"""
    row = db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.state.in_(IN_REVIEW_STATES),
        )
    ).scalars().first()
    if row is not None:
        label = DOCUMENT_STATE_LABELS.get(DocumentState(row.state), row.state)
        raise VersionRuleError(
            f"该文件已有版本 {row.version_no} 处于「{label}」，"
            f"同一文件不允许同时存在两个审批中的版本。请先完成或退回该版本。",
            code=4002,
        )


# ============================================================
# 版本创建
# ============================================================


def create_version(
    db: Session,
    *,
    document: Document,
    file_id: str,
    version_no: str | None = None,
    change_summary: str | None = None,
    creator_id: str | None = None,
    from_change_id: str | None = None,
    remark: str | None = None,
) -> DocumentVersion:
    """新建一个草稿版本。

    version_no 不传时自动递增：取该文档现有最大版本号 +0.1。
    """
    assert_no_inflight(db, document.id)

    existing = db.execute(
        select(DocumentVersion).where(DocumentVersion.document_id == document.id)
    ).scalars().all()

    if version_no is None:
        version_no = _next_version_no([v.version_no for v in existing])

    if any(v.version_no == version_no for v in existing):
        raise VersionRuleError(f"版本号 {version_no} 已存在", code=1001)

    # 新版本默认继承被替代的已发布版本
    prev_published = published_version_of(db, document.id)

    v = DocumentVersion(
        document_id=document.id,
        project_id=document.project_id,
        version_no=version_no,
        revision=len(existing),
        file_id=file_id,
        state=DocumentState.DRAFT.value,
        change_summary=change_summary,
        remark=remark,
        created_by=creator_id,
        from_change_id=from_change_id,
        supersedes_version_id=prev_published.id if prev_published else None,
    )
    db.add(v)
    db.flush()
    return v


def _next_version_no(version_nos: list[str]) -> str:
    """自动生成下一个版本号。

    支持 V1.0 / V1.1 与 A / B / C 两种命名习惯。
    优先跟随已有命名风格；没有历史时用 V1.0。
    """
    if not version_nos:
        return "V1.0"

    # 形如 V1.2
    numeric = [s for s in version_nos if s.upper().startswith("V") and "." in s]
    if numeric:
        def key(s: str) -> tuple[int, int]:
            parts = s[1:].split(".")
            try:
                return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
            except ValueError:
                return (0, 0)

        major, minor = max(key(s) for s in numeric)
        return f"V{major}.{minor + 1}"

    # 形如 A / B / C（单字母）
    single = [s for s in version_nos if len(s) == 1 and s.isalpha()]
    if single:
        last = max(single)
        return chr(ord(last.upper()) + 1)

    return "V1.0"


# ============================================================
# 提交校审
# ============================================================


def submit_for_review(
    db: Session, *, version: DocumentVersion, actor_id: str, due_days: int = 3
) -> WorkflowInstance:
    """提交签认：DRAFT/REVISING → CHECKING，并启动两级签认流程。

    **必须在启动流程之前取到文件的阶段码** —— 流程引擎要按阶段查
    《管理流程》矩阵来解析「主办单位 / 相关单位」。阶段传空就解析不出单位，
    任务挂不上（踩过的坑：stage_code=None 导致任务数为 0）。
    """
    if version.state not in (DocumentState.DRAFT.value, DocumentState.REVISING.value):
        label = DOCUMENT_STATE_LABELS.get(DocumentState(version.state), version.state)
        raise VersionRuleError(
            f"当前状态为「{label}」，只有「草稿」或「修订中」的版本可以提交签认"
        )

    doc = db.get(Document, version.document_id)
    stage_code = doc.stage_code if doc is not None else None

    inst = wf.start_workflow(
        db,
        project_id=version.project_id,
        biz_type=WorkflowBizType.REVIEW.value,
        biz_id=version.id,
        initiator_id=actor_id,
        stage_code=stage_code,
        due_days=due_days,
    )

    version.state = DocumentState.CHECKING.value
    version.submitted_at = _now()
    db.flush()
    return inst


# ============================================================
# 审批结果落到版本状态
# ============================================================

# 流程节点 → 版本状态（两级签认）
#   CONFIRM 主办单位确认 → 校核中
#   REVIEW  相关单位复核 → 审核中
#   VERIFY  审查单位提意见 → 审核中（与复核同属"待签认"阶段）
# 全部节点通过 → 已批准（在 apply_workflow_result 里单独处理）
_NODE_TO_STATE = {
    "CONFIRM": DocumentState.CHECKING.value,
    "REVIEW": DocumentState.REVIEWING.value,
    "VERIFY": DocumentState.REVIEWING.value,
    "SELF_CHECK": DocumentState.CHECKING.value,
}


def apply_workflow_result(
    db: Session, *, version: DocumentVersion, inst: WorkflowInstance
) -> DocumentVersion:
    """把流程实例的当前状态同步到版本状态。

    在每次审批动作之后调用。
    """
    if inst.status == WorkflowStatus.FINISHED.value:
        # 全节点通过 —— 此时状态为 APPROVED，等人工点"发布"
        version.state = DocumentState.APPROVED.value
    elif inst.current_node in _NODE_TO_STATE:
        version.state = _NODE_TO_STATE[inst.current_node]
    else:
        version.state = DocumentState.DRAFT.value
    db.flush()
    return version


# ============================================================
# 发布（铁律 3 / 4）
# ============================================================


def publish(
    db: Session,
    *,
    version: DocumentVersion,
    actor_id: str,
    void_reason_for_previous: str | None = None,
) -> DocumentVersion:
    """发布版本。

    强制校验：
      - 只有 APPROVED 可以发布
      - 铁律 3：PUBLISHED 不可回退、不可再次发布
      - 铁律 4：发布新版本时，旧的已发布版本自动作废（保留记录，不物理删除），
                并在 document_relation 里记录 SUPERSEDE 关系
    """
    if version.state == DocumentState.PUBLISHED.value:
        raise VersionRuleError("该版本已发布，不能重复发布（已发布版本不可回退）", code=4001)
    if version.state != DocumentState.APPROVED.value:
        label = DOCUMENT_STATE_LABELS.get(DocumentState(version.state), version.state)
        raise VersionRuleError(
            f"当前状态为「{label}」，只有「已批准」的版本可以发布。"
            f"请先完成校核 → 审核 → 批准。",
            code=4001,
        )

    doc = db.get(Document, version.document_id)
    if doc is None:
        raise VersionRuleError("文档不存在", code=4004)

    # 作废旧的有效版本
    old = published_version_of(db, doc.id)
    if old is not None and old.id != version.id:
        old.state = DocumentState.VOID.value
        old.voided_at = _now()
        old.voided_by = actor_id
        old.void_reason = void_reason_for_previous or f"被新版本 {version.version_no} 替代"

        db.add(
            DocumentRelation(
                project_id=doc.project_id,
                src_version_id=version.id,
                dst_version_id=old.id,
                rel_type="SUPERSEDE",
                note=f"{version.version_no} 替代 {old.version_no}",
            )
        )

    version.state = DocumentState.PUBLISHED.value
    version.published_at = _now()
    version.published_by = actor_id

    doc.current_version_id = version.id
    doc.published_version_no = version.version_no

    db.flush()
    return version


# ============================================================
# 发起修订（铁律 3 的配套：要改就发新版本）
# ============================================================


def start_revision(
    db: Session, *, document: Document, actor_id: str, reason: str
) -> DocumentVersion:
    """基于当前有效版本发起修订，生成一个 REVISING 的新版本。

    旧版本保持 PUBLISHED（在修订版发布前它仍是有效的），
    这样不会出现"修订期间没有有效版本可用"的空窗。
    """
    base = published_version_of(db, document.id)
    if base is None:
        raise VersionRuleError("该文件没有已发布版本，无法发起修订（请先完成首次校审发布）")
    if not reason or not reason.strip():
        raise VersionRuleError("发起修订必须填写修订原因", code=1001)

    assert_no_inflight(db, document.id)

    all_versions = db.execute(
        select(DocumentVersion).where(DocumentVersion.document_id == document.id)
    ).scalars().all()

    new_no = _next_version_no([v.version_no for v in all_versions])

    v = DocumentVersion(
        document_id=document.id,
        project_id=document.project_id,
        version_no=new_no,
        revision=len(all_versions),
        file_id=base.file_id,  # 先沿用原文件，后续上传替换
        state=DocumentState.REVISING.value,
        change_summary=reason,
        created_by=actor_id,
        supersedes_version_id=base.id,
    )
    db.add(v)
    db.flush()  # 必须先 flush 拿到 v.id，否则关联记录的 src_version_id 会是 None

    db.add(
        DocumentRelation(
            project_id=document.project_id,
            src_version_id=v.id,
            dst_version_id=base.id,
            rel_type="REFERENCE",
            note=f"{new_no} 基于 {base.version_no} 修订",
        )
    )
    db.flush()
    return v


# ============================================================
# 作废（铁律 4：不物理删除）
# ============================================================


def void_version(
    db: Session, *, version: DocumentVersion, actor_id: str, reason: str
) -> DocumentVersion:
    """作废版本。必须填原因，**不物理删除**。"""
    if not reason or not reason.strip():
        raise VersionRuleError("作废必须填写原因", code=1001)
    if version.state == DocumentState.VOID.value:
        raise VersionRuleError("该版本已作废，不能重复作废")

    was_published = version.state == DocumentState.PUBLISHED.value
    version.state = DocumentState.VOID.value
    version.voided_at = _now()
    version.voided_by = actor_id
    version.void_reason = reason

    if was_published:
        doc = db.get(Document, version.document_id)
        if doc is not None and doc.current_version_id == version.id:
            # 有效版本被作废 → 文档暂时没有有效版本
            # 这是需要人工介入的状态，所以不自动回退到上一个版本
            doc.current_version_id = None
            doc.published_version_no = None

    db.flush()
    return version


# ============================================================
# 引用关系
# ============================================================


def link_reference(
    db: Session, *, project_id: str, src_version_id: str, dst_version_id: str, note: str | None = None
) -> DocumentRelation:
    """登记"某版本引用了另一版本"。

    这是**变更影响分析的依据**：某个参数变了，
    通过 document_relation 找出哪些图纸引用了旧版本。
    """
    assert_published(db, src_version_id, purpose="建立引用关系")
    assert_published(db, dst_version_id, purpose="建立引用关系")

    rel = DocumentRelation(
        project_id=project_id,
        src_version_id=src_version_id,
        dst_version_id=dst_version_id,
        rel_type="REFERENCE",
        note=note,
    )
    db.add(rel)
    db.flush()
    return rel


def find_downstream_versions(db: Session, version_id: str) -> list[DocumentVersion]:
    """找出引用了某版本的所有下游版本。变更影响分析用。"""
    rels = db.execute(
        select(DocumentRelation).where(DocumentRelation.dst_version_id == version_id)
    ).scalars().all()
    if not rels:
        return []
    ids = [r.src_version_id for r in rels]
    return list(
        db.execute(select(DocumentVersion).where(DocumentVersion.id.in_(ids))).scalars().all()
    )
