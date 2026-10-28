"""标准文档清单落地接口。

把 document_catalog.json 里的 84 类标准文档，变成每个项目、每个阶段可操作的
「待上传清单」：每一项可 上传 / 标记不需要（原因）/ 暂未上传（原因）/ 更新版本。
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import select

from app.api.catalog import _load_catalog
from app.api.deps import CurrentPrincipal, DbSession, require_action, require_project_view
from app.models.document import Document, DocumentChecklist
from app.models.enums import PermissionAction
from app.schemas import ApiResponse, ChecklistStatusIn
from app.services import documents as docsvc
from app.services import storage

router = APIRouter(prefix="/projects/{project_id}/checklist", tags=["标准清单"])


def _catalog_item(doc_code: str) -> dict | None:
    for r in _load_catalog():
        if r.get("doc_code") == doc_code:
            return r
    return None


def _checklist_map(db, project_id: str) -> dict[str, DocumentChecklist]:
    rows = db.execute(
        select(DocumentChecklist).where(DocumentChecklist.project_id == project_id)
    ).scalars().all()
    return {r.doc_code: r for r in rows}


def _doc_map(db, project_id: str) -> dict[str, Document]:
    rows = db.execute(
        select(Document).where(
            Document.project_id == project_id, Document.doc_code.is_not(None)
        )
    ).scalars().all()
    m: dict[str, Document] = {}
    for d in rows:
        if d.doc_code and d.doc_code not in m:
            m[d.doc_code] = d
    return m


def _item_out(r: dict, st: DocumentChecklist | None, doc: Document | None) -> dict:
    return {
        "doc_code": r.get("doc_code"),
        "doc_name": r.get("doc_name"),
        "responsible_unit_name": r.get("responsible_unit_name"),
        "file_formats": r.get("file_formats"),
        "is_required": r.get("is_required"),
        "stage_code": r.get("stage_code"),
        "status": st.status if st else "PENDING",
        "reason": st.reason if st else None,
        "document_id": doc.id if doc else None,
        "document_title": doc.title if doc else None,
        "current_version_id": doc.current_version_id if doc else None,
    }


@router.get("", response_model=ApiResponse[list[dict]], summary="某阶段待上传清单（含状态）")
def list_checklist(
    project_id: str,
    db: DbSession,
    principal: CurrentPrincipal,
    stage: Annotated[str | None, Query(description="阶段码")] = None,
) -> ApiResponse[list[dict]]:
    require_project_view(project_id, principal)

    status_map = _checklist_map(db, project_id)
    doc_map = _doc_map(db, project_id)

    rows = _load_catalog()
    if stage:
        rows = [r for r in rows if r.get("stage_code") == stage]

    out = [
        _item_out(r, status_map.get(r.get("doc_code")), doc_map.get(r.get("doc_code")))
        for r in rows
    ]
    return ApiResponse(data=out)


@router.post("/{doc_code}/status", response_model=ApiResponse[dict], summary="标记清单条目（不需要 / 暂未上传）")
def set_checklist_status(
    project_id: str,
    doc_code: str,
    body: ChecklistStatusIn,
    db: DbSession,
    principal: CurrentPrincipal,
) -> ApiResponse[dict]:
    item = _catalog_item(doc_code)
    if item is None:
        raise HTTPException(status_code=404, detail="清单条目不存在")

    require_action(principal, PermissionAction.EDIT, project_id, item["stage_code"])

    row = db.execute(
        select(DocumentChecklist).where(
            DocumentChecklist.project_id == project_id,
            DocumentChecklist.doc_code == doc_code,
        )
    ).scalar_one_or_none()

    if row is None:
        row = DocumentChecklist(
            project_id=project_id,
            stage_code=item["stage_code"],
            doc_code=doc_code,
            status=body.status,
            reason=body.reason,
            updated_by=principal.user_id,
        )
        db.add(row)
    else:
        row.status = body.status
        row.reason = body.reason
        row.updated_by = principal.user_id
    db.commit()

    return ApiResponse(data={"doc_code": doc_code, "status": body.status, "reason": body.reason})


@router.post("/{doc_code}/upload", response_model=ApiResponse[dict], summary="按清单条目上传文件（含更新版本）")
async def upload_checklist_doc(
    project_id: str,
    doc_code: str,
    db: DbSession,
    principal: CurrentPrincipal,
    file: Annotated[UploadFile, File(description="文件本体")],
    version_no: Annotated[str | None, Form()] = None,
) -> ApiResponse[dict]:
    item = _catalog_item(doc_code)
    if item is None:
        raise HTTPException(status_code=404, detail="清单条目不存在")

    stage_code = item["stage_code"]
    require_action(principal, PermissionAction.EDIT, project_id, stage_code)

    # 找到或创建该清单条目对应的文档
    doc = db.execute(
        select(Document).where(
            Document.project_id == project_id, Document.doc_code == doc_code
        )
    ).scalar_one_or_none()

    if doc is None:
        doc = Document(
            project_id=project_id,
            stage_code=stage_code,
            title=item.get("doc_name") or doc_code,
            doc_code=doc_code,
            discipline="GENERAL",
            secret_level="INTERNAL",
            created_by=principal.user_id,
        )
        db.add(doc)
        db.flush()

    fo = await storage.save_upload(db, file, principal.user_id)
    v = docsvc.create_version(
        db,
        document=doc,
        file_id=fo.file_id,
        version_no=version_no,
        change_summary=None,
        creator_id=principal.user_id,
        remark=None,
    )

    # 标记为已上传
    row = db.execute(
        select(DocumentChecklist).where(
            DocumentChecklist.project_id == project_id,
            DocumentChecklist.doc_code == doc_code,
        )
    ).scalar_one_or_none()
    if row is None:
        row = DocumentChecklist(
            project_id=project_id,
            stage_code=stage_code,
            doc_code=doc_code,
            status="UPLOADED",
            updated_by=principal.user_id,
        )
        db.add(row)
    else:
        row.status = "UPLOADED"
        row.reason = None
        row.updated_by = principal.user_id

    db.commit()
    return ApiResponse(
        data={"doc_code": doc_code, "status": "UPLOADED", "document_id": doc.id, "version_id": v.id}
    )
