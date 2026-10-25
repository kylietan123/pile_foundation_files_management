"""工作台接口 —— 跨项目的"我的工作"。

一个人同时参与多个项目，所以待办必须跨项目聚合，
否则每天要一个项目一个项目点进去看到底有什么要处理。
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentPrincipal, DbSession, require_project_view
from app.schemas import ApiResponse, WorkbenchOut
from app.services import workbench as wbsvc

router = APIRouter(prefix="/workbench", tags=["工作台"])


@router.get("/my-work", response_model=ApiResponse[WorkbenchOut], summary="我的工作（跨项目）")
def my_work(db: DbSession, principal: CurrentPrincipal) -> ApiResponse[WorkbenchOut]:
    """跨项目的我的工作。

    三类，按紧迫度排序：

      1 **等我签认** —— 别人提交了卡在我这里，不动手就拖住别人
      2 被退回       —— 我提交的被打回，需要我改后重交
      3 我经手在途   —— 知悉用，不必动手

    只返回当前用户参与的项目，权限过滤在查询层完成。
    """
    data = wbsvc.my_work(db, user_id=principal.user_id)
    n = data["awaiting_count"]
    return ApiResponse(
        data=WorkbenchOut(**data),
        message=(
            f"有 {n} 份文件等你签认"
            + (f"，其中 {data['overdue_count']} 项已逾期" if data["overdue_count"] else "")
            if n
            else "当前没有等你签认的文件"
        ),
    )


@router.get("/projects/{project_id}/work", response_model=ApiResponse[WorkbenchOut],
            summary="某项目的交办事项")
def project_work(
    project_id: str, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[WorkbenchOut]:
    """单个项目的交办事项（按阶段聚合）。

    阶段页与项目总览用 —— 回答"这个项目现在有哪些事压在我身上"。
    """
    require_project_view(project_id, principal)
    data = wbsvc.project_work(db, project_id=project_id, user_id=principal.user_id)
    return ApiResponse(data=WorkbenchOut(**data))
