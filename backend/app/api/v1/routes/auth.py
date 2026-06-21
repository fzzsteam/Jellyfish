"""认证相关端点：登录、刷新令牌、获取当前用户信息。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.auth import AccessTokenRead, ChangePasswordRequest, LoginRequest, RefreshRequest, TokenPairRead, UserRead
from app.schemas.common import ApiResponse, empty_response, success_response
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


@router.post("/change-password", response_model=ApiResponse[None], summary="修改当前用户密码")
async def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    """当前用户校验旧密码后修改自己的密码；成功后已签发的 token 立即失效。"""
    try:
        await auth_service.change_password(
            db,
            user_id=current_user.id,
            current_password=body.current_password,
            new_password=body.new_password,
        )
    except auth_service.InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="current password is incorrect"
        ) from exc
    return empty_response()
