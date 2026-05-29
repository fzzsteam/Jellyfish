"""阿里百炼 (DashScope) 视频生成适配器（原生 API）。

使用 DashScope 视频合成原生 API（异步任务模式），
完整支持 HappyHorse-1.0-t2v 等系列模型。

API 模式：
1. 提交视频生成任务 → 获得 task_id
2. 轮询任务状态 → 等待完成
3. 获取结果 URL

官方参考：
- https://help.aliyun.com/zh/model-studio/getting-started/models

HappyHorse-1.0-t2v 官方 API 示例：
```bash
curl --location 'https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis' \\
    -H 'X-DashScope-Async: enable' \\
    -H "Authorization: Bearer $DASHSCOPE_API_KEY" \\
    -H 'Content-Type: application/json' \\
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

关键点：
- 端点: /api/v1/services/aigc/video-generation/video-synthesis (注意是 video-generation 非 text2video!)
- 必须请求头: X-DashScope-Async: enable (标识异步模式)
- 参数: resolution (720P/480P), ratio (16:9/9:16/1:1), duration (2-10秒)
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

#: DashScope 视频合成提交端点（官方文档确认的端点路径）
VIDEO_SUBMIT_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis"

#: DashScope 任务查询端点
VIDEO_QUERY_URL_TEMPLATE = "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"


class BailianVideoApiAdapter:
    """阿里百炼视频生成适配器（DashScope 原生异步任务模式）。

    支持 HappyHorse-1.0-t2v 及其他 DashScope 视频生成模型。
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
        # 必须包含 X-DashScope-Async: enable 头，否则服务端不会按异步模式处理
        self._headers = {
            "Authorization": f"Bearer {provider_config.api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",  # 关键：启用异步任务模式
        }

    async def generate(self, input_: VideoGenerationInput) -> VideoGenerationResult:
        """提交视频生成任务并轮询获取结果。

        完整流程:
        1. POST 提交视频生成请求 → 获得 task_id
        2. GET 循环轮询 task_status 直到 SUCCEEDED/FAILED
        3. 解析响应提取 video_url 并返回
        """
        # 1. 提交任务
        task_id = await self._submit_task(input_)
        logger.info("[BailianVideo] Task submitted: %s", task_id)

        # 2. 轮询等待完成
        result = await self._poll_until_complete(task_id)

        return result

    async def _submit_task(self, input_: VideoGenerationInput) -> str:
        """提交视频生成任务，返回 task_id。

        Args:
            input_: 视频生成输入参数（含 prompt、duration、ratio 等）

        Returns:
            str: 任务 ID，用于后续轮询查询

        Raises:
            RuntimeError: 当无法从响应中解析出 task_id 时抛出
        """
        payload = self._build_payload(input_)

        logger.info(
            "[BailianVideo] Submitting video: model=%s prompt_len=%d duration=%s ratio=%s resolution=%s",
            input_.model or "happyhorse-1.0-t2v",
            len(input_.prompt or ""),
            input_.seconds or "default",
            input_.ratio or "default",
            self._resolve_resolution(input_),
        )

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(VIDEO_SUBMIT_URL, json=payload, headers=self._headers)
            resp.raise_for_status()
            data = resp.json()

        # 提取 task_id（可能在 output.task_id 或顶层 task_id）
        output = data.get("output", {})
        task_id = output.get("task_id") or data.get("task_id") or ""
        if not task_id:
            logger.error("[BailianVideo] Failed to get task_id from response: %s", data)
            raise RuntimeError(f"Failed to submit video task: {data}")

        return task_id

    def _build_payload(self, input_: VideoGenerationInput) -> dict[str, Any]:
        """构建 DashScope 原生视频合成请求体（严格按官方示例格式）。

        官方请求体结构:
        {
            "model": "happyhorse-1.0-t2v",
            "input": {
                "prompt": "..."  // 文本描述（字符串，非数组）
            },
            "parameters": {
                "resolution": "720P",  // 分辨率: 480P 或 720P
                "ratio": "16:9",       // 比例: 16:9 / 9:16 / 1:1
                "duration": 5          // 时长: 2/3/5/10 秒
            }
        }
        """
        # 构建 prompt 文本
        prompt_text = input_.prompt or ""

        # 可选：如果有首帧/尾帧/关键帧，追加提示信息到 prompt
        ref_info_parts: list[str] = []
        if input_.first_frame_base64:
            ref_info_parts.append("首帧已提供")
        if input_.last_frame_base64:
            ref_info_parts.append("尾帧已提供")
        if input_.key_frame_base64:
            ref_info_parts.append("关键帧已提供")
        if ref_info_parts:
            prompt_text += f"\n(参考信息: {'; '.join(ref_info_parts)})"

        # 构建 parameters（严格按照官方示例的字段名）
        parameters: dict[str, Any] = {
            # 分辨率：480P (854×480) 或 720P (1280×720)
            "resolution": self._resolve_resolution(input_),
            # 画面比例
            "ratio": self._resolve_ratio(input_),
        }

        # 时长（秒）：支持 2, 3, 5, 10
        if input_.seconds is not None:
            # 确保值在合法范围内
            valid_durations = [2, 3, 5, 10]
            duration = int(input_.seconds)
            if duration not in valid_durations:
                # 取最接近的合法值
                duration = min(valid_durations, key=lambda x: abs(x - duration))
                logger.warning(
                    "[BailianVideo] Duration %s not in %s, using closest value: %d",
                    input_.seconds, valid_durations, duration,
                )
            parameters["duration"] = duration

        payload: dict[str, Any] = {
            # 模型名称（必须与官方一致）
            "model": input_.model or "happyhorse-1.0-t2v",
            # 输入：使用 prompt 字段（字符串格式，非 messages 数组）
            "input": {
                "prompt": prompt_text,
            },
            # 参数：resolution + ratio + duration
            "parameters": parameters,
        }

        # 可选：如果提供了首帧图 URL，作为参考传入
        if input_.first_frame_base64:
            payload["input"]["ref_image_first_frame_url"] = self._ensure_data_url(
                input_.first_frame_base64
            )

        return payload

    @staticmethod
    def _resolve_resolution(input_: VideoGenerationInput) -> str:
        """解析视频分辨率为 DashScope 支持的格式。

        HappyHorse-1.0-t2v 支持的分辨率:
        - "480P" (854×480, 标准清晰度)
        - "720P" (1280×720, 高清)

        默认返回 "720P" 以获得更好的画质。
        """
        # 尝试从输入参数获取分辨率偏好（使用 getattr 安全访问）
        size_val = getattr(input_, "size", None)
        if size_val:
            size_str = str(size_val).upper()
            if "480" in size_str or "SD" in size_str:
                return "480P"

        # 默认使用 720P 高清
        return "720P"

    @staticmethod
    def _resolve_ratio(input_: VideoGenerationInput) -> str:
        """解析画面比例为 DashScope 支持的格式。

        支持的比例:
        - "16:9" (横屏，默认，适合电影感)
        - "9:16" (竖屏，适合手机短视频)
        - "1:1" (方形，适合社交媒体)
        """
        valid_ratios = ["16:9", "9:16", "1:1"]
        if input_.ratio and input_.ratio in valid_ratios:
            return input_.ratio

        # 默认 16:9 横屏
        return "16:9"

    @staticmethod
    def _ensure_data_url(value: str) -> str:
        """确保值是 data URI 或 HTTP URL。"""
        if value.startswith(("http://", "https://", "data:")):
            return value
        # 假设是纯 base64 编码，补充前缀
        return f"data:image/png;base64,{value}"

    async def _poll_until_complete(self, task_id: str) -> VideoGenerationResult:
        """轮询任务状态直到完成或超时。

        轮询逻辑:
        - 每 5 秒查询一次任务状态
        - 最多查询 120 次（总时长 10 分钟）
        - 成功时返回 VideoGenerationResult
        - 失败时抛 RuntimeError
        - 超时时抛 TimeoutError

        可能的任务状态:
        - PENDING: 排队等待
        - RUNNING: 正在处理
        - SUCCEEDED: 完成 ✅
        - FAILED: 失败 ❌
        """
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
        """解析成功响应，提取 video_url。

        成功响应示例:
        {
            "output": {
                "task_status": "SUCCEEDED",
                "task_progress": 100,
                "results": [
                    {"video_url": "https://xxx.mp4"}
                ]
            },
            "request_id": "xxx",
            "code": "200"
        }
        """
        output = data.get("output", {})
        results = output.get("results", [])
        video_url: str = ""

        # 从 results 数组中提取第一个 video_url
        if isinstance(results, list):
            for r in results:
                url = r.get("video_url") or r.get("url") or ""
                if url:
                    video_url = url
                    break

        # 尝试从顶层的 video_url 字段直接提取
        if not video_url:
            video_url = output.get("video_url") or ""

        if not video_url:
            # 返回查询地址作为 fallback（理论上不应走到这里）
            video_url = VIDEO_QUERY_URL_TEMPLATE.format(task_id=task_id)
            logger.warning(
                "[BailianVideo] No video URL found, returning query URL as fallback"
            )

        logger.info("[BailianVideo] Task completed: %s, url: %s", task_id, video_url[:80])

        return VideoGenerationResult(
            url=video_url or None,
            provider_task_id=task_id,
            provider="aliyun_bailian",
            status="completed",
        )  # type: ignore[call-arg]
