"""阿里百炼 DashScope 图片生成 API（原生模式）。

支持两种 DashScope 原生 API 路径，均使用 messages 输入格式：

1. **qwen-image 系列**（如 qwen-image-2.0-pro）：多模态对话 API
   ``POST /services/aigc/multimodal-generation/generation``
   对应 DashScope SDK ``MultiModalConversation.call()``

2. **wanx / wan2 系列**（如 wan2.7-image-pro）：图片生成 API
   ``POST /services/aigc/image-generation/generation``
   对应 DashScope SDK ``ImageGeneration.call()``

注意：DashScope 兼容模式的 ``/compatible-mode/v1/images/generations`` 不支持这些模型。
"""

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

# 模型名前缀 → API 模式映射
_QWEN_IMAGE_PREFIXES = ("qwen-image", "qwen-vl")
_WANX_IMAGE_PREFIXES = ("wanx", "wan2", "wan")

# DashScope 原生 API 基础地址（不含 /compatible-mode/v1）
_DASHSCOPE_NATIVE_BASE = "https://dashscope.aliyuncs.com/api/v1"
_COMPATIBLE_MODE_BASE = "/compatible-mode/v1"


def _resolve_api_base(base_from_cfg: str | None, fallback: str | None) -> str:
    """从配置的 base_url 解析出 DashScope 原生 API 基础地址。

    优先使用传入的 base_from_cfg；
    如果包含 ``/compatible-mode/v1``（兼容模式前缀），则替换为原生 API 基础地址。
    """
    if not base_from_cfg:
        return fallback or _DASHSCOPE_NATIVE_BASE
    base = base_from_cfg.rstrip("/")
    # 检测是否包含了兼容模式前缀 → 替换为原生 API 基础
    if _COMPATIBLE_MODE_BASE in base:
        return _DASHSCOPE_NATIVE_BASE
    return base


def _resolve_image_api_mode(model: str | None) -> str:
    """判断图片模型的 API 调用模式。

    Returns:
        ``"multimodal"`` — qwen-image 系列走多模态对话 API
        ``"image_gen"``   — wanx/wan2 系列走图片生成 API
        ``"synthesis"``  — 兜底：旧版 text2image 异步任务 API
    """
    if not model:
        return "image_gen"
    lower = model.strip().lower()
    if any(lower.startswith(p) for p in _QWEN_IMAGE_PREFIXES):
        return "multimodal"
    if any(lower.startswith(p) for p in _WANX_IMAGE_PREFIXES):
        return "image_gen"
    # 默认走图片生成 API（兼容大部分新模型）
    return "image_gen"


