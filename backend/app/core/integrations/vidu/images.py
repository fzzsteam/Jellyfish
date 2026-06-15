"""Vidu 图片生成适配器（reference2image 异步轮询模式）。

API 流程：
1. POST /ent/v2/reference2image  → 创建任务，返回 task_id
2. GET  /ent/v2/tasks/{task_id}/creations  → 轮询直到 state == "success" | "failed"

鉴权：Authorization: Token {api_key}
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.core.contracts.image_generation import (
    ImageGenerationInput,
    ImageGenerationResult,
    ImageItem,
)
from app.core.contracts.provider import ProviderConfig
from app.core.integrations.vidu.image_capabilities import resolve_vidu_image_capability

logger = logging.getLogger(__name__)

# 轮询配置
_POLL_INTERVAL_S = 3.0
_TERMINAL_STATES = {"success", "failed"}


class ViduImageApiAdapter:
    """Vidu reference2image 异步轮询 HTTP 适配器；无状态，可单测替换。"""

    DEFAULT_MODEL = "viduq2"
    DEFAULT_BASE_URL = "https://api.vidu.cn"

    async def generate(
        self,
        *,
        cfg: ProviderConfig,
        inp: ImageGenerationInput,
        timeout_s: float = 120.0,
    ) -> ImageGenerationResult:
        """创建任务并轮询至完成，返回统一结果。"""
        try:
            import httpx
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("httpx is required for Vidu image generation") from e

        base_url = (cfg.base_url or self.DEFAULT_BASE_URL).rstrip("/")
        headers = {
            "Authorization": f"Token {cfg.api_key}",
            "Content-Type": "application/json",
        }

        body = self._build_request_body(inp)
        model = inp.model or self.DEFAULT_MODEL

        logger.info(
            "[ViduImage] Creating task: model=%s aspect_ratio=%s resolution=%s",
            model,
            body.get("aspect_ratio"),
            body.get("resolution"),
        )

        async with httpx.AsyncClient(timeout=timeout_s) as client:
            # 1. 创建任务
            create_url = f"{base_url}/ent/v2/reference2image"
            t0 = time.perf_counter()
            r = await client.post(create_url, headers=headers, json=body)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)

            logger.info(
                "[ViduImage] Create response: status=%d elapsed_ms=%d",
                r.status_code,
                elapsed_ms,
            )

            if r.status_code != 200:
                raise RuntimeError(
                    f"[ViduImage] Create task failed: status={r.status_code} body={r.text[:500]}"
                )

            create_data: dict[str, Any] = r.json()
            task_id: str = create_data.get("task_id", "")
            if not task_id:
                raise RuntimeError(
                    f"[ViduImage] Create response missing task_id: {create_data!r}"
                )

            logger.info("[ViduImage] Task created: task_id=%s state=%s", task_id, create_data.get("state"))

            # 2. 轮询任务结果
            return await self._poll_until_done(
                client=client,
                base_url=base_url,
                headers=headers,
                task_id=task_id,
                deadline=time.perf_counter() + timeout_s,
            )

    async def _poll_until_done(
        self,
        *,
        client: Any,
        base_url: str,
        headers: dict[str, str],
        task_id: str,
        deadline: float,
    ) -> ImageGenerationResult:
        """轮询 GET /ent/v2/tasks/{task_id}/creations 直至终态。"""
        poll_url = f"{base_url}/ent/v2/tasks/{task_id}/creations"

        while True:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                raise RuntimeError(
                    f"[ViduImage] Polling timeout for task_id={task_id}"
                )

            await asyncio.sleep(_POLL_INTERVAL_S)

            r = await client.get(poll_url, headers=headers, timeout=30.0)
            if r.status_code != 200:
                raise RuntimeError(
                    f"[ViduImage] Poll failed: status={r.status_code} body={r.text[:500]}"
                )

            data: dict[str, Any] = r.json()
            state: str = (data.get("state") or "").lower()

            logger.info("[ViduImage] Poll: task_id=%s state=%s", task_id, state)

            if state not in _TERMINAL_STATES:
                continue

            if state == "failed":
                err_msg = data.get("err_msg") or data.get("message") or "unknown error"
                raise RuntimeError(
                    f"[ViduImage] Task failed: task_id={task_id} err={err_msg}"
                )

            # state == "success"
            return self._parse_poll_response(data, task_id)

    def _build_request_body(self, inp: ImageGenerationInput) -> dict[str, Any]:
        """将 ImageGenerationInput 映射为 Vidu reference2image 请求体。"""
        model = inp.model or self.DEFAULT_MODEL
        cap = resolve_vidu_image_capability(model)

        # 画幅比例：优先 target_ratio，其次从 supported_ratios 取默认
        aspect_ratio: str = inp.target_ratio or "16:9"

        # 分辨率档位：优先从 size 直接透传（如 "2K"/"1080P"），
        # 其次由 resolution_profile + ratio 从 capability 推导
        vidu_resolution = self._resolve_resolution(inp, cap, aspect_ratio)

        # 参考图列表（取 image_url，Vidu 不支持 file_id 方式）
        images: list[str] = [
            ref.image_url
            for ref in inp.images
            if ref.image_url
        ]

        body: dict[str, Any] = {
            "model": model,
            "prompt": inp.prompt,
            "aspect_ratio": aspect_ratio,
            "resolution": vidu_resolution,
            "payload": "",
        }

        if images:
            body["images"] = images

        if inp.seed is not None:
            body["seed"] = int(inp.seed)

        return body

    @staticmethod
    def _resolve_resolution(
        inp: ImageGenerationInput,
        cap: Any,
        aspect_ratio: str,
    ) -> str:
        """解析最终 Vidu resolution 字符串（1080P / 2K / 4K）。

        优先级：
        1. inp.size 直接透传（调用方已指定 Vidu 分辨率关键字）
        2. ratio_size_profiles[aspect_ratio][resolution_profile]
        3. 默认 "1080P"
        """
        vidu_resolutions = {"1080P", "2K", "4K"}

        if inp.size and inp.size.upper() in vidu_resolutions:
            return inp.size.upper()

        profile = inp.resolution_profile or cap.default_resolution_profile or "standard"
        if cap.ratio_size_profiles:
            profiles_for_ratio = cap.ratio_size_profiles.get(aspect_ratio, {})
            resolution = profiles_for_ratio.get(profile)
            if resolution:
                return resolution

        return "1080P"

    @staticmethod
    def _parse_poll_response(data: dict[str, Any], task_id: str) -> ImageGenerationResult:
        """从轮询响应中提取图片结果。

        Vidu 轮询响应结构::

            {
              "task_id": "...",
              "state": "success",
              "creations": [
                {"id": "...", "url": "https://...", "cover_url": "https://..."}
              ]
            }
        """
        creations: list[dict[str, Any]] = data.get("creations") or []
        images: list[ImageItem] = []

        for item in creations:
            if not isinstance(item, dict):
                continue
            url = item.get("url") or item.get("image_url") or ""
            if url:
                images.append(ImageItem(url=url))
                logger.info("[ViduImage] Found image: url=%s", url[:80])

        if not images:
            raise RuntimeError(
                f"[ViduImage] Task succeeded but no image URLs found: task_id={task_id} data={data!r}"
            )

        logger.info("[ViduImage] Done: task_id=%s images=%d", task_id, len(images))

        return ImageGenerationResult(
            images=images,
            provider="vidu",  # type: ignore[arg-type]
            provider_task_id=task_id,
            status="completed",
        )
