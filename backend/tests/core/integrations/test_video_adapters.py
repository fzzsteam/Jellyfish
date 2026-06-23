"""视频 integrations：httpx MockTransport 单测。"""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import ValidationError

from app.core.integrations.openai.video import OpenAIVideoApiAdapter
from app.core.integrations.volcengine.video import VolcengineVideoApiAdapter
from app.core.integrations.vidu.video import ViduVideoApiAdapter
from app.core.integrations.bailian.video import BailianVideoApiAdapter
from app.core.contracts.provider import ProviderConfig
from app.core.contracts.video_generation import VideoGenerationInput


def _patch_httpx_client(monkeypatch: pytest.MonkeyPatch, transport: httpx.MockTransport) -> None:
    real_client = httpx.AsyncClient

    def factory(**kwargs: object) -> httpx.AsyncClient:
        timeout = kwargs.get("timeout", 60.0)
        return real_client(transport=transport, timeout=timeout)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx, "AsyncClient", factory)


def test_bailian_r2v_payload_uses_asset_reference_images() -> None:
    adapter = BailianVideoApiAdapter(
        provider_config=ProviderConfig(provider="aliyun_bailian", api_key="bailian-key"),
    )
    inp = VideoGenerationInput.model_validate(
        {
            "model": "happyhorse-1.0-r2v",
            "prompt": "角色在园林中奔跑，手里拿着纸鸢",
            "ratio": "9:16",
            "seconds": 5,
            "reference_image_base64s": [
                "data:image/png;base64,character",
                "data:image/png;base64,scene",
                "data:image/png;base64,prop",
            ],
        }
    )

    payload = adapter._build_payload(inp)

    assert payload["model"] == "happyhorse-1.0-r2v"
    assert payload["parameters"]["ratio"] == "9:16"
    assert payload["parameters"]["duration"] == 5
    assert payload["input"]["media"] == [
        {"type": "reference_image", "url": "data:image/png;base64,character"},
        {"type": "reference_image", "url": "data:image/png;base64,scene"},
        {"type": "reference_image", "url": "data:image/png;base64,prop"},
    ]


def test_bailian_happyhorse_duration_keeps_official_integer_range() -> None:
    adapter = BailianVideoApiAdapter(
        provider_config=ProviderConfig(provider="aliyun_bailian", api_key="bailian-key"),
    )
    inp = VideoGenerationInput.model_validate(
        {
            "model": "happyhorse-1.0-r2v",
            "prompt": "test",
            "ratio": "16:9",
            "seconds": 15,
            "reference_image_base64s": ["data:image/png;base64,ref"],
        }
    )

    payload = adapter._build_payload(inp)

    assert payload["parameters"]["duration"] == 15


@pytest.mark.asyncio
async def test_openai_video_create_returns_id(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url).rstrip("/").endswith("/videos")
        payload = json.loads(request.content.decode())
        assert payload["ratio"] == "16:9"
        assert payload["seed"] == 42
        assert payload["watermark"] is False
        assert payload["seconds"] == "6"
        return httpx.Response(200, json={"id": "video-1"})

    _patch_httpx_client(monkeypatch, httpx.MockTransport(handler))
    cfg = ProviderConfig(provider="openai", api_key="sk-test")
    inp = VideoGenerationInput.model_validate(
        {"prompt": "a cat", "ratio": "16:9", "seed": 42, "watermark": False, "seconds": 6}
    )
    vid = await OpenAIVideoApiAdapter().create_video(cfg=cfg, input_=inp, timeout_s=30.0)
    assert vid == "video-1"


