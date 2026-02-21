# E2-S2：Telegram ↔ Matrix Bridge
# Telegram 事件经 Webhook 进入 -> 转 Matrix Event；Matrix Event -> Telegram 发消息 API

import logging
from typing import Any, Dict, Optional

from channel.telegram.client import TelegramClient
from channel.telegram.provider import TelegramProvider
from channel.telegram.render import semantic_to_telegram_message

logger = logging.getLogger(__name__)


class TelegramBridge:
    """Telegram 与 Matrix 双向桥：收 Telegram 事件发 Matrix、收 Matrix 事件发 Telegram。"""

    def __init__(
        self,
        token: Optional[str] = None,
        webhook_secret: Optional[str] = None,
    ):
        self._token = token
        self._webhook_secret = webhook_secret
        self._client: Optional[TelegramClient] = None
        self._provider: Optional[TelegramProvider] = None

    @property
    def is_configured(self) -> bool:
        return bool(self._token)

    @property
    def client(self) -> Optional[TelegramClient]:
        if not self._client and self._token:
            self._client = TelegramClient(self._token)
        return self._client

    @property
    def provider(self) -> Optional[TelegramProvider]:
        if not self._provider and self._token:
            self._provider = TelegramProvider(self._token)
        return self._provider

    def verify_secret(self, secret: str) -> bool:
        """验证 Webhook 秘钥。"""
        if not self._webhook_secret:
            return True  # 未配置则跳过验证
        return secret == self._webhook_secret


async def handle_telegram_event(
    payload: Dict[str, Any],
    matrix_client: Any,
    room_manager: Any,
) -> bool:
    """
    处理 Telegram 事件：解析 -> 转 Matrix 格式 -> 发送到 Matrix。
    支持 message 和 callback_query 类型。
    """
    from core.translator import TelegramEventTranslator

    if not payload.get("message") and not payload.get("callback_query"):
        return False

    # 处理回调查询
    if payload.get("callback_query"):
        return await handle_telegram_callback(
            payload["callback_query"],
            matrix_client,
        )

    # 处理普通消息
    msg = payload.get("message", {})
    chat = msg.get("chat", {})
    chat_id = str(chat.get("id"))
    user = msg.get("from", {})
    user_id = str(user.get("id")) if user else ""
    text = msg.get("text", "")
    message_id = msg.get("message_id")

    if not chat_id:
        return False

    # 获取或创建 Matrix room
    room_id = room_manager.get_matrix_room_id(f"telegram:{chat_id}")
    if not room_id:
        # 尝试创建 room（需要在 Matrix 中先创建）
        logger.warning("Telegram chat_id %s 尚无 Matrix room 映射，跳过", chat_id)
        return False

    # 转换为 Matrix 消息格式
    translator = TelegramEventTranslator()
    matrix_content = translator.telegram_to_matrix(msg)

    # 发送到 Matrix
    from core.audit import inject_audit_fields
    content_with_audit = inject_audit_fields(
        matrix_content,
        sender=user_id or f"telegram:{chat_id}",
        receiver=room_id,
    )
    event_id = await matrix_client._send_custom(room_id, content_with_audit)
    if event_id:
        logger.info("Telegram -> Matrix 已转发 chat_id=%s room_id=%s", chat_id, room_id)
    return event_id is not None


async def handle_telegram_callback(
    callback: Dict[str, Any],
    matrix_client: Any,
) -> bool:
    """
    处理 Telegram 回调查询（按钮点击）。
    """
    query_id = callback.get("id")
    data = callback.get("data", "")
    message = callback.get("message", {})
    chat = message.get("chat", {})
    chat_id = str(chat.get("id"))
    message_id = message.get("message_id")

    if not query_id:
        return False

    # 获取 Telegram provider 回答回调
    from config import TELEGRAM_BOT_TOKEN
    if TELEGRAM_BOT_TOKEN:
        provider = TelegramProvider(TELEGRAM_BOT_TOKEN)
        await provider.answer_callback(query_id, text="处理中...")

    # 可以在这里将回调转发给业务逻辑或直接更新 Matrix 消息
    logger.info("Telegram callback: query_id=%s data=%s", query_id, data)
    return True


async def handle_delivery_event(
    room_id: str,
    msgtype: str,
    content: Dict[str, Any],
    telegram_bridge: TelegramBridge,
) -> bool:
    """
    E2-S3：处理投递类事件。解析 semantic_type/target/payload -> 渠道适配层转 Telegram 格式 -> Telegram API 发送。
    """
    from core.delivery import is_delivery_event, parse_delivery_event
    from core.delivery_log import (
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
    if target.get("channel") != "telegram":
        logger.debug("投递目标渠道非 telegram，跳过: %s", target.get("channel"))
        return False
    chat_id = target.get("receive_id")
    if not chat_id:
        return False

    provider = telegram_bridge.provider
    if not provider:
        logger.warning("Telegram 未配置，跳过投递")
        return False

    # 转换为 Telegram 消息格式
    tg_message = semantic_to_telegram_message(semantic_type, payload)
    text = tg_message.get("text", "")
    buttons = tg_message.get("buttons")

    # 记录投递开始
    delivery_id = record_delivery_start(
        semantic_type=semantic_type,
        target=target,
        payload_summary=content.get("body", "")[:200],
    )

    # 发送消息
    message_id = await provider.deliver(
        chat_id=chat_id,
        message=text,
        semantic_type=semantic_type,
        buttons=buttons if buttons else None,
    )

    if message_id:
        record_delivery_done(delivery_id, STATUS_DELIVERED)
        logger.info("投递事件已发送到 Telegram semantic_type=%s chat_id=%s delivery_id=%s", semantic_type, chat_id, delivery_id)
        return True
    else:
        record_delivery_done(delivery_id, STATUS_FAILED, error_reason="telegram_send_failed")
        logger.warning("投递事件发送失败 semantic_type=%s chat_id=%s delivery_id=%s", semantic_type, chat_id, delivery_id)
        return False


# Telegram 事件转换器（简化版）
class TelegramEventTranslator:
    """Telegram 消息转 Matrix 格式。"""

    def telegram_to_matrix(self, telegram_msg: Dict[str, Any]) -> Dict[str, Any]:
        """将 Telegram 消息转换为 Matrix 消息格式。"""
        msgtype = telegram_msg.get("type", "text")
        text = telegram_msg.get("text", "")

        # 处理 /start 命令
        if text and text.startswith("/start"):
            return {
                "msgtype": "m.text",
                "body": "/start",
                "format": "org.matrix.html",
                "formatted_body": "<code>/start</code>",
            }

        # 处理普通文本
        return {
            "msgtype": "m.text",
            "body": text,
            "format": "org.matrix.html",
            "formatted_body": self._escape_html(text),
        }

    def _escape_html(self, text: str) -> str:
        """转义 HTML 特殊字符。"""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
