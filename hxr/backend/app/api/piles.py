"""桩位 / 试桩台账接口。

试桩台账是「设计试桩 / 验收试桩」阶段的阶段功能：
列出试桩，并回填实测承载力，与设计承载力做对比。
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.deps import CurrentPrincipal, DbSession, require_action, require_project_view
from app.models.enums import PermissionAction
from app.models.project import Pile
from app.schemas import ApiResponse, PileOut, PileUpdateIn

router = APIRouter(tags=["桩位与试桩"])


@router.get("/projects/{project_id}/piles", response_model=ApiResponse[list[PileOut]], summary="桩位列表（可筛试桩）")
def list_piles(
    project_id: str,
    db: DbSession,
    principal: CurrentPrincipal,
    is_test_pile: Annotated[bool | None, Query(description="只返回试桩/工程桩")] = None,
) -> ApiResponse[list[PileOut]]:
    require_project_view(project_id, principal)

    stmt = select(Pile).where(Pile.project_id == project_id)
    if is_test_pile is not None:
        stmt = stmt.where(Pile.is_test_pile == is_test_pile)
    rows = db.execute(stmt.order_by(Pile.is_test_pile.desc(), Pile.zone, Pile.pile_no)).scalars().all()
    return ApiResponse(data=[PileOut.model_validate(p) for p in rows])


@router.patch("/piles/{pile_id}", response_model=ApiResponse[PileOut], summary="回填试桩实测承载力")
def update_pile(
    pile_id: str,
    body: PileUpdateIn,
    db: DbSession,
    principal: CurrentPrincipal,
) -> ApiResponse[PileOut]:
    pile = db.get(Pile, pile_id)
    if pile is None:
        raise HTTPException(status_code=404, detail={"code": 4004, "message": "桩位不存在"})

    require_action(principal, PermissionAction.EDIT, pile.project_id, None)

    if body.actual_capacity is not None:
        pile.actual_capacity = body.actual_capacity
    if body.actual_length is not None:
        pile.actual_length = body.actual_length
    if body.detection_method is not None:
        pile.detection_method = body.detection_method
    if body.review_status is not None:
        pile.review_status = body.review_status
    if body.review_note is not None:
        pile.review_note = body.review_note
    if body.status is not None:
        pile.status = body.status
    if body.remark is not None:
        pile.remark = body.remark

    db.commit()
    return ApiResponse(data=PileOut.model_validate(pile))
