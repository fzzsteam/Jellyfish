"""阿里百炼 (DashScope) 视频生成适配器（原生 API）。

使用 DashScope 视频合成原生 API（异步任务模式），
完整支持 HappyHorse-1.0-t2v / HappyHorse-1.0-i2v 等系列模型。

API 模式：
1. 提交视频生成任务 → 获得 task_id
2. 轮询任务状态 → 等待完成
3. 获取结果 URL

支持的模型与输入模式:
- t2v (Text-to-Video): happyhorse-1.0-t2v — 仅需 prompt 文本
- i2v (Image-to-Video): happyhorse-1.0-i2v — 需要 prompt + media（首帧图）

官方 t2v 参考示例:
```bash
curl --location 'https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis' \
    -H 'X-DashScope-Async: enable' \
    -H "Authorization: Bearer $DASHSCOPE_API_KEY" \
    -H 'Content-Type: application/json' \
    -d '{
        "model": "happyhorse-1.0-t2v",
        "input": {
            "prompt": "一座由硬纸板和瓶盖搭建的微型城市..."
        },
        "parameters": {
            "resolution": "720P",
            "ratio": "16:9",
            "duration": 5
        }
    }'
```

官方 i2v 参考示例:
```bash
curl --location 'https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis' \
    -H 'X-DashScope-Async: enable' \
    -H "Authorization: Bearer $DASHSCOPE_API_KEY" \
    -H 'Content-Type: application/json' \
    -d '{
        "model": "happyhorse-1.0-i2v",
        "input": {
            "prompt": "一只猫在草地上奔跑",
            "media": [
                {"type": "first_frame", "url": "https://cdn.example.com/image.png"}
            ]
        },
        "parameters": {
            "resolution": "720P",
            "duration": 5
        }
    }'
```

关键点：
- 端点: /api/v1/services/aigc/video-generation/video-synthesis
- 必须请求头: X-DashScope-Async: enable
- t2v 参数: resolution (720P/480P), ratio (16:9/9:16/1:1), duration (2/3/5/10)
- i2v 额外参数: input.media[] = [{type: "first_frame", url: "..."}]
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.core.contracts.provider import ProviderConfig
from app.core.contracts.video_generation import (
    VideoGenerationInput,
    VideoGenerationResult,
)

logger = logging.getLogger(__name__)

#: DashScope 视频合成提交端点
VIDEO_SUBMIT_URL = (
    "https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis"
)

#: DashScope 任务查询端点
VIDEO_QUERY_URL_TEMPLATE = "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"

#: i2v 模型名称标识（用于自动切换请求体格式）
_I2V_MODEL_PREFIXES = ("happyhorse-1.0-i2v", "i2v")


class BailianVideoApiAdapter:
    """阿里百炼视频生成适配器（DashScope 原生异步任务模式）。

    支持:
    - HappyHorse-1.0-t2v (文本→视频)
    - HappyHorse-1.0-i2v (图片→视频)

    使用异步任务模式：提交 → 轮询 → 获取结果。

    Attributes:
        POLL_INTERVAL_S: 轮询间隔秒数（默认5秒）
        MAX_POLL_COUNT: 最大轮询次数（默认120次=10分钟）
    """

    #: 轮询间隔（秒）
    POLL_INTERVAL_S = 5.0

    #: 最大轮询次数（5s * 120 = 10 分钟超时）
    MAX_POLL_COUNT = 120

    def __init__(self, *, provider_config: ProviderConfig, timeout_s: float = 600.0):
        self._cfg = provider_config
        self._timeout = timeout_s
        self._headers = {
            "Authorization": f"Bearer {provider_config.api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }

    async def generate(self, input_: VideoGenerationInput) -> VideoGenerationResult:
        """提交视频生成任务并轮询获取结果。

        完整流程:
        1. POST 提交视频生成请求 → 获得 task_id
        2. GET 循环轮询 task_status 直到 SUCCEEDED/FAILED
        3. 解析响应提取 video_url 并返回
        """
        task_id = await self._submit_task(input_)
        logger.info("[BailianVideo] Task submitted: %s", task_id)
        result = await self._poll_until_complete(task_id)
        return result

    async def _submit_task(self, input_: VideoGenerationInput) -> str:
        """提交视频生成任务，返回 task_id。"""
        payload = self._build_payload(input_)

        model_name = input_.model or "happyhorse-1.0-t2v"
        is_i2v = self._is_i2v_model(model_name) or bool(
            input_.first_frame_base64
        )

        logger.info(
            "[BailianVideo] Submitting video: model=%s mode=%s prompt_len=%d "
            "duration=%s ratio=%s resolution=%s has_media=%s",
            model_name,
            "i2v" if is_i2v else "t2v",
            len(input_.prompt or ""),
            input_.seconds or "default",
            input_.ratio or "default",
            self._resolve_resolution(input_),
            is_i2v,
        )

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(VIDEO_SUBMIT_URL, json=payload, headers=self._headers)
            resp.raise_for_status()
            data = resp.json()

        output = data.get("output", {})
        task_id = output.get("task_id") or data.get("task_id") or ""
        if not task_id:
            logger.error("[BailianVideo] Failed to get task_id from response: %s", data)
            raise RuntimeError(f"Failed to submit video task: {data}")

        return task_id

    def _build_payload(self, input_: VideoGenerationInput) -> dict[str, Any]:
        """构建 DashScope 原生视频合成请求体（严格按官方示例格式）。

        根据模型类型自动选择请求体结构:

        t2v 模式 (happyhorse-1.0-t2v):
        {
            "model": "happyhorse-1.0-t2v",
            "input": { "prompt": "..." },
            "parameters": { "resolution": "720P", "ratio": "16:9", "duration": 5 }
        }

        i2v 模式 (happyhorse-1.0-i2v):
        {
            "model": "happyhorse-1.0-i2v",
            "input": {
                "prompt": "...",
                "media": [{"type": "first_frame", "url": "https://..."}]
            },
            "parameters": { "resolution": "720P", "duration": 5 }
        }

        注意: i2v 模式不支持 ratio 参数（由首帧图决定画面比例）。
        """
        # 构建 prompt 文本
        prompt_text = input_.prompt or ""

        # 构建 parameters
        parameters: dict[str, Any] = {
            "resolution": self._resolve_resolution(input_),
        }

        # 时长（秒）：支持 2, 3, 5, 10
        if input_.seconds is not None:
            valid_durations = [2, 3, 5, 10]
            duration = int(input_.seconds)
            if duration not in valid_durations:
                duration = min(valid_durations, key=lambda x: abs(x - duration))
                logger.warning(
                    "[BailianVideo] Duration %s not in %s, using closest value: %d",
                    input_.seconds,
                    valid_durations,
                    duration,
                )
            parameters["duration"] = duration

        # 判断是否为 i2v 模式
        model_name = input_.model or "happyhorse-1.0-t2v"
        is_i2v = self._is_i2v_model(model_name) or bool(
            input_.first_frame_base64
        )

        if is_i2v:
            # ====== i2v (Image-to-Video) 模式 ======
            payload_input: dict[str, Any] = {"prompt": prompt_text}

            # 构建 media 数组（i2v 必需字段）
            media_list: list[dict[str, str]] = []

            # 首帧图 → type="first_frame"
            if input_.first_frame_base64:
                media_list.append({
                    "type": "first_frame",
                    "url": self._ensure_url(input_.first_frame_base64),
                })

            # 尾帧图 → type="last_frame" (如果有)
            if input_.last_frame_base64:
                media_list.append({
                    "type": "last_frame",
                    "url": self._ensure_url(input_.last_frame_base64),
                })

            # 关键帧图 → type="key_frame" (如果有)
            if input_.key_frame_base64:
                media_list.append({
                    "type": "key_frame",
                    "url": self._ensure_url(input_.key_frame_base64),
                })

            if media_list:
                payload_input["media"] = media_list

            payload: dict[str, Any] = {
                "model": model_name,
                "input": payload_input,
                "parameters": parameters,
            }

        else:
            # ====== t2v (Text-to-Video) 模式 ======
            payload = {
                "model": model_name,
                "input": {"prompt": prompt_text},
                "parameters": {
                    **parameters,
                    "ratio": self._resolve_ratio(input_),
                },
            }

        return payload

    @staticmethod
    def _is_i2v_model(model_name: str | None) -> bool:
        """判断模型名称是否属于 i2v (Image-to-Video) 类型。"""
        if not model_name:
            return False
        name_lower = model_name.lower().strip()
        return any(name_lower.startswith(p) for p in _I2V_MODEL_PREFIXES)

    @staticmethod
    def _resolve_resolution(input_: VideoGenerationInput) -> str:
        """解析视频分辨率为 DashScope 支持的格式。

        支持: "480P" (854x480), "720P" (1280x720)。默认 720P。
        """
        size_val = getattr(input_, "size", None)
        if size_val:
            size_str = str(size_val).upper()
            if "480" in size_str or "SD" in size_str:
                return "480P"
        return "720P"

    @staticmethod
    def _resolve_ratio(input_: VideoGenerationInput) -> str:
        """解析画面比例为 DashScope 支持的格式。

        支持: "16:9", "9:16", "1:1"。默认 16:9。
        （仅 t2v 模式使用；i2v 由首帧图决定比例）
        """
        valid_ratios = ["16:9", "9:16", "1:1"]
        if input_.ratio and input_.ratio in valid_ratios:
            return input_.ratio
        return "16:9"

    @staticmethod
    def _ensure_url(value: str) -> str:
        """确保值是可用的 URL（data URI 或 HTTP URL）。"""
        if value.startswith(("http://", "https://", "data:")):
            return value
        return f"data:image/png;base64,{value}"

    async def _poll_until_complete(self, task_id: str) -> VideoGenerationResult:
        """轮询任务状态直到完成或超时。"""
        query_url = VIDEO_QUERY_URL_TEMPLATE.format(task_id=task_id)

        for i in range(self.MAX_POLL_COUNT):
            await asyncio.sleep(self.POLL_INTERVAL_S)

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(query_url, headers=self._headers)
                resp.raise_for_status()
                data = resp.json()

            output = data.get("output", {})
            task_status = output.get("task_status", "")

            logger.debug(
                "[BailianVideo] Poll #%d task=%s status=%s progress=%s%%",
                i + 1,
                task_id,
                task_status,
                output.get("task_progress", "N/A"),
            )

            if task_status == "SUCCEEDED":
                return self._parse_success_response(data, task_id)
            elif task_status == "FAILED":
                code = output.get("code", "")
                message = output.get("message", "") or output.get("error", {})
                error_msg = f"[{code}] {message}" if code else str(message)
                raise RuntimeError(f"Video generation failed: {error_msg}")
            elif task_status in ("RUNNING", "PENDING", "QUEUED"):
                continue
            else:
                logger.warning("[BailianVideo] Unknown status: %s", task_status)

        raise TimeoutError(
            f"Video generation timed out after "
            f"{self.MAX_POLL_COUNT * self.POLL_INTERVAL_S}s"
        )

    def _parse_success_response(self, data: dict, task_id: str) -> VideoGenerationResult:
        """解析成功响应，提取 video_url。"""
        output = data.get("output", {})
        results = output.get("results", [])
        video_url: str = ""

        if isinstance(results, list):
            for r in results:
                url = r.get("video_url") or r.get("url") or ""
                if url:
                    video_url = url
                    break

        if not video_url:
            video_url = output.get("video_url") or ""

        if not video_url:
            video_url = VIDEO_QUERY_URL_TEMPLATE.format(task_id=task_id)
            logger.warning(
                "[BailianVideo] No video URL found, returning query URL as fallback"
            )

        logger.info(
            "[BailianVideo] Task completed: %s, url: %s",
            task_id,
            video_url[:80],
        )

        return VideoGenerationResult(
            url=video_url or None,
            provider_task_id=task_id,
            provider="aliyun_bailian",
            status="completed",
        )  # type: ignore[call-arg]
