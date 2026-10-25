"""文档台账与追溯接口。

**这是回答"文件丢了谁负责"的那一屏。**

三个接口：
    GET /projects/{id}/ledger              项目文档台账（含"在谁手上"）
    GET /projects/{id}/ledger/awaiting-me  只列等我处理的
    GET /projects/{id}/stage-responsibility 七阶段责任总览

台账的每一行都给出：
    - 主办单位（该阶段矩阵里的主要责任单位）—— 追责对象
    - 上传人 / 发布人（姓名 + 工号）—— 谁做的
    - 当前待签单位 —— **文件现在在谁手上**
    - 签认轨迹 —— 每一轮谁签的、什么时候
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import CurrentPrincipal, DbSession, require_project_view
from app.models.enums import STAGE_LABELS, StageCode
from app.schemas import (
    ApiResponse,
    LedgerOut,
    StageResponsibilityOut,
)
from app.services import ledger as lgsvc

router = APIRouter(prefix="/projects/{project_id}", tags=["文档台账与追溯"])


@router.get("/ledger", response_model=ApiResponse[LedgerOut], summary="项目文档台账")
def get_ledger(
    project_id: str,
    db: DbSession,
    principal: CurrentPrincipal,
    stage: str | None = Query(None, description="只看某阶段"),
    awaiting_me: bool = Query(False, description="只列等我处理的"),
) -> ApiResponse[LedgerOut]:
    """项目文档台账。

    **每一行都能追到人**：谁上传的、谁签认的、现在卡在哪个单位。
    可见范围受权限约束（阶段 + 敏感等级），过滤在查询层完成。
    """
    require_project_view(project_id, principal)

    # 阶段过滤要走权限：不能靠前端不传 stage 就绕过阶段限制
    if stage:
        if not principal.can_view_stage(project_id, stage):
            visible = principal.visible_stages(project_id)
            from fastapi import HTTPException, status as http_status

            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail={
                    "code": 3003,
                    "message": f"你在「{STAGE_LABELS.get(StageCode(stage), stage)}」阶段没有责任，"
                    f"看不到该阶段的文件。"
                    f"（你可访问的阶段："
                    f"{'、'.join(STAGE_LABELS.get(s, s.value) for s in visible) or '无'}）",
                },
            )

    data = lgsvc.build_ledger(
        db,
        project_id=project_id,
        stage_code=stage,
        only_awaiting_me=principal.user_id if awaiting_me else None,
        max_secret_level=principal.max_secret_level(project_id),
    )

    # 阶段级权限：把用户看不到的阶段整段滤掉（防止不传 stage 时越权）
    allowed = {s.value for s in principal.visible_stages(project_id)}
    if not principal.is_superuser and allowed:
        data["items"] = [i for i in data["items"] if i.get("stage_code") in allowed]
        data["item_count"] = len(data["items"])
        data["awaiting_count"] = sum(1 for i in data["items"] if i["awaiting_me"])

    return ApiResponse(data=LedgerOut(**data))


@router.get("/ledger/awaiting-me", response_model=ApiResponse[LedgerOut],
            summary="等我处理的文件")
def ledger_awaiting_me(
    project_id: str, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[LedgerOut]:
    """只列"现在等我签认"的文件 —— 跨阶段，按人聚合。

    这是"我的待办"在文档维度上的视图：不按阶段展开，
    直接告诉我"这几份文件卡在我这里"。
    """
    require_project_view(project_id, principal)
    data = lgsvc.build_ledger(
        db,
        project_id=project_id,
        stage_code=None,
        only_awaiting_me=principal.user_id,
        max_secret_level=principal.max_secret_level(project_id),
    )
    return ApiResponse(
        data=LedgerOut(**data),
        # 注意 message 是 str（不能传 None）—— 没有待办时显式给文案
        message=(
            f"有 {data['awaiting_count']} 份文件等你签认"
            if data["awaiting_count"]
            else "当前没有等你签认的文件"
        ),
    )


@router.get("/stage-responsibility", response_model=ApiResponse[list[StageResponsibilityOut]],
            summary="七阶段责任总览")
def stage_responsibility(
    project_id: str, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[list[StageResponsibilityOut]]:
    """七阶段各自的主办单位、全部参与单位及责任等级。

    这一屏直接展示《管理流程》矩阵在系统里的落地结果 ——
    哪个阶段谁主办、谁相关、谁只参与。
    """
    require_project_view(project_id, principal)
    rows = lgsvc.stage_responsibility_summary(db, project_id)
    return ApiResponse(data=[StageResponsibilityOut(**r) for r in rows])
