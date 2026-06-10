"""认证相关请求/响应 Schema。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    """登录请求体。"""

    username: str = Field(..., min_length=1, description="用户名")
    password: str = Field(..., min_length=1, description="密码")


class RefreshRequest(BaseModel):
    """刷新令牌请求体。"""

    refresh_token: str = Field(..., min_length=1, description="刷新令牌")


class TokenPairRead(BaseModel):
    """登录成功返回的令牌对。"""

    access_token: str = Field(..., description="短期访问令牌")
    refresh_token: str = Field(..., description="长期刷新令牌")
    token_type: str = Field("bearer", description="令牌类型")


class AccessTokenRead(BaseModel):
    """刷新接口返回的新 access token。"""

    access_token: str = Field(..., description="新的访问令牌")
    token_type: str = Field("bearer", description="令牌类型")


class UserRead(BaseModel):
    """当前用户信息。"""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="用户 ID")
    username: str = Field(..., description="用户名")
    is_admin: bool = Field(..., description="是否管理员")
    is_active: bool = Field(..., description="是否启用")
