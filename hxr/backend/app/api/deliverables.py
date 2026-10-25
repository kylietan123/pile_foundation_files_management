"""设计成果与交付接口。

**交付是设计阶段最需要"站得住"的环节。**

设计文件一旦交付给施工方，图纸版本出错就是责任问题。
所以"能不能交付"不能靠人记得检查，必须由系统逐项校验六道关卡：

  1 设计输入已锁定   —— 否则设计依据可以被悄悄改掉
  2 参数来源有效     —— 否则用了过期勘察数据
  3 成果齐备         —— 否则交付物缺项
  4 版本有效         —— 否则下游引用未发布版本
  5 问题闭环         —— 否则已知问题被带进施工
  6 变更闭环         —— 否则批了没改，图纸与现场不一致

第 1、2 关是这套系统区别于通用文档管理系统的关键：
通用系统只检查"文件在不在"，我们检查"设计依据站不站得住"。
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import (
    CurrentPrincipal,
    DbSession,
    require_action,
    require_project_view,
)
from app.models.enums import STAGE_LABELS, PermissionAction, StageCode
from app.schemas import (
    ApiResponse,
    DeliverableOut,
    DeliveryCheckOut,
    ManifestOut,
)
from app.services import deliverable as dlsvc

router = APIRouter(prefix="/projects/{project_id}/deliverables", tags=["设计成果与交付"])


@router.get("", response_model=ApiResponse[list[DeliverableOut]], summary="设计成果清单")
def list_deliverables(
    project_id: str,
    db: DbSession,
    principal: CurrentPrincipal,
    stage: str = Query(StageCode.DESIGN.value, description="阶段，默认设计阶段"),
) -> ApiResponse[list[DeliverableOut]]:
    """该阶段的成果清单及版本状态。

    对每一项标注：是否已有文件、当前有效版本、是否存在未发布的新版本。
    """
    require_project_view(project_id, principal)
    rows = dlsvc.list_deliverables(db, project_id, stage)
    return ApiResponse(data=[DeliverableOut(**r) for r in rows])


@router.get("/check", response_model=ApiResponse[DeliveryCheckOut], summary="交付完整性检查")
def check_delivery(
    project_id: str,
    db: DbSession,
    principal: CurrentPrincipal,
    stage: str = Query(StageCode.DESIGN.value),
) -> ApiResponse[DeliveryCheckOut]:
    """交付前完整性检查。

    六道关卡全部通过才允许交付。每一关都会说明：
      - 检查了什么（detail）
      - 为什么没过（blockers）
      - **该怎么办（suggestion）**
    """
    require_project_view(project_id, principal)
    result = dlsvc.check_delivery(db, project_id, stage)
    return ApiResponse(
        data=DeliveryCheckOut(**result),
        message=result["summary"],
    )


@router.get("/manifest", response_model=ApiResponse[ManifestOut], summary="生成交付清单")
def build_manifest(
    project_id: str,
    db: DbSession,
    principal: CurrentPrincipal,
    stage: str = Query(StageCode.DESIGN.value),
) -> ApiResponse[ManifestOut]:
    """生成交付清单。

    **只收录「已发布」版本的成果** —— 未发布的不能出现在交付清单里。
    这是版本状态机铁律 1 在交付场景的体现。

    权限：项目参与人均可查看。

    说明：原设计要求单独的 EXPORT 权限（导出 ≠ 下载），但经讨论认为
    交付清单的实际用途有限（真正的交付物是图纸与签章页），
    且"以单位为主体"后该区分意义不大，因此**已停用 EXPORT 动作**。
    方法保留，供后续做报表导出时复用。
    """
    # EXPORT 动作已停用（见下方说明），改为项目参与人即可查看
    require_project_view(project_id, principal)
    result = dlsvc.build_manifest(db, project_id, stage)

    from app.api.documents import _audit

    _audit(db, principal, "EXPORT", "deliverable_manifest", project_id,
           f"生成{STAGE_LABELS.get(StageCode(stage), stage)}阶段交付清单"
           f"（{result['item_count']} 项）",
           project_id, stage, commit=True)

    return ApiResponse(data=ManifestOut(**result))
