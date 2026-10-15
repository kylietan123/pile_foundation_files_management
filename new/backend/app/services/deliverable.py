"""设计与交付成果服务 —— 交付完整性检查。

**这是设计院内部试用最实际的落点。**

设计文件一旦交付给施工方，图纸版本出错就是责任问题。所以"能不能交付"
不能靠人记得检查，必须由系统逐项校验。

六道关卡（全部通过才允许交付）：

| # | 关卡 | 判定依据 | 不通过的后果 |
|---|---|---|---|
| 1 | 设计输入已锁定 | 必填参数全部核验且已锁定 | 设计依据可以被悄悄改掉 |
| 2 | 参数来源有效 | 没有 STALE 状态的参数 | 用了过期勘察数据 |
| 3 | 成果齐备 | 该阶段应有的成果类型都存在 | 交付物缺项 |
| 4 | 版本有效 | 每项成果都有「已发布」版本 | 下游引用了未发布版本 |
| 5 | 问题闭环 | 没有未闭环的阻断类问题 | 已知问题被带进施工 |
| 6 | 变更闭环 | 没有未关闭的变更 | 批了没改，图纸与现场不一致 |

第 1、2 关是这套系统区别于通用文档管理系统的关键 ——
通用系统只检查"文件在不在"，我们检查"设计依据站不站得住"。
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.change import ChangeImpact, ChangeRequest
from app.models.document import Document, DocumentVersion
from app.models.enums import (
    CHANGE_STATE_LABELS,
    DOCUMENT_STATE_LABELS,
    ISSUE_STATUS_LABELS,
    VERIFY_STATUS_LABELS,
    ChangeState,
    DocumentState,
    IssueStatus,
    Severity,
    StageCode,
    VerifyStatus,
)
from app.models.issue import Issue
from app.models.project import DesignParam

# 设计阶段的成果清单。缺任一项都会在交付检查中被指出。
# 依据：常规桩基工程施工图交付目录。
DESIGN_DELIVERABLE_TYPES: list[dict] = [
    {"code": "DESIGN_SPEC", "name": "桩基设计总说明", "required": True,
     "note": "含设计依据、桩型、施工要求"},
    {"code": "CALC_BOOK", "name": "单桩承载力计算书", "required": True,
     "note": "含承载力与沉降计算，须可追溯到设计输入参数"},
    {"code": "LAYOUT_DWG", "name": "桩基平面布置图", "required": True,
     "note": "含桩位编号、桩长、桩径"},
    {"code": "REBAR_DWG", "name": "承台配筋图", "required": True,
     "note": "含承台尺寸与配筋"},
    {"code": "CONSTR_DWG", "name": "桩基施工图", "required": True,
     "note": "施工方据此施工，必须为已发布版本"},
]

# 交付时允许剩下的非阻断问题等级
NON_BLOCKING_SEVERITIES = {Severity.LOW.value}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================
# 成果清单
# ============================================================


def list_deliverables(
    db: Session, project_id: str, stage_code: str = StageCode.DESIGN.value
) -> list[dict]:
    """列出该阶段的成果项及其状态。

    对每一项标注：是否已有文件、当前有效版本、是否存在未发布的新版本。
    """
    docs = list(
        db.execute(
            select(Document).where(
                Document.project_id == project_id, Document.stage_code == stage_code
            )
        ).scalars().all()
    )

    # 按类型归并
    by_type: dict[str, list[Document]] = {}
    for d in docs:
        key = _type_key(d)
        by_type.setdefault(key, []).append(d)

    out: list[dict] = []
    for spec in DESIGN_DELIVERABLE_TYPES:
        matched = by_type.get(spec["code"], [])
        item = _deliverable_item(db, spec, matched)
        out.append(item)

    # 未在标准清单里、但实际存在的其他文件（避免遗漏）
    known = {s["code"] for s in DESIGN_DELIVERABLE_TYPES}
    for key, ds in by_type.items():
        if key in known:
            continue
        for d in ds:
            out.append(
                _deliverable_item(
                    db,
                    {"code": key, "name": d.category_name or "其他成果",
                     "required": False, "note": "不在标准交付清单内"},
                    [d],
                )
            )
    return out


def _type_key(doc: Document) -> str:
    """把文档映射到成果类型码。

    优先用 doc.category_name（来自字典），退化到编号前缀。
    """
    name = (doc.category_name or "").strip()
    mapping = {
        "设计说明": "DESIGN_SPEC",
        "计算书": "CALC_BOOK",
        "布置图": "LAYOUT_DWG",
        "配筋图": "REBAR_DWG",
        "施工图": "CONSTR_DWG",
        "勘察报告": "SURVEY_REPORT",
        "试桩报告": "TEST_PILE_REPORT",
    }
    if name in mapping:
        return mapping[name]

    no = (doc.doc_no or "").upper()
    if "JS" in no:
        return "CALC_BOOK"
    if no.startswith("JG-SM"):
        return "DESIGN_SPEC"
    if no.startswith("JG-0"):
        return "LAYOUT_DWG"
    return f"OTHER:{name or no or doc.id[:8]}"


def _deliverable_item(db: Session, spec: dict, docs: list[Document]) -> dict:
    """构造单个成果项的状态。"""
    if not docs:
        return {
            "type_code": spec["code"],
            "type_name": spec["name"],
            "required": spec["required"],
            "note": spec.get("note"),
            "exists": False,
            "document_id": None,
            "document_title": None,
            "doc_no": None,
            "current_version_no": None,
            "current_version_state": None,
            "has_unpublished_newer": False,
            "latest_version_no": None,
            "latest_version_state": None,
            "version_count": 0,
            "ready": False,
            "blockers": ["尚未创建该成果文件"],
        }

    # 多项同类型时取最新创建的一份，其余作为附加信息
    primary = sorted(docs, key=lambda d: d.created_at or _now())[-1]
    versions = list(
        db.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == primary.id)
            .order_by(DocumentVersion.created_at)
        ).scalars().all()
    )

    current = next((v for v in versions if v.id == primary.current_version_id), None)
    latest = versions[-1] if versions else None

    # 会阻断交付的"未发布版本"只包括**在途状态**（草稿/校核中/审核中/已批准/修订中）。
    # **已作废的版本不算** —— 它是用户主动清理掉的结果，是干净状态。
    # 早期版本把"最新版本 ≠ 当前有效版本"一律当作阻断，导致作废一个版本后
    # 反而无法交付，与直觉相反。
    IN_FLIGHT = {
        DocumentState.DRAFT.value,
        DocumentState.CHECKING.value,
        DocumentState.REVIEWING.value,
        DocumentState.APPROVED.value,
        DocumentState.REVISING.value,
    }
    inflight_versions = [v for v in versions if v.state in IN_FLIGHT]
    has_unpublished = bool(inflight_versions)

    blockers: list[str] = []
    if current is None:
        blockers.append("没有已发布版本，下游不可引用")
    if inflight_versions:
        labels = "、".join(
            f"{v.version_no}（{DOCUMENT_STATE_LABELS.get(DocumentState(v.state), v.state)}）"
            for v in inflight_versions[:3]
        )
        more = f" 等 {len(inflight_versions)} 个" if len(inflight_versions) > 3 else ""
        blockers.append(f"存在在途版本未处理完：{labels}{more}，需完成校审或作废")
    if current is None and latest is not None and latest.state == DocumentState.VOID.value:
        blockers.append("所有版本均已作废，需要重新上传并发布")

    return {
        "type_code": spec["code"],
        "type_name": spec["name"],
        "required": spec["required"],
        "note": spec.get("note"),
        "exists": True,
        "document_id": primary.id,
        "document_title": primary.title,
        "doc_no": primary.doc_no,
        "current_version_no": current.version_no if current else None,
        "current_version_state": current.state if current else None,
        "has_unpublished_newer": has_unpublished,
        "latest_version_no": latest.version_no if latest else None,
        "latest_version_state": latest.state if latest else None,
        "version_count": len(versions),
        "ready": not blockers,
        "blockers": blockers,
        "extra_documents": [
            {"id": d.id, "title": d.title, "doc_no": d.doc_no}
            for d in docs
            if d.id != primary.id
        ],
    }


# ============================================================
# 交付完整性检查（六道关卡）
# ============================================================


def check_delivery(
    db: Session, project_id: str, stage_code: str = StageCode.DESIGN.value
) -> dict:
    """交付前完整性检查。

    返回 {can_deliver, gates, blockers, summary}。
    **每一关都要给出人话的原因和可操作的建议** ——
    只说"检查不通过"，用户不知道该怎么办。
    """
    gates: list[dict] = []

    # ---------- 关卡 1：设计输入已锁定 ----------
    params = list(
        db.execute(select(DesignParam).where(DesignParam.project_id == project_id))
        .scalars().all()
    )
    total_params = len(params)
    required = [p for p in params if p.required]
    locked = [p for p in params if p.locked]
    unverified_required = [
        p for p in required if p.verify_status != VerifyStatus.VERIFIED.value
    ]
    inputs_locked = total_params > 0 and len(locked) == total_params

    g1_ok = inputs_locked and not unverified_required
    g1_blockers: list[str] = []
    if total_params == 0:
        g1_blockers.append("该项目还没有设计输入参数，无法确认设计依据")
    elif not inputs_locked:
        g1_blockers.append(
            f"设计输入尚未锁定（已锁定 {len(locked)}/{total_params} 项）。"
            f"未锁定的设计依据可以被悄悄改动，交付前必须锁定"
        )
    if unverified_required:
        names = "、".join(p.param_name for p in unverified_required[:4])
        more = f" 等 {len(unverified_required)} 项" if len(unverified_required) > 4 else ""
        g1_blockers.append(f"必填参数未核验：{names}{more}")

    gates.append(
        {
            "gate": 1,
            "code": "INPUTS_LOCKED",
            "name": "设计输入已锁定",
            "passed": g1_ok,
            "detail": (
                f"共 {total_params} 项参数，必填 {len(required)} 项，"
                f"已核验 {len([p for p in params if p.verify_status == VerifyStatus.VERIFIED.value])} 项，"
                f"已锁定 {len(locked)} 项"
            ),
            "blockers": g1_blockers,
            "suggestion": "到「设计输入管理」核验全部必填参数后点击「锁定设计输入」",
        }
    )

    # ---------- 关卡 2：参数来源有效 ----------
    stale = [p for p in params if p.verify_status == VerifyStatus.STALE.value]
    doubtful = [p for p in params if p.verify_status == VerifyStatus.DOUBTFUL.value]
    g2_ok = not stale
    g2_blockers: list[str] = []
    if stale:
        names = "、".join(p.param_name for p in stale[:4])
        more = f" 等 {len(stale)} 项" if len(stale) > 4 else ""
        g2_blockers.append(
            f"{len(stale)} 项参数的来源文件已发布新版本，原核验结论不再成立：{names}{more}"
        )
    gates.append(
        {
            "gate": 2,
            "code": "PARAM_SOURCE_VALID",
            "name": "设计参数来源有效",
            "passed": g2_ok,
            "detail": (
                f"来源已失效 {len(stale)} 项，存疑 {len(doubtful)} 项"
                + ("（存疑不阻断交付，但建议澄清）" if doubtful else "")
            ),
            "blockers": g2_blockers,
            "suggestion": "到「设计输入管理」按新版本重新核验相关参数",
        }
    )

    # ---------- 关卡 3、4：成果齐备 + 版本有效 ----------
    deliverables = list_deliverables(db, project_id, stage_code)
    missing = [d for d in deliverables if d["required"] and not d["exists"]]
    not_ready = [d for d in deliverables if d["exists"] and not d["ready"]]

    gates.append(
        {
            "gate": 3,
            "code": "DELIVERABLES_COMPLETE",
            "name": "交付成果齐备",
            "passed": not missing,
            "detail": (
                f"标准交付清单 {len([d for d in deliverables if d['required']])} 项，"
                f"已存在 {len([d for d in deliverables if d['required'] and d['exists']])} 项"
            ),
            "blockers": [f"缺少「{d['type_name']}」" for d in missing],
            "suggestion": "到「文件与版本」新建缺失的成果文件并上传内容",
        }
    )

    gates.append(
        {
            "gate": 4,
            "code": "VERSIONS_PUBLISHED",
            "name": "成果版本均为已发布",
            "passed": not not_ready,
            "detail": (
                f"存在文件的成果项 {len([d for d in deliverables if d['exists']])} 项，"
                f"其中 {len(not_ready)} 项版本未就绪"
            ),
            "blockers": [
                f"「{d['type_name']}」：{'；'.join(d['blockers'])}" for d in not_ready
            ],
            "suggestion": "完成校审并发布，或作废多余的未发布版本",
        }
    )

    # ---------- 关卡 5：问题闭环 ----------
    issues = list(
        db.execute(select(Issue).where(Issue.project_id == project_id)).scalars().all()
    )
    blocking_issues = [
        i
        for i in issues
        if i.status != IssueStatus.CLOSED.value
        and i.severity not in NON_BLOCKING_SEVERITIES
    ]
    g5_ok = not blocking_issues
    g5_blockers: list[str] = []
    if blocking_issues:
        for i in blocking_issues[:4]:
            g5_blockers.append(
                f"{i.issue_no or '未编号'}「{i.title}」"
                f"（{ISSUE_STATUS_LABELS.get(IssueStatus(i.status), i.status)}）"
            )
        if len(blocking_issues) > 4:
            g5_blockers.append(f"…另有 {len(blocking_issues) - 4} 项")
    gates.append(
        {
            "gate": 5,
            "code": "ISSUES_CLOSED",
            "name": "问题已闭环",
            "passed": g5_ok,
            "detail": (
                f"共 {len(issues)} 项问题，"
                f"未闭环 {len([i for i in issues if i.status != IssueStatus.CLOSED.value])} 项，"
                f"其中需阻断交付 {len(blocking_issues)} 项"
                f"（低severity问题不阻断）"
            ),
            "blockers": g5_blockers,
            "suggestion": "到「问题管理」完成处理链路并闭环，特别是必须完成「验证」环节",
        }
    )

    # ---------- 关卡 6：变更闭环 ----------
    changes = list(
        db.execute(
            select(ChangeRequest).where(ChangeRequest.project_id == project_id)
        ).scalars().all()
    )
    open_changes = [
        c for c in changes if c.state not in (ChangeState.CLOSED.value, ChangeState.REJECTED.value)
    ]
    g6_ok = not open_changes
    g6_blockers: list[str] = []
    for c in open_changes[:4]:
        # 未处理的影响项数量 —— 这是"批了没改"的直接证据
        pending = db.execute(
            select(ChangeImpact).where(
                ChangeImpact.change_id == c.id, ChangeImpact.handled.is_(False)
            )
        ).scalars().all()
        extra = f"，另有 {len(pending)} 项影响未处理" if pending else ""
        g6_blockers.append(
            f"{c.change_no}「{c.title}」"
            f"（{CHANGE_STATE_LABELS.get(ChangeState(c.state), c.state)}）{extra}"
        )
    if len(open_changes) > 4:
        g6_blockers.append(f"…另有 {len(open_changes) - 4} 项")
    gates.append(
        {
            "gate": 6,
            "code": "CHANGES_CLOSED",
            "name": "设计变更已闭环",
            "passed": g6_ok,
            "detail": f"共 {len(changes)} 项变更，未关闭 {len(open_changes)} 项",
            "blockers": g6_blockers,
            "suggestion": "到「设计变更」处理完全部影响明细后关闭变更",
        }
    )

    # ---------- 汇总 ----------
    failed = [g for g in gates if not g["passed"]]
    return {
        "can_deliver": not failed,
        "stage_code": stage_code,
        "checked_at": _now().isoformat(),
        "gates": gates,
        "failed_gate_count": len(failed),
        "blocker_count": sum(len(g["blockers"]) for g in failed),
        "summary": (
            "全部关卡通过，可以交付"
            if not failed
            else f"还有 {len(failed)} 道关卡未通过，共 {sum(len(g['blockers']) for g in failed)} 项待处理"
        ),
    }


# ============================================================
# 交付清单（交付时附给接收方）
# ============================================================


def build_manifest(
    db: Session, project_id: str, stage_code: str = StageCode.DESIGN.value
) -> dict:
    """生成交付清单。

    只收录**已发布**版本的成果 —— 未发布的不能出现在交付清单里。
    这是铁律 1 在交付场景的体现。
    """
    deliverables = list_deliverables(db, project_id, stage_code)
    items: list[dict] = []
    for d in deliverables:
        if not d["exists"] or not d["current_version_no"]:
            continue
        doc = db.get(Document, d["document_id"]) if d["document_id"] else None
        ver = (
            db.get(DocumentVersion, doc.current_version_id)
            if doc and doc.current_version_id
            else None
        )
        items.append(
            {
                "type_name": d["type_name"],
                "document_id": d["document_id"],
                "title": d["document_title"],
                "doc_no": d["doc_no"],
                "version_no": d["current_version_no"],
                "published_at": ver.published_at if ver else None,
                "is_self_checked": ver.is_self_checked if ver else False,
                "file_name": None,
            }
        )

    return {
        "project_id": project_id,
        "stage_code": stage_code,
        "generated_at": _now().isoformat(),
        "item_count": len(items),
        "items": items,
        "note": (
            "本清单仅收录「已发布」版本的成果。"
            "未发布版本不可交付 —— 这是版本状态机的强制规则。"
        ),
    }
