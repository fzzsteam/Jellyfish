"""用户账号模型。"""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin


class User(Base, TimestampMixin):
    """用户账号。

    `token_version` 用于使已签发的 JWT 立即失效：管理员重置密码或禁用账号时递增该值，
    `get_current_user` 会校验 token 中的 `token_version` 与数据库当前值是否一致，
    不一致即视为该 token 已被吊销。
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="用户 ID")
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True, comment="用户名")
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False, comment="bcrypt 密码哈希")
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否管理员")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否启用")
    token_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="令牌版本号，递增可使已签发 token 失效"
    )
