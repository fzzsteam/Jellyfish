"""阿里百炼 DashScope 视频生成 API（原生模式）。

调用流程（happyhorse / wanx 视频模型）：
1. POST ``/services/aigc/video-generation/video-synthesis`` → 获取 task_id（异步模式）
2. 轮询 GET ``/tasks/{task_id}`` → SUCCEEDED / FAILED

关键差异（与 OpenAI 兼容模式不同）：
- 端点路径为 ``video-synthesis``（不是 ``synthesis``）
- 请求必须携带 ``X-DashScope-Async: enable`` 头
- 参考帧通过 ``input.media[]`` 数组传递
- resolution 使用字符串档位 ``"720P"`` / ``"1080P"``
"""

from __future__ import annotations

from typing import Any

from app.core.integrations.aliyun_bailian.video_payload import (
    build_async_headers,
    build_synthesis_body,
)
from app.core.contracts.provider import ProviderConfig


# DashScope 原生 API 基础地址（不含 /compatible-mode/v1）
_DASHSCOPE_NATIVE_BASE = "https://dashscope.aliyuncs.com/api/v1"
_COMPATIBLE_MODE_BASE = "/compatible-mode/v1"


def _resolve_api_base(base_from_cfg: str | None, fallback: str | None) -> str:
    """从配置的 base_url 解析出 DashScope 原生 API 基础地址。

    如果包含 ``/compatible-mode/v1``（兼容模式前缀），则替换为原生 API 基础地址。
    """
    if not base_from_cfg:
        return fallback or _DASHSCOPE_NATIVE_BASE
    base = base_from_cfg.rstrip("/")
    if _COMPATIBLE_MODE_BASE in base:
        return _DASHSCOPE_NATIVE_BASE
    return base


class AliyunBailianVideoApiAdapter:
    """阿里百炼视频任务 HTTP：创建与查询（原生 DashScope API）。"""

    def __init__(
        self,
        *,
        base_url: str | None = None,
    ) -> None:
        self._base_url = base_url or "https://dashscope.aliyuncs.com"

    async def create_video_task(
        self,
        *,
        cfg: ProviderConfig,
        input_: Any,  # VideoGenerationInput
        timeout_s: float,
    ) -> str:
        try:
            import httpx
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("httpx is required for video generation tasks") from e

        base = _resolve_api_base(cfg.base_url, self._base_url)
        headers = build_async_headers(cfg.api_key)
        body = build_synthesis_body(input_)

        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.post(
                f"{base}/services/aigc/video-generation/video-synthesis",
                headers=headers,
                json=body,
            )
            r.raise_for_status()
            data: dict[str, Any] = r.json()
            output = data.get("output") or {}
            # 异步模式下 task_id 在 output.task_id 中
            task_id = str(output.get("task_id") or "")
            if not task_id:
                raise RuntimeError(f"Aliyun Bailian create video missing task_id: {data!r}")
            return task_id

    async def get_video_task(
        self,
        *,
        cfg: ProviderConfig,
        task_id: str,
        timeout_s: float,
    ) -> dict[str, Any]:
        try:
            import httpx
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("httpx is required for video generation tasks") from e

        base = _resolve_api_base(cfg.base_url, self._base_url)
        headers = {
            "Authorization": f"Bearer {cfg.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=timeout_s) as client:
            rr = await client.get(f"{base}/tasks/{task_id}", headers=headers)
            rr.raise_for_status()
            return rr.json()
