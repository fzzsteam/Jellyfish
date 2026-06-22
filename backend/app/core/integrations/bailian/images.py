"""阿里百炼 (DashScope) 图片生成适配器（Wan2.7 官方 SDK 模式）。

仅支持：
- wan2.7-image-pro

使用 DashScope 官方 Python SDK (dashscope)
确保与阿里百炼官方调用方式完全一致。

官方示例：

    import dashscope
    from dashscope.aigc.image_generation import ImageGeneration

    dashscope.base_http_api_url = (
        "https://dashscope.aliyuncs.com/api/v1"
    )

    rsp = ImageGeneration.call(
        model="wan2.7-image-pro",
        api_key=api_key,
        messages=[
            {
                "role": "user",
                "content": [
                    {"text": "图片描述"}
                ]
            }
        ],
        n=1,
        size="1024x1024"
    )
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.contracts.image_generation import (
    ImageGenerationInput,
    ImageGenerationResult,
    ImageItem,
)
from app.core.contracts.provider import ProviderConfig

logger = logging.getLogger(__name__)


class BailianImageApiAdapter:
    """阿里百炼图片生成适配器（Wan2.7 SDK 模式）。"""

    DEFAULT_MODEL = "wan2.7-image-pro"

    def __init__(
        self,
        *,
        provider_config: ProviderConfig,
        timeout_s: float = 120.0,
    ):
        self._cfg = provider_config
        self._timeout = timeout_s
        self._api_key = provider_config.api_key or ""

    async def generate(
        self,
        input_: ImageGenerationInput,
    ) -> ImageGenerationResult:
        """异步生成图片（在线程池执行同步 SDK）。"""

        logger.info(
            "[BailianImage] Generating via SDK: "
            "model=%s n=%d size=%s",
            input_.model or self.DEFAULT_MODEL,
            input_.n,
            input_.size or "default",
        )

        loop = asyncio.get_running_loop()

        return await loop.run_in_executor(
            None,
            self._sync_generate,
            input_,
        )

    def _sync_generate(
        self,
        input_: ImageGenerationInput,
    ) -> ImageGenerationResult:
        """同步调用 DashScope SDK。"""

        try:
            import dashscope
            from dashscope.aigc.image_generation import (
                ImageGeneration,
            )
        except ImportError as e:
            raise RuntimeError(
                "dashscope SDK not installed. "
                "Run: uv add dashscope"
            ) from e

        # 强制使用官方 API 地址
        # 避免 SAE 环境变量残留错误 endpoint
        dashscope.base_http_api_url = (
            "https://dashscope.aliyuncs.com/api/v1"
        )

        # -------- 构建 message content --------

        message_content: list[dict[str, str]] = []

        # prompt
        message_content.append({
            "text": input_.prompt or ""
        })

        # 参考图（可选）
        for img_ref in input_.images:
            if img_ref.image_url:
                message_content.append({
                    "image": img_ref.image_url
                })

        message = {
            "role": "user",
            "content": message_content,
        }

        # -------- SDK 参数 --------

        sdk_kwargs: dict[str, Any] = {
            "model": input_.model
            or self.DEFAULT_MODEL,

            "api_key": self._api_key,

            "messages": [message],

            # 最大 4 张
            "n": min(input_.n, 4),

            "size": self._resolve_size(
                input_
            ),
        }

        # seed
        if input_.seed is not None:
            sdk_kwargs["seed"] = (
                input_.seed
            )

        # 多图一致性
        if input_.n > 1:
            sdk_kwargs[
                "enable_sequential"
            ] = True

        logger.info(
            "[BailianImage] SDK request: "
            "model=%s n=%s size=%s "
            "sequential=%s",
            sdk_kwargs["model"],
            sdk_kwargs["n"],
            sdk_kwargs["size"],
            sdk_kwargs.get(
                "enable_sequential",
                False,
            ),
        )

        # -------- 调用 SDK --------

        rsp = ImageGeneration.call(
            **sdk_kwargs
        )

        status_code = str(
            getattr(
                rsp,
                "status_code",
                "",
            )
        )

        request_id = getattr(
            rsp,
            "request_id",
            "",
        )

        logger.info(
            "[BailianImage] SDK response: "
            "status_code=%s "
            "request_id=%s",
            status_code,
            request_id,
        )

        # -------- 错误透传 --------

        if not status_code.startswith("2"):
            code = getattr(
                rsp,
                "code",
                "",
            )

            message = getattr(
                rsp,
                "message",
                "",
            )

            logger.error(
                "[BailianImage] "
                "SDK failed: "
                "status=%s "
                "code=%s "
                "message=%s "
                "request_id=%s",
                status_code,
                code,
                message,
                request_id,
            )

            raise RuntimeError(
                "[BailianImage] "
                f"SDK failed: "
                f"status={status_code}, "
                f"code={code}, "
                f"message={message}"
            )

        return self._parse_sdk_response(
            rsp
        )

    def _resolve_size(
        self,
        input_: ImageGenerationInput,
    ) -> str:
        """Wan2.7 size 解析。"""

        if input_.size:
            return input_.size

        if input_.purpose == "asset_image":
            profile = (input_.resolution_profile or "standard").strip().lower()
            if profile == "high":
                return "2048*2048"
            return "1024*1024"

        return "1024*1024"

    @staticmethod
    def _parse_sdk_response(
        rsp,
    ) -> ImageGenerationResult:
        """解析 DashScope SDK 图片生成响应。

        DashScope wan2.7-image-pro 实际返回的响应结构（2026-05-29 SAE 实测）::

            rsp: ImageGenerationResponse
            ├─ status_code: "200"
            ├─ request_id: "xxx"
            └─ output: ImageGenerationOutput
                └─ choices: [Choice]
                    └─ message: Message({'role': 'assistant', 'content': [
                          {'image': 'https://...oss-accelerate.aliyuncs.com/...png', 'type': 'image'}
                      ]})
                    └─ finish_reason: 'stop'

        注意：SDK 返回的是 Pydantic 模型对象，使用属性访问而非 __dict__。
        """

        items: list[ImageItem] = []

        status_code = str(
            getattr(rsp, "status_code", "")
        )

        request_id = getattr(
            rsp, "request_id", ""
        )

        # ====== 提取 output.choices 结构 ======
        output = getattr(rsp, "output", None)

        if not output:
            logger.warning(
                "[BailianImage] Response has no output field"
            )
            return ImageGenerationResult(
                images=[],
                provider="aliyun_bailian",
                provider_task_id=request_id,
                status="failed",
            )

        # DashScope SDK 返回: output.choices[].message.content[]
        choices = getattr(output, "choices", None)

        if not choices:
            logger.warning(
                "[BailianImage] Output has no choices, output=%s",
                repr(output)[:500],
            )
            return ImageGenerationResult(
                images=[],
                provider="aliyun_bailian",
                provider_task_id=request_id,
                status="failed",
            )

        for choice_idx, choice in enumerate(choices):
            # choice.message 可能是 Message 对象或 dict
            message = getattr(choice, "message", None)
            if message is None:
                continue

            # message.content 是列表: [{"image": url, "type": "image"}, ...]
            content_list = (
                getattr(message, "content", None)
                or (message.get("content") if isinstance(message, dict) else None)
            )

            if not content_list or not isinstance(content_list, list):
                continue

            for part in content_list:
                if isinstance(part, dict):
                    img_url = part.get("image") or ""
                    part_type = part.get("type", "")
                elif hasattr(part, "image"):
                    img_url = getattr(part, "image", "") or ""
                    part_type = getattr(part, "type", "")
                else:
                    continue

                # 提取图片 URL
                # 兼容两种模型响应格式:
                # - wan2.7-image-pro: [{"image": url, "type": "image"}]
                # - qwen-image-2.0-pro: [{"image": url}] (无 type 字段)
                if img_url and (not part_type or part_type == "image"):
                    items.append(ImageItem(url=img_url, b64_json=None))  # type: ignore[call-arg]
                    logger.info(
                        "[BailianImage] Found image: choice=%d url=%s",
                        choice_idx,
                        img_url[:80],
                    )

        # ====== 最终汇总 ======
        logger.info(
            "[BailianImage] Parsed: status_code=%s items_count=%d",
            status_code,
            len(items),
        )

        if str(status_code).startswith("2") and not items:
            logger.warning(
                "[BailianImage] Success but no images extracted. "
                "response=%s",
                repr(rsp)[:1000],
            )

        status = "completed" if items else "failed"

        from app.core.contracts.provider import ProviderKey as PK
        _provider_val: str | PK = "aliyun_bailian"  # type: ignore[assignment]

        return ImageGenerationResult(
            images=items,
            provider=_provider_val,  # type: ignore[assignment]
            provider_task_id=request_id,
            status=status,
        )
