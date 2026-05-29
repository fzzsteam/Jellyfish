"""阿里百炼 (DashScope) 图片生成适配器（原生 API）。

使用 DashScope 图像合成原生 API（非 OpenAI 兼容模式），
完整支持 wanx/wan2.x/wan2.7 系列模型的全部参数。

官方文档参考：
- https://help.aliyun.com/zh/model-studio/wanxiang-image-generation
- API: POST /api/v1/services/aigc/text2image/image-synthesis

对应 Python SDK 调用方式：
    from dashscope.aigc.image_generation import ImageGeneration
    ImageGeneration.call(model='wan2.7-image-pro', messages=[...], n=4, size='2K')
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.contracts.image_generation import (
    ImageGenerationInput,
    ImageGenerationResult,
    ImageItem,
)
from app.core.contracts.provider import ProviderConfig

logger = logging.getLogger(__name__)

#: DashScope 图像合成原生 API 端点
IMAGE_SYNTHESIS_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"

#: 支持的 size 映射（DashScope 特有格式 → 实际像素值）
SIZE_MAPPING: dict[str, str] = {
    # 标准尺寸
    "1024*1024": "1024x1024",
    "1536*1536": "1536x1536",
    "768*1344": "768x1344",
    "864*1152": "864x1152",
    "1152*864": "1152x864",
    "1344*768": "1344x768",
    "1440*960": "1440x960",
    "960*1440": "960x1440",
    # 高清规格
    "2K": "2048x2048",  # 2K 正方形
    "1:1": "1024x1024",
}


class BailianImageApiAdapter:
    """阿里百炼图片生成适配器（DashScope 原生 API 模式）。

    与 OpenAI 兼容模式不同，这里直接调用 DashScope 的
    text2image/image-synthesis 原生端点，以获得完整的
    百炼模型能力支持（如 2K、enable_sequential 等）。
    """

    def __init__(self, *, provider_config: ProviderConfig, timeout_s: float = 120.0):
        self._cfg = provider_config
        self._timeout = timeout_s
        # 从 provider_config.base_url 或默认值获取基础地址
        base = (provider_config.base_url or "").rstrip("/")
        if not base or "compatible-mode" in base:
            # 图片生成使用原生 API，不用兼容模式
            self._endpoint = IMAGE_SYNTHESIS_URL
        else:
            # 如果配置了自定义 base_url（如内网地址），拼接路径
            self._endpoint = f"{base}/services/aigc/text2image/image-synthesis"
        self._headers = {
            "Authorization": f"Bearer {provider_config.api_key}",
            "Content-Type": "application/json",
        }

    async def generate(self, input_: ImageGenerationInput) -> ImageGenerationResult:
        """调用 DashScope 原生图像合成 API 生成图片。"""
        payload = self._build_native_payload(input_)

        logger.info(
            "[BailianImage] Generating via native API: model=%s n=%d size=%s",
            input_.model or self._cfg.provider or "wan2.7-image-pro",
            input_.n,
            input_.size or "default",
        )

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(self._endpoint, json=payload, headers=self._headers)

            # 调试日志: 记录完整响应（特别是 400 错误时的具体原因）
            if resp.status_code != 200:
                logger.error(
                    "[BailianImage] API Error! status=%d url=%s\n"
                    "Request payload: %s\n"
                    "Response body: %s",
                    resp.status_code,
                    self._endpoint,
                    __import__("json").dumps(payload, ensure_ascii=False, indent=2),
                    resp.text,
                )

            resp.raise_for_status()
            data = resp.json()

        return self._parse_native_response(data)

    def _build_native_payload(self, input_: ImageGenerationInput) -> dict[str, Any]:
        """构建 DashScope 原生图像合成 API 请求体。

        参考官方 SDK 调用签名：
            ImageGeneration.call(
                model='wan2.7-image-pro',
                api_key=api_key,
                messages=[message],
                enable_sequential=True,
                n=4,
                size="2K"
            )
        """
        # 构建 messages（DashScope 多模态消息格式）
        message_content: list[dict[str, str]] = [{"text": input_.prompt}]

        # 可选：添加参考图片（如果有）
        for img_ref in input_.images:
            if img_ref.image_url:
                message_content.append({
                    "image": img_ref.image_url,
                })

        parameters: dict[str, Any] = {
            "size": self._resolve_size(input_),
            "n": min(input_.n, 4),  # DashScope 通常最多 4 张
        }

        # 随机种子
        if input_.seed is not None:
            parameters["seed"] = input_.seed

        # 启用顺序一致性模式（多图时保持角色一致）
        # 当 n > 1 时建议启用
        if input_.n > 1:
            parameters["enable_sequential"] = True

        payload: dict[str, Any] = {
            "model": input_.model or "wan2.7-image-pro",
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": message_content,
                    }
                ],
            },
            "parameters": parameters,
        }

        return payload

    def _resolve_size(self, input_: ImageGenerationInput) -> str:
        """解析目标尺寸为 DashScope 格式。

        DashScope 原生 API 支持的 size 格式：
        - 标准像素: "1024*1024", "1536*1536", "768*1344" 等（用 * 分隔）
        - 规格别名: "1:1", "2K" 等
        - 注意与 OpenAI 格式 "1024x1024"（用 x 分隔）不同！
        """
        if input_.size:
            # 如果传入的是 OpenAI 格式 (xxxxxyyyy)，转换为 DashScope 格式 (xxxx*yyyy)
            if "x" in input_.size and "*" not in input_.size:
                return input_.size.replace("x", "*")
            # 已经是 DashScope 格式或别名，直接返回
            return input_.size

        # 默认返回标准正方形
        return "1024*1024"

    def _parse_native_response(self, data: dict) -> ImageGenerationResult:
        """解析 DashScope 原生响应为统一的 ImageGenerationResult。"""

        items: list[ImageItem] = []

        # DashScope 响应结构参考 SDK 返回值：
        # {
        #   "status_code": "200",
        #   "request_id": "xxx",
        #   "code": "",
        #   "message": "",
        #   "output": {
        #       "results": [
        #           {"url": "https://...", "url_b64": null},
        #           ...
        #       ]
        #   },
        #   "usage": {...}
        # }
        output = data.get("output", {})
        results = output.get("results", [])

        if isinstance(results, list):
            for r in results:
                url = r.get("url") or ""
                b64 = r.get("url_b64") or r.get("b64_json") or ""
                if url:
                    items.append(ImageItem(url=url))  # type: ignore[call-arg]
                elif b64:
                    items.append(ImageItem(url=f"data:image/png;base64,{b64}"))  # type: ignore[call-arg]

        # 提取任务信息（用于调试和追踪）
        request_id = data.get("request_id") or ""

        # 如果没有解析到任何图片但状态码正常，记录警告
        status_code = data.get("status_code", "")
        if not items and str(status_code).startswith("2"):
            logger.warning(
                "[BailianImage] API returned success but no images parsed: %s",
                data,
            )

        # 判定最终状态
        status = "completed" if items else ("failed" if not str(status_code).startswith("2") else "unknown")

        # provider 字段需要是 ProviderKey 类型或兼容值
        from app.core.contracts.provider import ProviderKey as PK
        provider_value: str | PK = "aliyun_bailian"

        return ImageGenerationResult(
            images=items,
            provider=provider_value,  # type: ignore[assignment]
            provider_task_id=request_id,
            status=status,
        )
