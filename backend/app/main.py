"""FastAPI 应用入口。"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles as _StaticFiles

from app.api.v1 import router as api_v1_router
from app.bootstrap import bootstrap_all_registries, seed_initial_admin
from app.config import settings
from app.core.db import async_session_maker, close_db, init_db
from app.schemas.common import ApiResponse
from app.services.points.billing import PointsDomainError


def _error_message(detail: object) -> str:
    """将异常 detail 转为前端可读的 message。"""
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):
        parts = []
        for item in detail:
            if isinstance(item, dict) and "msg" in item:
                loc = item.get("loc", ())
                loc_str = ".".join(str(x) for x in loc if x != "body")
                parts.append(f"{loc_str}: {item['msg']}" if loc_str else item["msg"])
            else:
                parts.append(str(item))
        return "; ".join(parts) if parts else "Validation error"
    return str(detail)


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """HTTP 异常统一为 { code, message, data: null }。"""
    from fastapi import HTTPException

    if isinstance(exc, HTTPException):
        code = exc.status_code
        message = _error_message(exc.detail)
    else:
        code = 500
        message = "Internal server error"
    body = ApiResponse[None](code=code, message=message, data=None, meta=None).model_dump()
    return JSONResponse(status_code=code, content=body)


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """422 校验异常统一为 { code: 422, message, data: null }。"""
    assert isinstance(exc, RequestValidationError)
    message = _error_message(exc.errors())
    body = ApiResponse[None](code=422, message=message, data=None, meta=None).model_dump()
    return JSONResponse(status_code=422, content=body)


async def points_domain_error_handler(request: Request, exc: "PointsDomainError") -> JSONResponse:
    """积分领域错误处理器：保留稳定 code 与结构化 data。

    为什么独立于通用 HTTPException 处理器：
        `PointsDomainError` 需要在 data 中回带结构化字段（available/required/shortfall、
        最新试算结果等），供前端按 `data.error_code` 精确分支。通用 HTTPException 处理器
        会把 data 置 null，丢失这些字段，故注册专属处理器。
    稳定字符串 code 放在 `data.error_code`（`ApiResponse.code` 已是 HTTP int 状态码）。
    """
    from app.services.points.billing import PointsDomainError  # 局部 import 避免循环依赖

    assert isinstance(exc, PointsDomainError)
    body = ApiResponse[dict](
        code=exc.status_code,
        message=exc.message,
        data={**exc.data, "error_code": exc.code},
    ).model_dump()
    return JSONResponse(status_code=exc.status_code, content=body)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化，关闭时清理。"""
    await init_db()
    async with async_session_maker() as db:
        await seed_initial_admin(db)
    bootstrap_all_registries()
    yield
    await close_db()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# 统一错误响应格式：{ code, message, data: null }
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, http_exception_handler)
# 积分领域错误：保留结构化 data.error_code，必须在通用 Exception 处理器之外独立注册
# （PointsDomainError 非 HTTPException 子类，不会被上面的 HTTPException 处理器捕获）。
app.add_exception_handler(PointsDomainError, points_domain_error_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router, prefix=settings.api_v1_prefix)
# 影视技能路由同时挂到主应用，保证 /api/v1/film 一定可访问


@app.get("/health")
async def health():
    """健康检查。"""
    from app.schemas.common import success_response
    return success_response({"status": "ok"})


class _SPAStaticFiles(_StaticFiles):
    """为 React SPA 提供静态文件，并确保入口文件不会被浏览器错误缓存。"""

    _NO_STORE = "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0"

    async def get_response(self, path: str, scope):
        """返回静态资源；前端路由 fallback 到 index.html 时禁用缓存。"""
        try:
            response = await super().get_response(path, scope)
        except Exception as exc:
            from starlette.exceptions import HTTPException as _HTTPException
            if isinstance(exc, _HTTPException) and exc.status_code == 404:
                response = await super().get_response("index.html", scope)
                response.headers["Cache-Control"] = self._NO_STORE
                return response
            raise
        if path == "index.html" or path == "env.js" or response.headers.get("content-type", "").startswith("text/html"):
            response.headers["Cache-Control"] = self._NO_STORE
        return response


_dist_dir = Path(__file__).resolve().parent.parent / "dist"
if _dist_dir.exists():
    app.mount("/", _SPAStaticFiles(directory=str(_dist_dir), html=True), name="frontend")
