"""阿里百炼 DashScope 视频生成 API（异步任务模式）。

调用流程：
1. POST 创建视频任务 → 获取 task_id
2. 轮询 GET 查询任务状态 → SUCCEEDED / FAILED
"""

from __future__ import annotations

from typing import Any

from app.core.integrations.aliyun_bailian.video_payload import build_create_task_body
from app.core.contracts.provider import ProviderConfig
from app.core.contracts.video_generation import VideoGenerationInput


class AliyunBailianVideoApiAdapter:
    """阿里百炼视频任务 HTTP：创建与查询。"""

    async def create_video_task(
        self,
        *,
        cfg: ProviderConfig,
        input_: VideoGenerationInput,
        timeout_s: float,
    ) -> str:
        try:
            import httpx
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("httpx is required for video generation tasks") from e

        base_url = (
            cfg.base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ).rstrip("/")
        headers = {
            "Authorization": f"Bearer {cfg.api_key}",
            "Content-Type": "application/json",
        }
        body = build_create_task_body(input_)

        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.post(f"{base_url}/videos/tasks", headers=headers, json=body)
            r.raise_for_status()
            data: dict[str, Any] = r.json()
            task_id = str(data.get("output").get("task_id") or data.get("task_id") or "")
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

        base_url = (
            cfg.base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ).rstrip("/")
        headers = {
            "Authorization": f"Bearer {cfg.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=timeout_s) as client:
            rr = await client.get(f"{base_url}/videos/tasks/{task_id}", headers=headers)
            rr.raise_for_status()
            return rr.json()
