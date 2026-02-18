# E2-S2：飞书 ↔ Matrix 双向 Bridge
# 飞书事件经 HTTP 回调或 Stream 进入 -> 转 Matrix Event；Matrix Event -> 飞书发消息 API

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Dict, Optional

import aiohttp

from src.config import FEISHU_APP_ID, FEISHU_APP_SECRET

logger = logging.getLogger(__name__)

FEISHU_TOKEN_URL = "https://open.feishu.cn/open_api/auth/v3/tenant_access_token/internal"
FEISHU_SEND_MSG_URL = "https://open.feishu.cn/open_api/im/v1/messages"


class FeishuBridge:
    """飞书与 Matrix 双向桥：收飞书事件发 Matrix、收 Matrix 事件发飞书。"""

    def __init__(
        self,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
    ):
        self._app_id = app_id or FEISHU_APP_ID or ""
        self._app_secret = app_secret or FEISHU_APP_SECRET or ""
        self._tenant_access_token: Optional[str] = None

    @property
    def is_configured(self) -> bool:
        return bool(self._app_id and self._app_secret)

    async def get_tenant_access_token(self) -> Optional[str]:
        """获取飞书 tenant_access_token，带简单内存缓存。"""
        if self._tenant_access_token:
            return self._tenant_access_token
        if not self._app_id or not self._app_secret:
            logger.warning("飞书未配置 FEISHU_APP_ID / FEISHU_APP_SECRET")
            return None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    FEISHU_TOKEN_URL,
                    json={"app_id": self._app_id, "app_secret": self._app_secret},
                    headers={"Content-Type": "application/json"},
                ) as resp:
                    if resp.status != 200:
                        logger.error("飞书 token 请求失败: %s %s", resp.status, await resp.text())
                        return None
                    data = await resp.json()
                    if data.get("code") != 0:
                        logger.error("飞书 token 返回错误: %s", data)
                        return None
                    self._tenant_access_token = data.get("tenant_access_token")
                    return self._tenant_access_token
        except Exception as e:
            logger.exception("飞书获取 token 异常: %s", e)
            return None

    async def send_message(
        self,
        receive_id: str,
        receive_id_type: str = "chat_id",
        msg_type: str = "text",
        content: Dict[str, Any] = None,
    ) -> Optional[str]:
        """
        调用飞书发送消息 API。
        receive_id: chat_id（群）或 open_id（用户）等
        receive_id_type: chat_id / open_id
        返回 message_id，失败返回 None。
        """
        token = await self.get_tenant_access_token()
        if not token:
            return None
        content = content or {}
        if msg_type == "text" and "text" not in content:
            content["text"] = ""
        # 飞书卡片 API 要求 interactive 的 content 为 JSON 字符串
        if msg_type == "interactive" and isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False)
        body = {
            "receive_id": receive_id,
            "msg_type": msg_type,
            "content": content,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{FEISHU_SEND_MSG_URL}?receive_id_type={receive_id_type}",
                    json=body,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                ) as resp:
                    if resp.status != 200:
                        logger.error("飞书发消息失败: %s %s", resp.status, await resp.text())
                        return None
                    data = await resp.json()
                    if data.get("code") != 0:
                        logger.error("飞书发消息返回错误: %s", data)
                        return None
                    return data.get("data", {}).get("message_id")
        except Exception as e:
            logger.exception("飞书发消息异常: %s", e)
            return None

    @staticmethod
    def parse_feishu_event(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        从飞书事件 payload 解析出 chat_id、发送者、消息类型与内容。
        支持常见 event v2 结构；返回 None 表示非消息类或解析失败。
        """
        event = payload.get("event") or payload
        msg = event.get("message") or event
        if not msg:
            return None
        chat_id = msg.get("chat_id") or event.get("chat_id")
        if not chat_id:
            return None
        message_type = msg.get("message_type", "text")
        content = msg.get("content")
        if isinstance(content, str):
            try:
                content = json.loads(content) if content.strip().startswith("{") else {"text": content}
            except json.JSONDecodeError:
                content = {"text": content}
        sender = (event.get("sender") or {}).get("sender_id") or event.get("sender_id") or {}
        open_id = sender.get("open_id") or sender.get("user_id") or ""

        return {
            "chat_id": chat_id,
            "message_type": message_type,
            "content": content or {},
            "open_id": open_id,
            "message_id": msg.get("message_id"),
            "raw_message": msg,
        }


async def handle_feishu_event(
    payload: Dict[str, Any],
    matrix_client: Any,
    room_manager: Any,
    translator: Any,
    user_mapper: Any,
    create_room_if_missing: bool = True,
) -> bool:
    """
    处理飞书事件：解析 -> 转 Matrix 格式 -> 查/建 Room 映射 -> 发送到 Matrix。
    create_room_if_missing 为 True 时，若 chat_id 尚无 room 则自动 create_room 并 set_room_mapping。
    """
    parsed = FeishuBridge.parse_feishu_event(payload)
    if not parsed:
        return False
    chat_id = parsed["chat_id"]
    msgtype, content = translator.feishu_event_to_matrix(
        {"message_type": parsed["message_type"], "content": parsed["content"], "message": parsed["raw_message"]}
    )
    body = content.get("body", "")
    room_id = room_manager.get_matrix_room_id(chat_id)
    if not room_id and create_room_if_missing and hasattr(matrix_client, "create_room"):
        room_id = await matrix_client.create_room(name=f"feishu-{chat_id[:12]}")
        if room_id:
            room_manager.set_room_mapping(chat_id, room_id)
    if not room_id:
        logger.warning("飞书 chat_id %s 尚无 Matrix room 映射，跳过", chat_id)
        return False
    # E7-S1：注入可审计字段（message_id、sender、receiver、timestamp）
    from src.core.audit import inject_audit_fields
    sender = parsed.get("open_id") or chat_id
    content_with_audit = inject_audit_fields(
        {"msgtype": "m.text", "body": body}, sender=sender, receiver=room_id
    )
    event_id = await matrix_client._send_custom(room_id, content_with_audit)
    if event_id:
        logger.info("飞书 -> Matrix 已转发 chat_id=%s room_id=%s", chat_id, room_id)
    return event_id is not None


async def handle_matrix_event(
    room_id: str,
    msgtype: str,
    content: Dict[str, Any],
    feishu_bridge: FeishuBridge,
    room_manager: Any,
    translator: Any,
) -> bool:
    """
    处理 Matrix 事件：查飞书 chat_id（可多个）-> 转飞书格式 -> 调用飞书发消息 API。
    共享房间时向所有关联 chat 发送。
    """
    chat_ids = getattr(room_manager, "get_feishu_chat_ids", None) and room_manager.get_feishu_chat_ids(room_id)
    if not chat_ids:
        chat_id = room_manager.get_feishu_chat_id(room_id)
        chat_ids = [chat_id] if chat_id else []
    if not chat_ids:
        logger.debug("Matrix room_id %s 无飞书 chat 映射，跳过", room_id)
        return False
    feishu_body = translator.matrix_event_to_feishu(room_id, msgtype, content)
    ok = False
    for chat_id in chat_ids:
        msg_id = await feishu_bridge.send_message(
            receive_id=chat_id,
            receive_id_type="chat_id",
            msg_type=feishu_body.get("msg_type", "text"),
            content=feishu_body.get("content", {}),
        )
        if msg_id:
            logger.info("Matrix -> 飞书 已转发 room_id=%s chat_id=%s", room_id, chat_id)
            ok = True
    return ok


async def handle_delivery_event(
    room_id: str,
    msgtype: str,
    content: Dict[str, Any],
    feishu_bridge: FeishuBridge,
    channel_adapter: Any,
) -> bool:
    """
    E2-S3：处理投递类事件。解析 semantic_type/target/payload -> 渠道适配层转飞书格式 -> 飞书 Open API 发送。
    E6-S3：记录投递开始与结果（delivered/failed），供运维排障查询。
    channel_adapter 需有 semantic_to_feishu_message(semantic_type, payload) -> {"msg_type", "content"}。
    """
    from src.core.delivery import is_delivery_event, parse_delivery_event
    from src.core.delivery_log import (
        record_delivery_start,
        record_delivery_done,
        STATUS_DELIVERED,
        STATUS_FAILED,
    )

    if not is_delivery_event(msgtype, content):
        return False
    parsed = parse_delivery_event(content)
    if not parsed:
        return False
    semantic_type, target, payload = parsed
    if target.get("channel") != "feishu":
        logger.debug("投递目标渠道非 feishu，跳过: %s", target.get("channel"))
        return False
    receive_id = target.get("receive_id")
    receive_id_type = target.get("receive_id_type", "chat_id")
    if not receive_id:
        return False

    delivery_id = record_delivery_start(
        semantic_type=semantic_type,
        target=target,
        payload_summary=(content.get("body") or "")[:200],
    )
    feishu_body = channel_adapter.semantic_to_feishu_message(semantic_type, payload)
    msg_id = await feishu_bridge.send_message(
        receive_id=receive_id,
        receive_id_type=receive_id_type,
        msg_type=feishu_body.get("msg_type", "text"),
        content=feishu_body.get("content", {}),
    )
    if msg_id:
        record_delivery_done(delivery_id, STATUS_DELIVERED, feishu_message_id=msg_id)
        logger.info("投递事件已发送到飞书 semantic_type=%s receive_id=%s delivery_id=%s", semantic_type, receive_id, delivery_id)
    else:
        record_delivery_done(delivery_id, STATUS_FAILED, error_reason="feishu_send_failed")
        logger.warning("投递事件发送失败 semantic_type=%s receive_id=%s delivery_id=%s", semantic_type, receive_id, delivery_id)
    return msg_id is not None


def make_matrix_sync_callback(
    feishu_bridge: FeishuBridge,
    room_manager: Any,
    translator: Any,
    channel_adapter: Optional[Any] = None,
    telegram_bridge: Optional[Any] = None,
) -> Callable[[str, str, Dict[str, Any]], Awaitable[None]]:
    """
    生成供 MatrixClient.start_sync_loop(on_event) 使用的回调：
    收到投递类事件则消费并调渠道适配层+飞书/Telegram API；否则按 Matrix->飞书 消息转发。
    """
    from src.core.delivery import is_delivery_event
    from src.bridge.telegram import handle_delivery_event as handle_telegram_delivery

    if channel_adapter is None:
        import src.channel_adapter as _adapter
        channel_adapter = _adapter

    async def on_matrix_event(room_id: str, msgtype: str, content: Dict[str, Any]) -> None:
        if is_delivery_event(msgtype, content or {}):
            # 处理投递事件：先尝试飞书，再尝试 Telegram
            await handle_delivery_event(room_id, msgtype, content or {}, feishu_bridge, channel_adapter)
            if telegram_bridge:
                await handle_telegram_delivery(room_id, msgtype, content or {}, telegram_bridge)
        else:
            await handle_matrix_event(room_id, msgtype, content or {}, feishu_bridge, room_manager, translator)

    return on_matrix_event
