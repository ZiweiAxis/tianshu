# 天枢主入口
# E2-S2：可启动 Matrix 连接 + 飞书 Bridge（Matrix 事件 -> 飞书）；飞书事件需由 HTTP 回调或 Stream 调用 handle_feishu_event
# E11-S3：同进程提供 /health、/ready 探针

import asyncio
import logging
import os

import aiohttp.web

from bridge.feishu import FeishuBridge, make_matrix_sync_callback
from core import room_manager, translator
from config import HEALTH_PORT
from matrix.client import MatrixClient
from api.owners import owners_register_handler

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
    from discovery import get_discovery_payload
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
    from registration.human_initiated import register_agent_by_human
    from registration.diting.notify import notify_agent_registered
    from registration.diting.chain_did import register_did_on_chain

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
    from identity.agent_presence import agent_heartbeat as do_heartbeat

    out = do_heartbeat(agent_id, status)
    if not out.get("ok"):
        return aiohttp.web.json_response(out, status=404)
    return aiohttp.web.json_response(out)


async def approval_request_handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """
    POST /api/v1/delivery/approval-request：投递审批请求
    body: {
        "target": {
            "channel": "telegram",  // 或 "matrix"
            "receive_id": "123456789",  // Telegram user_id，可选
            "owner_id": "owner-xxx",    // 所有者 ID，可选（用于自动查找 Telegram receive_id）
            "receive_id_type": "user_id"
        },
        "payload": {
            "title": "审批标题",
            "description": "审批描述",
            "source_agent_id": "agent_xxx",
            "request_id": "req_xxx",
            "cheq_id": "cheq_xxx",  // CHEQ ID
            "callback_url": "http://xxx/callback"
        }
    }
    返回: {"ok": true, "message_id": "xxx", "channel": "telegram"}
    
    注意：
    - Telegram 渠道支持通过 owner_id 自动查找用户的 Telegram receive_id
    - 审批消息会带批准/拒绝按钮，用户点击后会自动更新 CHEQ 状态
    """
    from config import APPROVAL_USER_ID, DITING_MATRIX_TOKEN, MATRIX_HOMESERVER, TELEGRAM_APPROVAL_BOT_TOKEN
    
    try:
        body = await request.json()
    except Exception as e:
        return aiohttp.web.json_response({"ok": False, "error": f"无效 JSON: {e}"}, status=400)
    
    target = body.get("target", {})
    payload = body.get("payload", {})
    channel = target.get("channel", "matrix")
    
    if not payload:
        return aiohttp.web.json_response({"ok": False, "error": "缺少 payload"}, status=400)
    
    # Telegram 渠道投递
    if channel == "telegram":
        from channel.telegram.provider import TelegramProvider
        
        telegram_token = target.get("token") or TELEGRAM_APPROVAL_BOT_TOKEN
        if not telegram_token:
            return aiohttp.web.json_response({"ok": False, "error": "未配置 TELEGRAM_APPROVAL_BOT_TOKEN"}, status=500)
        
        telegram_chat_id = target.get("receive_id")
        owner_id = target.get("owner_id")
        
        # 如果没有 receive_id，尝试从 owner_id 查找 Telegram receive_id
        if not telegram_chat_id and owner_id:
            from identity.owners import get_enabled_channel, get_owner
            owner = get_owner(owner_id)
            if not owner:
                return aiohttp.web.json_response({"ok": False, "error": f"owner_id={owner_id} 不存在"}, status=400)
            
            # 查找 Telegram 渠道
            channel_info = get_enabled_channel(owner_id)
            if channel_info and channel_info.get("type") == "telegram":
                telegram_chat_id = channel_info.get("receive_id")
                logger.info(f"从 owner_id={owner_id} 找到 Telegram receive_id: {telegram_chat_id}")
            else:
                # 遍历所有渠道找 Telegram
                from identity.owners import get_channels
                all_channels = get_channels(owner_id)
                for ch in all_channels:
                    if ch.get("type") == "telegram" and ch.get("enabled", True):
                        telegram_chat_id = ch.get("receive_id")
                        logger.info(f"从 owner_id={owner_id} 渠道列表找到 Telegram receive_id: {telegram_chat_id}")
                        break
        
        if not telegram_chat_id:
            if owner_id:
                return aiohttp.web.json_response({"ok": False, "error": f"owner_id={owner_id} 未绑定 Telegram 渠道"}, status=400)
            else:
                return aiohttp.web.json_response({"ok": False, "error": "telegram 投递需要 receive_id 或 owner_id"}, status=400)
        
        provider = TelegramProvider(telegram_token)
        
        title = payload.get("title", "审批请求")
        description = payload.get("description", payload.get("content", ""))
        cheq_id = payload.get("request_id") or payload.get("cheq_id", "")
        request_id = payload.get("request_id", "")
        
        # 构建带按钮的审批消息
        buttons = [
            [
                {"text": "✅ 批准", "callback_data": f"approve:{request_id}"},
                {"text": "❌ 拒绝", "callback_data": f"reject:{request_id}"},
            ]
        ]
        
        message = f"🔔 *{title}*\n\n{description}\n\n🆔 ID: `{cheq_id}`"
        
        message_id = await provider.deliver(
            chat_id=telegram_chat_id,
            message=message,
            semantic_type="approval_request",
            buttons=buttons,
        )
        
        if message_id:
            return aiohttp.web.json_response({"ok": True, "message_id": message_id, "channel": "telegram", "chat_id": telegram_chat_id})
        else:
            return aiohttp.web.json_response({"ok": False, "error": "Telegram 投递失败"}, status=500)
    
    # 获取 Matrix 客户端实例
    matrix = MatrixClient()
    if not await matrix.connect():
        return aiohttp.web.json_response({"ok": False, "error": "Matrix 连接失败"}, status=500)
    
    try:
        # 卡片 ID（使用 request_id 或生成）
        card_id = payload.get("request_id") or payload.get("cheq_id")
        
        # 构造符合太白协议格式的 payload
        # 协议格式要求包含 metadata 和 actions
        card_payload = {
            "title": payload.get("title", "审批请求"),
            "content": payload.get("description", payload.get("content", "")),
            "metadata": {
                "cheq_id": payload.get("request_id") or payload.get("cheq_id", ""),
                "agent_did": payload.get("source_agent_id"),
                "operation": payload.get("operation"),
                "risk_level": payload.get("risk_level"),
            },
            "expires_at": payload.get("expires_at"),
        }
        
        # 发送 Matrix 原生卡片消息（支持交互按钮）
        event_id = await matrix.send_card_with_token(
            user_id=approval_user_id,
            semantic_type="approval_request",
            payload=card_payload,
            access_token=access_token,
            card_id=card_id,
        )
        
        if event_id:
            # 记录审批消息用于「回复即批准」
            from core.approval_reply import record_approval_message
            gateway_base_url = MATRIX_HOMESERVER
            request_id = payload.get("request_id", "")
            # 需要获取 room_id，从映射文件中获取
            import json
            from config import DM_MAPPING_FILE
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
    from bridge.telegram import TelegramBridge
    from config import TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET
    
    app = aiohttp.web.Application()
    app.router.add_get("/health", health)
    app.router.add_get("/ready", ready)
    app.router.add_get("/.well-known/tianshu-matrix", discovery_handler)
    app.router.add_get("/api/v1/discovery", discovery_handler)
    app.router.add_post("/api/v1/agents/register", agents_register_handler)
    app.router.add_post("/api/v1/agents/heartbeat", agents_heartbeat_handler)
    app.router.add_post("/api/v1/owners/register", owners_register_handler)
    app.router.add_post("/api/v1/delivery/approval-request", approval_request_handler)
    
    # Telegram Webhook 端点（使用 telegram_webhook 模块）
    if TELEGRAM_BOT_TOKEN:
        from telegram_webhook import setup_webhook_in_app, create_bridge_handler
        
        async def _bridge_handler(data):
            from bridge.telegram import handle_telegram_event
            matrix = MatrixClient()
            if await matrix.connect():
                try:
                    await handle_telegram_event(data, matrix, room_manager)
                finally:
                    await matrix.disconnect()
        
        setup_webhook_in_app(
            app,
            token=TELEGRAM_BOT_TOKEN,
            secret=TELEGRAM_WEBHOOK_SECRET,
            handlers=[_bridge_handler],
        )
        logger.info("Telegram Webhook 已通过 telegram_webhook 模块注册")
    
    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("健康探针已启动 http://0.0.0.0:%s/health, /ready, /api/v1/delivery/approval-request", port)
    return runner