@pytest.mark.asyncio
async def test_openai_video_get_returns_meta(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert "/videos/v-99" in str(request.url)
        return httpx.Response(200, json={"status": "completed", "id": "v-99"})

    _patch_httpx_client(monkeypatch, httpx.MockTransport(handler))
    cfg = ProviderConfig(provider="openai", api_key="sk-test")
    meta = await OpenAIVideoApiAdapter().get_video(cfg=cfg, video_id="v-99", timeout_s=30.0)
    assert meta["status"] == "completed"


@pytest.mark.asyncio
async def test_volcengine_video_create_and_get(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            body = json.loads(request.content.decode())
            assert "content" in body
            assert body["ratio"] == "9:16"
            assert body["duration"] == 8
            assert body["seed"] == 7
            assert body["watermark"] is True
            return httpx.Response(200, json={"id": "t-1"})
        if request.method == "GET":
            assert "/contents/generations/tasks/t-1" in str(request.url)
            return httpx.Response(
                200,
                json={"status": "succeeded", "content": {"video_url": "https://v.example/out.mp4"}},
            )
        return httpx.Response(500)

    _patch_httpx_client(monkeypatch, httpx.MockTransport(handler))
    cfg = ProviderConfig(provider="volcengine", api_key="ak-test")
    inp = VideoGenerationInput.model_validate(
        {"prompt": "舞", "ratio": "9:16", "seconds": 8, "seed": 7, "watermark": True}
    )
    tid = await VolcengineVideoApiAdapter().create_contents_task(cfg=cfg, input_=inp, timeout_s=30.0)
    assert tid == "t-1"
    meta = await VolcengineVideoApiAdapter().get_contents_task(cfg=cfg, task_id=tid, timeout_s=30.0)
    assert meta["status"] == "succeeded"
    assert meta["content"]["video_url"] == "https://v.example/out.mp4"


@pytest.mark.asyncio
async def test_vidu_video_reference2video_uses_subject_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def no_sleep(_seconds: float) -> None:
        return None

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            captured["path"] = request.url.path
            captured["auth"] = request.headers.get("authorization")
            body = json.loads(request.content.decode())
            captured["body"] = body
            assert request.url.path.endswith("/ent/v2/reference2video")
            assert body["model"] == "viduq3"
            assert body["duration"] == 8
            assert body["audio"] is True
            assert body["aspect_ratio"] == "3:4"
            assert body["resolution"] == "1080p"
            assert "watermark" not in body
            assert body["subjects"] == [
                {
                    "name": "subject_1",
                    "images": [
                        "https://cdn.example.com/first.png",
                        "https://cdn.example.com/last.png",
                        "data:image/png;base64,a2V5",
                    ],
                    "voice_id": "",
                }
            ]
            return httpx.Response(200, json={"task_id": "vidu-task-1", "state": "created"})
        if request.method == "GET":
            assert request.url.path.endswith("/ent/v2/tasks/vidu-task-1/creations")
            return httpx.Response(
                200,
                json={
                    "task_id": "vidu-task-1",
                    "state": "success",
                    "creations": [{"url": "https://cdn.example.com/out.mp4"}],
                },
            )
        return httpx.Response(500)

    monkeypatch.setattr("asyncio.sleep", no_sleep)
    _patch_httpx_client(monkeypatch, httpx.MockTransport(handler))
    cfg = ProviderConfig(provider="vidu", api_key="vidu-key", base_url="https://api.vidu.cn")
    inp = VideoGenerationInput.model_validate(
        {
            "model": "viduq3",
            "prompt": "@subject_1 在一起吃火锅",
            "ratio": "3:4",
            "seconds": 8,
            "watermark": False,
            "first_frame_base64": "https://cdn.example.com/first.png",
            "last_frame_base64": "https://cdn.example.com/last.png",
            "key_frame_base64": "a2V5",
        }
    )

    result = await ViduVideoApiAdapter().generate(cfg=cfg, inp=inp, timeout_s=30.0)

    assert captured["auth"] == "Token vidu-key"
    assert result.provider == "vidu"
    assert result.provider_task_id == "vidu-task-1"
    assert result.url == "https://cdn.example.com/out.mp4"


@pytest.mark.asyncio
async def test_vidu_video_reference2video_mix_uses_images_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def no_sleep(_seconds: float) -> None:
        return None

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            captured["auth"] = request.headers.get("authorization")
            body = json.loads(request.content.decode())
            captured["body"] = body
            assert request.url.path.endswith("/ent/v2/reference2video")
            assert body == {
                "model": "viduq3-mix",
                "images": [
                    "https://cdn.example.com/ref-1.png",
                    "https://cdn.example.com/ref-2.png",
                    "data:image/png;base64,cmVmMw==",
                ],
                "prompt": "Santa Claus and the bear hug by the lakeside.",
                "duration": 5,
                "aspect_ratio": "3:4",
                "resolution": "720p",
                "seed": 0,
            }
            return httpx.Response(200, json={"task_id": "vidu-mix-task-1", "state": "created"})
        if request.method == "GET":
            assert request.url.path.endswith("/ent/v2/tasks/vidu-mix-task-1/creations")
            return httpx.Response(
                200,
                json={
                    "task_id": "vidu-mix-task-1",
                    "state": "success",
                    "creations": [{"video_url": "https://cdn.example.com/mix-out.mp4"}],
                },
            )
        return httpx.Response(500)

    monkeypatch.setattr("asyncio.sleep", no_sleep)
    _patch_httpx_client(monkeypatch, httpx.MockTransport(handler))
    cfg = ProviderConfig(provider="vidu", api_key="vidu-key", base_url="https://api.vidu.cn")
    inp = VideoGenerationInput.model_validate(
        {
            "model": "viduq3-mix",
            "prompt": "Santa Claus and the bear hug by the lakeside.",
            "ratio": "3:4",
            "seconds": 5,
            "seed": 0,
            "first_frame_base64": "https://cdn.example.com/ref-1.png",
            "last_frame_base64": "https://cdn.example.com/ref-2.png",
            "key_frame_base64": "cmVmMw==",
        }
    )

    result = await ViduVideoApiAdapter().generate(cfg=cfg, inp=inp, timeout_s=30.0)

    assert captured["auth"] == "Token vidu-key"
    assert result.provider == "vidu"
    assert result.provider_task_id == "vidu-mix-task-1"
    assert result.url == "https://cdn.example.com/mix-out.mp4"


@pytest.mark.asyncio
async def test_vidu_video_text2video_uses_official_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def no_sleep(_seconds: float) -> None:
        return None

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            captured["auth"] = request.headers.get("authorization")
            body = json.loads(request.content.decode())
            captured["body"] = body
            assert request.url.path.endswith("/ent/v2/text2video")
            assert body == {
                "model": "viduq3-pro",
                "style": "general",
                "prompt": (
                    "In an ultra-realistic fashion photography style featuring light blue and pale amber tones, "
                    "an astronaut in a spacesuit walks through the fog."
                ),
                "duration": 5,
                "seed": 0,
                "aspect_ratio": "4:3",
                "resolution": "540p",
                "movement_amplitude": "auto",
                "off_peak": False,
            }
            return httpx.Response(200, json={"task_id": "vidu-text-task-1", "state": "created"})
        if request.method == "GET":
            assert request.url.path.endswith("/ent/v2/tasks/vidu-text-task-1/creations")
            return httpx.Response(
                200,
                json={
                    "task_id": "vidu-text-task-1",
                    "state": "success",
                    "creations": [{"url": "https://cdn.example.com/text-out.mp4"}],
                },
            )
        return httpx.Response(500)

    monkeypatch.setattr("asyncio.sleep", no_sleep)
    _patch_httpx_client(monkeypatch, httpx.MockTransport(handler))
    cfg = ProviderConfig(provider="vidu", api_key="vidu-key", base_url="https://api.vidu.cn")
    inp = VideoGenerationInput.model_validate(
        {
            "model": "viduq3-pro",
            "prompt": (
                "In an ultra-realistic fashion photography style featuring light blue and pale amber tones, "
                "an astronaut in a spacesuit walks through the fog."
            ),
            "ratio": "4:3",
            "seconds": 5,
            "seed": 0,
        }
    )

    result = await ViduVideoApiAdapter().generate(cfg=cfg, inp=inp, timeout_s=30.0)

    assert captured["auth"] == "Token vidu-key"
    assert result.provider == "vidu"
    assert result.provider_task_id == "vidu-text-task-1"
    assert result.url == "https://cdn.example.com/text-out.mp4"


@pytest.mark.asyncio
async def test_vidu_video_img2video_uses_official_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def no_sleep(_seconds: float) -> None:
        return None

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            captured["auth"] = request.headers.get("authorization")
            body = json.loads(request.content.decode())
            captured["body"] = body
            assert request.url.path.endswith("/ent/v2/img2video")
            assert body == {
                "model": "viduq3-pro",
                "images": ["https://cdn.example.com/image2video.png"],
                "prompt": "The astronaut waved and the camera moved up.",
                "audio": True,
                "voice_id": "professional_host",
                "duration": 5,
                "seed": 0,
                # Task 5c：未传 resolution 时回退到 capability mapping（viduq3-pro → 540p）
                "resolution": "540p",
                "movement_amplitude": "auto",
                "off_peak": False,
            }
            return httpx.Response(200, json={"task_id": "vidu-img-task-1", "state": "created"})
        if request.method == "GET":
            assert request.url.path.endswith("/ent/v2/tasks/vidu-img-task-1/creations")
            return httpx.Response(
                200,
                json={
                    "task_id": "vidu-img-task-1",
                    "state": "success",
                    "creations": [{"url": "https://cdn.example.com/img-out.mp4"}],
                },
            )
        return httpx.Response(500)

    monkeypatch.setattr("asyncio.sleep", no_sleep)
    _patch_httpx_client(monkeypatch, httpx.MockTransport(handler))
    cfg = ProviderConfig(provider="vidu", api_key="vidu-key", base_url="https://api.vidu.cn")
    inp = VideoGenerationInput.model_validate(
        {
            "model": "viduq3-pro",
            "prompt": "The astronaut waved and the camera moved up.",
            "ratio": "4:3",
            "seconds": 5,
            "seed": 0,
            "first_frame_base64": "https://cdn.example.com/image2video.png",
        }
    )

    result = await ViduVideoApiAdapter().generate(cfg=cfg, inp=inp, timeout_s=30.0)

    assert captured["auth"] == "Token vidu-key"
    assert result.provider == "vidu"
    assert result.provider_task_id == "vidu-img-task-1"
    assert result.url == "https://cdn.example.com/img-out.mp4"


@pytest.mark.asyncio
async def test_vidu_video_start_end2video_uses_official_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def no_sleep(_seconds: float) -> None:
        return None

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            captured["auth"] = request.headers.get("authorization")
            body = json.loads(request.content.decode())
            captured["body"] = body
            assert request.url.path.endswith("/ent/v2/start-end2video")
            assert body == {
                "model": "viduq3-pro",
                "images": [
                    "https://cdn.example.com/start.jpeg",
                    "https://cdn.example.com/end.jpeg",
                ],
                "prompt": "The camera zooms in on the bird, which then flies to the right.",
                "duration": 5,
                "seed": 0,
                # Task 5c：未传 resolution 时回退到 capability mapping（viduq3-pro → 540p）
                "resolution": "540p",
                "audio": True,
                "off_peak": False,
            }
            return httpx.Response(200, json={"task_id": "vidu-start-end-task-1", "state": "created"})
        if request.method == "GET":
            assert request.url.path.endswith("/ent/v2/tasks/vidu-start-end-task-1/creations")
            return httpx.Response(
                200,
                json={
                    "task_id": "vidu-start-end-task-1",
                    "state": "success",
                    "creations": [{"url": "https://cdn.example.com/start-end-out.mp4"}],
                },
            )
        return httpx.Response(500)

    monkeypatch.setattr("asyncio.sleep", no_sleep)
    _patch_httpx_client(monkeypatch, httpx.MockTransport(handler))
    cfg = ProviderConfig(provider="vidu", api_key="vidu-key", base_url="https://api.vidu.cn")
    inp = VideoGenerationInput.model_validate(
        {
            "model": "viduq3-pro",
            "prompt": "The camera zooms in on the bird, which then flies to the right.",
            "ratio": "4:3",
            "seconds": 5,
            "seed": 0,
            "first_frame_base64": "https://cdn.example.com/start.jpeg",
            "last_frame_base64": "https://cdn.example.com/end.jpeg",
        }
    )

    result = await ViduVideoApiAdapter().generate(cfg=cfg, inp=inp, timeout_s=30.0)

    assert captured["auth"] == "Token vidu-key"
    assert result.provider == "vidu"
    assert result.provider_task_id == "vidu-start-end-task-1"
    assert result.url == "https://cdn.example.com/start-end-out.mp4"


@pytest.mark.asyncio
async def test_vidu_video_multiframe_uses_official_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def no_sleep(_seconds: float) -> None:
        return None

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            captured["auth"] = request.headers.get("authorization")
            body = json.loads(request.content.decode())
            captured["body"] = body
            assert request.url.path.endswith("/ent/v2/multiframe")
            assert body == {
                "model": "viduq2-turbo",
                "start_image": "https://cdn.example.com/start.png",
                "image_settings": [
                    {
                        "prompt": "The camera follows the character through three key beats.",
                        "key_image": "https://cdn.example.com/key-1.png",
                        "duration": 5,
                    },
                    {
                        "prompt": "The camera follows the character through three key beats.",
                        "key_image": "data:image/png;base64,a2V5LTI=",
                        "duration": 5,
                    },
                ],
                "resolution": "1080p",
            }
            return httpx.Response(200, json={"task_id": "vidu-multiframe-task-1", "state": "success"})
        if request.method == "GET":
            assert request.url.path.endswith("/ent/v2/tasks/vidu-multiframe-task-1/creations")
            return httpx.Response(
                200,
                json={
                    "task_id": "vidu-multiframe-task-1",
                    "state": "success",
                    "creations": [{"url": "https://cdn.example.com/multiframe-out.mp4"}],
                },
            )
        return httpx.Response(500)

    monkeypatch.setattr("asyncio.sleep", no_sleep)
    _patch_httpx_client(monkeypatch, httpx.MockTransport(handler))
    cfg = ProviderConfig(provider="vidu", api_key="vidu-key", base_url="https://api.vidu.cn")
    inp = VideoGenerationInput.model_validate(
        {
            "model": "viduq2-turbo",
            "prompt": "The camera follows the character through three key beats.",
            "ratio": "4:3",
            "seconds": 5,
            "first_frame_base64": "https://cdn.example.com/start.png",
            "last_frame_base64": "https://cdn.example.com/key-1.png",
            "key_frame_base64": "a2V5LTI=",
        }
    )

    result = await ViduVideoApiAdapter().generate(cfg=cfg, inp=inp, timeout_s=30.0)

    assert captured["auth"] == "Token vidu-key"
    assert result.provider == "vidu"
    assert result.provider_task_id == "vidu-multiframe-task-1"
    assert result.url == "https://cdn.example.com/multiframe-out.mp4"


@pytest.mark.asyncio
async def test_vidu_video_template_uses_official_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def no_sleep(_seconds: float) -> None:
        return None

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            captured["auth"] = request.headers.get("authorization")
            body = json.loads(request.content.decode())
            captured["body"] = body
            assert request.url.path.endswith("/ent/v2/template")
            assert body == {
                "template": "hugging",
                "images": ["https://cdn.example.com/hug.jpeg"],
                "prompt": "Video content\n画面中的两个主体转向彼此，并开始拥抱# 要求\n将Motion Level设置为‘Large’",
                "seed": 0,
            }
            return httpx.Response(200, json={"task_id": "vidu-template-task-1", "state": "created"})
        if request.method == "GET":
            assert request.url.path.endswith("/ent/v2/tasks/vidu-template-task-1/creations")
            return httpx.Response(
                200,
                json={
                    "task_id": "vidu-template-task-1",
                    "state": "success",
                    "creations": [{"url": "https://cdn.example.com/template-out.mp4"}],
                },
            )
        return httpx.Response(500)

    monkeypatch.setattr("asyncio.sleep", no_sleep)
    _patch_httpx_client(monkeypatch, httpx.MockTransport(handler))
    cfg = ProviderConfig(provider="vidu", api_key="vidu-key", base_url="https://api.vidu.cn")
    inp = VideoGenerationInput.model_validate(
        {
            "model": "template:hugging",
            "prompt": "Video content\n画面中的两个主体转向彼此，并开始拥抱# 要求\n将Motion Level设置为‘Large’",
            "ratio": "4:3",
            "seed": 0,
            "first_frame_base64": "https://cdn.example.com/hug.jpeg",
        }
    )

    result = await ViduVideoApiAdapter().generate(cfg=cfg, inp=inp, timeout_s=30.0)

    assert captured["auth"] == "Token vidu-key"
    assert result.provider == "vidu"
    assert result.provider_task_id == "vidu-template-task-1"
    assert result.url == "https://cdn.example.com/template-out.mp4"


@pytest.mark.asyncio
async def test_vidu_video_template_story_uses_official_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def no_sleep(_seconds: float) -> None:
        return None

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            captured["auth"] = request.headers.get("authorization")
            body = json.loads(request.content.decode())
            captured["body"] = body
            assert request.url.path.endswith("/ent/v2/template-story")
            assert body == {
                "story": "choose_one_accept_value",
                "images": [
                    "https://cdn.example.com/story-1.png",
                    "https://cdn.example.com/story-2.png",
                ],
            }
            return httpx.Response(200, json={"task_id": "vidu-template-story-task-1", "state": "created"})
        if request.method == "GET":
            assert request.url.path.endswith("/ent/v2/tasks/vidu-template-story-task-1/creations")
            return httpx.Response(
                200,
                json={
                    "task_id": "vidu-template-story-task-1",
                    "state": "success",
                    "creations": [{"url": "https://cdn.example.com/template-story-out.mp4"}],
                },
            )
        return httpx.Response(500)

    monkeypatch.setattr("asyncio.sleep", no_sleep)
    _patch_httpx_client(monkeypatch, httpx.MockTransport(handler))
    cfg = ProviderConfig(provider="vidu", api_key="vidu-key", base_url="https://api.vidu.cn")
    inp = VideoGenerationInput.model_validate(
        {
            "model": "story:choose_one_accept_value",
            "ratio": "4:3",
            "first_frame_base64": "https://cdn.example.com/story-1.png",
            "last_frame_base64": "https://cdn.example.com/story-2.png",
        }
    )

    result = await ViduVideoApiAdapter().generate(cfg=cfg, inp=inp, timeout_s=30.0)

    assert captured["auth"] == "Token vidu-key"
    assert result.provider == "vidu"
    assert result.provider_task_id == "vidu-template-story-task-1"
    assert result.url == "https://cdn.example.com/template-story-out.mp4"


def test_video_input_seed_bounds_validation() -> None:
    # 边界值应可通过：-1 以及 uint32 最大值
    VideoGenerationInput.model_validate({"prompt": "ok", "ratio": "16:9", "seed": -1})
    VideoGenerationInput.model_validate({"prompt": "ok", "ratio": "16:9", "seed": 4294967295})

    # 越界值应被拒绝：小于 -1 或大于 uint32 最大值
    with pytest.raises(ValidationError):
        VideoGenerationInput.model_validate({"prompt": "bad", "ratio": "16:9", "seed": -2})
    with pytest.raises(ValidationError):
        VideoGenerationInput.model_validate({"prompt": "bad", "ratio": "16:9", "seed": 4294967296})
