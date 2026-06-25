"""视频生成任务（Task）：对接 OpenAI Videos API、火山方舟与阿里百炼（DashScope）。

HTTP 细节在 `app.core.integrations`；本模块保留轮询节奏与 BaseTask 契约。
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)

from app.core.integrations.openai.video import OpenAIVideoApiAdapter
from app.core.integrations.volcengine.video import VolcengineVideoApiAdapter
from app.core.integrations.bailian.video import BailianVideoApiAdapter
from app.core.integrations.vidu.video import ViduVideoApiAdapter
from app.core.contracts.provider import ProviderConfig
from app.core.tasks.registry import resolve_task_adapter
from app.core.contracts.video_generation import VideoGenerationInput, VideoGenerationResult
from app.core.task_manager.types import BaseTask

__all__ = [
    "VideoGenerationInput",
    "VideoGenerationResult",
    "AbstractVideoGenerationTask",
    "OpenAIVideoGenerationTask",
    "VolcengineVideoGenerationTask",
    "BailianVideoGenerationTask",
    "ViduVideoGenerationTask",
    "VideoGenerationTask",
]


class AbstractVideoGenerationTask(BaseTask, ABC):
    """视频生成任务基类：公共状态与 run/status/is_done/get_result。"""

    def __init__(
        self,
        *,
        provider_config: ProviderConfig,
        input_: VideoGenerationInput,
        poll_interval_s: float = 2.0,
        timeout_s: float = 120.0,
    ) -> None:
        self._cfg = provider_config
        self._input = input_
        self._poll_interval_s = poll_interval_s
        self._timeout_s = timeout_s
        self._provider_task_id: str | None = None
        self._result: VideoGenerationResult | None = None
        self._error: str = ""

    async def _sleep_poll(self) -> None:
        await asyncio.sleep(self._poll_interval_s)

    @abstractmethod
    async def _create_task(self) -> None:
        """发起供应商创建任务请求，并设置 self._provider_task_id。"""

    @abstractmethod
    async def _poll_and_get_result(self) -> VideoGenerationResult:
        """轮询至终态并解析为 VideoGenerationResult。"""

    async def run(self, *args: Any, **kwargs: Any) -> AsyncIterator[Any] | None:  # type: ignore[override]
        try:
            await self._create_task()
            self._result = await self._poll_and_get_result()
            if self._result is not None:
                self._provider_task_id = self._result.provider_task_id
        except Exception as exc:  # noqa: BLE001
            # str(exc) can be empty for some network exceptions (e.g. httpx.ConnectError);
            # fall back to the exception type name so the error is never silently lost.
            error_msg = str(exc) or f"{type(exc).__name__}: (no message)"
            logger.exception(
                "Video generation task failed: provider=%s error=%s",
                self._cfg.provider,
                error_msg,
            )
            self._error = error_msg
            self._result = None
        return None

    async def status(self) -> dict[str, Any]:  # type: ignore[override]
        return {
            "task": "video_generation",
            "provider": self._cfg.provider,
            "provider_task_id": self._provider_task_id,
            "done": await self.is_done(),
            "has_result": self._result is not None,
            "error": self._error,
            "status": self._result.status if self._result else None,
        }

    async def is_done(self) -> bool:  # type: ignore[override]
        return self._result is not None or bool(self._error)

    async def get_result(self) -> VideoGenerationResult | None:  # type: ignore[override]
        return self._result


class OpenAIVideoGenerationTask(AbstractVideoGenerationTask):
    """OpenAI Videos：adapter 负责 HTTP，Task 负责轮询间隔。"""

    def __init__(
        self,
        *,
        adapter: OpenAIVideoApiAdapter | None = None,
        provider_config: ProviderConfig,
        input_: VideoGenerationInput,
        poll_interval_s: float = 2.0,
        timeout_s: float = 120.0,
    ) -> None:
        super().__init__(
            provider_config=provider_config,
            input_=input_,
            poll_interval_s=poll_interval_s,
            timeout_s=timeout_s,
        )
        self._adapter = adapter or OpenAIVideoApiAdapter()

    async def _create_task(self) -> None:
        self._provider_task_id = await self._adapter.create_video(
            cfg=self._cfg,
            input_=self._input,
            timeout_s=self._timeout_s,
        )

    async def _poll_and_get_result(self) -> VideoGenerationResult:
        video_id = self._provider_task_id or ""
        if not video_id:
            raise RuntimeError("OpenAI poll missing provider task id")

        base_url = (self._cfg.base_url or "https://api.openai.com/v1").rstrip("/")
        status_val = ""
        while True:
            meta = await self._adapter.get_video(
                cfg=self._cfg,
                video_id=video_id,
                timeout_s=self._timeout_s,
            )
            status_val = str(meta.get("status") or "")
            if status_val in ("completed", "failed"):
                if status_val == "failed":
                    raise RuntimeError(f"OpenAI video failed: {meta.get('error')!r}")
                break
            await self._sleep_poll()

        return VideoGenerationResult(
            url=f"{base_url}/videos/{video_id}/content",
            file_id=None,
            provider_task_id=video_id,
            provider="openai",
            status=status_val or "completed",
        )


class VolcengineVideoGenerationTask(AbstractVideoGenerationTask):
    """火山内容生成任务：adapter 负责 HTTP，Task 负责轮询。"""

    def __init__(
        self,
        *,
        adapter: VolcengineVideoApiAdapter | None = None,
        provider_config: ProviderConfig,
        input_: VideoGenerationInput,
        poll_interval_s: float = 2.0,
        timeout_s: float = 120.0,
    ) -> None:
        super().__init__(
            provider_config=provider_config,
            input_=input_,
            poll_interval_s=poll_interval_s,
            timeout_s=timeout_s,
        )
        self._adapter = adapter or VolcengineVideoApiAdapter()

    async def _create_task(self) -> None:
        self._provider_task_id = await self._adapter.create_contents_task(
            cfg=self._cfg,
            input_=self._input,
            timeout_s=self._timeout_s,
        )

    async def _poll_and_get_result(self) -> VideoGenerationResult:
        task_id = self._provider_task_id or ""
        if not task_id:
            raise RuntimeError("Volcengine poll missing provider task id")

        base_url = (self._cfg.base_url or "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
        status_val = ""
        video_url: str | None = None
        while True:
            meta = await self._adapter.get_contents_task(
                cfg=self._cfg,
                task_id=task_id,
                timeout_s=self._timeout_s,
            )
            status_val = str(meta.get("status") or "")
            content = meta.get("content") or {}
            if isinstance(content, dict):
                vu = content.get("video_url")
                if isinstance(vu, str) and vu:
                    video_url = vu
            if status_val in ("succeeded", "failed", "cancelled"):
                if status_val != "succeeded":
                    raise RuntimeError(f"Volcengine task not succeeded: status={status_val!r} meta={meta!r}")
                break
            await self._sleep_poll()

        if not video_url:
            video_url = f"{base_url}/contents/generations/tasks/{task_id}"

        return VideoGenerationResult(
            url=video_url,
            file_id=None,
            provider_task_id=task_id,
            provider="volcengine",
            status=status_val or "succeeded",
        )


class BailianVideoGenerationTask(AbstractVideoGenerationTask):
    """阿里百炼 DashScope 视频生成任务：委托 `BailianVideoApiAdapter`。

    支持模型：
    - HappyHorse-1.0-t2v (文本转视频)
    - 其他 DashScope 视频生成模型

    特点：
    - 异步任务模式（提交 → 轮询）
    - 内置轮询逻辑，无需外部控制
    """

    def __init__(
        self,
        *,
        adapter: BailianVideoApiAdapter | None = None,
        provider_config: ProviderConfig,
        input_: VideoGenerationInput,
        poll_interval_s: float = 5.0,  # 百炼视频生成较慢
        timeout_s: float = 600.0,   # 默认等待最多 10 分钟
    ) -> None:
        super().__init__(
            provider_config=provider_config,
            input_=input_,
            poll_interval_s=poll_interval_s,
            timeout_s=timeout_s,
        )
        self._adapter = adapter or BailianVideoApiAdapter(provider_config=provider_config)
        self._deferred: VideoGenerationResult | None = None

    async def _create_task(self) -> None:
        # Bailian adapter 内部处理提交+轮询全流程
        self._deferred = await self._adapter.generate(self._input)

    async def _poll_and_get_result(self) -> VideoGenerationResult:
        if self._deferred is None:
            raise RuntimeError("Bailian video generate() completed without setting deferred result")
        return self._deferred


class ViduVideoGenerationTask(AbstractVideoGenerationTask):
    """Vidu reference2video task wrapper around the Vidu HTTP adapter."""

    def __init__(
        self,
        *,
        adapter: ViduVideoApiAdapter | None = None,
        provider_config: ProviderConfig,
        input_: VideoGenerationInput,
        poll_interval_s: float = 3.0,
        timeout_s: float = 600.0,
    ) -> None:
        super().__init__(
            provider_config=provider_config,
            input_=input_,
            poll_interval_s=poll_interval_s,
            timeout_s=timeout_s,
        )
        self._adapter = adapter or ViduVideoApiAdapter()
        self._deferred: VideoGenerationResult | None = None

    async def _create_task(self) -> None:
        self._deferred = await self._adapter.generate(
            cfg=self._cfg,
            inp=self._input,
            timeout_s=self._timeout_s,
        )

    async def _poll_and_get_result(self) -> VideoGenerationResult:
        if self._deferred is None:
            raise RuntimeError("Vidu video generate() completed without setting deferred result")
        return self._deferred


class VideoGenerationTask(BaseTask):
    """按 provider 分派到 OpenAI / 火山实现；对外构造函数签名保持不变。"""

    def __init__(
        self,
        *,
        provider_config: ProviderConfig,
        input_: VideoGenerationInput,
        poll_interval_s: float | None = None,
        timeout_s: float | None = None,
    ) -> None:
        from app.bootstrap import bootstrap_all_registries

        bootstrap_all_registries()
        factory = resolve_task_adapter("video_generation", provider_config.provider)
        # Only pass overrides that were explicitly provided; otherwise let each
        # provider factory use its own defaults (e.g. Vidu uses 600 s, not 120 s).
        kwargs: dict[str, Any] = {"provider_config": provider_config, "input_": input_}
        if poll_interval_s is not None:
            kwargs["poll_interval_s"] = poll_interval_s
        if timeout_s is not None:
            kwargs["timeout_s"] = timeout_s
        self._impl: AbstractVideoGenerationTask = factory(**kwargs)  # type: ignore[assignment]

    @staticmethod
    def _build_openai_impl(
        *,
        provider_config: ProviderConfig,
        input_: VideoGenerationInput,
        poll_interval_s: float = 2.0,
        timeout_s: float = 120.0,
    ) -> AbstractVideoGenerationTask:
        return OpenAIVideoGenerationTask(
            provider_config=provider_config,
            input_=input_,
            poll_interval_s=poll_interval_s,
            timeout_s=timeout_s,
        )

    @staticmethod
    def _build_volcengine_impl(
        *,
        provider_config: ProviderConfig,
        input_: VideoGenerationInput,
        poll_interval_s: float = 2.0,
        timeout_s: float = 120.0,
    ) -> AbstractVideoGenerationTask:
        return VolcengineVideoGenerationTask(
            provider_config=provider_config,
            input_=input_,
            poll_interval_s=poll_interval_s,
            timeout_s=timeout_s,
        )

    @staticmethod
    def _build_bailian_impl(
        *,
        provider_config: ProviderConfig,
        input_: VideoGenerationInput,
        poll_interval_s: float = 5.0,
        timeout_s: float = 600.0,
    ) -> AbstractVideoGenerationTask:
        return BailianVideoGenerationTask(
            provider_config=provider_config,
            input_=input_,
            poll_interval_s=poll_interval_s,
            timeout_s=timeout_s,
        )

    @staticmethod
    def _build_vidu_impl(
        *,
        provider_config: ProviderConfig,
        input_: VideoGenerationInput,
        poll_interval_s: float = 3.0,
        timeout_s: float = 600.0,
    ) -> AbstractVideoGenerationTask:
        return ViduVideoGenerationTask(
            provider_config=provider_config,
            input_=input_,
            poll_interval_s=poll_interval_s,
            timeout_s=timeout_s,
        )

    async def run(self, *args: Any, **kwargs: Any) -> AsyncIterator[Any] | None:  # type: ignore[override]
        return await self._impl.run(*args, **kwargs)

    async def status(self) -> dict[str, Any]:  # type: ignore[override]
        return await self._impl.status()

    async def is_done(self) -> bool:  # type: ignore[override]
        return await self._impl.is_done()

    async def get_result(self) -> VideoGenerationResult | None:  # type: ignore[override]
        return await self._impl.get_result()
