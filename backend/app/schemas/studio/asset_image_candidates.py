"""资产图片候选 API schema。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.models.studio_image_candidates import AssetImageCandidate


class AssetImageCandidateRead(BaseModel):
    """图片候选读模型。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    target_type: str
    target_id: int
    file_id: str
    source_type: str
    source_ref: str | None = None
    is_adopted: bool = False

    @classmethod
    def from_candidate(cls, candidate: AssetImageCandidate, *, current_file_id: str | None) -> "AssetImageCandidateRead":
        """从 ORM 候选行构造读模型，并补充是否为当前采用图。"""
        data = cls.model_validate(candidate)
        data.is_adopted = bool(current_file_id and candidate.file_id == current_file_id)
        return data


class AssetImageCandidateAttachRequest(BaseModel):
    """把文件加入目标图片槽位候选池。"""

    file_ids: list[str] = Field(..., min_length=1, max_length=100)
    source_type: str = Field("upload", pattern="^(generation|upload)$")
    source_ref: str | None = None
    auto_adopt_if_empty: bool = False


__all__ = ["AssetImageCandidateAttachRequest", "AssetImageCandidateRead"]
