import asyncio

from app.core.storage import init_storage


async def _main() -> None:
    """初始化对象存储（例如创建 bucket）。"""
    await asyncio.to_thread(init_storage)


if __name__ == "__main__":
    asyncio.run(_main())

