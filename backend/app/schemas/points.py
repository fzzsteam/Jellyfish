"""积分计费相关的 Pydantic 请求/响应 Schema。

为什么独立成模块：积分试算/余额/流水/充值端点的 DTO 与鉴权/用户/资产等其它领域解耦，
集中放在此处便于跨层（route ↔ service）引用，且与 `app.services.points` 领域模型边界清晰。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.llm import ModelCategoryKey
from app.models.points import PointTransactionType


class PointsQuoteRequest(BaseModel):
    """积分试算请求体。

    - `business_type`: 业务类型标签（如 image_generation / video_generation），仅用于流水归因
      与 quote_token 绑定，不参与计价。
    - `category`: 模型类别，决定计价规则（文本/图片按单价；视频按时长×分辨率×单价）。
    - `model_id`: 显式模型 ID；为空时按当前用户默认模型解析。
    - `duration_seconds` / `resolution`: 视频类别的计价参数；文本/图片忽略。
    - `generation_count`: 当前固定为 1（多轮生成能力后续任务再放开）。
    """

    business_type: str = Field(..., min_length=1, description="业务类型标签，用于流水归因")
    category: ModelCategoryKey = Field(..., description="模型类别：text/image/video")
    model_id: str | None = Field(None, description="显式模型 ID；空则用用户默认模型")
    duration_seconds: int | None = Field(None, ge=1, description="视频时长（秒），仅 video 必填")
    resolution: Literal["720p", "1080p"] | None = Field(None, description="视频分辨率，仅 video 必填")
    generation_count: Literal[1] = Field(1, description="生成次数，当前仅支持 1")

    @model_validator(mode="after")
    def _require_video_params(self) -> "PointsQuoteRequest":
        """视频类别必须在请求体中显式提供 `duration_seconds` 与 `resolution`。

        为什么需要：计价器（pricing.calculate_points）对 video 缺这两个参数会抛 ValueError，
        若不在此拦截会冒泡成 500。这里在 schema 层提前校验，让 FastAPI 返回结构化的 422，
        与未知分辨率（Literal）→422 的行为保持一致，便于前端按字段定位错误。
        """
        if self.category == ModelCategoryKey.video:
            missing: list[str] = []
            if self.duration_seconds is None:
                missing.append("duration_seconds")
            if self.resolution is None:
                missing.append("resolution")
            if missing:
                raise ValueError(f"{missing} required when category=video")
        return self


class PointsQuoteResponse(BaseModel):
    """积分试算响应。

    - `resolved_model_id/name`: 实际解析到的模型（显式或默认）。
    - `using_default_model`: 是否走了用户默认模型（model_id 为空时为 True）。
    - `required_points`: 本次生成需扣减的积分。
    - `available_points`: 当前可用额度（balance - frozen）。
    - `sufficient`: 可用额度是否足够。
    - `quote_token`: 短期试算凭证 JWT，确认扣费时回带以防参数被篡改。
    """

    resolved_model_id: str = Field(..., description="解析后的模型 ID")
    resolved_model_name: str = Field(..., description="解析后的模型名称")
    using_default_model: bool = Field(..., description="是否使用了用户默认模型")
    required_points: int = Field(..., ge=0, description="本次生成需扣减积分")
    available_points: int = Field(..., ge=0, description="当前可用积分")
    sufficient: bool = Field(..., description="可用积分是否足够")
    quote_token: str = Field(..., description="短期试算凭证 JWT")


class PointsSummaryRead(BaseModel):
    """用户积分账户摘要：余额/冻结/可用。

    语义：`balance`=账户总额（含冻结），`frozen`=已冻结，`available=balance-frozen`。
    """

    balance: int = Field(..., description="积分余额（含冻结）")
    frozen: int = Field(..., ge=0, description="已冻结积分")
    available: int = Field(..., description="可用积分 = balance - frozen")


class PointTransactionRead(BaseModel):
    """积分流水只读 DTO。

    `type` 直接取 ORM 枚举值字符串（recharge/freeze/consume/unfreeze），
    `pricing_snapshot` 透传 JSON 快照用于历史对账。
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="流水 ID")
    user_id: str = Field(..., description="归属用户 ID")
    type: PointTransactionType = Field(..., description="流水类型")
    amount: int = Field(..., description="本次变更积分数量（符号随类型）")
    balance_after: int = Field(..., description="变更后余额")
    frozen_after: int = Field(..., description="变更后冻结额")
    source: str = Field(..., description="来源标签")
    billing_id: str | None = Field(None, description="计费单据 ID")
    business_type: str | None = Field(None, description="业务类型")
    business_id: str | None = Field(None, description="业务实体 ID")
    model_id: str | None = Field(None, description="涉及的模型 ID")
    pricing_snapshot: dict[str, Any] | None = Field(None, description="计价快照")
    remark: str | None = Field(None, description="备注")
    created_by: str | None = Field(None, description="操作人")


class PointsRechargeRequest(BaseModel):
    """管理员充值请求体。

    - `amount`: 非零整数；正数为充值，负数为扣减。
    - `remark`: 备注；负充值（扣减）必填。
    """

    amount: int = Field(..., description="充值金额，正数充值/负数扣减，不可为 0")
    remark: str | None = Field(None, description="备注；负充值必填")
