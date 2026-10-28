"""设计输入服务 —— 参数溯源链的实现。

设计输入的定位（对应《设计阶段-落地版》§2 第 5 页）：
    每个参数固定 5 个字段：参数名 / 数值 / 单位 / 来源文件与位置 / 核验状态

核心价值在**溯源**：
    设计里每个参数都能点开看到来自哪份勘察报告哪一页哪张表。
    这从机制上堵死"参数从哪来说不清"的问题，也是 AI 幻觉的防线。

锁定语义：
    全部必填参数核验通过后可"锁定"设计输入。
    锁定后如需修改，**必须走变更流程** —— 否则设计依据会被悄悄改掉。

STALE 自动推导：
    当参数的来源文件发布了新版本，原核验结论不再成立，
    系统自动把参数置为 STALE 并要求重新核验。
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentVersion
from app.models.enums import DocumentState, VerifyStatus
from app.models.project import DesignParam


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DesignInputError(HTTPException):
    def __init__(self, message: str, code: int = 4004):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": code, "message": message},
        )


# ============================================================
# 查询
# ============================================================


def list_params(
    db: Session,
    project_id: str,
    *,
    group: str | None = None,
    verify_status: str | None = None,
    only_unverified: bool = False,
) -> list[DesignParam]:
    stmt = select(DesignParam).where(DesignParam.project_id == project_id)
    if group:
        stmt = stmt.where(DesignParam.param_group == group)
    if verify_status:
        stmt = stmt.where(DesignParam.verify_status == verify_status)
    if only_unverified:
        stmt = stmt.where(DesignParam.verify_status != VerifyStatus.VERIFIED.value)
    return list(db.execute(stmt.order_by(DesignParam.param_group, DesignParam.param_code)).scalars().all())


def get_param(db: Session, param_id: str) -> DesignParam:
    p = db.get(DesignParam, param_id)
    if p is None:
        raise DesignInputError("设计参数不存在", code=4004)
    return p


def param_summary(db: Session, project_id: str) -> dict:
    """核验进度汇总。前端"设计输入核验状态"卡片用。"""
    rows = list_params(db, project_id)
    total = len(rows)
    required = [r for r in rows if r.required]
    by_status: dict[str, int] = {}
    for r in rows:
        by_status[r.verify_status] = by_status.get(r.verify_status, 0) + 1

    unverified_required = [
        r for r in required if r.verify_status != VerifyStatus.VERIFIED.value
    ]
    locked_count = sum(1 for r in rows if r.locked)

    return {
        "total": total,
        "required_total": len(required),
        "verified": by_status.get(VerifyStatus.VERIFIED.value, 0),
        "pending": by_status.get(VerifyStatus.PENDING.value, 0),
        "doubtful": by_status.get(VerifyStatus.DOUBTFUL.value, 0),
        "stale": by_status.get(VerifyStatus.STALE.value, 0),
        "modified": by_status.get(VerifyStatus.MODIFIED.value, 0),
        "by_status": by_status,
        "unverified_required_count": len(unverified_required),
        "unverified_required": [
            {"param_code": r.param_code, "param_name": r.param_name, "status": r.verify_status}
            for r in unverified_required
        ],
        "locked": locked_count == total and total > 0,
        "locked_count": locked_count,
        "can_lock": len(unverified_required) == 0 and total > 0 and locked_count == 0,
    }


def source_info(db: Session, param: DesignParam) -> dict | None:
    """参数的来源详情 —— 前端点开"来源"时展示。

    返回文件名、版本号、状态、位置，以及**该来源是否已有更新版本**。
    """
    if not param.source_version_id:
        return None

    v = db.get(DocumentVersion, param.source_version_id)
    if v is None:
        return None

    doc = db.get(Document, v.document_id)
    latest = None
    if doc is not None:
        latest = db.execute(
            select(DocumentVersion)
            .where(
                DocumentVersion.document_id == doc.id,
                DocumentVersion.state == DocumentState.PUBLISHED.value,
            )
        ).scalar_one_or_none()

    return {
        "version_id": v.id,
        "version_no": v.version_no,
        "state": v.state,
        "document_id": v.document_id,
        "document_title": doc.title if doc else None,
        "doc_no": doc.doc_no if doc else None,
        "category_name": doc.category_name if doc else None,
        "locator": param.source_locator,
        "has_newer_published": bool(latest and latest.id != v.id),
        "latest_version_no": latest.version_no if latest else None,
        "latest_version_id": latest.id if latest else None,
    }


# ============================================================
# 核验
# ============================================================


def verify_param(
    db: Session,
    *,
    param: DesignParam,
    actor_id: str,
    action: str,
    new_value_num: float | None = None,
    new_value_text: str | None = None,
    note: str | None = None,
) -> DesignParam:
    """核验单个参数。

    action:
      verify  通过核验
      modify  修改取值后通过（记 MODIFIED，保留修改说明）
      doubtful 标记存疑（挂起，需资料提供方澄清）
      pending  撤销核验，回到待核验
    """
    if param.locked:
        raise DesignInputError(
            f"参数「{param.param_name}」已随设计输入锁定，"
            f"如需修改必须走设计变更流程（变更原因分类选「勘察资料变化」）",
            code=4005,
        )

    if action == "verify":
        param.verify_status = VerifyStatus.VERIFIED.value
        param.verified_by = actor_id
        param.verified_at = _now()
        param.verify_note = note

    elif action == "modify":
        if new_value_num is None and new_value_text is None:
            raise DesignInputError("修改取值时必须提供新的数值或文本", code=1001)
        if not note or not note.strip():
            raise DesignInputError("修改取值必须填写理由（谁改的、按什么依据改）", code=1001)

        # 保留原始来源，另记人工修改 —— 溯源链不能断
        param.value_num = new_value_num if new_value_num is not None else param.value_num
        param.value_text = new_value_text if new_value_text is not None else param.value_text
        param.source_type = "MANUAL"
        param.verify_status = VerifyStatus.MODIFIED.value
        param.verified_by = actor_id
        param.verified_at = _now()
        param.verify_note = note

    elif action == "doubtful":
        if not note or not note.strip():
            raise DesignInputError("标记存疑必须说明原因（需哪一方澄清什么）", code=1001)
        param.verify_status = VerifyStatus.DOUBTFUL.value
        param.verify_note = note
        param.verified_by = actor_id
        param.verified_at = _now()

    elif action == "pending":
        param.verify_status = VerifyStatus.PENDING.value
        param.verified_by = None
        param.verified_at = None
        param.verify_note = note

    else:
        raise DesignInputError(f"未知的核验动作 {action}", code=1001)

    db.flush()
    return param


# ============================================================
# 锁定 / 解锁
# ============================================================


def lock_inputs(db: Session, *, project_id: str, actor_id: str) -> dict:
    """锁定设计输入。

    前置条件：**全部必填参数都已核验**。
    锁定后任何参数修改都必须走变更流程。
    """
    summary = param_summary(db, project_id)
    if summary["total"] == 0:
        raise DesignInputError("该项目还没有设计输入参数，无法锁定", code=4004)
    if summary["unverified_required_count"] > 0:
        names = "、".join(p["param_name"] for p in summary["unverified_required"][:5])
        more = (
            f" 等 {summary['unverified_required_count']} 项"
            if summary["unverified_required_count"] > 5
            else ""
        )
        raise DesignInputError(
            f"还有必填参数未通过核验（{names}{more}），核验完成后才能锁定设计输入",
            code=4005,
        )

    rows = list_params(db, project_id)
    for r in rows:
        r.locked = True
        r.locked_at = _now()
        r.locked_by = actor_id
    db.flush()

    return {"locked_count": len(rows), "locked_at": _now().isoformat()}


def unlock_inputs(db: Session, *, project_id: str, actor_id: str, reason: str) -> dict:
    """解锁设计输入。

    **这是特权操作**：正常流程下应该走设计变更。
    只允许在变更流程中调用，且必须记录原因。
    """
    if not reason or not reason.strip():
        raise DesignInputError("解锁设计输入必须填写原因（应关联具体的设计变更单号）", code=1001)

    rows = list_params(db, project_id)
    for r in rows:
        r.locked = False
        r.locked_at = None
        r.locked_by = None
        r.verify_note = f"[解锁] {reason}" + (f"；原说明：{r.verify_note}" if r.verify_note else "")
    db.flush()
    return {"unlocked_count": len(rows), "reason": reason, "by": actor_id}


# ============================================================
# STALE 自动推导
# ============================================================


def refresh_stale(db: Session, project_id: str) -> dict:
    """当来源文件发布了新版本时，把相关参数置为 STALE。

    这是"勘察报告更新了，设计根本不知道"这个工程风险的机制化防线。
    设计院内部试用时，这个功能直接对应页 2 上那条红色提示：
        "勘察报告（详勘）V2 已更新 → 设计输入参数需重新核验"

    返回值用于前端提示"有 N 项参数因来源更新需要重新核验"。
    """
    rows = list_params(db, project_id)
    # 一次性载入所有相关的已发布版本，避免 N+1 查询
    version_ids = {r.source_version_id for r in rows if r.source_version_id}
    if not version_ids:
        return {"stale_count": 0, "affected": []}

    versions = {
        v.id: v
        for v in db.execute(
            select(DocumentVersion).where(DocumentVersion.id.in_(version_ids))
        ).scalars().all()
    }

    # 各文档当前的有效版本
    doc_ids = {v.document_id for v in versions.values()}
    latest_map: dict[str, DocumentVersion] = {}
    if doc_ids:
        for v in db.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id.in_(doc_ids),
                DocumentVersion.state == DocumentState.PUBLISHED.value,
            )
        ).scalars().all():
            latest_map[v.document_id] = v

    affected: list[dict] = []
    for r in rows:
        if not r.source_version_id or r.verify_status == VerifyStatus.STALE.value:
            continue
        src = versions.get(r.source_version_id)
        if src is None:
            continue
        latest = latest_map.get(src.document_id)
        if latest is not None and latest.id != src.id:
            r.verify_status = VerifyStatus.STALE.value
            r.verify_note = (
                f"来源文件已发布新版本 {latest.version_no}"
                f"（原核验基于 {src.version_no}），需重新核验"
            )
            affected.append(
                {
                    "param_id": r.id,
                    "param_code": r.param_code,
                    "param_name": r.param_name,
                    "from_version": src.version_no,
                    "to_version": latest.version_no,
                    "locator": r.source_locator,
                }
            )

    db.flush()
    return {"stale_count": len(affected), "affected": affected}


# ============================================================
# 从参数生成引用（打通"参数 → 文件版本"的溯源）
# ============================================================


def relink_source(
    db: Session, *, param: DesignParam, new_version_id: str, actor_id: str
) -> DesignParam:
    """把参数的来源指向新的文件版本，并重置核验状态。

    用于"来源文件更新后重新核验"：人工确认新版本取值仍适用时调用，
    或人工修改取值后调用。
    """
    new_v = db.get(DocumentVersion, new_version_id)
    if new_v is None:
        raise DesignInputError("目标文件版本不存在", code=4004)
    if new_v.state != DocumentState.PUBLISHED.value:
        raise DesignInputError(
            "只能把参数来源指向「已发布」的文件版本 —— 未发布版本不可被引用",
            code=4001,
        )

    param.source_version_id = new_version_id
    param.verify_status = VerifyStatus.PENDING.value
    param.verified_by = actor_id
    param.verified_at = _now()
    param.verify_note = f"来源已更新至 {new_v.version_no}，待重新核验"
    db.flush()
    return param
