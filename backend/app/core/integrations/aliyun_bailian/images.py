"""阿里百炼 DashScope 图片生成 API（兼容模式 /images/generations）。"""

from __future__ import annotations

import time
from typing import Any

from app.core.integrations.http_logging import (
    json_dumps_for_log,
    log_image_http_request,
    log_image_http_response,
    safe_body_for_log_aliyun_bailian_image,
)
from app.core.contracts.image_generation import (
    ImageGenerationInput,
    ImageGenerationResult,
    ImageItem,
)
from app.core.contracts.provider import ProviderConfig
from app.core.integrations.image_capabilities import resolve_image_size
from app.core.integrations.aliyun_bailian.image_capabilities import validate_aliyun_bailian_image_options


class AliyunBailianImageApiAdapter:
    """阿里百炼图片生成 HTTP；无状态，可单测替换。

    基于 DashScope 兼容模式，调用 ``POST /images/generations``。
    尺寸格式使用星号分隔（如 ``1024*1024``），与 OpenAI 的 ``x`` 不同。
    """

    async def generate(
        self,
        *,
        cfg: ProviderConfig,
        inp: ImageGenerationInput,
        timeout_s: float,
    ) -> ImageGenerationResult:
        try:
            import httpx
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("httpx is required for image generation tasks") from e

        base_url = (
            cfg.base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ).rstrip("/")
        resolved_size = resolve_image_size(
            provider="aliyun_bailian",
            model=inp.model,
            purpose=inp.purpose,
            target_ratio=inp.target_ratio,
            resolution_profile=inp.resolution_profile,
            requested_size=inp.size,
        )
        resolved_input = inp.model_copy(update={"size": resolved_size})
        validate_aliyun_bailian_image_options(resolved_input)
        headers = {
            "Authorization": f"Bearer {cfg.api_key}",
            "Content-Type": "application/json",
        }

        body = _build_image_body(resolved_input)

        async with httpx.AsyncClient(timeout=timeout_s) as client:
            url = f"{base_url}/images/generations"
            t0 = time.perf_counter()
            log_image_http_request(
                provider="aliyun_bailian",
                method="POST",
                url=url,
                headers=headers,
                body_log=json_dumps_for_log(safe_body_for_log_aliyun_bailian_image(body)),
            )
            r = await client.post(url, headers=headers, json=body)

            dt_ms = int((time.perf_counter() - t0) * 1000)
            resp_text = ""
            try:
                resp_text = r.text or ""
            except Exception:  # noqa: BLE001
                resp_text = ""
            log_image_http_response(
                provider="aliyun_bailian",
                status_code=r.status_code,
                elapsed_ms=dt_ms,
                resp_headers=dict(r.headers),
                resp_text=resp_text,
            )

            r.raise_for_status()
            data = r.json()

        return _parse_aliyun_bailian_images_payload(data)


def _build_image_body(inp: ImageGenerationInput) -> dict[str, Any]:
    """构建 DashScope 图片生成请求体。

    DashScope 兼容模式下参数基本对齐 OpenAI，但 size 格式为 ``W*H``（星号）。
    """
    body: dict[str, Any] = {
        "prompt": inp.prompt,
        "n": inp.n,
    }
    if inp.model:
        body["model"] = inp.model
    if inp.size:
        body["size"] = inp.size
    if inp.response_format:
        body["response_format"] = inp.response_format
    if inp.seed is not None:
        body["seed"] = int(inp.seed)
    if inp.watermark is not None:
        body["watermark"] = bool(inp.watermark)

    return body


def _parse_aliyun_bailian_images_payload(data: dict[str, Any]) -> ImageGenerationResult:
    """解析 DashScope 兼容模式的 images/generations 响应。"""
    raw_items = data.get("data") or []
    images: list[ImageItem] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        b64 = item.get("b64_json")
        if not url and not b64:
            continue
        images.append(ImageItem(url=url, b64_json=b64))

    if not images:
        raise RuntimeError(f"Aliyun Bailian images response has no usable data: {data!r}")

    provider_task_id = str(data.get("id") or data.get("task_id") or "")

    return ImageGenerationResult(
        images=images,
        provider="aliyun_bailian",
        provider_task_id=provider_task_id or None,
        status=str(data.get("status") or "succeeded"),
    )
