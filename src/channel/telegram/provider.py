# Telegram Provider - 消息投递提供者

import logging
from typing import Any, Dict, List, Optional

from channel.telegram.client import TelegramClient

logger = logging.getLogger(__name__)


class TelegramProvider:
    """Telegram 消息投递 Provider。"""

    def __init__(self, token: str):
        self.client = TelegramClient(token)

    async def deliver(
        self,
        chat_id: str,
        message: str,
        semantic_type: str = "text",
        buttons: Optional[List[List[Dict[str, str]]]] = None,
        reply_to_message_id: Optional[int] = None,
    ) -> Optional[int]:
        """
        投递消息到 Telegram。

        Args:
            chat_id: Telegram 聊天 ID（用户 ID 或群组 ID）
            message: 消息文本
            semantic_type: 语义类型（用于渲染决策）
            buttons: 内联按钮 [[{"text": "...", "callback_data": "..."}, ...], ...]
            reply_to_message_id: 回复的消息 ID

        Returns:
            发送成功的消息 ID，失败返回 None
        """
        if buttons:
            message_id = await self.client.send_message_with_buttons(
                chat_id=chat_id,
                text=message,
                buttons=buttons,
            )
        else:
            message_id = await self.client.send_message(
                chat_id=chat_id,
                text=message,
                reply_to_message_id=reply_to_message_id,
            )

        if message_id:
            logger.info("Telegram 消息投递成功 chat_id=%s message_id=%s", chat_id, message_id)
        else:
            logger.warning("Telegram 消息投递失败 chat_id=%s", chat_id)

        return message_id

    async def answer_callback(
        self,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False,
    ) -> bool:
        """
        处理回调查询。
        """
        return await self.client.answer_callback_query(callback_query_id, text, show_alert)

    async def edit_message(
        self,
        chat_id: str,
        message_id: int,
        text: str,
        buttons: Optional[List[List[Dict[str, str]]]] = None,
    ) -> bool:
        """
        编辑已发送的消息。
        """
        reply_markup = None
        if buttons:
            reply_markup = {"inline_keyboard": buttons}

        return await self.client.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
        )


# 便捷函数：使用默认 token 创建 provider
_default_token: Optional[str] = None


def set_default_token(token: str) -> None:
    """设置默认的 Telegram Bot Token。"""
    global _default_token
    _default_token = token


def get_default_provider() -> Optional[TelegramProvider]:
    """获取默认的 Telegram Provider（需先设置 token）。"""
    if _default_token:
        return TelegramProvider(_default_token)
    return None
