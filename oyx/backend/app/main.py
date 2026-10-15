"""FastAPI 应用入口。

启动（backend/ 目录下）：
    .venv\\Scripts\\python.exe -m uvicorn app.main:app --reload --port 8000

接口文档：http://127.0.0.1:8000/docs
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import (
    ai,
    auth,
    changes,
    deliverables,
    design_inputs,
    dicts,
    documents,
    issues,
    ledger,
    projects,
    tasks,
    workbench,
)
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时的初始化钩子（后续可放预热、调度器启动等）
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description=(
        "桩基工程全生命周期管理平台 —— 后端 API\n\n"
        "**权限模型**：角色 × 数据范围 × 阶段，三层同时校验。\n"
        "**版本铁律**：未发布（PUBLISHED 之外）的版本不可被下游引用。\n"
        "**AI 规则**：没有引用来源的回答不允许展示给用户。"
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS：开发期允许本地前端。生产部署到院内时改为白名单。
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# 统一响应格式：{code, message, data, trace_id}
# ============================================================


def _envelope(code: int, message: str, data=None, trace_id: str | None = None) -> dict:
    return {"code": code, "message": message, "data": data, "trace_id": trace_id}


@app.middleware("http")
async def add_trace_id(request: Request, call_next):
    request.state.trace_id = uuid.uuid4().hex
    response = await call_next(request)
    response.headers["X-Trace-Id"] = request.state.trace_id
    return response


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """把 HTTPException 转成统一包体。

    detail 支持两种形态：
      - dict：{"code": 3001, "message": "..."}  —— 业务错误码，优先
      - str ：直接用 4xx/5xx 作为 code
    """
    trace_id = getattr(request.state, "trace_id", None)
    if isinstance(exc.detail, dict):
        code = exc.detail.get("code", exc.status_code)
        message = exc.detail.get("message", "请求失败")
    else:
        code = exc.status_code
        message = str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(code, message, None, trace_id),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """参数校验错误 → code 1000 段。"""
    trace_id = getattr(request.state, "trace_id", None)
    # 精简错误信息，只保留定位与说明
    details = [
        {"loc": ".".join(str(x) for x in e.get("loc", [])), "msg": e.get("msg", "")}
        for e in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=_envelope(1001, "参数校验失败", details, trace_id),
    )


@app.exception_handler(PermissionError)
async def permission_error_handler(request: Request, exc: PermissionError):
    """权限引擎抛出的 PermissionError → 403 + code 3000 段。"""
    trace_id = getattr(request.state, "trace_id", None)
    return JSONResponse(
        status_code=403,
        content=_envelope(3002, str(exc), None, trace_id),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    trace_id = getattr(request.state, "trace_id", None)
    return JSONResponse(
        status_code=500,
        content=_envelope(5000, f"服务器内部错误：{exc}" if settings.DEBUG else "服务器内部错误", None, trace_id),
    )


# ============================================================
# 路由注册
# ============================================================

app.include_router(auth.router, prefix=settings.API_PREFIX)
app.include_router(projects.router, prefix=settings.API_PREFIX)
app.include_router(dicts.router, prefix=settings.API_PREFIX)
app.include_router(documents.router, prefix=settings.API_PREFIX)
app.include_router(changes.router, prefix=settings.API_PREFIX)
app.include_router(ledger.router, prefix=settings.API_PREFIX)
app.include_router(issues.router, prefix=settings.API_PREFIX)
app.include_router(deliverables.router, prefix=settings.API_PREFIX)
app.include_router(ai.router, prefix=settings.API_PREFIX)
app.include_router(design_inputs.router, prefix=settings.API_PREFIX)
app.include_router(workbench.router, prefix=settings.API_PREFIX)
app.include_router(tasks.router, prefix=settings.API_PREFIX)


@app.get("/api/v1/health", tags=["系统"], summary="健康检查")
def health() -> dict:
    return _envelope(0, "ok", {"status": "healthy", "app": settings.APP_NAME, "env": settings.APP_ENV})


@app.get("/", include_in_schema=False)
def root() -> dict:
    return _envelope(0, "ok", {"docs": "/docs", "api_prefix": settings.API_PREFIX})
