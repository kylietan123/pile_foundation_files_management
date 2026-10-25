"""字典接口。

**统一 ID 原则的对外入口。**
各阶段都从这里取桩型、土层、文档类型等选项，
不得各自维护一份列表 —— 否则跨阶段数据无法互通。
"""
from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import CurrentPrincipal, DbSession
from app.models.dict import DictCategory, DictItem
from app.schemas import ApiResponse, DictCategoryOut, DictItemOut

router = APIRouter(prefix="/dict", tags=["字典"])


@router.get("/categories", response_model=ApiResponse[list[DictCategoryOut]], summary="字典分类（含字典项）")
def list_categories(
    db: DbSession,
    principal: CurrentPrincipal,
    with_items: bool = True,
) -> ApiResponse[list[DictCategoryOut]]:
    """返回全部字典分类，可选是否附带字典项。

    前端做下拉框时用这个接口，不要硬编码选项。
    """
    cats = db.execute(select(DictCategory).order_by(DictCategory.sort)).scalars().all()

    items_by_cat: dict[str, list[DictItem]] = {}
    if with_items and cats:
        cids = [c.id for c in cats]
        rows = db.execute(
            select(DictItem)
            .where(DictItem.category_id.in_(cids), DictItem.active.is_(True))
            .order_by(DictItem.sort, DictItem.name)
        ).scalars().all()
        for it in rows:
            items_by_cat.setdefault(it.category_id, []).append(it)

    data = [
        DictCategoryOut(
            id=c.id,
            code=c.code,
            name=c.name,
            description=c.description,
            is_system=c.is_system,
            sort=c.sort,
            items=[DictItemOut.model_validate(i) for i in items_by_cat.get(c.id, [])],
        )
        for c in cats
    ]
    return ApiResponse(data=data)


@router.get("/items", response_model=ApiResponse[list[DictItemOut]], summary="按分类取字典项")
def list_items(
    db: DbSession,
    principal: CurrentPrincipal,
    category: str = Query(..., description="字典分类 code，如 PILE_TYPE / SOIL_LAYER / DOC_TYPE"),
) -> ApiResponse[list[DictItemOut]]:
    cat = db.execute(
        select(DictCategory).where(DictCategory.code == category)
    ).scalar_one_or_none()
    if cat is None:
        return ApiResponse(data=[], message=f"字典分类 {category} 不存在")

    rows = db.execute(
        select(DictItem)
        .where(DictItem.category_id == cat.id, DictItem.active.is_(True))
        .order_by(DictItem.sort, DictItem.name)
    ).scalars().all()
    return ApiResponse(data=[DictItemOut.model_validate(i) for i in rows])