async def run_bridge():
    """连接 Matrix，启动 sync 循环，将 Matrix 事件转发到飞书和 Telegram。"""
    from config import TELEGRAM_WUKONG_BOT_TOKEN
    from bridge.feishu import FeishuBridge, make_matrix_sync_callback
    from bridge.telegram import TelegramBridge
    
    matrix = MatrixClient()
    feishu = FeishuBridge()
    telegram = TelegramBridge(token=TELEGRAM_WUKONG_BOT_TOKEN)
    
    if not feishu.is_configured:
        logger.warning("飞书未配置，Matrix -> 飞书 将不可用")
    if not telegram.is_configured:
        logger.warning("Telegram 未配置，Matrix -> Telegram 将不可用")
    
    on_event = make_matrix_sync_callback(feishu, room_manager, translator, telegram_bridge=telegram)
    matrix_connected = await matrix.connect()
    if not matrix_connected:
        logger.warning("Matrix 连接失败，将以只读模式运行（仅支持 Telegram 投递）")
    else:
        set_matrix_ready(True)
        matrix.start_sync_loop(on_event)
    
    # 启动 @diting 审批监听器（监听审批回复）
    from diting_listener import start_diting_listener
    if not await start_diting_listener():
        logger.warning("DitingApprovalListener 启动失败，审批回复功能将不可用")
    
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass
    finally:
        set_matrix_ready(False)
        from diting_listener import stop_diting_listener
        await stop_diting_listener()
    await matrix.disconnect()


async def main():
    """先启动健康探针，再跑桥接（桥接阻塞直到退出）。"""
    from gateway_bootstrap import bootstrap_gateway_token
    if not bootstrap_gateway_token():
        logger.warning("网关 token 未配置且自举失败，Matrix 连接可能失败")
    runner = await run_health_server(HEALTH_PORT)
    try:
        await run_bridge()
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
