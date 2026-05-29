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

        return "1024x1024"

    @staticmethod
    def _parse_sdk_response(
        rsp,
    ) -> ImageGenerationResult:
        """解析 SDK 响应。"""

        items: list[
            ImageItem
        ] = []

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

        output = getattr(
            rsp,
            "output",
            None,
        )

        if output:
            results = getattr(
                output,
                "results",
                [],
            )

            if isinstance(
                results,
                list,
            ):
                for r in results:
                    url = (
                        getattr(
                            r,
                            "url",
                            "",
                        )
                        or ""
                    )

                    b64 = getattr(
                        r,
                        "url_b64",
                        None,
                    )

                    if b64:
                        items.append(
                            ImageItem(
                                url=(
                                    "data:image/png;"
                                    "base64,"
                                    f"{b64}"
                                ),
                                b64_json=b64,
                            )
                        )

                    elif url:
                        items.append(
                            ImageItem(
                                url=url,
                                b64_json=None,
                            )
                        )

        if (
            str(status_code)
            .startswith("2")
            and not items
        ):
            logger.warning(
                "[BailianImage] "
                "Success but "
                "no images returned. "
                "response=%s",
                repr(rsp),
            )

        status = (
            "completed"
            if items
            else "failed"
        )

        from app.core.contracts.provider import (
            ProviderKey as PK,
        )

        provider_value: str | PK = (
            "aliyun_bailian"
        )

        return ImageGenerationResult(
            images=items,
            provider=provider_value,
            provider_task_id=request_id,
            status=status,
        )