class AliyunBailianImageApiAdapter:
    """阿里百炼图片生成 HTTP；无状态，可单测替换。

    根据模型名自动选择正确的 DashScope 原生 API 路径。
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
    ) -> None:
        self._base_url = base_url or "https://dashscope.aliyuncs.com"

    async def generate(
        self,
        *,
        cfg: ProviderConfig,
        inp: ImageGenerationInput,
        timeout_s: float,
    ) -> ImageGenerationResult:
        mode = _resolve_image_api_mode(inp.model)
        if mode == "multimodal":
            return await self._generate_multimodal(cfg=cfg, inp=inp, timeout_s=timeout_s)
        elif mode == "image_gen":
            return await self._generate_image_gen(cfg=cfg, inp=inp, timeout_s=timeout_s)
        else:
            return await self._generate_synthesis(cfg=cfg, inp=inp, timeout_s=timeout_s)

    # ------------------------------------------------------------------
    # 路径 A: qwen-image 系列多模态对话 API
    # ------------------------------------------------------------------

    async def _generate_multimodal(
        self,
        *,
        cfg: ProviderConfig,
        inp: ImageGenerationInput,
        timeout_s: float,
    ) -> ImageGenerationResult:
        """通过 DashScope 多模态生成 API 调用 qwen-image 模型。"""
        try:
            import httpx
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("httpx is required for image generation tasks") from e

        base = _resolve_api_base(cfg.base_url, self._base_url)
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
        body = _build_multimodal_body(resolved_input)

        async with httpx.AsyncClient(timeout=timeout_s) as client:
            url = f"{base}/services/aigc/multimodal-generation/generation"
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

        return _parse_multimodal_response(data)

    # ------------------------------------------------------------------
    # 路径 B: wanx/wan2 系列图片生成 API（messages 格式）
    # ------------------------------------------------------------------

    async def _generate_image_gen(
        self,
        *,
        cfg: ProviderConfig,
        inp: ImageGenerationInput,
        timeout_s: float,
    ) -> ImageGenerationResult:
        """通过 DashScope 图片生成 API 调用 wanx/wan2 等模型。

        使用 messages 输入格式（与 ImageGeneration.call() SDK 一致），异步任务 + 轮询。
        """
        try:
            import httpx
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("httpx is required for image generation tasks") from e

        base = _resolve_api_base(cfg.base_url, self._base_url)
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
        body = _build_image_gen_body(resolved_input)

        # 1. 提交异步任务
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            url = f"{base}/services/aigc/image-generation/generation"
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
            submit_data = r.json()

        # 2. 提取 task_id 并轮询
        output = submit_data.get("output") or {}
        task_id = str(output.get("task_id") or "")
        if not task_id:
            # 同步返回兜底
            return _parse_image_gen_response(submit_data)

        result_data = await self._poll_task(base=base, headers=headers, task_id=task_id, timeout_s=timeout_s)
        return _parse_image_gen_response(result_data)

    # ------------------------------------------------------------------
    # 路径 C: 旧版 text2image 合成 API（异步任务，prompt 字符串输入）
    # ------------------------------------------------------------------

    async def _generate_synthesis(
        self,
        *,
        cfg: ProviderConfig,
        inp: ImageGenerationInput,
        timeout_s: float,
    ) -> ImageGenerationResult:
        """通过旧版 text2image API 调用（prompt 字符串输入，异步任务）。"""
        try:
            import httpx
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("httpx is required for image generation tasks") from e

        base = _resolve_api_base(cfg.base_url, self._base_url)
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
        body = _build_synthesis_body(resolved_input)

        async with httpx.AsyncClient(timeout=timeout_s) as client:
            url = f"{base}/services/aigc/text2image/image-synthesis"
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
            submit_data = r.json()

        output = submit_data.get("output") or {}
        task_id = str(output.get("task_id") or "")
        if not task_id:
            return _parse_native_response(submit_data)

        result_data = await self._poll_task(base=base, headers=headers, task_id=task_id, timeout_s=timeout_s)
        return _parse_native_response(result_data)

    async def _poll_task(
        self,
        *,
        base: str,
        headers: dict[str, str],
        task_id: str,
        timeout_s: float,
    ) -> dict[str, Any]:
        """轮询图片任务状态直至终态。"""
        import asyncio
        import httpx

        poll_interval = 1.0
        url = f"{base}/api/v1/tasks/{task_id}"

        async with httpx.AsyncClient(timeout=timeout_s) as client:
            while True:
                rr = await client.get(url, headers=headers)
                rr.raise_for_status()
                data = rr.json()

                output = data.get("output") or {}
                task_status = str(output.get("task_status") or "")

                if task_status in ("SUCCEEDED", "FAILED", "CANCELED"):
                    if task_status != "SUCCEEDED":
                        raise RuntimeError(
                            f"Aliyun Bailian image task failed: "
                            f"status={task_status} data={data!r}"
                        )
                    return data

                await asyncio.sleep(poll_interval)


# ---------------------------------------------------------------------------
# 请求体构建器
# ---------------------------------------------------------------------------

def _build_multimodal_body(inp: ImageGenerationInput) -> dict[str, Any]:
    """构建多模态对话请求体（用于 qwen-image 系列）。

    对应 DashScope SDK ``MultiModalConversation.call()`` 的底层 HTTP 结构。

    DashScope 原生格式要求：
    - 文本: ``{"text": "..."}``
    - 图片: ``{"image": "<可访问的HTTP URL>"}``

    注意：DashScope 不支持 ``data:image/png;base64,...`` 格式的 Data URL，
    也不支持 OpenAI 风格的嵌套 ``type:image_url`` 结构。
    """
    content_parts: list[dict[str, Any]] = [
        {"text": inp.prompt}
    ]

    # 参考图作为图片内容块（DashScope 扁平格式）
    for ref in inp.images:
        if ref.image_url:
            # 跳过 Data URL — DashScope 无法解析 base64 内联数据
            if ref.image_url.startswith("data:"):
                continue
            # 仅使用可公开访问的真实 HTTP(S) URL
            content_parts.append({"image": ref.image_url})
        elif ref.file_id:
            # file_id 暂不直接支持（DashScope 需要 URL）；
            # 若上游已将 file_id 解析为 image_url 则优先走上面的分支
            pass

    body: dict[str, Any] = {
        "model": inp.model or "qwen-image-2.0-pro",
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": content_parts,
                }
            ]
        },
        "parameters": {},
    }

    params: dict[str, Any] = {}
    params["result_format"] = "message"
    if inp.n is not None and inp.n > 0:
        params["n"] = min(inp.n, 4)
    if inp.size:
        params["size"] = inp.size
    if inp.seed is not None:
        params["seed"] = int(inp.seed)
    if inp.watermark is not None:
        params["watermark"] = bool(inp.watermark)
    body["parameters"] = params

    return body


def _build_image_gen_body(inp: ImageGenerationInput) -> dict[str, Any]:
    """构建图片生成请求体（用于 wanx/wan2 系列）。

    对应 DashScope SDK ``ImageGeneration.call()`` 的底层 HTTP 结构。
    输入为 messages 格式，支持 enable_sequential、n、size(如 "2K") 等参数。
    """
    message: dict[str, Any] = {
        "role": "user",
        "content": [{"type": "text", "text": inp.prompt}],
    }

    # 参考图附加到消息内容
    for ref in inp.images:
        if ref.image_url:
            message["content"].append({
                "type": "image_url",
                "image_url": {"url": ref.image_url},
            })
        elif ref.file_id:
            message["content"].append({
                "type": "file_id",
                "file_id": ref.file_id,
            })

    body: dict[str, Any] = {
        "model": inp.model or "wan2.7-image-pro",
        "input": {
            "messages": [message]
        },
        "parameters": {},
    }

    params: dict[str, Any] = {}
    if inp.size:
        # wan2.7 支持 "2K"/"1K" 等档位，也接受像素值
        params["size"] = inp.size
    if inp.n is not None and inp.n > 0:
        params["n"] = min(inp.n, 4)
    if inp.seed is not None:
        params["seed"] = int(inp.seed)
    if inp.response_format:
        params["response_format"] = inp.response_format
    if inp.watermark is not None:
        params["watermark"] = bool(inp.watermark)
    # wan2.7 支持顺序生成多张图
    params["enable_sequential"] = True
    body["parameters"] = params

    return body


def _build_synthesis_body(inp: ImageGenerationInput) -> dict[str, Any]:
    """构建旧版 text2image 合成请求体（prompt 字符串输入）。"""
    body: dict[str, Any] = {
        "model": inp.model or "wanx-v1",
        "input": {
            "prompt": inp.prompt,
        },
        "parameters": {},
    }

    params: dict[str, Any] = {}
    if inp.size:
        params["size"] = inp.size
    if inp.n is not None:
        params["n"] = min(inp.n, 4)
    if inp.seed is not None:
        params["seed"] = int(inp.seed)
    if inp.response_format:
        params["response_format"] = inp.response_format
    if inp.watermark is not None:
        params["watermark"] = bool(inp.watermark)
    body["parameters"] = params

    return body


# ---------------------------------------------------------------------------
# 响应解析器
# ---------------------------------------------------------------------------

def _parse_multimodal_response(data: dict[str, Any]) -> ImageGenerationResult:
    """解析多模态对话 API 响应，提取生成的图片 URL。

    qwen-image 系列实际返回结构::

        {
          "output": {
            "choices": [{
              "message": {
                "content": [
                  {"image": "<图片URL字符串>"},
                  {"type": "text", "text": "..."}
                ]
              }
            }]
          },
          "request_id": "...",
          "usage": {"height": 2048, "width": 2048, "image_count": 1}
        }
    """
    output = data.get("output") or {}
    images: list[ImageItem] = []

    # 路径 1: output.choices[].message.content[]（qwen-image 实际返回结构）
    choices = output.get("choices") or []
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        msg = choice.get("message") or {}
        content_list = msg.get("content") or []
        if isinstance(content_list, list):
            for block in content_list:
                if not isinstance(block, dict):
                    continue
                # qwen-image 返回: {"image": "<URL字符串>"}
                img_url = block.get("image")
                if img_url and isinstance(img_url, str):
                    images.append(ImageItem(url=img_url))
                    continue
                # 兼容 OpenAI 风格嵌套格式
                url = block.get("url")
                b64 = block.get("b64_json")
                if url or b64:
                    images.append(ImageItem(url=url, b64_json=b64))

    # 路径 2: output.results[]（兼容旧版或其他模型）
    if not images:
        raw_results = output.get("results") or []
        for result_item in raw_results:
            if not isinstance(result_item, dict):
                continue
            inner_choices = result_item.get("choices") or []
            for ic in inner_choices:
                imsg = ic.get("message") or ic
                for iblock in (imsg.get("content") or []):
                    if isinstance(iblock, dict):
                        u = iblock.get("url") or (iblock.get("image_url") or {}).get("url") if isinstance(iblock.get("image_url"), dict) else None
                        b = iblock.get("b64_json")
                        if u or b:
                            images.append(ImageItem(url=u, b64_json=b))
            # 扁平格式
            flat_url = result_item.get("url")
            if flat_url and not images:
                images.append(ImageItem(url=flat_url))

    if not images:
        raise RuntimeError(f"Aliyun Bailian multimodal response has no usable data: {data!r}")

    task_id = str(output.get("task_id") or data.get("request_id") or "")

    return ImageGenerationResult(
        images=images,
        provider="aliyun_bailian",
        provider_task_id=task_id or None,
        status=str(output.get("task_status") or "succeeded"),
    )


def _parse_image_gen_response(data: dict[str, Any]) -> ImageGenerationResult:
    """解析图片生成 API（ImageGeneration.call）响应。"""
    output = data.get("output") or {}

    raw_results = output.get("results") or []
    images: list[ImageItem] = []
    for item in raw_results:
        if isinstance(item, dict):
            url = item.get("url")
            b64 = item.get("b64_json")
            if url or b64:
                images.append(ImageItem(url=url, b64_json=b64))
            # 嵌套 choices 结构
            for choice in (item.get("choices") or []):
                msg = choice.get("message") or choice
                for block in (msg.get("content") or []):
                    if isinstance(block, dict):
                        u = block.get("url")
                        b = block.get("b64_json")
                        if u or b:
                            images.append(ImageItem(url=u, b64_json=b))

    if not images:
        # 兜底
        raw_items = data.get("data") or []
        for item in raw_items:
            if isinstance(item, dict):
                url = item.get("url")
                b64 = item.get("b64_json")
                if url or b64:
                    images.append(ImageItem(url=url, b64_json=b64))

    if not images:
        raise RuntimeError(f"Aliyun Bailian image-gen response has no usable data: {data!r}")

    task_id = str(output.get("task_id") or data.get("request_id") or "")

    return ImageGenerationResult(
        images=images,
        provider="aliyun_bailian",
        provider_task_id=task_id or None,
        status=str(output.get("task_status") or "succeeded"),
    )


def _parse_native_response(data: dict[str, Any]) -> ImageGenerationResult:
    """解析旧版 text2image 合成 API 响应（异步任务模式）。"""
    output = data.get("output") or {}
    raw_items = output.get("results") or []
    images: list[ImageItem] = []
    for item in raw_items:
        if isinstance(item, dict):
            url = item.get("url")
            b64 = item.get("b64_json")
            if url or b64:
                images.append(ImageItem(url=url, b64_json=b64))

    if not images:
        raw_items = data.get("data") or []
        for item in raw_items:
            if isinstance(item, dict):
                url = item.get("url")
                b64 = item.get("b64_json")
                if url or b64:
                    images.append(ImageItem(url=url, b64_json=b64))

    if not images:
        raise RuntimeError(f"Aliyun Bailian synthesis response has no usable data: {data!r}")

    task_id = str(output.get("task_id") or data.get("request_id") or "")

    return ImageGenerationResult(
        images=images,
        provider="aliyun_bailian",
        provider_task_id=task_id or None,
        status=str(output.get("task_status") or "succeeded"),
    )
