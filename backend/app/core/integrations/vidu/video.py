"""Vidu video generation adapter.

The adapter maps the shared `VideoGenerationInput` contract to Vidu APIs:

1. POST `/ent/v2/reference2video`, `/ent/v2/text2video`, `/ent/v2/img2video`,
   `/ent/v2/start-end2video`, `/ent/v2/multiframe`, `/ent/v2/template`,
   or `/ent/v2/template-story` creates an async task.
2. GET `/ent/v2/tasks/{task_id}/creations` polls until success or failure.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from app.core.contracts.provider import ProviderConfig
from app.core.contracts.video_generation import VideoGenerationInput, VideoGenerationResult
from app.core.integrations.vidu.video_capabilities import resolve_vidu_video_capability

logger = logging.getLogger(__name__)

_POLL_INTERVAL_S = 3.0
_TERMINAL_STATES = {"success", "failed"}


class ViduVideoApiAdapter:
    """HTTP adapter for Vidu subject reference-to-video generation."""

    DEFAULT_MODEL = "viduq3"
    DEFAULT_BASE_URL = "https://api.vidu.cn"

    async def generate(
        self,
        *,
        cfg: ProviderConfig,
        inp: VideoGenerationInput,
        timeout_s: float = 600.0,
    ) -> VideoGenerationResult:
        """Create a Vidu video task and poll it to a normalized result."""
        base_url = (cfg.base_url or self.DEFAULT_BASE_URL).rstrip("/")
        headers = {
            "Authorization": f"Token {cfg.api_key}",
            "Content-Type": "application/json",
        }
        body = self._build_request_body(inp)
        create_url = f"{base_url}{self._resolve_create_path(body)}"

        logger.info(
            "[ViduVideo] Creating task: model=%s duration=%s ratio=%s subjects=%d images=%d url=%s",
            body.get("model"),
            body.get("duration"),
            body.get("aspect_ratio"),
            len(body.get("subjects") or []),
            len(body.get("images") or []),
            create_url,
        )

        async with httpx.AsyncClient(timeout=timeout_s) as client:
            t0 = time.perf_counter()
            try:
                response = await client.post(create_url, headers=headers, json=body)
            except Exception as exc:
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                raise RuntimeError(
                    f"[ViduVideo] HTTP request failed after {elapsed_ms}ms:"
                    f" {type(exc).__name__}: {exc or '(no message)'}"
                ) from exc
            elapsed_ms = int((time.perf_counter() - t0) * 1000)

            logger.info(
                "[ViduVideo] Create response: status=%d elapsed_ms=%d",
                response.status_code,
                elapsed_ms,
            )

            if response.status_code != 200:
                raise RuntimeError(
                    f"[ViduVideo] Create task failed: status={response.status_code} body={response.text[:500]}"
                )

            create_data: dict[str, Any] = response.json()
            task_id = str(create_data.get("task_id") or "")
            if not task_id:
                raise RuntimeError(
                    f"[ViduVideo] Create response missing task_id: {create_data!r}"
                )

            return await self._poll_until_done(
                client=client,
                base_url=base_url,
                headers=headers,
                task_id=task_id,
                deadline=time.perf_counter() + timeout_s,
            )

    def _build_request_body(self, inp: VideoGenerationInput) -> dict[str, Any]:
        """Build the Vidu request body from shared video input."""
        model = inp.model or self.DEFAULT_MODEL
        cap = resolve_vidu_video_capability(model)
        aspect_ratio = inp.ratio or cap.default_ratio or "3:4"
        resolution = self._resolve_resolution(inp, cap, aspect_ratio, model)
        duration = int(inp.seconds or 8)
        images = self._build_reference_images(inp)

        if self._uses_template_story_payload(model):
            if not images:
                raise ValueError("Vidu template-story video requires at least one reference image")
            return {
                "story": self._resolve_story_name(model),
                "images": images,
            }

        if self._uses_template_payload(model):
            if not images:
                raise ValueError("Vidu template video requires at least one reference image")
            body = {
                "template": self._resolve_template_name(model),
                "images": images,
                "prompt": inp.prompt or "",
            }
            if inp.seed is not None:
                body["seed"] = int(inp.seed)
            return body

        if self._uses_multiframe_payload(model):
            if len(images) < 2:
                raise ValueError("Vidu multiframe requires a start image and at least one key image")
            return {
                "model": model,
                "start_image": images[0],
                "image_settings": [
                    {
                        "prompt": inp.prompt or "",
                        "key_image": image,
                        "duration": duration,
                    }
                    for image in images[1:]
                ],
                # Task 5c：优先业务层 resolution（720p/1080p），保证计费与生成一致。
                "resolution": resolution,
            }

        if self._uses_text2video_payload(model, images):
            body: dict[str, Any] = {
                "model": model,
                "style": "general",
                "prompt": inp.prompt or "",
                "duration": duration,
                "aspect_ratio": aspect_ratio,
                "resolution": resolution,
                "movement_amplitude": "auto",
                "off_peak": False,
            }
            if inp.seed is not None:
                body["seed"] = int(inp.seed)
            return body

        if self._uses_start_end2video_payload(model, images):
            body = {
                "model": model,
                "images": images[:2],
                "prompt": inp.prompt or "",
                "duration": duration,
                "resolution": resolution,
                "audio": True,
                "off_peak": False,
            }
            if inp.seed is not None:
                body["seed"] = int(inp.seed)
            return body

        if self._uses_img2video_payload(model, images):
            body = {
                "model": model,
                "images": images[:1],
                "prompt": inp.prompt or "",
                "audio": True,
                "voice_id": "professional_host",
                "duration": duration,
                "resolution": resolution,
                "movement_amplitude": "auto",
                "off_peak": False,
            }
            if inp.seed is not None:
                body["seed"] = int(inp.seed)
            return body

        if not images:
            raise ValueError("Vidu reference2video requires at least one reference image")

        body: dict[str, Any] = {
            "model": model,
            "prompt": inp.prompt or "",
            "duration": duration,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
        }

        if self._uses_flat_images_payload(model):
            body["images"] = images
        else:
            body["subjects"] = [{"name": "subject_1", "images": images, "voice_id": ""}]
            body["audio"] = True

        if inp.seed is not None:
            body["seed"] = int(inp.seed)

        return body

    @staticmethod
    def _resolve_create_path(body: dict[str, Any]) -> str:
        """Choose Vidu create endpoint from the built request body shape."""
        if "story" in body:
            return "/ent/v2/template-story"
        if "template" in body:
            return "/ent/v2/template"
        if "image_settings" in body:
            return "/ent/v2/multiframe"
        if "style" in body:
            return "/ent/v2/text2video"
        if "audio" in body and "voice_id" not in body and "images" in body:
            return "/ent/v2/start-end2video"
        if "voice_id" in body:
            return "/ent/v2/img2video"
        return "/ent/v2/reference2video"

    @classmethod
    def _build_reference_images(cls, inp: VideoGenerationInput) -> list[str]:
        """Collect Vidu reference images from frame fields plus r2v asset references.

        Each image is compressed before inclusion so the JSON request body stays
        within Vidu's limit (large base64 blobs trigger ReadError on their API).
        """
        raw = [
            cls._ensure_image_url(value)
            for value in (
                inp.first_frame_base64,
                inp.last_frame_base64,
                inp.key_frame_base64,
                *inp.reference_image_base64s,
            )
            if value
        ]
        return [cls._compress_image_for_vidu(url) for url in raw]

    @staticmethod
    def _compress_image_for_vidu(
        data_url: str,
        *,
        max_px: int = 1024,
        quality: int = 85,
        size_threshold_bytes: int = 512 * 1024,
    ) -> str:
        """Resize and JPEG-compress a base64 data URL image before sending to Vidu.

        HTTP/HTTPS URLs are returned unchanged so Vidu can fetch them directly.
        Images smaller than size_threshold_bytes and within max_px are kept as-is.
        Falls back to the original URL on any error so generation is not blocked.
        """
        if not data_url.startswith("data:"):
            return data_url  # already an HTTP URL

        try:
            import base64
            import io
            from PIL import Image  # pillow must be in dependencies

            _header, b64_data = data_url.split(",", 1)
            raw_bytes = base64.b64decode(b64_data)

            if len(raw_bytes) <= size_threshold_bytes:
                # Already small — check pixel dimensions
                img = Image.open(io.BytesIO(raw_bytes))
                if max(img.width, img.height) <= max_px:
                    img.close()
                    return data_url

            img = Image.open(io.BytesIO(raw_bytes))
            original_size = (img.width, img.height)
            img.thumbnail((max_px, max_px), Image.LANCZOS)

            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")

            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            compressed_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

            logger.info(
                "[ViduVideo] Compressed image: original_size=%s px, raw=%d B → compressed=%d B",
                "x".join(map(str, original_size)),
                len(raw_bytes),
                len(buf.getvalue()),
            )
            return f"data:image/jpeg;base64,{compressed_b64}"
        except Exception:  # noqa: BLE001
            logger.exception("[ViduVideo] Image compression failed; using original")
            return data_url

    @staticmethod
    def _uses_flat_images_payload(model: str) -> bool:
        """Return True for Vidu non-subject reference2video models."""
        return model.strip().lower().endswith("-mix")

    @staticmethod
    def _uses_multiframe_payload(model: str) -> bool:
        """Return True for Vidu smart multi-frame video generation models."""
        return model.strip().lower().startswith("viduq2-turbo")

    @staticmethod
    def _uses_template_payload(model: str) -> bool:
        """Return True for Vidu scene-effect template video generation."""
        name = model.strip().lower()
        return name.startswith("template:") or name in {"hugging", "hug"}

    @staticmethod
    def _uses_template_story_payload(model: str) -> bool:
        """Return True for Vidu story-template full-video generation."""
        name = model.strip().lower()
        return name.startswith("story:") or name.startswith("template-story:")

    @staticmethod
    def _resolve_template_name(model: str) -> str:
        """Resolve the Vidu template identifier encoded in the configured model name."""
        name = model.strip()
        if name.lower().startswith("template:"):
            return name.split(":", 1)[1].strip()
        return name

    @staticmethod
    def _resolve_story_name(model: str) -> str:
        """Resolve the Vidu story identifier encoded in the configured model name."""
        name = model.strip()
        lowered = name.lower()
        if lowered.startswith("template-story:"):
            return name.split(":", 1)[1].strip()
        if lowered.startswith("story:"):
            return name.split(":", 1)[1].strip()
        return name

    @staticmethod
    def _is_standard_vidu_model(model: str) -> bool:
        """Return True for Vidu models that use text2video/img2video/start-end2video routing.

        -pro 和 -turbo 后缀的 viduq3 系列均通过标准 API（text2video / img2video /
        start-end2video）接入，由图片数量自动分流。viduq2-turbo 在更早的 multiframe
        分支已被捕获，不会到达此处。
        """
        m = model.strip().lower()
        return m.endswith("-pro") or m.endswith("-turbo")

    @staticmethod
    def _uses_text2video_payload(model: str, images: list[str]) -> bool:
        """Return True for Vidu text-to-video models without reference images."""
        return not images and ViduVideoApiAdapter._is_standard_vidu_model(model)

    @staticmethod
    def _uses_img2video_payload(model: str, images: list[str]) -> bool:
        """Return True for Vidu image-to-video models with one reference image."""
        return len(images) == 1 and ViduVideoApiAdapter._is_standard_vidu_model(model)

    @staticmethod
    def _uses_start_end2video_payload(model: str, images: list[str]) -> bool:
        """Return True for Vidu first/last-frame video generation."""
        return len(images) >= 2 and ViduVideoApiAdapter._is_standard_vidu_model(model)

    @staticmethod
    def _resolve_resolution(
        inp: VideoGenerationInput,
        cap: Any,
        aspect_ratio: str,
        model: str,
    ) -> str:
        """Resolve Vidu video resolution, defaulting by payload mode.

        Task 5c：业务层 `inp.resolution`（720p/1080p）为权威值，直接透传，保证计费
        与生成一致；未指定时回退到原有的 capability/源视频推断（兼容存量/未计费路径）。
        """
        if getattr(inp, "resolution", None):
            return str(inp.resolution).strip().lower()
        if inp.source_video_base64:
            return "1080p"

        mapping = cap.ratio_to_size_mapping or {}
        fallback = "720p" if ViduVideoApiAdapter._uses_flat_images_payload(model) else "1080p"
        return mapping.get(aspect_ratio) or fallback

    @staticmethod
    def _ensure_image_url(value: str) -> str:
        """Return HTTP/data URLs unchanged; wrap bare base64 as PNG data URI."""
        stripped = value.strip()
        if stripped.startswith(("http://", "https://", "data:")):
            return stripped
        return f"data:image/png;base64,{stripped}"

    async def _poll_until_done(
        self,
        *,
        client: httpx.AsyncClient,
        base_url: str,
        headers: dict[str, str],
        task_id: str,
        deadline: float,
    ) -> VideoGenerationResult:
        """Poll Vidu task creations until a terminal state is reached."""
        poll_url = f"{base_url}/ent/v2/tasks/{task_id}/creations"

        while True:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                raise RuntimeError(f"[ViduVideo] Polling timeout for task_id={task_id}")

            await asyncio.sleep(_POLL_INTERVAL_S)

            response = await client.get(poll_url, headers=headers, timeout=30.0)
            if response.status_code != 200:
                raise RuntimeError(
                    f"[ViduVideo] Poll failed: status={response.status_code} body={response.text[:500]}"
                )

            data: dict[str, Any] = response.json()
            state = str(data.get("state") or "").lower()
            logger.info("[ViduVideo] Poll: task_id=%s state=%s", task_id, state)

            if state not in _TERMINAL_STATES:
                continue

            if state == "failed":
                err_msg = data.get("err_msg") or data.get("message") or "unknown error"
                raise RuntimeError(f"[ViduVideo] Task failed: task_id={task_id} err={err_msg}")

            return self._parse_poll_response(data, task_id)

    @staticmethod
    def _parse_poll_response(data: dict[str, Any], task_id: str) -> VideoGenerationResult:
        """Extract the first video URL from Vidu polling response."""
        creations = data.get("creations") or []
        video_url = ""

        if isinstance(creations, list):
            for item in creations:
                if not isinstance(item, dict):
                    continue
                candidate = item.get("url") or item.get("video_url") or item.get("cover_url") or ""
                if candidate:
                    video_url = str(candidate)
                    break

        if not video_url:
            video_url = str(data.get("video_url") or data.get("url") or "")

        if not video_url:
            raise RuntimeError(
                f"[ViduVideo] Task succeeded but no video URL found: task_id={task_id} data={data!r}"
            )

        return VideoGenerationResult(
            url=video_url,
            file_id=None,
            provider_task_id=task_id,
            provider="vidu",
            status="completed",
        )
