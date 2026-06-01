"""阿里百炼 (DashScope) 视频生成适配器（原生 API）。

使用 DashScope 视频合成原生 API（异步任务模式），
完整支持三种视频生成模型。

API 模式：
1. 提交视频生成任务 → 获得 task_id
2. 轮询任务状态 → 等待完成
3. 获取结果 URL

支持的模型与输入模式:

t2v (Text-to-Video): happyhorse-1.0-t2v — 仅需 prompt 文本
  官方示例:
    curl ... -d '{"model":"happyhorse-1.0-t2v","input":{"prompt":"..."},"parameters":{"resolution":"720P","ratio":"16:9","duration":5}}'

i2v (Image-to-Video): happyhorse-1.0-i2v — prompt + 首帧图(可选尾帧/关键帧)
  官方示例:
    curl ... -d '{"model":"happyhorse-1.0-i2v",
      "input":{"prompt":"...","media":[{"type":"first_frame","url":"..."}]},
      "parameters":{"resolution":"720P","duration":5}}'

r2v (Reference-to-Video): happyhorse-1.0-r2v — prompt + 多张参考图 + ratio
  官方示例:
    curl ... -d '{"model":"happyhorse-1.0-r2v",
      "input":{"prompt":"...","media":[
        {"type":"reference_image","url":"https://..."},
        {"type":"reference_image","url":"https://..."},
        {"type":"reference_image","url":"https://..."}
      ]},
      "parameters":{"resolution":"720P","ratio":"16:9","duration":5}}'

关键差异:
- t2v: 无 media 字段，有 ratio
- i2v: media type = first_frame / last_frame / key_frame，无 ratio
- r2v: media type = reference_image（可多张），有 ratio
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

#: i2v 模型名称标识
_I2V_MODEL_PREFIXES = ("happyhorse-1.0-i2v", "i2v")

#: r2v 模型名称标识
_R2V_MODEL_PREFIXES = ("happyhorse-1.0-r2v", "r2v")


class BailianVideoApiAdapter:
    """阿里百炼视频生成适配器（DashScope 原生异步任务模式）。

    支持:
    - HappyHorse-1.0-t2v  (文本→视频)
    - HappyHorse-1.0-i2v  (首帧图→视频)
    - HappyHorse-1.0-r2v  (参考图→视频)

    Attributes:
        POLL_INTERVAL_S: 轮询间隔秒数（默认5秒）
        MAX_POLL_COUNT: 最大轮询次数（默认120次=10分钟）
    """

    POLL_INTERVAL_S = 5.0
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
        """提交视频生成任务并轮询获取结果。"""
        task_id = await self._submit_task(input_)
        logger.info("[BailianVideo] Task submitted: %s", task_id)
        result = await self._poll_until_complete(task_id)
        return result

    async def _submit_task(self, input_: VideoGenerationInput) -> str:
        """提交视频生成任务，返回 task_id。"""
        payload = self._build_payload(input_)

        model_name = input_.model or "happyhorse-1.0-t2v"
        mode = self._detect_mode(model_name, input_)

        logger.info(
            "[BailianVideo] Submitting video: model=%s mode=%s prompt_len=%d "
            "duration=%s ratio=%s resolution=%s has_media=%s",
            model_name,
            mode,
            len(input_.prompt or ""),
            input_.seconds or "default",
            input_.ratio or "default",
            self._resolve_resolution(input_),
            bool(mode != "t2v"),
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

    @staticmethod
    def _detect_mode(model_name: str, input_: VideoGenerationInput) -> str:
        """检测当前请求应使用的视频生成模式。

        返回值: 't2v' | 'i2v' | 'r2v'
        """
        name_lower = (model_name or "").lower().strip()
        has_media_input = any(
            getattr(input_, attr, None)
            for attr in ("first_frame_base64", "last_frame_base64", "key_frame_base64")
        )

        if any(name_lower.startswith(p) for p in _R2V_MODEL_PREFIXES):
            return "r2v"
        if any(name_lower.startswith(p) for p in _I2V_MODEL_PREFIXES):
            return "i2v"
        if has_media_input:
            return "i2v"
        return "t2v"

    def _build_payload(self, input_: VideoGenerationInput) -> dict[str, Any]:
        """构建 DashScope 原生视频合成请求体。

        三种模式的请求体结构:

        t2v (纯文本):
          {"model": "...", "input": {"prompt": "..."}, "parameters": {"resolution":"720P","ratio":"16:9","duration":5}}

        i2v (首帧图→视频):
          {"model": "...", "input": {"prompt":"...", "media":[{"type":"first_frame","url":"..."}]}, "parameters":{"resolution":"720P","duration":5}}

        r2v (参考图→视频):
          {"model": "...", "input": {"prompt":"...", "media":[{"type":"reference_image","url":"..."}]}, "parameters":{"resolution":"720P","ratio":"16:9","duration":5}}
        """
        prompt_text = input_.prompt or ""

        parameters: dict[str, Any] = {
            "resolution": self._resolve_resolution(input_),
        }

        # 时长（秒）
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

        model_name = input_.model or "happyhorse-1.0-t2v"
        mode = self._detect_mode(model_name, input_)

        if mode == "r2v":
            # ====== r2v (Reference-to-Video) ======
            payload_input: dict[str, Any] = {"prompt": prompt_text}

            media_list: list[dict[str, str]] = []
            for img_field in ("first_frame_base64", "last_frame_base64", "key_frame_base64"):
                val = getattr(input_, img_field, None)
                if val:
                    media_list.append({
                        "type": "reference_image",   # r2v 统一用 reference_image
                        "url": self._ensure_url(val),
                    })

            if media_list:
                payload_input["media"] = media_list

            payload: dict[str, Any] = {
                "model": model_name,
                "input": payload_input,
                "parameters": {
                    **parameters,
                    "ratio": self._resolve_ratio(input_),     # r2v 支持 ratio
                },
            }

        elif mode == "i2v":
            # ====== i2v (Image-to-Video) ======
            payload_input: dict[str, Any] = {"prompt": prompt_text}
            media_list: list[dict[str, str]] = []

            if input_.first_frame_base64:
                media_list.append({
                    "type": "first_frame",
                    "url": self._ensure_url(input_.first_frame_base64),
                })
            if input_.last_frame_base64:
                media_list.append({
                    "type": "last_frame",
                    "url": self._ensure_url(input_.last_frame_base64),
                })
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
            # ====== t2v (Text-to-Video) ======
            payload: dict[str, Any] = {
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
        """判断模型是否为 i2v 或 r2v 类型（两者都需要 input.media）。"""
        if not model_name:
            return False
        name_lower = model_name.lower().strip()
        return any(
            name_lower.startswith(p)
            for p in _I2V_MODEL_PREFIXES + _R2V_MODEL_PREFIXES
        )

    @staticmethod
    def _resolve_resolution(input_: VideoGenerationInput) -> str:
        """解析视频分辨率。支持 480P/720P，默认 720P。"""
        size_val = getattr(input_, "size", None)
        if size_val:
            size_str = str(size_val).upper()
            if "480" in size_str or "SD" in size_str:
                return "480P"
        return "720P"

    @staticmethod
    def _resolve_ratio(input_: VideoGenerationInput) -> str:
        """解析画面比例。支持 16:9/9:16/1:1，默认 16:9。"""
        valid_ratios = ["16:9", "9:16", "1:1"]
        if input_.ratio and input_.ratio in valid_ratios:
            return input_.ratio
        return "16:9"

    @staticmethod
    def _ensure_url(value: str) -> str:
        """确保值是可用 URL（data URI 或 HTTP URL）。"""
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

            if task_status == "SUCCEEDED":
                return self._parse_success_response(data, task_id)
            elif task_status == "FAILED":
                code = output.get("code", "")
                message = output.get("message", "") or output.get("error", {})
                error_msg = f"[{code}] {message}" if code else str(message)
                raise RuntimeError(f"Video generation failed: {error_msg}")
            elif task_status in ("RUNNING", "POLIDING", "QUEUED"):
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
