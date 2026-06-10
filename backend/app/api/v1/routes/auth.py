"""认证相关端点：登录、刷新令牌、获取当前用户信息。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.auth import AccessTokenRead, LoginRequest, RefreshRequest, TokenPairRead, UserRead
from app.schemas.common import ApiResponse, success_response
from app.services import auth as auth_service

router = APIRouter()


@router.post("/login", response_model=ApiResponse[TokenPairRead], summary="登录")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> ApiResponse[TokenPairRead]:
    """用户名密码登录，返回 access_token 和 refresh_token。"""
    try:
        tokens = await auth_service.authenticate(db, username=body.username, password=body.password)
    except auth_service.InvalidCredentialsError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid username or password") from exc
    return success_response(tokens)


@router.post("/refresh", response_model=ApiResponse[AccessTokenRead], summary="刷新 access token")
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> ApiResponse[AccessTokenRead]:
    """使用 refresh_token 换取新的 access_token。"""
    try:
        token = await auth_service.refresh_access_token(db, refresh_token=body.refresh_token)
    except auth_service.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired refresh token") from exc
    return success_response(token)


@router.get("/me", response_model=ApiResponse[UserRead], summary="获取当前用户信息")
async def get_me(current_user: User = Depends(get_current_user)) -> ApiResponse[UserRead]:
    """获取当前登录用户的基本信息。"""
    return success_response(UserRead.model_validate(current_user))
