# 天枢主入口
# E2-S2：可启动 Matrix 连接 + 飞书 Bridge（Matrix 事件 -> 飞书）；飞书事件需由 HTTP 回调或 Stream 调用 handle_feishu_event
# E11-S3：同进程提供 /health、/ready 探针

import asyncio
import logging
import os

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


async def discovery_handler(_request: aiohttp.web.Request) -> aiohttp.web.Response:
    """Agent 发现：GET /.well-known/tianshu-matrix 或 /api/v1/discovery，返回 matrix_homeserver 与可选 api_base。"""
    from src.discovery import get_discovery_payload
    return aiohttp.web.json_response(get_discovery_payload())


async def agents_register_handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """POST /api/v1/agents/register：太白 SDK 约定，body { owner_id, agent_display_id? }，返回 { ok, agent_id, owner_id }。"""
    try:
        body = await request.json()
    except Exception as e:
        return aiohttp.web.json_response({"ok": False, "error": f"无效 JSON: {e}"}, status=400)
    owner_id = (body.get("owner_id") or "").strip()
    if not owner_id:
        return aiohttp.web.json_response({"ok": False, "error": "缺少 owner_id"}, status=400)
    agent_display_id = (body.get("agent_display_id") or "").strip() or None
    from src.registration.human_initiated import register_agent_by_human
    from src.diting_client.init_permission import notify_agent_registered
    from src.diting_client.chain_did import register_did_on_chain

    out = register_agent_by_human("api", owner_id, agent_display_id, ensure_owner_registered=True, notify_diting=False)
    if not out.get("ok"):
        return aiohttp.web.json_response(out, status=400)
    agent_id = out["agent_id"]
    owner_id_res = out["owner_id"]

    async def _notify_diting():
        try:
            await notify_agent_registered(agent_id, owner_id_res)
            await register_did_on_chain(agent_id, owner_id_res)
        except Exception as e:
            logger.warning("注册后通知谛听/链上 DID 失败: %s", e)

    asyncio.create_task(_notify_diting())
    return aiohttp.web.json_response(out)


async def agents_heartbeat_handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """POST /api/v1/agents/heartbeat：太白 SDK 约定，body { agent_id, status? }，返回 { ok, agent_id, last_seen_ts }。"""
    try:
        body = await request.json()
    except Exception as e:
        return aiohttp.web.json_response({"ok": False, "error": f"无效 JSON: {e}"}, status=400)
    agent_id = (body.get("agent_id") or "").strip()
    if not agent_id:
        return aiohttp.web.json_response({"ok": False, "error": "缺少 agent_id"}, status=400)
    status = (body.get("status") or "").strip() or None
    from src.identity.agent_presence import agent_heartbeat as do_heartbeat

    out = do_heartbeat(agent_id, status)
    if not out.get("ok"):
        return aiohttp.web.json_response(out, status=404)
    return aiohttp.web.json_response(out)


async def approval_request_handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """
    POST /api/v1/delivery/approval-request：投递审批请求
    body: {
        "target": {"channel": "feishu", "receive_id": "oc_xxx", "receive_id_type": "chat_id"},
        "payload": {
            "title": "审批标题",
            "description": "审批描述",
            "source_agent_id": "agent_xxx",
            "request_id": "req_xxx",
            "callback_url": "http://xxx/callback"
        }
    }
    返回: {"ok": true, "event_id": "xxx", "room_id": "xxx"}
    """
    from src.config import APPROVAL_USER_ID, DITING_MATRIX_TOKEN, MATRIX_HOMESERVER
    
    try:
        body = await request.json()
    except Exception as e:
        return aiohttp.web.json_response({"ok": False, "error": f"无效 JSON: {e}"}, status=400)
    
    target = body.get("target", {})
    payload = body.get("payload", {})
    
    if not target:
        return aiohttp.web.json_response({"ok": False, "error": "缺少 target"}, status=400)
    if not payload:
        return aiohttp.web.json_response({"ok": False, "error": "缺少 payload"}, status=400)
    
    # 获取审批目标用户 ID（默认为配置中的 APPROVAL_USER_ID）
    approval_user_id = body.get("user_id") or APPROVAL_USER_ID
    if not approval_user_id:
        return aiohttp.web.json_response({"ok": False, "error": "未配置 APPROVAL_USER_ID"}, status=500)
    
    # 使用 DITING_MATRIX_TOKEN 发送审批请求（DM 复用）
    access_token = body.get("access_token") or DITING_MATRIX_TOKEN
    if not access_token:
        return aiohttp.web.json_response({"ok": False, "error": "未配置 DITING_MATRIX_TOKEN"}, status=500)
    
    # 获取 Matrix 客户端实例
    matrix = MatrixClient()
    if not await matrix.connect():
        return aiohttp.web.json_response({"ok": False, "error": "Matrix 连接失败"}, status=500)
    
    try:
        # 发送审批请求（使用 DM 复用）
        event_id = await matrix.send_delivery_with_token(
            user_id=approval_user_id,
            semantic_type="approval_request",
            target=target,
            payload=payload,
            access_token=access_token,
            body_summary=payload.get("title") or "审批请求",
        )
        
        if event_id:
            # 记录审批消息用于「回复即批准」
            from src.core.approval_reply import record_approval_message
            gateway_base_url = MATRIX_HOMESERVER
            request_id = payload.get("request_id", "")
            # 需要获取 room_id，从映射文件中获取
            import json
            from src.config import DM_MAPPING_FILE
            room_id = None
            try:
                if os.path.exists(DM_MAPPING_FILE):
                    with open(DM_MAPPING_FILE, "r") as f:
                        mapping = json.load(f)
                        room_id = mapping.get(approval_user_id)
            except Exception:
                pass
            
            if room_id and request_id:
                record_approval_message(room_id, event_id, request_id, gateway_base_url)
            
            return aiohttp.web.json_response({
                "ok": True,
                "event_id": event_id,
                "room_id": room_id,
            })
        else:
            return aiohttp.web.json_response({"ok": False, "error": "发送审批请求失败"}, status=500)
    finally:
        await matrix.disconnect()


async def run_health_server(port: int) -> aiohttp.web.AppRunner:
    """在后台提供 /health、/ready 与 Agent 发现端点。"""
    app = aiohttp.web.Application()
    app.router.add_get("/health", health)
    app.router.add_get("/ready", ready)
    app.router.add_get("/.well-known/tianshu-matrix", discovery_handler)
    app.router.add_get("/api/v1/discovery", discovery_handler)
    app.router.add_post("/api/v1/agents/register", agents_register_handler)
    app.router.add_post("/api/v1/agents/heartbeat", agents_heartbeat_handler)
    app.router.add_post("/api/v1/delivery/approval-request", approval_request_handler)
    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("健康探针已启动 http://0.0.0.0:%s/health, /ready, /api/v1/delivery/approval-request", port)
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
    from src.gateway_bootstrap import bootstrap_gateway_token
    if not bootstrap_gateway_token():
        logger.warning("网关 token 未配置且自举失败，Matrix 连接可能失败")
    runner = await run_health_server(HEALTH_PORT)
    try:
        await run_bridge()
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
