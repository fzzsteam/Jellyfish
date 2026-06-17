"""SPA 静态入口缓存头测试。"""

from __future__ import annotations

import pytest

from app.main import _SPAStaticFiles


@pytest.mark.asyncio
async def test_spa_fallback_index_disables_browser_cache(tmp_path) -> None:
    """验证前端路由 fallback 到 index.html 时禁止浏览器缓存入口文件。"""
    (tmp_path / "index.html").write_text("<div id='root'></div>", encoding="utf-8")
    files = _SPAStaticFiles(directory=str(tmp_path), html=True)

    response = await files.get_response(
        "projects",
        {
            "type": "http",
            "method": "GET",
            "path": "/projects",
            "headers": [],
        },
    )

    assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0"

