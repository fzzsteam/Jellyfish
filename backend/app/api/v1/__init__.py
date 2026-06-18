"""API v1 路由聚合。"""

from fastapi import APIRouter, Depends

from app.api.v1.routes import auth, film, health, llm, studio, script_processing
from app.api.v1.routes.admin import users as admin_users
from app.dependencies import get_current_user, require_admin

router = APIRouter()

router.include_router(health.router, tags=["health"])
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(
    admin_users.router,
    prefix="/admin/users",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)
router.include_router(film.router, prefix="/film", tags=["film"], dependencies=[Depends(get_current_user)])
router.include_router(llm.router, prefix="/llm", tags=["llm"], dependencies=[Depends(get_current_user)])
router.include_router(studio.router, prefix="/studio", dependencies=[Depends(get_current_user)])
router.include_router(script_processing.router, dependencies=[Depends(get_current_user)])
