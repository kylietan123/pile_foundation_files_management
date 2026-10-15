"""文件、文档、版本接口 —— 版本状态机的对外入口。

权限动作映射：
    查看/列表   VIEW
    上传/新建   EDIT
    提交校审    EDIT
    审批        EDIT（且必须是指派给你、或具备对应校审角色）
    发布        EDIT + 角色属于 DESIGN_APPROVER / ADMIN
    作废        EDIT + 同上
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import func, select

from app.api.deps import (
    CurrentPrincipal,
    DbSession,
    require_action,
    require_project_view,
)
from app.models.document import Document, DocumentRelation, DocumentVersion, FileObject
from app.models.enums import (
    DOCUMENT_STATE_LABELS,
    RESPONSIBILITY_LABELS,
    SECRET_ORDER,
    STAGE_LABELS,
    UNIT_LABELS,
    DocumentState,
    PermissionAction,
    SecretLevel,
    StageCode,
    TaskAction,
    UnitCode,
    WorkflowBizType,
)
from app.models.org import AppUser
from app.models.workflow import WorkflowInstance, WorkflowTask
from app.schemas import (
    ApiResponse,
    DocumentCreate,
    DocumentOut,
    DocumentVersionOut,
    DownloadTokenOut,
    FileObjectOut,
    PublishIn,
    RevisionIn,
    VersionActionIn,
    VersionCreate,
    VoidIn,
    WorkflowTaskOut,
    WorkflowTraceOut,
)
from app.services import documents as docsvc
from app.services import storage, workflow as wf

router = APIRouter(tags=["文件与版本"])

# 发布 / 作废 不再用硬编码角色名单 ——
# 改为按权限矩阵校验 PermissionAction.PUBLISH（主办单位才有）。
# 见 app/core/permissions.py：责任等级 → 动作。


# ============================================================
# 序列化辅助
# ============================================================


def _user_names(db, ids: set[str]) -> dict[str, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    rows = db.execute(select(AppUser).where(AppUser.id.in_(ids))).scalars().all()
    return {u.id: u.name for u in rows}


def _available_version_actions(
    db, principal, version: DocumentVersion, doc: Document, inst: WorkflowInstance | None
) -> list[str]:
    """当前用户对该版本可执行的动作。

    **动作来自权限矩阵**（主办能发布、相关只能复核），
    不再是硬编码的角色名单 —— 责任划分调整时这里自动跟着变。
    阶段取文件自身所属阶段，所以同一份文件在不同阶段权限不同。
    """
    from app.models.enums import PermissionAction as PA

    actions: list[str] = []
    stage = doc.stage_code
    can_edit = principal.can(PA.EDIT, doc.project_id, stage)
    can_publish = principal.can(PA.PUBLISH, doc.project_id, stage)

    if version.state in (DocumentState.DRAFT.value, DocumentState.REVISING.value) and can_edit:
        actions.append("submit")
    if version.state in (DocumentState.CHECKING.value, DocumentState.REVIEWING.value) and inst:
        # 只给当前待办的处理人显示签认按钮（同单位其他成员也可代办）
        tasks = wf.pending_tasks_of_node(db, inst.id, inst.current_node or "")
        if principal.is_superuser or any(
            t.assignee == principal.user_id for t in tasks
        ):
            actions.extend(["approve", "return"])
    if version.state == DocumentState.APPROVED.value and can_publish:
        actions.append("publish")
    if version.state == DocumentState.PUBLISHED.value:
        if can_edit:
            actions.append("revise")
        if can_publish:
            actions.append("void")
    if version.state in (
        DocumentState.DRAFT.value,
        DocumentState.CHECKING.value,
        DocumentState.REVIEWING.value,
        DocumentState.APPROVED.value,
        DocumentState.REVISING.value,
    ) and can_publish:
        actions.append("void")
    if version.state == DocumentState.PUBLISHED.value:
        actions.append("download")
    return actions


def _run_in_of(db, version_id: str) -> WorkflowInstance | None:
    return db.execute(
        select(WorkflowInstance)
        .where(
            WorkflowInstance.biz_type == WorkflowBizType.REVIEW.value,
            WorkflowInstance.biz_id == version_id,
        )
        .order_by(WorkflowInstance.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _version_out(db, principal, v: DocumentVersion, doc: Document) -> DocumentVersionOut:
    inst = _run_in_of(db, v.id)
    names = _user_names(db, {v.created_by, v.published_by})

    fo = db.get(FileObject, v.file_id)
    return DocumentVersionOut(
        id=v.id,
        document_id=v.document_id,
        project_id=v.project_id,
        version_no=v.version_no,
        revision=v.revision,
        state=DocumentState(v.state),
        state_label=DOCUMENT_STATE_LABELS.get(DocumentState(v.state), v.state),
        change_summary=v.change_summary,
        remark=v.remark,
        file=FileObjectOut.model_validate(fo) if fo else None,
        created_by=v.created_by,
        created_by_name=names.get(v.created_by or ""),
        created_at=v.created_at,
        submitted_at=v.submitted_at,
        published_at=v.published_at,
        published_by=v.published_by,
        voided_at=v.voided_at,
        void_reason=v.void_reason,
        from_change_id=v.from_change_id,
        supersedes_version_id=v.supersedes_version_id,
        is_self_checked=v.is_self_checked,
        self_check_reason=v.self_check_reason,
        workflow_instance_id=inst.id if inst else None,
        current_node=inst.current_node if inst else None,
        available_actions=_available_version_actions(db, principal, v, doc, inst),
    )


def _document_out(db, principal, doc: Document, with_versions: bool = True) -> DocumentOut:
    versions = db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == doc.id)
        .order_by(DocumentVersion.created_at)
    ).scalars().all()

    latest = versions[-1] if versions else None
    secret_label = {
        SecretLevel.PUBLIC.value: "公开",
        SecretLevel.INTERNAL.value: "内部",
        SecretLevel.RESTRICTED.value: "受限",
        SecretLevel.SECRET.value: "保密",
    }.get(doc.secret_level, doc.secret_level)

    return DocumentOut(
        id=doc.id,
        project_id=doc.project_id,
        stage_code=StageCode(doc.stage_code),
        stage_label=STAGE_LABELS.get(StageCode(doc.stage_code)),
        category_id=doc.category_id,
        category_name=doc.category_name,
        title=doc.title,
        doc_no=doc.doc_no,
        discipline=doc.discipline,
        secret_level=doc.secret_level,
        secret_level_label=secret_label,
        current_version_id=doc.current_version_id,
        published_version_no=doc.published_version_no,
        created_by=doc.created_by,
        created_at=doc.created_at,
        remark=doc.remark,
        version_count=len(versions),
        latest_version_no=latest.version_no if latest else None,
        latest_state=DocumentState(latest.state) if latest else None,
        versions=[_version_out(db, principal, v, doc) for v in versions] if with_versions else [],
    )


def _get_document(db, document_id: str) -> Document:
    doc = db.get(Document, document_id)
    if doc is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": 4004, "message": "文档不存在"},
        )
    return doc


def _get_version(db, version_id: str) -> DocumentVersion:
    v = db.get(DocumentVersion, version_id)
    if v is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": 4004, "message": "文件版本不存在"},
        )
    return v


def _assert_secret_visible(principal, project_id: str, secret_level: str) -> None:
    """敏感等级校验。超出可查看等级 → 403 且说明原因。"""
    if not principal.can_view_secret(project_id, secret_level):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": 3002,
                "message": f"该文件为「{secret_level}」级，超出你的可查看范围，"
                f"需项目管理员单独授权",
            },
        )


# ============================================================
# 文档
# ============================================================


@router.get("/projects/{project_id}/documents", response_model=ApiResponse[list[DocumentOut]],
            summary="文件列表")
def list_documents(
    project_id: str,
    db: DbSession,
    principal: CurrentPrincipal,
    stage: str | None = None,
    category_id: str | None = None,
    keyword: str | None = None,
    with_versions: bool = False,
) -> ApiResponse[list[DocumentOut]]:
    require_project_view(project_id, principal)

    stmt = select(Document).where(Document.project_id == project_id)
    # 阶段过滤：只返回用户有权限的阶段
    visible = principal.visible_stages(project_id)
    if stage:
        if StageCode(stage) not in visible:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": 3003, "message": f"你的角色不覆盖阶段 {stage}"},
            )
        stmt = stmt.where(Document.stage_code == stage)
    elif visible and len(visible) < len(StageCode):
        stmt = stmt.where(Document.stage_code.in_([s.value for s in visible]))

    if category_id:
        stmt = stmt.where(Document.category_id == category_id)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(Document.title.like(like) | Document.doc_no.like(like))

    docs = db.execute(stmt.order_by(Document.created_at.desc())).scalars().all()

    # 敏感等级过滤：超范围的直接不出现在列表里
    docs = [d for d in docs if principal.can_view_secret(project_id, d.secret_level)]

    return ApiResponse(data=[_document_out(db, principal, d, with_versions) for d in docs])


@router.post("/documents", response_model=ApiResponse[DocumentOut], summary="新建文档")
def create_document(
    body: DocumentCreate, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[DocumentOut]:
    require_action(principal, PermissionAction.EDIT, body.project_id, body.stage_code.value)

    from app.models.dict import DictItem

    cat_name = None
    if body.category_id:
        cat = db.get(DictItem, body.category_id)
        cat_name = cat.name if cat else None

    doc = Document(
        project_id=body.project_id,
        stage_code=body.stage_code.value,
        category_id=body.category_id,
        category_name=cat_name,
        title=body.title,
        doc_no=body.doc_no,
        discipline=body.discipline,
        secret_level=body.secret_level.value,
        created_by=principal.user_id,
        remark=body.remark,
    )
    db.add(doc)
    db.flush()

    # 审计留痕
    _audit(db, principal, "CREATE", "document", doc.id, doc.title, body.project_id, body.stage_code.value)
    db.commit()
    return ApiResponse(data=_document_out(db, principal, doc))


@router.get("/documents/{document_id}", response_model=ApiResponse[DocumentOut], summary="文档详情（含全部版本）")
def get_document(document_id: str, db: DbSession, principal: CurrentPrincipal) -> ApiResponse[DocumentOut]:
    doc = _get_document(db, document_id)
    require_project_view(doc.project_id, principal)
    _assert_secret_visible(principal, doc.project_id, doc.secret_level)
    return ApiResponse(data=_document_out(db, principal, doc))


# ============================================================
# 版本：上传 / 提交 / 审批 / 发布 / 修订 / 作废
# ============================================================


@router.post(
    "/documents/{document_id}/versions",
    response_model=ApiResponse[DocumentVersionOut],
    summary="上传新版本（草稿）",
)
async def upload_version(
    document_id: str,
    db: DbSession,
    principal: CurrentPrincipal,
    file: Annotated[UploadFile, File(description="文件本体")],
    change_summary: Annotated[str | None, Form()] = None,
    version_no: Annotated[str | None, Form()] = None,
    remark: Annotated[str | None, Form()] = None,
) -> ApiResponse[DocumentVersionOut]:
    """上传文件并创建草稿版本。

    内容寻址去重：相同文件重复上传只增加引用计数，不重复占用存储。
    """
    doc = _get_document(db, document_id)
    require_action(principal, PermissionAction.EDIT, doc.project_id, doc.stage_code)

    fo = await storage.save_upload(db, file, principal.user_id)
    v = docsvc.create_version(
        db,
        document=doc,
        file_id=fo.file_id,
        version_no=version_no,
        change_summary=change_summary,
        creator_id=principal.user_id,
        remark=remark,
    )
    _audit(db, principal, "CREATE", "document_version", v.id,
           f"{doc.title} {v.version_no}", doc.project_id, doc.stage_code)
    db.commit()
    return ApiResponse(data=_version_out(db, principal, v, doc))


@router.get("/documents/{document_id}/versions", response_model=ApiResponse[list[DocumentVersionOut]],
            summary="版本列表")
def list_versions(document_id: str, db: DbSession, principal: CurrentPrincipal) -> ApiResponse[list[DocumentVersionOut]]:
    doc = _get_document(db, document_id)
    require_project_view(doc.project_id, principal)
    _assert_secret_visible(principal, doc.project_id, doc.secret_level)
    versions = db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.created_at)
    ).scalars().all()
    return ApiResponse(data=[_version_out(db, principal, v, doc) for v in versions])


@router.get("/versions/{version_id}", response_model=ApiResponse[DocumentVersionOut], summary="版本详情")
def get_version(version_id: str, db: DbSession, principal: CurrentPrincipal) -> ApiResponse[DocumentVersionOut]:
    v = _get_version(db, version_id)
    doc = _get_document(db, v.document_id)
    require_project_view(doc.project_id, principal)
    _assert_secret_visible(principal, doc.project_id, doc.secret_level)
    return ApiResponse(data=_version_out(db, principal, v, doc))


@router.post("/versions/{version_id}/submit", response_model=ApiResponse[DocumentVersionOut],
             summary="提交校审（草稿 → 校核中）")
def submit_version(version_id: str, db: DbSession, principal: CurrentPrincipal) -> ApiResponse[DocumentVersionOut]:
    v = _get_version(db, version_id)
    doc = _get_document(db, v.document_id)
    require_action(principal, PermissionAction.EDIT, doc.project_id, doc.stage_code)

    docsvc.submit_for_review(db, version=v, actor_id=principal.user_id)
    _audit(db, principal, "SUBMIT", "document_version", v.id,
           f"{doc.title} {v.version_no}", doc.project_id, doc.stage_code)
    db.commit()
    return ApiResponse(data=_version_out(db, principal, v, doc))


@router.post("/versions/{version_id}/decide", response_model=ApiResponse[DocumentVersionOut],
             summary="审批（通过 / 退回）")
def decide_version(
    version_id: str, body: VersionActionIn, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[DocumentVersionOut]:
    """处理当前审批节点。

    三级校审由流程模板控制：校核 → 审核 → 批准。
    **校核 / 审核 / 批准必须由不同人员完成**；确需自校时必须显式
    传 allow_self_check=true，系统会留痕并在前台标注。
    """
    v = _get_version(db, version_id)
    doc = _get_document(db, v.document_id)
    require_project_view(doc.project_id, principal)

    inst = _run_in_of(db, v.id)
    if inst is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 4002, "message": "该版本没有进行中的审批流程"},
        )

    # **取本节点的全部待办任务，不能只取一条** ——
    # 相关单位可能有多个（监理 + 政府审查），是并列任务，各签各的。
    # 只取最新一条会把"另一个单位的人"误判成非处理人，
    # 进而要求 EDIT 权限而拒绝其签认（踩过的坑）。
    pending = wf.pending_tasks_of_node(db, inst.id, inst.current_node or "")
    if not pending:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 4002, "message": "当前没有待处理的签认任务"},
        )

    my_task = next((t for t in pending if t.assignee == principal.user_id), None)

    # 签认权限由**任务是否指派给你**决定，而不是 EDIT 权限：
    # 相关单位（监理、政府审查）本就不该能改设计文件，
    # 但他们必须能签自己的意见 —— 否则"复核"这件事就没法落地。
    # 非处理人的其他人仍需要 EDIT 权限（例如主办单位代为处理）。
    if my_task is None and not principal.is_superuser:
        require_action(principal, PermissionAction.EDIT, doc.project_id, doc.stage_code)
        # 代签时用本节点任意一条任务（由 workflow.decide 再校验归属）
        my_task = pending[0]

    inst = wf.decide(
        db,
        task_id=my_task.id,
        actor_id=principal.user_id,
        action=body.action.value,
        comment=body.comment,
        allow_self_check=body.allow_self_check,
    )
    docsvc.apply_workflow_result(db, version=v, inst=inst)

    # **退回要显式回到草稿态。**
    # 流程退回会新建一轮并回到首节点（CONFIRM），若只按"当前节点"映射状态，
    # 版本会又变成「校核中」—— 提交人就改不了了，只能干等，
    # 这与"退回后由提交人修改再重交"的业务语义矛盾（踩过的坑）。
    if body.action != TaskAction.APPROVE:
        v.state = DocumentState.DRAFT.value
        # 保留 submitted_at 作为"曾提交过"的记录，便于识别被退回的文件

    # 自校留痕：任一节点标记了自校，版本上就要显著标注
    if my_task.is_self_check:
        v.is_self_checked = True
        v.self_check_reason = (
            f"节点「{my_task.node_name or my_task.node_code}」由同一人处理（人员不足，走自校）"
        )

    action_label = {"APPROVE": "通过", "RETURN": "退回修改", "REJECT": "驳回"}.get(
        body.action.value, body.action.value
    )
    _audit(db, principal, "APPROVE" if body.action == TaskAction.APPROVE else "RETURN",
           "document_version", v.id, f"{doc.title} {v.version_no} {action_label}",
           doc.project_id, doc.stage_code)
    db.commit()
    return ApiResponse(data=_version_out(db, principal, v, doc))


@router.post("/versions/{version_id}/publish", response_model=ApiResponse[DocumentVersionOut],
             summary="发布（已批准 → 已发布）")
def publish_version(
    version_id: str, body: PublishIn, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[DocumentVersionOut]:
    """发布版本。发布后该版本成为文档的**唯一有效版本**，旧版本自动作废。

    只有「已批准」状态可以发布；已发布版本不可重复发布、不可回退。
    """
    v = _get_version(db, version_id)
    doc = _get_document(db, v.document_id)
    require_project_view(doc.project_id, principal)

    # 发布权限 = **本阶段的主办单位**，由《管理流程》矩阵推导。
    # 注意这里**不要求 EDIT**：发布是"对文件负责"的动作，不是"改文件"的动作。
    # 要求 EDIT 会把建设单位这类"有发布权但不编辑文件"的单位挡住，
    # 也会让审批与编辑两件事混在一起（这是踩过的坑）。
    if not principal.can(PermissionAction.PUBLISH, doc.project_id, doc.stage_code):
        from fastapi import HTTPException

        stage_label = STAGE_LABELS.get(StageCode(doc.stage_code), doc.stage_code)
        # 区分"阶段无责任"与"有责任但不是主办"，提示更有用
        if not principal.can(PermissionAction.VIEW, doc.project_id, doc.stage_code):
            visible = principal.visible_stages(doc.project_id)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": 3003,
                    "message": f"你在「{stage_label}」阶段没有责任，无法发布该阶段文件。"
                    f"（你可访问的阶段："
                    f"{'、'.join(STAGE_LABELS.get(s, s.value) for s in visible) or '无'}）",
                },
            )
        units = "、".join(
            UNIT_LABELS.get(UnitCode(u), u) for u in sorted(principal.units_in(doc.project_id))
        ) or "无"
        resp = principal.responsibility_in_stage(doc.project_id, doc.stage_code)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": 3002,
                "message": f"你在本项目的参与身份为「{units}」，"
                f"在「{stage_label}」阶段是"
                f"「{RESPONSIBILITY_LABELS.get(resp, '参与') if resp else '无'}」，"
                f"不是主办单位，无权发布文件。",
            },
        )

    docsvc.publish(
        db, version=v, actor_id=principal.user_id,
        void_reason_for_previous=body.void_reason_for_previous,
    )
    _audit(db, principal, "PUBLISH", "document_version", v.id,
           f"{doc.title} {v.version_no}", doc.project_id, doc.stage_code)

    # 发布后自动检查设计输入是否因来源更新而失效
    # 注意：这里不能让异常静默 —— 溯源检查失败必须可见，
    # 否则"勘察报告更新了设计却不知道"这个风险会被悄悄掩盖。
    stale = None
    stale_error: str | None = None
    try:
        from app.services import design_input as disvc

        stale = disvc.refresh_stale(db, doc.project_id)
    except Exception as exc:  # noqa: BLE001 —— 不阻断发布，但必须记录
        import logging

        logging.getLogger("app.publish").exception("refresh_stale 失败：%s", exc)
        stale_error = str(exc)

    # 发布后自动切片入知识库，供 AI 检索。
    # **不能让用户手工记得索引** —— 否则 AI 永远检索不到内容，
    # 而且"哪些文件进了知识库"会变得不可预期。
    index_note: str | None = None
    try:
        from app.services import retrieval as ret_svc

        chunks = ret_svc.index_document_version(db, version_id=v.id)
        index_note = f"{len(chunks)} 个知识块"
    except Exception as exc:  # noqa: BLE001 —— 索引失败不阻断发布
        import logging

        logging.getLogger("app.publish").exception("知识库索引失败：%s", exc)
        index_note = f"索引失败（{exc}）"

    db.commit()
    out = _version_out(db, principal, v, doc)

    bits: list[str] = ["发布成功"]
    if stale and stale.get("stale_count"):
        bits.append(f"{stale['stale_count']} 项设计输入参数因来源更新需要重新核验")
    if stale_error:
        bits.append(f"注意：设计输入溯源检查失败（{stale_error}）")
    if index_note:
        bits.append(f"已入知识库（{index_note}）")
    return ApiResponse(data=out, message="。".join(bits))


@router.post("/documents/{document_id}/revision", response_model=ApiResponse[DocumentVersionOut],
             summary="发起修订（生成新版本）")
def start_revision(
    document_id: str, body: RevisionIn, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[DocumentVersionOut]:
    """基于当前有效版本发起修订。

    已发布版本**不可直接修改**，必须走这里生成新版本 —— 这是铁律 3 的落地点。
    """
    doc = _get_document(db, document_id)
    require_action(principal, PermissionAction.EDIT, doc.project_id, doc.stage_code)

    v = docsvc.start_revision(db, document=doc, actor_id=principal.user_id, reason=body.reason)
    _audit(db, principal, "UPDATE", "document_version", v.id,
           f"{doc.title} 发起修订 {v.version_no}", doc.project_id, doc.stage_code)
    db.commit()
    return ApiResponse(data=_version_out(db, principal, v, doc))


@router.post("/versions/{version_id}/void", response_model=ApiResponse[DocumentVersionOut],
             summary="作废版本")
def void_version(
    version_id: str, body: VoidIn, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[DocumentVersionOut]:
    """作废版本。**必须填原因，且不物理删除**（保留完整历史）。"""
    v = _get_version(db, version_id)
    doc = _get_document(db, v.document_id)
    require_project_view(doc.project_id, principal)

    # 作废同发布：主办单位才有权（由权限矩阵推导），不额外要求 EDIT ——
    # 作废是"撤销对文件的确认"，不是"改文件"。
    if not principal.can(PermissionAction.PUBLISH, doc.project_id, doc.stage_code):
        from fastapi import HTTPException

        units = "、".join(
            UNIT_LABELS.get(UnitCode(u), u) for u in sorted(principal.units_in(doc.project_id))
        ) or "无"
        stage_label = STAGE_LABELS.get(StageCode(doc.stage_code), doc.stage_code)
        resp = principal.responsibility_in_stage(doc.project_id, doc.stage_code)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": 3002,
                "message": f"你在本项目的参与身份为「{units}」，"
                f"在「{stage_label}」阶段是"
                f"「{RESPONSIBILITY_LABELS.get(resp, '参与') if resp else '无'}」，"
                f"不是主办单位，无权作废文件。",
            },
        )

    docsvc.void_version(db, version=v, actor_id=principal.user_id, reason=body.reason)
    _audit(db, principal, "VOID", "document_version", v.id,
           f"{doc.title} {v.version_no} 作废：{body.reason}", doc.project_id, doc.stage_code)
    db.commit()
    return ApiResponse(data=_version_out(db, principal, v, doc))


# ============================================================
# 下载
# ============================================================


@router.get("/versions/{version_id}/download-token", response_model=ApiResponse[DownloadTokenOut],
            summary="获取签名下载令牌")
def download_token(
    version_id: str, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[DownloadTokenOut]:
    """返回短时效签名下载链接。

    签名**绑定 file_id + version_id + 过期时间**，
    拿到链接也不能改参数去下载同一文件的其它版本。
    """
    v = _get_version(db, version_id)
    doc = _get_document(db, v.document_id)
    require_project_view(doc.project_id, principal)
    _assert_secret_visible(principal, doc.project_id, doc.secret_level)
    require_action(principal, PermissionAction.DOWNLOAD, doc.project_id, doc.stage_code)

    tok = storage.make_download_token(v.file_id, v.id)
    _audit(db, principal, "DOWNLOAD", "document_version", v.id,
           f"{doc.title} {v.version_no}", doc.project_id, doc.stage_code, commit=True)

    return ApiResponse(
        data=DownloadTokenOut(
            file_id=tok["file_id"],
            version_id=tok["version_id"],
            expires_at=tok["expires_at"],
            ttl_seconds=tok["ttl_seconds"],
            url=tok["url"],
        )
    )


@router.get("/files/{file_id}/download", summary="下载文件（签名校验）")
def download_file(
    file_id: str,
    db: DbSession,
    version_id: str = Query(""),
    expires_at: int = Query(...),
    signature: str = Query(...),
) -> Response:
    """实际下载。

    注意：本接口**不要求登录**，靠签名保护 ——
    因为浏览器直接跳转下载时不一定带得上 Authorization 头。
    签名绑定了 version_id，所以仍然无法越权取到别的版本。
    """
    storage.verify_download_token(file_id, version_id, expires_at, signature)

    fo = storage.get_file_object(db, file_id)

    # 若指定了版本，校验文件与版本匹配（防篡改）
    if version_id:
        v = db.get(DocumentVersion, version_id)
        if v is None or v.file_id != file_id:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": 3004, "message": "下载链接与文件版本不匹配"},
            )

    content = storage.read_bytes(file_id)
    filename = fo.original_name or f"{file_id}{fo.ext or ''}"
    # 中文文件名用 RFC 5987 编码，避免 header 编码报错
    from urllib.parse import quote

    return Response(
        content=content,
        media_type=fo.mime or "application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "Content-Length": str(len(content)),
        },
    )


# ============================================================
# 审计辅助
# ============================================================


def _audit(
    db,
    principal,
    action: str,
    target_type: str,
    target_id: str,
    target_name: str | None,
    project_id: str | None = None,
    stage_code: str | None = None,
    commit: bool = False,
) -> None:
    """写审计日志。任何写操作都必须留痕。"""
    from app.models.ai import AuditLog

    m = principal.membership(project_id) if project_id else None
    db.add(
        AuditLog(
            project_id=project_id,
            stage_code=stage_code,
            actor=principal.user_id,
            actor_name=principal.user.name,
            actor_org_id=m.org_id if m else None,
            action=action,
            target_type=target_type,
            target_id=target_id,
            target_name=target_name,
            success=True,
        )
    )
    if commit:
        db.commit()
    else:
        db.flush()
