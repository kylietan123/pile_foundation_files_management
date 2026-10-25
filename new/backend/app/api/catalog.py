"""标准文档清单接口。

来源：陈铠俐版 `kylie/src/data/catalog.json`，并按最新 Excel 清单更新（当前 7 阶段 / 88 项，含 2 项运维待补充）。
在合并版中它不改写 oyx 的文件与版本模型，而是作为项目阶段页的“应上传清单”
基线，供工作台和后续阶段业务页复用。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentPrincipal
from app.core.upload_formats import allowed_extensions_for_formats
from app.models.enums import STAGE_LABELS, StageCode
from app.schemas import ApiResponse

router = APIRouter(prefix="/catalog", tags=["标准文档清单"])

PHASE_TO_STAGE = {
    "前期调研阶段": StageCode.PRE_SURVEY.value,
    "地质勘察阶段": StageCode.INVESTIGATION.value,
    "设计试桩阶段": StageCode.DESIGN_TEST_PILE.value,
    "工程设计阶段": StageCode.DESIGN.value,
    "桩基施工阶段": StageCode.CONSTRUCTION.value,
    "验收试桩阶段": StageCode.ACCEPT_TEST_PILE.value,
    "运维监测阶段": StageCode.MONITORING.value,
}

CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "document_catalog.json"


@lru_cache(maxsize=1)
def _load_catalog() -> list[dict]:
    with CATALOG_PATH.open("r", encoding="utf-8") as fh:
        rows = json.load(fh)
    for row in rows:
        stage_code = PHASE_TO_STAGE.get(row.get("phase_name"), "")
        row["stage_code"] = stage_code
        if stage_code:
            row["stage_label"] = STAGE_LABELS[StageCode(stage_code)]
        else:
            row["stage_label"] = row.get("phase_name", "")
        row["allowed_extensions"] = allowed_extensions_for_formats(row.get("file_formats"))
    return rows


@router.get("/documents", response_model=ApiResponse[list[dict]], summary="标准文档清单")
def list_document_catalog(
    principal: CurrentPrincipal,
    stage: Annotated[str | None, Query(description="阶段码，如 CONSTRUCTION")] = None,
) -> ApiResponse[list[dict]]:
    rows = _load_catalog()
    if stage:
        rows = [row for row in rows if row.get("stage_code") == stage]
    return ApiResponse(data=rows)
