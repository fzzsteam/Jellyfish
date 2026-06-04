"""资产与镜头图片候选模型。"""

from __future__ import annotations

from enum import Enum

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin


class AssetImageCandidateSource(str, Enum):
    """候选图片来源。"""

    generation = "generation"
    upload = "upload"


class AssetImageCandidate(Base, TimestampMixin):
    """资产或镜头图片候选。

    target_type + target_id 指向具体图片槽位，file_id 指向一张可采用的候选图。
    当前采用图仍由图片槽位自身的 file_id 表达，候选池保留生成和上传历史。
    """

    __tablename__ = "asset_image_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="目标图片槽位类型")
    target_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="目标图片槽位 ID")
    file_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
        comment="候选图片文件 ID",
    )
    source_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=AssetImageCandidateSource.generation.value,
        comment="候选来源：generation/upload",
    )
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="来源引用")

    __table_args__ = (
        UniqueConstraint("target_type", "target_id", "file_id", name="uq_asset_image_candidate_target_file"),
        Index("ix_asset_image_candidates_target", "target_type", "target_id"),
        Index("ix_asset_image_candidates_file_id", "file_id"),
        Index("ix_asset_image_candidates_source", "source_type", "source_ref"),
    )


__all__ = ["AssetImageCandidate", "AssetImageCandidateSource"]
