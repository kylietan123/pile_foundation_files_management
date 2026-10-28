"""桩基选型接口（设计阶段的选型方案）。

三件事：
1. **算**：给定项目条件（+ 可选勘察参数）跑规则引擎，返回桩型排序与建议桩参数；
2. **存**：设计人校对/确认后保存为方案（一个项目一条，可覆盖）；
3. **查**：读回已保存的方案，或列出可选桩型。

权限：读要能进本项目；写（保存方案）要**设计阶段的编辑权**——
与文件上传同一套判定，不新造权限概念。
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentPrincipal, CurrentUser, DbSession, require_action, require_project_view
from app.models.enums import PermissionAction, StageCode
from app.models.org import AppUser
from app.models.pile_selection import PileSelection
from app.models.project import Project
from app.schemas import (
    ApiResponse,
    PileReportIn,
    PileReportOut,
    PileSelectionOut,
    PileSelectionSaveIn,
    PileSuggestionOut,
    PileSuggestIn,
)
from app.services import pile_calc
from app.services import pile_report as reporter
from app.services import pile_selection as engine

router = APIRouter(prefix="/projects/{project_id}/pile-selection", tags=["桩基选型"])

STAGE = StageCode.DESIGN.value


# ============================================================
# 工具
# ============================================================


def _get_project(db: DbSession, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"code": 4004, "message": "项目不存在"})
    return project


def _conditions_dict(payload) -> dict:
    return payload.model_dump(exclude_none=False)


def _geo_dict(payload) -> dict | None:
    if payload is None:
        return None
    d = payload.model_dump()
    if not d.get("capacity_rows") and not d.get("strata"):
        # 既没有承载力表也没有地层 → 视作"没填勘察参数"，走典型组合
        return {k: v for k, v in d.items() if v} or None
    return d


def _to_out(db: DbSession, row: PileSelection) -> PileSelectionOut:
    name = None
    if row.confirmed_by:
        u = db.get(AppUser, row.confirmed_by)
        name = u.name if u else None
    return PileSelectionOut(
        id=row.id,
        project_id=row.project_id,
        stage_code=row.stage_code,
        conditions=row.conditions or {},
        geo=row.geo,
        overview=row.overview,
        calc_inputs=row.calc_inputs,
        main=row.main or {},
        base=row.base or {},
        snapshot=row.snapshot,
        reason=row.reason,
        status=row.status,
        confirmed_by=row.confirmed_by,
        confirmed_by_name=name,
        confirmed_at=row.confirmed_at,
        updated_at=row.updated_at,
        report_text=row.report_text,
        report_meta=row.report_meta,
        report_generated_at=row.report_generated_at,
    )


# ============================================================
# 可选桩型（校对表下拉）
# ============================================================


@router.get("/options", response_model=ApiResponse[dict], summary="可选桩型与条件说明")
def selection_options(project_id: str, db: DbSession, principal: CurrentPrincipal) -> ApiResponse[dict]:
    require_project_view(project_id, principal)
    from app.services import pile_selection_rules as R

    return ApiResponse(
        data={
            "pile_types": engine.pile_type_options(with_combos=True),
            "conditions": [
                {"key": k, "label": v, "hard": k in (
                    "metro_protection_zone", "inner_ring",
                    "near_viaduct_bridge", "dense_buildings_nearby",
                )}
                for k, v in R.CONDITION_LABELS.items()
            ],
            "bands": [{"code": c, "label": l} for c, l in R.BAND_LABELS.items()],
        }
    )


# ============================================================
# 试算（不落库）
# ============================================================


@router.post("/suggest", response_model=ApiResponse[PileSuggestionOut], summary="试算选型建议")
def suggest_selection(
    project_id: str, body: PileSuggestIn, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[PileSuggestionOut]:
    require_project_view(project_id, principal)
    _get_project(db, project_id)

    result = engine.suggest(_conditions_dict(body.conditions), _geo_dict(body.geo))
    # result 里已带 basis（survey / typical）：告诉前端"这次结论有没有勘察数据支撑"，
    # 避免界面在没有任何勘察输入时就摆出一份看起来很权威的建议。
    return ApiResponse(data=PileSuggestionOut.model_validate(result))


# ============================================================
# 已保存的方案
# ============================================================


@router.get("", response_model=ApiResponse[PileSelectionOut | None], summary="读取已保存的选型方案")
def get_selection(
    project_id: str, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[PileSelectionOut | None]:
    require_project_view(project_id, principal)
    row = db.execute(
        select(PileSelection).where(PileSelection.project_id == project_id)
    ).scalar_one_or_none()
    return ApiResponse(data=_to_out(db, row) if row else None)


@router.put("", response_model=ApiResponse[PileSelectionOut], summary="保存选型方案")
def save_selection(
    project_id: str,
    body: PileSelectionSaveIn,
    db: DbSession,
    principal: CurrentPrincipal,
    user: CurrentUser,
) -> ApiResponse[PileSelectionOut]:
    require_action(principal, PermissionAction.EDIT, project_id, STAGE)
    project = _get_project(db, project_id)

    known = {x["code"] for x in engine.pile_type_options()}
    for role, choice in (("主楼", body.main), ("地下室", body.base)):
        if choice.type_name not in known:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": 1001, "message": f"{role}桩型不存在：{choice.type_name}"},
            )

    conditions = _conditions_dict(body.conditions)
    geo = _geo_dict(body.geo)
    label = {
        x["code"]: x["label"] for x in engine.pile_type_options()
    }

    # 确认（CONFIRMED）必须有勘察依据 —— 选型是设计依据性结论，
    # 拿"典型组合"（历史项目经验值）定案等于没有依据。
    # 服务端重新跑一遍参数匹配来判断，不信任前端传来的 from_row。
    if body.status == "CONFIRMED":
        lacked: list[str] = []
        for role, choice, name in (
            ("main", body.main, "主楼"),
            ("base", body.base, "纯地下室"),
        ):
            picked = engine.pick_params(choice.type_name, role, conditions, geo)
            if not picked.get("from_row"):
                lacked.append(f"{name}「{label.get(choice.type_name, choice.type_name)}」")
        if len(lacked) == 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": 4000,
                    "message": (
                        "确认选型需要勘察依据：当前没有可匹配的勘察承载力表行，"
                        "桩参数只能取典型组合。请把勘察报告的承载力估算表录入后再确认；"
                        "在此之前可以保存草稿。"
                    ),
                },
            )

    reason = body.reason or engine.build_reason(
        conditions, body.main.type_name, body.base.type_name
    )

    row = db.execute(
        select(PileSelection).where(PileSelection.project_id == project_id)
    ).scalar_one_or_none()
    if row is None:
        row = PileSelection(
            project_id=project_id,
            stage_code=STAGE,
            conditions=conditions,
            geo=geo,
            main={},
            base={},
        )
        db.add(row)

    row.conditions = conditions
    row.geo = geo
    row.overview = body.overview.model_dump() if body.overview else None
    row.calc_inputs = body.calc_inputs.model_dump() if body.calc_inputs else None
    row.main = {
        "type_name": body.main.type_name,
        "label": label.get(body.main.type_name, body.main.type_name),
        "params": body.main.params.model_dump(),
    }
    row.base = {
        "type_name": body.base.type_name,
        "label": label.get(body.base.type_name, body.base.type_name),
        "params": body.base.params.model_dump(),
    }
    # 冻结一份引擎建议快照，方便事后解释"当初为什么这么选"
    row.snapshot = engine.suggest(conditions, geo)
    row.reason = reason
    row.remark = body.remark
    row.status = body.status
    if body.status == "CONFIRMED":
        row.confirmed_by = user.id
        row.confirmed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(row)
    # 方案是本项目的设计依据，记一条审计（与其他关键动作一致）
    _audit(db, principal, project, row)
    return ApiResponse(data=_to_out(db, row))


def _audit(db: DbSession, principal, project: Project, row: PileSelection,
           action: str | None = None, detail: str | None = None) -> None:
    from app.models.ai import AuditLog

    m = principal.membership(project.id)
    db.add(
        AuditLog(
            project_id=project.id,
            stage_code=STAGE,
            actor=principal.user_id,
            actor_name=principal.user.name,
            actor_org_id=m.org_id if m else None,
            action=action or ("CONFIRM" if row.status == "CONFIRMED" else "UPDATE"),
            target_type="pile_selection",
            target_id=row.id,
            target_name="桩基选型方案",
            detail=detail or (
                f"桩基选型方案（{row.status}）："
                f"主楼 {row.main.get('label')} / 地下室 {row.base.get('label')}"
            ),
        )
    )
    db.commit()


# ============================================================
# 桩基评估报告（TXT）
# ============================================================


def _build_report_text(row: PileSelection, body: PileReportIn) -> str:
    """用已保存的选型结论 + 概况/非主楼数据拼出报告全文。"""
    overview = body.overview.model_dump() if body.overview else (row.overview or None)
    calc_inputs = (
        body.calc_inputs.model_dump() if body.calc_inputs else (row.calc_inputs or {})
    )
    main = (row.main or {})
    base = (row.base or {})
    selection = {
        "main": {
            "type_name": main.get("type_name"),
            **(main.get("params") or {}),
        },
        "base": {
            "type_name": base.get("type_name"),
            **(base.get("params") or {}),
        },
    }
    meta = {
        "report_title": body.report_title or "桩基评估",
        "date": body.date or datetime.now(timezone.utc).strftime("%Y.%m.%d"),
        "basis_files": body.basis_files,
        "project_name": body.project_name
        or (overview or {}).get("project_name")
        or None,
        "conditions": row.conditions or {},
    }
    return reporter.build_report(overview, row.geo, selection, calc_inputs, meta)


@router.post("/report", response_model=ApiResponse[PileReportOut], summary="生成桩基评估报告（试算，不落库）")
def preview_report(
    project_id: str, body: PileReportIn, db: DbSession, principal: CurrentPrincipal
) -> ApiResponse[PileReportOut]:
    require_project_view(project_id, principal)
    row = db.execute(
        select(PileSelection).where(PileSelection.project_id == project_id)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 4000, "message": "请先试算并保存选型方案，再生成评估报告"},
        )
    try:
        text = _build_report_text(row, body)
    except ValueError as exc:
        # 缺关键数字（如单桩承载力、柱网、投影面积）时给出可读原因
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 4000, "message": f"报告无法生成：{exc}"},
        ) from exc
    return ApiResponse(
        data=PileReportOut(text=text, char_count=len(text), generated_at=None)
    )


@router.put("/report", response_model=ApiResponse[PileReportOut], summary="生成并保存评估报告")
def save_report(
    project_id: str,
    body: PileReportIn,
    db: DbSession,
    principal: CurrentPrincipal,
    user: CurrentUser,
) -> ApiResponse[PileReportOut]:
    require_action(principal, PermissionAction.EDIT, project_id, STAGE)
    project = _get_project(db, project_id)
    row = db.execute(
        select(PileSelection).where(PileSelection.project_id == project_id)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 4000, "message": "请先试算并保存选型方案，再生成评估报告"},
        )
    try:
        text = _build_report_text(row, body)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 4000, "message": f"报告无法生成：{exc}"},
        ) from exc

    row.overview = body.overview.model_dump() if body.overview else row.overview
    row.calc_inputs = (
        body.calc_inputs.model_dump() if body.calc_inputs else row.calc_inputs
    )
    row.report_text = text
    row.report_meta = {
        "report_title": body.report_title or "桩基评估",
        "date": body.date,
        "basis_files": body.basis_files,
        "project_name": body.project_name,
    }
    row.report_generated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    _audit(db, principal, project, row, action="EXPORT",
           detail=f"生成桩基评估报告（{len(text)} 字）")
    return ApiResponse(
        data=PileReportOut(text=text, char_count=len(text),
                           generated_at=row.report_generated_at)
    )


@router.get("/report.txt", summary="下载已保存的评估报告（TXT）")
def download_report(
    project_id: str, db: DbSession, principal: CurrentPrincipal,
    download: bool = False,
):
    """返回 text/plain。默认 inline（浏览器直接显示），?download=1 强制另存为。"""
    from urllib.parse import quote

    from fastapi import Response

    require_project_view(project_id, principal)
    row = db.execute(
        select(PileSelection).where(PileSelection.project_id == project_id)
    ).scalar_one_or_none()
    if row is None or not row.report_text:
        raise HTTPException(
            status_code=404,
            detail={"code": 4004, "message": "还没有生成过评估报告"},
        )
    project = _get_project(db, project_id)
    filename = f"{project.project_no}_桩基评估报告.txt"
    disposition = "attachment" if download else "inline"
    return Response(
        content=row.report_text.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(filename)}",
        },
    )
