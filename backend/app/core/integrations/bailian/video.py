"""阿里百炼 (DashScope) 视频生成适配器（原生 API）。

使用 DashScope 视频合成原生 API（异步任务模式），
完整支持四种视频生成模型。

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
        {"type":"reference_image","url":"https://..."}
      ]},
      "parameters":{"resolution":"720P","ratio":"16:9","duration":5}}'

video-edit (视频编辑): happyhorse-1.0-video-edit — prompt + 源视频 + 可选参考图
  官方示例:
    curl ... -d '{"model":"happyhorse-1.0-video-edit",
      "input":{"prompt":"...","media":[
        {"type":"video","url":"https://...mp4"},
        {"type":"reference_image","url":"https://..."}
      ]},
      "parameters":{"resolution":"720P"}}'

关键差异:
- t2v:    无 media 字段，有 ratio, duration
- i2v:    media type = first_frame / last_frame / key_frame，无 ratio
- r2v:    media type = reference_image（可多张），有 ratio, duration
- edit:   media type = video(必需) + reference_image(可选)，仅 resolution
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

#: video-edit 模型名称标识
_VIDEO_EDIT_PREFIXES = ("happyhorse-1.0-video-edit", "video-edit")

HAPPYHORSE_MIN_DURATION_SECONDS = 3
HAPPYHORSE_MAX_DURATION_SECONDS = 15


class BailianVideoApiAdapter:
    """阿里百炼视频生成适配器（DashScope 原生异步任务模式）。

    支持:
    - HappyHorse-1.0-t2v       (文本→视频)
    - HappyHorse-1.0-i2v       (首帧图→视频)
    - HappyHorse-1.0-r2v       (参考图→视频)
    - HappyHorse-1.0-video-edit (视频编辑)

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
            "duration=%s ratio=%s resolution=%s has_media=%s has_video=%s",
            model_name,
            mode,
            len(input_.prompt or ""),
            input_.seconds or "default",
            input_.ratio or "default",
            self._resolve_resolution(input_),
            bool(mode != "t2v"),
            bool(mode == "edit" and bool(input_.source_video_base64)),
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

        返回值: 't2v' | 'i2v' | 'r2v' | 'edit'
        """
        name_lower = (model_name or "").lower().strip()

        # 优先按模型名判断
        if any(name_lower.startswith(p) for p in _VIDEO_EDIT_PREFIXES):
            return "edit"
        if any(name_lower.startswith(p) for p in _R2V_MODEL_PREFIXES):
            return "r2v"
        if any(name_lower.startswith(p) for p in _I2V_MODEL_PREFIXES):
            return "i2v"

        # 无明确模型名时，根据输入内容推断
        if getattr(input_, "source_video_base64", None):
            return "edit"

        has_img_input = any(
            getattr(input_, attr, None)
            for attr in ("first_frame_base64", "last_frame_base64", "key_frame_base64")
        )
        if has_img_input:
            return "i2v"

        return "t2v"

    def _build_payload(self, input_: VideoGenerationInput) -> dict[str, Any]:
        """构建 DashScope 原生视频合成请求体。

        四种模式的请求体结构:

        t2v (纯文本):
          {"model":"...", "input":{"prompt":"..."}, "parameters":{"resolution":"720P","ratio":"16:9","duration":5}}

        i2v (首帧图→视频):
          {"model":"...", "input":{"prompt":"...", "media":[{"type":"first_frame","url":"..."}]}, "parameters":{"resolution":"720P","duration":5}}

        r2v (参考图→视频):
          {"model":"...", "input":{"prompt":"...", "media":[{"type":"reference_image","url":"..."}]}, "parameters":{"resolution":"720P","ratio":"16:9","duration":5}}

        edit (视频编辑):
          {"model":"...", "input":{"prompt":"...",
             "media":[
               {"type":"video","url":"https://...mp4"},
               {"type":"reference_image","url":"https://..."}
             ]},
           "parameters":{"resolution":"720P"}}
        """
        prompt_text = input_.prompt or ""

        parameters: dict[str, Any] = {
            "resolution": self._resolve_resolution(input_),
        }
        # watermark=False 可关闭百炼视频水印；None 表示未指定，不传参（沿用平台默认）
        if input_.watermark is not None:
            parameters["watermark"] = input_.watermark

        model_name = input_.model or "happyhorse-1.0-t2v"
        mode = self._detect_mode(model_name, input_)

        # ====== edit (视频编辑模式) ======
        if mode == "edit":
            payload_input: dict[str, Any] = {"prompt": prompt_text}
            media_list: list[dict[str, str]] = []

            # 必填：源视频 → type="video"
            src_video = getattr(input_, "source_video_base64", None)
            if src_video:
                media_list.append({
                    "type": "video",
                    "url": self._ensure_url(src_video),
                })

            # 可选：参考图 → type="reference_image"
            for img_field in ("first_frame_base64", "key_frame_base64"):
                val = getattr(input_, img_field, None)
                if val:
                    media_list.append({
                        "type": "reference_image",
                        "url": self._ensure_url(val),
                    })
                    break  # video-edit 只需要一张参考图即可

            if media_list:
                payload_input["media"] = media_list

            # video-edit 只传 resolution，不传 ratio 和 duration
            payload: dict[str, Any] = {
                "model": model_name,
                "input": payload_input,
                "parameters": parameters,
            }
            return payload

        # ====== r2v (Reference-to-Video) ======
        if mode == "r2v":
            payload_input = {"prompt": prompt_text}
            media_list = []
            seen_ref_urls: set[str] = set()

            def add_reference_image(value: str | None) -> None:
                """Append one r2v reference image while preserving order and removing duplicates."""
                if not value:
                    return
                url = self._ensure_url(value)
                if url in seen_ref_urls:
                    return
                seen_ref_urls.add(url)
                media_list.append({
                    "type": "reference_image",
                    "url": url,
                })

            for img_field in ("first_frame_base64", "last_frame_base64", "key_frame_base64"):
                add_reference_image(getattr(input_, img_field, None))
            for val in input_.reference_image_base64s:
                add_reference_image(val)

            if media_list:
                payload_input["media"] = media_list

            payload = {
                "model": model_name,
                "input": payload_input,
                "parameters": {
                    **parameters,
                    "ratio": self._resolve_ratio(input_),     # r2v 支持 ratio
                },
            }

            # r2v 支持 duration
            if input_.seconds is not None:
                payload["parameters"]["duration"] = self._resolve_duration(input_)

            return payload

        # ====== i2v (Image-to-Video) ======
        if mode == "i2v":
            payload_input = {"prompt": prompt_text}
            media_list = []

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

            payload = {
                "model": model_name,
                "input": payload_input,
                "parameters": parameters,
            }

            # i2v 支持 duration
            if input_.seconds is not None:
                payload["parameters"]["duration"] = self._resolve_duration(input_)

            return payload

        # ====== t2v (Text-to-Video) ======
        payload = {
            "model": model_name,
            "input": {"prompt": prompt_text},
            "parameters": {
                **parameters,
                "ratio": self._resolve_ratio(input_),
            },
        }

        # t2v 支持 duration
        if input_.seconds is not None:
            payload["parameters"]["duration"] = self._resolve_duration(input_)

        return payload

    @staticmethod
    def _resolve_duration(input_: VideoGenerationInput) -> int:
        """Resolve HappyHorse duration using the official 3-15 second integer range."""
        duration = int(round(input_.seconds or HAPPYHORSE_MIN_DURATION_SECONDS))
        return max(HAPPYHORSE_MIN_DURATION_SECONDS, min(HAPPYHORSE_MAX_DURATION_SECONDS, duration))

    @staticmethod
    def _is_i2v_model(model_name: str | None) -> bool:
        """判断模型是否为非 t2v 类型（i2v / r2v / edit 都需要 input.media）。"""
        if not model_name:
            return False
        name_lower = model_name.lower().strip()
        return any(
            name_lower.startswith(p)
            for p in _I2V_MODEL_PREFIXES + _R2V_MODEL_PREFIXES + _VIDEO_EDIT_PREFIXES
        )

    @staticmethod
    def _resolve_resolution(input_: VideoGenerationInput) -> str:
        """解析视频分辨率（百炼 resolution 参数）。

        Task 5c：业务层统一用 720p/1080p，百炼侧只支持 480P/720P。
        - 业务 resolution=720p → "720P"（大写，符合 DashScope API 规范）。
        - 业务 resolution=1080p → 百炼不支持，必须在调用前拒绝，否则会出现
          「按 1080p 收费却生成 720p」的计费与生成不一致。拒绝以 ValueError 抛出，
          交给上层转化为 HTTPException(400)。
        - 未指定 resolution（None，存量/非计费路径）→ 默认 720P，保持原行为。
        """
        # VideoGenerationInput 契约上只有 resolution 一个分辨率来源（无 size 字段）。
        business_resolution = input_.resolution
        if business_resolution:
            normalized = str(business_resolution).strip().lower()
            if normalized == "720p":
                return "720P"
            if normalized == "1080p":
                raise ValueError(
                    "Bailian video does not support 1080p resolution; supported: 480P/720P"
                )
            raise ValueError(f"Unsupported business resolution for bailian: {business_resolution}")
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
