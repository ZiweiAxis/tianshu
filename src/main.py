# 天枢主入口
# E2-S2：可启动 Matrix 连接 + 飞书 Bridge（Matrix 事件 -> 飞书）；飞书事件需由 HTTP 回调或 Stream 调用 handle_feishu_event
# E11-S3：同进程提供 /health、/ready 探针

import asyncio
import logging

import aiohttp.web

from src.bridge.feishu import FeishuBridge, make_matrix_sync_callback
from src.core import room_manager, translator
from src.config import HEALTH_PORT
from src.matrix.client import MatrixClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 就绪：可扩展为检查 Matrix 连接等
_matrix_ready = False


def set_matrix_ready(ready: bool):
    global _matrix_ready
    _matrix_ready = ready


async def health(_request: aiohttp.web.Request) -> aiohttp.web.Response:
    """E11-S3：liveness，进程存活即 200。"""
    return aiohttp.web.json_response({"status": "ok"})


async def ready(_request: aiohttp.web.Request) -> aiohttp.web.Response:
    """E11-S3：readiness，当前实现为进程已启动即 200；可扩展为依赖 Matrix 连接。"""
    return aiohttp.web.json_response({"ready": True, "matrix_connected": _matrix_ready})


async def run_health_server(port: int) -> aiohttp.web.AppRunner:
    """在后台提供 /health、/ready。"""
    app = aiohttp.web.Application()
    app.router.add_get("/health", health)
    app.router.add_get("/ready", ready)
    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("健康探针已启动 http://0.0.0.0:%s/health, /ready", port)
    return runner


async def run_bridge():
    """连接 Matrix，启动 sync 循环，将 Matrix 事件转发到飞书。"""
    matrix = MatrixClient()
    feishu = FeishuBridge()
    if not feishu.is_configured:
        logger.warning("飞书未配置，Matrix -> 飞书 将不可用")
    on_event = make_matrix_sync_callback(feishu, room_manager, translator)
    if not await matrix.connect():
        logger.error("Matrix 连接失败，退出")
        return
    set_matrix_ready(True)
    matrix.start_sync_loop(on_event)
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass
    finally:
        set_matrix_ready(False)
    await matrix.disconnect()


async def main():
    """先启动健康探针，再跑桥接（桥接阻塞直到退出）。"""
    runner = await run_health_server(HEALTH_PORT)
    try:
        await run_bridge()
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
