# Telegram Bot API 客户端
# 用于发送消息和处理回调

import json
import logging
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org"


class TelegramClient:
    """Telegram Bot API 异步客户端。"""

    def __init__(self, token: str):
        self.token = token
        self.api_url = f"{TELEGRAM_API_URL}/bot{token}"

    async def _request(self, method: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """发送 API 请求。"""
        url = f"{self.api_url}/{method}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data or {}, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    result = await resp.json()
                    if not result.get("ok"):
                        logger.error("Telegram API 错误: %s", result)
                        return {"ok": False, "error": result.get("description", "Unknown error")}
                    return result
        except Exception as e:
            logger.exception("Telegram 请求异常: %s", e)
            return {"ok": False, "error": str(e)}

    async def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: str = "Markdown",
        reply_markup: Optional[Dict[str, Any]] = None,
        reply_to_message_id: Optional[int] = None,
    ) -> Optional[int]:
        """
        发送文本消息。
        返回 message_id，失败返回 None。
        """
        data: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup:
            data["reply_markup"] = reply_markup
        if reply_to_message_id:
            data["reply_to_message_id"] = reply_to_message_id

        result = await self._request("sendMessage", data)
        if result.get("ok"):
            return result["result"]["message_id"]
        return None

    async def send_message_with_buttons(
        self,
        chat_id: str,
        text: str,
        buttons: List[List[Dict[str, str]]],
        parse_mode: str = "Markdown",
    ) -> Optional[int]:
        """
        发送带内联按钮的消息。
        buttons: [[{"text": "按钮文本", "callback_data": "回调数据"}, ...], ...]
        """
        reply_markup = {"inline_keyboard": buttons}
        return await self.send_message(chat_id, text, parse_mode, reply_markup)

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False,
    ) -> bool:
        """
        回答回调查询（消除 Loading 状态）。
        """
        data: Dict[str, Any] = {
            "callback_query_id": callback_query_id,
        }
        if text:
            data["text"] = text
        if show_alert:
            data["show_alert"] = show_alert

        result = await self._request("answerCallbackQuery", data)
        return result.get("ok", False)

    async def edit_message_text(
        self,
        chat_id: str,
        message_id: int,
        text: str,
        parse_mode: str = "Markdown",
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        编辑消息文本。
        """
        data: Dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup:
            data["reply_markup"] = reply_markup

        result = await self._request("editMessageText", data)
        return result.get("ok", False)

    async def get_chat(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """获取聊天信息。"""
        result = await self._request("getChat", {"chat_id": chat_id})
        if result.get("ok"):
            return result["result"]
        return None

    async def set_webhook(
        self,
        url: str,
        secret_token: Optional[str] = None,
        allowed_updates: Optional[List[str]] = None,
    ) -> bool:
        """
        设置 Webhook。
        """
        data: Dict[str, Any] = {
            "url": url,
            "allowed_updates": allowed_updates or ["message", "callback_query"],
        }
        if secret_token:
            data["secret_token"] = secret_token

        result = await self._request("setWebhook", data)
        return result.get("ok", False)

    async def delete_webhook(self) -> bool:
        """删除 Webhook。"""
        result = await self._request("deleteWebhook")
        return result.get("ok", False)

    async def get_webhook_info(self) -> Optional[Dict[str, Any]]:
        """获取 Webhook 信息。"""
        result = await self._request("getWebhookInfo")
        if result.get("ok"):
            return result["result"]
        return None

    async def get_me(self) -> Optional[Dict[str, Any]]:
        """获取 Bot 信息。"""
        result = await self._request("getMe")
        if result.get("ok"):
            return result["result"]
        return None
